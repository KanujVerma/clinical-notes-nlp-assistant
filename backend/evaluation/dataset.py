"""Fail-closed loader for the curated *synthetic development* benchmark.

The legacy 20-note corpus is neither an independent clinical validation set nor
an untouched holdout. Every labeled case is accounted for before scoring.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


CATEGORIES = ("vitals", "medications", "instructions", "metadata")


def load_curated_corpus(data_dir: str | Path) -> tuple[list[tuple[str, str, dict]], dict[str, Any]]:
    root = Path(data_dir)
    notes_dir, labels_dir = root / "notes", root / "labels"
    if not notes_dir.is_dir() or not labels_dir.is_dir():
        raise ValueError("Synthetic evaluation notes/labels directories are missing")

    notes = {p.stem: p for p in notes_dir.glob("*.txt") if p.is_file()}
    labels = {p.stem: p for p in labels_dir.glob("*.json") if p.is_file()}
    if not notes or notes.keys() != labels.keys():
        missing = sorted(notes.keys() - labels.keys())
        orphaned = sorted(labels.keys() - notes.keys())
        raise ValueError(f"Incomplete evaluation pairs: missing_labels={missing}, orphan_labels={orphaned}")

    paired = []
    entries = []
    for note_id in sorted(notes):
        source_bytes = notes[note_id].read_bytes()
        try:
            note_text = source_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Invalid UTF-8 benchmark input: {note_id}") from exc
        if not note_text.strip():
            raise ValueError(f"Empty synthetic evaluation input: {note_id}")
        gold_bytes = labels[note_id].read_bytes()
        try:
            gold = json.loads(gold_bytes.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError(f"Invalid JSON/UTF-8 gold labels: {note_id}") from exc
        if not isinstance(gold, dict) or set(CATEGORIES) - set(gold):
            raise ValueError(f"Missing required gold categories: {note_id}")
        if (not isinstance(gold["vitals"], dict)
                or not isinstance(gold["metadata"], dict)
                or not isinstance(gold["medications"], list)
                or not isinstance(gold["instructions"], (list, dict))):
            raise ValueError(f"Malformed structured gold labels: {note_id}")
        if any(not isinstance(m, dict) or not str(m.get("name", "")).strip()
               for m in gold["medications"]):
            raise ValueError(f"Invalid gold medication occurrence: {note_id}")
        paired.append((note_id, note_text, gold))
        entries.append({
            "id": note_id,
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "gold_sha256": hashlib.sha256(gold_bytes).hexdigest(),
        })

    return paired, {
        "dataset_id": "legacy_synthetic_development",
        "annotation_status": "author-created_inspected_not_clinician_adjudicated",
        "expected_cases": len(notes),
        "entries": entries,
        "manifest_sha256": hashlib.sha256(
            json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }
