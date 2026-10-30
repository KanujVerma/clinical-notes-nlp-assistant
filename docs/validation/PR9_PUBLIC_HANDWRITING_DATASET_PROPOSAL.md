# PR9 alternative: a public, genuinely handwritten clinical-document benchmark

**Decision:** User approved AMR primary + RxHandBD supplemental on 2026-10-30. AMR reproducibility/intake/three-arm OCR/replay implementation is in PR9, under privacy-gated, externally attested publisher ground truth. **No actual AMR model accuracy has been run or asserted yet.** The original PR9 six-person fictional-handwriting protocol remains unchanged as a separate, higher-assurance option.

## Recommended primary source: African Medical Records (AMR)

- Canonical dataset: https://huggingface.co/datasets/Nigeria-Health-data-OCR-pipeline/African-Medical-Records
- Reported provenance: 62 handwritten clinical-document records contributed by 15 volunteers, with matched published transcriptions; visit notes, prescriptions, nursing observations, lab requests, and case scenarios. Publisher describes these as *synthetic/volunteer-produced*, not real patient charts.
- Published metadata: `metadata.csv`, columns `pair_id,htr_file,truth_file,num_pages,contributor`. Multiple source pages are semicolon-delimited for five records. Files currently reference PNG scans and `.txt` transcriptions (not PDF, despite a stale secondary README).
- License on upstream dataset card: CC BY 4.0. Attribute AMR Contributors and link the source.
- Current upstream is ~219 MB. Reproducibility requires pinning and reporting an exact upstream revision, **not** using moving `main` for analysis. Example observed revision on 2026-10-30: `fa27d29dae4128ac45f035fd580928c84bec4e98`; verify that it resolves before downloading.
- Source claims are *publisher-reported*, not independent proof of physical handwriting or every contributor's consent.
- Corrections to published transcriptions have been committed upstream. Treat the selected revision and raw transcript bytes as frozen; do not silently track later edits.
- The native Hugging Face dataset viewer currently reports a legacy dataset-script error; use `hf download`/file downloads, **not** `load_dataset` or reliance on the viewer.

### Secondary source: RxHandBD

https://data.mendeley.com/datasets/dsb5r6vskg/3, DOI 10.17632/dsb5r6vskg.3, CC BY 4.0; 5,578 handwritten prescription-word crops, published text labels and 1,115 predefined test images. This offers a **separate medical-word OCR** stress test, not a substitute for whole-note testing. Never pool word-level metrics with document-level metrics.

## Separate evidence tracks (do not falsify attestations)

| Track | Images and reference | What can be concluded |
| --- | --- | --- |
| PR9 original | New physically handwritten fictional notes plus two blinded human transcriptions and a separate adjudicator | Externally attested independent fictional handwriting protocol; still not clinical validation |
| PR9 public AMR (proposed) | Publisher-provided physically handwritten clinical-style scans and publisher-provided transcripts | Exploratory **external public handwritten clinical-document OCR** benchmark, subject to integrity/privacy audits. **Not** equivalent to our own dual-blind gold |
| RxHandBD supplemental | Actual cropped handwritten medical words with published labels | External word-level handwriting recognition, not full-note/structured extraction |
| PR7/8 holdout | Generated printed/degraded documents with synthetic gold | Synthetic printed-image engineering evaluation only |

**Do not** put AMR images through `handwriting_study.py scaffold` and then mark writer consent or independent transcriber/adjudicator attestations `true`. Those are attestations for an entirely different collection process. Do not repurpose `synthetic_only` or `independent_human_transcription` fields dishonestly. Implement the public dataset as a distinct pipeline, manifest schema, freeze and evidence status.

## Implemented local AMR commands

The source-pinned public benchmark lives in `backend/evaluation/public_amr_benchmark.py`, separate from volunteer intake. Run this on the Mac with Python 3.11, project dependencies, and previously installed Tesseract + Ollama models. The 24-pair pilot uses round-robin contributor sampling over all 62 publisher records. It supports multiple source PNG pages per document and scores against its one text reference.

```bash
hf download Nigeria-Health-data-OCR-pipeline/African-Medical-Records \
  --repo-type dataset \
  --revision fa27d29dae4128ac45f035fd580928c84bec4e98 \
  --local-dir data/handwriting-private/amr-upstream

python backend/evaluation/public_amr_benchmark.py scaffold \
  --dataset-root data/handwriting-private/amr-upstream \
  --study data/handwriting-private/amr-intake
```

The resulting `privacy_review.json` is **deliberately unapproved**. A real reviewer must inspect every page and the published transcript for the selected cases before entering an actual reviewer identity, marking `all_pages_and_transcript_reviewed=true`, `contains_real_patient_data=false`, `contains_identifiers=false`, `decision=approved`; uncertain records should be excluded with one of the specified reasons. This is a privacy review, not independent blinded transcription. No source photos or text should be committed or uploaded.

```bash
python backend/evaluation/public_amr_benchmark.py seal \
  --study data/handwriting-private/amr-intake \
  --out data/handwriting-private/amr-sealed

# Independently timestamp/hash study_seal.json BEFORE inference.
shasum -a 256 data/handwriting-private/amr-sealed/study_seal.json

python backend/evaluation/public_amr_benchmark.py verify \
  --sealed data/handwriting-private/amr-sealed

python backend/evaluation/public_amr_benchmark.py execute \
  --sealed data/handwriting-private/amr-sealed \
  --out artifacts/handwriting-private/amr-real

python backend/evaluation/public_amr_benchmark.py replay \
  --sealed data/handwriting-private/amr-sealed \
  --run artifacts/handwriting-private/amr-real
```

