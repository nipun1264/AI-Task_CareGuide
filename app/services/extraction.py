import re
from pathlib import Path
from ..schemas import InvoiceExtraction


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
        return pytesseract.image_to_string(Image.open(file))
    if suffix in {".xlsx", ".xls"}:
        import pandas as pd
        book = pd.read_excel(file, sheet_name=None)
        return "\n\n".join(f"[{name}]\n{frame.to_csv(index=False)}" for name, frame in book.items())
    if suffix == ".csv":
        return file.read_text(encoding="utf-8", errors="replace")
    raise ValueError(f"Unsupported file type: {suffix}")


def _amount(text: str, labels: list[str]) -> float | None:
    labels_pattern = "|".join(re.escape(label) for label in labels)
    hit = re.search(rf"\b(?:{labels_pattern})\b\s*[:#]?\s*(?:USD|EUR|GBP|BDT|\$|€|£)?\s*([\d,]+(?:\.\d{{1,2}})?)", text, re.I)
    return float(hit.group(1).replace(",", "")) if hit else None


def rule_based_extract(text: str) -> InvoiceExtraction:
    number = re.search(r"(?:invoice\s*(?:no\.?|number|#)?|inv\s*#)\s*[:#-]?\s*([A-Z0-9][A-Z0-9-]+)", text, re.I)
    date = re.search(r"(?:invoice\s*date|date)\s*[:#]?\s*(\d{1,4}[/-]\d{1,2}[/-]\d{1,4})", text, re.I)
    currency = re.search(r"\b(USD|EUR|GBP|BDT)\b|([$€£])", text)
    currency_value = currency.group(1) or currency.group(2) if currency else None
    return InvoiceExtraction(
        invoice_number=number.group(1) if number else None,
        invoice_date=date.group(1) if date else None,
        subtotal=_amount(text, ["subtotal", "sub total"]),
        tax=_amount(text, ["tax", "vat", "gst"]),
        total=_amount(text, ["grand total", "total due", "total"]),
        currency=currency_value,
        confidence=0.35,
    )


def extract_invoice(text: str) -> InvoiceExtraction:
    # Kept deterministic by default. Add a provider here only after an API key is configured.
    return rule_based_extract(text)
