"""Bygger kvartalsafregnings-regnearket ud fra de gemte fakturalinjer.

Layoutet følger Kvartalsafregning_..._Emballage_Galic.xlsx: ét faneblad pr.
kvartal med kolonnerne Dato…Note, en TOTAL-række med formler, og til sidst et
"Oversigt"-faneblad der summerer på tværs. Totalerne skrives som formler, så
arket bliver ved med at regne hvis man retter i det bagefter.
"""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# genudstilles, så eksisterende kald stadig virker
from services.packaging_helpers import quarter_of  # noqa: F401

# Overskrifterne brydes over to linjer. Autofilterets knap lægger sig i højre
# ende af overskriftsfeltet, så en lang etiket på én linje bliver dækket af den.
HEADERS = [
    "Dato", "Faktura", "Kvartal", "Vare", "Antal", "Tom flaske\nkg",
    "Glas i alt\nkg", "Pap pr.\nflaske kg", "Pap i alt\nkg", "Note",
]
COL_WIDTHS = [12, 13, 11, 38, 10, 13, 13, 16, 13, 30]
# Tal højrestilles, tekst venstrestilles, datoen centreres
COL_ALIGN = ["center", "left", "center", "left", "right", "right",
             "right", "right", "right", "left"]

NAVY = "1F3864"
HEADER_FILL = PatternFill("solid", fgColor=NAVY)
HEADER_FONT = Font(bold=True, color="FFFFFF", size=10)
ZEBRA_FILL = PatternFill("solid", fgColor="F5F8FC")
TOTAL_FILL = PatternFill("solid", fgColor="DDEBF7")
TOTAL_FONT = Font(bold=True, size=11)
MISSING_FILL = PatternFill("solid", fgColor="FFF7E6")
BODY_FONT = Font(size=10)
TITLE_FONT = Font(bold=True, size=14, color="1F3864")
SUBTITLE_FONT = Font(size=10, color="7F7F7F")
OK_FONT = Font(size=10, bold=True, color="1E7B4D")
MISSING_FONT = Font(size=10, bold=True, color="B45309")

HAIR = Side(style="hair", color="D6DEE8")
MEDIUM_TOP = Side(style="thin", color="1F3864")
BORDER = Border(left=HAIR, right=HAIR, top=HAIR, bottom=HAIR)
TOTAL_BORDER = Border(left=HAIR, right=HAIR, top=MEDIUM_TOP, bottom=HAIR)

KG3 = "#,##0.000"
KG4 = "0.0000"
COUNT_FMT = "#,##0"
# Små bogstaver er den kanoniske form (det Excel selv skriver). Med store
# bogstaver tolker nogle fremvisere koden forkert og viser dagnummeret.
DATE_FMT = "dd-mm-yyyy"
HEADER_HEIGHT = 32
ROW_HEIGHT = 18


def _style_cell(cell, align="left", fmt=None, zebra=False, missing=False,
                total=False):
    """Samler den styling der ellers skulle gentages på hver eneste celle."""
    cell.font = TOTAL_FONT if total else BODY_FONT
    cell.alignment = Alignment(horizontal=align, vertical="center")
    cell.border = TOTAL_BORDER if total else BORDER
    if fmt:
        cell.number_format = fmt
    if total:
        cell.fill = TOTAL_FILL
    elif missing:
        cell.fill = MISSING_FILL
    elif zebra:
        cell.fill = ZEBRA_FILL


def _quarter_sort_key(q: str):
    try:
        qq, yy = q.split()
        return (int(yy), int(qq[1:]))
    except Exception:
        return (0, 0)


def _style_header(ws, headers=HEADERS, widths=COL_WIDTHS, row=1):
    for col, (head, width) in enumerate(zip(headers, widths), start=1):
        cell = ws.cell(row=row, column=col, value=head)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   wrap_text=True)
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.row_dimensions[row].height = HEADER_HEIGHT
    ws.sheet_view.showGridLines = False


