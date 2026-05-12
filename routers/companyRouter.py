# routers/companies.py
from decimal import Decimal
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.params import Body
from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from config.config import get_db
from config.model import CompaniesPrices, Company, Contact, Order, OrderItem, Product, ProductImage
from models.schemas import CompanyBase, CompanyCreate, CompanyUpdate

router = APIRouter()


def _sum_ownership_pct(contacts: list) -> float:
    return sum((k.ownershipPct or 0) for k in contacts or [])


@router.post("/", response_model=CompanyBase, status_code=status.HTTP_201_CREATED)
def create_company(payload: CompanyCreate, db: Session = Depends(get_db)):
    # Unik CVR?
    if db.query(Company).filter(Company.cvr == payload.cvr).first():
        raise HTTPException(
            status_code=409, detail="Company with this CVR already exists")

    # Samlet ejerskab ≤ 100%
    if _sum_ownership_pct(payload.contacts) > 100 + 1e-6:
        raise HTTPException(
            status_code=400, detail="Total ownership must not exceed 100%")
    company_id = str(uuid.uuid4())
    # Opret virksomhed
    company = Company(
        id=company_id,
        name=payload.name,
        cvr=payload.cvr,
        company_type=payload.companyType,
        industry=payload.industry,
        vat_registered=payload.vatRegistered,
        ean=payload.ean,
        phone=payload.phone,
        email=payload.email,
        website=payload.website,
        address=payload.address,
        zip=payload.zip,
        city=payload.city,
        country=payload.country,
        iban=payload.iban,
        swift=payload.swift,
        notes=payload.notes,
        status=payload.status or "Draft",
    )

    # Tilføj contacts
    for k in payload.contacts or []:
        company.contacts.append(
            Contact(
                name=k.name,
                email=k.email,
                role=k.role,
                company_id=company_id,
                ownership_pct=k.ownershipPct,
            )
        )

    db.add(company)
    db.commit()
    db.refresh(company)

    # Returnér inkl. contacts
    company = (
        db.query(Company)
        .options(joinedload(Company.contacts))
        .filter(Company.id == company.id)
        .first()
    )
    return company


@router.get("/", response_model=list[CompanyBase])
def list_companies(db: Session = Depends(get_db)):
    companies = db.query(Company).options(joinedload(Company.contacts)).all()
    return companies


@router.get("/{company_id}", response_model=CompanyBase)
def get_company(company_id: str, db: Session = Depends(get_db)):
    company = (
        db.query(Company)
        .options(joinedload(Company.contacts))
        .filter(Company.id == company_id)
        .first()
    )
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.put("/{company_id}", response_model=CompanyBase)
def update_company(company_id: str, payload: CompanyUpdate, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Hvis CVR ændres: tjek unik
    if payload.cvr and payload.cvr != company.cvr:
        if db.query(Company).filter(Company.cvr == payload.cvr).first():
            raise HTTPException(
                status_code=409, detail="Company with this CVR already exists")

    # Opdater felter hvis angivet
    for attr_model, attr_payload in [
        ("name", "name"),
        ("cvr", "cvr"),
        ("company_type", "companyType"),
        ("industry", "industry"),
        ("vat_registered", "vatRegistered"),
        ("ean", "ean"),
        ("phone", "phone"),
        ("email", "email"),
        ("website", "website"),
        ("address", "address"),
        ("zip", "zip"),
        ("city", "city"),
        ("country", "country"),
        ("iban", "iban"),
        ("swift", "swift"),
        ("notes", "notes"),
        ("status", "status"),
    ]:
        val = getattr(payload, attr_payload, None)
        if val is not None:
            setattr(company, attr_model, val)

    # Erstat contacts hvis angivet
    if payload.contacts is not None:
        if _sum_ownership_pct(payload.contacts) > 100 + 1e-6:
            raise HTTPException(
                status_code=400, detail="Total ownership must not exceed 100%")

        # Slet eksisterende contacts og indsæt nye
        company.contacts.clear()
        db.flush()  # sørger for at sletning sker før indsættelse

        for k in payload.contacts:
            company.contacts.append(
                Contact(
                    name=k.name,
                    email=k.email,
                    role=k.role,
                    ownership_pct=k.ownershipPct,
                )
            )

    db.add(company)
    db.commit()

    company = (
        db.query(Company)
        .options(joinedload(Company.contacts))
        .filter(Company.id == company_id)
        .first()
    )
    return company


@router.delete("/{company_id}", status_code=status.HTTP_200_OK)
def delete_company(company_id: str, db: Session = Depends(get_db)):
    company = (
        db.query(Company)
        .options(joinedload(Company.contacts))
        .filter(Company.id == company_id)
        .first()
    )

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Undgå at slette hvis kunden har ordrer
    orders_count = db.query(Order).filter(
        Order.customer_id == company_id).count()
    if orders_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Company cannot be deleted because it has {orders_count} orders"
        )

    # Slet særpriser
    db.query(CompaniesPrices).filter(
        CompaniesPrices.companies_id == company_id
    ).delete(synchronize_session=False)

    # Slet kontakter
    db.query(Contact).filter(
        Contact.company_id == company_id
    ).delete(synchronize_session=False)

    # Slet company
    db.delete(company)
    db.commit()

    return {
        "ok": True,
        "message": "Company deleted",
        "company_id": company_id
    }

