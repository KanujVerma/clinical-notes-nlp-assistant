"""Fail-closed intake for *genuine* handwritten fictional notes.

This validates attested writer/transcriber separation and source integrity,
not whether pixels actually depict human handwriting. The latter and gold
adjudication require external human verification. No samples are bundled.

    python backend/evaluation/handwriting_intake.py --manifest /private/fake_notes/manifest.json
    python backend/evaluation/handwriting_intake.py --manifest /private/fake_notes/manifest.json --run --arms tesseract
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from evaluation.vision_benchmark import load_gold_manifest  # noqa: E402
from evaluation.local_vision_eval import parse_arms, run_evaluation  # noqa: E402

_ALLOWED_ACQUISITION = {"pen_on_paper_photograph", "pen_on_paper_scan", "freehand_stylus"}
_NO_FAKE_HANDWRITING = {"font_render", "cursive_font", "ai_generated", "synthetic_font", "digitally_typeset"}


def validate_handwriting_manifest(path: Path) -> dict:
    """Validate signed-off fictional provenance and independent transcription.

    This checks submitted attestations only. It cannot independently prove a
    person's identity, review quality, or that an image is genuinely handwritten.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("INVALID_HANDWRITING_MANIFEST")
    if (data.get("annotation_status") != "independent_human_transcription"
            or data.get("synthetic_only") is not True
            or data.get("contains_actual_patient_data") is not False
            or data.get("intended_use") != "fictional_handwriting_evaluation_only"
            or data.get("attestation_verified_outside_software") is not True):
        raise ValueError("HANDWRITING_INDEPENDENT_GOLD_REQUIRED")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("EMPTY_HANDWRITING_CASES")

    images, checked = load_gold_manifest(path)
    by_id = {c["id"]: c for c in cases}
    for case in cases:
        ident = case.get("id")
        if case.get("source_type") != "handwritten":
            raise ValueError("FALSE_HANDWRITING_SOURCE_TYPE")
        provenance = case.get("human_provenance")
        if not isinstance(provenance, dict):
            raise ValueError("HANDWRITING_PROVENANCE_MISSING")
        writer = provenance.get("writer_pseudonym")
        annotators = provenance.get("independent_transcriber_pseudonyms")
        adjudicator = provenance.get("adjudicator_pseudonym")
        method = provenance.get("capture_method")
        if not all(isinstance(x, str) and re.fullmatch(r"[a-z0-9_-]{3,50}", x)
                   for x in (writer, adjudicator)):
            raise ValueError("HANDWRITING_INDEPENDENT_REVIEW_REQUIRED")
        if (method not in _ALLOWED_ACQUISITION or
                provenance.get("generation_method") != "freehand" or
                provenance.get("generation_method") in _NO_FAKE_HANDWRITING or
                provenance.get("genuine_handwriting_attested") is not True):
            raise ValueError("FONTS_OR_AI_NOT_HANDWRITING")
        if (not isinstance(annotators, list) or len(annotators) < 2 or
                any(not isinstance(x, str) or not re.fullmatch(r"[a-z0-9_-]{3,50}", x)
                    for x in annotators) or
                len(set(annotators)) != len(annotators) or
                writer in annotators or adjudicator == writer or adjudicator in annotators):
            raise ValueError("HANDWRITING_INDEPENDENT_REVIEW_REQUIRED")
        if (provenance.get("fictional_content_attested") is not True or
                provenance.get("source_image_reviewed_for_identifiers") is not True or
                not isinstance(provenance.get("adjudication_record_id"), str) or
                not provenance["adjudication_record_id"].strip()):
            raise ValueError("HANDWRITING_ATTESTATIONS_INCOMPLETE")
        gold = case.get("reference_text")
        if (not isinstance(gold, str) or not gold.strip() or
                not isinstance(case.get("expected_medications"), list) or
                not isinstance(case.get("expected_vitals"), list)):
            raise ValueError("HANDWRITING_GOLD_INCOMPLETE")
        if (not isinstance(case.get("critical_tokens"), list) or
                any(not isinstance(token, str) or token not in gold
                    for token in case["critical_tokens"])):
            raise ValueError("HANDWRITING_GOLD_INCOMPLETE")
        if ident not in by_id:
            raise ValueError("HANDWRITING_CASE_MISMATCH")

    return {
        "status": "attested_handwriting_intake_valid",
        "case_count": len(images),
        "annotation_status": checked["annotation_status"],
        "manifest_sha256": checked["manifest_sha256"],
        "cannot_verify": [
            "Human provenance authenticity cannot be established by this parser alone",
            "A reviewer must physically inspect image source and signed attestations",
            "This is fictional handwriting evaluation, not clinical validation",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--run", action="store_true", help="After intake checks, run actual installed local models")
    parser.add_argument("--arms", default="tesseract")
    parser.add_argument("--output", type=Path, default=Path("artifacts/handwriting-evaluation"))
    opts = parser.parse_args()
    try:
        verified = validate_handwriting_manifest(opts.manifest)
        if opts.run:
            result = run_evaluation(opts.manifest, parse_arms(opts.arms), opts.output)
            verified["model_result_file"] = str(result)
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        print("HANDWRITING_INTAKE_NOT_COMPLETED: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(verified, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
