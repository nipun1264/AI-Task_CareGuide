import re
import csv
from calendar import month_name
from datetime import datetime
from math import isclose
from pathlib import Path
from ..schemas import InvoiceExtraction, LineItem


def extract_text(path: str) -> str:
    file = Path(path)
    suffix = file.suffix.lower()
    if suffix == ".pdf":
        import fitz
        from PIL import Image
        import pytesseract
        with fitz.open(file) as pdf:
            chunks = []
            for page in pdf:
                text = page.get_text("text").strip()
                if not text:
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    text = pytesseract.image_to_string(image)
                chunks.append(text)
            return "\n".join(chunks)
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        from PIL import Image
        import pytesseract
        image = Image.open(file).convert("RGB")
        enlarged = image.resize((image.width * 2, image.height * 2))
        candidates = [
            pytesseract.image_to_string(image, config="--psm 3"),
            pytesseract.image_to_string(enlarged, config="--psm 6"),
        ]
        # Documents can be table-like or paragraph-like. Select the OCR
        # layout that preserves the most invoice-specific labels.
        primary = max(candidates, key=lambda value: sum(value.lower().count(label) for label in ("invoice", "subtotal", "tax", "total", "bill")))
        # Sparse mode can recover isolated header text that table OCR misses.
        sparse = pytesseract.image_to_string(enlarged, config="--psm 11")
        return f"{primary}\n\n{sparse}"
    if suffix in {".xlsx", ".xls"}:
        import pandas as pd
        # First inspect the unheaded grid.  Many accounting exports are a
        # formatted invoice template rather than a normal data table, and the
        # labels and values live in separate columns.
        raw_book = pd.read_excel(file, sheet_name=None, header=None, dtype=str, keep_default_na=False)
        layout_sections = [_csv_layout_text(frame.values.tolist()) for frame in raw_book.values()]
        layout_text = "\n\n".join(section for section in layout_sections if section)
        if layout_text:
            return layout_text
        book = pd.read_excel(file, sheet_name=None, dtype=str, keep_default_na=False)
        return _tabular_text(book)
    if suffix == ".csv":
        with file.open(encoding="utf-8-sig", errors="replace", newline="") as source:
            rows = list(csv.reader(source))
        layout_text = _csv_layout_text(rows)
        if layout_text:
            return layout_text
        import pandas as pd
        frame = pd.read_csv(file, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        return _tabular_text({"CSV": frame})
    raise ValueError(f"Unsupported file type: {suffix}")


def _tabular_text(sheets: dict) -> str:
    """Preserve table data and add label:value records that invoice rules can read."""
    sections = []
    for name, frame in sheets.items():
        records = []
        for _, row in frame.iterrows():
            fields = [f"{column}: {value}" for column, value in row.items() if str(value).strip()]
            if fields:
                records.append("\n".join(fields))
        # The label:value representation retains every cell while avoiding a
        # header row such as "Subtotal,Tax,Total" being parsed as a value.
        sections.append(f"[{name}]\n" + "\n\n".join(records))
    return "\n\n".join(sections)


def _csv_layout_text(rows: list[list[str]]) -> str:
    """Normalize visually laid-out CSV invoice templates without losing cell positions."""
    cleaned = [[cell.strip() for cell in row] for row in rows]
    # Ordinary CSVs start with a dense header row and should follow the
    # existing header/value normalization path instead.
    if cleaned and sum(bool(cell) for cell in cleaned[0]) > 1:
        return ""
    lines: list[str] = []

    def right_value(row: list[str], index: int) -> str | None:
        return next((cell for cell in row[index + 1:] if cell), None)

    labels = {
        "invoice #": "Invoice No", "invoice no": "Invoice No", "invoice number": "Invoice No",
        "date": "Date", "credit date": "Date", "to": "Customer", "customer": "Customer",
        "customer id/name": "Customer", "seller": "Supplier", "supplier": "Supplier", "vendor": "Supplier",
        "subtotal": "Subtotal", "sales tax": "Sales Tax", "tax": "Tax", "total": "Total",
    }
    for row in cleaned:
        for index, cell in enumerate(row):
            output_label = labels.get(cell.lower().rstrip(":"))
            value = right_value(row, index) if output_label else None
            if output_label and value and value.lower() not in {"description", "amount", "unit price", "quantity"}:
                if output_label == "Date":
                    us_date = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", value)
                    if us_date and 1 <= int(us_date.group(1)) <= 12:
                        value = f"{us_date.group(2)} {month_name[int(us_date.group(1))]} {us_date.group(3)}"
                lines.append(f"{output_label}: {value}")

    for row_index, row in enumerate(cleaned):
        if any(cell.upper() == "INVOICE" for cell in row):
            following = next((cell for next_row in cleaned[row_index + 1:row_index + 5] for cell in next_row if cell and cell.upper() not in {"INVOICE", "TO"}), None)
            if following:
                lines.append(f"Supplier: {following}")
            break

    for row_index, row in enumerate(cleaned):
        headers = {cell.lower(): index for index, cell in enumerate(row) if cell}
        description_index = headers.get("description")
        quantity_index = headers.get("qty", headers.get("quantity"))
        price_index = headers.get("unit price")
        discount_index = headers.get("discount")
        amount_index = headers.get("line total", headers.get("amount"))
        if None in {description_index, quantity_index, price_index, amount_index}:
            continue
        for data_row in cleaned[row_index + 1:]:
            if max(description_index, quantity_index, price_index, amount_index) >= len(data_row):
                continue
            description, quantity, price, amount = (data_row[index] for index in (description_index, quantity_index, price_index, amount_index))
            if not (description and quantity and price and amount):
                if any(cell.lower() in {"subtotal", "total"} for cell in data_row):
                    break
                continue
            if not re.fullmatch(r"\d+(?:\.\d+)?", quantity):
                continue
            discount = data_row[discount_index] if discount_index is not None and discount_index < len(data_row) else ""
            discount_text = f"\nDiscount: {discount}" if discount else ""
            lines.append(f"Line Item\nDescription: {description}\nQuantity: {quantity}\nUnit Price: {price}{discount_text}\nAmount: {amount}")
        break
    return "\n".join(lines)


def _parse_amount(value: str) -> float:
    """Parse both 1,234.56 and comma-decimal values such as 1,23."""
    value = value.strip()
    if "." not in value and "," in value:
        whole, decimal = value.rsplit(",", 1)
        value = f"{whole.replace(',', '')}.{decimal}"
    else:
        value = value.replace(",", "")
    return float(value)


def _amount(text: str, labels: list[str]) -> float | None:
    labels_pattern = "|".join(re.escape(label) for label in labels)
    # Keep whitespace on the same line.  Otherwise a heading such as
    # "INVOICE" or "TOTAL" can accidentally consume text on the next line.
    # A tax label can be followed by a rate (for example 5.0%) before its
    # monetary amount, so skip that rate when present.
    hit = re.search(
        rf"\b(?:{labels_pattern})\b[ \t]*[:#|]?[ \t|]*(?:(?:\(?\d+(?:\.\d+)?%\)?|[A-Za-z]+\))[ \t|]*)?(?:USD|EUR|GBP|BDT|\$|€|£)?[ \t|]*([\d,]+(?:\.\d{{1,2}})?)",
        text,
        re.I,
    )
    return _parse_amount(hit.group(1)) if hit else None


def _amount_before_label(text: str, labels: list[str]) -> float | None:
    """Read receipt layouts where the value is printed before its label."""
    labels_pattern = "|".join(re.escape(label) for label in labels)
    hit = re.search(
        rf"([\d,]+(?:\.\d{{1,2}})?)[ \t]*(?:\(\+\)|\(-\))?[ \t]*(?:{labels_pattern})\b",
        text,
        re.I,
    )
    return _parse_amount(hit.group(1)) if hit else None


def _receipt_amount_after_label(text: str, label: str) -> float | None:
    hit = re.search(rf"{re.escape(label)}[ \t:]*\n[ \t]*(-?[\d,]+(?:\.\d{{1,2}})?)", text, re.I)
    return _parse_amount(hit.group(1)) if hit else None


def _receipt_amount_before_label(text: str, label: str) -> float | None:
    hit = re.search(rf"([\d,]+(?:\.\d{{1,2}})?)\s*(?:\(\+\)|\(-\))?\s*{re.escape(label)}\b", text, re.I)
    return _parse_amount(hit.group(1)) if hit else None


def _adjustment(text: str) -> float | None:
    """Return a signed adjustment: discounts/refunds/credits reduce the total."""
    # The layout normalizer emits per-item discounts as ``Discount:`` lines.
    # They affect the line total, not the invoice summary, so exclude them
    # when looking for a document-level adjustment.
    summary_text = "\n".join(
        line for line in text.splitlines()
        if not re.match(r"^\s*discount\s*:", line, re.I)
    )
    for label in ("less discount", "discount", "refund", "credit note", "credit", "rebate", "return", "exchange"):
        value = _amount(summary_text, [label]) or _receipt_amount_after_label(summary_text, label) or _receipt_amount_before_label(summary_text, label)
        if value is not None:
            return -abs(value)
    for label in ("service charge", "surcharge", "additional fee", "adjustment"):
        value = _amount(summary_text, [label]) or _receipt_amount_after_label(summary_text, label) or _receipt_amount_before_label(summary_text, label)
        if value is not None:
            return abs(value)
    return None


def _supplier_name(text: str) -> str | None:
    labeled = _party_name(text, ("seller", "supplier", "vendor"))
    if labeled:
        return labeled
    receipt_header = re.search(r"^\s*--\s*([A-Za-z][A-Za-z &'\-]+?)\s*--", text, re.M)
    return receipt_header.group(1).strip().title() if receipt_header else _header_supplier(text) or _first_supplier_line(text)


def _first_supplier_line(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines()]
    bill_index = next((i for i, line in enumerate(lines) if re.search(r"\b(?:bill(?:ed)?|illed)\s*to\b", line, re.I)), None)
    if bill_index is None:
        return None
    start = bill_index - 1
    while start >= 0 and lines[start]:
        start -= 1
    block = [line for line in lines[start + 1:bill_index] if line]
    if not block:
        return None
    # The first line in the sender address block is the supplier name.
    return block[0].rstrip(":").strip() or None


def _bill_to_name(text: str) -> str | None:
    labeled = _party_name(text, ("client", "customer"))
    if labeled:
        return labeled
    lines = [line.strip() for line in text.splitlines()]
    bill_index = next((i for i, line in enumerate(lines) if re.search(r"\b(?:bill(?:ed)?|illed)\s*to\b", line, re.I)), None)
    if bill_index is None:
        return None
    candidate = next((line for line in lines[bill_index + 1:] if line), "")
    # On two-column invoices OCR emits the Bill To and Ship To names on one
    # line.  Keep the left (Bill To) name when both columns are identical.
    candidate = re.split(
        r"\binvoice\s*date\b|\bpo\.?\b|\s+\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+\d{4}",
        candidate,
        maxsplit=1,
        flags=re.I,
    )[0].strip()
    candidate = re.sub(r"^.*?purchase!\s*", "", candidate, flags=re.I)
    repeated = re.match(r"^(.+?)\s+\1(?:\s|$)", candidate, re.I)
    return (repeated.group(1) if repeated else candidate).strip() or None


def _party_name(text: str, labels: tuple[str, ...]) -> str | None:
    """Return the first name following a simple party label such as Seller or Client."""
    labels_pattern = "|".join(re.escape(label) for label in labels)
    hit = re.search(rf"\b(?:{labels_pattern})\b[ \t]*:[ \t]*(?:\n[ \t]*)?([^\n]+)", text, re.I)
    return hit.group(1).strip() if hit else None


def _header_supplier(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines()]
    date_pattern = r"\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}"
    candidates = []
    for index, line in enumerate(lines):
        if not re.search(r"\b(?:invoice|no[.,]?)\b", line, re.I):
            continue
        date_end = re.search(rf"{date_pattern}\s*(.*)$", line, re.I)
        if not date_end:
            continue
        parts = [date_end.group(1).strip()] if date_end.group(1).strip() else []
        for following in lines[index + 1:]:
            if following.upper().startswith("INVOICE"):
                break
            if following:
                parts.append(following)
        candidate = " ".join(parts).strip()
        if candidate:
            candidates.append(candidate)
    return max(candidates, key=lambda value: len(value.split())) if candidates else None


def _normalize_date(value: str) -> str | None:
    value = re.sub(r"(\d{1,2})(?:st|nd|rd|th)\b", r"\1", value.strip(), flags=re.I)
    formats = (
        "%d %B %Y", "%d %b %Y",
        "%Y/%m/%d", "%Y-%m-%d",
        "%d/%m/%Y", "%d-%m-%Y",
    )
    for date_format in formats:
        try:
            return datetime.strptime(value, date_format).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return None


def _invoice_date(text: str) -> str | None:
    date_value = r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+\d{4}|\d{1,4}[/-]\d{1,2}[/-]\d{1,4})"
    labeled = re.search(rf"(?:invoice[ \t]*date|date(?:[ \t]+of[ \t]+issue)?)[ \t]*[:#]?[ \t]*{date_value}", text, re.I)
    if labeled:
        return _normalize_date(labeled.group(1))
    # Some clean invoice layouts place the date directly under "Invoice No."
    near_number = re.search(rf"invoice[ \t]*(?:no\.?|number|#)[^\n]*\n[ \t]*{date_value}", text, re.I)
    if near_number:
        return _normalize_date(near_number.group(1))
    first_date = re.search(date_value, text, re.I)
    return _normalize_date(first_date.group(1)) if first_date else None