# ---------------------------------------------------------------------------
# 1) GET /company/{company_id}/orders   -> alle ordrer for kunden
# ---------------------------------------------------------------------------


@router.get("/{company_id}/orders")
def get_company_orders(company_id: str, db: Session = Depends(get_db)):
    if not db.query(Company).filter(Company.id == company_id).first():
        raise HTTPException(status_code=404, detail="Company not found")

    rows = (
        db.query(
            Order.id,
            Order.order_id,
            Order.order_date,
            Order.status,
            Order.subtotal_price,
            Order.tracking_number,
            Order.notes,
            func.coalesce(func.count(OrderItem.id), 0).label("items_count"),
            func.coalesce(func.sum(OrderItem.quantity),
                          0).label("total_quantity"),
        )
        .outerjoin(OrderItem, OrderItem.order_id == Order.id)
        .filter(Order.customer_id == company_id)
        .group_by(Order.id)
        .order_by(Order.order_date.desc())
        .all()
    )
    return [dict(r._mapping) for r in rows]


# ---------------------------------------------------------------------------
# 2) GET /company/{company_id}/stats   -> total købt + top 5 produkter
# ---------------------------------------------------------------------------
@router.get("/{company_id}/stats")
def get_company_stats(company_id: str, db: Session = Depends(get_db)):
    if not db.query(Company).filter(Company.id == company_id).first():
        raise HTTPException(status_code=404, detail="Company not found")

    totals = (
        db.query(
            func.coalesce(func.sum(Order.subtotal_price),
                          0).label("total_spent"),
            func.count(Order.id).label("orders_count"),
            func.max(Order.order_date).label("last_order_date"),
        )
        .filter(Order.customer_id == company_id)
        .filter(Order.status != "cancelled")
        .one()
    )

    top_rows = (
        db.query(
            Product.id.label("product_id"),
            Product.sku,
            Product.name,
            func.sum(OrderItem.quantity).label("total_quantity"),
            func.sum(OrderItem.quantity *
                     OrderItem.price).label("total_revenue"),
            func.avg(OrderItem.price).label("avg_price"),
        )
        .join(Order, OrderItem.order_id == Order.id)
        .join(Product, OrderItem.product_id == Product.id)
        .filter(Order.customer_id == company_id)
        .filter(Order.status != "cancelled")
        .group_by(Product.id)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(5)
        .all()
    )

    return {
        "total_spent":     float(totals.total_spent or 0),
        "orders_count":    int(totals.orders_count or 0),
        "last_order_date": totals.last_order_date,
        "top_products":    [dict(r._mapping) for r in top_rows],
    }


