"""Parameterized screen executor.

The native screen was produced by an uncommitted private driver. Its preserved
bytes hash to
``486e15ea2bb9824cf821215e79ea42991384ae246a0a270e1a9ab608a61d3167``.
This module is a later sanitized reconstruction: paths and the code head are
arguments, and it does not embed a private absolute path. Importing or replaying
it does not prove that the historical process used this source.
"""
from __future__ import annotations

import argparse
import json
import traceback
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image

from evaluation.ocr_c2.budget import Ledger
from evaluation.ocr_c2.controller import acquire_lock, step, write_checkpoint
from evaluation.ocr_c2.holdout import cohort_for, refuse_tuning_ids
from evaluation.ocr_c2.identity import request_identity
from evaluation.ocr_c2.metrics import (
    micro_rate, normalize_recognition, normalized_errors, occurrence_case, strict_case,
)
from evaluation.ocr_c2.native import build_native_payload, control_call
from evaluation.ocr_c2.protocol import CAMPAIGN_ID, load_protocol
from evaluation.ocr_c2.replay import replay_case
from evaluation.ocr_c2.runner import run_page
from evaluation.pr10_autoresearch import AMR_INTAKE, _amr_case, _rx_case, _rx_labels
from evaluation.pr10_replay import reference_text
from evaluation.public_amr_benchmark import sha
from services.inference_pipeline import get_installed_model_digest
from services.multimodal_service import glm_ocr_infer

QUEUE = ("B8192", "N1", "N3", "N4", "Blegacy")


def next_request_prefix(prefix: str, existing: set[str]) -> str:
    """Avoid a request id the ledger already charged, including a crash charge."""
    attempt = 2
    chosen = prefix
    while f"{chosen}-0" in existing:
        chosen = f"{prefix}-r{attempt}"
        attempt += 1
    return chosen


def log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(message.rstrip() + "\n")
    print(message, flush=True)


def rx_sha(name: str) -> str:
    from evaluation.ocr_c2.protocol import partition
    for row in partition()["rxhandbd"]["train"]:
        if row["image_name"] == name:
            return row["original_sha256"]
    raise ValueError("OCR_C2_RX_SOURCE")


def load_case(dataset: str, ident: str):
    if dataset == "amr":
        pages, _text, reference_sha = _amr_case(json.loads(AMR_INTAKE.read_text()), ident)
        return pages, reference_sha
    pages, _text, reference_sha = _rx_case(ident, _rx_labels(), rx_sha(ident))
    return pages, reference_sha


def native_transport(digest: str, parent: str | None):
    def transport(prepared: bytes, candidate: str, allowed: float) -> dict:
        payload = build_native_payload(prepared, candidate, parent=parent)
        request = urllib.request.Request(
            "http://127.0.0.1:11434/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=max(1.0, allowed)) as response:
            body = json.loads(response.read().decode("utf-8"))
        if not isinstance(body, dict):
            return body
        body["model_digest"] = digest
        if body.get("elapsed_seconds") is None and isinstance(body.get("total_duration"), (int, float)):
            body["elapsed_seconds"] = body["total_duration"] / 1e9
        return body
    return transport


def control_response(result: dict, digest: str) -> dict:
    """Map a frozen control result without inventing a clean stop."""
    completed = result.get("status") == "completed"
    text = result.get("transcribed_text") if completed else ""
    if not isinstance(text, str):
        text = ""
    reason = result.get("done_reason")
    done = result.get("done") is True and isinstance(reason, str)
    elapsed = None
    if isinstance(result.get("total_duration"), (int, float)):
        elapsed = result["total_duration"] / 1e9
    return {
        "model": "glm-ocr:q8_0",
        "response": text if done else "",
        "done": done,
        "done_reason": reason if isinstance(reason, str) else None,
        "elapsed_seconds": elapsed,
        "model_digest": digest,
        "control_status": result.get("status"),
    }


def control_transport(digest: str):
    def transport(prepared: bytes, candidate: str, allowed: float) -> dict:
        del allowed
        result = control_call(candidate, prepared, page_number=1, infer=glm_ocr_infer)
        return control_response(result, digest)
    return transport


def accept_saved_case(saved: dict, identity: dict, reference_sha: str, reference_bytes: bytes) -> None:
    stored = saved.get("identity") if isinstance(saved.get("identity"), dict) else {}
    if saved.get("reference_sha256") != reference_sha:
        raise ValueError("OCR_C2_STALE_EVIDENCE")
    for key in ("experiment_fingerprint", "inference_sha256", "scoring_sha256"):
        if stored.get(key) != identity.get(key):
            raise ValueError("OCR_C2_STALE_EVIDENCE")
    if identity.get("control_sha256") is not None and stored.get("control_sha256") != identity.get("control_sha256"):
        raise ValueError("OCR_C2_STALE_EVIDENCE")
    if saved.get("status") == "scored":
        replay_case(saved, reference_bytes)
    elif saved.get("status") != "incomplete":
        raise ValueError("OCR_C2_STALE_EVIDENCE")


def accept_saved_page(saved: dict, identity: dict, source_sha: str, reference_sha: str) -> None:
    regions = saved.get("regions")
    if saved.get("status") not in {"scored", "incomplete"}:
        raise ValueError("OCR_C2_STALE_EVIDENCE")
    if saved.get("source_sha256") != source_sha or saved.get("reference_sha256") != reference_sha:
        raise ValueError("OCR_C2_STALE_EVIDENCE")
    if saved.get("experiment_fingerprint") != identity.get("experiment_fingerprint"):
        raise ValueError("OCR_C2_STALE_EVIDENCE")
    if saved.get("scoring_sha256") != identity.get("scoring_sha256"):
        raise ValueError("OCR_C2_STALE_EVIDENCE")
    if not isinstance(regions, list) or any(not isinstance(region, dict) or "crop_sha256" not in region for region in regions):
        raise ValueError("OCR_C2_STALE_EVIDENCE")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)