def _indian_tax_summary(text: str) -> tuple[float | None, float | None, float | None]:
    """Read Net Worth/VAT/Gross Worth totals that are printed below an INR table."""
    amount = r"([\d,]+(?:\.\d{1,2})?)"
    hit = re.search(
        rf"\bTotal\b\s*(?:INR|₹)\s*{amount}\s*(?:INR|₹)\s*{amount}\s*(?:INR|₹)\s*{amount}",
        text,
        re.I,
    )
    if not hit:
        return None, None, None
    return tuple(_parse_amount(hit.group(index)) for index in (1, 2, 3))


def _table_line_items(text: str) -> list[LineItem]:
    """Parse the one-value-per-line text emitted from common PDF invoice tables."""
    items_section = re.search(r"\bITEMS\b.*?(?=\bSUMMARY\b|\Z)", text, re.I | re.S)
    if not items_section:
        return []
    amount = r"([\d,]+(?:\.\d{1,2})?)"
    row = re.compile(
        rf"^\s*\d+\.\s*\n(.+?)\n\s*(\d+(?:\.\d+)?)\s*\n\s*([^\n]+)\n\s*{amount}\s*\n\s*{amount}\s*\n\s*(\d+(?:\.\d+)?)%\s*\n\s*{amount}",
        re.M | re.S,
    )
    result = []
    for match in row.finditer(items_section.group(0)):
        description = re.sub(r"\s*\n\s*", " ", match.group(1)).strip()
        result.append(LineItem(
            description=description,
            quantity=float(match.group(2)),
            unit=match.group(3).strip(),
            unit_price=_parse_amount(match.group(4)),
            tax=float(match.group(6)),
            # Net Worth, not Gross Worth: this preserves quantity x unit-price validation.
            total=_parse_amount(match.group(5)),
        ))
    return result


