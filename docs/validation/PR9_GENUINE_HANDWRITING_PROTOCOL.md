# PR #9: Genuine fictional handwriting benchmark, independent annotation and freeze

> **Approved public-dataset alternative (2026-10-30; real local measurements still pending):** The six-person volunteer study is **not the only way to run a genuine-handwriting OCR benchmark**. A separate, provenance-labeled AMR public-cohort plan using 62 publisher-supplied volunteer-written clinical documents and matching reference transcriptions is described in [PR9_PUBLIC_HANDWRITING_DATASET_PROPOSAL.md](PR9_PUBLIC_HANDWRITING_DATASET_PROPOSAL.md). It has different evidence/independence claims and must **not** be fed into this protocol by inventing human attestations. Nothing has been measured on AMR yet.

## What PR #9 can certify

**No handwriting model accuracy has been measured yet.** This PR supplies a private collection format, fail-closed attestation/independent-transcription checks, SHA-256 source+gold seal, real local three-model runner, independent replay and contract tests. It cannot itself create real handwriting, recruit independent humans, inspect their identity, or prove signed consent. Human claims are *externally attested*, not cryptographically established by the program.

The purpose is to extend PR #8's synthetic **printed** benchmark to **physically produced fictional handwriting** without changing PR #8 frozen Tesseract/GLM/Qwen adapters, medication parser, evaluator, prompts, gold, or medication/vital scoring. This is never intended for PHI, clinical use, automatic medication decisions or autonomous EHR activity.

## Cohort and study design

**Minimum exploratory pilot:** 12 distinct genuinely handwritten fictional notes from at least **3 writers**, 2 separate, blinded independent human transcribers and 1 adjudicator independent from both transcribers and every writer. Prefer at least 4 notes per writer. **Target final cohort:** at least 24 different original handwritten notes from at least 3 writers (8 per person) with a balanced spread of block-print, cursive and mixed writing; clean versus challenging captures; medication orders, decimals/units, negations, hold/stop/PRN, vitals and true negative controls. The code does not falsely label a 12-case pilot final or a duplicated image independent.

**Only genuinely physical handwriting:** pen on paper scanned/photographed, or human freehand stylus, not handwriting fonts, text rendering, programmatic stroke images, generated imitations, or user-uploaded patient charts. Do not copy any PR #7/8 source notes verbatim; do not collect names, dates of birth, contact info, institutions, real diagnoses/patients or signatures. Write `SYNTHETIC FICTIONAL NOTE` on the page.

Provide the handwriting writer only with a fictional writer card, never with model predictions. The two transcribers independently view the original image **without the writer cards, each other's transcript, gold fields or any OCR/model outputs**. They create independent transcription JSON files, including every visible line and number. A separate adjudicator independently reviews the original image and both raw transcriptions, resolves disagreements, and records final text, literal structured medication fields (name, dose, route, frequency and action when explicitly supported), canonical vital type/value/unit and exact critical tokens. Do not silently fill missing or illegible numerals from the writer card. Mark irreducibly ambiguous cases *unscorable before any inference* with a reason and preserve them in the full cohort denominator; do not discard them afterward.

### Sample coverage prompts for the writers

Use the separately committed [writer cards](PR9_FICTIONAL_WRITER_CARDS.md) only to guide physical handwriting. Ask each writer to restate the fictional card naturally in their own hand; no medical meaning or patient info is required. This preserves natural layout and variation while giving challenging numeric/negation cases. Writer cards are *not* gold annotations and should never be shown to transcribers or used to correct the model predictions.

## Low-friction Mac collection: generate UNFILLED JSON files automatically

Once you have photos or scans of actual handwritten fictional notes, place the original PNG/JPG files in `data/handwriting-private/photographs/`. Then run:

```bash
python backend/evaluation/handwriting_study.py scaffold \
  --images data/handwriting-private/photographs \
  --dataset-id fictional_handwriting_cohort_01 \
  --output data/handwriting-private/intake
```

This copies every original image **byte-for-byte**, computes its SHA-256, assigns stable IDs (`hw001` onward), and creates the four required JSON templates with the correct hashes and case IDs already filled. **Every human consent, independence, writer, and adjudication attestation defaults to `false` or `null`; all transcription and gold text is empty.** A scaffolded dataset must fail `validate` until distinct humans actually complete and verify all records. Never run scaffold as proof a sample is handwriting.

## Private folder structure (do not commit these files)

```text
data/handwriting-private/intake/
  collection.json
  transcriber_a.json
  transcriber_b.json
  adjudication.json
  images/
    hw001.png
    hw002.jpg
    ...
```

### `collection.json` example (repeat for every distinct original source image)

```json
{
  "schema_version": "genuine_fictional_handwriting_v1",
  "dataset_id": "fictional_handwriting_cohort_01",
  "synthetic_only": true,
  "contains_actual_patient_data": false,
  "attestation_verified_outside_software": true,
  "cases": [{
    "id": "hw001", "image": "images/hw001.png",
    "sha256": "REPLACE_WITH_REAL_IMAGE_SHA256_64_LOWERCASE_HEX",
    "writer_pseudonym": "writer_01",
    "generation_method": "freehand",
    "capture_method": "pen_on_paper_photograph",
    "writing_style": "block_print",
    "capture_quality": "clean",
    "genuine_handwriting_attested": true,
    "fictional_content_attested": true,
    "source_image_reviewed_for_identifiers": true,
    "writer_consent_attested": true
  }]
}
```

