import os
import json
from pathlib import Path
from flask import Blueprint, jsonify, request
from evaluation.strict_evaluator import evaluate_corpus_strictly
from extractors.pipeline import run_pipeline

bp = Blueprint("eval_runs", __name__)

EVAL_ARTIFACTS_DIR = Path(__file__).parent.parent.parent / "artifacts" / "evaluation"


@bp.get("/api/evaluation/runs")
def list_eval_runs():
    runs = []
    if EVAL_ARTIFACTS_DIR.exists():
        for run_dir in sorted(EVAL_ARTIFACTS_DIR.iterdir(), reverse=True):
            if run_dir.is_dir():
                meta_path = run_dir / "run_metadata.json"
                summary_path = run_dir / "summary_metrics.json"
                if meta_path.exists() and summary_path.exists():
                    try:
                        with open(meta_path) as f:
                            meta = json.load(f)
                        with open(summary_path) as f:
                            summary = json.load(f)
                        runs.append({
                            "run_id": meta.get("run_id", run_dir.name),
                            "evaluator": meta.get("evaluator", "strict_multiset_v2"),
                            "started_at": meta.get("started_at"),
                            "finished_at": meta.get("finished_at"),
                            "note_count": meta.get("note_count", 20),
                            "summary": summary,
                        })
                    except Exception:
                        pass

    # Include legacy baseline if available
    legacy_path = Path(__file__).parent.parent / "evaluation" / "results.json"
    if legacy_path.exists():
        try:
            with open(legacy_path) as f:
                leg = json.load(f)
            by_cat = leg.get("by_category", {})
            runs.append({
                "run_id": "legacy_baseline_v1",
                "evaluator": "legacy_relaxed_v1",
                "started_at": leg.get("run_at") or leg.get("timestamp"),
                "note_count": len(leg.get("per_note", [])) or 20,
                "is_legacy_baseline": True,
                "summary": {
                    "overall": leg.get("overall", {"f1": 0.6549, "precision": 0.768, "recall": 0.5709}),
                    "by_category": by_cat,
                    "medications": by_cat.get("medications", {}),
                    "vitals": by_cat.get("vitals", {}),
                    "instructions": by_cat.get("instructions", {}),
                    "metadata": by_cat.get("metadata", {}),
                }
            })
        except Exception:
            pass

    return jsonify(runs)


@bp.get("/api/evaluation/runs/<string:run_id>")
def get_eval_run_detail(run_id: str):
    run_dir = EVAL_ARTIFACTS_DIR / run_id
    if not run_dir.exists() or not run_dir.is_dir():
        return jsonify({"error": "Evaluation run not found", "code": "NOT_FOUND"}), 404

    try:
        with open(run_dir / "run_metadata.json") as f:
            meta = json.load(f)
        with open(run_dir / "summary_metrics.json") as f:
            summary = json.load(f)
        with open(run_dir / "case_results.json") as f:
            cases = json.load(f)
        with open(run_dir / "manifest.json") as f:
            manifest = json.load(f)

        return jsonify({
            "metadata": meta,
            "summary": summary,
            "cases": cases,
            "manifest": manifest,
        })
    except Exception as e:
        return jsonify({"error": f"Failed reading run artifacts: {str(e)}", "code": "CORRUPTED_RUN"}), 500


@bp.post("/api/evaluation/runs")
def trigger_eval_run():
    notes_dir = Path(__file__).parent.parent.parent / "data" / "eval" / "notes"
    labels_dir = Path(__file__).parent.parent.parent / "data" / "eval" / "labels"

    pairs = []
    for n_path in sorted(notes_dir.glob("*.txt")):
        l_path = labels_dir / (n_path.stem + ".json")
        if l_path.exists():
            with open(n_path) as f:
                txt = f.read()
            with open(l_path) as f:
                lbl = json.load(f)
            pairs.append((n_path.stem, txt, lbl))

    bundle = evaluate_corpus_strictly(
        notes_and_labels=pairs,
        pipeline_fn=run_pipeline,
        output_dir=str(EVAL_ARTIFACTS_DIR),
    )

    return jsonify({
        "run_id": bundle["run_id"],
        "evaluator_version": bundle["evaluator_version"],
        "summary": bundle["summary"],
    }), 201
