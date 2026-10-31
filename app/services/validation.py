from math import isclose
from sqlalchemy.orm import Session
from ..models import Invoice, ValidationResult


def validate_invoice(db: Session, invoice: Invoice) -> list[ValidationResult]:
    db.query(ValidationResult).filter_by(invoice_id=invoice.id).delete()
    results: list[ValidationResult] = []
    required = ("invoice_number", "supplier_name", "total", "currency")
    for field in required:
        if getattr(invoice, field) is None:
            results.append(ValidationResult(invoice_id=invoice.id, rule="required_field", severity="warning", message=f"Missing {field}."))
    if all(value is not None for value in (invoice.subtotal, invoice.tax, invoice.total)):
        expected = round(invoice.subtotal + invoice.tax, 2)
        if abs(expected - invoice.total) > 0.02:
            results.append(ValidationResult(invoice_id=invoice.id, rule="total_math", severity="error", message=f"Subtotal + tax is {expected:.2f}, but total is {invoice.total:.2f}."))
    for field in ("subtotal", "tax", "total"):
        value = getattr(invoice, field)
        if value is not None and value < 0:
            results.append(ValidationResult(invoice_id=invoice.id, rule="non_negative_amount", severity="error", message=f"{field} cannot be negative."))
    item_totals = []
    for index, item in enumerate(invoice.line_items or [], start=1):
        quantity, unit_price, item_total = item.get("quantity"), item.get("unit_price"), item.get("total")
        if quantity is not None and unit_price is not None and item_total is not None:
            expected = round(quantity * unit_price, 2)
            if not isclose(expected, item_total, abs_tol=0.02):
                results.append(ValidationResult(invoice_id=invoice.id, rule="line_item_math", severity="error", message=f"Line {index}: quantity × unit price is {expected:.2f}, but line total is {item_total:.2f}."))
        if item_total is not None:
            item_totals.append(item_total)
    if invoice.subtotal is not None and item_totals and not isclose(round(sum(item_totals), 2), invoice.subtotal, abs_tol=0.02):
        results.append(ValidationResult(invoice_id=invoice.id, rule="line_item_subtotal", severity="warning", message=f"Line items total {sum(item_totals):.2f}, but subtotal is {invoice.subtotal:.2f}."))
    if invoice.invoice_number:
        duplicate = db.query(Invoice).filter(Invoice.invoice_number == invoice.invoice_number, Invoice.id != invoice.id).first()
        if duplicate:
            results.append(ValidationResult(invoice_id=invoice.id, rule="duplicate_number", severity="warning", message=f"Matches invoice {duplicate.id}."))
    if invoice.supplier_name and invoice.total is not None:
        probable = db.query(Invoice).filter(Invoice.supplier_name == invoice.supplier_name, Invoice.total == invoice.total, Invoice.id != invoice.id).first()
        if probable:
            results.append(ValidationResult(invoice_id=invoice.id, rule="probable_duplicate", severity="warning", message=f"Same supplier and total as invoice {probable.id}; review for a duplicate."))
    db.add_all(results)
    return results
