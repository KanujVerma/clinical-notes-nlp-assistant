import io
import fitz
import pytest
from PIL import Image
from app import create_app
from utils.acquisition import acquire_document


@pytest.fixture
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "DATABASE_URL": f"sqlite:///{tmp_path / 'acq_test.db'}",
    })


@pytest.fixture
def client(app):
    return app.test_client()


def test_upload_rejects_invalid_utf8(client):
    headers = {"X-Session-ID": "test-enc-session"}
    # Send bytes that are invalid UTF-8 (e.g. lone 0xFF or continuation byte 0x80 without leading byte)
    invalid_bytes = b"Patient note \xff\xfe invalid utf8 data \x80\x81."
    res = client.post(
        "/api/upload",
        headers=headers,
        data={"file": (io.BytesIO(invalid_bytes), "corrupt.txt")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 422
    assert res.json["code"] == "INVALID_ENCODING"


def test_mixed_pdf_pagewise_acquisition_digital_and_scanned(tmp_path):
    # Create a 2-page PDF in-memory:
    # Page 1: Digital text (>= 50 chars)
    # Page 2: Image-only (scanned page)
    doc = fitz.open()

    # Page 1 (digital)
    p1 = doc.new_page(width=595, height=842)
    digital_text = "This is a digital clinical document page with sufficient text characters to exceed the 50 char threshold."
    p1.insert_text((50, 72), digital_text, fontsize=12)

    # Page 2 (scanned image)
    img = Image.new("RGB", (300, 100), color=(255, 255, 255))
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="PNG")
    img_bytes = img_byte_arr.getvalue()

    p2 = doc.new_page(width=595, height=842)
    p2.insert_image(p2.rect, stream=img_bytes)

    pdf_bytes = doc.tobytes()
    doc.close()

    asset, acq_run, details = acquire_document(
        file_bytes=pdf_bytes,
        original_filename="mixed_sample.pdf",
        mime_type="application/pdf",
        workspace_id="ws-test",
        storage_root=str(tmp_path / "storage"),
    )

    assert asset.page_count == 2
    pages = details["pages"]
    assert len(pages) == 2

    # Page 1 should be acquired via native_pdf
    assert pages[0]["acquisition_method"] == "native_pdf"
    assert pages[0]["confidence"] == 1.0

    # Page 2 (image with no text) should fall back to tesseract_ocr
    assert pages[1]["acquisition_method"] == "tesseract_ocr"
