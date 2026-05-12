from io import BytesIO
from datetime import datetime, timedelta
from decimal import Decimal
 
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_RIGHT, TA_LEFT, TA_CENTER
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Spacer, Table, TableStyle, KeepTogether,
)
from reportlab.pdfgen import canvas
import os
 
 
# --------------------------- konfiguration ---------------------------
VAT_RATE          = Decimal("0.25")   # 25% DK moms
PAYMENT_TERMS_DAYS = 8                # Netto X dage
LATE_FEE_PCT       = "0,81"           # rente pr. måned
LATE_FEE_FIXED     = "100,00"         # gebyr
 
# Sti til logo (PNG eller JPG). Læg filen på serveren og opdater stien her.
# Hvis filen ikke findes, falder vi tilbage til tekst-baseret logo.
LOGO_PATH = os.environ.get(
    "INVOICE_LOGO_PATH",
    "static/logo.png",
)
LOGO_WIDTH_MM  = 55  # bredde af logoet på fakturaen
 
# Justér til din egen virksomhed
SELLER = {
    "name":    "Kroatisk Vin",
    "address": "Svostrupvej 58,",
    "zip":     "8600",
    "city":    "Silkeborg",
    "country": "Danmark",
    "cvr":     "DK30541170",
    "phone":   "+ 45 61 73 18 10",
    "web":     "www.kroatiskvin.dk",
    "email":   "info@kroatiskvin.dk",
    "bank_reg":     "0000",
    "bank_konto":   "0000000000",
}
 
# Danske månednavne (til "17. Marts 2026")
MONTHS_DA = {
    1: "Januar",   2: "Februar", 3: "Marts",     4: "April",
    5: "Maj",      6: "Juni",    7: "Juli",      8: "August",
    9: "September",10: "Oktober",11: "November", 12: "December",
}
 
def _fmt_date_da(d: datetime) -> str:
    if not d: return ""
    return f"{d.day}. {MONTHS_DA[d.month]} {d.year}"
 
def _money(v) -> str:
    """1234.5 -> '1.234,50'"""
    n = Decimal(str(v or 0)).quantize(Decimal("0.01"))
    s = f"{n:,.2f}"            # '1,234.50'
    return s.replace(",", "X").replace(".", ",").replace("X", ".")
 
 
# --------------------------- header / footer ---------------------------
def _has_valid_logo() -> bool:
    """True hvis LOGO_PATH er en streng der peger på en eksisterende fil."""
    if not LOGO_PATH or not isinstance(LOGO_PATH, str):
        return False
    try:
        return os.path.isfile(LOGO_PATH)
    except Exception:
        return False
 
 
def _draw_text_logo(canv: canvas.Canvas, w: float, h: float):
    """Tekst-baseret logo (fallback)."""
    canv.setFont("Helvetica-Bold", 18)
    canv.setFillColor(colors.HexColor("#111111"))
    canv.drawRightString(w - 18 * mm, h - 22 * mm, SELLER["name"])
    canv.setFont("Helvetica", 8)
    canv.setFillColor(colors.HexColor("#888888"))
    canv.drawRightString(w - 18 * mm, h - 27 * mm, SELLER["web"])
 
 
