"""Udtræk af varelinjer fra Galićs pakirna lista / følgeseddel (PDF).

Layoutet ser sådan ud:

    Dokument: ROT-EUR 41/01/011 od 23.09.2025.
    ...
    Rbr./No.  Artikal/Item                     Količina/Quantity   Jmj/Unit
    1   0108  GRAŠEVINA 0,75l 2024.                     90,000     kom
    2   0109  SAUVIGNON 0,75l 2024.                    120,000     kom

Tal står i europæisk format ("90,000" = 90, "1.168,57" = 1168,57).
Dokumentnummeret i regnearkets Faktura-kolonne er delen efter "ROT-EUR",
altså "41/01/011".
"""

from __future__ import annotations

import io
import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher

import pdfplumber

# Enheder der kan stå sidst på en varelinje (kom = stk på kroatisk)
UNIT_RE = r"(?:kom|kos|kpl|pcs|stk|st|kar|ltr|l)"

# "1  0108  GRAŠEVINA 0,75l 2024.   90,000  kom"
LINE_WITH_UNIT_RE = re.compile(
    rf"^\s*(\d{{1,3}})\s+(\d{{3,6}})\s+(.+?)\s+([\d.,]+)\s+{UNIT_RE}\.?\s*$",
    re.IGNORECASE,
)
# Samme, men uden enhed til sidst
LINE_NO_UNIT_RE = re.compile(
    r"^\s*(\d{1,3})\s+(\d{3,6})\s+(.+?)\s+(\d[\d.,]*)\s*$"
)

DOC_RE = re.compile(
    r"Dokument\s*:?\s*(?:ROT-?EUR\s*)?([0-9]{1,4}/[0-9]{1,3}/[0-9]{1,4})",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b")
PACKAGES_RE = re.compile(r"Br\.\s*paketa\s*:?\s*(\d+)", re.IGNORECASE)

# Linjer der aldrig er varelinjer
SKIP_MARKERS = (
    "bruto", "neto", "ukupno", "total", "pakirna", "rbr", "artikal",
    "količina", "quantity", "pošiljatelj", "primatelj", "dokument",
)


def parse_number(raw: str):
    """'90,000' -> 90.0, '1.168,57' -> 1168.57, '1,303' -> 1.303.

    Europæisk format: punktum er tusindtalsseparator, komma er decimaltegn.
    """
    if raw is None:
        return None
    s = str(raw).strip().replace(" ", "").replace(" ", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _is_skip_line(line: str) -> bool:
    low = line.lower()
    return any(m in low for m in SKIP_MARKERS)


def extract_text(data: bytes) -> str:
    """Al tekst fra PDF'en, side for side."""
    out = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            out.append(page.extract_text() or "")
    return "\n".join(out)


def parse_packing_list(data: bytes) -> dict:
    """Læs en Galić-følgeseddel og returnér hoved + varelinjer.

    Kaster ValueError hvis PDF'en ikke indeholder tekst (typisk et scannet
    billede), så kaldet kan give brugeren en forståelig besked.
    """
    text = extract_text(data)
    if not text.strip():
        raise ValueError(
            "PDF'en indeholder ingen tekst – den er sandsynligvis et scannet "
            "billede. Indtast linjerne manuelt, eller bed Galić om en digital PDF."
        )

    lines = [l for l in (ln.rstrip() for ln in text.splitlines()) if l.strip()]

    # ---- hoved ----
    doc_number = None
    m = DOC_RE.search(text)
    if m:
        doc_number = m.group(1)

    doc_date = None
    # Datoen ved siden af dokumentnummeret ("... od 23.09.2025.") er den rigtige;
    # ellers tages den første dato på siden.
    date_search = text[m.end():m.end() + 60] if m else ""
    dm = DATE_RE.search(date_search) or DATE_RE.search(text)
    if dm:
        day, month, year = (int(x) for x in dm.groups())
        try:
            doc_date = datetime(year, month, day)
        except ValueError:
            doc_date = None

    packages = None
    pm = PACKAGES_RE.search(text)
    if pm:
        packages = int(pm.group(1))

    # ---- varelinjer ----
    items = []
    for raw_line in lines:
        if _is_skip_line(raw_line):
            continue
        m2 = LINE_WITH_UNIT_RE.match(raw_line) or LINE_NO_UNIT_RE.match(raw_line)
        if not m2:
            continue
        line_no, code, name, qty_raw = m2.groups()
        qty = parse_number(qty_raw)
        if qty is None:
            continue
        name = re.sub(r"\s+", " ", name).strip(" .")
        if not name:
            continue
        items.append({
            "line_no": int(line_no),
            "article_code": code,
            "item_name": name,
            "quantity": int(round(qty)),
            "raw_quantity": qty,
        })

    # Numrene skal løbe 1,2,3… – ellers har vi fanget noget der ikke er varelinjer
    items.sort(key=lambda i: i["line_no"])

    return {
        "invoice_number": doc_number,
        "invoice_date": doc_date.isoformat() if doc_date else None,
        "packages": packages,
        "items": items,
        "raw_text": text,
    }


# ---------------------------------------------------------------
# Matchning mod emballage-stamdata
# ---------------------------------------------------------------

def normalize(s: str) -> str:
    """Slår accenter, store bogstaver og tegnsætning sammen, så
    'GRAŠEVINA 0,75l 2024.' og 'Graševina 0,75L 2024' bliver ens."""
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    # đ/Đ har ingen kombinerende accent
    s = s.replace("đ", "d").replace("Đ", "D")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _name_score(a: str, b: str) -> float:
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    overlap = len(ta & tb) / max(len(ta | tb), 1)
    return max(ratio, (ratio + overlap) / 2)


def match_material(item: dict, materials: list) -> tuple:
    """Find den bedste stamdata-række til en fakturalinje.

    Returnerer (material, confidence, how) hvor how er 'code', 'name' eller None.
    Varenummer vinder altid over navn – det er leverandørens egen nøgle.
    """
    code = (item.get("article_code") or "").strip().lstrip("0") or None
    if code:
        for mat in materials:
            mc = (mat.article_code or "").strip().lstrip("0")
            if mc and mc == code:
                return mat, 1.0, "code"

    best, best_score = None, 0.0
    for mat in materials:
        candidates = [mat.name]
        if mat.match_text:
            candidates += [c for c in mat.match_text.split(";") if c.strip()]
        score = max(_name_score(item.get("item_name", ""), c) for c in candidates)
        if score > best_score:
            best, best_score = mat, score

    if best is not None and best_score >= 0.62:
        return best, round(best_score, 3), "name"
    return None, round(best_score, 3), None