def run_one_page(image_bytes: bytes, candidate: str, transport, ledger: Ledger, request_prefix: str, digest: str, parent: str | None) -> dict:
    before = ledger.charged()
    image = Image.open(BytesIO(image_bytes))
    image.load()
    try:
        result = run_page(
            image, candidate, transport, ledger, request_prefix, digest, parent=parent,
        )
    except Exception:
        ledger.recover_crashes()
        raise
    result["page_seconds"] = ledger.charged() - before
    return result


def score_document(pages: list[dict], reference_sha: str, reference_bytes: bytes, identity: dict) -> dict:
    completed = all(page.get("completed") for page in pages)
    prediction = "\n".join(page.get("prediction") or "" for page in pages)
    status = "scored" if completed and prediction.strip() else "incomplete"
    case = {
        "status": status,
        "prediction": prediction,
        "reference_sha256": reference_sha,
        "normalized_prediction": None,
        "metrics": None,
        "page_seconds": [page.get("page_seconds") for page in pages],
        "generation_limit": any(
            region.get("status") == "generation_limit"
            for page in pages for region in page.get("regions", [])
        ),
        "identity": identity,
    }
    if status == "scored":
        reference = reference_text(reference_bytes)
        case["metrics"] = strict_case(reference, prediction)
        aligned = occurrence_case(reference, prediction)
        case.update({
            "occurrence_hits": aligned["occurrence_hits"],
            "occurrence_total": aligned["occurrence_total"],
            "occurrence_false_positives": aligned["occurrence_false_positives"],
            "normalized_prediction": normalize_recognition(prediction),
            "normalized": normalized_errors(reference, prediction),
        })
        replay_case(case, reference_bytes)
    return case


def document_reference(dataset: str, ident: str) -> bytes:
    if dataset == "amr":
        selection = json.loads(AMR_INTAKE.read_text())
        record = next(row for row in selection["all_records"] if row["id"] == ident)
        return (Path(selection["source_root"]) / record["truth"]).read_bytes()
    return _rx_labels()[ident].encode("utf-8")


def run_candidate(root: Path, candidate: str, digest: str, ledger: Ledger, record) -> str:
    protocol = load_protocol()
    role = protocol["candidates"][candidate]["role"]
    parent = None
    for dataset in ("amr", "rx"):
        ids = cohort_for("screen", dataset)
        refuse_tuning_ids(ids)
        identity = request_identity(candidate, dataset, ids, digest, parent=parent)
        for ident in ids:
            case_path = root / "screen" / candidate / dataset / f"{ident}.json"
            if ledger.exploration_blocked() and not case_path.exists():
                return "budget_blocked"
            pages, reference_sha = load_case(dataset, ident)
            reference_bytes = document_reference(dataset, ident)
            if sha(reference_bytes) != reference_sha:
                raise ValueError("OCR_C2_REFERENCE_HASH")
            if case_path.exists():
                accept_saved_case(json.loads(case_path.read_text()), identity, reference_sha, reference_bytes)
                record(f"skip {candidate} {dataset} {ident}")
                continue
            transport = control_transport(digest) if role == "control" else native_transport(digest, parent)
            page_results = []
            for index, raw in enumerate(pages):
                stored = root / "screen" / candidate / dataset / f"{ident}-p{index}.json"
                source_sha = sha(raw)
                if stored.exists():
                    saved = json.loads(stored.read_text())
                    accept_saved_page(saved, identity, source_sha, reference_sha)
                    page_results.append(saved)
                    continue
                prefix = next_request_prefix(
                    f"{candidate}-{dataset}-{ident}-p{index}",
                    {row["request_id"] for row in ledger.rows()},
                )
                try:
                    result = run_one_page(raw, candidate, transport, ledger, prefix, digest, parent)
                except (urllib.error.URLError, TimeoutError, ConnectionError):
                    ledger.recover_crashes()
                    record(f"transport_error {candidate} {dataset} {ident} p{index} charged={ledger.charged():.1f}")
                    return "budget_blocked" if ledger.exploration_blocked() else "integrity_blocked"
                write_json(stored, {
                    "status": result["status"],
                    "completed": result["completed"],
                    "prediction": result["prediction"],
                    "regions": [
                        {
                            "order": region["order"],
                            "status": region["status"],
                            "crop_sha256": region.get("crop_sha256"),
                        }
                        for region in result["regions"]
                    ],
                    "page_seconds": result["page_seconds"],
                    "source_sha256": source_sha,
                    "reference_sha256": reference_sha,
                    "experiment_fingerprint": identity["experiment_fingerprint"],
                    "scoring_sha256": identity["scoring_sha256"],
                })
                page_results.append(json.loads(stored.read_text()))
                if result["status"] == "budget_blocked":
                    record(f"budget {candidate} {dataset} {ident} charged={ledger.charged():.1f}")
                    return "budget_blocked"
            case = score_document(page_results, reference_sha, reference_bytes, identity)
            write_json(case_path, case)
            record(f"done {candidate} {dataset} {ident} {case['status']} charged={ledger.charged():.1f}")
    return "screen_done"


