import io
import fitz
import pytest
from PIL import Image
from app import create_app
from utils.coordinates import validate_bbox_geometry, transform_bbox, check_source_image_agreement
from utils.acquisition import acquire_document


@pytest.fixture
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "DATABASE_URL": f"sqlite:///{tmp_path / 'viewer_test.db'}",
    })


@pytest.fixture
def client(app):
    return app.test_client()


def test_validate_bbox_geometry():
    page_w, page_h = 612.0, 792.0

    # Valid box
    valid, code, msg = validate_bbox_geometry([50.0, 100.0, 200.0, 150.0], page_w, page_h)
    assert valid is True
    assert code == "VALID"
    assert msg is None

    # Missing / None geometry
    valid, code, msg = validate_bbox_geometry(None, page_w, page_h)
    assert valid is False
    assert code == "MISSING_GEOMETRY"

    # Incomplete geometry
    valid, code, msg = validate_bbox_geometry([50.0, 100.0], page_w, page_h)
    assert valid is False
    assert code == "MISSING_GEOMETRY"

    # Degenerate (width <= 0)
    valid, code, msg = validate_bbox_geometry([200.0, 100.0, 50.0, 150.0], page_w, page_h)
    assert valid is False
    assert code == "DEGENERATE_BOX"

    # Out of bounds
    valid, code, msg = validate_bbox_geometry([50.0, 100.0, 700.0, 150.0], page_w, page_h)
    assert valid is False
    assert code == "OUT_OF_BOUNDS"


def test_coordinate_transforms_across_rotations():
    # 200x100 page, box [20, 10, 60, 40]
    # Box width = 40, height = 30
    page_w, page_h = 200.0, 100.0
    bbox = [20.0, 10.0, 60.0, 40.0]

    # 0 degrees
    t0 = transform_bbox(bbox, page_w, page_h, rotation=0)
    assert t0["left_pct"] == pytest.approx(10.0, 0.01)   # (20/200)*100
    assert t0["top_pct"] == pytest.approx(10.0, 0.01)    # (10/100)*100
    assert t0["width_pct"] == pytest.approx(20.0, 0.01)  # (40/200)*100
    assert t0["height_pct"] == pytest.approx(30.0, 0.01) # (30/100)*100
    assert t0["rendered_width"] == 200.0
    assert t0["rendered_height"] == 100.0

    # 90 degrees clockwise: rendered_width = 100, rendered_height = 200
    # x0_rot = height - y1 = 100 - 40 = 60
    # y0_rot = x0 = 20
    # w_rot = y1 - y0 = 30
    # h_rot = x1 - x0 = 40
    t90 = transform_bbox(bbox, page_w, page_h, rotation=90)
    assert t90["rendered_width"] == 100.0
    assert t90["rendered_height"] == 200.0
    assert t90["left_pct"] == pytest.approx(60.0, 0.01)   # (60/100)*100
    assert t90["top_pct"] == pytest.approx(10.0, 0.01)    # (20/200)*100
    assert t90["width_pct"] == pytest.approx(30.0, 0.01)  # (30/100)*100
    assert t90["height_pct"] == pytest.approx(20.0, 0.01) # (40/200)*100

    # 180 degrees: rendered_width = 200, rendered_height = 100
    # x0_rot = width - x1 = 200 - 60 = 140
    # y0_rot = height - y1 = 100 - 40 = 60
    t180 = transform_bbox(bbox, page_w, page_h, rotation=180)
    assert t180["left_pct"] == pytest.approx(70.0, 0.01)  # (140/200)*100
    assert t180["top_pct"] == pytest.approx(60.0, 0.01)   # (60/100)*100

    # 270 degrees clockwise: rendered_width = 100, rendered_height = 200
    # x0_rot = y0 = 10
    # y0_rot = width - x1 = 200 - 60 = 140
    t270 = transform_bbox(bbox, page_w, page_h, rotation=270)
    assert t270["left_pct"] == pytest.approx(10.0, 0.01)  # (10/100)*100
    assert t270["top_pct"] == pytest.approx(70.0, 0.01)   # (140/200)*100


