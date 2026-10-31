from sqlalchemy.orm import Session
from ..models import AuditEvent, Document, Invoice
from .extraction import extract_invoice, extract_text
from .validation import validate_invoice


def process_document(db: Session, document_id: int) -> None:
    doc = db.get(Document, document_id)
    if not doc:
        return
    try:
        doc.status = "processing"; db.commit()
        text = extract_text(doc.storage_path)
        doc.text = text
        extraction = extract_invoice(text)
        invoice = doc.invoice or Invoice(document_id=doc.id)
        for key, value in extraction.model_dump().items():
            # model_dump() already turns Pydantic line items into dictionaries.
            # Retain support for model instances as well for callers that provide
            # an extraction object directly.
            if key == "line_items":
                value = [item.model_dump() if hasattr(item, "model_dump") else item for item in value]
            setattr(invoice, key, value)
        db.add(invoice); db.flush()
        validate_invoice(db, invoice)
        doc.status = "completed"
        db.add(AuditEvent(document_id=doc.id, event="processed", detail={"characters": len(text)}))
        db.commit()
    except Exception as exc:
        # The failed flush may have invalidated the current transaction.
        # Roll back first so the failure status itself is always persisted.
        db.rollback()
        doc = db.get(Document, document_id)
        if doc:
            doc.status = "failed"; doc.error = str(exc)
            db.add(AuditEvent(document_id=doc.id, event="failed", detail={"error": str(exc)})); db.commit()
        raise