def _labelled_line_items(text: str) -> list[LineItem]:
    pattern = re.compile(
        r"Line Item\s*\nDescription:\s*([^\n]+)\s*\nQuantity:\s*(\d+(?:\.\d+)?)\s*\nUnit Price:\s*[^\d\n]*([\d,]+(?:\.\d{1,2})?)(?:\s*\nDiscount:\s*[^\d\n]*([\d,]+(?:\.\d{1,2})?))?\s*\nAmount:\s*[^\d\n]*([\d,]+(?:\.\d{1,2})?)",
        re.I,
    )
    return [LineItem(description=match.group(1).strip(), quantity=float(match.group(2)), unit_price=_parse_amount(match.group(3)), discount=_parse_amount(match.group(4)) if match.group(4) else None, total=_parse_amount(match.group(5))) for match in pattern.finditer(text)]


def _confidence(*, invoice_number: str | None, invoice_date: str | None, supplier_name: str | None,
                customer_name: str | None, subtotal: float | None, tax: float | None,
                adjustment: float | None, total: float | None, currency: str | None, line_items: list) -> float:
    """A transparent completeness and consistency score in the 0.0-1.0 range."""
    fields = (
        (invoice_number, 0.12), (invoice_date, 0.10), (supplier_name, 0.14),
        (customer_name, 0.14), (subtotal, 0.10), (tax, 0.10),
        (total, 0.15), (currency, 0.05), (line_items, 0.05),
    )
    score = sum(weight for value, weight in fields if value is not None and value != "" and (not isinstance(value, list) or bool(value)))
    if subtotal is not None and tax is not None and total is not None and isclose(subtotal + tax + (adjustment or 0.0), total, abs_tol=0.01):
        score += 0.05
    return round(min(score, 1.0), 2)


