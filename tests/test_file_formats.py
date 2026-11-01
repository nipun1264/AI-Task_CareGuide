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


def test_extracts_spreadsheet_style_sales_invoice_csv(tmp_path):
    path = tmp_path / "sales-layout.csv"
    path.write_text("""\n,INVOICE,,,,\n,SHADOW BEAUTY,,,,\n,TO,Jens Martensson,,DATE,11/1/2026\n,INVOICE #,54167,,,,\n,QTY,ITEM #,DESCRIPTION,UNIT PRICE,DISCOUNT,LINE TOTAL\n,50,2452,Liquid foundation,$2.75,$0.00,$137.50\n,30,6235,Eyeshadow palette,$1.24,$0.00,$37.20\n,,,,,SUBTOTAL,$174.70\n,,,,,SALES TAX,$0.00\n,,,,,TOTAL,$174.70\n""", encoding="utf-8")

    invoice = rule_based_extract(extract_text(str(path)))
    assert invoice.invoice_number == "54167"
    assert invoice.supplier_name == "SHADOW BEAUTY"
    assert invoice.customer_name == "Jens Martensson"
    assert invoice.invoice_date == "01/11/2026"
    assert invoice.subtotal == 174.70
    assert invoice.tax == 0.0
    assert invoice.total == 174.70
    assert invoice.adjustment is None
    assert [(item.description, item.quantity, item.discount, item.total) for item in invoice.line_items] == [
        ("Liquid foundation", 50.0, 0.0, 137.50),
        ("Eyeshadow palette", 30.0, 0.0, 37.20),
    ]


def test_extracts_spreadsheet_style_sales_invoice_xlsx(tmp_path):
    path = tmp_path / "sales-layout.xlsx"
    rows = [
        ["", "INVOICE", "", "", "", "", ""],
        ["", "SHADOW BEAUTY", "", "", "", "", ""],
        ["", "TO", "Jens Martensson", "", "DATE", "11/1/2026", ""],
        ["", "INVOICE #", "54167", "", "", "", ""],
        ["", "QTY", "ITEM #", "DESCRIPTION", "UNIT PRICE", "DISCOUNT", "LINE TOTAL"],
        ["", "50", "2452", "Liquid foundation", "$2.75", "$0.00", "$137.50"],
        ["", "", "", "", "", "SUBTOTAL", "$137.50"],
        ["", "", "", "", "", "SALES TAX", "$0.00"],
        ["", "", "", "", "", "TOTAL", "$137.50"],
    ]
    pd.DataFrame(rows).to_excel(path, index=False, header=False)

    invoice = rule_based_extract(extract_text(str(path)))
    assert invoice.invoice_number == "54167"
    assert invoice.supplier_name == "SHADOW BEAUTY"
    assert invoice.customer_name == "Jens Martensson"
    assert invoice.invoice_date == "01/11/2026"
    assert invoice.subtotal == 137.50
    assert invoice.tax == 0.0
    assert invoice.total == 137.50
    assert len(invoice.line_items) == 1
