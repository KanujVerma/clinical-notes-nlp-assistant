# V1 release evidence

Local checks below were run on 2026-11-02 in the worktree
`.worktrees/v1-release` before the release commit. `make verify-release`
records `head` `0dd45ab3c07561b04ac264d5ec8d8f28935d4676` because that command
ran against the uncommitted tree whose parent is that SHA. The release
candidate SHA is the commit that adds this file on
`feat/clinical-nlp-v1-release`. It is not clinically validated and it is not
deployed.

Human clinician review: none.

## Renderer pin

`requirements.txt` is hash-frozen by `FROZEN_DEPENDENCY_AMENDMENT.json` and
still says `pillow>=10`. Pillow 10.4.0 regenerates frozen manifest SHA-256
`c30cfdd3ce457b157d1ee89a7859dfbe137c71e17990e84dcab49a74c6e6c332`. Pillow
12.2.0 and 13.0.0 both generate
`88ca0b0ebe0e7f2fe3f2356aa70a7f9aba1db239ebdeb9fd7e36f6a704214d1a`. Editing
`requirements.txt` to pin Pillow raises `FROZEN_DEPENDENCY_CHANGED`. CI
installs `pillow==10.4.0` after the frozen requirements file.
`scripts/verify_v1_release.py` refuses any other installed Pillow. Images,
gold, model reports, and scores were not rewritten.

## Commands

| Check | Command | Result |
|---|---|---|
| Backend | `.venv/bin/python -m pytest backend/tests/ -q` | 552 passed, 0 failed, 32.23s, exit 0 |
| Holdout file | `.venv/bin/python -m pytest backend/tests/test_paired_holdout.py -q` | 26 passed, exit 0 |
| Postgres | `REQUIRE_POSTGRES=1 .venv/bin/python -m pytest backend/tests/test_postgres_concurrency.py -q` | 3 passed, 1.55s, exit 0. Disposable cluster. A missing binary fails. |
| Vitest | `npm test --prefix frontend -- --run` | 13 files, 101 passed, 1.99s, exit 0 |
| Lint | `npm run lint --prefix frontend` | 0 errors, 99 warnings, exit 0 |
| Playwright | `cd frontend && CI=true npx playwright test --workers=1` | 31 passed, 2 skipped, 0 failed, 40.8s, exit 0 |
| Restart | `.venv/bin/python scripts/check_restart_persistence.py` | `passed_real_process_restart`, review_events 1, same extraction and source hash, workspace isolation preserved |
| Archive | SHA-256 of `docs/validation/evidence/PR8_REAL_BENCHMARK_EVIDENCE.zip.base64.txt` decoded bytes | `d073a12c5f9f7b9ff2a3cb406a5d4c06e50c7812f4ddda43e72001007a73a80d`, `testzip` None |
| Bundle | `make verify-release` | `RELEASE_GATE pass`. Checks: backend 32.24s, postgres 1.91s, frontend 2.44s, lint 1.31s, build 2.52s, restart 2.13s, archive 0.04s. Summary is gitignored. |

Playwright skips are `frontend/e2e/hosted-real.spec.ts`. They run only when
`RUN_REAL_HOSTED_E2E=1` and the server is `APP_MODE=hosted_demo`. The mocked
hosted spec passed. `make verify-release` does not start a browser;
`make verify-release` with `--with-browser` was not the command used. The
Playwright row above is the browser evidence.

Build inside the bundle: `tsc -b && vite build`, exit 0.

## Benchmark tiers

These stay separate.

- Unit fixtures and the 20-note Validation Lab.
- 3-case Tesseract showcase, `artifacts/evaluation/paired_local_030d0865b198675a.json`.
- Frozen 24-image aggregate. Manifest SHA above. Gold: 23 medication occurrences, 5 vitals, 2896 characters, 494 words. Tesseract medications 11/3/12, vitals 4/0/1, CER 124/2896, WER 164/494, critical 42/55. GLM medications 23/0/0, vitals 5/0/0, CER 17/2896, WER 13/494, critical 55/55. Qwen medications 15/8/8, vitals 0/7/5. Qwen OCR CER/WER is N/A. Raw transcripts are not published.
- Older archives stay historical.
- Clinical validation: not done.

Matching is source-occurrence-first, then bounded span overlap
(`strict_annotated_record_source_first_v3`). It is not the Hungarian algorithm.

## Validation loop

`data/validation_loop/v1_synthetic_note.txt` is extracted by the current
pipeline. `v1_injected_counterexample.json` is a planted quote and leading-zero
counterexample, not extractor output. `frontend/e2e/validation-loop.spec.ts`
covers paste, A02 and A10, a real dose correction, accept, reload, drilldown,
transcription update, and a replay that returns 409 `STALE_REVIEW`.

## Gates

| Gate | Local state |
|---|---|
| G1 Scope | Documented as a synthetic review workbench. No clinical or handwriting-accuracy claim. |
| G2 Source/review integrity | Stale idempotent replay and no-op parent edit are rejected by tests. |
| G3 Validation loop | Fixture, planted counterexample, and Playwright spec above. |
| G4 Evaluation integrity | Frozen archive hash matches. Tiers are not mixed. No score rewrite. |
| G5 Functional UI | Playwright 31 passed. Screenshots under `docs/screenshots/`. |
| G6 Local reproducibility | `make verify-release` plus the Pillow pin documented in the README. No paid AI. |
| G7 Automated quality | Counts above. Disclosed skip: two hosted-real Playwright tests. |
| G8 Documentation | README, architecture, demo script, and showcase use the same matcher and tiers. |
| G9 Portfolio evidence | `docs/validation/demo-script.md`, `docs/INTERVIEW_WALKTHROUGH.md`, `docs/validation/V1_RESUME_CLAIMS.md`. |
| G10 Review | Not complete. GitHub CI and the native Codex review of the release SHA are still required. No human review. |
| G11 Research isolation | Handwriting branch and PRs #9–#12 were not merged or edited. Holdout gold was not opened for retuning. |
| G12 Release integrity | This file is in the release commit. CI on that SHA is still required. |

Status until G10 and the CI run on the release SHA: not
`V1_RELEASE_CANDIDATE_READY`.