def test_source_image_agreement_and_disagreement():
    page_w, page_h = 600.0, 800.0
    page_boxes = [
        {"bbox": [50.0, 100.0, 120.0, 120.0], "text": "Metformin"},
        {"bbox": [125.0, 100.0, 175.0, 120.0], "text": "500mg"},
        {"bbox": [50.0, 150.0, 120.0, 170.0], "text": "Lisinopril"},
        {"bbox": [125.0, 150.0, 165.0, 170.0], "text": "10mg"},
    ]

    # Agreement case: span matches OCR text inside bbox
    res = check_source_image_agreement(
        span_text="Metformin 500mg",
        bbox=[45.0, 95.0, 180.0, 125.0],
        page_boxes=page_boxes,
        page_width=page_w,
        page_height=page_h,
    )
    assert res["agreement"] is True
    assert res["status"] == "ocr_consistent_unverified"
    assert "Metformin 500mg" in res["ocr_text"]

    # Disagreement case: transcript claims Warfarin, but OCR contains Lisinopril
    res_disagree = check_source_image_agreement(
        span_text="Warfarin 5mg",
        bbox=[45.0, 145.0, 170.0, 175.0],
        page_boxes=page_boxes,
        page_width=page_w,
        page_height=page_h,
    )
    assert res_disagree["agreement"] is False
    assert res_disagree["status"] == "disagreement"
    assert "Lisinopril" in res_disagree["ocr_text"]
    assert "Disagreement" in res_disagree["reason"]

    # Missing geometry case
    res_missing = check_source_image_agreement(
        span_text="Aspirin 81mg",
        bbox=None,
        page_boxes=page_boxes,
        page_width=page_w,
        page_height=page_h,
    )
    assert res_missing["agreement"] is False
    assert res_missing["status"] == "missing_geometry"

    # Decimal dose discrepancy case: Warfarin 2.5 mg vs 25 mg
    res_decimal = check_source_image_agreement(
        span_text="Warfarin 2.5 mg",
        bbox=[45.0, 145.0, 170.0, 175.0],
        page_boxes=[
            {"bbox": [50.0, 150.0, 120.0, 170.0], "text": "Warfarin"},
            {"bbox": [125.0, 150.0, 165.0, 170.0], "text": "25mg"},
        ],
        page_width=page_w,
        page_height=page_h,
    )
    assert res_decimal["agreement"] is False
    assert res_decimal["status"] == "disagreement"
    assert "2.5" in res_decimal["reason"]

    # Negation polarity mismatch: Continue aspirin vs Do not continue aspirin
    res_neg = check_source_image_agreement(
        span_text="Continue aspirin",
        bbox=[45.0, 145.0, 170.0, 175.0],
        page_boxes=[
            {"bbox": [50.0, 150.0, 70.0, 170.0], "text": "Do"},
            {"bbox": [75.0, 150.0, 100.0, 170.0], "text": "not"},
            {"bbox": [105.0, 150.0, 150.0, 170.0], "text": "continue"},
            {"bbox": [155.0, 150.0, 190.0, 170.0], "text": "aspirin"},
        ],
        page_width=page_w,
        page_height=page_h,
    )
    assert res_neg["agreement"] is False
    assert res_neg["status"] == "disagreement"
    assert "polarity mismatch" in res_neg["reason"]


