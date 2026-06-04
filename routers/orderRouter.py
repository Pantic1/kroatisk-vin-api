# routers/companies.py
from ast import List
from datetime import datetime
from decimal import Decimal
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.params import Body
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy.exc import SQLAlchemyError
from services.dinero_client import DineroError
from services.dinero_invoice import book_invoice, create_invoice_draft
from services.ftp_upload import upload_bytes_to_ftp
from services.gls import create_shipment, GLSCreateError
from services.gls_mapper import map_order_to_gls_payload

from config.config import get_db
from config.model import Order, OrderItem, OrderStatus, Product, Company
from models.schemas import OrderCreateReview, OrderItemOut, OrderOut, OrderWithCustomerNameOut, UpdateStatusRequest
from services.invoice_pdf import build_invoice_pdf

router = APIRouter()


@router.post("/review", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order_in_review(payload: OrderCreateReview, db: Session = Depends(get_db)):
    customer = db.get(Company, payload.customer_id)

    if not customer:
        raise HTTPException(status_code=404, detail="Company not found")

    if not payload.items:
        raise HTTPException(
            status_code=400,
            detail="Order must contain at least one item"
        )

    order = Order(
        customer_id=str(payload.customer_id),
        order_date=datetime.utcnow(),
        status=OrderStatus.review,
        subtotal_price=payload.subtotal_price,
        notes=payload.notes or None,
    )

    db.add(order)
    db.flush()

    created_items: List[OrderItem] = []

    for line in payload.items:
        product = db.get(Product, line.product_id)

        if not product:
            raise HTTPException(
                status_code=400,
                detail=f"Product not found: {line.product_id}"
            )

        # VIGTIGT:
        # Brug prisen fra frontend/cart/company price
        # IKKE product.sale_price
        price = Decimal(str(line.unit_price))
        quantity = Decimal(str(line.quantity))

        oi = OrderItem(
            order_id=order.id,
            product_id=str(product.id),
            quantity=quantity,
            price=price,
        )

        created_items.append(oi)
        db.add(oi)

    db.commit()
    db.refresh(order)

    for oi in created_items:
        db.refresh(oi)

    return OrderOut(
        id=str(order.id),
        customer_id=str(order.customer_id),
        order_date=order.order_date,
        status=order.status.value if hasattr(
            order.status, "value") else str(order.status),
        notes=order.notes,
        items=[
            OrderItemOut(
                id=str(oi.id),
                product_id=str(oi.product_id),
                quantity=oi.quantity,
                price=oi.price,
            )
            for oi in created_items
        ],
    )


@router.get("/sellers")
def list_sellers(db: Session = Depends(get_db)):
    from config.model import User
    users = db.query(User).all()
    return [{"id": u.id, "username": u.username} for u in users]


@router.get("/", response_model=list[OrderOut])
def list_orders_all(db: Session = Depends(get_db)):
    orders = (db.query(Order)
                .options(joinedload(Order.company), joinedload(Order.seller), selectinload(Order.items))
                .order_by(Order.order_date.desc())
                .all())
    return orders


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: str, db: Session = Depends(get_db)):
    order = (db.query(Order)
             .options(joinedload(Order.company), joinedload(Order.seller), selectinload(Order.items))
             .filter(Order.id == order_id)
             .first())
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.put("/{order_id}/seller")
def update_order_seller(order_id: str, payload: dict = Body(...), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order.seller_id = payload.get("seller_id")
    db.commit()
    return {"ok": True}


@router.put("/{order_id}/status")
def update_order_status(order_id: str, payload: UpdateStatusRequest, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = payload.status
    db.add(order)
    db.commit()
    db.refresh(order)
    return {"message": "Order status updated", "order": order}


@router.post("/{order_id}/approve")
def approve_order(order_id: str, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status != "review":
        raise HTTPException(
            status_code=400, detail="Order is not in review state")

    company = db.query(Company).filter(Company.id == order.customer_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Customer not found")

    # ---- 1) Hent ordrelinjer + produktnavne ----
    item_rows = (
        db.query(OrderItem, Product)
        .join(Product, Product.id == OrderItem.product_id)
        .filter(OrderItem.order_id == order.id)
        .all()
    )
    if not item_rows:
        raise HTTPException(status_code=400, detail="Ordren har ingen linjer")

    lines = [
        {
            "name":       prod.name,
            "sku":        prod.sku,
            "quantity":   float(oi.quantity),
            "unit_price": float(oi.price),
            "line_total": float(oi.quantity) * float(oi.price),
        }
        for (oi, prod) in item_rows
    ]

    # ---- 2) Generér PDF ----
    try:
        pdf_bytes = build_invoice_pdf(order, company, lines)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Kunne ikke generere faktura: {e}")

    # ---- 3) Upload til FTP ----
    filename = f"faktura-{order.order_id}-{uuid.uuid4().hex[:8]}.pdf"
    try:
        invoice_url = upload_bytes_to_ftp(pdf_bytes, filename)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Kunne ikke uploade faktura: {e}")

    # ---- 4) Opdater ordre i DB ----
    try:
        order.status = "confirmed"
        order.invoice_url = invoice_url
        order.invoice_date = datetime.utcnow()
        db.add(order)
        db.commit()
        db.refresh(order)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Kunne ikke gemme ordre: {e}")

    return {
        "message":     "Order approved",
        "invoice_url": invoice_url,
        "order":       order,
    }


@router.post("/{order_id}/dinero")
def create_dinero_invoice(order_id: str, book: bool = True, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.company:
        raise HTTPException(status_code=422, detail="Order mangler company")

    try:
        inv = create_invoice_draft(order)
        invoice_guid = inv.get("Guid") or inv.get(
            "GuidId") or inv.get("InvoiceGuid")
        if not invoice_guid:
            raise HTTPException(
                status_code=500, detail="Kunne ikke få Invoice Guid fra Dinero")
        booked = None
        if book:
            booked = book_invoice(invoice_guid)
        return {"invoice": inv, "booked": booked}
    except DineroError as e:
        raise HTTPException(status_code=502, detail=f"Dinero: {e}")


@router.put("/{order_id}/items")
def update_order_items(
    order_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    # 1) Find ordre
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # 2) Tjek status
    if order.status != "review":
        raise HTTPException(
            status_code=400,
            detail=f"Ordre kan kun redigeres når status er 'review' (er: {order.status})",
        )

    items = payload.get("items")
    if not isinstance(items, list):
        raise HTTPException(
            status_code=400, detail="'items' skal være en liste")

    if len(items) == 0:
        raise HTTPException(
            status_code=400, detail="Ordre skal have mindst én linje")

    # 3) Validér hver linje + tjek at produkterne findes
    cleaned = []
    for line in items:
        product_id = line.get("product_id")
        if not product_id:
            raise HTTPException(
                status_code=400, detail="Hver linje skal have product_id")

        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(
                status_code=400,
                detail=f"Produkt {product_id} findes ikke",
            )

        try:
            qty = Decimal(str(line.get("quantity")))
            price = Decimal(str(line.get("price")))
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="quantity og price skal være tal",
            )

        if qty <= 0:
            raise HTTPException(status_code=400, detail="Antal skal være > 0")
        if price < 0:
            raise HTTPException(
                status_code=400, detail="Pris kan ikke være negativ")

        cleaned.append({"product_id": product_id,
                       "quantity": qty, "price": price})

    # 4) Slet alle eksisterende linjer + indsæt nye
    try:
        db.query(OrderItem).filter(OrderItem.order_id == order.id).delete(
            synchronize_session=False
        )
        db.flush()

        new_subtotal = Decimal("0")
        for ln in cleaned:
            db.add(OrderItem(
                order_id=order.id,
                product_id=ln["product_id"],
                quantity=ln["quantity"],
                price=ln["price"],
            ))
            new_subtotal += ln["quantity"] * ln["price"]

        # 5) Opdater subtotal på ordren
        order.subtotal_price = float(new_subtotal)
        db.add(order)
        db.commit()
        db.refresh(order)

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"DB-fejl: {e}")

    return {
        "ok":            True,
        "order_id":      order.id,
        "items_count":   len(cleaned),
        "subtotal_price": float(order.subtotal_price or 0),
    }
