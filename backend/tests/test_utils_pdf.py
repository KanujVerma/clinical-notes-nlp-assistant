# backend/tests/test_utils_pdf.py
import pytest
from unittest.mock import patch, MagicMock, call
from PIL import Image
from pytesseract import Output

from utils.pdf import (
    _preprocess_image,
    _ocr_image_with_confidence,
    _ocr_pdf,
    extract_text_from_pdf,
    extract_text_from_image,
)


# ---------------------------------------------------------------------------
# _preprocess_image
# ---------------------------------------------------------------------------

class TestPreprocessImage:
    def _make_grey_image(self):
        img = Image.new("RGB", (100, 50), color=(200, 200, 200))
        return img

    def test_returns_pil_image(self):
        img = self._make_grey_image()
        result = _preprocess_image(img)
        assert isinstance(result, Image.Image)

    def test_output_is_grayscale(self):
        img = self._make_grey_image()
        result = _preprocess_image(img)
        assert result.mode == "L"

    def test_deskew_skips_gracefully_on_tesseract_error(self):
        """If image_to_osd raises TesseractError, preprocessing still completes."""
        import pytesseract
        img = self._make_grey_image()
        with patch("utils.pdf.pytesseract.image_to_osd",
                   side_effect=pytesseract.TesseractError(1, "OSD failed")):
            result = _preprocess_image(img)
        assert isinstance(result, Image.Image)

    def test_deskew_rotates_by_osd_angle(self):
        """When OSD reports a rotation, the image should be rotated."""
        img = self._make_grey_image()
        osd_output = "Orientation in degrees: 0\nRotate: 90\nOrientation confidence: 5.00"
        rotated_img = Image.new("L", (50, 100))  # rotated dimensions
        with patch("utils.pdf.pytesseract.image_to_osd", return_value=osd_output):
            with patch.object(Image.Image, "rotate", return_value=rotated_img) as mock_rotate:
                result = _preprocess_image(img)
        # rotate should have been called with -90
        mock_rotate.assert_called_once_with(-90, expand=True)
        assert result is not None

    def test_deskew_skips_rotate_when_angle_is_zero(self):
        """No rotation when OSD reports 0 degrees."""
        img = self._make_grey_image()
        osd_output = "Orientation in degrees: 0\nRotate: 0\nOrientation confidence: 5.00"
        with patch("utils.pdf.pytesseract.image_to_osd", return_value=osd_output):
            with patch.object(Image.Image, "rotate") as mock_rotate:
                _preprocess_image(img)
        mock_rotate.assert_not_called()


# ---------------------------------------------------------------------------
# _ocr_image_with_confidence
# ---------------------------------------------------------------------------

class TestOcrImageWithConfidence:
    def _fake_data(self, texts, confs):
        return {"text": texts, "conf": confs}

    def test_returns_text_and_confidence_tuple(self):
        img = MagicMock(spec=Image.Image)
        fake_data = self._fake_data(["Hello", "world"], [80, 90])
        with patch("utils.pdf._preprocess_image", return_value=img), \
             patch("utils.pdf.pytesseract.image_to_data", return_value=fake_data):
            text, conf = _ocr_image_with_confidence(img)
        assert "Hello" in text
        assert "world" in text
        assert abs(conf - 0.85) < 1e-9  # (80+90)/2 / 100

    def test_excludes_minus_one_confidences(self):
        """Words with conf == -1 (separators) are excluded from average and text."""
        img = MagicMock(spec=Image.Image)
        fake_data = self._fake_data(["Hello", "", "world"], [80, -1, 60])
        with patch("utils.pdf._preprocess_image", return_value=img), \
             patch("utils.pdf.pytesseract.image_to_data", return_value=fake_data):
            text, conf = _ocr_image_with_confidence(img)
        assert "" not in text.split()
        assert abs(conf - 0.70) < 1e-9  # (80+60)/2 / 100

    def test_confidence_is_zero_when_no_valid_words(self):
        img = MagicMock(spec=Image.Image)
        fake_data = self._fake_data([], [])
        with patch("utils.pdf._preprocess_image", return_value=img), \
             patch("utils.pdf.pytesseract.image_to_data", return_value=fake_data):
            text, conf = _ocr_image_with_confidence(img)
        assert conf == 0.0
        assert text == ""

    def test_passes_tess_config_to_image_to_data(self):
        img = MagicMock(spec=Image.Image)
        fake_data = self._fake_data(["Test"], [75])
        with patch("utils.pdf._preprocess_image", return_value=img), \
             patch("utils.pdf.pytesseract.image_to_data", return_value=fake_data) as mock_itd:
            _ocr_image_with_confidence(img)
        _, kwargs = mock_itd.call_args
        assert kwargs.get("config") == "--psm 6 --oem 1 -l eng"
        assert kwargs.get("output_type") == Output.DICT


# ---------------------------------------------------------------------------
# _ocr_pdf
# ---------------------------------------------------------------------------

class TestOcrPdf:
    def test_returns_text_and_float_confidence(self, tmp_path):
        pdf_path = str(tmp_path / "test.pdf")
        mock_img = MagicMock()
        with patch("utils.pdf.convert_from_path", return_value=[mock_img, mock_img]), \
             patch("utils.pdf._ocr_image_with_confidence",
                   side_effect=[("Page one text", 0.80), ("Page two text", 0.60)]):
            text, conf = _ocr_pdf(pdf_path)
        assert "Page one text" in text
        assert "Page two text" in text
        assert abs(conf - 0.70) < 1e-9  # mean of 0.80 and 0.60

    def test_pages_joined_with_double_newline(self, tmp_path):
        pdf_path = str(tmp_path / "test.pdf")
        mock_img = MagicMock()
        with patch("utils.pdf.convert_from_path", return_value=[mock_img, mock_img]), \
             patch("utils.pdf._ocr_image_with_confidence",
                   side_effect=[("First page", 0.90), ("Second page", 0.90)]):
            text, _ = _ocr_pdf(pdf_path)
        assert text == "First page\n\nSecond page"

    def test_empty_pdf_returns_zero_confidence(self, tmp_path):
        pdf_path = str(tmp_path / "empty.pdf")
        with patch("utils.pdf.convert_from_path", return_value=[]):
            text, conf = _ocr_pdf(pdf_path)
        assert text == ""
        assert conf == 0.0


