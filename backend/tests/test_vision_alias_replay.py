"""Offline regression checks for post-hoc replay of REAL saved local model outputs.

The replay must never call models, alter the raw predictions, or claim that a
normalization selected after viewing outputs is a prospective clinical score.
"""
import json
from pathlib import Path

import pytest

from evaluation.local_vision_eval import VITAL_FIELDS, score_occurrences
from evaluation.replay_vital_scoring import replay
from evaluation.vision_vital_aliases import (
    ALIAS_VERSION, canonical_vital_type, normalized_vitals,
)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "vision_gold_30" / "manifest.json"
ORIGINAL = ROOT / "artifacts" / "evaluation" / "paired_local_17f5737320b78e10.json"


@pytest.mark.parametrize("label,expected", [
    ("BP", "blood_pressure"),
    ("blood pressure", "blood_pressure"),
    ("blood_pressure", "blood_pressure"),
    ("HR", "heart_rate"),
    ("Pulse", "heart_rate"),
    ("RR", "respiratory_rate"),
    ("SpO2", "oxygen_saturation"),
    ("oxygen saturation", "oxygen_saturation"),
    ("Temp", "temperature"),
    ("fasting blood glucose", "blood_glucose"),
    ("systolic BP", "systolic_bp"),
    ("QT interval", "qt_interval"),
])
def test_safe_vital_alias_map_is_explicit(label, expected):
    assert canonical_vital_type(label) == expected
    assert "posthoc" in ALIAS_VERSION


def test_blood_pressure_mismatch_remains_incorrect_after_alias_normalization():
    gold = normalized_vitals([
        {"vital_type": "blood_pressure", "value": "118/76", "unit": "mmHg"},
    ])
    pred = normalized_vitals([
        {"vital_type": "BP", "value": "118/78", "unit": "mmHg"},
    ])
    scored = score_occurrences(gold, pred, VITAL_FIELDS, "vital_type")
    assert scored["tp"] == 0 and scored["fp"] == 1 and scored["fn"] == 1
    assert scored["mismatches"][0]["attributes"]["value"]["expected"] == "118/76"

    # A single systolic measurement does not become a full blood pressure.
    partial = normalized_vitals([
        {"vital_type": "systolic BP", "value": "118", "unit": "mmHg"},
    ])
    assert score_occurrences(gold, partial, VITAL_FIELDS, "vital_type")["tp"] == 0


def test_redundant_spo2_percent_only_when_unit_is_already_percent():
    expected = normalized_vitals([
        {"vital_type": "oxygen_saturation", "value": "98", "unit": "%"},
    ])
    prediction = normalized_vitals([
        {"vital_type": "SpO2", "value": "98%", "unit": "%"},
    ])
    assert score_occurrences(expected, prediction, VITAL_FIELDS, "vital_type")["tp"] == 1
    bad = normalized_vitals([
        {"vital_type": "SpO2", "value": "98", "unit": "bpm"},
    ])
    assert score_occurrences(expected, bad, VITAL_FIELDS, "vital_type")["tp"] == 0


def test_original_model_evidence_replays_without_a_new_ollama_call(tmp_path, monkeypatch):
    from evaluation import local_vision_eval as vision
    monkeypatch.setattr(
        vision, "get_installed_model_digest",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("A replay must not invoke Ollama")
        ),
    )
    result = replay(MANIFEST, ORIGINAL, tmp_path)
    data = json.loads(result.read_text(encoding="utf-8"))

    assert data["status"] == "completed_posthoc_reanalysis_from_saved_predictions"
    assert data["is_new_model_run"] is False
    assert data["evidence_tier"] == "exploratory_after_inspecting_model_outputs"
    assert data["normalization_version"] == ALIAS_VERSION
    assert data["original_exact_vitals"]["tp"] == 1
    assert data["original_exact_vitals"]["fp"] == 28
    assert data["original_exact_vitals"]["fn"] == 23
    # Exact source images and raw saved Qwen predictions, new scorer ONLY.
    corrected = data["posthoc_alias_normalized_vitals"]
    assert (corrected["tp"], corrected["fp"], corrected["fn"]) == (23, 6, 1)
    assert corrected["f1"] == pytest.approx(0.8679245283018867)
    assert data["dataset"]["case_count"] == 30
    assert data["reference_model_git_sha"].startswith("22f38cc")
    assert len(data["reference_report_sha256"]) == 64
    assert len(data["cases"]) == 30
    assert any(
        x["case_id"] == "clean_07_multiple_vitals_panel"
        and x["posthoc_vitals"]["fn"] >= 1
        for x in data["cases"]
    )


def test_replay_detects_tampered_stored_image_binding(tmp_path):
    modified = json.loads(ORIGINAL.read_text(encoding="utf-8"))
    modified["cases"]["qwen3_vl"][0]["source_sha256"] = "0" * 64
    source = tmp_path / "modified.json"
    source.write_text(json.dumps(modified), encoding="utf-8")
    with pytest.raises(ValueError, match="EVALUATION_SOURCE_MISMATCH"):
        replay(MANIFEST, source, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_saved_qwen_warfarin_case_was_omitted_not_successfully_extracted():
    data = json.loads(ORIGINAL.read_text(encoding="utf-8"))
    warfarin = next(
        x for x in data["cases"]["qwen3_vl"]
        if x["case_id"] == "clean_02_decimal_warfarin"
    )
    assert warfarin["structured_candidates"]["medications"] == []
    assert warfarin["medications"]["fn"] == 1
    assert warfarin["medications"]["tp"] == 0