def summarize(root: Path, candidate: str, record) -> None:
    rows = []
    for dataset in ("amr", "rx"):
        ids = cohort_for("screen", dataset)
        folder = root / "screen" / candidate / dataset
        files = [folder / f"{ident}.json" for ident in ids]
        if not all(path.exists() for path in files):
            return
        rows.append((dataset, [json.loads(path.read_text()) for path in files]))
    summary = {"candidate": candidate, "datasets": {}}
    for dataset, cases in rows:
        scored = [case for case in cases if case["status"] == "scored" and case.get("metrics")]
        summary["datasets"][dataset] = {
            "attempted": len(cases),
            "scored": len(scored),
            "cer": micro_rate(
                [case["metrics"]["character_distance"] for case in scored],
                [case["metrics"]["ref_chars"] for case in scored],
            ),
            "normalized_cer": micro_rate(
                [case["normalized"]["char_distance"] for case in scored if case["normalized"]["char_distance"] is not None],
                [case["normalized"]["ref_chars"] for case in scored if case["normalized"]["char_distance"] is not None],
            ),
        }
    write_json(root / "screen" / candidate / "summary.json", summary)
    record(f"summary {candidate} {json.dumps(summary['datasets'])}")


def run_screen(root: Path, head: str, expected_digest_prefix: str) -> int:
    digest = get_installed_model_digest("glm-ocr:q8_0")
    if not str(digest).startswith(expected_digest_prefix):
        log(root / "screening.log", f"digest_mismatch {digest}")
        return 2
    record = lambda message: log(root / "screening.log", message)
    lock = acquire_lock(root / "campaign.lock")
    try:
        state = step(step("preflight", "preflight_ok"), "review_passed")
        ledger = Ledger(root / "ledger.jsonl")
        ledger.recover_crashes()
        amr = cohort_for("screen", "amr")
        rx = cohort_for("screen", "rx")
        refuse_tuning_ids(amr + rx)
        fingerprint = request_identity("B8192", "amr", amr, digest)["experiment_fingerprint"]
        write_checkpoint(root / "checkpoint.json", {
            "campaign_id": CAMPAIGN_ID,
            "state": state,
            "config_fingerprint": fingerprint,
            "budget_seconds": ledger.charged(),
            "stop_reason": None,
            "process_started": True,
            "head": head,
            "model_digest": digest,
        })
        record(f"screening_start amr={len(amr)} rx={len(rx)} charged={ledger.charged():.1f}")
        queue = list(QUEUE)
        index = 0
        while index < len(queue):
            candidate = queue[index]
            index += 1
            if ledger.exploration_blocked():
                state = step(state, "budget_blocked")
                break
            outcome = run_candidate(root, candidate, digest, ledger, record)
            if outcome != "screen_done":
                state = step(state, outcome)
                break
            summarize(root, candidate, record)
            if candidate == "N1":
                limited = False
                for dataset in ("amr", "rx"):
                    for ident in cohort_for("screen", dataset):
                        case_file = root / "screen" / "N1" / dataset / f"{ident}.json"
                        if case_file.exists() and json.loads(case_file.read_text()).get("generation_limit"):
                            limited = True
                if limited and "N2" not in queue:
                    queue.insert(index, "N2")
                    record("n2_required generation_limit")
        else:
            state = step(state, "screen_done")
        write_checkpoint(root / "checkpoint.json", {
            "campaign_id": CAMPAIGN_ID,
            "state": state,
            "config_fingerprint": fingerprint,
            "budget_seconds": ledger.charged(),
            "stop_reason": None if state == "confirming" else state,
            "process_started": True,
            "head": head,
            "model_digest": digest,
        })
        record(f"screening_stop state={state} charged={ledger.charged():.1f}")
        return 0
    except Exception:
        traceback.print_exc()
        record("screening_crashed")
        return 1
    finally:
        lock.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--expected-digest-prefix", default="6e5935a916fc")
    args = parser.parse_args(argv)
    return run_screen(args.private_root, args.head, args.expected_digest_prefix)


if __name__ == "__main__":
    raise SystemExit(main())