def _draw_header_footer(canv: canvas.Canvas, doc):
    """Tegner logo øverst og firma-footer nederst på hver side."""
    w, h = A4
 
    # ---- Logo top-right ----
    canv.saveState()
    try:
        if _has_valid_logo():
            from reportlab.lib.utils import ImageReader
            img = ImageReader(LOGO_PATH)
            iw, ih = img.getSize()
            target_w = LOGO_WIDTH_MM * mm
            target_h = target_w * (ih / iw)
            x = w - 18 * mm - target_w
            y = h - 14 * mm - target_h
            canv.drawImage(
                LOGO_PATH, x, y,
                width=target_w, height=target_h,
                preserveAspectRatio=True, mask="auto",
            )
        else:
            _draw_text_logo(canv, w, h)
    except Exception:
        # Hvis NOGET fejler i logo-tegning, så fald tilbage til tekst
        _draw_text_logo(canv, w, h)
    canv.restoreState()
 
    # ---- Footer linje + firma-info ----
    canv.saveState()
    canv.setStrokeColor(colors.HexColor("#cccccc"))
    canv.setLineWidth(0.4)
    canv.line(18 * mm, 22 * mm, w - 18 * mm, 22 * mm)
 
    canv.setFont("Helvetica-Bold", 9)
    canv.setFillColor(colors.HexColor("#111111"))
    line1 = f"{SELLER['name']}"
    canv.drawCentredString(w / 2, 16 * mm, line1 +
        f"  /  {SELLER['address']} / {SELLER['zip']} {SELLER['city']}")
 
    canv.setFont("Helvetica", 8)
    canv.setFillColor(colors.HexColor("#444444"))
    canv.drawCentredString(
        w / 2, 11 * mm,
        f"CVR-nr. {SELLER['cvr']} / Tlf. {SELLER['phone']} "
        f"/ Web: {SELLER['web']} / Mail: {SELLER['email']}",
    )
    canv.restoreState()
 
 
# --------------------------- hoved-funktion ---------------------------
def build_invoice_pdf(order, company, lines) -> bytes:
    """
    order   : Order-instans (med order_id, order_date, notes)
    company : Company-instans (kunden)
    lines   : list[dict] med {name, sku, quantity, unit_price, line_total, description?}
    """
    buf = BytesIO()
 
    doc = BaseDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=38 * mm, bottomMargin=28 * mm,
        title=f"Faktura {order.order_id}",
        author=SELLER["name"],
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        id="content",
    )
    doc.addPageTemplates([
        PageTemplate(id="main", frames=[frame], onPage=_draw_header_footer),
    ])
 
    # Styles
    base   = ParagraphStyle("base",   fontName="Helvetica",      fontSize=10, leading=13, textColor=colors.HexColor("#111111"))
    bold   = ParagraphStyle("bold",   parent=base, fontName="Helvetica-Bold")
    small  = ParagraphStyle("small",  parent=base, fontSize=9, textColor=colors.HexColor("#555555"))
    label  = ParagraphStyle("label",  parent=base, fontSize=10, textColor=colors.HexColor("#444444"))
    h_big  = ParagraphStyle("hbig",   parent=base, fontName="Helvetica-Bold", fontSize=22, leading=26, spaceAfter=4)
    right  = ParagraphStyle("right",  parent=base, alignment=TA_RIGHT)
    right_b= ParagraphStyle("rightb", parent=bold, alignment=TA_RIGHT)
 
    story = []
 
    # ---- Kundeadresse (øverst venstre) ----
    story.append(Paragraph(f"<b>{company.name}</b>", base))
    if company.address:
        story.append(Paragraph(company.address, base))
    if company.zip or company.city:
        story.append(Paragraph(f"{company.zip or ''} {company.city or ''}".strip(), base))
    if company.cvr:
        story.append(Paragraph(f"Cvr-nr.: DK{company.cvr}", base))
    story.append(Spacer(1, 18 * mm))
 
    # ---- Dato + fakturanr ----
    invoice_date = datetime.utcnow()
    due_date     = invoice_date + timedelta(days=PAYMENT_TERMS_DAYS)
 
    date_tbl = Table(
        [[
            Paragraph(f"Dato: <b>{_fmt_date_da(invoice_date)}</b>", base),
            Paragraph(f"Fakturanr. <b>{order.order_id}</b>", right),
        ]],
        colWidths=[None, None],
    )
    date_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
    ]))
    story.append(date_tbl)
 
    # ---- Subtitle (fra order.notes hvis sat) ----
    if getattr(order, "notes", None):
        story.append(Paragraph(order.notes, base))
    story.append(Spacer(1, 10 * mm))
 
    # ---- "Faktura" heading ----
    story.append(Paragraph("Faktura", h_big))
    story.append(Spacer(1, 2 * mm))
 
    # ---- Items table ----
    th = ParagraphStyle("th", parent=label, fontSize=9, textColor=colors.HexColor("#555555"))
    th_r = ParagraphStyle("thr", parent=th, alignment=TA_RIGHT)
 
    data = [[
        Paragraph("Beskrivelse", th),
        Paragraph("Antal", th_r),
        Paragraph("Enhed", th),
        Paragraph("Enhedspris", th_r),
        Paragraph("Pris", th_r),
    ]]
 
    subtotal = Decimal("0")
    for ln in lines:
        qty   = Decimal(str(ln["quantity"]))
        unit  = Decimal(str(ln["unit_price"]))
        total = (qty * unit).quantize(Decimal("0.01"))
        subtotal += total
 
        # Navn (fed) + valgfri beskrivelse (lille grå) under
        desc = ln.get("description") or ""
        name_html = f"<b>{ln['name']}</b>"
        if desc:
            name_html += f"<br/><font size=8 color='#888888'>{desc}</font>"
 
        data.append([
            Paragraph(name_html, base),
            Paragraph(f"{qty:.2f}".replace(".", ","), right),
            Paragraph("stk.", base),
            Paragraph(_money(unit), right),
            Paragraph(_money(total), right),
        ])
 
    items_tbl = Table(
        data,
        colWidths=[66 * mm, 18 * mm, 18 * mm, 32 * mm, 34 * mm],
        repeatRows=1,
    )
    items_tbl.setStyle(TableStyle([
        # Header
        ("LINEABOVE", (0, 0), (-1, 0), 0.6, colors.HexColor("#111111")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.4, colors.HexColor("#cccccc")),
        ("TOPPADDING",    (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        # Body rows
        ("VALIGN",        (0, 1), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 1), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 8),
        ("LINEBELOW",     (0, -1), (-1, -1), 0.4, colors.HexColor("#cccccc")),
    ]))
    story.append(items_tbl)
 
    # ---- Totaler (højrestillet, kun højre kolonne) ----
    vat   = (subtotal * VAT_RATE).quantize(Decimal("0.01"))
    grand = (subtotal + vat).quantize(Decimal("0.01"))
 
    totals_tbl = Table(
        [
            [Paragraph("Subtotal", base),
             Paragraph(_money(subtotal), right)],
            [Paragraph(f"Moms ({int(VAT_RATE*100)},00%)", base),
             Paragraph(_money(vat), right)],
            [Paragraph("<b>Total DKK</b>", bold),
             Paragraph(f"<b>{_money(grand)}</b>", right_b)],
        ],
        colWidths=[40 * mm, 34 * mm],     # matcher den perfekte position du havde
        hAlign="RIGHT",
    )
    totals_tbl.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW",     (0, -1), (-1, -1), 0.6, colors.HexColor("#111111")),
    ]))
    story.append(totals_tbl)
    story.append(Spacer(1, 12 * mm))
 
    # ---- Betalingsoplysninger ----
    story.append(Paragraph(
        f"Betalingsbetingelser: Netto {PAYMENT_TERMS_DAYS} dage "
        f"- Forfaldsdato: <b>{_fmt_date_da(due_date)}</b>",
        base,
    ))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Beløbet indbetales på bankkonto:", base))
    story.append(Paragraph(
        f"Bank / Reg.nr. <b>{SELLER['bank_reg']}</b> "
        f"/ Kontonr. <b>{SELLER['bank_konto']}</b>",
        base,
    ))
    story.append(Paragraph(
        f"Fakturanr. <b>{order.order_id}</b> bedes angivet ved bankoverførsel",
        base,
    ))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph(
        f"Ved betaling efter forfald tilskrives der renter på {LATE_FEE_PCT}%, "
        f"pr. påbegyndt måned, samt et gebyr på {LATE_FEE_FIXED} DKK",
        small,
    ))
 
    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes
 
 