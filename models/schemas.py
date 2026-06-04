# models/schemas.py
from decimal import Decimal
from typing import Optional, List
from datetime import datetime
from sqlalchemy import Column
from typing_extensions import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, condecimal, constr, validator

# Brug ENUM fra dine modeller – undgå at redefinere her
from config.model import OrderStatus

# =========================
# Auth / Users
# =========================
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: Optional[str] = "user"

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    username: str
    email: EmailStr
    role: Optional[str]
    model_config = ConfigDict(from_attributes=True)

class TokenResponse(BaseModel):
    token: str
    token_type: str = "bearer"


# =========================
# Products
# =========================
class ProductImageBase(BaseModel):
    image_url: str

class ProductImageCreate(ProductImageBase):
    pass

class ProductImage(ProductImageBase):
    id: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class ProductBase(BaseModel):
    id: Optional[str] = None
    sku: str = Field(..., example="MATCHA-001")
    name: str
    description: str
    purchase_price: Decimal
    qty_per_koli: int
    sale_price: Decimal
    stock_quantity: int
    unit: Optional[str] = "stk"
    images: List[ProductImageBase] = Field(default_factory=list)

class ProductCreate(ProductBase):
    images: List[ProductImageCreate] = Field(default_factory=list)

class ProductUpdate(ProductBase):
    images: List[ProductImageCreate] = Field(default_factory=list)

class Product(ProductBase):
    id: str
    created_at: datetime
    images: List[ProductImage] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


# =========================
# Contacts / Companies
# =========================
class ContactBase(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    ownershipPct: Optional[float] = Field(default=None, alias="ownership_pct")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class ContactCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    ownershipPct: Optional[float] = None
    model_config = ConfigDict(populate_by_name=True)

class ContactUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    ownershipPct: Optional[float] = None
    model_config = ConfigDict(populate_by_name=True)

class CompanyBase(BaseModel):
    id: str
    name: str
    cvr: str
    companyType: Optional[str] = None
    industry: Optional[str] = None
    vatRegistered: bool = True
    ean: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    zip: Optional[str] = None
    city: Optional[str] = None
    country: str = "Danmark"
    iban: Optional[str] = None
    swift: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = "Draft"

    contacts: List[ContactBase] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class CompanyCreate(BaseModel):
    name: str
    cvr: str
    companyType: Optional[str] = None
    industry: Optional[str] = None
    vatRegistered: bool = True
    ean: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    zip: Optional[str] = None
    city: Optional[str] = None
    country: str = "Danmark"
    iban: Optional[str] = None
    swift: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = "Draft"

    contacts: Optional[List[ContactCreate]] = Field(default=None, alias="kontakter")

    model_config = ConfigDict(populate_by_name=True)

class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    cvr: Optional[str] = None
    companyType: Optional[str] = None
    industry: Optional[str] = None
    vatRegistered: Optional[bool] = None
    ean: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    zip: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    iban: Optional[str] = None
    swift: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None

    contacts: Optional[List[ContactCreate]] = Field(default=None, alias="kontakter")
    model_config = ConfigDict(populate_by_name=True)


# =========================
# Orders
# =========================
class OrderItemIn(BaseModel):
    product_id: str  # eller UUID
    unit_price: Decimal
    quantity: condecimal(gt=0) = Field(..., description="Antal i styk/koli")

class OrderCreateReview(BaseModel):
    customer_id: str  # eller UUID
    notes: Optional[str] = None
    subtotal_price: Optional[float] = None
    invoice_url: Optional[str] = None
    invoice_date: Optional[str] = None
    # Ignoreres server-side og sættes til 'review'
    status: Optional[str] = Field("review", description="Ignoreres server-side og sættes til 'review'")
    items: List[OrderItemIn]

class CompanyMini(BaseModel):
    id: str
    name: str
    cvr: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    zip: Optional[str] = None
    city: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class OrderItemOut(BaseModel):
    id: str
    product_id: str
    quantity: Decimal
    price: Decimal
    model_config = ConfigDict(from_attributes=True)

class SellerMini(BaseModel):
    id: str
    username: str
    model_config = ConfigDict(from_attributes=True)

class OrderOut(BaseModel):
    id: str
    order_id: Optional[int] = None
    customer_id: str
    seller_id: Optional[str] = None
    seller: Optional[SellerMini] = None
    customer: Optional[CompanyMini] = Field(default=None, alias="company")
    order_date: datetime
    status: str
    subtotal_price: Optional[float] = None
    invoice_url: Optional[str] = None
    invoice_date: Optional[datetime] = None
    tracking_number: Optional[str] = None
    notes: Optional[str] = None
    items: List[OrderItemOut]
    model_config = ConfigDict(from_attributes=True)

# (Valgfrit) Fladt felt, hvis du vil sende customer_name direkte
class OrderWithCustomerNameOut(OrderOut):
    customer_name: Optional[str] = None

class UpdateStatusRequest(BaseModel):
    status: Literal["pending","review","confirmed","shipped","delivered","cancelled"]
