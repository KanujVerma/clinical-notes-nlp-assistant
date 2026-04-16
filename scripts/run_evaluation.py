#!/usr/bin/env python3
# scripts/run_evaluation.py
"""
Run evaluation on the 20 labeled eval notes.
Writes results to backend/evaluation/results.json.
Prints a formatted summary.
Usage: python scripts/run_evaluation.py
"""
import sys, os, json
from pathlib import Path

_BACKEND = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(_BACKEND))

from config import Config
from extractors.pipeline import run_pipeline
from evaluation.compare import (
    compare_vitals, compare_instructions, compare_medications, compare_metadata
)
from evaluation.metrics import compute_metrics, aggregate_metrics
from evaluation.report import build_report, print_summary

EVAL_NOTES_DIR = Path(__file__).parent.parent / "data" / "eval" / "notes"
EVAL_LABELS_DIR = Path(__file__).parent.parent / "data" / "eval" / "labels"


def evaluate_note(note_text: str, label: dict) -> dict:
    prediction = run_pipeline(note_text)

    v_tp, v_fp, v_fn = compare_vitals(prediction.get("vitals", {}), label.get("vitals", {}))
    m_tp, m_fp, m_fn = compare_medications(prediction.get("medications", []), label.get("medications", []))
    i_tp, i_fp, i_fn = compare_instructions(prediction.get("instructions", {}), label.get("instructions", {}))
    mt_tp, mt_fp, mt_fn = compare_metadata(prediction.get("metadata", {}), label.get("metadata", {}))

    return {
        "vitals_f1": compute_metrics(v_tp, v_fp, v_fn)["f1"],
        "medications_f1": compute_metrics(m_tp, m_fp, m_fn)["f1"],
        "instructions_f1": compute_metrics(i_tp, i_fp, i_fn)["f1"],
        "metadata_f1": compute_metrics(mt_tp, mt_fp, mt_fn)["f1"],
        "_tp": (v_tp, m_tp, i_tp, mt_tp),
        "_fp": (v_fp, m_fp, i_fp, mt_fp),
        "_fn": (v_fn, m_fn, i_fn, mt_fn),
    }


def main():
    note_files = sorted(EVAL_NOTES_DIR.glob("*.txt"))
    if not note_files:
        print(f"No eval notes found in {EVAL_NOTES_DIR}")
        sys.exit(1)

    per_note = []
    totals = {"vitals": [0,0,0], "medications": [0,0,0], "instructions": [0,0,0], "metadata": [0,0,0]}
    cats = ["vitals", "medications", "instructions", "metadata"]

    for note_path in note_files:
        label_path = EVAL_LABELS_DIR / (note_path.stem + ".json")
        if not label_path.exists():
            print(f"  SKIP {note_path.name}: no label file found")
            continue

        note_text = note_path.read_text(encoding="utf-8")
        label = json.loads(label_path.read_text(encoding="utf-8"))

        result = evaluate_note(note_text, label)

        for i, cat in enumerate(cats):
            totals[cat][0] += result["_tp"][i]
            totals[cat][1] += result["_fp"][i]
            totals[cat][2] += result["_fn"][i]

        per_note.append({
            "note": note_path.name,
            "vitals_f1": result["vitals_f1"],
            "medications_f1": result["medications_f1"],
            "instructions_f1": result["instructions_f1"],
            "metadata_f1": result["metadata_f1"],
        })
        print(f"  Evaluated {note_path.name}")

    agg = aggregate_metrics(
        tuple(totals["vitals"]),
        tuple(totals["medications"]),
        tuple(totals["instructions"]),
        tuple(totals["metadata"]),
    )

    report = build_report(Config.PIPELINE_VERSION, agg["overall"], agg["by_category"], per_note)

    results_path = Path(Config.EVAL_RESULTS_PATH)
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n  Results written to {results_path}")

    print_summary(report)


if __name__ == "__main__":
    main()
