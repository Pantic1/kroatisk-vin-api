"""Emballage-afregning: upload af Galić-følgesedler, stamdata for flaskevægte
og eksport af kvartalsregnearket."""

from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from config.config import get_db
from config.model import (DEFAULT_CARTON_KG, PackagingInvoice, PackagingLine,
                          PackagingMaterial, PackagingOutbound)
from models.schemas import (PackagingInvoiceCreate, PackagingInvoiceOut,
                            PackagingInvoiceUpdate, PackagingMaterialCreate,
                            PackagingMaterialOut, PackagingMaterialUpdate,
                            PackagingOutboundOut, PackagingOutboundQuarter,
                            ParsedInvoice, ParsedLine, QuarterSummary)
from services.packaging_excel import build_workbook, quarter_of
from services.packaging_pdf import (match_material, normalize,
                                    parse_packing_list)

router = APIRouter()

MAX_PDF_BYTES = 15 * 1024 * 1024
QUARTER_RE = re.compile(r"^Q[1-4] \d{4}$")


# =========================================================
# Stamdata: flaskevægte
# =========================================================

@router.get("/materials", response_model=list[PackagingMaterialOut])
def list_materials(include_inactive: bool = False, db: Session = Depends(get_db)):
    q = db.query(PackagingMaterial)
    if not include_inactive:
        q = q.filter(PackagingMaterial.active.is_(True))
    return q.order_by(PackagingMaterial.name).all()


@router.post("/materials", response_model=PackagingMaterialOut)
def create_material(payload: PackagingMaterialCreate, db: Session = Depends(get_db)):
    if db.query(PackagingMaterial).filter(PackagingMaterial.name == payload.name).first():
        raise HTTPException(400, f"Varen '{payload.name}' findes allerede")
    if payload.article_code and db.query(PackagingMaterial).filter(
            PackagingMaterial.article_code == payload.article_code).first():
        raise HTTPException(400, f"Varenummer {payload.article_code} findes allerede")

    material = PackagingMaterial(**payload.model_dump())
    db.add(material)
    db.commit()
    db.refresh(material)
    return material


@router.put("/materials/{material_id}", response_model=PackagingMaterialOut)
def update_material(material_id: str, payload: PackagingMaterialUpdate,
                    db: Session = Depends(get_db)):
    material = db.get(PackagingMaterial, material_id)
    if not material:
        raise HTTPException(404, "Varen findes ikke")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(material, key, value)
    db.commit()
    db.refresh(material)
    return material


@router.delete("/materials/{material_id}")
def delete_material(material_id: str, db: Session = Depends(get_db)):
    material = db.get(PackagingMaterial, material_id)
    if not material:
        raise HTTPException(404, "Varen findes ikke")
    # Linjer beholder deres egen kopi af vægten, så gamle afregninger står fast
    db.query(PackagingLine).filter(
        PackagingLine.material_id == material_id).update({"material_id": None})
    db.query(PackagingOutbound).filter(
        PackagingOutbound.material_id == material_id).update({"material_id": None})
    db.delete(material)
    db.commit()
    return {"detail": "Varen er slettet"}


# =========================================================
# Upload og aflæsning af følgeseddel
# =========================================================

def _to_parsed_line(item: dict, materials: list) -> ParsedLine:
    material, confidence, how = match_material(item, materials)
    return ParsedLine(
        line_no=item.get("line_no"),
        article_code=item.get("article_code"),
        item_name=item.get("item_name"),
        quantity=item.get("quantity", 0),
        glass_kg=float(material.glass_kg) if material is not None
        and material.glass_kg is not None else None,
        carton_kg=float(material.carton_kg) if material is not None
        and material.carton_kg is not None else DEFAULT_CARTON_KG,
        material_id=material.id if material is not None else None,
        matched_name=material.name if material is not None else None,
        match_type=how,
        match_confidence=confidence,
        status="OK" if material is not None and material.glass_kg is not None
        else "MANGLER",
    )


