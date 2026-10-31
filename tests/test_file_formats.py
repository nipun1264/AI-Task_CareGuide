import fitz
import pandas as pd
from PIL import Image
import pytesseract

from app.services.extraction import extract_text, rule_based_extract


TABULAR_INVOICE = {
    "Invoice No": "TAB-001",
    "Date": "2026-10-31",
    "Supplier": "Acme Supplies",
    "Customer": "Northwind Traders",
    "Subtotal": "100.00",
    "Tax": "10.00",
    "Total": "110.00",
    "Currency": "USD",
}


def _assert_tabular_invoice(path):
    invoice = rule_based_extract(extract_text(str(path)))
    assert invoice.invoice_number == "TAB-001"
    assert invoice.supplier_name == "Acme Supplies"
    assert invoice.customer_name == "Northwind Traders"
    assert invoice.subtotal == 100.0
    assert invoice.tax == 10.0
    assert invoice.total == 110.0
    assert invoice.currency == "USD"


def test_extracts_csv_invoice_columns(tmp_path):
    path = tmp_path / "invoice.csv"
    pd.DataFrame([TABULAR_INVOICE]).to_csv(path, index=False)
    _assert_tabular_invoice(path)


def test_extracts_xlsx_invoice_columns(tmp_path):
    path = tmp_path / "invoice.xlsx"
    pd.DataFrame([TABULAR_INVOICE]).to_excel(path, index=False)
    _assert_tabular_invoice(path)


def test_extracts_text_pdf(tmp_path):
    path = tmp_path / "invoice.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Invoice No: PDF-001\nSubtotal: $100.00\nTax: $10.00\nTotal: $110.00")
    document.save(path)
    assert "PDF-001" in extract_text(str(path))


def test_extracts_image_via_ocr_path(tmp_path, monkeypatch):
    path = tmp_path / "invoice.png"
    Image.new("RGB", (20, 20), "white").save(path)
    monkeypatch.setattr(
        pytesseract,
        "image_to_string",
        lambda *_args, **_kwargs: "Invoice No: IMG-001\nSubtotal: $100.00\nTax: $10.00\nTotal: $110.00",
    )
    invoice = rule_based_extract(extract_text(str(path)))
    assert invoice.invoice_number == "IMG-001"
    assert invoice.total == 110.0
