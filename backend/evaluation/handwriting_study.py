"""PR9: seal an externally adjudicated, genuinely HANDWRITTEN fictional corpus.

This tool never invents images, simulates independent humans or infers gold.
Inputs are private: a case ledger, TWO separately written blind transcripts,
and an independent human adjudicator's final annotations. Attestations need
real off-software verification. Never commit image or human annotation files.

python backend/evaluation/handwriting_study.py validate --input data/handwriting-private/intake
python backend/evaluation/handwriting_study.py seal --input data/handwriting-private/intake --output data/handwriting-private/sealed-v1
python backend/evaluation/handwriting_study.py verify --sealed data/handwriting-private/sealed-v1
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from PIL import Image  # noqa: E402
from evaluation.handwriting_intake import validate_handwriting_manifest  # noqa: E402
from evaluation.prospective_holdout import validate_freeze  # noqa: E402
from evaluation.vision_benchmark import load_gold_manifest, MAX_CASES, MAX_IMAGE_BYTES, MAX_PIXELS  # noqa: E402

VERSION = "genuine_fictional_handwriting_v1"
LOCK = ROOT / "docs/validation/PROSPECTIVE_HOLDOUT_LOCK.json"
MODEL_TAGS = {"glm_ocr": "glm-ocr:q8_0", "qwen3_vl": "qwen3-vl:4b"}
SOURCE_FILES = (
    "backend/evaluation/handwriting_study.py",
    "backend/evaluation/handwriting_evaluate.py",
    "backend/evaluation/handwriting_intake.py",
    "backend/evaluation/local_ollama_resource_sampler.py",
    "backend/evaluation/run_paired_holdout.py",
    "backend/evaluation/paired_holdout_analysis.py",
    "backend/evaluation/prospective_holdout.py",
    "backend/evaluation/local_vision_eval.py",
    "backend/evaluation/vision_benchmark.py",
    "backend/services/multimodal_service.py",
    "backend/services/inference_pipeline.py",
)
CAPTURE_METHODS = {"pen_on_paper_scan", "pen_on_paper_photograph", "freehand_stylus"}
STYLES = {"block_print", "cursive", "mixed"}
QUALITIES = {"clean", "challenging"}
ALLOWED_EXCLUDED_REASON = {"irreducibly_ambiguous", "unreadable_source", "independent_annotation_unavailable"}
SAFE_ID = re.compile(r"[a-zA-Z0-9_-]{3,80}\Z")
SAFE_ACTOR = re.compile(r"[a-z0-9_-]{3,50}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("HANDWRITING_INPUT_NOT_OBJECT")
    return data


def _expect(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def _pseudonym(value: Any) -> bool:
    return isinstance(value, str) and SAFE_ACTOR.fullmatch(value) is not None


def _files_in_input(source: Path) -> dict[str, Path]:
    _expect(source.is_dir(), "HANDWRITING_INTAKE_FOLDER_MISSING")
    return {name: source / (name + ".json")
            for name in ("collection", "transcriber_a", "transcriber_b", "adjudication")}


def _cases_by_id(cases: Any, code: str) -> dict[str, dict]:
    _expect(isinstance(cases, list) and 1 <= len(cases) <= MAX_CASES, code)
    found = {}
    for case in cases:
        _expect(isinstance(case, dict) and isinstance(case.get("id"), str)
                and SAFE_ID.fullmatch(case["id"]) is not None
                and case["id"] not in found, code)
        found[case["id"]] = case
    return found


def _source_image(root: Path, item: dict) -> tuple[Path, bytes]:
    name, expected = item.get("image"), item.get("sha256")
    _expect(isinstance(name, str) and isinstance(expected, str)
            and SHA.fullmatch(expected) is not None,
            "HANDWRITING_SOURCE_IDENTITY_REQUIRED")
    loc = (root / name).resolve()
    _expect(loc.is_relative_to(root.resolve()) and loc.is_file()
            and loc.suffix.lower() in {".jpg", ".jpeg", ".png"},
            "HANDWRITING_UNSAFE_OR_MISSING_IMAGE")
    _expect(0 < loc.stat().st_size <= MAX_IMAGE_BYTES, "HANDWRITING_IMAGE_TOO_LARGE")
    contents = loc.read_bytes()
    _expect(digest_bytes(contents) == expected, "HANDWRITING_IMAGE_SHA_CHANGED")
    with Image.open(loc) as image:
        _expect(image.width * image.height <= MAX_PIXELS, "HANDWRITING_IMAGE_TOO_LARGE")
        _expect(image.format in ("PNG", "JPEG"), "HANDWRITING_IMAGE_ENCODING_INVALID")
        image.verify()
    return loc, contents


def _validate_gold_fields(case: dict) -> None:
    meds, vitals = case.get("expected_medications"), case.get("expected_vitals")
    _expect(isinstance(meds, list) and isinstance(vitals, list),
            "HANDWRITING_STRUCTURED_GOLD_REQUIRED")
    for med in meds:
        _expect(isinstance(med, dict)
                and isinstance(med.get("name"), str) and bool(med["name"].strip())
                and isinstance(med.get("dose"), str),
                "HANDWRITING_MEDICATION_GOLD_INVALID")
        for optional in ("route", "frequency", "action"):
            _expect(optional not in med or isinstance(med[optional], str),
                    "HANDWRITING_MEDICATION_GOLD_INVALID")
    for vital in vitals:
        _expect(isinstance(vital, dict)
                and all(isinstance(vital.get(key), str) and vital[key].strip()
                        for key in ("vital_type", "value", "unit"))
                and re.fullmatch(r"[a-z][a-z0-9_]*", vital["vital_type"]) is not None,
                "HANDWRITING_VITAL_GOLD_INVALID")
    text = case.get("reference_text")
    _expect(isinstance(text, str) and bool(text.strip()) and len(text) <= 32768
            and "[ILLEGIBLE]" not in text.upper(),
            "HANDWRITING_FINAL_TRANSCRIPTION_REQUIRED")
    tokens = case.get("critical_tokens")
    _expect(isinstance(tokens, list) and bool(tokens)
            and all(isinstance(t, str) and t and t in text for t in tokens),
            "HANDWRITING_CRITICAL_TOKENS_INVALID")


def validate_collection(source: Path) -> tuple[dict, list[tuple[dict, bytes]]]:
    """Return proposed manifest + original source bytes, but make NO writes."""
    docs = {name: load_object(path) for name, path in _files_in_input(source).items()}
    collection, a, b, decisions = (docs[x] for x in
                                   ("collection", "transcriber_a", "transcriber_b", "adjudication"))
    dataset_id = collection.get("dataset_id")
    _expect(collection.get("schema_version") == VERSION
            and isinstance(dataset_id, str) and SAFE_ID.fullmatch(dataset_id) is not None
            and collection.get("synthetic_only") is True
            and collection.get("contains_actual_patient_data") is False
            and collection.get("attestation_verified_outside_software") is True,
            "HANDWRITING_COLLECTION_ATTESTATION_REQUIRED")
    source_cases = _cases_by_id(collection.get("cases"), "HANDWRITING_COLLECTION_CASES_INVALID")
    # Every cohort entry must be a distinct original image, not another case
    # ID pointing to the same file/bytes. Pixel-equivalent re-encodings still
    # need manual human deduplication and cannot be proven by SHA alone.
    source_hashes = [x.get("sha256") for x in source_cases.values()]
    _expect(all(isinstance(sha, str) and SHA.fullmatch(sha) is not None
                for sha in source_hashes)
            and len(set(source_hashes)) == len(source_hashes),
            "HANDWRITING_DUPLICATE_OR_INVALID_SOURCE_HASH")
    actors = []
    for doc in (a, b):
        _expect(doc.get("schema_version") == VERSION and doc.get("dataset_id") == dataset_id
                and _pseudonym(doc.get("transcriber_pseudonym"))
                and doc.get("independent_transcription_attested") is True
                and doc.get("blind_to_models_and_writer_prompts") is True,
                "HANDWRITING_BLIND_TRANSCRIBER_REQUIRED")
        actors.append(doc["transcriber_pseudonym"])
    _expect(actors[0] != actors[1], "HANDWRITING_TRANSCRIBERS_NOT_INDEPENDENT")
    _expect(decisions.get("schema_version") == VERSION
            and decisions.get("dataset_id") == dataset_id
            and _pseudonym(decisions.get("adjudicator_pseudonym"))
            and decisions.get("blinded_to_models") is True
            and decisions.get("independent_review_attested") is True
            and decisions.get("reviewed_both_transcripts") is True
            and decisions["adjudicator_pseudonym"] not in actors,
            "HANDWRITING_ADJUDICATOR_REQUIRED")
    trans_a = _cases_by_id(a.get("cases"), "HANDWRITING_TRANSCRIBER_CASES_MISSING")
    trans_b = _cases_by_id(b.get("cases"), "HANDWRITING_TRANSCRIBER_CASES_MISSING")
    adjud = _cases_by_id(decisions.get("cases"), "HANDWRITING_ADJUDICATION_CASES_MISSING")
    expected_ids = set(source_cases)
    _expect(all(set(z) == expected_ids for z in (trans_a, trans_b, adjud)),
            "HANDWRITING_PARTITION_CASES_MISMATCH")

    emitted, bytes_by_case = [], []
    for ident, item in source_cases.items():
        path, original = _source_image(source, item)
        writer = item.get("writer_pseudonym")
        _expect(_pseudonym(writer) and writer not in actors
                and writer != decisions["adjudicator_pseudonym"],
                "HANDWRITING_WRITER_REVIEWER_OVERLAP")
        _expect(item.get("generation_method") == "freehand"
                and item.get("capture_method") in CAPTURE_METHODS
                and item.get("writing_style") in STYLES
                and item.get("capture_quality") in QUALITIES
                and all(item.get(k) is True for k in (
                    "genuine_handwriting_attested", "fictional_content_attested",
                    "source_image_reviewed_for_identifiers", "writer_consent_attested")),
                "HANDWRITING_HUMAN_CAPTURE_ATTESTATIONS_REQUIRED")
        first, second, final = trans_a[ident], trans_b[ident], adjud[ident]
        for record in (first, second, final):
            _expect(record.get("sha256") == item["sha256"],
                    "HANDWRITING_ANNOTATION_IMAGE_MISMATCH")
        resolution = final.get("resolution")
        _expect(resolution in ("agreed", "adjudicated", "unscorable"),
                "HANDWRITING_ADJUDICATION_RESOLUTION_REQUIRED")
        # Real independent transcription may be impossible for an unreadable
        # image. The case must remain in the pre-inference exclusion ledger,
        # not acquire invented placeholder text merely to pass validation.
        for trans in (first, second):
            _expect(isinstance(trans.get("reference_text"), str)
                    and (resolution == "unscorable"
                         or bool(trans["reference_text"].strip())),
                    "HANDWRITING_TRANSCRIPTION_EMPTY")
        _expect(final.get("adjudication_record_id")
                and isinstance(final["adjudication_record_id"], str)
                and final.get("reviewed_original_image") is True,
                "HANDWRITING_ADJUDICATION_RECORD_REQUIRED")
        difference = first["reference_text"] != second["reference_text"]
        _expect((resolution != "agreed" or (not difference and
                 final.get("reference_text") == first["reference_text"]))
                and (not difference or resolution != "agreed"),
                "HANDWRITING_DISAGREEMENT_MUST_BE_RESOLVED")
        if difference:
            _expect(isinstance(final.get("resolution_notes"), str)
                    and bool(final["resolution_notes"].strip()),
                    "HANDWRITING_DISAGREEMENT_NOT_DOCUMENTED")
        if resolution == "unscorable":
            _expect(final.get("exclusion_reason") in ALLOWED_EXCLUDED_REASON
                    and isinstance(final.get("resolution_notes"), str)
                    and bool(final["resolution_notes"].strip()),
                    "HANDWRITING_UNSCORABLE_REASON_REQUIRED")
        else:
            _validate_gold_fields(final)
        image_name = "images/" + ident + path.suffix.lower()
        case = {
            "id": ident,
            "image": image_name,
            "sha256": item["sha256"],
            "source_type": "handwritten",
            "reference_text": final.get("reference_text") if resolution != "unscorable"
                              else "UNSCORABLE - EXCLUDED BEFORE ANY MODEL RUN",
            "expected_medications": final.get("expected_medications", []) if resolution != "unscorable" else [],
            "expected_vitals": final.get("expected_vitals", []) if resolution != "unscorable" else [],
            "critical_tokens": final.get("critical_tokens", []) if resolution != "unscorable" else [],
            "writing_style": item["writing_style"],
            "capture_quality": item["capture_quality"],
            "scoring_status": "excluded_before_inference" if resolution == "unscorable" else "scored",
            "exclusion_reason": final.get("exclusion_reason") if resolution == "unscorable" else None,
            "human_provenance": {
                "writer_pseudonym": writer,
                "independent_transcriber_pseudonyms": actors,
                "adjudicator_pseudonym": decisions["adjudicator_pseudonym"],
                "capture_method": item["capture_method"],
                "generation_method": "freehand",
                "genuine_handwriting_attested": True,
                "fictional_content_attested": True,
                "source_image_reviewed_for_identifiers": True,
                "adjudication_record_id": final["adjudication_record_id"],
            },
        }
        emitted.append(case)
        bytes_by_case.append((case, original))
    manifest = {
        "dataset_id": dataset_id,
        "study_version": VERSION,
        "synthetic_only": True,
        "annotation_status": "independent_human_transcription",
        "contains_actual_patient_data": False,
        "intended_use": "fictional_handwriting_evaluation_only",
        "attestation_verified_outside_software": True,
        "all_cases_included_before_scoring": True,
        "cases": emitted,
    }
    return manifest, bytes_by_case


def _sha_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def _source_sha() -> dict[str, str]:
    validate_freeze(LOCK)  # The original PR7/PR8 model prompts, parser and scorer.
    return {relative: _sha_file(ROOT / relative) for relative in SOURCE_FILES}


def _write_once(path: Path, obj: dict) -> None:
    with path.open("x", encoding="utf-8") as dest:
        json.dump(obj, dest, indent=2, sort_keys=True, ensure_ascii=False)
        dest.write("\n")


def prepare(source: Path, destination: Path) -> dict:
    """Copy original bytes unchanged, preserve independent transcripts, seal gold."""
    if destination.exists():
        raise ValueError("HANDWRITING_SEAL_DESTINATION_EXISTS")
    # Hold exact original annotation bytes before validation and persist those
    # same bytes; copying again from mutable paths after adjudication checking
    # could create a contradictory but otherwise hash-consistent seal.
    snapshots = {name: path.read_bytes()
                 for name, path in _files_in_input(source).items()}
    manifest, images = validate_collection(source)  # No output on failure.
    _expect(all(path.read_bytes() == snapshots[name]
                for name, path in _files_in_input(source).items()),
            "HANDWRITING_ANNOTATIONS_CHANGED_DURING_INTAKE")
    _expect(source.resolve() != destination.resolve() and
            not destination.resolve().is_relative_to(source.resolve()),
            "HANDWRITING_SEAL_CANNOT_NEST_INSIDE_SOURCE")
    hashes = _source_sha()
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "images").mkdir()
    (destination / "annotations").mkdir()
    for case, original in images:
        image = destination / case["image"]
        with image.open("xb") as f:
            f.write(original)  # Original photograph/scan bytes, never reconstructed.
    for name, snapshot in snapshots.items():
        with (destination / "annotations" / (name + ".json")).open("xb") as f:
            f.write(snapshot)
    _write_once(destination / "manifest.json", manifest)
    # The older PR7 handwriting intake path accepts the proper, explicit
    # external attestations; it never treats them as cryptographic identity proof.
    # Excluded cases are sealed but will be omitted from the scored manifest.
    scored = dict(manifest)
    scored["cases"] = [c for c in manifest["cases"] if c["scoring_status"] == "scored"]
    _expect(bool(scored["cases"]), "HANDWRITING_NO_SCORABLE_CASES")
    _write_once(destination / "scored_manifest.json", scored)
    validate_handwriting_manifest(destination / "scored_manifest.json")
    verified, meta = load_gold_manifest(destination / "scored_manifest.json")
    _expect(len(verified) == len(scored["cases"]), "HANDWRITING_SEALED_DATASET_MISMATCH")
    excluded = [c["id"] for c in manifest["cases"] if c["scoring_status"] != "scored"]
    people = {c["human_provenance"]["writer_pseudonym"] for c in manifest["cases"]}
    scored_people = {c["human_provenance"]["writer_pseudonym"]
                     for c in scored["cases"]}
    seal = {
        "version": VERSION,
        "status": "locally_attested_not_independently_proven",
        "dataset_id": manifest["dataset_id"],
        "manifest_sha256": _sha_file(destination / "manifest.json"),
        "scored_manifest_sha256": meta["manifest_sha256"],
        "annotation_file_sha256": {
            name: _sha_file(destination / "annotations" / (name + ".json"))
            for name in _files_in_input(source)
        },
        "model_identity_tags": MODEL_TAGS,
        "source_code_sha256": hashes,
        "case_count": len(manifest["cases"]),
        "scorable_count": len(scored["cases"]),
        "unscorable_case_ids": excluded,
        "writer_count": len(people),
        "cohort_phase": ("final_candidate" if len(scored["cases"]) >= 24
                         and len(scored_people) >= 3
                         else "pilot_or_insufficient_sample"),
        "limitations": [
            "Attestations are not independent verification that images are hand-written",
            "Synthetic fictional notes, not medical records or clinical validation",
            "Freeze should be independently timestamped before any model inference",
            "Unscorable cases excluded BEFORE inference, never selected by model performance",
        ],
    }
    _write_once(destination / "study_seal.json", seal)
    return seal


def verify_seal(directory: Path) -> dict:
    seal = load_object(directory / "study_seal.json")
    _expect(seal.get("version") == VERSION
            and seal.get("status") == "locally_attested_not_independently_proven"
            and seal.get("model_identity_tags") == MODEL_TAGS,
            "HANDWRITING_STUDY_SEAL_INVALID")
    hashes = _source_sha()
    _expect(seal.get("source_code_sha256") == hashes,
            "HANDWRITING_EVALUATION_CODE_CHANGED")
    _expect(_sha_file(directory / "manifest.json") == seal.get("manifest_sha256")
            and _sha_file(directory / "scored_manifest.json") == seal.get("scored_manifest_sha256"),
            "HANDWRITING_SEALED_GOLD_CHANGED")
    _expect(isinstance(seal.get("annotation_file_sha256"), dict)
            and set(seal["annotation_file_sha256"]) == set(_files_in_input(directory)),
            "HANDWRITING_INDEPENDENT_ANNOTATIONS_CHANGED")
    for name, sha in seal["annotation_file_sha256"].items():
        _expect(_sha_file(directory / "annotations" / (name + ".json")) == sha,
                "HANDWRITING_INDEPENDENT_ANNOTATIONS_CHANGED")
    manifest = load_object(directory / "manifest.json")
    scored = load_object(directory / "scored_manifest.json")
    cases = _cases_by_id(manifest.get("cases"), "HANDWRITING_STUDY_SEAL_INVALID")
    scored_cases = _cases_by_id(scored.get("cases"), "HANDWRITING_STUDY_SEAL_INVALID")
    _expect(set(scored_cases) == {k for k, case in cases.items()
                                  if case.get("scoring_status") == "scored"}
            and seal.get("case_count") == len(cases)
            and seal.get("scorable_count") == len(scored_cases)
            and seal.get("unscorable_case_ids") == [
                k for k, case in cases.items() if case.get("scoring_status") != "scored"
            ],
            "HANDWRITING_SCORING_PARTITION_CHANGED")
    _expect(all(scored_cases[k] == cases[k] for k in scored_cases),
            "HANDWRITING_SEALED_GOLD_CHANGED")
    all_writers = {
        c["human_provenance"]["writer_pseudonym"] for c in cases.values()
    }
    scored_writers = {
        c["human_provenance"]["writer_pseudonym"] for c in scored_cases.values()
    }
    expected_phase = ("final_candidate" if len(scored_cases) >= 24
                      and len(scored_writers) >= 3
                      else "pilot_or_insufficient_sample")
    _expect(seal.get("writer_count") == len(all_writers)
            and seal.get("cohort_phase") == expected_phase,
            "HANDWRITING_SEAL_DERIVED_COHORT_MISMATCH")
    validate_handwriting_manifest(directory / "scored_manifest.json")
    for case in cases.values():
        # load_gold_manifest() only checks scored images; check excluded image
        # bytes too, so that every included/excluded source remains immutable.
        _source_image(directory, case)
    return seal


def scaffold_images(images_dir: Path, destination: Path, dataset_id: str) -> dict:
    """Make unfilled, FALSE-by-default human annotation templates; no gold."""
    _expect(isinstance(dataset_id, str) and SAFE_ID.fullmatch(dataset_id) is not None,
            "HANDWRITING_DATASET_ID_REQUIRED")
    if destination.exists():
        raise ValueError("HANDWRITING_SCAFFOLD_DESTINATION_EXISTS")
    _expect(images_dir.is_dir(), "HANDWRITING_IMAGE_DIRECTORY_MISSING")
    sources = sorted(p for p in images_dir.iterdir()
                     if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
    _expect(1 <= len(sources) <= MAX_CASES,
            "HANDWRITING_SCAFFOLD_REQUIRES_IMAGES")
    # Validate the actual original byte hashes and formats BEFORE output.
    originals = []
    for i, path in enumerate(sources, 1):
        _expect(path.is_file() and not path.is_symlink(), "HANDWRITING_UNSAFE_OR_MISSING_IMAGE")
        ident = f"hw{i:03d}"
        payload = path.read_bytes()
        stub = {"image": path.name, "sha256": digest_bytes(payload)}
        _source_image(images_dir, stub)
        originals.append((ident, path.suffix.lower(), payload, stub["sha256"]))
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "images").mkdir()
    for ident, suffix, payload, sha in originals:
        with (destination / "images" / (ident + suffix)).open("xb") as file:
            file.write(payload)
    base = {
        "schema_version": VERSION,
        "dataset_id": dataset_id,
    }
    _write_once(destination / "collection.json", {
        **base, "synthetic_only": True,
        "contains_actual_patient_data": False,
        "attestation_verified_outside_software": False,
        "cases": [{
            "id": ident, "image": "images/" + ident + suffix,
            "sha256": sha,
            "writer_pseudonym": None,
            "generation_method": None,
            "capture_method": None,
            "writing_style": None,
            "capture_quality": None,
            "genuine_handwriting_attested": False,
            "fictional_content_attested": False,
            "source_image_reviewed_for_identifiers": False,
            "writer_consent_attested": False,
        } for ident, suffix, _, sha in originals],
    })
    for name in ("transcriber_a", "transcriber_b"):
        _write_once(destination / (name + ".json"), {
            **base,
            "transcriber_pseudonym": None,
            "independent_transcription_attested": False,
            "blind_to_models_and_writer_prompts": False,
            "cases": [{
                "id": ident, "sha256": sha, "reference_text": "",
            } for ident, _, _, sha in originals],
        })
    _write_once(destination / "adjudication.json", {
        **base, "adjudicator_pseudonym": None,
        "blinded_to_models": False,
        "independent_review_attested": False,
        "reviewed_both_transcripts": False,
        "cases": [{
            "id": ident, "sha256": sha,
            "adjudication_record_id": None,
            "reviewed_original_image": False,
            "resolution": None,
            "resolution_notes": "",
            "reference_text": "",
            "expected_medications": [],
            "expected_vitals": [],
            "critical_tokens": [],
        } for ident, _, _, sha in originals],
    })
    return {
        "status": "UNFILLED_TEMPLATES_NOT_A_HANDWRITING_ATTESTATION",
        "case_count": len(originals),
        "output": str(destination),
        "no_transcription_or_gold_generated": True,
        "human_attestations_default_false": True,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    command = p.add_subparsers(dest="command", required=True)
    for name in ("validate", "seal"):
        cmd = command.add_parser(name)
        cmd.add_argument("--input", type=Path, required=True)
        if name == "seal":
            cmd.add_argument("--output", type=Path, required=True)
    start = command.add_parser("scaffold")
    start.add_argument("--images", type=Path, required=True)
    start.add_argument("--dataset-id", required=True)
    start.add_argument("--output", type=Path, required=True)
    check = command.add_parser("verify")
    check.add_argument("--sealed", type=Path, required=True)
    args = p.parse_args()
    try:
        if args.command == "scaffold":
            result = scaffold_images(args.images, args.output, args.dataset_id)
            print(json.dumps(result, indent=2))
        elif args.command == "validate":
            result, _ = validate_collection(args.input)
            print(json.dumps({
                "status": "INTAKE_ATTESTATIONS_ONLY",
                "cases": len(result["cases"]),
                "no_model_calls": True,
            }, indent=2))
        elif args.command == "seal":
            result = prepare(args.input, args.output)
            print(json.dumps(result, indent=2))
        else:
            result = verify_seal(args.sealed)
            print("HANDWRITING_SEAL_VALID: " + result["scored_manifest_sha256"])
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
        code = str(exc)
        if not re.fullmatch(r"[A-Z0-9_:-]{2,120}", code):
            code = "HANDWRITING_STUDY_NOT_COMPLETED"
        print("HANDWRITING_STUDY_NOT_COMPLETED:" + code, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