def test_page_image_api_and_evidence_geometry_verification(client):
    headers = {"X-Session-ID": "test-viewer-session"}

    # 1. Upload a 2-page PDF
    doc = fitz.open()
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 72), "Patient John Doe. Prescribed Metformin 500 mg daily oral.", fontsize=12)
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((50, 72), "Second page follow up instructions: Return in 3 months.", fontsize=12)
    pdf_bytes = doc.tobytes()
    doc.close()

    upload_res = client.post(
        "/api/upload",
        headers=headers,
        data={"file": (io.BytesIO(pdf_bytes), "clinical_doc.pdf")},
        content_type="multipart/form-data",
    )
    assert upload_res.status_code == 201
    note_id = upload_res.json["note_id"]

    # 2. Get Page 1 Image
    img_res = client.get(f"/api/notes/{note_id}/pages/1/image", headers=headers)
    assert img_res.status_code == 200
    assert img_res.content_type == "image/png"
    assert len(img_res.data) > 1000

    # 3. Get Page 1 Image with rotation = 90
    img_res_rot = client.get(f"/api/notes/{note_id}/pages/1/image?rotation=90", headers=headers)
    assert img_res_rot.status_code == 200
    assert img_res_rot.content_type == "image/png"

    # Unsupported angle must fail instead of rendering a page with
    # geometry that the client does not know how to transform.
    invalid_rotation = client.get(
        f"/api/notes/{note_id}/pages/1/image?rotation=45", headers=headers
    )
    assert invalid_rotation.status_code == 422
    assert invalid_rotation.json["code"] == "INVALID_ROTATION"

    # 4. Out of bounds page
    img_res_oob = client.get(f"/api/notes/{note_id}/pages/99/image", headers=headers)
    assert img_res_oob.status_code == 404
    assert img_res_oob.json["code"] == "PAGE_OUT_OF_BOUNDS"

    # 5. Verify evidence geometry API
    ver_res = client.post(
        f"/api/notes/{note_id}/verify-evidence-geometry",
        headers=headers,
        json={
            "page_number": 1,
            "span_text": "Metformin 500 mg",
            "bbox": [50.0, 60.0, 250.0, 90.0],
            "rotation": 0,
        },
    )
    assert ver_res.status_code == 200
    data = ver_res.json
    assert data["is_valid_geometry"] is True
    assert data["transformed_overlay"] is not None
    assert "left_pct" in data["transformed_overlay"]
    assert "top_pct" in data["transformed_overlay"]

    unsupported_page = client.post(
        f"/api/notes/{note_id}/verify-evidence-geometry",
        headers=headers,
        json={"page_number": 99, "span_text": "Metformin", "bbox": [10, 10, 50, 30]},
    )
    assert unsupported_page.status_code == 404
    assert unsupported_page.json["code"] == "PAGE_OUT_OF_BOUNDS"

    # 6. Verify evidence geometry with missing bbox
    ver_missing = client.post(
        f"/api/notes/{note_id}/verify-evidence-geometry",
        headers=headers,
        json={
            "page_number": 1,
            "span_text": "Metformin 500 mg",
            "bbox": None,
        },
    )
    assert ver_missing.status_code == 200
    assert ver_missing.json["is_valid_geometry"] is False
    assert ver_missing.json["geometry_code"] == "MISSING_GEOMETRY"


def test_rotated_ocr_boxes_mapped_to_unrotated_page_frame(tmp_path):
    from unittest.mock import patch

    pdf = fitz.open()
    pdf.new_page(width=200, height=100)
    data = pdf.tobytes()
    pdf.close()

    tess = {"text": ["Drug"], "conf": [99], "left": [10], "top": [400], "width": [40], "height": [40]}
    with patch("utils.acquisition.pytesseract.image_to_osd", return_value="Rotate: 90"), patch(
        "utils.acquisition.pytesseract.image_to_data", return_value=tess
    ):
        _, _, details = acquire_document(data, "rotated.pdf", "application/pdf", "probe", str(tmp_path))
        boxes = details["pages"][0]["boxes"]
        assert len(boxes) == 1
        # Bbox in original unrotated 200x100 page frame:
        assert boxes[0]["bbox"] == [143.88, 82.01, 158.27, 96.4]