The execute command compares three real local **OCR** arms: Tesseract, GLM-OCR, and Qwen3-VL with a *separately frozen Qwen handwriting transcription prompt*. This differs from the existing Qwen **structured entity** adapter, so Qwen OCR CER/WER is valid on this new task only. No medication or vital F1 is inferred from published text. The CLI also accepts `--arms tesseract` for a Tesseract-only pilot, which must be labeled a **partial**, not three-model completion.

The seal SHA-locks all 62 input metadata records and original source hashes, the publisher text gold, manual privacy reviewer decisions, retained original PNGs, fixed common inference JPEG transforms, PR7/8 inherited code locks, and the new runner. Replay verifies exact saved predictions/metrics and completion receipt with no inference. CI tests use pixel patterns and mocked model outputs only; **no real AMR samples or performance measurements are stored in CI**.

## Proposed execution gates (in order)

1. **License/source/PHI gate before inference.** Pin upstream revision and verify the 62-record metadata, document/page pairing, image bytes, text bytes, source formats and duplicate hashes. Review **all** pages/transcripts for identifiable patient information, including real-looking record numbers, handwritten names, stamps and signatures. The published *synthetic/volunteer* description alone is insufficient to certify no identifiers. Use local-only processing; never upload source data or unredacted predictions to cloud services or public GitHub. Predeclare exclusions/redactions and keep their counts and reasons. Do not claim that all 62 are eligible before inspection.
2. **Prospective selection/freeze.** Start with a **24-document pilot** selected deterministically across as many distinct contributors as possible, without seeing model answers. Record all 62 source rows in the denominator and precisely identify selected, privacy-excluded, multipage or unreadable records. Pin the repository revision, exact original file/image SHA-256, source-page order, exact reference-text SHA-256, model prompt, parser, scorer and any preprocessing code. Timestamp/hash the manifest **before** inference.
3. **Preserve pages.** Five upstream records are multipage (`AMR_002`, `AMR_013`, `AMR_018`, `AMR_045`, `AMR_052`). Evaluate multi-page records only when every page can be processed in order and compared to their **one record-level** published transcript; never score each page against the entire document transcript. If unsupported at pilot time, exclude those cases *prospectively* with a documented reason and count.
4. **Resource-safe, source-bound local inference.** Do not pull additional models or use paid/cloud endpoints. Reuse validated loopback Ollama allowlist and source SHA checks. If source resolution/downsampling is needed for the local 10 MB / 20 MP image limits, record an explicitly specified deterministic transform plus both original and inference-image hashes. All arms see equivalent transformed source pages. Run sequentially on the 16-GB Mac and record exact installed model digests, source-code hashes and timings.
5. **Honest model/metric comparison.** Score Tesseract and GLM-OCR *document-level* CER, WER, number/dose/unit string recall, per-case failure types and latency against the **published** reference text. Existing Qwen3-VL adapter returns structured candidates, **not OCR text**: it must not be assigned a CER/WER. Either (a) add a separately preregistered Qwen transcription prompt for a clearly labeled **new OCR task** with exact model digest and replay, or (b) defer Qwen's clinical F1 until distinct, manually curated structured-medication/vital gold is made. Never equate publisher-provided transcripts with independently adjudicated structured labels. Record reference errors/uncertainties rather than covertly editing published gold.
6. **Review and publication.** Rerun deterministic checks, secure CI and a full-diff Codex review. Publish only aggregates and transparent denominators/limitations. Keep original scans, transcripts, any model outputs containing identifiers and audit images private. No PHI/deployment/clinical-safety claims. No production changes or automatic merges.

## Acceptance language

A passing 24-case public pilot can support: **"On an exploratory, pinned public dataset of volunteer-produced handwritten clinical-style documents, the locally run OCR adapters achieved the reported CER/WER against publisher-supplied ground truth; model versions, exclusions, and all source hashes are documented."**

It **cannot** support: **"Our team collected 24 independent fictional notes with two blinded transcribers and third-person adjudication"**, or clinical validity, guaranteed PHI-free provenance, production readiness or measured structured medication/vital performance without independent structured gold.

## Pinned download (approved dataset, model measurements still pending)

```bash
hf download Nigeria-Health-data-OCR-pipeline/African-Medical-Records \
  --repo-type dataset \
  --revision fa27d29dae4128ac45f035fd580928c84bec4e98 \
  --local-dir data/handwriting-private/amr-upstream
```

The revision has been verified against the upstream commit page. Never commit the downloaded repository, image bytes or transcripts. The standalone AMR intake, sealing, inference and replay path has been implemented in this PR; actual data review, local inference and real-model replay remain separate execution gates.

## Original source citations (checked 2026-10-30)

- AMR official dataset card: https://huggingface.co/datasets/Nigeria-Health-data-OCR-pipeline/African-Medical-Records
- Current metadata (including multipage entries and contributor names): https://huggingface.co/datasets/Nigeria-Health-data-OCR-pipeline/African-Medical-Records/blob/main/metadata.csv
- RxHandBD original dataset listing and license: https://data.mendeley.com/datasets/dsb5r6vskg/3
