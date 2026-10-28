import os
import json
import re
from pathlib import Path
from flask import Blueprint, jsonify, request
from evaluation.strict_evaluator import evaluate_corpus_strictly
from evaluation.dataset import load_curated_corpus
from extractors.pipeline import run_pipeline
from config import Config

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
    # Run IDs are single path components; reject URL path traversal.
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run_id):
        return jsonify({"error": "Invalid evaluation run ID", "code": "INVALID_RUN_ID"}), 422
    run_dir = (EVAL_ARTIFACTS_DIR / run_id).resolve()
    if run_dir.parent != EVAL_ARTIFACTS_DIR.resolve() or not run_dir.is_dir():
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
        return jsonify({"error": "Evaluation run artifacts could not be read", "code": "CORRUPTED_RUN"}), 500


@bp.post("/api/evaluation/runs")
def trigger_eval_run():
    # The hosted sandbox serves published immutable benchmark runs only.
    if Config.APP_MODE != "local":
        return jsonify({"error": "Benchmark execution is local-only", "code": "FEATURE_RESTRICTED"}), 403
    data_dir = Path(__file__).parent.parent.parent / "data" / "eval"
    try:
        pairs, dataset_manifest = load_curated_corpus(data_dir)
    except ValueError:
        return jsonify({"error": "Synthetic evaluation dataset failed integrity validation",
                        "code": "DATASET_INVALID"}), 422

    bundle = evaluate_corpus_strictly(
        notes_and_labels=pairs,
        pipeline_fn=run_pipeline,
        output_dir=str(EVAL_ARTIFACTS_DIR),
        dataset_manifest=dataset_manifest,
    )

    return jsonify({
        "run_id": bundle["run_id"],
        "evaluator_version": bundle["evaluator_version"],
        "summary": bundle["summary"],
    }), 201
