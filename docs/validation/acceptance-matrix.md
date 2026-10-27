# Acceptance matrix — source audit in progress

**Do not use the earlier 48/48 PASS claim.** The prior matrix remapped the original A01–A32 identifiers, included names of tests that were not present, and marked documentation/module existence as execution evidence. This table restores the controlling requirement identifiers. A row only becomes PASS after the linked executable test has actually run on the final SHA.

Source reviewed: draft PR #1. The Gemini-reported 295 backend / 68 frontend / 21 browser results predate subsequent review fixes and do not establish all acceptance groups. The direct GitHub corrections also have **not** been executed in a runnable local checkout in this audit.

| ID | Contract | Current release status | Required evidence |
|---|---|---|---|
| A01 | Wrong medication route/frequency fail per-attribute and strict record | NOT VERIFIED | Executable test + observed output required |
| A02 | Duplicate-name medication occurrences preserved and paired one-to-one | NOT VERIFIED | Executable test + observed output required |
| A03 | Unit-preserving vital/dose comparison | NOT VERIFIED | Executable test + observed output required |
| A04 | Atomic instruction omissions and contradictions | NOT VERIFIED | Executable test + observed output required |
| A05 | Dataset integrity: hashes, missing/orphan labels, exceptions | NOT VERIFIED | Executable test + observed output required |
| A06 | Zero-support N/A with raw counts | NOT VERIFIED | Executable test + observed output required |
| A07 | Benchmark and extraction provenance complete and versioned | NOT VERIFIED | Executable test + observed output required |
| A08 | Exact raw evidence spans and normalized mapping | NOT VERIFIED | Executable test + observed output required |
| A09 | Decimal dose and medication attribution boundaries | NOT VERIFIED | Executable test + observed output required |
| A10 | Negated/held/stopped/historical/conditional status | NOT VERIFIED | Executable test + observed output required |
| A11 | Vital conflicts and ambiguous metadata | NOT VERIFIED | Executable test + observed output required |
| A12 | Repeated instructions and narrative disambiguation | NOT VERIFIED | Executable test + observed output required |
| A13 | Additions persist through draft/reload/export | NOT VERIFIED | Executable test + observed output required |
| A14 | Child attribute versus full medication removal | NOT VERIFIED | Executable test + observed output required |
| A15 | All decisions and four explicit completeness acknowledgments | NOT VERIFIED | P0 server-authoritative review behavior still unverified |
| A16 | Stale source edit invalidates current completion and queue | NOT VERIFIED | Current queue-source binding has a direct source fix; needs runtime regression |
| A17 | Pipeline rerun requires new review | NOT VERIFIED | Executable test + observed output required |
| A18 | Real concurrent review writers use CAS | NOT VERIFIED | P0 separate-transaction concurrency/retry test required |
| A19 | Idempotent retry vs conflicting key | NOT VERIFIED | P0 separate-transaction concurrency/retry test required |
| A20 | Strict schema, decision-derived snapshot and spoof prevention | NOT VERIFIED | P0 server-authoritative review behavior still unverified |
| A21 | Cross-workspace authorization on every API | NOT VERIFIED | Executable test + observed output required |
| A22 | Preserving SQLite and PostgreSQL migration | NOT VERIFIED | P0/P1 populated migration validation required |
| A23 | Mixed PDF page-wise acquisition | NOT VERIFIED | Executable test + observed output required |
| A24 | OCR resource and failure handling | NOT VERIFIED | Executable test + observed output required |
| A25 | Optional provider and logging safety | NOT VERIFIED | Executable test + observed output required |
| A26 | Readiness checks DB/schema/core availability | NOT VERIFIED | Executable test + observed output required |
| A27 | Current-only metrics and correct denominators | NOT VERIFIED | Executable test + observed output required |
| A28 | Actionable dashboard URL drilldowns | NOT VERIFIED | Executable test + observed output required |
| A29 | Keyboard and accessibility behavior | NOT VERIFIED | Executable test + observed output required |
| A30 | Real offline workflow including backend restart | NOT VERIFIED | Executable test + observed output required |
| A31 | Independent failure/mitigation/regression loop | NOT VERIFIED | Executable test + observed output required |
| A32 | Clean checkout reproducibility | NOT VERIFIED | Executable test + observed output required |
| A33 | AI proposal cannot mutate reviewed state | NOT VERIFIED | Executable test + observed output required |
| A34 | AI/OCR disagreement preserves exact critical tokens | NOT VERIFIED | Executable test + observed output required |
| A35 | Text OCR evidence not treated as verified image evidence | NOT VERIFIED | Executable test + observed output required |
| A36 | Transcription correction invalidates review | NOT VERIFIED | Executable test + observed output required |
| A37 | AI claims without source coordinates rejected | NOT VERIFIED | Executable test + observed output required |
| A38 | Ollama missing/invalid output cannot corrupt NLP | NOT VERIFIED | Executable test + observed output required |
| A39 | Job leases, idempotency and restart recovery | NOT VERIFIED | Executable test + observed output required |
| A40 | Document image geometry persists | NOT VERIFIED | Executable test + observed output required |
| A41 | Exact review export manifests and scope | NOT VERIFIED | Executable test + observed output required |
| A42 | Hosted APIs reject free-text/upload/live inference | NOT VERIFIED | Executable test + observed output required |
| A43 | Recorded public-demo AI results labeled correctly | NOT VERIFIED | P1 model/version provenance required |
| A44 | Versioned benchmark case-level mismatch drilldowns | NOT VERIFIED | Executable test + observed output required |
| A45 | Handwriting critical-token benchmark | NOT VERIFIED | Executable test + observed output required |
| A46 | Populated UI accessibility and visual QA | NOT VERIFIED | Executable test + observed output required |
| A47 | No note source or secrets leaked via logs | NOT VERIFIED | Executable test + observed output required |
| A48 | Final independent Codex review applied to full final diff | NOT VERIFIED | Executable test + observed output required |

## Critical release gates

Original fixed canaries: **A01 A02 A03 A08 A09 A10 A13 A14 A16 A18 A20 A21 A22 A23**. Any failed, skipped or unexecuted critical gate blocks merge.

## Current source-level findings

- The original evaluator selects exact attribute pairings first; this biases strict counts and violates fixed occurrence matching (A01/A02/A07). Its run artifact does not prove comparable base/candidate results.
- The server stores client-provided `reviewed_snapshot` rather than deriving it from validated decisions; added medication and attribute removal paths still need complete round trips (A13/A14/A15/A20).
- Initial legacy `/api/validate` and destructive `PUT /api/notes/{id}/text` bypasses were removed in the feature branch during this audit; local tests have not been rerun (A16/A20).
- The current public workspace API does not yet verify the issued capability token on protected routes (A21/A42).
- `frontend/e2e` contains no dedicated new Validation Lab/source image/AI disagreement/export end-to-end suite despite previous PASS claims (A28/A30/A34/A35/A40–A46).
- The upload route still uses the legacy document-wide PDF OCR fallback, rather than the new `acquire_document` helper (A23/A24).
- This matrix must be filled with actual `test path::test_name`, fixture, command, exit code, test counts, and artifact link **after** verification. A prose claim, existing module, or pre-change run is not enough.
