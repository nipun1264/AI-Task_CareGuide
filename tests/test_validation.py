from app.schemas import InvoiceExtraction
from app.services.extraction import rule_based_extract


def test_rule_extractor_finds_core_amounts():
    invoice = rule_based_extract("Invoice No: INV-001\nSubtotal: $100.00\nTax: $10.00\nGrand Total: $110.00")
    assert invoice.invoice_number == "INV-001"
    assert invoice.subtotal == 100.0
    assert invoice.tax == 10.0
    assert invoice.total == 110.0