def rule_based_extract(text: str) -> InvoiceExtraction:
    number = re.search(r"(?:invoice[ \t]*(?:no\.?|number|#)|receipt[ \t]*(?:no\.?|number|#)|inv[ \t]*#|\bno\b[.,]?)[ \t]*[:#-]?[ \t]*([A-Z0-9][A-Z0-9-]+)", text, re.I)
    receipt_number = re.search(r"receipt[ \t]*(?:no\.?|number|#)[ \t]*:[ \t]*\n[ \t]*([A-Z0-9-]+)", text, re.I)
    currency = re.search(r"\b(USD|EUR|GBP|BDT|INR)\b|([$€£₹])", text, re.I)
    currency_value = (currency.group(1).upper() if currency and currency.group(1) else currency.group(2)) if currency else ("BDT" if re.search(r"\bTk\.?\b", text, re.I) else None)
    indian_subtotal, indian_tax, indian_total = _indian_tax_summary(text)
    subtotal = indian_subtotal if indian_subtotal is not None else (_amount(text, ["subtotal", "sub total"]) or _receipt_amount_after_label(text, "Sub Total"))
    detected_tax = _amount(text, ["sales tax", "tax", "vat", "gst"])
    tax = indian_tax if indian_tax is not None else (detected_tax if detected_tax is not None else (_amount_before_label(text, ["add vat", "vat"]) or _receipt_amount_before_label(text, "Add VAT")))
    adjustment = _adjustment(text)
    total = indian_total if indian_total is not None else (_amount_before_label(text, ["net payable"]) or _receipt_amount_before_label(text, "Net Payable") or _receipt_amount_after_label(text, "Net Payable") or _amount(text, ["grand total", "total due", "total"]))
    extracted = {
        "invoice_number": receipt_number.group(1) if receipt_number else (number.group(1) if number else None),
        "invoice_date": _invoice_date(text),
        "supplier_name": _supplier_name(text),
        "customer_name": _bill_to_name(text),
        "subtotal": subtotal,
        "tax": tax,
        "adjustment": adjustment,
        "total": total,
        "currency": currency_value,
        "line_items": _table_line_items(text) or _labelled_line_items(text),
    }
    return InvoiceExtraction(
        **extracted,
        confidence=_confidence(**extracted),
    )


def extract_invoice(text: str) -> InvoiceExtraction:
    # Kept deterministic by default. Add a provider here only after an API key is configured.
    return rule_based_extract(text)