def test_edit_note_source_preserves_page_inventory_for_multipage_pdf(client):
    headers = {"X-Session-ID": "test-multipage-edit"}

    # Upload 2-page PDF
    pdf = fitz.open()
    pdf.new_page(width=600, height=800)
    pdf.new_page(width=600, height=800)
    page0 = pdf[0]
    page0.insert_text((50, 100), "Prescription: Lisinopril 10 mg PO daily for hypertension.")
    page1 = pdf[1]
    page1.insert_text((50, 100), "Blood pressure: 120/80 mmHg. Follow up in 2 weeks.")
    pdf_bytes = pdf.tobytes()
    pdf.close()

    upload_res = client.post(
        "/api/upload",
        headers=headers,
        data={"file": (io.BytesIO(pdf_bytes), "multipage.pdf")},
        content_type="multipart/form-data",
    )
    assert upload_res.status_code == 201
    note_id = upload_res.json["note_id"]

    # Initial source has 2 pages
    source_res1 = client.get(f"/api/notes/{note_id}/source", headers=headers)
    assert source_res1.status_code == 200
    assert len(source_res1.json["pages"]) == 2
    rev1_id = source_res1.json["revision_id"]

    # Edit transcription text
    edit_res = client.post(
        f"/api/notes/{note_id}/revisions",
        headers=headers,
        json={
            "raw_text": "Updated text: Lisinopril 20 mg PO daily.",
            "expected_source_revision_id": rev1_id,
            "expected_lock_version": 0,
            "reason": "transcription_correction",
        },
    )
    assert edit_res.status_code == 201

    # Source after edit must retain the 2-page inventory
    source_res2 = client.get(f"/api/notes/{note_id}/source", headers=headers)
    assert source_res2.status_code == 200
    pages2 = source_res2.json["pages"]
    assert len(pages2) == 2


def test_decimal_dose_disagreement_detection():
    # Transcript has Warfarin .5 mg PO daily, OCR has Warfarin 5 mg PO daily
    boxes = [{"bbox": [50.0, 50.0, 200.0, 80.0], "text": "Warfarin 5 mg PO daily"}]
    res = check_source_image_agreement(
        "Warfarin .5 mg PO daily",
        [50.0, 50.0, 200.0, 80.0],
        boxes,
        800.0,
        1100.0,
    )
    assert not res["agreement"]
    assert res["status"] == "disagreement"
    assert "numeric value '0.5'" in res["reason"] or "0.5" in res["reason"]


def test_text_note_multipage_pagination(client):
    headers = {"X-Session-ID": "test-text-pagination"}
    # Create note with 70 lines (should produce 2 pages, 45 lines/page)
    long_text = "\n".join([f"Line {i}: Clinical observation data" for i in range(1, 71)])
    create_res = client.post(
        "/api/notes",
        headers=headers,
        json={"text": long_text},
    )
    assert create_res.status_code == 201
    note_id = create_res.json["note_id"]

    source_res = client.get(f"/api/notes/{note_id}/source", headers=headers)
    assert source_res.status_code == 200
    assert len(source_res.json["pages"]) == 2

    # Fetch page 1 image
    p1_res = client.get(f"/api/notes/{note_id}/pages/1/image", headers=headers)
    assert p1_res.status_code == 200
    assert p1_res.content_type == "image/png"

    # Fetch page 2 image
    p2_res = client.get(f"/api/notes/{note_id}/pages/2/image", headers=headers)
    assert p2_res.status_code == 200
    assert p2_res.content_type == "image/png"

    # Page 3 is out of bounds
    p3_res = client.get(f"/api/notes/{note_id}/pages/3/image", headers=headers)
    assert p3_res.status_code == 404
    assert p3_res.json["code"] == "PAGE_OUT_OF_BOUNDS"
    assert source_res.json["pages"][0]["page_number"] == 1
    assert source_res.json["pages"][1]["page_number"] == 2
