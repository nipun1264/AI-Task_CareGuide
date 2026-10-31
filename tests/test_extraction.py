from app.services.extraction import rule_based_extract


INVOICE_TEXT = """
John Smith :
4490 Oak Drive
Albany, NY 12210
BILL TO SHIP TO INVOICE # INT-001
Jessie M Horne Jessie M Horne INVOICE DATE 11/02/2019
4312 Wood Road 2019 Redbud Drive PO.
New York, NY 10031 New York, NY 10011
DUE DATE 26/02/2019
QTY DESCRIPTION UNIT PRICE AMOUNT
1 Front and rear brake cables 100.00 100.00
2 New set of pedal arms 25.00 50.00
3 Labor 3hrs 15.00 45.00
Subtotal 195.00
Sales Tax 5.0% 9.75
TOTAL $204.75
"""


def test_extracts_labeled_people_and_amounts_from_two_column_invoice():
    invoice = rule_based_extract(INVOICE_TEXT)

    assert invoice.supplier_name == "John Smith"
    assert invoice.customer_name == "Jessie M Horne"
    assert invoice.invoice_number == "INT-001"
    assert invoice.subtotal == 195.00
    assert invoice.tax == 9.75
    assert invoice.total == 204.75
    assert invoice.currency == "$"
    assert invoice.confidence == 0.95


def test_accepts_billed_to_written_dates_and_dynamic_tax_presentation():
    invoice = rule_based_extract("""
    Billed to:
    Estelle Darcy 30 July 2025
    123 Anywhere St., Any City, ST 12345

    Invoice No. 12345
    30 July 2025

    Subtotal $870
    Tax (10%) $87
    Total $957
    Pay by: 10 July 2025
    """)

    assert invoice.customer_name == "Estelle Darcy"
    assert invoice.invoice_number == "12345"
    assert invoice.invoice_date == "30/07/2025"
    assert invoice.tax == 87.00


def test_parses_a_final_comma_as_a_decimal_separator_when_no_dot_exists():
    invoice = rule_based_extract("""
    Invoice No. 1234567890
    Subtotal $123
    Tax (11%) $1,23
    Total $124,23
    """)

    assert invoice.subtotal == 123.00
    assert invoice.tax == 1.23
    assert invoice.total == 124.23
    assert invoice.confidence == 0.57


def test_parses_two_column_header_with_ordinal_date_and_comma_amounts():
    invoice = rule_based_extract("""
    No, 1234567890 | 12th December 2025 Fradel and
    Spies
    INVOICE
    Thank you for your illed to:
    purchase! Samira Hadid
    Subtotal | $123
    Tax (11%) | $1,23
    Total | $124,23
    """)

    assert invoice.invoice_number == "1234567890"
    assert invoice.invoice_date == "12/12/2025"
    assert invoice.supplier_name == "Fradel and Spies"
    assert invoice.customer_name == "Samira Hadid"
    assert invoice.subtotal == 123.00
    assert invoice.tax == 1.23
    assert invoice.total == 124.23
    assert invoice.confidence == 0.95


def test_parses_receipt_labels_and_amounts_printed_after_values():
    invoice = rule_based_extract("""
    --AARONG--
    Tax Invoice (MUSAK-6.3)
    Receipt No : NS083000111537
    30/10/2026 8:36:41PM Date :
    Sub Total 250.00
    (-) Less Discount 15.00
    17.63 (+) Add VAT
    252.63 Net Payable
    Tk 15 cashback
    """)

    assert invoice.invoice_number == "NS083000111537"
    assert invoice.invoice_date == "30/10/2026"
    assert invoice.supplier_name == "Aarong"
    assert invoice.subtotal == 250.00
    assert invoice.adjustment == -15.00
    assert invoice.tax == 17.63
    assert invoice.total == 252.63
    assert invoice.currency == "BDT"


def test_parses_indian_vat_invoice_with_seller_client_and_table_rows():
    invoice = rule_based_extract("""
    Invoice no: 51109305
    Date of issue:
    09/03/2024
    Seller:
    TechVision Distributors Pvt Ltd
    Client:
    Hyderabad IT Traders
    ITEMS
    No.
    Description
    Qty
    UM
    Net Price
    Net Worth
    VAT %
    Gross Worth
    1.
    Belkin MagSafe 3-in-1 Wireless Charger
    9.00
    pcs
    8,175.00
    73,575.00
    10%
    80,932.50
    2.
    Samsung Galaxy S24 256GB Phantom
    Black
    8.00
    pcs
    72,370.00
    578,960.00
    10%
    636,856.00
    SUMMARY
    Total
    INR 2,023,625.00
    INR 202,362.50
    INR 2,225,987.50
    """)

    assert invoice.invoice_number == "51109305"
    assert invoice.invoice_date == "09/03/2024"
    assert invoice.supplier_name == "TechVision Distributors Pvt Ltd"
    assert invoice.customer_name == "Hyderabad IT Traders"
    assert invoice.subtotal == 2_023_625.00
    assert invoice.tax == 202_362.50
    assert invoice.total == 2_225_987.50
    assert invoice.currency == "INR"
    assert [item.model_dump() for item in invoice.line_items] == [
        {"description": "Belkin MagSafe 3-in-1 Wireless Charger", "quantity": 9.0, "unit": "pcs", "unit_price": 8175.0, "tax": 10.0, "total": 73575.0},
        {"description": "Samsung Galaxy S24 256GB Phantom Black", "quantity": 8.0, "unit": "pcs", "unit_price": 72370.0, "tax": 10.0, "total": 578960.0},
    ]
