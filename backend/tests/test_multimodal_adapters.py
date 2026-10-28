import io
import json
import pytest
from PIL import Image, ImageDraw
from app import create_app
from services.multimodal_service import (
    glm_ocr_infer,
    qwen3_vl_infer,
    calculate_cer_wer,
    _levenshtein_distance,
)
from models import Note, NoteRevision, Extraction, InferenceRun, SourceAsset


@pytest.fixture
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "DATABASE_URL": f"sqlite:///{tmp_path / 'multimodal_test.db'}",
    })


@pytest.fixture
def client(app):
    return app.test_client()


def test_levenshtein_distance_and_cer_wer():
    # Identical
    m_identical = calculate_cer_wer("Lisinopril 10 mg", "Lisinopril 10 mg")
    assert m_identical["cer"] == 0.0
    assert m_identical["wer"] == 0.0
    assert m_identical["char_distance"] == 0

    # 1 char substitution
    m_sub = calculate_cer_wer("Lisinopril 10 mg", "Lisinopril 20 mg")
    assert m_sub["char_distance"] == 1
    assert m_sub["cer"] > 0.0
    assert m_sub["wer"] > 0.0

    # High error rate
    m_high = calculate_cer_wer("Warfarin 2.5 mg", "Aspirin 81 mg")
    assert m_high["cer"] > 0.50
    assert m_high["wer"] > 0.50


def test_glm_ocr_offline_graceful_fallback(monkeypatch):
    # When Ollama is offline, adapter must gracefully return status="disabled"
    monkeypatch.setattr("services.multimodal_service.is_ollama_available", lambda: False)
    dummy_image = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

    res = glm_ocr_infer(dummy_image, page_number=1)
    assert res["status"] == "disabled"
    assert res["error_code"] == "OLLAMA_OFFLINE"
    assert res["transcribed_text"] == ""
    assert res["boxes"] == []


def test_qwen3_vl_offline_graceful_fallback(monkeypatch):
    monkeypatch.setattr("services.multimodal_service.is_ollama_available", lambda: False)
    dummy_image = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

    res = qwen3_vl_infer(dummy_image)
    assert res["status"] == "disabled"
    assert res["error_code"] == "OLLAMA_OFFLINE"
    assert res["candidates"] is None
    assert res["discrepancies"] == []


def test_qwen3_vl_multimodal_proposal_with_discrepancy(monkeypatch):
    monkeypatch.setattr("services.multimodal_service.is_ollama_available", lambda: True)

    mock_ollama_response = {
        "response": json.dumps({
            "medications": [
                {"name": "Metformin", "dose": "1000 mg", "route": "PO", "frequency": "BID"},
                {"name": "Atorvastatin", "dose": "20 mg", "route": "PO", "frequency": "daily"},
            ],
            "vitals": [{"vital_type": "bp", "value": "130/80", "unit": "mmHg"}],
            "visual_evidence": [{"entity": "Metformin", "bbox": [50, 100, 200, 140]}],
        })
    }
    monkeypatch.setattr("services.multimodal_service.query_ollama_multimodal", lambda **kwargs: mock_ollama_response)

    rule_extraction = {
        "medications": [
            {"name": "Metformin", "dose": "500 mg", "route": "PO", "frequency": "BID"},
        ]
    }

    dummy_image = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    res = qwen3_vl_infer(dummy_image, rule_extraction=rule_extraction)

    assert res["status"] == "completed"
    assert len(res["candidates"]["medications"]) == 2
    # Verify discrepancies detected
    discs = res["discrepancies"]
    assert len(discs) >= 2  # 1 dose discrepancy (500mg vs 1000mg) and 1 omitted medication (Atorvastatin)
    disc_types = [d["type"] for d in discs]
    assert "dose_discrepancy" in disc_types
    assert "omitted_medication" in disc_types