These boolean attestations must be supplied **only after actual human verification**; setting true for font-generated images, identifiers or patient material is false documentation. A test fixture containing a blank PNG can pass *structural* checks by construction; CI explicitly labels those tests MOCK ONLY and not real handwriting.

### `transcriber_a.json` and `transcriber_b.json` (created independently)

```json
{
  "schema_version": "genuine_fictional_handwriting_v1",
  "dataset_id": "fictional_handwriting_cohort_01",
  "transcriber_pseudonym": "annotator_alpha",
  "independent_transcription_attested": true,
  "blind_to_models_and_writer_prompts": true,
  "cases": [{
    "id": "hw001",
    "sha256": "SAME_64_HEX_SOURCE_SHA256",
    "reference_text": "SYNTHETIC FICTIONAL NOTE\n...independently read exact image text..."
  }]
}
```

Use a **different** `transcriber_pseudonym` in file B. An annotator cannot also have written any note. Transcriptions must be created before anyone evaluates OCR/model results; save the original independent files unchanged.

### `adjudication.json` (from a third, independent person)

```json
{
  "schema_version": "genuine_fictional_handwriting_v1",
  "dataset_id": "fictional_handwriting_cohort_01",
  "adjudicator_pseudonym": "adjudicator_01",
  "blinded_to_models": true,
  "independent_review_attested": true,
  "reviewed_both_transcripts": true,
  "cases": [{
    "id": "hw001", "sha256": "SAME_64_HEX_SOURCE_SHA256",
    "adjudication_record_id": "audit_hw001",
    "reviewed_original_image": true,
    "resolution": "adjudicated",
    "resolution_notes": "Checked disputed decimal by examining image independently",
    "reference_text": "SYNTHETIC FICTIONAL NOTE\nMetformin 500 mg PO BID.",
    "critical_tokens": ["500 mg", "BID"],
    "expected_medications": [
      {"name": "Metformin", "dose": "500 mg", "route": "PO", "frequency": "BID"}
    ],
    "expected_vitals": []
  }]
}
```

If both separate transcripts agree word-for-word and adjudicator agrees, use `"resolution": "agreed"` with matching `reference_text`. Otherwise use `"adjudicated"` with nonempty `resolution_notes`. For genuinely undecidable images, set `"resolution": "unscorable"`, `"exclusion_reason": "irreducibly_ambiguous"` (or `"unreadable_source"`/`"independent_annotation_unavailable"`) and descriptive notes; all cases, including exclusions, stay in the seal. The tool never infers entities from writer cards.

## Execute locally after all independent annotations exist

Use the latest PR #9 branch on the Mac with Python 3.11, pinned requirements and already installed Tesseract, GLM-OCR `glm-ocr:q8_0`, Qwen3-VL `qwen3-vl:4b` on loopback-only Ollama. **Do not pull new models or use cloud endpoints without prior user authorization.**

```bash
python backend/evaluation/handwriting_study.py validate \
  --input data/handwriting-private/intake
python backend/evaluation/handwriting_study.py seal \
  --input data/handwriting-private/intake \
  --output data/handwriting-private/sealed-v1
python backend/evaluation/handwriting_study.py verify \
  --sealed data/handwriting-private/sealed-v1
```

Before inference, preserve the local `study_seal.json` SHA-256 in a separate dated commit or externally timestamped audit record. The seal records exact image hashes, original raw blind transcript/adjudication file hashes, frozen scorer/prompt source byte hashes and cohort exclusions. This is more transparent than a post-results 'we froze it' claim; absence of independent timestamping limits the prospective claim.

```bash
python backend/evaluation/handwriting_evaluate.py execute \
  --sealed data/handwriting-private/sealed-v1 \
  --output artifacts/handwriting-private/run1
python backend/evaluation/handwriting_evaluate.py replay \
  --sealed data/handwriting-private/sealed-v1 \
  --run artifacts/handwriting-private/run1 \
  --output artifacts/handwriting-private/replay1
```

The runner processes the three actual locally installed arms **sequentially**, records model digests before and after, refusal on missing models/invalid tags, source-identical case IDs, real per-image timing, and best-effort Ollama residency plus macOS swap snapshots. The independent replay needs original results and completion receipt; recomputes every raw prediction's metric from the **frozen PR #8 scorer**. It never invents model outputs or changes gold.

Keep all input photos, gold and transcripts local/private. If the user explicitly authorizes evidence sharing, only upload a reviewed, consented, identifier-free sample with hashes and agreed annotations; otherwise publish high-level aggregate counts and salted/opaque hashes, not image text. CI exercises synthetic blank-image fixtures and MOCKED model responses **only to test code correctness**, never to measure real handwriting.

## Report and non-claims

Always report scorable cases, predeclared unscorable exclusions, distinct writers, style and capture strata, raw strict medication/vital TP/FP/FN/F1, per-case dose/unit/stop/PRN errors, OCR CER/WER/critical strings (Tesseract and GLM only), per-case paired win/loss/ties, latency and actual model digests. Never convert Qwen structured outputs into fake OCR CER. Do not compare a 12-case handwriting pilot numerically as though it were the same population as PR #8 printed 24-case synthetic benchmark. Do not claim a 100% handwriting accuracy result from a CI test or volunteer attestations alone.

**No patient clinical validation, clinical handwriting accuracy, HIPAA/PHI compliance, treatment recommendation or deployment authorization follows from this protocol.**
