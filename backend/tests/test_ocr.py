# backend/tests/test_ocr.py
import pytest
from unittest.mock import patch, MagicMock
from utils.pdf import extract_text_from_pdf, extract_text_from_image


class TestExtractTextFromPdf:
    def test_returns_pdf_source_when_text_layer_present(self, tmp_path):
        """PyMuPDF finds text → returns (text, 'pdf') without calling OCR."""
        pdf_path = str(tmp_path / "test.pdf")
        long_text = "Patient: Jane Smith\nBP 120/80\n" * 4  # well over 50 chars
        with patch("utils.pdf.fitz.open") as mock_open, \
             patch("utils.pdf._ocr_pdf") as mock_ocr:
            mock_doc = MagicMock()
            mock_page = MagicMock()
            mock_page.get_text.return_value = long_text
            mock_doc.__iter__ = lambda s: iter([mock_page])
            mock_doc.__enter__ = MagicMock(return_value=mock_doc)
            mock_doc.__exit__ = MagicMock(return_value=None)
            mock_open.return_value = mock_doc
            text, source = extract_text_from_pdf(pdf_path)
        assert source == "pdf"
        assert "Jane Smith" in text
        mock_ocr.assert_not_called()

    def test_returns_ocr_source_when_no_text_layer(self, tmp_path):
        """PyMuPDF finds < 50 chars → falls back to OCR, returns ('text', 'ocr')."""
        pdf_path = str(tmp_path / "scan.pdf")
        ocr_text = "Patient: Jane Smith\nBP 120/80\n" * 4
        with patch("utils.pdf.fitz.open") as mock_open, \
             patch("utils.pdf._ocr_pdf") as mock_ocr:
            mock_doc = MagicMock()
            mock_page = MagicMock()
            mock_page.get_text.return_value = "   "
            mock_doc.__iter__ = lambda s: iter([mock_page])
            mock_doc.__enter__ = MagicMock(return_value=mock_doc)
            mock_doc.__exit__ = MagicMock(return_value=None)
            mock_open.return_value = mock_doc
            mock_ocr.return_value = ocr_text
            text, source = extract_text_from_pdf(pdf_path)
        assert source == "ocr"
        assert "Jane Smith" in text

    def test_raises_if_ocr_produces_no_text(self, tmp_path):
        pdf_path = str(tmp_path / "blank.pdf")
        with patch("utils.pdf.fitz.open") as mock_open, \
             patch("utils.pdf._ocr_pdf") as mock_ocr:
            mock_doc = MagicMock()
            mock_page = MagicMock()
            mock_page.get_text.return_value = ""
            mock_doc.__iter__ = lambda s: iter([mock_page])
            mock_doc.__enter__ = MagicMock(return_value=mock_doc)
            mock_doc.__exit__ = MagicMock(return_value=None)
            mock_open.return_value = mock_doc
            mock_ocr.return_value = "   "
            with pytest.raises(ValueError, match="no readable text"):
                extract_text_from_pdf(pdf_path)


class TestExtractTextFromImage:
    def test_returns_ocr_text_for_valid_image(self, tmp_path):
        img_path = str(tmp_path / "note.png")
        ocr_text = "BP 120/80\nHR 76\n" * 4
        with patch("utils.pdf.Image") as mock_Image, \
             patch("utils.pdf.pytesseract") as mock_tess:
            mock_img = MagicMock()
            mock_img.__enter__ = MagicMock(return_value=mock_img)
            mock_img.__exit__ = MagicMock(return_value=None)
            mock_Image.open.return_value = mock_img
            mock_tess.image_to_string.return_value = ocr_text
            text = extract_text_from_image(img_path)
        assert "BP" in text

    def test_raises_if_ocr_produces_no_text(self, tmp_path):
        img_path = str(tmp_path / "blank.png")
        with patch("utils.pdf.Image") as mock_Image, \
             patch("utils.pdf.pytesseract") as mock_tess:
            mock_img = MagicMock()
            mock_img.__enter__ = MagicMock(return_value=mock_img)
            mock_img.__exit__ = MagicMock(return_value=None)
            mock_Image.open.return_value = mock_img
            mock_tess.image_to_string.return_value = "  "
            with pytest.raises(ValueError, match="no readable text"):
                extract_text_from_image(img_path)