def _write_quarter_sheet(wb: Workbook, quarter: str, rows: list[dict]) -> int:
    """Skriver ét kvartalsfaneblad. Returnerer rækkenummeret på TOTAL-rækken."""
    ws = wb.create_sheet(title=quarter)
    _style_header(ws)
    ws.freeze_panes = "A2"

    r = 2
    for i, row in enumerate(rows):
        missing = row.get("glass_kg") is None
        zebra = i % 2 == 1
        vals = [
            (row.get("invoice_date"), DATE_FMT),
            (row.get("invoice_number"), None),
            (quarter, None),
            (row.get("item_name"), None),
            (row.get("quantity"), COUNT_FMT),
            (row.get("glass_kg"), KG3),
            # Regnes i arket, så tallene følger med hvis man retter antal eller vægt
            (None if missing else f"=E{r}*F{r}", KG3),
            (row.get("carton_kg"), KG4),
            (f"=E{r}*H{r}", KG3),
            (row.get("note"), None),
        ]
        for c, (value, fmt) in enumerate(vals, start=1):
            cell = ws.cell(row=r, column=c, value=value)
            _style_cell(cell, align=COL_ALIGN[c - 1], fmt=fmt,
                        zebra=zebra, missing=missing)
        # Uden en statuskolonne er den tonede række markeringen af at
        # flaskevægten mangler
        ws.row_dimensions[r].height = ROW_HEIGHT
        r += 1

    last = r - 1
    total_row = r
    ws.cell(row=total_row, column=1, value="TOTAL")
    ws.cell(row=total_row, column=3, value=quarter)
    if last >= 2:
        ws.cell(row=total_row, column=5, value=f"=SUM(E2:E{last})")
        # Samme spærre som i dit eget ark: mangler der en vægt, må totalen ikke
        # præsenteres som et facit. Der tælles tomme flaskevægte, siden der
        # ikke længere er en statuskolonne at se efter "MANGLER" i.
        ws.cell(row=total_row, column=7,
                value=f'=IF(COUNTBLANK(F2:F{last})>0,"UFULDSTÆNDIG",SUM(G2:G{last}))')
        ws.cell(row=total_row, column=9, value=f"=SUM(I2:I{last})")
    else:
        for c in (5, 7, 9):
            ws.cell(row=total_row, column=c, value=0)
    for c in range(1, len(HEADERS) + 1):
        fmt = COUNT_FMT if c == 5 else (KG3 if c in (7, 9) else None)
        _style_cell(ws.cell(row=total_row, column=c),
                    align=COL_ALIGN[c - 1], fmt=fmt, total=True)
    ws.row_dimensions[total_row].height = 20

    if last >= 2:
        ws.auto_filter.ref = f"A1:J{last}"
    return total_row


OUT_HEADERS = ["Kvartal", "Vare", "Antal", "Tom flaske\nkg", "Glas i alt\nkg",
               "Pap pr.\nflaske kg", "Pap i alt\nkg", "Note"]
OUT_WIDTHS = [11, 38, 10, 13, 13, 16, 13, 28]
OUT_ALIGN = ["center", "left", "right", "right", "right", "right", "right", "left"]


def _write_outbound_sheet(wb: Workbook, rows_by_quarter: dict) -> tuple:
    """Én samlet side med alt der er solgt ud af huset, på tværs af kvartaler.
    Returnerer (arknavn, sidste datarække) så Oversigt kan summere herfra."""
    ws = wb.create_sheet(title="Ud af huset")
    _style_header(ws, OUT_HEADERS, OUT_WIDTHS)
    ws.freeze_panes = "A2"

    r = 2
    i = 0
    for quarter in sorted(rows_by_quarter, key=_quarter_sort_key):
        for row in rows_by_quarter[quarter]:
            missing = row.get("glass_kg") is None
            zebra = i % 2 == 1
            vals = [
                (quarter, None),
                (row.get("item_name"), None),
                (row.get("quantity"), COUNT_FMT),
                (row.get("glass_kg"), KG3),
                (None if missing else f"=C{r}*D{r}", KG3),
                (row.get("carton_kg"), KG4),
                (f"=C{r}*F{r}", KG3),
                (row.get("note"), None),
            ]
            for c, (value, fmt) in enumerate(vals, start=1):
                _style_cell(ws.cell(row=r, column=c, value=value),
                            align=OUT_ALIGN[c - 1], fmt=fmt,
                            zebra=zebra, missing=missing)
            ws.row_dimensions[r].height = ROW_HEIGHT
            r += 1
            i += 1

    last = r - 1
    if last >= 2:
        ws.cell(row=r, column=1, value="TOTAL")
        ws.cell(row=r, column=3, value=f"=SUM(C2:C{last})")
        ws.cell(row=r, column=5, value=f"=SUM(E2:E{last})")
        ws.cell(row=r, column=7, value=f"=SUM(G2:G{last})")
        for c in range(1, len(OUT_HEADERS) + 1):
            fmt = COUNT_FMT if c == 3 else (KG3 if c in (5, 7) else None)
            _style_cell(ws.cell(row=r, column=c), align=OUT_ALIGN[c - 1],
                        fmt=fmt, total=True)
        ws.row_dimensions[r].height = 20
        ws.auto_filter.ref = f"A1:H{last}"
    else:
        cell = ws.cell(row=2, column=1,
                       value="Der er endnu ikke registreret salg ud af huset.")
        cell.font = SUBTITLE_FONT

    return "Ud af huset", last