@router.post("/parse", response_model=ParsedInvoice)
async def parse_invoice(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Læser en følgeseddel og returnerer et udkast. Der gemmes ingenting her –
    brugeren godkender linjerne først, og POST /invoices gemmer dem."""
    data = await file.read()
    if not data:
        raise HTTPException(400, "Filen er tom")
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(400, "Filen er for stor (maks. 15 MB)")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "Filen er ikke en PDF")

    try:
        parsed = parse_packing_list(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:
        raise HTTPException(422, f"Kunne ikke læse PDF'en: {exc}")

    materials = db.query(PackagingMaterial).filter(
        PackagingMaterial.active.is_(True)).all()
    lines = [_to_parsed_line(item, materials) for item in parsed["items"]]

    invoice_date = None
    if parsed.get("invoice_date"):
        invoice_date = datetime.fromisoformat(parsed["invoice_date"])

    warnings: list[str] = []
    if not lines:
        warnings.append(
            "Der blev ikke fundet nogen varelinjer i PDF'en. Tilføj dem manuelt.")
    if not parsed.get("invoice_number"):
        warnings.append("Dokumentnummeret kunne ikke aflæses – udfyld det selv.")
    if invoice_date is None:
        warnings.append("Datoen kunne ikke aflæses – udfyld den selv.")

    duplicate = None
    if parsed.get("invoice_number"):
        existing = db.query(PackagingInvoice).filter(
            PackagingInvoice.invoice_number == parsed["invoice_number"]).first()
        if existing:
            duplicate = existing.id
            warnings.append(
                f"Følgeseddel {existing.invoice_number} er allerede importeret.")

    return ParsedInvoice(
        invoice_number=parsed.get("invoice_number"),
        invoice_date=invoice_date,
        quarter=quarter_of(invoice_date),
        source_filename=file.filename,
        packages=parsed.get("packages"),
        lines=lines,
        unmatched_count=sum(1 for l in lines if l.status == "MANGLER"),
        duplicate_of=duplicate,
        warnings=warnings,
    )


# =========================================================
# Fakturaer
# =========================================================

def _serialize(invoice: PackagingInvoice) -> PackagingInvoiceOut:
    lines = []
    for line in invoice.lines:
        lines.append({
            "id": line.id,
            "line_no": line.line_no,
            "article_code": line.article_code,
            "item_name": line.item_name,
            "quantity": line.quantity,
            "glass_kg": float(line.glass_kg) if line.glass_kg is not None else None,
            "carton_kg": float(line.carton_kg) if line.carton_kg is not None
            else DEFAULT_CARTON_KG,
            "material_id": line.material_id,
            "note": line.note,
            "status": line.status,
            "glass_total_kg": line.glass_total_kg,
            "carton_total_kg": line.carton_total_kg,
        })
    missing = sum(1 for l in lines if l["status"] == "MANGLER")
    return PackagingInvoiceOut(
        id=invoice.id,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        quarter=invoice.quarter,
        supplier=invoice.supplier,
        file_url=invoice.file_url,
        source_filename=invoice.source_filename,
        notes=invoice.notes,
        lines=lines,
        total_bottles=sum(l["quantity"] or 0 for l in lines),
        # Mangler bare én vægt, er totalen ikke et facit – så vises den ikke
        total_glass_kg=None if missing else round(
            sum(l["glass_total_kg"] or 0 for l in lines), 3),
        total_carton_kg=round(sum(l["carton_total_kg"] or 0 for l in lines), 3),
        missing_count=missing,
    )


def _apply_lines(invoice: PackagingInvoice, lines, db: Session):
    invoice.lines.clear()
    db.flush()
    for idx, line in enumerate(lines, start=1):
        invoice.lines.append(PackagingLine(
            line_no=line.line_no or idx,
            article_code=line.article_code,
            item_name=line.item_name,
            quantity=line.quantity or 0,
            glass_kg=line.glass_kg,
            carton_kg=line.carton_kg if line.carton_kg is not None
            else DEFAULT_CARTON_KG,
            material_id=line.material_id,
            note=line.note,
        ))


@router.get("/invoices", response_model=list[PackagingInvoiceOut])
def list_invoices(quarter: str | None = None, db: Session = Depends(get_db)):
    q = db.query(PackagingInvoice).options(joinedload(PackagingInvoice.lines))
    if quarter:
        q = q.filter(PackagingInvoice.quarter == quarter)
    invoices = q.order_by(PackagingInvoice.invoice_date.desc()).all()
    return [_serialize(i) for i in invoices]


@router.get("/invoices/{invoice_id}", response_model=PackagingInvoiceOut)
def get_invoice(invoice_id: str, db: Session = Depends(get_db)):
    invoice = db.get(PackagingInvoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "Følgesedlen findes ikke")
    return _serialize(invoice)


@router.post("/invoices", response_model=PackagingInvoiceOut)
def create_invoice(payload: PackagingInvoiceCreate, db: Session = Depends(get_db)):
    if payload.invoice_number:
        existing = db.query(PackagingInvoice).filter(
            PackagingInvoice.invoice_number == payload.invoice_number).first()
        if existing:
            raise HTTPException(
                400, f"Følgeseddel {payload.invoice_number} er allerede importeret")

    invoice = PackagingInvoice(
        invoice_number=payload.invoice_number,
        invoice_date=payload.invoice_date,
        quarter=payload.quarter or quarter_of(payload.invoice_date),
        supplier=payload.supplier or "Galic",
        file_url=payload.file_url,
        source_filename=payload.source_filename,
        notes=payload.notes,
    )
    db.add(invoice)
    _apply_lines(invoice, payload.lines, db)
    db.commit()
    db.refresh(invoice)
    return _serialize(invoice)


@router.put("/invoices/{invoice_id}", response_model=PackagingInvoiceOut)
def update_invoice(invoice_id: str, payload: PackagingInvoiceUpdate,
                   db: Session = Depends(get_db)):
    invoice = db.get(PackagingInvoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "Følgesedlen findes ikke")

    data = payload.model_dump(exclude_unset=True)
    lines = data.pop("lines", None)
    for key, value in data.items():
        setattr(invoice, key, value)
    if "invoice_date" in data and "quarter" not in data:
        invoice.quarter = quarter_of(invoice.invoice_date)
    if lines is not None:
        _apply_lines(invoice, payload.lines, db)

    db.commit()
    db.refresh(invoice)
    return _serialize(invoice)


@router.delete("/invoices/{invoice_id}")
def delete_invoice(invoice_id: str, db: Session = Depends(get_db)):
    invoice = db.get(PackagingInvoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "Følgesedlen findes ikke")
    db.delete(invoice)
    db.commit()
    return {"detail": "Følgesedlen er slettet"}


# =========================================================
# Ud af huset: flasker kunden tager med hjem
# =========================================================

def _serialize_outbound(row: PackagingOutbound) -> dict:
    return {
        "id": row.id,
        "quarter": row.quarter,
        "material_id": row.material_id,
        "article_code": row.article_code,
        "item_name": row.item_name,
        "quantity": row.quantity,
        "glass_kg": float(row.glass_kg) if row.glass_kg is not None else None,
        "carton_kg": float(row.carton_kg) if row.carton_kg is not None
        else DEFAULT_CARTON_KG,
        "note": row.note,
        "status": row.status,
        "glass_total_kg": row.glass_total_kg,
        "carton_total_kg": row.carton_total_kg,
    }


@router.get("/outbound", response_model=list[PackagingOutboundOut])
def list_outbound(quarter: str | None = None, db: Session = Depends(get_db)):
    q = db.query(PackagingOutbound)
    if quarter:
        q = q.filter(PackagingOutbound.quarter == quarter)
    rows = q.order_by(PackagingOutbound.quarter,
                      PackagingOutbound.item_name).all()
    return [_serialize_outbound(r) for r in rows]


@router.put("/outbound/{quarter}", response_model=list[PackagingOutboundOut])
def replace_outbound(quarter: str, payload: PackagingOutboundQuarter,
                     db: Session = Depends(get_db)):
    """Gemmer hele kvartalet på én gang – listen erstatter det der lå før.
    Det matcher siden, hvor man retter i en tabel og gemmer samlet."""
    if not QUARTER_RE.match(quarter):
        raise HTTPException(400, "Kvartal skal skrives som fx 'Q3 2026'")

    db.query(PackagingOutbound).filter(
        PackagingOutbound.quarter == quarter).delete()
    for line in payload.lines:
        if not line.item_name:
            continue
        db.add(PackagingOutbound(
            quarter=quarter,
            material_id=line.material_id,
            article_code=line.article_code,
            item_name=line.item_name,
            quantity=line.quantity or 0,
            glass_kg=line.glass_kg,
            carton_kg=line.carton_kg if line.carton_kg is not None
            else DEFAULT_CARTON_KG,
            note=line.note,
        ))
    db.commit()

    rows = db.query(PackagingOutbound).filter(
        PackagingOutbound.quarter == quarter).order_by(
        PackagingOutbound.item_name).all()
    return [_serialize_outbound(r) for r in rows]


@router.delete("/outbound/{row_id}")
def delete_outbound(row_id: str, db: Session = Depends(get_db)):
    row = db.get(PackagingOutbound, row_id)
    if not row:
        raise HTTPException(404, "Linjen findes ikke")
    db.delete(row)
    db.commit()
    return {"detail": "Linjen er slettet"}


# =========================================================
# Oversigt og eksport
# =========================================================

def _rows_by_quarter(db: Session, year: int | None = None) -> dict:
    q = db.query(PackagingInvoice).options(joinedload(PackagingInvoice.lines))
    invoices = q.order_by(PackagingInvoice.invoice_date).all()

    rows: dict[str, list[dict]] = {}
    for invoice in invoices:
        quarter = invoice.quarter or quarter_of(invoice.invoice_date) or "Ukendt"
        if year and not quarter.endswith(str(year)):
            continue
        for line in invoice.lines:
            rows.setdefault(quarter, []).append({
                "invoice_date": invoice.invoice_date,
                "invoice_number": invoice.invoice_number,
                "material_id": line.material_id,
                "article_code": line.article_code,
                "item_name": line.item_name,
                "quantity": line.quantity,
                "glass_kg": float(line.glass_kg) if line.glass_kg is not None else None,
                "carton_kg": float(line.carton_kg) if line.carton_kg is not None
                else DEFAULT_CARTON_KG,
                "note": line.note,
            })
    return rows


def _outbound_by_quarter(db: Session, year: int | None = None) -> dict:
    rows: dict[str, list[dict]] = {}
    for row in db.query(PackagingOutbound).order_by(PackagingOutbound.item_name).all():
        if year and not (row.quarter or "").endswith(str(year)):
            continue
        rows.setdefault(row.quarter, []).append({
            "quarter": row.quarter,
            "material_id": row.material_id,
            "article_code": row.article_code,
            "item_name": row.item_name,
            "quantity": row.quantity,
            "glass_kg": float(row.glass_kg) if row.glass_kg is not None else None,
            "carton_kg": float(row.carton_kg) if row.carton_kg is not None
            else DEFAULT_CARTON_KG,
            "note": row.note,
        })
    return rows


def _quarter_key(quarter: str):
    try:
        qq, yy = quarter.split()
        return (int(yy), int(qq[1:]))
    except Exception:
        return (0, 0)


def _totals(lines: list[dict]) -> tuple:
    """(flasker, glas kg, pap kg, antal linjer uden vægt). Glas er None hvis
    bare én vægt mangler – så vises der ikke et tal der ser rigtigt ud."""
    missing = sum(1 for l in lines if l["glass_kg"] is None)
    bottles = sum(l["quantity"] or 0 for l in lines)
    glass = None if missing else round(
        sum((l["glass_kg"] or 0) * (l["quantity"] or 0) for l in lines), 3)
    carton = round(
        sum((l["carton_kg"] or 0) * (l["quantity"] or 0) for l in lines), 3)
    return bottles, glass, carton, missing


@router.get("/summary", response_model=list[QuarterSummary])
def summary(db: Session = Depends(get_db)):
    imported = _rows_by_quarter(db)
    outbound = _outbound_by_quarter(db)

    invoice_counts: dict[str, set] = {}
    for invoice in db.query(PackagingInvoice).all():
        quarter = invoice.quarter or quarter_of(invoice.invoice_date) or "Ukendt"
        invoice_counts.setdefault(quarter, set()).add(invoice.id)

    quarters = sorted(set(imported) | set(outbound), key=_quarter_key)

    # Lager løber over kvartalsskel: man kan sælge i Q4 det der kom ind i Q3.
    # Derfor sammenlignes akkumuleret, ikke kvartal for kvartal.
    #
    # Importlinjer bærer navnet som det står på følgesedlen ("GRAŠEVINA 0,75l
    # 2024"), de udgående bærer stamdata-navnet, så navnet duer ikke som nøgle.
    #
    # Galićs varenummer er den rigtige nøgle, men det står ikke nødvendigvis på
    # begge sider: importlinjen har det altid fra følgesedlen, mens en udgående
    # linje kun har det hvis den er valgt ud fra stamdata. Derfor slås nummeret
    # op via stamdata når linjen ikke selv har det – ellers ville de to sider få
    # hver sin nøgle og aldrig tælle sammen.
    codes_by_material = {
        m.id: (m.article_code or "").strip().lstrip("0")
        for m in db.query(PackagingMaterial).all()
    }

    def key(line):
        code = (line.get("article_code") or "").strip().lstrip("0")
        if not code and line.get("material_id"):
            code = codes_by_material.get(line["material_id"]) or ""
        if code:
            return f"nr:{code}"
        # Varer uden varenummer hos Galić (fx Rosé Magnum) kobles på stamdata
        if line.get("material_id"):
            return f"id:{line['material_id']}"
        return f"navn:{normalize(line['item_name'])}"

    seen_in: dict[str, int] = {}
    seen_out: dict[str, int] = {}
    labels: dict[str, str] = {}

    out = []
    for quarter in quarters:
        in_lines = imported.get(quarter, [])
        out_lines = outbound.get(quarter, [])

        in_bottles, in_glass, in_carton, in_missing = _totals(in_lines)
        out_bottles, out_glass, out_carton, out_missing = _totals(out_lines)

        for l in in_lines:
            k = key(l)
            seen_in[k] = seen_in.get(k, 0) + (l["quantity"] or 0)
            labels.setdefault(k, l["item_name"])
        for l in out_lines:
            k = key(l)
            seen_out[k] = seen_out.get(k, 0) + (l["quantity"] or 0)
            labels[k] = l["item_name"]

        warnings = []
        for k, sold in seen_out.items():
            bought = seen_in.get(k, 0)
            if sold > bought:
                warnings.append(
                    f"{labels.get(k, k)}: solgt {sold} ud af huset, men kun {bought} "
                    f"importeret til og med {quarter}")

        out.append(QuarterSummary(
            quarter=quarter,
            bottles=in_bottles,
            glass_kg=in_glass,
            carton_kg=in_carton,
            invoices=len(invoice_counts.get(quarter, set())),
            missing_count=in_missing,
            status="OK" if in_missing == 0 and out_missing == 0 else "UFULDSTÆNDIG",
            out_bottles=out_bottles,
            out_glass_kg=out_glass,
            out_carton_kg=out_carton,
            out_missing_count=out_missing,
            net_bottles=in_bottles - out_bottles,
            net_glass_kg=None if (in_glass is None or out_glass is None)
            else round(in_glass - out_glass, 3),
            net_carton_kg=round(in_carton - out_carton, 3),
            warnings=warnings,
        ))

    return out


@router.get("/export")
def export_excel(year: int | None = Query(default=None), db: Session = Depends(get_db)):
    rows = _rows_by_quarter(db, year=year)
    outbound = _outbound_by_quarter(db, year=year)
    data = build_workbook(rows, outbound)

    years = sorted({q.split()[-1] for q in set(rows) | set(outbound) if " " in q})
    span = f"{years[0]}_{years[-1]}" if len(years) > 1 else (
        years[0] if years else "tom")
    filename = f"Kvartalsafregning_{span}_Emballage_Galic.xlsx"

    from io import BytesIO
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
