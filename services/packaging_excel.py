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


OUT_HEADERS = ["Kvartal", "Vare", "Antal", "Tom flaske kg", "Glas i alt kg",
               "Pap pr. flaske kg", "Pap i alt kg", "Note"]
OUT_WIDTHS = [11, 36, 9, 14, 14, 17, 13, 30]


def _write_outbound_sheet(wb: Workbook, rows_by_quarter: dict) -> tuple:
    """Én samlet side med alt der er solgt ud af huset, på tværs af kvartaler.
    Returnerer (arknavn, sidste datarække) så Oversigt kan summere herfra."""
    ws = wb.create_sheet(title="Ud af huset")

    for col, (head_, width) in enumerate(zip(OUT_HEADERS, OUT_WIDTHS), start=1):
        cell = ws.cell(row=1, column=col, value=head_)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   wrap_text=True)
        cell.border = BORDER
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"

    r = 2
    for quarter in sorted(rows_by_quarter, key=_quarter_sort_key):
        for row in rows_by_quarter[quarter]:
            missing = row.get("glass_kg") is None
            ws.cell(row=r, column=1, value=quarter)
            ws.cell(row=r, column=2, value=row.get("item_name"))
            ws.cell(row=r, column=3, value=row.get("quantity"))
            ws.cell(row=r, column=4, value=row.get("glass_kg")).number_format = KG3
            ws.cell(row=r, column=5,
                    value=None if missing else f"=C{r}*D{r}").number_format = KG3
            ws.cell(row=r, column=6, value=row.get("carton_kg")).number_format = KG4
            ws.cell(row=r, column=7, value=f"=C{r}*F{r}").number_format = KG3
            ws.cell(row=r, column=8, value=row.get("note"))
            for c in range(1, len(OUT_HEADERS) + 1):
                ws.cell(row=r, column=c).border = BORDER
                if missing:
                    ws.cell(row=r, column=c).fill = MISSING_FILL
            r += 1

    last = r - 1
    if last >= 2:
        ws.cell(row=r, column=1, value="TOTAL")
        ws.cell(row=r, column=3, value=f"=SUM(C2:C{last})")
        ws.cell(row=r, column=5, value=f"=SUM(E2:E{last})").number_format = KG3
        ws.cell(row=r, column=7, value=f"=SUM(G2:G{last})").number_format = KG3
        for c in range(1, len(OUT_HEADERS) + 1):
            cell = ws.cell(row=r, column=c)
            cell.fill = TOTAL_FILL
            cell.font = TOTAL_FONT
            cell.border = BORDER
        ws.auto_filter.ref = f"A1:H{last}"
    else:
        ws.cell(row=2, column=1,
                value="Der er endnu ikke registreret salg ud af huset.")

    return "Ud af huset", last


OVERVIEW_HEADERS = [
    "Kvartal",
    "Importeret\nflasker", "Import\nglas kg", "Import\npap kg",
    "Ud af huset\nflasker", "Ud af huset\nglas kg", "Ud af huset\npap kg",
    "Tilbage i huset\nflasker", "Tilbage i huset\nglas kg", "Tilbage i huset\npap kg",
    "Status", "Bemærkning",
]
OVERVIEW_WIDTHS = [11, 12, 11, 11, 12, 12, 12, 14, 14, 14, 14, 40]


