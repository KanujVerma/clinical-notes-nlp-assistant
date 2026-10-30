"""PR9: external handwritten AMR documents with PUBLISHER gold, not human adjudication.

Distinct from PR9 volunteer handwriting study. Sources, labels and raw predictions
are private/local only. No cloud/Ollama downloads, PHI claims or clinical validation.
CI uses only fabricated fixtures to test code integrity, not handwriting accuracy.
"""
from __future__ import annotations

import argparse
import base64
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from PIL import Image, ImageOps  # noqa: E402
from evaluation.handwriting_study import _source_sha  # noqa: E402
from evaluation.local_vision_eval import _score_text, pytesseract  # noqa: E402
from evaluation.run_paired_holdout import _preflight_models  # noqa: E402
from services.inference_pipeline import get_installed_model_digest  # noqa: E402
from services.multimodal_service import (  # noqa: E402
    DEFAULT_VL_MODEL, glm_ocr_infer, query_ollama_multimodal,
)

DATASET = "Nigeria-Health-data-OCR-pipeline/African-Medical-Records"
REVISION = "fa27d29dae4128ac45f035fd580928c84bec4e98"
VERSION = "public_amr_publisher_reference_v1"
ARMS = ("tesseract", "glm_ocr", "qwen3_vl_ocr")
PILOT_COUNT = 24
EXPECTED_RECORDS = 62
MAX_ORIGINAL_BYTES = 50 * 1024 * 1024
MAX_INPUT_BYTES = 10 * 1024 * 1024
ID = re.compile(r"AMR_\d{3}\Z")
CRITICAL = re.compile(
    r"(?<!\w)\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|mmhg|bpm|kg|cm|%)\b"
    r"|\b(?:prn|hold|stop|stopped|discontinue|discontinued|no|not)\b",
    re.IGNORECASE,
)
QWEN_SYSTEM = (
    "Transcribe the handwritten page exactly, without medical interpretation. "
    "Preserve words, line breaks, doses, decimals, numbers, units and negations. "
    "Return one JSON object containing a string field 'text'. "
    "Do not infer missing content or provide advice."
)
QWEN_USER = "Transcribe all visible handwriting on this page into JSON."


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def raw_json(data: object) -> bytes:
    return (json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def load(path: Path) -> dict:
    obj = json.loads(path.read_text("utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("AMR_EXPECTED_JSON_OBJECT")
    return obj


def check(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as f:
        f.write(data)


def safe(root: Path, rel: str, suffix: str) -> Path:
    check(isinstance(rel, str) and bool(rel) and "\\" not in rel
          and not rel.startswith("/") and ".." not in Path(rel).parts
          and Path(rel).suffix.lower() == suffix, "AMR_INVALID_FILE_PATH")
    path = (root.resolve() / rel).resolve()
    check(path.is_relative_to(root.resolve()) and path.is_file()
          and not (root / rel).is_symlink(), "AMR_MISSING_OR_ESCAPED_PATH")
    return path


def png(raw: bytes) -> None:
    check(0 < len(raw) <= MAX_ORIGINAL_BYTES, "AMR_SOURCE_IMAGE_OVERSIZE")
    with Image.open(io.BytesIO(raw)) as im:
        check(im.format == "PNG" and getattr(im, "n_frames", 1) == 1
              and 0 < im.width * im.height <= 100_000_000,
              "AMR_UNSUPPORTED_OR_OVERSIZED_SOURCE_IMAGE")
        im.verify()


def catalog(root: Path) -> tuple[list[dict], str]:
    """Original source images are never silently regenerated or edited."""
    metadata = safe(root, "metadata.csv", ".csv").read_bytes()
    rows = list(csv.DictReader(io.StringIO(metadata.decode("utf-8-sig"))))
    check(len(rows) == EXPECTED_RECORDS, "AMR_EXPECTED_62_PAIRS")
    ids, image_hashes = set(), set()
    records = []
    for row in rows:
        ident = row.get("pair_id", "")
        check(bool(ID.fullmatch(ident)) and ident not in ids, "AMR_DUPLICATE_CASE_ID")
        ids.add(ident)
        images = row.get("htr_file", "").split(";")
        check(1 <= len(images) <= 20 and str(len(images)) == row.get("num_pages"),
              "AMR_INCORRECT_MULTIPAGE_PAIRING")
        contributor = (row.get("contributor") or "").strip()
        check(bool(contributor), "AMR_CONTRIBUTOR_MISSING")
        pages = []
        for image_path in images:
            check(image_path.startswith("htr/"), "AMR_INCORRECT_IMAGE_FOLDER")
            contents = safe(root, image_path, ".png").read_bytes()
            png(contents)
            fingerprint = sha(contents)
            check(fingerprint not in image_hashes, "AMR_DUPLICATE_IMAGE_CONTENT")
            image_hashes.add(fingerprint)
            pages.append({"path": image_path, "sha256": fingerprint})
        truth_path = row.get("truth_file", "")
        check(truth_path.startswith("truth/"), "AMR_INVALID_TRUTH_FOLDER")
        truth = safe(root, truth_path, ".txt").read_bytes()
        check(0 < len(truth) <= 128 * 1024 and bool(truth.decode("utf-8-sig").strip()),
              "AMR_EMPTY_OR_INVALID_PUBLISHER_REFERENCE")
        records.append({"id": ident, "contributor": contributor, "pages": pages,
                        "truth": truth_path, "truth_sha256": sha(truth)})
    return sorted(records, key=lambda x: x["id"]), sha(metadata)


def pick(rows: list[dict], count: int) -> list[str]:
    check(12 <= count <= len(rows), "AMR_INVALID_PILOT_SIZE")
    by_group: dict[str, list[str]] = {}
    for r in rows:
        by_group.setdefault(r["contributor"], []).append(r["id"])
    for ids in by_group.values():
        ids.sort()
    selected = []
    while len(selected) < count:
        for contributor in sorted(by_group):
            if by_group[contributor] and len(selected) < count:
                selected.append(by_group[contributor].pop(0))
    return sorted(selected)


def scaffold(dataset_root: Path, study: Path, count: int = PILOT_COUNT) -> dict:
    check(not study.exists(), "AMR_INTAKE_ALREADY_EXISTS")
    rows, metadata_hash = catalog(dataset_root)
    selected = pick(rows, count)
    groups = {name: "writer_group_%02d" % (i + 1)
              for i, name in enumerate(sorted({r["contributor"] for r in rows}))}
    ledger = [{**{k: v for k, v in r.items() if k != "contributor"},
               "writer_group": groups[r["contributor"]]} for r in rows]
    manifest = {"schema": VERSION, "dataset": DATASET, "revision": REVISION,
                "license": "CC-BY-4.0", "source_root": str(dataset_root.resolve()),
                "metadata_sha256": metadata_hash, "all_records": ledger,
                "selected_ids": selected,
                "sampling_policy": "contributor_round_robin_then_source_id_v1",
                "gold_provenance": "publisher_reference_not_independent_adjudication",
                "handwriting_provenance": "publisher_claims_volunteer_produced"}
    review = {"schema": VERSION, "selection_sha256": sha(raw_json(manifest)),
              "reviewer_id": "",
              "instructions": ("Inspect every source page AND publisher transcript locally. "
                               "Set approved only after checking for real patient data and "
                               "identifiers. Exclude anything questionable. These checkboxes "
                               "cannot independently prove consent or handwriting origins."),
              "cases": [
                  {"id": i, "all_pages_and_transcript_reviewed": False,
                   "contains_real_patient_data": None,
                   "contains_identifiers": None, "decision": "unreviewed",
                   "exclusion_reason": None}
                  for i in selected]}
    study.mkdir(parents=True, exist_ok=False)
    write(study / "selection.json", raw_json(manifest))
    write(study / "privacy_review.json", raw_json(review))
    return {"status": "privacy_review_required_no_benchmark", "selected": count,
            "publisher_records": len(rows), "selected_ids": selected}


def review_cases(study: Path, selection: dict,
                 snapshot: bytes | None = None) -> dict[str, dict]:
    review = json.loads(snapshot) if snapshot is not None else load(study / "privacy_review.json")
    check(isinstance(review, dict), "AMR_PRIVACY_REVIEW_INVALID")
    check(review.get("schema") == VERSION and review.get("selection_sha256") ==
          sha((study / "selection.json").read_bytes())
          and isinstance(review.get("reviewer_id"), str)
          and bool(review["reviewer_id"].strip()) and len(review["reviewer_id"]) <= 80,
          "AMR_PRIVACY_REVIEW_NOT_SIGNED")
    cases = review.get("cases")
    check(isinstance(cases, list) and len(cases) == len(selection["selected_ids"]),
          "AMR_INCOMPLETE_PRIVACY_REVIEW")
    result = {}
    for c in cases:
        check(isinstance(c, dict) and c.get("id") in selection["selected_ids"]
              and c["id"] not in result and c.get("all_pages_and_transcript_reviewed") is True,
              "AMR_CASE_NOT_INDEPENDENTLY_PRIVACY_REVIEWED")
        if c.get("decision") == "approved":
            check(c.get("contains_real_patient_data") is False
                  and c.get("contains_identifiers") is False
                  and c.get("exclusion_reason") is None,
                  "AMR_PRIVACY_UNSAFE_APPROVAL")
        else:
            check(c.get("decision") == "exclude"
                  and isinstance(c.get("contains_real_patient_data"), bool)
                  and isinstance(c.get("contains_identifiers"), bool)
                  and c.get("exclusion_reason") in
                  ("possible_phi", "possible_identifiers",
                   "unreadable_or_mismatched_reference", "other_concern"),
                  "AMR_PRIVACY_EXCLUSION_REQUIRED")
        result[c["id"]] = c
    return result


def infer_image(original: bytes) -> bytes:
    """Deterministic, shared, non-destructive image conversion; freeze both hashes."""
    with Image.open(io.BytesIO(original)) as image:
        rgb = ImageOps.exif_transpose(image).convert("RGB")
        scale = min(1.0, 3000 / max(rgb.size),
                    math.sqrt(14_000_000 / (rgb.width * rgb.height)))
        if scale < 1:
            rgb = rgb.resize((max(1, int(rgb.width * scale)),
                              max(1, int(rgb.height * scale))), Image.Resampling.LANCZOS)
        f = io.BytesIO()
        rgb.save(f, format="JPEG", quality=85, subsampling=0, optimize=True)
        result = f.getvalue()
    check(0 < len(result) <= MAX_INPUT_BYTES, "AMR_INFERENCE_IMAGE_TOO_LARGE")
    return result


def source_hashes() -> dict:
    frozen = _source_sha()  # Includes frozen PR7/8 dependencies and lock metadata.
    new = "backend/evaluation/public_amr_benchmark.py"
    frozen[new] = sha((ROOT / new).read_bytes())
    return frozen


def seal(study: Path, out: Path) -> dict:
    check(not out.exists(), "AMR_SEAL_ALREADY_EXISTS")
    selection_bytes = (study / "selection.json").read_bytes()
    review_bytes = (study / "privacy_review.json").read_bytes()
    selection = json.loads(selection_bytes)
    check(isinstance(selection, dict), "AMR_SELECTION_INVALID")
    check(selection.get("schema") == VERSION and selection.get("dataset") == DATASET
          and selection.get("revision") == REVISION
          and selection.get("license") == "CC-BY-4.0"
          and selection.get("gold_provenance") ==
          "publisher_reference_not_independent_adjudication"
          and selection.get("handwriting_provenance") ==
          "publisher_claims_volunteer_produced",
          "AMR_UNRECOGNIZED_DATASET_PROVENANCE")
    current, metadata_hash = catalog(Path(selection["source_root"]))
    expected_ids = pick(current, len(selection["selected_ids"]))
    check(metadata_hash == selection["metadata_sha256"]
          and selection["selected_ids"] == expected_ids
          and selection.get("sampling_policy") == "contributor_round_robin_then_source_id_v1",
          "AMR_UPSTREAM_OR_SELECTION_CHANGED")
    expected_groups = {name: "writer_group_%02d" % (i + 1)
                       for i, name in enumerate(sorted({r["contributor"] for r in current}))}
    ledger = [{**{k: v for k, v in r.items() if k != "contributor"},
               "writer_group": expected_groups[r["contributor"]]} for r in current]
    check(selection["all_records"] == ledger, "AMR_UPSTREAM_BYTES_CHANGED")
    reviews = review_cases(study, selection, review_bytes)
    chosen = {r["id"]: r for r in ledger if r["id"] in expected_ids}
    approved = [i for i in expected_ids if reviews[i]["decision"] == "approved"]
    check(len(approved) >= 12
          and len({chosen[i]["writer_group"] for i in approved}) >= 3,
          "AMR_INSUFFICIENT_APPROVED_REAL_HANDWRITING")
    locked_sources = source_hashes()
    # Prepare raw bytes before creating any output.
    prepared = {}
    for ident in approved:
        entry = chosen[ident]
        pages = []
        for p in entry["pages"]:
            original = safe(Path(selection["source_root"]), p["path"], ".png").read_bytes()
            check(sha(original) == p["sha256"], "AMR_ORIGINAL_CHANGED")
            pages.append((original, infer_image(original)))
        truth = safe(Path(selection["source_root"]), entry["truth"], ".txt").read_bytes()
        check(sha(truth) == entry["truth_sha256"], "AMR_PUBLISHER_GOLD_CHANGED")
        prepared[ident] = pages, truth
    check(selection_bytes == (study / "selection.json").read_bytes()
          and review_bytes == (study / "privacy_review.json").read_bytes(),
          "AMR_INTAKE_CHANGED_DURING_SEAL")
    out.mkdir(parents=True, exist_ok=False)
    write(out / "selection.json", selection_bytes)
    write(out / "privacy_review.json", review_bytes)
    cases = []
    for ident in approved:
        entry = chosen[ident]
        pages, truth = prepared[ident]
        result_pages = []
        for number, (original, transformed) in enumerate(pages, 1):
            original_path = f"originals/{ident}_{number}.png"
            inference_path = f"images/{ident}_{number}.jpg"
            write(out / original_path, original)
            write(out / inference_path, transformed)
            result_pages.append({"original": original_path, "original_sha256": sha(original),
                                 "inference": inference_path,
                                 "inference_sha256": sha(transformed)})
        truth_path = f"publisher_truth/{ident}.txt"
        write(out / truth_path, truth)
        cases.append({"id": ident, "writer_group": entry["writer_group"],
                      "pages": result_pages, "reference": truth_path,
                      "reference_sha256": sha(truth)})
    manifest = {
        "schema": VERSION, "dataset": DATASET, "revision": REVISION,
        "total_upstream_records": EXPECTED_RECORDS, "selected_ids": expected_ids,
        "scored_ids": approved,
        "excluded_before_inference": [
            {"id": i, "reason": reviews[i]["exclusion_reason"]}
            for i in expected_ids if i not in approved],
        "cases": cases, "reference_source": "publisher_supplied_not_adjudicated",
        "no_own_human_annotations": True, "no_structured_entity_gold": True,
        "not_clinical_validation": True,
    }
    write(out / "scored_manifest.json", raw_json(manifest))
    seal_data = {
        "schema": VERSION, "status": "sealed_publisher_gold_privacy_review_attested",
        "selection_sha256": sha(selection_bytes), "review_sha256": sha(review_bytes),
        "manifest_sha256": sha((out / "scored_manifest.json").read_bytes()),
        "metadata_sha256": metadata_hash, "code_sha256": locked_sources,
        "arms": list(ARMS),
        "selected": len(expected_ids), "scored": len(approved),
        "excluded": len(expected_ids) - len(approved),
    }
    write(out / "study_seal.json", raw_json(seal_data))
    return {"status": "sealed_without_model_inference", "selected": len(expected_ids),
            "scored": len(approved), "excluded": len(expected_ids) - len(approved),
            "seal_sha256": sha((out / "study_seal.json").read_bytes())}


def verify(sealed: Path) -> tuple[dict, dict]:
    seal_data = load(sealed / "study_seal.json")
    selection = load(sealed / "selection.json")
    review = review_cases(sealed, selection)
    manifest = load(sealed / "scored_manifest.json")
    check(seal_data.get("schema") == VERSION and manifest.get("schema") == VERSION
          and selection.get("schema") == VERSION
          and selection.get("dataset") == DATASET and selection.get("revision") == REVISION
          and manifest.get("dataset") == DATASET and manifest.get("revision") == REVISION
          and seal_data.get("status") == "sealed_publisher_gold_privacy_review_attested"
          and seal_data.get("arms") == list(ARMS)
          and seal_data.get("code_sha256") == source_hashes()
          and seal_data.get("selection_sha256") ==
          sha((sealed / "selection.json").read_bytes())
          and seal_data.get("review_sha256") ==
          sha((sealed / "privacy_review.json").read_bytes())
          and seal_data.get("manifest_sha256") ==
          sha((sealed / "scored_manifest.json").read_bytes())
          and seal_data.get("metadata_sha256") == selection["metadata_sha256"],
          "AMR_SEAL_OR_CODE_CHANGED")
    chosen = {r["id"]: r for r in selection["all_records"]}
    ids = selection["selected_ids"]
    approved = [i for i in ids if review[i]["decision"] == "approved"]
    excluded = [{"id": i, "reason": review[i]["exclusion_reason"]}
                for i in ids if i not in approved]
    check(len(chosen) == EXPECTED_RECORDS
          and len(approved) >= 12
          and len({chosen[i]["writer_group"] for i in approved}) >= 3
          and seal_data["selected"] == len(ids)
          and seal_data["scored"] == len(approved)
          and seal_data["excluded"] == len(excluded)
          and manifest.get("total_upstream_records") == EXPECTED_RECORDS
          and manifest.get("selected_ids") == ids
          and manifest.get("scored_ids") == approved
          and manifest.get("excluded_before_inference") == excluded
          and manifest.get("reference_source") == "publisher_supplied_not_adjudicated"
          and manifest.get("no_own_human_annotations") is True
          and manifest.get("no_structured_entity_gold") is True
          and manifest.get("not_clinical_validation") is True
          and len(manifest["cases"]) == len(approved),
          "AMR_INVALID_SEALED_COHORT_OR_CLAIMS")
    for c, ident in zip(manifest["cases"], approved):
        entry = chosen[ident]
        check(c["id"] == ident and c["writer_group"] == entry["writer_group"]
              and len(c["pages"]) == len(entry["pages"])
              and c["reference"] == f"publisher_truth/{ident}.txt"
              and c["reference_sha256"] == entry["truth_sha256"],
              "AMR_PUBLISHER_GOLD_BINDING_MISMATCH")
        check(sha(safe(sealed, c["reference"], ".txt").read_bytes()) ==
              c["reference_sha256"], "AMR_PUBLISHER_GOLD_TAMPERED")
        for number, (page, upstream_page) in enumerate(zip(c["pages"], entry["pages"]), 1):
            check(page["original"] == f"originals/{ident}_{number}.png"
                  and page["inference"] == f"images/{ident}_{number}.jpg"
                  and page["original_sha256"] == upstream_page["sha256"],
                  "AMR_SOURCE_PAGE_IDENTITY_MISMATCH")
            original = safe(sealed, page["original"], ".png").read_bytes()
            inference = safe(sealed, page["inference"], ".jpg").read_bytes()
            check(sha(original) == page["original_sha256"]
                  and sha(inference) == page["inference_sha256"]
                  and sha(infer_image(original)) == page["inference_sha256"],
                  "AMR_SEALED_SOURCE_MODIFIED")
    return seal_data, manifest


def score(reference: str, hypothesis: str) -> dict:
    tokens = list(dict.fromkeys(m.group() for m in CRITICAL.finditer(reference)))
    return _score_text(reference, hypothesis, tokens)


def aggregates(cases: list[dict], arms: tuple[str, ...]) -> dict:
    output = {}
    for arm in arms:
        rows = [c["results"][arm] for c in cases]
        metrics = [r["metrics"] for r in rows]
        char_dist = sum(m["character_distance"] for m in metrics)
        word_dist = sum(m["word_distance"] for m in metrics)
        chars = sum(m["ref_chars"] for m in metrics)
        words = sum(m["ref_words"] for m in metrics)
        tokens = [x for m in metrics for x in m["critical_tokens"]]
        latencies = [r["latency_ms"] for r in rows]
        output[arm] = {
            "cases": len(rows), "char_distance": char_dist, "word_distance": word_dist,
            "reference_chars": chars, "reference_words": words,
            "cer_micro": char_dist / chars if chars else None,
            "wer_micro": word_dist / words if words else None,
            "critical_hit": sum(int(t["recognized"]) for t in tokens),
            "critical_total": len(tokens),
            "critical_recall": (sum(int(t["recognized"]) for t in tokens) / len(tokens)
                                if tokens else None),
            "median_case_latency_ms": statistics.median(latencies),
            "total_latency_ms": sum(latencies),
        }
    return output


def preflight(arms: tuple[str, ...]) -> dict[str, str]:
    check(bool(arms) and len(set(arms)) == len(arms) and
          all(a in ARMS for a in arms), "AMR_INVALID_MODEL_ARMS")
    if any(a != "tesseract" for a in arms):
        installed = _preflight_models()
    else:
        installed = {"tesseract": str(pytesseract.get_tesseract_version())}
    return {a: installed["qwen3_vl"] if a == "qwen3_vl_ocr" else installed[a]
            for a in arms}


def infer(arm: str, raw: bytes) -> str:
    if arm == "tesseract":
        with Image.open(io.BytesIO(raw)) as image:
            return pytesseract.image_to_string(image.convert("RGB"), config="--psm 6")
    if arm == "glm_ocr":
        res = glm_ocr_infer(raw)
        check(res.get("status") == "completed"
              and isinstance(res.get("transcribed_text"), str), "AMR_GLM_OCR_FAILED")
        return res["transcribed_text"]
    if arm == "qwen3_vl_ocr":
        res = query_ollama_multimodal(
            model=DEFAULT_VL_MODEL, system=QWEN_SYSTEM, prompt=QWEN_USER,
            images_b64=[base64.b64encode(raw).decode("ascii")])
        output = res.get("response")
        check(isinstance(output, str), "AMR_QWEN_OCR_FAILED")
        # Strict JSON response from local Ollama, without repurposing structured candidates.
        parsed = json.loads(output)
        check(isinstance(parsed, dict) and isinstance(parsed.get("text"), str),
              "AMR_QWEN_OCR_FAILED")
        return parsed["text"]
    raise ValueError("AMR_UNKNOWN_MODEL_ARM")


def execute(sealed: Path, out: Path, arms: tuple[str, ...] = ARMS) -> dict:
    seal_data, manifest = verify(sealed)
    model_ids = preflight(arms)  # Must fail before any inference if required models missing.
    check(not out.exists(), "AMR_OUTPUT_EXISTS")
    results: dict[str, dict] = {}
    for arm in arms:
        for c in manifest["cases"]:
            reference_bytes = safe(sealed, c["reference"], ".txt").read_bytes()
            check(sha(reference_bytes) == c["reference_sha256"],
                  "AMR_REFERENCE_CHANGED_DURING_RUN")
            reference = reference_bytes.decode("utf-8-sig")
            original_pages = []
            for page in c["pages"]:
                image_bytes = safe(sealed, page["inference"], ".jpg").read_bytes()
                check(sha(image_bytes) == page["inference_sha256"],
                      "AMR_IMAGE_CHANGED_DURING_RUN")
                original_pages.append(image_bytes)
            t0 = time.perf_counter()
            prediction = "\n".join(infer(arm, p) for p in original_pages)
            elapsed = max(0, int(1000 * (time.perf_counter() - t0)))
            results.setdefault(c["id"], {})[arm] = {
                "transcription": prediction, "latency_ms": elapsed,
                "metrics": score(reference, prediction)}
        digest_after = (str(pytesseract.get_tesseract_version()) if arm == "tesseract"
                        else get_installed_model_digest(
                            "glm-ocr:q8_0" if arm == "glm_ocr" else "qwen3-vl:4b"))
        check(digest_after == model_ids[arm], "AMR_MODEL_DIGEST_CHANGED_DURING_RUN")
        verify(sealed)
    rows = [{"id": c["id"], "reference_sha256": c["reference_sha256"],
             "image_sha256": [p["inference_sha256"] for p in c["pages"]],
             "results": results[c["id"]]} for c in manifest["cases"]]
    report = {
        "status": "completed_real_local_public_amr_ocr", "schema": VERSION,
        "source_seal_sha256": sha((sealed / "study_seal.json").read_bytes()),
        "dataset": DATASET, "revision": REVISION,
        "model_versions": model_ids, "arms": list(arms),
        "qwen_task": "new_transcription_prompt_not_structured_extraction",
        "qwen_system_prompt_sha256": sha(QWEN_SYSTEM.encode()),
        "qwen_user_prompt_sha256": sha(QWEN_USER.encode()),
        "published_ground_truth_not_independently_adjudicated": True,
        "not_structured_medication_vital_accuracy": True,
        "not_clinical_validation": True,
        "selected": seal_data["selected"], "scored": seal_data["scored"],
        "excluded": seal_data["excluded"], "upstream_total": EXPECTED_RECORDS,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "summaries": aggregates(rows, arms), "cases": rows}
    out.mkdir(parents=True, exist_ok=False)
    report_bytes = raw_json(report)
    write(out / "raw_results.json", report_bytes)
    write(out / "completion_receipt.json", raw_json({
        "status": report["status"], "result_sha256": sha(report_bytes),
        "source_seal_sha256": report["source_seal_sha256"],
        "cases": len(rows), "arms": list(arms)}))
    return {"status": report["status"], "scored": len(rows),
            "summaries": report["summaries"], "arms": list(arms)}


def replay(sealed: Path, run: Path) -> dict:
    seal_data, manifest = verify(sealed)
    raw = (run / "raw_results.json").read_bytes()
    report = load(run / "raw_results.json")
    receipt = load(run / "completion_receipt.json")
    arms = tuple(report.get("arms", []))
    check(bool(arms) and len(set(arms)) == len(arms) and
          all(a in ARMS for a in arms), "AMR_REPLAY_INVALID_ARMS")
    source = sha((sealed / "study_seal.json").read_bytes())
    check(report.get("schema") == VERSION
          and report.get("status") == "completed_real_local_public_amr_ocr"
          and report.get("dataset") == DATASET and report.get("revision") == REVISION
          and report.get("source_seal_sha256") == source
          and report.get("qwen_task") == "new_transcription_prompt_not_structured_extraction"
          and report.get("qwen_system_prompt_sha256") == sha(QWEN_SYSTEM.encode())
          and report.get("qwen_user_prompt_sha256") == sha(QWEN_USER.encode())
          and report.get("published_ground_truth_not_independently_adjudicated") is True
          and report.get("not_structured_medication_vital_accuracy") is True
          and report.get("not_clinical_validation") is True
          and report.get("selected") == seal_data["selected"]
          and report.get("scored") == seal_data["scored"]
          and report.get("excluded") == seal_data["excluded"]
          and report.get("upstream_total") == EXPECTED_RECORDS
          and receipt.get("status") == report["status"]
          and receipt.get("result_sha256") == sha(raw)
          and receipt.get("source_seal_sha256") == source
          and receipt.get("cases") == len(manifest["cases"])
          and receipt.get("arms") == list(arms), "AMR_REPLAY_SOURCE_OR_RECEIPT_MISMATCH")
    versions = report.get("model_versions")
    check(isinstance(versions, dict) and set(versions) == set(arms)
          and all(isinstance(v, str) and bool(v) for v in versions.values()),
          "AMR_REPLAY_MODEL_IDENTITY_UNVERIFIED")
    rows = report.get("cases")
    check(isinstance(rows, list) and len(rows) == len(manifest["cases"]),
          "AMR_REPLAY_INCOMPLETE_CASES")
    for row, case in zip(rows, manifest["cases"]):
        check(row.get("id") == case["id"]
              and row.get("reference_sha256") == case["reference_sha256"]
              and row.get("image_sha256") ==
              [p["inference_sha256"] for p in case["pages"]]
              and isinstance(row.get("results"), dict)
              and set(row["results"]) == set(arms),
              "AMR_REPLAY_WRONG_SOURCE_BINDING")
        gold = safe(sealed, case["reference"], ".txt").read_text("utf-8-sig")
        for arm in arms:
            obj = row["results"][arm]
            check(isinstance(obj.get("transcription"), str)
                  and type(obj.get("latency_ms")) is int
                  and obj["latency_ms"] >= 0
                  and obj.get("metrics") == score(gold, obj["transcription"]),
                  "AMR_REPLAY_PREDICTION_OR_METRICS_TAMPERED")
    check(report.get("summaries") == aggregates(rows, arms),
          "AMR_REPLAY_AGGREGATE_TAMPERED")
    return {"status": "replayed_all_saved_predictions", "cases": len(rows),
            "arms": list(arms), "summaries": report["summaries"]}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("scaffold")
    a.add_argument("--dataset-root", type=Path, required=True)
    a.add_argument("--study", type=Path, required=True)
    a.add_argument("--count", type=int, default=PILOT_COUNT)
    a = sub.add_parser("seal")
    a.add_argument("--study", type=Path, required=True)
    a.add_argument("--out", type=Path, required=True)
    a = sub.add_parser("verify")
    a.add_argument("--sealed", type=Path, required=True)
    a = sub.add_parser("execute")
    a.add_argument("--sealed", type=Path, required=True)
    a.add_argument("--out", type=Path, required=True)
    a.add_argument("--arms", default=",".join(ARMS))
    a = sub.add_parser("replay")
    a.add_argument("--sealed", type=Path, required=True)
    a.add_argument("--run", type=Path, required=True)
    args = p.parse_args()
    try:
        if args.command == "scaffold":
            data = scaffold(args.dataset_root, args.study, args.count)
        elif args.command == "seal":
            data = seal(args.study, args.out)
        elif args.command == "verify":
            _, manifest = verify(args.sealed)
            data = {"status": "verified_no_inference", "cases": len(manifest["cases"])}
        elif args.command == "execute":
            data = execute(args.sealed, args.out, tuple(args.arms.split(",")))
        else:
            data = replay(args.sealed, args.run)
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
        print("AMR_NOT_COMPLETED:" + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
