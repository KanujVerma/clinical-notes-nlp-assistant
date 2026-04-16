# backend/utils/pdf.py
import fitz  # PyMuPDF
import pytesseract
from pytesseract import Output
from PIL import Image, ImageFilter, ImageOps
from pdf2image import convert_from_path

_MIN_TEXT_LEN = 50
_TESS_CONFIG = "--psm 6 --oem 1 -l eng"  # Clinical notes are assumed to be in English


def _preprocess_image(img: Image.Image) -> Image.Image:
    """Apply preprocessing to improve OCR accuracy.

    Steps:
    1. Grayscale conversion
    2. Contrast enhancement + binarization
    3. Deskew (via pytesseract.image_to_osd; skipped gracefully on TesseractError)
    4. Noise removal via median filter
    """
    # 1. Grayscale
    out = img.convert("L")

    # 2. Autocontrast then binarize at threshold 128
    out = ImageOps.autocontrast(out)
    out = out.point(lambda p: 255 if p >= 128 else 0)

    # 3. Deskew
    try:
        osd = pytesseract.image_to_osd(out, config="--psm 0 -c min_characters_to_try=5")
        for line in osd.splitlines():
            if "Rotate:" in line:
                angle = int(line.split(":")[-1].strip())
                if angle != 0:
                    out = out.rotate(-angle, expand=True)
                break
    except pytesseract.TesseractError:
        pass  # skip deskew gracefully

    # 4. Noise removal
    out = out.filter(ImageFilter.MedianFilter(size=3))

    return out


def _ocr_image_with_confidence(img: Image.Image) -> tuple[str, float]:
    """Run Tesseract on a single image, returning (text, confidence 0.0–1.0)."""
    preprocessed = _preprocess_image(img)
    data = pytesseract.image_to_data(
        preprocessed,
        config=_TESS_CONFIG,
        output_type=Output.DICT,
    )
    confs = [c for c in data["conf"] if c != -1]
    confidence = (sum(confs) / len(confs) / 100.0) if confs else 0.0
    text = " ".join(
        word for word, conf in zip(data["text"], data["conf"])
        if conf != -1 and word.strip()
    )
    return text, confidence


def _ocr_pdf(filepath: str) -> tuple[str, float]:
    """Convert each PDF page to an image and run Tesseract OCR on it.

    Returns:
        (text, ocr_confidence) where ocr_confidence is the mean per-page
        confidence (each page's confidence is itself a mean of its word-level
        confidences), expressed as a float 0.0–1.0.
    """
    images = convert_from_path(filepath)
    page_texts: list[str] = []
    page_confs: list[float] = []
    for img in images:
        text, conf = _ocr_image_with_confidence(img)
        page_texts.append(text)
        page_confs.append(conf)
    combined_text = "\n\n".join(page_texts)
    avg_confidence = (sum(page_confs) / len(page_confs)) if page_confs else 0.0
    return combined_text, avg_confidence


def extract_text_from_pdf(filepath: str) -> tuple[str, str, float | None]:
    """Extract text from a PDF file.

    Returns:
        (text, source, ocr_confidence) where:
        - source is 'pdf' when a text layer was found (ocr_confidence is None)
        - source is 'ocr' when Tesseract was used as a fallback
          (ocr_confidence is a float 0.0–1.0)

    Raises:
        ValueError: if both PyMuPDF and OCR produce fewer than 50 characters.
        pytesseract.TesseractNotFoundError: if tesseract binary is not installed.
    """
    with fitz.open(filepath) as doc:
        text = "\n".join(page.get_text() for page in doc)
    if len(text.strip()) >= _MIN_TEXT_LEN:
        return text, "pdf", None
    # Fall back to Tesseract OCR
    ocr_text, ocr_confidence = _ocr_pdf(filepath)
    if len(ocr_text.strip()) < _MIN_TEXT_LEN:
        raise ValueError("OCR produced no readable text.")
    return ocr_text, "ocr", ocr_confidence


def extract_text_from_image(filepath: str) -> tuple[str, float]:
    """Run Tesseract OCR on a PNG/JPG/TIFF image file.

    Returns:
        (text, ocr_confidence) where ocr_confidence is a float 0.0–1.0.

    Raises:
        ValueError: if Tesseract output is under 50 characters after stripping.
        pytesseract.TesseractNotFoundError: if tesseract binary is not installed.
    """
    with Image.open(filepath) as img:
        text, confidence = _ocr_image_with_confidence(img)
    if len(text.strip()) < _MIN_TEXT_LEN:
        raise ValueError("OCR produced no readable text.")
    return text, confidence
