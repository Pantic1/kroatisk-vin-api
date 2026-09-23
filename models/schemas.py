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


# =========================
# Emballage / kvartalsafregning
# =========================
class PackagingMaterialBase(BaseModel):
    article_code: Optional[str] = Field(default=None, example="0108")
    name: str = Field(..., example="Graševina 0,75L")
    match_text: Optional[str] = None
    bottle_size: Optional[str] = None
    glass_kg: Optional[float] = Field(default=None, description="Tom flaskevægt i kg")
    carton_kg: float = 0.0648
    active: bool = True

class PackagingMaterialCreate(PackagingMaterialBase):
    pass

class PackagingMaterialUpdate(BaseModel):
    article_code: Optional[str] = None
    name: Optional[str] = None
    match_text: Optional[str] = None
    bottle_size: Optional[str] = None
    glass_kg: Optional[float] = None
    carton_kg: Optional[float] = None
    active: Optional[bool] = None

class PackagingMaterialOut(PackagingMaterialBase):
    id: str
    model_config = ConfigDict(from_attributes=True)


class PackagingLineIn(BaseModel):
    line_no: Optional[int] = None
    article_code: Optional[str] = None
    item_name: str
    quantity: int = 0
    glass_kg: Optional[float] = None
    carton_kg: float = 0.0648
    material_id: Optional[str] = None
    note: Optional[str] = None

class PackagingLineOut(PackagingLineIn):
    id: str
    status: str
    glass_total_kg: Optional[float] = None
    carton_total_kg: Optional[float] = None
    model_config = ConfigDict(from_attributes=True)


class PackagingInvoiceCreate(BaseModel):
    invoice_number: Optional[str] = None
    invoice_date: Optional[datetime] = None
    quarter: Optional[str] = Field(
        default=None, description="Udledes af datoen hvis den ikke sendes med")
    supplier: Optional[str] = "Galic"
    file_url: Optional[str] = None
    source_filename: Optional[str] = None
    notes: Optional[str] = None
    lines: List[PackagingLineIn] = Field(default_factory=list)

class PackagingInvoiceUpdate(PackagingInvoiceCreate):
    lines: Optional[List[PackagingLineIn]] = None

class PackagingInvoiceOut(BaseModel):
    id: str
    invoice_number: Optional[str] = None
    invoice_date: Optional[datetime] = None
    quarter: Optional[str] = None
    supplier: Optional[str] = None
    file_url: Optional[str] = None
    source_filename: Optional[str] = None
    notes: Optional[str] = None
    lines: List[PackagingLineOut] = Field(default_factory=list)
    total_bottles: int = 0
    total_glass_kg: Optional[float] = None
    total_carton_kg: Optional[float] = None
    missing_count: int = 0
    model_config = ConfigDict(from_attributes=True)


class ParsedLine(BaseModel):
    line_no: Optional[int] = None
    article_code: Optional[str] = None
    item_name: str
    quantity: int
    glass_kg: Optional[float] = None
    carton_kg: float = 0.0648
    material_id: Optional[str] = None
    matched_name: Optional[str] = None
    match_type: Optional[str] = None      # 'code' | 'name' | None
    match_confidence: Optional[float] = None
    status: str = "MANGLER"

class ParsedInvoice(BaseModel):
    invoice_number: Optional[str] = None
    invoice_date: Optional[datetime] = None
    quarter: Optional[str] = None
    supplier: str = "Galic"
    source_filename: Optional[str] = None
    packages: Optional[int] = None
    lines: List[ParsedLine] = Field(default_factory=list)
    unmatched_count: int = 0
    duplicate_of: Optional[str] = Field(
        default=None, description="Id på en allerede gemt faktura med samme nummer")
    warnings: List[str] = Field(default_factory=list)


class QuarterSummary(BaseModel):
    quarter: str
    bottles: int
    glass_kg: Optional[float] = None
    carton_kg: float = 0.0
    invoices: int = 0
    missing_count: int = 0
    status: str = "OK"
