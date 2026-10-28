# PR #1 — Single Mac-only verification runbook

This is the consolidated local execution handoff. The PR already includes the
backend worker, inference service, job API, React polling, tests and printed
visual benchmark generator. Do not rebuild the architecture.

Safety: synthetic-only input; no PHI, paid API, Vercel reviews/previews,
production migration or merge without separate owner approval.

## 1. Synchronize safely

In the local repo, run:

    git status --short --branch
    git fetch origin
    git switch feat/clinical-validation-workbench
    git pull --ff-only origin feat/clinical-validation-workbench
    git rev-parse HEAD

Preserve existing work, stashes and worktrees. Record the exact SHA and check
the current draft PR description and reviews before making changes.

## 2. Focused new gates

    .venv/bin/python -m pytest backend/tests/test_ai_job_pipeline.py backend/tests/test_multimodal_adapters.py backend/tests/test_vision_benchmark_contract.py backend/tests/test_source_viewer.py backend/tests/test_workspace_authorization.py -q
    npm test --prefix frontend -- --run
    npm run build --prefix frontend
    npm run lint --prefix frontend

Test that Flask queues AI inference and never directly calls the model. The
worker must persist only a source/extraction-bound candidate, with a real
model digest on live runs, no Note or ReviewEvent mutation, strict idempotency,
a safe error on missing models, and historical candidates marked noncurrent
after any re-extraction. Test the browser's 2-second job polling and rejected
plain-text vision requests. Do not weaken assertions.

## 3. Full offline / PostgreSQL gates

    make check
    .venv/bin/python -m pytest backend/tests/ -q
    .venv/bin/python -m pytest backend/tests/test_postgres_concurrency.py -q

The PostgreSQL 15 test must use a disposable local instance only, never
Supabase. If binaries are missing and tests skip, record NOT RUN. Verify
migration 001->002->003, simultaneous writer barriers, and hosted cleanup
with enforced foreign keys.

## 4. Browser run with worker

Launch in terminal A with a disposable database:

    export DATABASE_URL=sqlite:////tmp/clinical-nlp-qa.db
    make dev

In terminal B:

    cd frontend
    CI=true npx playwright test --workers=1 --reporter=line

Verify the original PDF source image loads via authenticated blob, rotate and
page navigation work, annotations are honest about OCR-only evidence, and
review/save/export survives refresh and backend restart. Verify the AI job
stays queued until the separate worker consumes it and that model failures
never change reviewed state.

## 5. Actual local model experiment (optional, no cloud or payment)

    ollama --version
    ollama list
    .venv/bin/python backend/evaluation/generate_synthetic_visual_cases.py --output data/vision_gold
    .venv/bin/python backend/evaluation/vision_benchmark.py --manifest data/vision_gold/manifest.json

The generated cases are PRINTED synthetic examples, not handwriting. A live
GLM-OCR run requires an installed model digest and produces actual predictions,
source hashes, CER/WER and critical-token failure counts. If no installed
compatible model, local GPU memory or labeled image is available, report
NOT RUN. On a 16 GB M2 Pro, run models sequentially and unload between jobs.

Qwen3-VL image quality also requires a real synthetic image and actual model
execution; mocked tests are NOT evidence of quality. Never quote the old
hardcoded 0.0789/0.2727 handwriting example as observed model performance.

## 6. Final independent Codex review

After fixes, commit on the existing feature branch and run:

    git fetch origin main
    codex login status
    codex review --base origin/main

Use the existing ChatGPT sign-in without API-key billing. A clean-tree
uncommitted-diff review is not a full PR review. Resolve confirmed serious
findings, rerun changed tests and repeat full diff review on the final SHA.

Update the acceptance matrix with executable evidence, actual test exit codes
and the exact SHA. A43 (recorded hosted AI outputs) remains NOT IMPLEMENTED;
A45 (real handwriting model benchmark) remains NOT MEASURED unless proven
otherwise with actual runs. Keep PR #1 draft. Do not merge, deploy, use
Vercel as a code reviewer, or migrate production databases.

Report final HEAD, all test counts/exits, PostgreSQL and browser outcomes,
actual Ollama model digest/metrics or NOT RUN, Codex findings and remaining
release blockers.
