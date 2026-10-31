import shutil
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session
from .config import settings
from .database import get_db
from .models import AuditEvent, Document, Invoice, ReconciliationResult
from .schemas import Correction
from .services.processing import process_document
from .services.validation import validate_invoice
from .services.reconciliation import run_reconciliation
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


def reconciliation_view(result: ReconciliationResult, db: Session) -> dict:
    candidate = db.get(Invoice, result.matched_invoice_id)
    return {"id": result.id, "match_score": result.match_score, "status": result.status,
            "differences": result.differences, "candidate": invoice_view(candidate) if candidate else None,
            "created_at": result.created_at}


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
    doc.status = "queued"; doc.error = None; db.commit()
    try:
        process_document_task.delay(doc.id)
    except Exception:
        process_document(db, doc.id)
    return {"id": doc.id, "status": "queued"}


@router.post("/documents/retry-failed", status_code=202)
def retry_failed_documents(db: Session = Depends(get_db)):
    failed = db.query(Document).filter_by(status="failed").all()
    for doc in failed:
        doc.status = "queued"; doc.error = None
        db.add(AuditEvent(document_id=doc.id, event="retry_queued", detail={}))
    db.commit()
    for doc in failed:
        try:
            process_document_task.delay(doc.id)
        except Exception:
            process_document(db, doc.id)
    return {"retried_document_ids": [doc.id for doc in failed]}


@router.patch("/invoices/{invoice_id}")
def correct_invoice(invoice_id: int, correction: Correction, db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice: raise HTTPException(404, "Invoice not found")
    changed = correction.model_dump(exclude_unset=True)
    reason = changed.pop("reason", None)
    for key, value in changed.items(): setattr(invoice, key, [item.model_dump() for item in value] if key == "line_items" and value else value)
    db.add(AuditEvent(document_id=invoice.document_id, event="manual_correction", detail={"changed": changed, "reason": reason})); db.flush(); validate_invoice(db, invoice); db.commit(); db.refresh(invoice)
    return invoice_view(invoice)


@router.post("/invoices/{invoice_id}/validate")
def validate_existing_invoice(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice: raise HTTPException(404, "Invoice not found")
    validate_invoice(db, invoice); db.commit(); db.refresh(invoice)
    return invoice_view(invoice)


@router.get("/invoices/{invoice_id}/history")
def invoice_history(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice: raise HTTPException(404, "Invoice not found")
    events = db.query(AuditEvent).filter_by(document_id=invoice.document_id).order_by(AuditEvent.created_at.desc()).all()
    return [{"event": event.event, "detail": event.detail, "created_at": event.created_at} for event in events]


@router.get("/search")
def search(q: str, severity: str | None = None, db: Session = Depends(get_db)):
    term = f"%{q}%"
    query = db.query(Invoice).join(Document).filter(or_(Invoice.invoice_number.ilike(term), Invoice.supplier_name.ilike(term), Document.text.ilike(term)))
    if severity:
        query = query.join(Invoice.validations).filter_by(severity=severity)
    results = []
    needle = q.lower()
    for invoice in query.distinct().all():
        score = 0
        if (invoice.invoice_number or "").lower() == needle: score += 100
        elif needle in (invoice.invoice_number or "").lower(): score += 60
        if needle in (invoice.supplier_name or "").lower(): score += 40
        if needle in (invoice.document.text or "").lower(): score += 10
        results.append({"relevance": score, "invoice": invoice_view(invoice)})
    return sorted(results, key=lambda result: result["relevance"], reverse=True)


@router.post("/reconciliation/{invoice_id}/run")
def reconcile(invoice_id: int, candidate_ids: list[int] | None = None, db: Session = Depends(get_db)):
    source = db.get(Invoice, invoice_id)
    if not source: raise HTTPException(404, "Invoice not found")
    reports = run_reconciliation(db, source, candidate_ids); db.commit()
    return [reconciliation_view(report, db) for report in reports]


@router.get("/reconciliation/{invoice_id}")
def reconciliation_results(invoice_id: int, db: Session = Depends(get_db)):
    source = db.get(Invoice, invoice_id)
    if not source: raise HTTPException(404, "Invoice not found")
    reports = db.query(ReconciliationResult).filter_by(source_invoice_id=invoice_id).order_by(ReconciliationResult.match_score.desc()).all()
    return [reconciliation_view(report, db) for report in reports]