def _write_overview(wb: Workbook, totals: list[tuple[str, int]],
                    out_sheet: str, out_last_row: int):
    ws = wb.create_sheet(title="Oversigt", index=len(wb.worksheets))
    ws.merge_cells("A1:L1")
    t = ws["A1"]
    t.value = "Kvartalsafregning – importeret glas og pap, minus salg ud af huset"
    t.font = TITLE_FONT
    t.alignment = Alignment(horizontal="left", vertical="center")

    for col, (head, width) in enumerate(zip(OVERVIEW_HEADERS, OVERVIEW_WIDTHS), start=1):
        cell = ws.cell(row=3, column=col, value=head)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   wrap_text=True)
        cell.border = BORDER
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.row_dimensions[3].height = 34

    # Områder på "Ud af huset"-arket, som der summeres hen over pr. kvartal
    has_out = out_last_row >= 2
    q_rng = f"'{out_sheet}'!$A$2:$A${out_last_row}" if has_out else None
    n_rng = f"'{out_sheet}'!$C$2:$C${out_last_row}" if has_out else None
    g_rng = f"'{out_sheet}'!$E$2:$E${out_last_row}" if has_out else None
    p_rng = f"'{out_sheet}'!$G$2:$G${out_last_row}" if has_out else None

    r = 4
    for quarter, total_row in totals:
        ref = f"'{quarter}'!"
        ws.cell(row=r, column=1, value=quarter)
        ws.cell(row=r, column=2, value=f"={ref}E{total_row}")
        ws.cell(row=r, column=3, value=f"={ref}G{total_row}").number_format = KG3
        ws.cell(row=r, column=4, value=f"={ref}I{total_row}").number_format = KG3

        if has_out:
            ws.cell(row=r, column=5, value=f'=SUMIF({q_rng},$A{r},{n_rng})')
            ws.cell(row=r, column=6, value=f'=SUMIF({q_rng},$A{r},{g_rng})').number_format = KG3
            ws.cell(row=r, column=7, value=f'=SUMIF({q_rng},$A{r},{p_rng})').number_format = KG3
        else:
            for c in (5, 6, 7):
                ws.cell(row=r, column=c, value=0)

        ws.cell(row=r, column=8, value=f"=B{r}-E{r}")
        # Mangler en flaskevægt, står importtotalen som tekst – så kan der ikke
        # trækkes fra, og feltet siger det i stedet for at vise et forkert tal.
        ws.cell(row=r, column=9,
                value=f'=IF(ISNUMBER(C{r}),C{r}-F{r},"UFULDSTÆNDIG")').number_format = KG3
        ws.cell(row=r, column=10, value=f"=D{r}-G{r}").number_format = KG3
        ws.cell(row=r, column=11,
                value=f'=IF(ISNUMBER(I{r}),"OK","UFULDSTÆNDIG")')
        ws.cell(row=r, column=12,
                value=f'=IF(ISNUMBER(I{r}),"Alle glasvægte kendt","Mangler flaskevægt på en eller flere varer")')
        for c in range(1, 13):
            ws.cell(row=r, column=c).border = BORDER
        r += 1

    last = r - 1
    tr = r + 1
    ws.cell(row=tr, column=1, value="TOTAL")
    if last >= 4:
        # SUM springer selv tekst som "UFULDSTÆNDIG" over og tager negative tal
        # med – og negative forekommer, når et kvartal sælger af tidligere lager.
        for col in (2, 5, 8):
            letter = get_column_letter(col)
            ws.cell(row=tr, column=col, value=f"=SUM({letter}4:{letter}{last})")
        for col in (3, 4, 6, 7, 9, 10):
            letter = get_column_letter(col)
            ws.cell(row=tr, column=col,
                    value=f"=SUM({letter}4:{letter}{last})").number_format = KG3
    for c in range(1, 13):
        cell = ws.cell(row=tr, column=c)
        cell.fill = TOTAL_FILL
        cell.font = TOTAL_FONT
        cell.border = BORDER

    ws.cell(row=tr + 2, column=1,
            value="Tilbage i huset = importeret minus det kunderne har taget med hjem.")


def build_workbook(rows_by_quarter: dict[str, list[dict]],
                   outbound_by_quarter: dict[str, list[dict]] | None = None) -> bytes:
    """rows_by_quarter: importerede linjer pr. kvartal.
    outbound_by_quarter: solgt ud af huset pr. kvartal. -> xlsx-bytes."""
    outbound_by_quarter = outbound_by_quarter or {}
    wb = Workbook()
    wb.remove(wb.active)

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
