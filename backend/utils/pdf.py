# backend/utils/pdf.py
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from pdf2image import convert_from_path

_MIN_TEXT_LEN = 50


def _ocr_pdf(filepath: str) -> str:
    """Convert each PDF page to an image and run Tesseract OCR on it."""
    images = convert_from_path(filepath)
    pages = [pytesseract.image_to_string(img) for img in images]
    return "\n\n".join(pages)


def extract_text_from_pdf(filepath: str) -> tuple[str, str]:
    """Extract text from a PDF file.

    Returns:
        (text, source) where source is 'pdf' when a text layer was found,
        or 'ocr' when Tesseract was used as a fallback.

    Raises:
        ValueError: if both PyMuPDF and OCR produce fewer than 50 characters.
        pytesseract.TesseractNotFoundError: if tesseract binary is not installed.
    """
    with fitz.open(filepath) as doc:
        text = "\n".join(page.get_text() for page in doc)
    if len(text.strip()) >= _MIN_TEXT_LEN:
        return text, "pdf"
    # Fall back to Tesseract OCR
    ocr_text = _ocr_pdf(filepath)
    if len(ocr_text.strip()) < _MIN_TEXT_LEN:
        raise ValueError("OCR produced no readable text.")
    return ocr_text, "ocr"


def extract_text_from_image(filepath: str) -> str:
    """Run Tesseract OCR on a PNG/JPG/TIFF image file.

    Raises:
        ValueError: if Tesseract output is under 50 characters after stripping.
        pytesseract.TesseractNotFoundError: if tesseract binary is not installed.
    """
    with Image.open(filepath) as img:
        text = pytesseract.image_to_string(img)
    if len(text.strip()) < _MIN_TEXT_LEN:
        raise ValueError("OCR produced no readable text.")
    return text
