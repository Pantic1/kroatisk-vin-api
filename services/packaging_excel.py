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

HEADERS = [
    "Dato", "Faktura", "Kvartal", "Vare", "Antal", "Tom flaske kg",
    "Glas i alt kg", "Pap pr. flaske kg", "Pap i alt kg", "Status", "Note",
]
COL_WIDTHS = [12, 14, 10, 36, 9, 14, 14, 17, 13, 11, 28]

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TOTAL_FILL = PatternFill("solid", fgColor="DDEBF7")
TOTAL_FONT = Font(bold=True)
MISSING_FILL = PatternFill("solid", fgColor="FFF2CC")
TITLE_FONT = Font(bold=True, size=14)
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

KG3 = "0.000"
KG4 = "0.0000"
DATE_FMT = "DD-MM-YYYY"


def quarter_of(dt) -> str | None:
    """datetime -> 'Q3 2026' (almindelige kalenderkvartaler)."""
    if not dt:
        return None
    return f"Q{(dt.month - 1) // 3 + 1} {dt.year}"


def _quarter_sort_key(q: str):
    try:
        qq, yy = q.split()
        return (int(yy), int(qq[1:]))
    except Exception:
        return (0, 0)


def _style_header(ws):
    for col, (head, width) in enumerate(zip(HEADERS, COL_WIDTHS), start=1):
        cell = ws.cell(row=1, column=col, value=head)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   wrap_text=True)
        cell.border = BORDER
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"


def _write_quarter_sheet(wb: Workbook, quarter: str, rows: list[dict]) -> int:
    """Skriver ét kvartalsfaneblad. Returnerer rækkenummeret på TOTAL-rækken."""
    ws = wb.create_sheet(title=quarter)
    _style_header(ws)

    r = 2
    for row in rows:
        missing = row.get("glass_kg") is None
        ws.cell(row=r, column=1, value=row.get("invoice_date")).number_format = DATE_FMT
        ws.cell(row=r, column=2, value=row.get("invoice_number"))
        ws.cell(row=r, column=3, value=quarter)
        ws.cell(row=r, column=4, value=row.get("item_name"))
        ws.cell(row=r, column=5, value=row.get("quantity"))
        ws.cell(row=r, column=6, value=row.get("glass_kg")).number_format = KG3
        # Regnes i arket, så tallene følger med hvis man retter antal eller vægt
        g = ws.cell(row=r, column=7,
                    value=None if missing else f"=E{r}*F{r}")
        g.number_format = KG3
        ws.cell(row=r, column=8, value=row.get("carton_kg")).number_format = KG4
        ws.cell(row=r, column=9, value=f"=E{r}*H{r}").number_format = KG3
        ws.cell(row=r, column=10, value="MANGLER" if missing else "OK")
        ws.cell(row=r, column=11, value=row.get("note"))

        for c in range(1, len(HEADERS) + 1):
            ws.cell(row=r, column=c).border = BORDER
        if missing:
            for c in range(1, len(HEADERS) + 1):
                ws.cell(row=r, column=c).fill = MISSING_FILL
        r += 1

    last = r - 1
    total_row = r
    ws.cell(row=total_row, column=1, value="TOTAL")
    ws.cell(row=total_row, column=3, value=quarter)
    if last >= 2:
        ws.cell(row=total_row, column=5, value=f"=SUM(E2:E{last})")
        # Samme spærre som i dit eget ark: mangler der en vægt, må totalen ikke
        # præsenteres som et facit.
        ws.cell(row=total_row, column=7,
                value=f'=IF(COUNTIF(J2:J{last},"MANGLER")>0,"UFULDSTÆNDIG",SUM(G2:G{last}))')
        ws.cell(row=total_row, column=9, value=f"=SUM(I2:I{last})")
    else:
        ws.cell(row=total_row, column=5, value=0)
        ws.cell(row=total_row, column=7, value=0)
        ws.cell(row=total_row, column=9, value=0)
    ws.cell(row=total_row, column=7).number_format = KG3
    ws.cell(row=total_row, column=9).number_format = KG3
    for c in range(1, len(HEADERS) + 1):
        cell = ws.cell(row=total_row, column=c)
        cell.fill = TOTAL_FILL
        cell.font = TOTAL_FONT
        cell.border = BORDER

    ws.auto_filter.ref = f"A1:K{max(last, 1)}"
    return total_row


def _write_overview(wb: Workbook, totals: list[tuple[str, int]]):
    ws = wb.create_sheet(title="Oversigt", index=len(wb.worksheets))
    ws.merge_cells("A1:F1")
    t = ws["A1"]
    t.value = "Kvartalsafregning – importeret glas og pap"
    t.font = TITLE_FONT
    t.alignment = Alignment(horizontal="left", vertical="center")

    heads = ["Kvartal", "Antal flasker", "Glas kg", "Pap kg", "Status", "Bemærkning"]
    for col, (head, width) in enumerate(zip(heads, [14, 15, 14, 14, 12, 42]), start=1):
        cell = ws.cell(row=3, column=col, value=head)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")
        cell.border = BORDER
        ws.column_dimensions[get_column_letter(col)].width = width

    r = 4
    for quarter, total_row in totals:
        ref = f"'{quarter}'!"
        ws.cell(row=r, column=1, value=quarter)
        ws.cell(row=r, column=2, value=f"={ref}E{total_row}")
        ws.cell(row=r, column=3, value=f"={ref}G{total_row}").number_format = KG3
        ws.cell(row=r, column=4, value=f"={ref}I{total_row}").number_format = KG3
        ws.cell(row=r, column=5,
                value=f'=IF(ISNUMBER({ref}G{total_row}),"OK","UFULDSTÆNDIG")')
        ws.cell(row=r, column=6,
                value=f'=IF(ISNUMBER({ref}G{total_row}),"Alle glasvægte kendt","Mangler flaskevægt på en eller flere varer")')
        for c in range(1, 7):
            ws.cell(row=r, column=c).border = BORDER
        r += 1

    last = r - 1
    tr = r + 1
    ws.cell(row=tr, column=1, value="TOTAL")
    if last >= 4:
        ws.cell(row=tr, column=2, value=f"=SUM(B4:B{last})")
        # SUMIF springer "UFULDSTÆNDIG"-tekst over, så totalen ikke fejler
        ws.cell(row=tr, column=3, value=f"=SUMIF(C4:C{last},\">=0\")").number_format = KG3
        ws.cell(row=tr, column=4, value=f"=SUM(D4:D{last})").number_format = KG3
    for c in range(1, 7):
        cell = ws.cell(row=tr, column=c)
        cell.fill = TOTAL_FILL
        cell.font = TOTAL_FONT
        cell.border = BORDER


def build_workbook(rows_by_quarter: dict[str, list[dict]]) -> bytes:
    """rows_by_quarter: {'Q3 2025': [ {...linje...}, ... ], ...} -> xlsx-bytes."""
    wb = Workbook()
    wb.remove(wb.active)

    totals = []
    for quarter in sorted(rows_by_quarter, key=_quarter_sort_key):
        total_row = _write_quarter_sheet(wb, quarter, rows_by_quarter[quarter])
        totals.append((quarter, total_row))

    if not totals:
        ws = wb.create_sheet(title="Ingen data")
        ws["A1"] = "Der er endnu ingen fakturalinjer at eksportere."

    _write_overview(wb, totals)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
