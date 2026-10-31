from sqlalchemy.orm import Session
from ..models import Invoice, ValidationResult


def validate_invoice(db: Session, invoice: Invoice) -> list[ValidationResult]:
    db.query(ValidationResult).filter_by(invoice_id=invoice.id).delete()
    results: list[ValidationResult] = []
    required = ("invoice_number", "supplier_name", "total")
    for field in required:
        if getattr(invoice, field) is None:
            results.append(ValidationResult(invoice_id=invoice.id, rule="required_field", severity="warning", message=f"Missing {field}."))
    if all(value is not None for value in (invoice.subtotal, invoice.tax, invoice.total)):
        expected = round(invoice.subtotal + invoice.tax, 2)
        if abs(expected - invoice.total) > 0.02:
            results.append(ValidationResult(invoice_id=invoice.id, rule="total_math", severity="error", message=f"Subtotal + tax is {expected:.2f}, but total is {invoice.total:.2f}."))
    if invoice.invoice_number:
        duplicate = db.query(Invoice).filter(Invoice.invoice_number == invoice.invoice_number, Invoice.id != invoice.id).first()
        if duplicate:
            results.append(ValidationResult(invoice_id=invoice.id, rule="duplicate_number", severity="warning", message=f"Matches invoice {duplicate.id}."))
    db.add_all(results)
    return results
