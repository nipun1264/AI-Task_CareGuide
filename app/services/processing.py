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
            setattr(invoice, key, [item.model_dump() for item in value] if key == "line_items" else value)
        db.add(invoice); db.flush()
        validate_invoice(db, invoice)
        doc.status = "completed"
        db.add(AuditEvent(document_id=doc.id, event="processed", detail={"characters": len(text)}))
        db.commit()
    except Exception as exc:
        doc.status = "failed"; doc.error = str(exc)
        db.add(AuditEvent(document_id=doc.id, event="failed", detail={"error": str(exc)})); db.commit()
        raise