def test_multimodal_ai_candidates_api_preserves_authoritative_state(client, monkeypatch):
    """
    Verifies that running multimodal inference creates an InferenceRun record
    without mutating the authoritative Note extraction or creating ReviewEvents.
    """
    headers = {"X-Session-ID": "test-multimodal-session"}

    # Mock Ollama response
    monkeypatch.setattr("services.multimodal_service.is_ollama_available", lambda: True)
    mock_resp = {
        "response": json.dumps({
            "medications": [{"name": "Lisinopril", "dose": "20 mg", "route": "PO", "frequency": "daily"}],
            "vitals": [],
        })
    }
    monkeypatch.setattr("services.multimodal_service.query_ollama_multimodal", lambda **kwargs: mock_resp)

    # 1. Upload a REAL digital PDF with rendered pixels; a .txt upload must
    # NOT be accepted as a successful visual model experiment.
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72),
        "Synthetic medication prescription: Lisinopril 10 mg PO daily. "
        "The remaining content is deliberately long enough to use native PDF text.")
    pdf_bytes = doc.tobytes()
    doc.close()
    up_res = client.post(
        "/api/upload",
        headers=headers,
        data={"file": (io.BytesIO(pdf_bytes), "note.pdf")},
        content_type="multipart/form-data",
    )
    assert up_res.status_code == 201
    note_id = up_res.json["note_id"]
    original_ext_id = up_res.json["extraction_id"]

    # 2. Invoke multimodal candidates API
    ai_res = client.post(
        f"/api/notes/{note_id}/ai-candidates",
        headers=headers,
        json={"adapter": "qwen3_vl", "model": "qwen3-vl:4b"},
    )
    assert ai_res.status_code == 201
    data = ai_res.json
    assert data["status"] == "completed"
    assert "inference_run_id" in data

    # 3. Check note state: authoritative extraction MUST NOT be altered
    st_res = client.get(f"/api/notes/{note_id}", headers=headers)
    assert st_res.status_code == 200
    st_data = st_res.json
    assert st_data["current_extraction_id"] == original_ext_id
    # Note must still be in needs_review, no review head event
    assert st_data["status"] == "needs_review"
    assert st_data["review_head"] is None


def test_vision_adapter_rejects_text_only_source_without_model_fallback(client, monkeypatch):
    headers = {"X-Session-ID": "vision-negative-workspace"}
    created = client.post(
        "/api/notes",
        headers=headers,
        json={"text": "Synthetic note. Lisinopril 10 mg daily."},
    )
    assert created.status_code == 201
    note_id = created.json["note_id"]
    calls = []
    monkeypatch.setattr(
        "services.ollama_service.query_ollama",
        lambda **kwargs: calls.append(kwargs),
    )
    res = client.post(
        f"/api/notes/{note_id}/ai-candidates",
        headers=headers,
        json={"adapter": "qwen3_vl", "model": "qwen3-vl:4b"},
    )
    assert res.status_code == 422
    assert res.json["code"] == "IMAGE_SOURCE_REQUIRED"
    assert calls == []
    assert client.post(
        f"/api/notes/{note_id}/ai-candidates",
        headers=headers,
        json={"adapter": "qwen3_vl", "model": "unsupported-external-model"},
    ).status_code == 422


def test_multimodal_transport_rejects_remote_ollama_without_network(monkeypatch):
    from services import multimodal_service as mm
    monkeypatch.setattr(mm, "OLLAMA_BASE_URL", "https://external-provider.example")
    with pytest.raises(ValueError, match="loopback"):
        mm.query_ollama_multimodal(
            model=mm.DEFAULT_OCR_MODEL,
            prompt="Transcribe synthetic image",
            images_b64=["AAAA"],
        )


def test_multimodal_transport_rejects_unlisted_model_without_network():
    from services import multimodal_service as mm
    with pytest.raises(ValueError, match="allowlist"):
        mm.query_ollama_multimodal(
            model="user-supplied-remote-model",
            prompt="Transcribe synthetic image",
            images_b64=["AAAA"],
        )


def test_inference_rejects_malformed_or_unbounded_model_response(monkeypatch):
    monkeypatch.setattr("services.multimodal_service.is_ollama_available", lambda: True)
    monkeypatch.setattr(
        "services.multimodal_service.query_ollama_multimodal",
        lambda **kwargs: {"response": "[]"},
    )
    glm = glm_ocr_infer(b"synthetic bytes")
    qwen = qwen3_vl_infer(b"synthetic bytes")
    assert glm["status"] == qwen["status"] == "failed"
    assert glm["error_code"] == qwen["error_code"] == "INFERENCE_ERROR"


def test_duplicate_same_name_proposals_flag_occurrence_ambiguity():
    from services.ollama_service import detect_discrepancies
    rule_data = {
        "medications": [
            {"name": "Metformin", "dose": "500 mg"},
            {"name": "Metformin", "dose": "1000 mg"},
        ],
    }
    ai_data = {
        "medications": [
            {"name": "Metformin", "dose": "1000 mg"},
            {"name": "Metformin", "dose": "500 mg"},
        ],
    }
    findings = detect_discrepancies(rule_data, ai_data)
    assert any(item["type"] == "ambiguous_duplicate_occurrences" for item in findings)
    assert not any(item["type"] == "dose_discrepancy" for item in findings)


def test_vision_rejects_tampered_original_asset_before_ollama(
    client, tmp_path, monkeypatch
):
    import fitz
    from utils.db import get_session

    monkeypatch.setattr("routes.upload.STORAGE_ROOT", str(tmp_path / "assets"))
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((50, 70),
        "Synthetic document for provenance checking. "
        "Lisinopril 10 mg PO daily. This is harmless test text.")
    pdf = doc.tobytes()
    doc.close()
    headers = {"X-Session-ID": "asset-integrity-workspace"}
    uploaded = client.post(
        "/api/upload", headers=headers,
        data={"file": (io.BytesIO(pdf), "integrity.pdf")},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 201, uploaded.json

    with get_session(client.application.config["ENGINE"]) as session:
        note = session.query(Note).filter_by(id=uploaded.json["note_id"]).one()
        revision = session.query(NoteRevision).filter_by(
            id=note.current_source_revision_id
        ).one()
        asset = session.query(SourceAsset).filter_by(id=revision.source_asset_id).one()
        from pathlib import Path
        stored_path = Path(asset.storage_key)

    stored_path.write_bytes(b"tampered fixture bytes")
    res = client.post(
        f'/api/notes/{uploaded.json["note_id"]}/ai-candidates',
        headers=headers,
        json={"adapter": "qwen3_vl"},
    )
    assert res.status_code == 409
    assert res.json["code"] == "SOURCE_ASSET_INTEGRITY_FAILURE"


def test_synthetic_handwriting_and_printed_benchmark():
    """
    Deterministic error-metric fixture, NOT a live OCR model benchmark.
    Tests the CER/WER arithmetic against handcrafted candidate strings across:
      1. Clean printed clinical prescriptions.
      2. Degraded / noisy printed prescriptions.
      3. Cursive / handwritten clinical prescriptions.
    Asserts measured failure modes on handwriting and confirms no unverified
    handwriting claims are made.
    """
    # Ground truth test set
    BENCHMARK_CASES = [
        {
            "id": "SYN-PRINT-01",
            "type": "printed_clean",
            "ground_truth": "Rx: Metformin 500 mg PO BID with meals. Lisinopril 10 mg PO daily. BP: 120/80 mmHg.",
            # Model transcription for clean printed text (high accuracy)
            "model_transcription": "Rx: Metformin 500 mg PO BID with meals. Lisinopril 10 mg PO daily. BP: 120/80 mmHg.",
            "ground_truth_meds": ["metformin", "lisinopril"],
            "model_meds": ["metformin", "lisinopril"],
        },
        {
            "id": "SYN-NOISY-02",
            "type": "printed_skewed_noisy",
            "ground_truth": "Rx: Amoxicillin 500 mg TID x 10 days for acute pharyngitis. Temp: 101.2 F.",
            # Model transcription with minor OCR artifact
            "model_transcription": "Rx: Amoxicillin 500 mg T1D x 10 days for acute pharyngitis. Temp: 101.2 F.",
            "ground_truth_meds": ["amoxicillin"],
            "model_meds": ["amoxicillin"],
        },
        {
            "id": "SYN-HAND-03",
            "type": "cursive_handwritten",
            # Realistic physician handwriting sample with cursive stroke ambiguity
            "ground_truth": "Rx: Warfarin 2.5 mg PO daily at bedtime. Check INR weekly. Sig: take with water.",
            # HAND-WRITTEN SIMULATION of an OCR failure, not generated by GLM-OCR.
            "model_transcription": "Rx: Warfarin 25 mg PO daily at bedtme. Check INR weakly. Big: take with water.",
            "ground_truth_meds": ["warfarin 2.5 mg"],
            "model_meds": ["warfarin 25 mg"],  # Critical dosage error!
        },
    ]

    benchmark_results = []
    for case in BENCHMARK_CASES:
        scores = calculate_cer_wer(case["ground_truth"], case["model_transcription"])
        benchmark_results.append({
            "case_id": case["id"],
            "type": case["type"],
            "cer": scores["cer"],
            "wer": scores["wer"],
        })

    # Printed Clean: expect zero or negligible errors
    print_res = next(r for r in benchmark_results if r["case_id"] == "SYN-PRINT-01")
    assert print_res["cer"] <= 0.02
    assert print_res["wer"] <= 0.02

    # Handwritten-error SIMULATION: must preserve the ability to measure
    # large critical-dose transcription errors; no live model was executed.
    hand_res = next(r for r in benchmark_results if r["case_id"] == "SYN-HAND-03")
    assert hand_res["cer"] >= 0.05, f"Expected measured error on handwriting, got {hand_res['cer']}"
    assert hand_res["wer"] >= 0.15, f"Expected word error on handwriting, got {hand_res['wer']}"

    # Critical Assertion: handwriting support CANNOT be claimed without empirical verification
    handwriting_supported = False if hand_res["cer"] > 0.03 else True
    assert handwriting_supported is False, (
        "Handwriting support cannot be claimed as production-ready: measured CER exceeds tolerance."
    )
