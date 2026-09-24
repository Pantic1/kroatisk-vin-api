"""Små hjælpefunktioner til emballage-modulet.

Ligger for sig, fordi routeren har brug for dem ved hver forespørgsel, mens
resten af emballage-koden trækker openpyxl og pdfplumber med sig. Her er der
kun standardbiblioteket.
"""

from __future__ import annotations

import re
import unicodedata


def quarter_of(dt) -> str | None:
    """datetime -> 'Q3 2026' (almindelige kalenderkvartaler)."""
    if not dt:
        return None
    return f"Q{(dt.month - 1) // 3 + 1} {dt.year}"


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