OVERVIEW_HEADERS = [
    "Kvartal",
    "Flasker", "Glas kg", "Pap kg",
    "Flasker", "Glas kg", "Pap kg",
    "Flasker", "Glas kg", "Pap kg",
    "Bemærkning",
]
OVERVIEW_WIDTHS = [12, 11, 12, 11, 11, 12, 11, 11, 12, 11, 46]
# Grupper over overskriftsrækken: (starttekst, antal kolonner, farve)
OVERVIEW_GROUPS = [
    ("", 1, None),
    ("Importeret fra Galić", 3, "1F3864"),
    ("Solgt ud af huset", 3, "B45309"),
    ("Tilbage i huset", 3, "1E7B4D"),
    ("", 1, None),
]


def _write_overview(wb: Workbook, totals: list[tuple[str, int]],
                    out_sheet: str, out_last_row: int):
    ws = wb.create_sheet(title="Oversigt", index=len(wb.worksheets))
    ws.sheet_view.showGridLines = False

    ws.merge_cells("A1:K1")
    t = ws["A1"]
    t.value = "Kvartalsafregning – emballage"
    t.font = TITLE_FONT
    t.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 24

    ws.merge_cells("A2:K2")
    sub = ws["A2"]
    sub.value = ("Importeret glas og pap fra Galić, minus det kunderne har taget "
                 "med hjem. Det der er tilbage, er drukket i huset.")
    sub.font = SUBTITLE_FONT
    sub.alignment = Alignment(horizontal="left", vertical="center")

    # Gruppebånd over kolonneoverskrifterne
    col = 1
    for label, span, color in OVERVIEW_GROUPS:
        if label:
            ws.merge_cells(start_row=4, start_column=col,
                           end_row=4, end_column=col + span - 1)
            cell = ws.cell(row=4, column=col, value=label)
            cell.fill = PatternFill("solid", fgColor=color)
            cell.font = Font(bold=True, color="FFFFFF", size=10)
            cell.alignment = Alignment(horizontal="center", vertical="center")
        col += span
    ws.row_dimensions[4].height = 20

    for c, (head, width) in enumerate(zip(OVERVIEW_HEADERS, OVERVIEW_WIDTHS), start=1):
        cell = ws.cell(row=5, column=c, value=head)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   wrap_text=True)
        ws.column_dimensions[get_column_letter(c)].width = width
    ws.row_dimensions[5].height = 22
    ws.freeze_panes = "B6"

    align = ["center"] + ["right"] * 9 + ["left"]

    # Områder på "Ud af huset"-arket, som der summeres hen over pr. kvartal
    has_out = out_last_row >= 2
    q_rng = f"'{out_sheet}'!$A$2:$A${out_last_row}" if has_out else None
    n_rng = f"'{out_sheet}'!$C$2:$C${out_last_row}" if has_out else None
    g_rng = f"'{out_sheet}'!$E$2:$E${out_last_row}" if has_out else None
    p_rng = f"'{out_sheet}'!$G$2:$G${out_last_row}" if has_out else None

    r = 6
    for i, (quarter, total_row) in enumerate(totals):
        ref = f"'{quarter}'!"
        vals = [
            (quarter, None),
            (f"={ref}E{total_row}", COUNT_FMT),
            (f"={ref}G{total_row}", KG3),
            (f"={ref}I{total_row}", KG3),
            (f'=SUMIF({q_rng},$A{r},{n_rng})' if has_out else 0, COUNT_FMT),
            (f'=SUMIF({q_rng},$A{r},{g_rng})' if has_out else 0, KG3),
            (f'=SUMIF({q_rng},$A{r},{p_rng})' if has_out else 0, KG3),
            (f"=B{r}-E{r}", COUNT_FMT),
            # Mangler en flaskevægt, står importtotalen som tekst – så kan der
            # ikke trækkes fra, og feltet siger det i stedet for at vise et
            # forkert tal.
            (f'=IF(ISNUMBER(C{r}),C{r}-F{r},"UFULDSTÆNDIG")', KG3),
            (f"=D{r}-G{r}", KG3),
            # Bemærkningen siger med ord det statuskolonnen sagde med et flag
            (f'=IF(ISNUMBER(I{r}),"Alle glasvægte kendt","Mangler flaskevægt på en eller flere varer")', None),
        ]
        for c, (value, fmt) in enumerate(vals, start=1):
            _style_cell(ws.cell(row=r, column=c, value=value),
                        align=align[c - 1], fmt=fmt, zebra=i % 2 == 1)
        # Nettotallene er pointen med arket, så de står med fed
        for c in (8, 9, 10):
            ws.cell(row=r, column=c).font = Font(size=10, bold=True)
        ws.row_dimensions[r].height = ROW_HEIGHT
        r += 1

    last = r - 1
    tr = r
    ws.cell(row=tr, column=1, value="TOTAL")
    if last >= 6:
        # SUM springer selv tekst som "UFULDSTÆNDIG" over og tager negative tal
        # med – og negative forekommer, når et kvartal sælger af tidligere lager.
        for col_ in range(2, 11):
            letter = get_column_letter(col_)
            ws.cell(row=tr, column=col_, value=f"=SUM({letter}6:{letter}{last})")
    for c in range(1, 12):
        fmt = COUNT_FMT if c in (2, 5, 8) else (KG3 if 2 < c < 11 else None)
        _style_cell(ws.cell(row=tr, column=c), align=align[c - 1],
                    fmt=fmt, total=True)
    ws.row_dimensions[tr].height = 22

    note = ws.cell(row=tr + 2, column=1,
                   value="Tilbage i huset = importeret minus det kunderne har taget med hjem.")
    note.font = SUBTITLE_FONT


