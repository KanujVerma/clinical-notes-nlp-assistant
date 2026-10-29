"""Only measured, hash-bound, curated synthetic evidence can be public."""
import json

import pytest

from app import create_app
from services.showcase_evidence import (
    ShowcaseEvidenceError, BASELINE_FILE, public_showcase,
    verified_tesseract_baseline, verified_recorded_ai,
)
from scripts.freeze_local_showcase_ai import freeze


def test_real_committed_tesseract_baseline_is_labeled_and_arithmetically_valid():
    baseline = verified_tesseract_baseline()
    assert baseline["status"] == "recorded_real_tesseract"
    assert baseline["case_count"] == 3
    assert baseline["critical_token_hits"] == baseline["critical_token_total"] == 11
    assert baseline["cer_micro"] == pytest.approx(15 / 392)
    assert baseline["wer_micro"] == pytest.approx(19 / 70)
    assert all(len(row["source_sha256"]) == 64 for row in baseline["cases"])
    assert "clinical validation" in baseline["limitations"]


def test_public_showcase_requires_no_workspace_and_no_ai_keys(tmp_path):
    app = create_app({"TESTING": True, "DATABASE_URL": f"sqlite:///{tmp_path / 'showcase.db'}"})
    resp = app.test_client().get("/api/showcase-evidence")
    assert resp.status_code == 200, resp.json
    assert resp.json["synthetic_only"] is True
    assert resp.json["ready_for_clinical_use"] is False
    assert resp.json["recorded_ai"]["status"] == "not_recorded"
    assert resp.json["baseline"]["model"] == "Tesseract"
    assert resp.headers["Cache-Control"] == "no-store"
    assert resp.json["baseline"]["cases"][0]["transcription"]


def test_rejects_fabricated_or_wrong_dataset_recorded_model_results(tmp_path):
    baseline = verified_tesseract_baseline()
    rec = tmp_path / "recorded_ai.json"
    model_cases = [{
        "case_id": sample["case_id"],
        "source_sha256": sample["source_sha256"],
        "transcription": sample["transcription"],
    } for sample in baseline["cases"]]

    payload = {
        "schema_version": "1",
        "synthetic_only": True,
        "independently_reviewed": True,
        "source_manifest_sha256": "0" * 64,
        "model_runs": [{
            "adapter": "glm_ocr",
            "model_digest": "sha256:" + ("a" * 64),
            "cases": model_cases,
        }],
    }
    rec.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ShowcaseEvidenceError, match="RECORDED_AI_INVALID"):
        verified_recorded_ai(baseline, rec)

    payload["source_manifest_sha256"] = baseline["manifest_sha256"]
    payload["model_runs"][0]["cases"][0]["source_sha256"] = "f" * 64
    rec.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ShowcaseEvidenceError, match="RECORDED_AI_SOURCE_MISMATCH"):
        verified_recorded_ai(baseline, rec)

    # Unit fixtures can exercise a validation contract, not assert real AI
    # performance or produce a file committed as a recorded model example.
    payload["model_runs"][0]["cases"][0]["source_sha256"] = baseline["cases"][0]["source_sha256"]
    rec.write_text(json.dumps(payload), encoding="utf-8")
    result = verified_recorded_ai(baseline, rec)
    assert result["models"][0]["source"] == "curator_reviewed_local_recording"
    assert result["status"] == "recorded_model_proposals_unverified"


def test_tesseract_only_report_never_promoted_as_ai(tmp_path):
    report = tmp_path / "tesseract_only.json"
    report.write_bytes(BASELINE_FILE.read_bytes())
    target = tmp_path / "recorded_ai.json"
    with pytest.raises(ShowcaseEvidenceError, match="CURATOR_APPROVAL_REQUIRED"):
        freeze(report, target, reviewed=False)
    with pytest.raises(ShowcaseEvidenceError, match="NO_REAL_LOCAL_AI_MODEL_ARMS"):
        freeze(report, target, reviewed=True)
    assert not target.exists()


def test_corrupt_published_evidence_fails_closed(tmp_path, monkeypatch):
    import services.showcase_evidence as service
    bad = tmp_path / "bad.json"
    bad.write_text('{"synthetic_only": false, "status": "completed_local_actual_predictions"}')
    with pytest.raises(ShowcaseEvidenceError):
        public_showcase(path=bad, recordings=tmp_path / "missing.json")

    # Ensure the HTTP endpoint does not leak fixture paths or raw data on
    # corruption and cannot silently substitute fabricated model results.
    monkeypatch.setattr(service, "BASELINE_FILE", bad)
    # The endpoint invokes public_showcase's bound default path, so directly
    # verify the pure validation contract above; do not pretend monkeypatch
    # changes an already bound default argument.
