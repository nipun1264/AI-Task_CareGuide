import shutil
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session
from .config import settings
from .database import get_db
from .models import AuditEvent, Document, Invoice, ValidationResult
from .schemas import Correction
from .services.processing import process_document
from .services.validation import validate_invoice
from .workers.tasks import process_document_task

router = APIRouter(prefix="/api/v1")
SUPPORTED = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".xlsx", ".xls", ".csv"}


def document_view(doc: Document) -> dict:
    invoice = doc.invoice
    return {"id": doc.id, "filename": doc.filename, "status": doc.status, "error": doc.error,
            "created_at": doc.created_at, "invoice": invoice_view(invoice) if invoice else None}


def invoice_view(invoice: Invoice) -> dict:
    return {"id": invoice.id, "document_id": invoice.document_id, "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date, "supplier_name": invoice.supplier_name, "customer_name": invoice.customer_name,
            "subtotal": invoice.subtotal, "tax": invoice.tax, "total": invoice.total, "currency": invoice.currency,
            "line_items": invoice.line_items, "confidence": invoice.confidence,
            "validations": [{"rule": x.rule, "severity": x.severity, "message": x.message} for x in invoice.validations]}


@router.post("/documents/upload", status_code=202)
def upload_documents(files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    accepted = []
    for upload in files:
        suffix = Path(upload.filename or "").suffix.lower()
        if suffix not in SUPPORTED:
            raise HTTPException(415, f"Unsupported extension {suffix}; expected one of {sorted(SUPPORTED)}")
        path = settings.storage_path / f"{uuid4()}{suffix}"
        with path.open("wb") as handle:
            shutil.copyfileobj(upload.file, handle)
        if path.stat().st_size > settings.max_upload_mb * 1024 * 1024:
            path.unlink(); raise HTTPException(413, "File exceeds configured upload limit")
        doc = Document(filename=upload.filename or path.name, content_type=upload.content_type, storage_path=str(path))
        db.add(doc); db.flush(); db.add(AuditEvent(document_id=doc.id, event="queued", detail={})); db.commit(); db.refresh(doc)
        try:
            process_document_task.delay(doc.id)
        except Exception:
            # Local development remains useful without Redis/Celery.
            process_document(db, doc.id); db.refresh(doc)
        accepted.append(document_view(doc))
    return {"documents": accepted}


@router.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    return [document_view(doc) for doc in db.query(Document).order_by(Document.created_at.desc()).all()]


@router.get("/documents/{document_id}")
def get_document(document_id: int, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc: raise HTTPException(404, "Document not found")
    return document_view(doc)


@router.post("/documents/{document_id}/reprocess", status_code=202)
def reprocess(document_id: int, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc: raise HTTPException(404, "Document not found")
    doc.status = "queued"; db.commit()
    process_document_task.delay(doc.id)
    return {"id": doc.id, "status": "queued"}


@router.patch("/invoices/{invoice_id}")
def correct_invoice(invoice_id: int, correction: Correction, db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice: raise HTTPException(404, "Invoice not found")
    changed = correction.model_dump(exclude_unset=True)
    for key, value in changed.items(): setattr(invoice, key, [item.model_dump() for item in value] if key == "line_items" and value else value)
    db.add(AuditEvent(document_id=invoice.document_id, event="manual_correction", detail=changed)); db.flush(); validate_invoice(db, invoice); db.commit(); db.refresh(invoice)
    return invoice_view(invoice)


@router.get("/search")
def search(q: str, db: Session = Depends(get_db)):
    term = f"%{q}%"
    results = db.query(Invoice).join(Document).filter(or_(Invoice.invoice_number.ilike(term), Invoice.supplier_name.ilike(term), Document.text.ilike(term))).all()
    return [invoice_view(invoice) for invoice in results]


@router.get("/reconciliation/{invoice_id}")
def reconcile(invoice_id: int, db: Session = Depends(get_db)):
    source = db.get(Invoice, invoice_id)
    if not source: raise HTTPException(404, "Invoice not found")
    candidates = db.query(Invoice).filter(Invoice.id != source.id, or_(Invoice.invoice_number == source.invoice_number, Invoice.supplier_name == source.supplier_name)).all()
    return [{"invoice": invoice_view(other), "total_matches": other.total == source.total, "number_matches": other.invoice_number == source.invoice_number} for other in candidates]
