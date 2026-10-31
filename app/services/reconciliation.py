from math import isclose
from sqlalchemy.orm import Session
from ..models import Invoice, ReconciliationResult


def _normalized(value: str | None) -> str:
    return "".join(char for char in (value or "").lower() if char.isalnum())


def _difference(field: str, source, candidate) -> dict | None:
    if source == candidate:
        return None
    return {"field": field, "source": source, "candidate": candidate}


def compare_invoices(source: Invoice, candidate: Invoice) -> tuple[float, list[dict]]:
    """Return an explainable match score and the field-level differences."""
    score = 0.0
    differences: list[dict] = []
    number_match = bool(source.invoice_number and source.invoice_number == candidate.invoice_number)
    supplier_match = bool(_normalized(source.supplier_name) and _normalized(source.supplier_name) == _normalized(candidate.supplier_name))
    amount_match = source.total is not None and candidate.total is not None and isclose(source.total, candidate.total, abs_tol=0.02)
    date_match = bool(source.invoice_date and source.invoice_date == candidate.invoice_date)

    score += 0.55 if number_match else 0.0
    score += 0.20 if supplier_match else 0.0
    score += 0.15 if amount_match else 0.0
    score += 0.10 if date_match else 0.0
    for field in ("invoice_number", "supplier_name", "invoice_date", "currency", "subtotal", "tax", "total"):
        difference = _difference(field, getattr(source, field), getattr(candidate, field))
        if difference:
            differences.append(difference)
    return round(score, 2), differences


def reconciliation_status(score: float) -> str:
    if score >= 0.95:
        return "exact_match"
    if score >= 0.60:
        return "match"
    if score >= 0.35:
        return "review"
    return "mismatch"


def run_reconciliation(db: Session, source: Invoice, candidate_ids: list[int] | None = None) -> list[ReconciliationResult]:
    query = db.query(Invoice).filter(Invoice.id != source.id)
    if candidate_ids:
        query = query.filter(Invoice.id.in_(candidate_ids))
    candidates = query.all()
    db.query(ReconciliationResult).filter_by(source_invoice_id=source.id).delete(synchronize_session=False)
    reports = []
    for candidate in candidates:
        score, differences = compare_invoices(source, candidate)
        report = ReconciliationResult(
            source_invoice_id=source.id,
            matched_invoice_id=candidate.id,
            match_score=score,
            status=reconciliation_status(score),
            differences=differences,
        )
        db.add(report)
        reports.append(report)
    db.flush()
    return sorted(reports, key=lambda report: report.match_score, reverse=True)
