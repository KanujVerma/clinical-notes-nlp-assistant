import sys, os, io, pytest
import pytesseract
from unittest.mock import patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import create_app

@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE_URL": "sqlite:///" + str(tmp_path / "test.db")})
    with app.test_client() as c:
        yield c

def test_upload_txt_returns_note_id(client):
    content = b"BP: 120/80. HR: 72. Patient takes lisinopril 10 mg PO daily."
    data = {"file": (io.BytesIO(content), "note.txt", "text/plain")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 201
    assert "note_id" in resp.get_json()

def test_upload_returns_extracted_json(client):
    content = b"BP: 130/85. HR: 68."
    data = {"file": (io.BytesIO(content), "note.txt", "text/plain")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data")
    body = resp.get_json()
    assert "extracted_json" in body
    assert "vitals" in body["extracted_json"]

def test_upload_no_file_returns_400(client):
    resp = client.post("/api/upload", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400

def test_upload_unsupported_extension_returns_400(client):
    data = {"file": (io.BytesIO(b"hello"), "note.doc", "application/msword")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "UNSUPPORTED_FILE_TYPE"


class TestUploadOCR:
    def test_png_upload_returns_201(self, client):
        """PNG upload with mocked OCR returns 201 and note_id."""
        fake_text = "Patient: Test\nBP 120/80\n" * 4
        with patch("routes.upload.extract_text_from_image", return_value=(fake_text, 0.95)):
            resp = client.post(
                "/api/upload",
                data={"file": (io.BytesIO(b"fakepng"), "note.png")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 201
        assert "note_id" in resp.get_json()

    def test_jpg_upload_returns_201(self, client):
        fake_text = "Patient: Test\nBP 120/80\n" * 4
        with patch("routes.upload.extract_text_from_image", return_value=(fake_text, 0.95)):
            resp = client.post(
                "/api/upload",
                data={"file": (io.BytesIO(b"fakejpg"), "note.jpg")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 201

    def test_scanned_pdf_returns_201_with_ocr_source(self, client):
        """PDF with no text layer: extract_text_from_pdf returns ('text', 'ocr').
        The response must include source='ocr' so the frontend can display the badge."""
        fake_text = "Patient: Test\nBP 120/80\n" * 4
        with patch("routes.upload.extract_text_from_pdf", return_value=(fake_text, "ocr", 0.85)):
            resp = client.post(
                "/api/upload",
                data={"file": (io.BytesIO(b"%PDF"), "scan.pdf")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 201
        assert resp.get_json()["source"] == "ocr"

    def test_docx_returns_400_unsupported(self, client):
        resp = client.post(
            "/api/upload",
            data={"file": (io.BytesIO(b"data"), "note.docx")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "UNSUPPORTED_FILE_TYPE"

    def test_tesseract_not_found_returns_503(self, client):
        with patch("routes.upload.extract_text_from_image",
                   side_effect=pytesseract.TesseractNotFoundError()):
            resp = client.post(
                "/api/upload",
                data={"file": (io.BytesIO(b"fakepng"), "note.png")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 503
        assert resp.get_json()["code"] == "OCR_UNAVAILABLE"

    def test_ocr_empty_returns_400(self, client):
        with patch("routes.upload.extract_text_from_image",
                   side_effect=ValueError("OCR produced no readable text.")):
            resp = client.post(
                "/api/upload",
                data={"file": (io.BytesIO(b"fakepng"), "note.png")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "OCR_EMPTY"

    def test_pdf_tesseract_not_found_returns_503(self, client):
        """Scanned PDF where Tesseract binary is missing → 503 OCR_UNAVAILABLE."""
        with patch("routes.upload.extract_text_from_pdf",
                   side_effect=pytesseract.TesseractNotFoundError()):
            resp = client.post(
                "/api/upload",
                data={"file": (io.BytesIO(b"%PDF"), "scan.pdf")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 503
        assert resp.get_json()["code"] == "OCR_UNAVAILABLE"

    def test_pdf_ocr_empty_returns_400(self, client):
        """Scanned PDF where OCR finds no text → 400 OCR_EMPTY."""
        with patch("routes.upload.extract_text_from_pdf",
                   side_effect=ValueError("OCR produced no readable text.")):
            resp = client.post(
                "/api/upload",
                data={"file": (io.BytesIO(b"%PDF"), "scan.pdf")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "OCR_EMPTY"


class TestUploadResponseShape:
    """Response must include raw_text and ocr_confidence fields."""

    def test_txt_upload_response_includes_raw_text_and_null_confidence(self, client):
        content = b"BP: 120/80. HR: 72."
        data = {"file": (io.BytesIO(content), "note.txt", "text/plain")}
        resp = client.post("/api/upload", data=data, content_type="multipart/form-data")
        body = resp.get_json()
        assert resp.status_code == 201
        assert "raw_text" in body
        assert body["raw_text"] == "BP: 120/80. HR: 72."
        assert "ocr_confidence" in body
        assert body["ocr_confidence"] is None

    def test_image_upload_response_includes_ocr_confidence(self, client):
        fake_text = "Patient: Test\nBP 120/80\n" * 4
        with patch("routes.upload.extract_text_from_image", return_value=(fake_text, 0.92)):
            resp = client.post(
                "/api/upload",
                data={"file": (io.BytesIO(b"fakepng"), "note.png")},
                content_type="multipart/form-data",
            )
        body = resp.get_json()
        assert resp.status_code == 201
        assert body["ocr_confidence"] == 0.92
        assert body["raw_text"] == fake_text

    def test_scanned_pdf_response_includes_ocr_confidence(self, client):
        fake_text = "Patient: Test\nBP 120/80\n" * 4
        with patch("routes.upload.extract_text_from_pdf", return_value=(fake_text, "ocr", 0.85)):
            resp = client.post(
                "/api/upload",
                data={"file": (io.BytesIO(b"%PDF"), "scan.pdf")},
                content_type="multipart/form-data",
            )
        body = resp.get_json()
        assert resp.status_code == 201
        assert body["ocr_confidence"] == 0.85
        assert body["source"] == "ocr"
