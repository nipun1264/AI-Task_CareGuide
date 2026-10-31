from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    storage_path: Mapped[str] = mapped_column(String(1024), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    invoice: Mapped["Invoice | None"] = relationship(back_populates="document", uselist=False, cascade="all, delete-orphan")


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), unique=True)
    invoice_number: Mapped[str | None] = mapped_column(String(128), index=True)
    invoice_date: Mapped[str | None] = mapped_column(String(32))
    supplier_name: Mapped[str | None] = mapped_column(String(256), index=True)
    customer_name: Mapped[str | None] = mapped_column(String(256))
    subtotal: Mapped[float | None] = mapped_column(Float)
    tax: Mapped[float | None] = mapped_column(Float)
    adjustment: Mapped[float | None] = mapped_column(Float)
    total: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(8))
    line_items: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float | None] = mapped_column(Float)
    document: Mapped[Document] = relationship(back_populates="invoice")
    validations: Mapped[list["ValidationResult"]] = relationship(cascade="all, delete-orphan")


class ValidationResult(Base):
    __tablename__ = "validation_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    rule: Mapped[str] = mapped_column(String(128))
    severity: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    event: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ReconciliationResult(Base):
    __tablename__ = "reconciliation_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    matched_invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    match_score: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32))
    differences: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