def build_workbook(rows_by_quarter: dict[str, list[dict]],
                   outbound_by_quarter: dict[str, list[dict]] | None = None) -> bytes:
    """rows_by_quarter: importerede linjer pr. kvartal.
    outbound_by_quarter: solgt ud af huset pr. kvartal. -> xlsx-bytes."""
    outbound_by_quarter = outbound_by_quarter or {}
    wb = Workbook()
    wb.remove(wb.active)
    # Totalerne er formler uden gemt resultat, så Excel skal regne ved åbning
    wb.calculation.fullCalcOnLoad = True

    # Et kvartal kan have salg ud af huset uden at der er importeret noget i
    # netop det kvartal (lager fra tidligere). Det skal stadig med i Oversigt,
    # ellers bliver de flasker aldrig trukket fra.
    quarters = sorted(set(rows_by_quarter) | set(outbound_by_quarter),
                      key=_quarter_sort_key)

    totals = []
    for quarter in quarters:
        total_row = _write_quarter_sheet(wb, quarter,
                                         rows_by_quarter.get(quarter, []))
        totals.append((quarter, total_row))

    if not totals:
        ws = wb.create_sheet(title="Ingen data")
        ws["A1"] = "Der er endnu ingen linjer at eksportere."

    out_sheet, out_last = _write_outbound_sheet(wb, outbound_by_quarter)
    _write_overview(wb, totals, out_sheet, out_last)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
