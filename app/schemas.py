from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str | None = None
    quantity: float | None = None
    unit_price: float | None = None
    tax: float | None = None
    total: float | None = None


class InvoiceExtraction(BaseModel):
    invoice_number: str | None = None
    invoice_date: str | None = None
    supplier_name: str | None = None
    customer_name: str | None = None
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    currency: str | None = None
    line_items: list[LineItem] = Field(default_factory=list)
    confidence: float | None = None


class Correction(BaseModel):
    invoice_number: str | None = None
    invoice_date: str | None = None
    supplier_name: str | None = None
    customer_name: str | None = None
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    currency: str | None = None
    line_items: list[LineItem] | None = None
