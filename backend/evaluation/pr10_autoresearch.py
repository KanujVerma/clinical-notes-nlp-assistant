"""Resumable PR #10 GLM-OCR experiments. One case per checkpoint.

Private predictions stay under artifacts/handwriting-private/pr10-autoresearch/.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from evaluation.pr10_candidate import (  # noqa: E402
    CANDIDATES, CONTEXT, GLM_OCR_SYSTEM, GLM_OCR_USER, historical_specs,
    postprocess, prompt_for, render_regions,
)
from evaluation.pr10_identity import (  # noqa: E402
    IDENTITY_VERSION, CheckpointRejected, LegacyCheckpoint, assess_reuse, fingerprint,
)
from evaluation.pr10_replay import align_critical, critical_false_positives, micro_summary  # noqa: E402
from evaluation.public_amr_benchmark import score, sha  # noqa: E402
from services.inference_pipeline import get_installed_model_digest  # noqa: E402
from services.multimodal_service import glm_ocr_infer  # noqa: E402

MANIFEST = ROOT / "docs" / "validation" / "pr10_partition_manifest.json"
TREND = ROOT / "docs" / "validation" / "pr10_run_trend.tsv"
PRIVATE = ROOT / "artifacts" / "handwriting-private" / "pr10-autoresearch"
MODEL = "glm-ocr:q8_0"
AMR_INTAKE = ROOT / "data" / "handwriting-private" / "amr-intake" / "selection.json"
RX_TRAIN_CSV = ROOT / "data" / "handwriting-private" / "rxhandbd-v3" / "RxHandBD-ML" / "Train_Label.csv"
RX_TRAIN_DIR = ROOT / "data" / "handwriting-private" / "rxhandbd-v3" / "RxHandBD-ML" / "Train_Set"


def screening_selection(manifest: dict) -> dict:
    """Fixed screen chosen from partition roles only, never from predictions."""
    by_group: dict[str, str] = {}
    for row in manifest["amr"]["development"]:
        current = by_group.get(row["writer_group"])
        if current is None or row["id"] < current:
            by_group[row["writer_group"]] = row["id"]
    amr_ids = [by_group[group] for group in sorted(by_group)]
    if len(amr_ids) != 8:
        raise ValueError("PR10_SCREEN_AMR_COUNT")
    rx = [row["image_name"] for row in manifest["rxhandbd"]["train"]
          if row["role"] == "development"][:64]
    if len(rx) != 64:
        raise ValueError("PR10_SCREEN_RX_COUNT")
    holdout = {row["id"] for row in manifest["amr"]["untouched_holdout"]}
    if set(amr_ids) & holdout:
        raise ValueError("PR10_SCREEN_TOUCHED_HOLDOUT")
    untouched = {row["image_name"] for row in manifest["rxhandbd"]["official_test"]
                 if row["role"] == "untouched_official_test"}
    if set(rx) & untouched:
        raise ValueError("PR10_SCREEN_TOUCHED_RX_TEST")
    return {"amr_ids": amr_ids, "rx_image_names": rx,
            "rule": "one_lowest_id_per_development_writer_group_and_first_64_hash_ranked_train"}


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def _amr_case(selection: dict, ident: str) -> tuple[list[bytes], str, str]:
    record = next(row for row in selection["all_records"] if row["id"] == ident)
    root = Path(selection["source_root"])
    pages = []
    for page in record["pages"]:
        raw = (root / page["path"]).read_bytes()
        if sha(raw) != page["sha256"]:
            raise ValueError("PR10_AMR_SOURCE_HASH")
        pages.append(raw)
    truth = (root / record["truth"]).read_bytes()
    if sha(truth) != record["truth_sha256"]:
        raise ValueError("PR10_AMR_GOLD_HASH")
    return pages, truth.decode("utf-8-sig"), record["truth_sha256"]


def _rx_labels() -> dict[str, str]:
    import csv
    labels = {}
    with RX_TRAIN_CSV.open(newline="") as handle:
        for row in csv.DictReader(handle):
            labels[row["Images"].strip()] = row["Text"]
    return labels


def _rx_case(name: str, labels: dict[str, str], expected_sha: str) -> tuple[list[bytes], str, str]:
    raw = (RX_TRAIN_DIR / name).read_bytes()
    digest = sha(raw)
    if digest != expected_sha:
        raise ValueError("PR10_RX_SOURCE_HASH")
    return [raw], labels[name], sha(labels[name].encode("utf-8"))


def _predict(candidate: str, pages: list[bytes]) -> tuple[str | None, int, str]:
    prediction, latency, status, _passes = predict_spec(historical_specs()[candidate], pages)
    return prediction, latency, status


def predict_spec(spec: dict, pages: list[bytes]) -> tuple[str | None, int, str, int]:
    started = time.perf_counter()
    system, user_template = prompt_for(spec)
    frozen = spec["prompt"] == "frozen"
    parts = []
    for page_number, original in enumerate(pages, start=1):
        regions = render_regions(spec, original)
        for region_number, transformed in enumerate(regions, start=1):
            if len(transformed) > 10 * 1024 * 1024:
                elapsed = max(0, int((time.perf_counter() - started) * 1000))
                return None, elapsed, "transform_too_large", 1
            label = page_number if len(regions) == 1 else region_number
            user = user_template.format(page_number=label)
            result = glm_ocr_infer(
                transformed, page_number=label, num_ctx=spec.get("num_ctx"),
                system_prompt=None if frozen else system,
                user_prompt=None if frozen else user,
            )
            if result.get("status") != "completed" or not isinstance(result.get("transcribed_text"), str):
                elapsed = max(0, int((time.perf_counter() - started) * 1000))
                return None, elapsed, result.get("error_code") or "glm_failed", 1
            parts.append(result["transcribed_text"])
    text = postprocess(spec, "\n".join(parts))
    passes = 1
    if spec.get("second_pass") and len(text.strip()) < 12:
        passes = 2
        retry = []
        for page_number, original in enumerate(pages, start=1):
            for region_number, transformed in enumerate(render_regions(spec, original), start=1):
                label = page_number if region_number == 1 else region_number
                user = user_template.format(page_number=label)
                result = glm_ocr_infer(
                    transformed, page_number=label, num_ctx=spec.get("num_ctx"),
                    system_prompt=None if frozen else system,
                    user_prompt=None if frozen else user,
                )
                if result.get("status") != "completed" or not isinstance(result.get("transcribed_text"), str):
                    elapsed = max(0, int((time.perf_counter() - started) * 1000))
                    return None, elapsed, result.get("error_code") or "glm_failed", passes
                retry.append(result["transcribed_text"])
        retried = postprocess(spec, "\n".join(retry))
        if len(retried.strip()) > len(text.strip()):
            text = retried
    elapsed = max(0, int((time.perf_counter() - started) * 1000))
    return text or "", elapsed, completed_status(text), passes


def work_items(manifest: dict, stage: str, dataset: str) -> list[str]:
    screen = screening_selection(manifest)
    if stage == "screen" and dataset == "amr":
        return screen["amr_ids"]
    if stage == "screen" and dataset == "rx":
        return screen["rx_image_names"]
    if stage == "confirm" and dataset == "amr":
        return [row["id"] for row in manifest["amr"]["development"]]
    if stage == "confirm" and dataset == "rx":
        names = [row["image_name"] for row in manifest["rxhandbd"]["train"]
                 if row["role"] == "development"]
        if len(names) < 256:
            raise ValueError("PR10_CONFIRM_RX_COUNT")
        return names[:256]
    raise ValueError("PR10_UNKNOWN_SPLIT")


def run_screen(candidate: str, dataset: str, limit: int | None) -> dict:
    if candidate not in CANDIDATES:
        raise ValueError("PR10_UNKNOWN_CANDIDATE")
    return run_spec(historical_specs()[candidate], "screen", dataset, limit)


def completed_status(text: str | None) -> str:
    if not isinstance(text, str) or not text.strip():
        return "empty_transcription"
    return "scored"


def _existing_cases(out: Path, identifiers: list[str]) -> dict[str, dict]:
    existing = {}
    expected = set(identifiers)
    for path in out.glob("*.json"):
        if path.name == "summary.json":
            continue
        if path.stem not in expected:
            raise CheckpointRejected("extra")
        existing[path.stem] = json.loads(path.read_text())
    return existing


def run_spec(spec: dict, stage: str, dataset: str, limit: int | None) -> dict:
    candidate = spec["name"]
    manifest_bytes = MANIFEST.read_bytes()
    manifest = json.loads(manifest_bytes)
    screen = screening_selection(manifest)
    identifiers = work_items(manifest, stage, dataset)
    if limit is not None:
        identifiers = identifiers[:limit]
    out = PRIVATE / stage / candidate / dataset
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "summary.json"
    existing = _existing_cases(out, identifiers)
    if any(case.get("identity_version") != IDENTITY_VERSION for case in existing.values()):
        raise LegacyCheckpoint(f"legacy_unverified {candidate} {stage} {dataset}")
    digest_before = get_installed_model_digest(MODEL)
    adapter = Path(glm_ocr_infer.__code__.co_filename).read_text()
    fragments = [
        "You are an accurate visual OCR document transcription model (GLM-OCR). ",
        "Transcribe all text from the image accurately into JSON format with keys: ",
        "'text' (full transcribed text string of all lines), ",
        "'boxes' (list of {text, bbox: [x0, y0, x1, y1]}), and ",
        "'confidence' (number between 0 and 1). ",
        "Ensure all document lines are included in the 'text' field.",
        GLM_OCR_USER,
    ]
    if any(fragment not in adapter for fragment in fragments):
        raise ValueError("PR10_PROMPT_DRIFT")
    system, user = prompt_for(spec)
    prompt_sha = sha((system + "\n" + user).encode())
    spec_sha = sha(json.dumps(spec, sort_keys=True).encode())
    experiment_fingerprint = fingerprint({
        "identity_version": IDENTITY_VERSION,
        "manifest_sha256": sha(manifest_bytes),
        "dataset": dataset,
        "stage": stage,
        "selection_policy": screen["rule"],
        "case_ids_sha256": sha("\n".join(identifiers).encode()),
        "candidate": candidate,
        "parent": spec.get("parent"),
        "model": MODEL,
        "model_digest": digest_before,
        "num_ctx": spec.get("num_ctx"),
        "prompt_sha256": prompt_sha,
        "spec_sha256": spec_sha,
    })
    verdict = assess_reuse(existing, identifiers, experiment_fingerprint)
    if verdict == "legacy_unverified":
        raise LegacyCheckpoint(f"legacy_unverified {candidate} {stage} {dataset}")
    if verdict in {"fingerprint_mismatch", "invalid", "extra", "duplicate_expected"}:
        raise CheckpointRejected(f"{verdict} {candidate} {stage} {dataset}")
    if verdict == "reusable":
        cases = [existing[ident] for ident in identifiers]
        recomputed = micro_summary(cases)
        summary = {
            "candidate": candidate, "stage": stage, "dataset": dataset, "model": MODEL,
            "model_digest": digest_before, "prompt_sha256": prompt_sha,
            "spec_sha256": spec_sha, "experiment_fingerprint": experiment_fingerprint,
            "identity_version": IDENTITY_VERSION, "num_ctx": spec.get("num_ctx"),
            "parent": spec.get("parent"), "family": spec.get("family"),
            "hypothesis": spec.get("hypothesis"), "screen_rule": screen["rule"],
            **recomputed,
        }
        _write(summary_path, summary)
        return summary
    selection = json.loads(AMR_INTAKE.read_text()) if dataset == "amr" else None
    labels = _rx_labels() if dataset == "rx" else None
    expected = None
    if dataset == "rx":
        expected = {row["image_name"]: row["original_sha256"]
                    for row in manifest["rxhandbd"]["train"]}
    for ident in identifiers:
        destination = out / f"{ident}.json"
        if destination.exists():
            continue
        if dataset == "amr":
            pages, reference, reference_sha = _amr_case(selection, ident)
        else:
            pages, reference, reference_sha = _rx_case(ident, labels, expected[ident])
        prediction, latency, status, passes = predict_spec(spec, pages)
        payload = {
            "id": ident, "dataset": dataset, "candidate": candidate, "stage": stage,
            "status": status, "model": MODEL, "model_digest": digest_before,
            "prompt_sha256": prompt_sha, "spec_sha256": spec_sha,
            "reference_sha256": reference_sha, "latency_ms": latency,
            "passes": passes, "prediction": prediction,
            "completed_utc": datetime.now(timezone.utc).isoformat(),
            "identity_version": IDENTITY_VERSION,
            "experiment_fingerprint": experiment_fingerprint,
        }
        if status == "scored" and isinstance(prediction, str) and prediction.strip():
            aligned = align_critical(reference, prediction)
            payload["metrics"] = score(reference, prediction)
            payload["critical_false_positives"] = critical_false_positives(reference, prediction)
            payload["unique_unmatched_critical_tokens"] = payload["critical_false_positives"]
            payload["occurrence_hits"] = aligned["occurrence_hits"]
            payload["occurrence_total"] = aligned["occurrence_total"]
            payload["occurrence_false_positives"] = aligned["occurrence_false_positives"]
        _write(destination, payload)
        print(f"PR10_CASE {stage} {candidate} {dataset} {ident} {status} {latency}ms", flush=True)
        _write(PRIVATE / "run_state.json", {
            "status": "running", "stage": stage, "candidate": candidate,
            "dataset": dataset, "hypothesis": spec.get("hypothesis"),
            "last_case": ident, "updated_utc": datetime.now(timezone.utc).isoformat(),
        })
    digest_after = get_installed_model_digest(MODEL)
    if digest_after != digest_before:
        raise ValueError("PR10_MODEL_DIGEST_CHANGED")
    cases = [json.loads((out / f"{ident}.json").read_text()) for ident in identifiers]
    recomputed = micro_summary(cases)
    summary = {
        "candidate": candidate, "stage": stage, "dataset": dataset, "model": MODEL,
        "model_digest": digest_before, "prompt_sha256": prompt_sha,
        "spec_sha256": spec_sha, "experiment_fingerprint": experiment_fingerprint,
        "identity_version": IDENTITY_VERSION, "num_ctx": spec.get("num_ctx"),
        "parent": spec.get("parent"), "family": spec.get("family"),
        "hypothesis": spec.get("hypothesis"), "screen_rule": screen["rule"],
        **recomputed,
    }
    if micro_summary(cases) != recomputed:
        raise ValueError("PR10_SUMMARY_MISMATCH")
    _write(summary_path, summary)
    ledger = PRIVATE / "experiments.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a") as handle:
        handle.write(json.dumps({
            "utc": datetime.now(timezone.utc).isoformat(),
            "experiment_id": f"{stage}-{candidate}-{dataset}",
            "candidate": candidate, "stage": stage, "dataset": dataset, "status": "measured",
            **{key: summary[key] for key in (
                "scored", "attempted", "failed", "cer_micro", "wer_micro",
                "critical_recall", "critical_false_positives",
                "median_latency_ms", "p95_latency_ms", "model_digest")},
        }) + "\n")
    print("PR10_SUMMARY " + json.dumps(summary), flush=True)
    _append_trend(summary)
    return summary


def _append_trend(summary: dict) -> None:
    """One comparable row per finished run. Aggregates only, no transcriptions."""
    header = (
        "utc\texperiment\tdataset\tscored\tattempted\tfailed\t"
        "cer_micro\twer_micro\tcritical_recall\tcritical_false_positives\t"
        "median_latency_ms\tp95_latency_ms\tnum_ctx\n"
    )
    line = "\t".join(str(summary.get(key)) for key in (
        "candidate", "dataset", "scored", "attempted", "failed",
        "cer_micro", "wer_micro", "critical_recall", "critical_false_positives",
        "median_latency_ms", "p95_latency_ms", "num_ctx",
    ))
    row = datetime.now(timezone.utc).isoformat() + "\t" + line + "\n"
    if not TREND.exists():
        TREND.write_text(header)
    with TREND.open("a") as handle:
        handle.write(row)
    print(
        "PR10_TREND "
        f"{summary['candidate']} {summary['dataset']} "
        f"scored {summary['scored']}/{summary['attempted']} "
        f"CER {summary['cer_micro']} WER {summary['wer_micro']} "
        f"critical {summary['critical_recall']} "
        f"fp {summary['critical_false_positives']} "
        f"p95 {summary['p95_latency_ms']}ms",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", action="store_true")
    parser.add_argument("--candidate", default="jpeg_baseline")
    parser.add_argument("--dataset", choices=("amr", "rx"))
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.campaign:
        from evaluation.pr10_campaign import campaign
        return campaign()
    if args.dataset is None:
        raise SystemExit("PR10_DATASET_REQUIRED")
    run_screen(args.candidate, args.dataset, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
