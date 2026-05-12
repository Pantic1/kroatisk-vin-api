from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from config.config import get_db
from config.model import Product, ProductImage
from models.schemas import ProductBase, ProductCreate, ProductUpdate
from sqlalchemy.orm import joinedload
router = APIRouter()


@router.post("/", response_model=ProductBase)
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    # Tjek om SKU allerede findes
    existing = db.query(Product).filter(Product.sku == product.sku).first()
    if existing:
        raise HTTPException(status_code=400, detail="SKU already exists")

    db_product = Product(
        sku=product.sku,
        name=product.name,
        description=product.description,
        purchase_price=product.purchase_price,
        qty_per_koli=product.qty_per_koli,
        sale_price=product.sale_price,  
        stock_quantity=product.stock_quantity,
        unit=product.unit,
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)

    # Tilføj billeder
    for img in product.images:
        db_image = ProductImage(product_id=db_product.id, image_url=img.image_url)
        db.add(db_image)
    db.commit()
    db.refresh(db_product)

    return db_product

@router.get("/", response_model=list[ProductBase])
def list_products(db: Session = Depends(get_db)):
    products = db.query(Product).options(joinedload(Product.images)).all()
    return products


@router.get("/{product_id}", response_model=ProductBase)
def get_product(product_id: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@router.put("/{product_id}", response_model=ProductBase)
def update_product(product_id: str, product_data: ProductUpdate, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    for key, value in product_data.dict(exclude_unset=True).items():
        if key != "images":
            setattr(product, key, value)

    # Opdater billeder
    db.query(ProductImage).filter(ProductImage.product_id == product_id).delete()
    for img in product_data.images:
        db_image = ProductImage(product_id=product.id, image_url=img.image_url)
        db.add(db_image)

    db.commit()
    db.refresh(product)
    return product

@router.delete("/{product_id}")
def delete_product(product_id: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(product)
    db.commit()
    return {"detail": "Product deleted successfully"}
