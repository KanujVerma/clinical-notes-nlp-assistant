"""Synthetic evaluation manifest gates must fail closed (not silently skip cases)."""
import json

import pytest

from evaluation.dataset import load_curated_corpus


def _write_pair(root, stem="case-001"):
    notes = root / "notes"
    labels = root / "labels"
    notes.mkdir(parents=True, exist_ok=True)
    labels.mkdir(parents=True, exist_ok=True)
    (notes / f"{stem}.txt").write_text("Synthetic note. BP 120/80.", encoding="utf-8")
    (labels / f"{stem}.json").write_text(json.dumps({
        "vitals": {}, "medications": [], "instructions": {}, "metadata": {},
    }), encoding="utf-8")


def test_complete_synthetic_pair_has_hashed_manifest(tmp_path):
    _write_pair(tmp_path)
    cases, manifest = load_curated_corpus(tmp_path)
    assert len(cases) == manifest["expected_cases"] == 1
    assert len(manifest["manifest_sha256"]) == 64
    assert all(len(row["source_sha256"]) == len(row["gold_sha256"]) == 64
               for row in manifest["entries"])
    assert manifest["annotation_status"] == "author-created_inspected_not_clinician_adjudicated"


def test_missing_and_orphan_labels_fail_closed(tmp_path):
    _write_pair(tmp_path)
    (tmp_path / "labels" / "case-001.json").unlink()
    with pytest.raises(ValueError, match="missing_labels"):
        load_curated_corpus(tmp_path)
    _write_pair(tmp_path)
    (tmp_path / "labels" / "orphan.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="orphan_labels"):
        load_curated_corpus(tmp_path)


def test_missing_category_or_malformed_gold_fails_closed(tmp_path):
    _write_pair(tmp_path)
    label = tmp_path / "labels" / "case-001.json"
    label.write_text('{"medications":[]}', encoding="utf-8")
    with pytest.raises(ValueError, match="Missing required gold"):
        load_curated_corpus(tmp_path)
    label.write_text("garbage", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON"):
        load_curated_corpus(tmp_path)


def test_invalid_utf8_and_empty_note_fail_closed(tmp_path):
    _write_pair(tmp_path)
    note = tmp_path / "notes" / "case-001.txt"
    note.write_bytes(b"\xff\xfe")
    with pytest.raises(ValueError, match="UTF-8"):
        load_curated_corpus(tmp_path)
    note.write_text("   ", encoding="utf-8")
    with pytest.raises(ValueError, match="Empty synthetic"):
        load_curated_corpus(tmp_path)
