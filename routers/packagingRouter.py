"""Emballage-afregning: upload af Galić-følgesedler, stamdata for flaskevægte
og eksport af kvartalsregnearket."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from config.config import get_db
from config.model import (DEFAULT_CARTON_KG, PackagingInvoice, PackagingLine,
                          PackagingMaterial)
from models.schemas import (PackagingInvoiceCreate, PackagingInvoiceOut,
                            PackagingInvoiceUpdate, PackagingMaterialCreate,
                            PackagingMaterialOut, PackagingMaterialUpdate,
                            ParsedInvoice, ParsedLine, QuarterSummary)
from services.packaging_excel import build_workbook, quarter_of
from services.packaging_pdf import match_material, parse_packing_list

router = APIRouter()

MAX_PDF_BYTES = 15 * 1024 * 1024


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
                "item_name": line.item_name,
                "quantity": line.quantity,
                "glass_kg": float(line.glass_kg) if line.glass_kg is not None else None,
                "carton_kg": float(line.carton_kg) if line.carton_kg is not None
                else DEFAULT_CARTON_KG,
                "note": line.note,
            })
    return rows


@router.get("/summary", response_model=list[QuarterSummary])
def summary(db: Session = Depends(get_db)):
    rows = _rows_by_quarter(db)
    invoice_counts: dict[str, set] = {}
    for invoice in db.query(PackagingInvoice).all():
        quarter = invoice.quarter or quarter_of(invoice.invoice_date) or "Ukendt"
        invoice_counts.setdefault(quarter, set()).add(invoice.id)

    out = []
    for quarter, lines in rows.items():
        missing = sum(1 for l in lines if l["glass_kg"] is None)
        out.append(QuarterSummary(
            quarter=quarter,
            bottles=sum(l["quantity"] or 0 for l in lines),
            glass_kg=None if missing else round(
                sum((l["glass_kg"] or 0) * (l["quantity"] or 0) for l in lines), 3),
            carton_kg=round(
                sum((l["carton_kg"] or 0) * (l["quantity"] or 0) for l in lines), 3),
            invoices=len(invoice_counts.get(quarter, set())),
            missing_count=missing,
            status="OK" if missing == 0 else "UFULDSTÆNDIG",
        ))

    def key(s: QuarterSummary):
        try:
            qq, yy = s.quarter.split()
            return (int(yy), int(qq[1:]))
        except Exception:
            return (0, 0)

    return sorted(out, key=key)


@router.get("/export")
def export_excel(year: int | None = Query(default=None), db: Session = Depends(get_db)):
    rows = _rows_by_quarter(db, year=year)
    data = build_workbook(rows)

    years = sorted({q.split()[-1] for q in rows if " " in q})
    span = f"{years[0]}_{years[-1]}" if len(years) > 1 else (
        years[0] if years else "tom")
    filename = f"Kvartalsafregning_{span}_Emballage_Galic.xlsx"

    from io import BytesIO
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
