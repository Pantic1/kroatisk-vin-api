from email.mime import text
import uuid
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, DECIMAL, TIMESTAMP, Enum, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime
import enum

from sqlalchemy.ext.declarative import declarative_base
Base = declarative_base()


class OrderStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    shipped = "shipped"
    delivered = "delivered"
    cancelled = "cancelled"
    review = "review"

def generate_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    id = Column(CHAR(36), primary_key=True, default=generate_uuid)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(Text, nullable=False)
    role = Column(Enum("admin", "staff", "customer"), default="customer")
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


class CompaniesPrices(Base):
    __tablename__ = "companies_prices"
    id = Column(String(36), primary_key=True, default=generate_uuid)
    product_id = Column(CHAR(36), ForeignKey("products.id"), nullable=False)
    special_price = Column(DECIMAL(10, 2), nullable=False)
    companies_id = Column(String(36))

    product = relationship("Product", back_populates="special_prices")


class Order(Base):
    __tablename__ = "orders"
    id = Column(CHAR(36), primary_key=True, default=generate_uuid)
    customer_id = Column(CHAR(36), ForeignKey("companies.id"), nullable=False)
    order_id = Column(Integer, nullable=True)
    order_date = Column(TIMESTAMP, default=datetime.utcnow)
    status = Column(Enum(OrderStatus), default=OrderStatus.review)
    invoice_url  = Column(String(500), nullable=True)
    invoice_date = Column(DateTime,   nullable=True)    
    subtotal_price = Column(DECIMAL, nullable=True)
    tracking_number = Column(String, nullable=True)
    notes = Column(Text)

    items = relationship("OrderItem", back_populates="order")
    company = relationship("Company", back_populates="orders")


class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(CHAR(36), primary_key=True, default=generate_uuid)
    order_id = Column(CHAR(36), ForeignKey("orders.id"), nullable=False)
    product_id = Column(CHAR(36), ForeignKey("products.id"), nullable=False)
    quantity = Column(DECIMAL(10, 2), nullable=False)
    price = Column(DECIMAL(10, 2), nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")


class Product(Base):
    __tablename__ = "products"

    id = Column(String(36), primary_key=True,
                default=lambda: str(uuid.uuid4()))
    sku = Column(String(50), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    purchase_price = Column(DECIMAL(10, 2), nullable=False)
    qty_per_koli = Column(Integer, nullable=False)
    sale_price = Column(DECIMAL(10, 2), nullable=False)
    stock_quantity = Column(Integer, nullable=False)
    unit = Column(String(50), nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    images = relationship(
        "ProductImage", back_populates="product", cascade="all, delete")
    special_prices = relationship("CompaniesPrices", back_populates="product")
    order_items = relationship(
        "OrderItem", back_populates="product", cascade="all, delete")


class ProductImage(Base):
    __tablename__ = "product_images"
    id = Column(String(36), primary_key=True,
                default=lambda: str(uuid.uuid4()))
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False)
    image_url = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    product = relationship("Product", back_populates="images")


class Company(Base):
    __tablename__ = "companies"
    id = Column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    cvr: Mapped[str] = mapped_column(
        String(20), nullable=False, unique=True, index=True)
    company_type: Mapped[str] = mapped_column(
        String(100), nullable=True)   # fx ApS / A/S / Enkeltmandsvirksomhed
    industry: Mapped[str] = mapped_column(
        String(255), nullable=True)       # "463700 - Engroshandel …"
    vat_registered: Mapped[bool] = mapped_column(Boolean, default=True)
    ean: Mapped[str] = mapped_column(String(32), nullable=True)
    phone: Mapped[str] = mapped_column(String(50), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=True)
    website: Mapped[str] = mapped_column(String(255), nullable=True)
    address: Mapped[str] = mapped_column(String(255), nullable=True)
    zip: Mapped[str] = mapped_column(String(20), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=True)
    country: Mapped[str] = mapped_column(String(100), default="Danmark")
    iban: Mapped[str] = mapped_column(String(64), nullable=True)
    swift: Mapped[str] = mapped_column(String(32), nullable=True)
    notes: Mapped[str] = mapped_column(String(4000), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="Draft")  # Draft|Published|Archived

    # Renamed relationship
    contacts: Mapped[list["Contact"]] = relationship(
        "Contact",
        back_populates="company",
        cascade="all, delete-orphan",
    )
    orders = relationship("Order", back_populates="company")


    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Contact(Base):
    __tablename__ = "contacts"
    id = Column(String(36), primary_key=True,
                default=lambda: str(uuid.uuid4()))
    company_id: Mapped[int] = mapped_column(ForeignKey(
        "companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(
        String(100), nullable=True)  # fx Direktør, Ejer
    ownership_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    company: Mapped["Company"] = relationship(
        "Company", back_populates="contacts")

    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_Contact_company_name"),
    )
