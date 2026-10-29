# PR #4 — Recorded synthetic evidence and reviewer drilldowns

## Purpose

A portfolio viewer should see **what actually ran**, and drill down from a
dashboard count to the exact current source-bound note and issue. A mock model
response or correction rate is not clinical accuracy evidence.

This is offline/hosted read-only showcase infrastructure, **not** a hosted
model execution feature or production deployment authorization.

## User flow

1. Open sidebar **Evidence Showcase** (/showcase). The public
   /api/showcase-evidence route reads the committed real Tesseract
   synthetic development baseline, checks its SHA-256 source identities,
   case counts, aggregate error counts and critical-token counts, then
   displays the actual case-level OCR predictions and metrics.
2. The Tesseract dataset contains three generator-produced printed/
   artificially degraded documents. These are NOT a held-out corpus,
   real handwriting, or a clinical validation dataset. Critical-token
   recognition alone does not establish correct negation or attribution.
3. Recorded GLM-OCR and Qwen3-VL model output remains NOT RECORDED until a
   real approved local experiment is frozen. No fake model predictions,
   unit-test mocks or model self-confidence are shown.
4. Dashboard category/field correction rates, current issue counters,
   and current review outcomes link to /metrics/drilldown. Its workspace
   authorized backend returns at most 50 current source/extraction-bound
   rows, with no raw note text or medication values. A result opens
   /review/:noteId with a field or issue link and source/issue focus.
5. Accessibility: keyboard skip to main, semantic headings and links,
   focus-visible styles, selected-issue focus, and error/empty states.

## Curator-approved real local AI recordings

Run PR #3 on actual synthetic image bytes, with both installed free local
models if hardware permits:

    python backend/evaluation/generate_synthetic_visual_cases.py --output data/vision_gold
    python backend/evaluation/local_vision_eval.py --manifest data/vision_gold/manifest.json --arms tesseract,glm_ocr,qwen3_vl

Inspect the original images, case-level candidate output, model digest,
source hashes, and dangerous critical dose/negation errors. Only after
this **actual** human approval run:

    python scripts/freeze_local_showcase_ai.py --evaluation artifacts/evaluation/paired_local_<actual>.json --approve-reviewed

The exporter creates data/showcase/recorded_ai.json only if real GLM/Qwen
model arms are included, all source hashes match the frozen dataset,
the installed model digests are formatted as SHA-256, and a reviewer
explicitly accepts responsibility for the synthetic recording. A
Tesseract-only artifact fails closed. The generated file must be
inspected separately before committing to the public repository.

A43 (recorded hosted AI results) is still NOT IMPLEMENTED as an actual
published data example until approved local model predictions exist.
A45 (real handwriting accuracy) is still NOT MEASURED. Capturing an
output does not grant clinical correctness or independent adjudication.
No PHI, EHR, diagnosis, treatment or HIPAA claims are supported.

## Test gates

    python -m pytest backend/tests/test_metric_drilldown.py backend/tests/test_showcase_evidence.py -q
    python scripts/check_restart_persistence.py
    npm test --prefix frontend -- --run
    npm run build --prefix frontend
    npm run lint --prefix frontend

With real local Flask/Vite services on a disposable SQLite database:

    cd frontend
    CI=true npx playwright test e2e/showcase.spec.ts --workers=1

The subprocess check starts TWO separate Flask OS processes, writes an
immutable synthetic ReviewEvent to disposable SQLite, stops the first
process, boots the second and verifies source hash, extraction binding,
ReviewEvent, metrics, queue and workspace isolation. This is stronger
than merely rebuilding a test_client within one process.

CI: .github/workflows/showcase-integrity.yml. The main Quality workflow
also covers offline backend, frontend and browser suites.

## Deployment boundary

No automatic Vercel or Render deployment, no production Supabase migration,
no paid AI. PR #2's manual hosted preflight, public Vercel-to-Render API
origin configuration, exact CORS allowlist, backup and rollback plan must be
approved separately before any public release. Keep PR #4 draft.