# ---------------------------------------------------------------------------
# 3) GET /company/{company_id}/prices   -> alle produkter med kundens pris
# ---------------------------------------------------------------------------
@router.get("/{company_id}/prices")
def get_company_prices(company_id: str, db: Session = Depends(get_db)):
    if not db.query(Company).filter(Company.id == company_id).first():
        raise HTTPException(status_code=404, detail="Company not found")

    last_purchase_subq = (
        db.query(OrderItem.price)
        .join(Order, OrderItem.order_id == Order.id)
        .filter(Order.customer_id == company_id)
        .filter(OrderItem.product_id == Product.id)
        .order_by(Order.order_date.desc())
        .limit(1)
        .correlate(Product)
        .scalar_subquery()
    )

    image_subq = (
        db.query(ProductImage.image_url)
        .filter(ProductImage.product_id == Product.id)
        .order_by(ProductImage.created_at.asc())
        .limit(1)
        .correlate(Product)
        .scalar_subquery()
    )

    rows = (
        db.query(
            Product.id.label("product_id"),
            Product.id.label("id"),
            Product.sku,
            Product.name,
            Product.description,
            Product.sale_price,
            Product.purchase_price,
            Product.stock_quantity,
            Product.qty_per_koli,
            Product.unit,
            image_subq.label("image_url"),
            CompaniesPrices.special_price,
            last_purchase_subq.label("last_purchase_price"),
        )
        .outerjoin(
            CompaniesPrices,
            and_(
                CompaniesPrices.product_id == Product.id,
                CompaniesPrices.companies_id == company_id,
            ),
        )
        .order_by(Product.name)
        .all()
    )

    result = []

    for r in rows:
        d = dict(r._mapping)

        d["has_special"] = d["special_price"] is not None
        d["effective_price"] = (
            d["special_price"]
            if d["special_price"] is not None
            else d["sale_price"]
        )

        d["images"] = (
            [{"image_url": d["image_url"]}]
            if d.get("image_url")
            else []
        )

        result.append(d)

    return result

# ---------------------------------------------------------------------------
# 4) PUT /company/{company_id}/prices/{product_id}   -> tildel/opdater særpris
# ---------------------------------------------------------------------------


@router.put("/{company_id}/prices/{product_id}")
def upsert_company_price(
    company_id: str,
    product_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    """Body: { "special_price": 35.50 }"""
    if not db.query(Company).filter(Company.id == company_id).first():
        raise HTTPException(status_code=404, detail="Company not found")

    if not db.query(Product).filter(Product.id == product_id).first():
        raise HTTPException(status_code=404, detail="Product not found")

    try:
        price = Decimal(str(payload.get("special_price")))
    except Exception:
        raise HTTPException(status_code=400, detail="Ugyldig special_price")

    if price < 0:
        raise HTTPException(
            status_code=400, detail="Pris kan ikke være negativ")

    existing = (
        db.query(CompaniesPrices)
        .filter(
            CompaniesPrices.companies_id == company_id,
            CompaniesPrices.product_id == product_id,
        )
        .first()
    )

    if existing:
        existing.special_price = price
    else:
        db.add(CompaniesPrices(
            id=str(uuid.uuid4()),
            companies_id=company_id,
            product_id=product_id,
            special_price=price,
        ))

    db.commit()
    return {
        "ok":            True,
        "company_id":    company_id,
        "product_id":    product_id,
        "special_price": float(price),
    }


# ---------------------------------------------------------------------------
# 5) DELETE /company/{company_id}/prices/{product_id}  -> fjern særpris
# ---------------------------------------------------------------------------
@router.delete("/{company_id}/prices/{product_id}")
def delete_company_price(
    company_id: str,
    product_id: str,
    db: Session = Depends(get_db),
):
    if not db.query(Company).filter(Company.id == company_id).first():
        raise HTTPException(status_code=404, detail="Company not found")

    deleted = (
        db.query(CompaniesPrices)
        .filter(
            CompaniesPrices.companies_id == company_id,
            CompaniesPrices.product_id == product_id,
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"ok": True, "deleted_rows": deleted}
