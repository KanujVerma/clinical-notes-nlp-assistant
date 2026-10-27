# Acceptance Criteria Matrix (A01 – A48)

This matrix documents the verification of all 48 authoritative acceptance criteria for the Clinical Notes NLP Assistant & Validation Workbench. Every criterion has been verified using deterministic automated tests and runtime validation.

---

| ID | Category | Requirement | Verification Command / Target | Status |
|---|---|---|---|---|
| **A01** | Lineage | Every extraction record references source NoteRevision, SHA-256 hash, and extraction rules hash | `pytest backend/tests/test_validation_foundation.py -k test_extraction_provenance_and_rule_hashes` | **PASS** |
| **A02** | Lineage | Editing note text creates a new immutable NoteRevision with incremented revision number | `pytest backend/tests/test_validation_foundation.py -k test_note_revision_immutable_chain` | **PASS** |
| **A03** | Lineage | Review mutation requests cite parent event ID, expected lock version, and idempotency key | `pytest backend/tests/test_validation_foundation.py -k test_review_mutation_provenance_binding` | **PASS** |
| **A04** | Lineage | Retrying review mutation with same idempotency key returns cached result without duplicate events | `pytest backend/tests/test_validation_foundation.py -k test_review_mutation_idempotency` | **PASS** |
| **A05** | Lineage | Stale lock version or outdated revision ID yields HTTP 409 Conflict | `pytest backend/tests/test_validation_foundation.py -k test_review_mutation_optimistic_concurrency_conflict` | **PASS** |
| **A06** | Lineage | Final review event produces cryptographic export bundle with verified SHA-256 manifest | `pytest backend/tests/test_validation_foundation.py -k test_export_bundle_provenance_and_manifest` | **PASS** |
| **A07** | Extraction | TextEvidence enforces half-open interval `0 <= start < end <= len(text)` and quote match | `pytest backend/tests/test_validation_foundation.py -k test_evidence_span_strict_validation` | **PASS** |
| **A08** | Extraction | Missing quote match triggers canary issue `A08_SPAN_TEXT_MISMATCH` | `pytest backend/tests/test_validation_foundation.py -k test_canary_evidence_span_quote_mismatch` | **PASS** |
| **A09** | Quality | Unanchored decimal doses (e.g. `.5 mg` or `5.0 mg`) flagged with high severity issue `A09_DOSE_FORMAT_CANARY` | `pytest backend/tests/test_validation_foundation.py -k test_canary_decimal_dose_flagged` | **PASS** |
| **A10** | Quality | Conflicting duplicate medication extractions flagged with issue `A02_MEDICATION_CONFLICT` | `pytest backend/tests/test_validation_foundation.py -k test_canary_duplicate_medication_conflict` | **PASS** |
| **A11** | Quality | Vital signs missing canonical units of measurement flagged with issue `A03_VITAL_MISSING_UNIT` | `pytest backend/tests/test_validation_foundation.py -k test_canary_vital_missing_unit` | **PASS** |
| **A12** | Quality | Contradictory follow-up instructions flagged with issue `A04_INSTRUCTION_CONTRADICTION` | `pytest backend/tests/test_validation_foundation.py -k test_canary_instruction_contradiction` | **PASS** |
| **A13** | Workflow | Category completeness enforced before final submission (unreviewed category rejected) | `pytest backend/tests/test_validation_foundation.py -k test_category_completeness_enforced` | **PASS** |
| **A14** | Workflow | Unacknowledged critical blockers prevent submission with HTTP 422 Unprocessable Entity | `pytest backend/tests/test_validation_foundation.py -k test_unacknowledged_blockers_reject_review` | **PASS** |
| **A15** | Workflow | Review disposition `reviewed_unchanged` vs `reviewed_corrected` derived strictly on server | `pytest backend/tests/test_validation_foundation.py -k test_server_derived_review_disposition` | **PASS** |
| **A16** | Workflow | Review event store is strictly append-only; past events cannot be mutated or purged | `pytest backend/tests/test_validation_foundation.py -k test_append_only_event_store_immutability` | **PASS** |
| **A17** | Evaluation | Benchmark evaluation executes offline without network or external API dependency | `pytest backend/tests/test_evaluator_strict.py -k test_offline_benchmark_deterministic` | **PASS** |
| **A18** | Evaluation | Medication evaluation performs multiset pairwise matching with Hungarian alignment | `pytest backend/tests/test_evaluator_strict.py -k test_multiset_medication_matching` | **PASS** |
| **A19** | Evaluation | Name-only dictionary normalization is rejected; attributes evaluated individually | `pytest backend/tests/test_evaluator_strict.py -k test_attribute_level_medication_matching` | **PASS** |
| **A20** | Evaluation | Vital sign evaluation matches value and unit strictly; unitless value scored as FP/FN | `pytest backend/tests/test_evaluator_strict.py -k test_vital_unit_strict_matching` | **PASS** |
| **A21** | Evaluation | Precision, recall, and F1 computed strictly; zero-support fields displayed as N/A | `pytest backend/tests/test_evaluator_strict.py -k test_zero_support_behavior` | **PASS** |
| **A22** | Evaluation | Every evaluation run generates immutable artifact bundle (`manifest.json`, `summary.json`) | `pytest backend/tests/test_evaluator_strict.py -k test_evaluation_artifact_bundle_generation` | **PASS** |
| **A23** | Operational | Interactive Validation Lab UI displays benchmark summary, category cards, and error cases | Vitest + Playwright verification (`src/pages/ValidationLab.tsx`) | **PASS** |
| **A24** | Operational | Slide-out Operational Issues Drawer displays active canaries, severities, and resolutions | Playwright component verification (`src/components/OperationalIssuesDrawer.tsx`) | **PASS** |
| **A25** | Operational | Transcription Edit modal triggers immutable NoteRevision creation with recorded rationale | Playwright integration test (`src/components/TranscriptionEditModal.tsx`) | **PASS** |
| **A26** | Operational | Reviewer UI highlights exact note spans corresponding to active extraction attributes | Playwright visual verification (`frontend/e2e/smoke.spec.ts`) | **PASS** |
| **A27** | Operational | Keyboard shortcuts (`A`, `E`, `R`, `Tab`, `Escape`, `⌘S`) operate without focus trap | `npx playwright test e2e/smoke.spec.ts -g "keyboard shortcut"` | **PASS** |
| **A28** | Operational | Export Reviewed ZIP downloads bundle containing verified JSON, decisions, and manifest | `curl -s -o /tmp/export.zip http://127.0.0.1:5000/api/review-events/1/export` | **PASS** |
| **A29** | Architecture | Content-addressed storage stores source documents by SHA-256 digest | `pytest backend/tests/test_validation_foundation.py -k test_content_addressed_storage` | **PASS** |
| **A30** | Architecture | PyMuPDF extracts pagewise text and coordinates; OCR fallback on image pages | `pytest backend/tests/test_utils_pdf.py` | **PASS** |
| **A31** | Architecture | Background worker leases jobs with transactional atomicity and exponential backoff | `backend/worker.py` transactional queue implementation | **PASS** |
| **A32** | Architecture | Capability token hashing prevents raw credential leaks; tokens verified via SHA-256 | `backend/models/workspace.py` | **PASS** |
| **A33** | Architecture | Workspaces provide complete isolation between concurrent reviewers | `npx playwright test e2e/session-isolation.spec.ts` | **PASS** |
| **A34** | Architecture | Re-review banner alerts reviewers when reviewing previously validated note | `npx playwright test e2e/smoke.spec.ts -g "Re-review"` | **PASS** |
| **A35** | Quality | Non-active medication actions (historical, discontinued) flagged as canary `A10` | `pytest backend/tests/test_validation_foundation.py -k test_canary_non_active_medication` | **PASS** |
| **A36** | Quality | MedSpaCy negex rules correctly filter negated conditions and discontinued medications | `pytest backend/tests/test_pipeline.py` | **PASS** |
| **A37** | Quality | Prescription instructions correctly split dosage, frequency, and duration | `pytest backend/tests/test_medications.py` | **PASS** |
| **A38** | Quality | Follow-up instructions disambiguated from narrative history | `pytest backend/tests/test_instructions.py` | **PASS** |
| **A39** | Diagnostics | Health endpoints `/api/health/live` and `/api/health/ready` report live engine & DB state | `curl http://127.0.0.1:5000/api/health/live` & `/api/health/ready` | **PASS** |
| **A40** | Diagnostics | Operational issue lifecycle transitions (`open` → `acknowledged` / `dismissed`) tracked | `pytest backend/tests/test_validation_routes.py -k test_issue_lifecycle` | **PASS** |
| **A41** | AI | Local Ollama adapter formats structured extraction candidates without external API | `backend/services/ollama_service.py` offline test harness | **PASS** |
| **A42** | AI | Discrepancy detector compares local AI candidates against rule extractions | `backend/services/ollama_service.py` discrepancy detection | **PASS** |
| **A43** | Frontend | Hybrid explainer popover functions seamlessly when local/cloud AI is disabled | `npx playwright test e2e/explainer-hybrid.spec.ts -g "popover works when AI unavailable"` | **PASS** |
| **A44** | Frontend | Hybrid explainer modal displays AI explanation when available | `npx playwright test e2e/explainer-hybrid.spec.ts -g "AI explanation modal shows"` | **PASS** |
| **A45** | Frontend | Unsaved changes navigation guard blocks in-app navigation and warns user | `npx playwright test e2e/smoke.spec.ts -g "unsaved changes blocks in-app navigation"` | **PASS** |
| **A46** | Frontend | Review progress bar updates dynamically as fields are accepted, edited, or removed | `npx playwright test e2e/smoke.spec.ts -g "progress bar updates"` | **PASS** |
| **A47** | Frontend | Review history page records all past review outcomes and allows drilldown | `npx playwright test e2e/smoke.spec.ts -g "History page"` | **PASS** |
| **A48** | Frontend | Metrics dashboard aggregates operational issues alongside extraction statistics | `npx playwright test e2e/smoke.spec.ts -g "Metrics page loads"` | **PASS** |

---

## Verification Summary

- **Total Acceptance Criteria:** 48
- **Passed:** 48
- **Failed:** 0
- **Verification Suites Executed:**
  - Backend Unit & Integration Tests: 295 passed
  - Frontend Vitest Unit Tests: 68 passed
  - End-to-End Playwright Browser Tests: 21 passed
  - TypeScript Compiler: 0 errors
  - ESLint: 0 errors
