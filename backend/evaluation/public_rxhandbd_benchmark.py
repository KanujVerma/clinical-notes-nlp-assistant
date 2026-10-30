"""PR9 supplementary RxHandBD public MEDICAL WORD OCR benchmark.

Distinct from AMR document-level and from PR9 independent human adjudication.
Use the publisher's v3 TEST labels only, not training data, and keep all
images, labels, reviewer decisions and raw model predictions local/private.
No model performance is measured by CI; its samples/outputs are MOCKS.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from PIL import Image  # noqa: E402
from evaluation import public_amr_benchmark as amr  # noqa: E402
from evaluation.local_vision_eval import pytesseract  # noqa: E402
from services.inference_pipeline import get_installed_model_digest  # noqa: E402

DOI = "10.17632/dsb5r6vskg.3"
DATASET = "RxHandBD-ML test-split handwritten prescription word images"
VERSION = "public_rxhandbd_test_words_v1"
EXPECTED_TEST = 1115
DEFAULT_PILOT = 100
IMAGE_COLUMNS = ("filename", "image", "image_path", "file", "path", "image_name")
TEXT_COLUMNS = ("label", "text", "transcription", "word", "ground_truth")
ARMS = amr.ARMS


def file_index(root: Path) -> dict[str, Path]:
    images: dict[str, Path] = {}
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in (".jpg", ".jpeg", ".png"):
            # Require unique names within the selected image directory.
            if path.name in images:
                raise ValueError("RX_AMBIGUOUS_IMAGE_BASENAME_USE_IMAGES_DIR")
            images[path.name] = path
    return images


def catalog(data_root: Path, *, csv_path: Path | None = None,
            images_dir: Path | None = None,
            image_col: str | None = None, text_col: str | None = None) -> tuple[list[dict], dict]:
    # Explicit test split: never use train_labels.csv as a convenient fallback.
    if csv_path is None:
        choices = list(data_root.rglob("test_labels.csv"))
        amr.check(len(choices) == 1, "RX_ONE_PUBLISHER_TEST_CSV_REQUIRED")
        csv_path = choices[0]
    amr.check(csv_path.name == "test_labels.csv", "RX_NOT_PUBLISHER_TEST_SPLIT")
    amr.check(csv_path.resolve().is_relative_to(data_root.resolve())
              and csv_path.is_file(), "RX_UNSAFE_TEST_CSV")
    images_dir = images_dir or data_root
    amr.check(images_dir.resolve().is_relative_to(data_root.resolve())
              and images_dir.is_dir(), "RX_UNSAFE_IMAGE_FOLDER")
    labels_raw = csv_path.read_bytes()
    reader = csv.DictReader(io.StringIO(labels_raw.decode("utf-8-sig")))
    headers = reader.fieldnames or []
    image_col = image_col or next((n for n in IMAGE_COLUMNS if n in headers), None)
    text_col = text_col or next((n for n in TEXT_COLUMNS if n in headers), None)
    amr.check(bool(image_col and text_col) and image_col != text_col
              and image_col in headers and text_col in headers,
              "RX_UNKNOWN_CSV_COLUMNS_SPECIFY_IMAGE_AND_TEXT")
    rows = list(reader)
    amr.check(len(rows) == EXPECTED_TEST, "RX_EXPECTED_1115_PUBLISHER_TEST_ROWS")
    lookup = file_index(images_dir)
    seen_names, seen_hashes, entries = set(), set(), []
    for idx, row in enumerate(rows):
        name = (row.get(image_col) or "").strip().replace("\\", "/")
        label = row.get(text_col)
        amr.check(bool(name) and name == Path(name).name
                  and Path(name).suffix.lower() in (".jpg", ".jpeg", ".png")
                  and isinstance(label, str) and bool(label.strip())
                  and len(label) <= 256, "RX_BAD_SOURCE_OR_REFERENCE")
        amr.check(name not in seen_names and name in lookup,
                  "RX_MISSING_OR_DUPLICATE_TEST_IMAGE")
        seen_names.add(name)
        path = lookup[name]
        amr.check(path.stat().st_size <= amr.MAX_ORIGINAL_BYTES,
                  "RX_SOURCE_OVERSIZE")
        raw = path.read_bytes()
        with Image.open(io.BytesIO(raw)) as im:
            amr.check(im.format in ("JPEG", "PNG")
                      and 0 < im.width * im.height <= 100_000_000,
                      "RX_INVALID_SOURCE_IMAGE")
            im.verify()
        img_sha = amr.sha(raw)
        amr.check(img_sha not in seen_hashes, "RX_DUPLICATE_TEST_IMAGE_BYTES")
        seen_hashes.add(img_sha)
        entries.append({"id": f"rx{idx + 1:05d}", "image_name": name,
                        "original_sha256": img_sha,
                        "reference_text": label,
                        "reference_sha256": amr.sha(label.encode("utf-8"))})
    return entries, {
        "test_csv_sha256": amr.sha(labels_raw),
        "image_column": image_col, "text_column": text_col,
        "csv_relative": csv_path.resolve().relative_to(data_root.resolve()).as_posix(),
        "image_directory_relative": images_dir.resolve().relative_to(data_root.resolve()).as_posix(),
    }


def scaffold(data_root: Path, study: Path, count: int = DEFAULT_PILOT,
             *, images_dir: Path | None = None,
             image_col: str | None = None, text_col: str | None = None) -> dict:
    amr.check(not study.exists(), "RX_STUDY_ALREADY_EXISTS")
    entries, meta = catalog(data_root, images_dir=images_dir,
                            image_col=image_col, text_col=text_col)
    amr.check(12 <= count <= len(entries), "RX_INVALID_SAMPLE_SIZE")
    # Filename-only hash ranking; no selection by labels, image appearance, or model accuracy.
    selected = sorted(entries, key=lambda x: (amr.sha(x["image_name"].encode()), x["id"]))[:count]
    selected_ids = sorted(x["id"] for x in selected)
    manifest = {
        "schema": VERSION, "doi": DOI, "dataset": DATASET, "license": "CC-BY-4.0",
        "data_root": str(data_root.resolve()), "publisher_test_rows": EXPECTED_TEST,
        "test_csv": meta, "full_test_ledger": entries, "selected_ids": selected_ids,
        "selection_policy": "sha256_filename_rank_v1",
        "gold_provenance": "publisher_test_labels_unadjudicated",
        "image_provenance": "publisher_claims_physical_prescription_word_crops",
        "task": "single_word_ocr_not_clinical_document_extraction",
    }
    review = {
        "schema": VERSION, "selection_sha256": amr.sha(amr.raw_json(manifest)),
        "reviewer_id": "", "cases": [
            {"id": ident, "image_and_label_inspected": False, "contains_identifiers": None,
             "contains_real_patient_data": None, "decision": "unreviewed",
             "exclusion_reason": None}
            for ident in selected_ids],
    }
    study.mkdir(parents=True, exist_ok=False)
    amr.write(study / "selection.json", amr.raw_json(manifest))
    amr.write(study / "privacy_review.json", amr.raw_json(review))
    return {"status": "rx_public_test_privacy_review_required",
            "publisher_test_rows": len(entries), "selected_words": count}


def reviews(study: Path, sel: dict) -> dict:
    r = amr.load(study / "privacy_review.json")
    amr.check(r.get("schema") == VERSION and r.get("selection_sha256") ==
              amr.sha((study / "selection.json").read_bytes())
              and isinstance(r.get("reviewer_id"), str)
              and bool(r["reviewer_id"].strip()), "RX_PRIVACY_REVIEW_REQUIRED")
    cases = r.get("cases")
    amr.check(isinstance(cases, list) and len(cases) == len(sel["selected_ids"]),
              "RX_REVIEW_NOT_COMPLETE")
    by_id = {}
    for c in cases:
        amr.check(isinstance(c, dict) and c.get("id") in sel["selected_ids"]
                  and c["id"] not in by_id and c.get("image_and_label_inspected") is True,
                  "RX_RECORD_NOT_REVIEWED")
        if c.get("decision") == "approved":
            amr.check(c.get("contains_identifiers") is False
                      and c.get("contains_real_patient_data") is False
                      and c.get("exclusion_reason") is None, "RX_BAD_PRIVACY_APPROVAL")
        else:
            amr.check(c.get("decision") == "exclude"
                      and c.get("exclusion_reason") in
                      ("possible_identifiers", "possible_phi", "unreadable", "other_concern"),
                      "RX_EXCLUSION_NOT_DOCUMENTED")
        by_id[c["id"]] = c
    return by_id


def code_hashes() -> dict:
    result = amr.source_hashes()
    p = "backend/evaluation/public_rxhandbd_benchmark.py"
    result[p] = amr.sha((ROOT / p).read_bytes())
    return result


def seal(study: Path, out: Path) -> dict:
    amr.check(not out.exists(), "RX_SEAL_ALREADY_EXISTS")
    sel = amr.load(study / "selection.json")
    amr.check(sel.get("schema") == VERSION and sel.get("doi") == DOI
              and sel.get("license") == "CC-BY-4.0"
              and sel.get("dataset") == DATASET
              and sel.get("task") == "single_word_ocr_not_clinical_document_extraction"
              and sel.get("gold_provenance") == "publisher_test_labels_unadjudicated",
              "RX_INCORRECT_SOURCE_OR_SCOPE")
    root = Path(sel["data_root"])
    details = sel["test_csv"]
    images_dir = root / details["image_directory_relative"]
    entries, current_meta = catalog(root, csv_path=root / details["csv_relative"],
                                    images_dir=images_dir,
                                    image_col=details["image_column"],
                                    text_col=details["text_column"])
    expected_ids = sorted(x["id"] for x in sorted(
        entries, key=lambda x: (amr.sha(x["image_name"].encode()), x["id"]))
        [:len(sel["selected_ids"])])
    amr.check(sel.get("full_test_ledger") == entries
              and current_meta == details
              and sel.get("selected_ids") == expected_ids
              and sel.get("selection_policy") == "sha256_filename_rank_v1",
              "RX_PUBLISHER_OR_SELECTION_CHANGED")
    checked = reviews(study, sel)
    accepted = [ident for ident in expected_ids if checked[ident]["decision"] == "approved"]
    amr.check(len(accepted) >= 12, "RX_INSUFFICIENT_APPROVED_WORDS")
    source_by_id = {entry["id"]: entry for entry in entries}
    # Capture exact original file bytes before creating an output.
    snapshots = []
    for ident in accepted:
        e = source_by_id[ident]
        original = images_dir / e["image_name"]
        amr.check(original.is_file() and not original.is_symlink(), "RX_IMAGE_MISSING")
        original_bytes = original.read_bytes()
        amr.check(amr.sha(original_bytes) == e["original_sha256"],
                  "RX_IMAGE_CHANGED_DURING_SEAL")
        snapshots.append((ident, original_bytes, amr.infer_image(original_bytes)))
    select_bytes = (study / "selection.json").read_bytes()
    review_bytes = (study / "privacy_review.json").read_bytes()
    protected = code_hashes()
    out.mkdir(parents=True, exist_ok=False)
    amr.write(out / "selection.json", select_bytes)
    amr.write(out / "privacy_review.json", review_bytes)
    cases = []
    for ident, original, converted in snapshots:
        e = source_by_id[ident]
        original_path = f"originals/{ident}{Path(e['image_name']).suffix.lower()}"
        image_path = f"images/{ident}.jpg"
        amr.write(out / original_path, original)
        amr.write(out / image_path, converted)
        cases.append({
            "id": ident, "original": original_path, "original_sha256": amr.sha(original),
            "image": image_path, "image_sha256": amr.sha(converted),
            "reference_text": e["reference_text"],
            "reference_sha256": e["reference_sha256"],
        })
    manifest = {
        "schema": VERSION, "doi": DOI, "dataset": DATASET,
        "test_total": EXPECTED_TEST, "selected_ids": expected_ids,
        "scored_ids": accepted,
        "excluded_before_inference": [
            {"id": i, "reason": checked[i]["exclusion_reason"]}
            for i in expected_ids if i not in accepted],
        "cases": cases, "publisher_gold_not_human_adjudicated": True,
        "word_level_only": True, "no_structured_gold": True,
        "not_clinically_validated": True,
    }
    amr.write(out / "manifest.json", amr.raw_json(manifest))
    lock = {
        "schema": VERSION, "status": "source_and_privacy_review_sealed",
        "selection_sha256": amr.sha(select_bytes),
        "review_sha256": amr.sha(review_bytes),
        "manifest_sha256": amr.sha((out / "manifest.json").read_bytes()),
        "code_sha256": protected,
        "source_test_csv_sha256": details["test_csv_sha256"],
        "selected": len(expected_ids), "scored": len(accepted),
        "arms": list(ARMS),
    }
    amr.write(out / "study_seal.json", amr.raw_json(lock))
    return {"status": "rx_sealed_no_model_inference", "scored": len(accepted)}


def verify(sealed: Path) -> tuple[dict, dict]:
    lock = amr.load(sealed / "study_seal.json")
    selection = amr.load(sealed / "selection.json")
    manifest = amr.load(sealed / "manifest.json")
    reviewed = reviews(sealed, selection)
    accepted = [i for i in selection["selected_ids"] if reviewed[i]["decision"] == "approved"]
    exclusions = [{"id": i, "reason": reviewed[i]["exclusion_reason"]}
                  for i in selection["selected_ids"] if i not in accepted]
    amr.check(lock.get("schema") == VERSION and lock.get("status") ==
              "source_and_privacy_review_sealed"
              and lock.get("code_sha256") == code_hashes()
              and lock.get("arms") == list(ARMS)
              and lock.get("selection_sha256") ==
              amr.sha((sealed / "selection.json").read_bytes())
              and lock.get("review_sha256") ==
              amr.sha((sealed / "privacy_review.json").read_bytes())
              and lock.get("manifest_sha256") ==
              amr.sha((sealed / "manifest.json").read_bytes())
              and lock.get("source_test_csv_sha256") ==
              selection["test_csv"]["test_csv_sha256"]
              and lock.get("selected") == len(selection["selected_ids"])
              and lock.get("scored") == len(accepted)
              and manifest.get("schema") == VERSION
              and manifest.get("doi") == DOI and manifest.get("dataset") == DATASET
              and manifest.get("test_total") == EXPECTED_TEST
              and manifest.get("selected_ids") == selection["selected_ids"]
              and manifest.get("scored_ids") == accepted
              and manifest.get("excluded_before_inference") == exclusions
              and manifest.get("publisher_gold_not_human_adjudicated") is True
              and manifest.get("word_level_only") is True
              and manifest.get("no_structured_gold") is True
              and manifest.get("not_clinically_validated") is True
              and len(accepted) >= 12 and len(manifest["cases"]) == len(accepted),
              "RX_SOURCE_FREEZE_OR_CLAIM_TAMPERED")
    by_id = {r["id"]: r for r in selection["full_test_ledger"]}
    for case, ident in zip(manifest["cases"], accepted):
        original = by_id[ident]
        suffix = Path(original["image_name"]).suffix.lower()
        amr.check(case["id"] == ident and
                  case["original"] == f"originals/{ident}{suffix}" and
                  case["image"] == f"images/{ident}.jpg" and
                  case["original_sha256"] == original["original_sha256"] and
                  case["reference_sha256"] == original["reference_sha256"] and
                  case["reference_text"] == original["reference_text"],
                  "RX_MANIFEST_SOURCE_BINDING_TAMPERED")
        original_bytes = amr.safe(sealed, case["original"], suffix).read_bytes()
        inference_bytes = amr.safe(sealed, case["image"], ".jpg").read_bytes()
        amr.check(amr.sha(original_bytes) == case["original_sha256"]
                  and amr.sha(inference_bytes) == case["image_sha256"]
                  and amr.sha(amr.infer_image(original_bytes)) == case["image_sha256"],
                  "RX_IMAGE_SOURCE_TAMPERED")
    return lock, manifest


def infer_word(arm: str, image: bytes) -> str:
    if arm == "tesseract":
        with Image.open(io.BytesIO(image)) as im:
            return pytesseract.image_to_string(im.convert("RGB"), config="--psm 7")
    return amr.infer(arm, image)


def evaluate(sealed: Path, out: Path, arms: tuple[str, ...] = ARMS) -> dict:
    lock, manifest = verify(sealed)
    versions = amr.preflight(arms)
    amr.check(not out.exists(), "RX_RESULT_EXISTS")
    by_id = {c["id"]: {} for c in manifest["cases"]}
    for arm in arms:
        for c in manifest["cases"]:
            image = amr.safe(sealed, c["image"], ".jpg").read_bytes()
            start = time.perf_counter()
            pred = infer_word(arm, image)
            duration = max(0, int((time.perf_counter() - start) * 1000))
            by_id[c["id"]][arm] = {
                "transcription": pred, "latency_ms": duration,
                "metrics": amr.score(c["reference_text"], pred)}
        actual_version = (str(pytesseract.get_tesseract_version()) if arm == "tesseract"
                          else get_installed_model_digest(
                              "glm-ocr:q8_0" if arm == "glm_ocr" else "qwen3-vl:4b"))
        amr.check(actual_version == versions[arm], "RX_MODEL_CHANGED_DURING_INFERENCE")
        verify(sealed)
    rows = [
        {"id": c["id"], "image_sha256": c["image_sha256"],
         "reference_sha256": c["reference_sha256"], "results": by_id[c["id"]]}
        for c in manifest["cases"]]
    report = {
        "status": "real_local_rxhandbd_published_word_ocr", "schema": VERSION,
        "source_seal_sha256": amr.sha((sealed / "study_seal.json").read_bytes()),
        "doi": DOI, "dataset": DATASET, "arms": list(arms),
        "model_versions": versions,
        "qwen_task": "new_transcription_prompt_not_structured_extraction",
        "qwen_prompt_sha256": amr.sha(amr.QWEN_SYSTEM.encode()),
        "publisher_gold_not_human_adjudicated": True,
        "word_level_only": True, "not_clinical_validation": True,
        "test_total": EXPECTED_TEST, "selected": lock["selected"],
        "scored": lock["scored"], "excluded": lock["selected"] - lock["scored"],
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "summaries": amr.aggregates(rows, arms), "cases": rows,
    }
    out.mkdir(parents=True, exist_ok=False)
    payload = amr.raw_json(report)
    amr.write(out / "raw_results.json", payload)
    amr.write(out / "completion_receipt.json", amr.raw_json({
        "status": report["status"], "source_seal_sha256": report["source_seal_sha256"],
        "results_sha256": amr.sha(payload), "arms": list(arms),
        "cases": len(rows)}))
    return {"status": report["status"], "scored": len(rows), "summaries": report["summaries"]}


def replay(sealed: Path, run: Path) -> dict:
    lock, manifest = verify(sealed)
    raw = (run / "raw_results.json").read_bytes()
    report = amr.load(run / "raw_results.json")
    receipt = amr.load(run / "completion_receipt.json")
    arms = tuple(report.get("arms", []))
    source = amr.sha((sealed / "study_seal.json").read_bytes())
    amr.check(bool(arms) and set(arms) <= set(ARMS) and len(arms) == len(set(arms))
              and report.get("schema") == VERSION
              and report.get("status") == "real_local_rxhandbd_published_word_ocr"
              and report.get("source_seal_sha256") == source
              and report.get("doi") == DOI and report.get("dataset") == DATASET
              and report.get("test_total") == EXPECTED_TEST
              and report.get("selected") == lock["selected"]
              and report.get("scored") == lock["scored"]
              and report.get("excluded") == lock["selected"] - lock["scored"]
              and report.get("qwen_task") ==
              "new_transcription_prompt_not_structured_extraction"
              and report.get("qwen_prompt_sha256") == amr.sha(amr.QWEN_SYSTEM.encode())
              and report.get("publisher_gold_not_human_adjudicated") is True
              and report.get("word_level_only") is True
              and report.get("not_clinical_validation") is True
              and receipt.get("source_seal_sha256") == source
              and receipt.get("results_sha256") == amr.sha(raw)
              and receipt.get("status") == report["status"]
              and receipt.get("cases") == len(manifest["cases"])
              and receipt.get("arms") == list(arms),
              "RX_REPLAY_REPORT_OR_RECEIPT_TAMPERED")
    versions = report.get("model_versions")
    amr.check(isinstance(versions, dict) and set(versions) == set(arms)
              and all(isinstance(v, str) and bool(v) for v in versions.values()),
              "RX_MODEL_PROVENANCE_MISSING")
    rows = report.get("cases")
    amr.check(isinstance(rows, list) and len(rows) == len(manifest["cases"]),
              "RX_REPLAY_CASES_INCOMPLETE")
    for row, case in zip(rows, manifest["cases"]):
        amr.check(row.get("id") == case["id"]
                  and row.get("image_sha256") == case["image_sha256"]
                  and row.get("reference_sha256") == case["reference_sha256"]
                  and isinstance(row.get("results"), dict)
                  and set(row["results"]) == set(arms),
                  "RX_REPLAY_WRONG_SOURCE")
        for arm in arms:
            item = row["results"][arm]
            amr.check(isinstance(item.get("transcription"), str)
                      and type(item.get("latency_ms")) is int
                      and item["latency_ms"] >= 0
                      and item.get("metrics") ==
                      amr.score(case["reference_text"], item["transcription"]),
                      "RX_REPLAY_METRICS_CHANGED")
    amr.check(report.get("summaries") == amr.aggregates(rows, arms),
              "RX_REPLAY_AGGREGATES_CHANGED")
    return {"status": "replayed_publisher_word_gold", "cases": len(rows),
            "summaries": report["summaries"]}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("scaffold")
    a.add_argument("--dataset-root", type=Path, required=True)
    a.add_argument("--study", type=Path, required=True)
    a.add_argument("--count", type=int, default=DEFAULT_PILOT)
    a.add_argument("--images-dir", type=Path)
    a.add_argument("--image-column")
    a.add_argument("--text-column")
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
            result = scaffold(args.dataset_root, args.study, args.count,
                              images_dir=args.images_dir,
                              image_col=args.image_column,
                              text_col=args.text_column)
        elif args.command == "seal":
            result = seal(args.study, args.out)
        elif args.command == "verify":
            _, m = verify(args.sealed)
            result = {"status": "rx_verify_passed", "cases": len(m["cases"])}
        elif args.command == "execute":
            result = evaluate(args.sealed, args.out, tuple(args.arms.split(",")))
        else:
            result = replay(args.sealed, args.run)
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
        print("RX_NOT_COMPLETED:" + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
