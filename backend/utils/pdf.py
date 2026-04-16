import fitz  # PyMuPDF

_MIN_TEXT_LEN = 50


def extract_text_from_pdf(filepath: str) -> str:
    doc = fitz.open(filepath)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    if len(text.strip()) < _MIN_TEXT_LEN:
        raise ValueError("PDF appears to be image-only (no embedded text layer). OCR is not supported.")
    return text