# ---------------------------------------------------------------------------
# extract_text_from_pdf
# ---------------------------------------------------------------------------

class TestExtractTextFromPdf:
    def test_returns_pdf_source_none_confidence_when_text_layer(self, tmp_path):
        """PyMuPDF finds text → returns (text, 'pdf', None)."""
        pdf_path = str(tmp_path / "test.pdf")
        long_text = "Patient: Jane Smith\nBP 120/80\n" * 4
        with patch("utils.pdf.fitz.open") as mock_open, \
             patch("utils.pdf._ocr_pdf") as mock_ocr:
            mock_doc = MagicMock()
            mock_page = MagicMock()
            mock_page.get_text.return_value = long_text
            mock_doc.__iter__ = lambda s: iter([mock_page])
            mock_doc.__enter__ = MagicMock(return_value=mock_doc)
            mock_doc.__exit__ = MagicMock(return_value=None)
            mock_open.return_value = mock_doc
            text, source, ocr_confidence = extract_text_from_pdf(pdf_path)
        assert source == "pdf"
        assert ocr_confidence is None
        assert "Jane Smith" in text
        mock_ocr.assert_not_called()

    def test_returns_ocr_source_with_confidence_when_no_text_layer(self, tmp_path):
        """PyMuPDF finds < 50 chars → falls back to OCR, returns ('text', 'ocr', float)."""
        pdf_path = str(tmp_path / "scan.pdf")
        ocr_text = "Patient: Jane Smith\nBP 120/80\n" * 4
        with patch("utils.pdf.fitz.open") as mock_open, \
             patch("utils.pdf._ocr_pdf", return_value=(ocr_text, 0.88)) as mock_ocr:
            mock_doc = MagicMock()
            mock_page = MagicMock()
            mock_page.get_text.return_value = "   "
            mock_doc.__iter__ = lambda s: iter([mock_page])
            mock_doc.__enter__ = MagicMock(return_value=mock_doc)
            mock_doc.__exit__ = MagicMock(return_value=None)
            mock_open.return_value = mock_doc
            text, source, ocr_confidence = extract_text_from_pdf(pdf_path)
        assert source == "ocr"
        assert abs(ocr_confidence - 0.88) < 1e-9
        assert "Jane Smith" in text

    def test_raises_value_error_when_ocr_produces_no_text(self, tmp_path):
        pdf_path = str(tmp_path / "blank.pdf")
        with patch("utils.pdf.fitz.open") as mock_open, \
             patch("utils.pdf._ocr_pdf", return_value=("   ", 0.0)):
            mock_doc = MagicMock()
            mock_page = MagicMock()
            mock_page.get_text.return_value = ""
            mock_doc.__iter__ = lambda s: iter([mock_page])
            mock_doc.__enter__ = MagicMock(return_value=mock_doc)
            mock_doc.__exit__ = MagicMock(return_value=None)
            mock_open.return_value = mock_doc
            with pytest.raises(ValueError, match="no readable text"):
                extract_text_from_pdf(pdf_path)


# ---------------------------------------------------------------------------
# extract_text_from_image
# ---------------------------------------------------------------------------

class TestExtractTextFromImage:
    def test_returns_text_and_confidence_tuple(self, tmp_path):
        img_path = str(tmp_path / "note.png")
        ocr_text = "BP 120/80\nHR 76\n" * 4
        with patch("utils.pdf.Image") as mock_Image, \
             patch("utils.pdf._ocr_image_with_confidence",
                   return_value=(ocr_text, 0.92)):
            mock_img = MagicMock()
            mock_img.__enter__ = MagicMock(return_value=mock_img)
            mock_img.__exit__ = MagicMock(return_value=None)
            mock_Image.open.return_value = mock_img
            text, conf = extract_text_from_image(img_path)
        assert "BP" in text
        assert abs(conf - 0.92) < 1e-9

    def test_raises_if_ocr_produces_no_text(self, tmp_path):
        img_path = str(tmp_path / "blank.png")
        with patch("utils.pdf.Image") as mock_Image, \
             patch("utils.pdf._ocr_image_with_confidence",
                   return_value=("  ", 0.0)):
            mock_img = MagicMock()
            mock_img.__enter__ = MagicMock(return_value=mock_img)
            mock_img.__exit__ = MagicMock(return_value=None)
            mock_Image.open.return_value = mock_img
            with pytest.raises(ValueError, match="no readable text"):
                extract_text_from_image(img_path)

    def test_confidence_is_float_between_zero_and_one(self, tmp_path):
        img_path = str(tmp_path / "note.png")
        ocr_text = "Patient: John Doe\nBP 130/85\n" * 4
        with patch("utils.pdf.Image") as mock_Image, \
             patch("utils.pdf._ocr_image_with_confidence",
                   return_value=(ocr_text, 0.75)):
            mock_img = MagicMock()
            mock_img.__enter__ = MagicMock(return_value=mock_img)
            mock_img.__exit__ = MagicMock(return_value=None)
            mock_Image.open.return_value = mock_img
            _, conf = extract_text_from_image(img_path)
        assert 0.0 <= conf <= 1.0
