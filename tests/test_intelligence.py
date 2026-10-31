from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Document, Invoice
from app.services.reconciliation import run_reconciliation
from app.services.validation import validate_invoice


def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def invoice(db, number, supplier, total, **values):
    index = db.query(Document).count()
    document = Document(filename=f"{number}-{index}.pdf", storage_path=f"/{number}-{index}.pdf", status="completed")
    db.add(document); db.flush()
    item = Invoice(document_id=document.id, invoice_number=number, supplier_name=supplier, total=total, currency="USD", **values)
    db.add(item); db.flush()
    return item


def test_validation_catches_line_math_and_probable_duplicate():
    db = session()
    invoice(db, "INV-1", "Acme", 100.0)
    target = invoice(db, "INV-2", "Acme", 100.0, subtotal=100.0, tax=0.0, line_items=[{"quantity": 2, "unit_price": 20.0, "total": 30.0}])
    results = validate_invoice(db, target)
    assert {result.rule for result in results} >= {"line_item_math", "line_item_subtotal", "probable_duplicate"}


def test_reconciliation_persists_explainable_exact_match():
    db = session()
    source = invoice(db, "INV-100", "Acme Ltd", 110.0, invoice_date="2026-10-31", subtotal=100.0, tax=10.0)
    candidate = invoice(db, "INV-100", "Acme Ltd", 110.0, invoice_date="2026-10-31", subtotal=100.0, tax=10.0)
    reports = run_reconciliation(db, source)
    assert reports[0].matched_invoice_id == candidate.id
    assert reports[0].status == "exact_match"
    assert reports[0].differences == []
