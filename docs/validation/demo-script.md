# Software Engineering Demonstration Script

This demonstration script is designed for an end-to-end walkthrough of the Clinical Notes NLP Assistant & Validation Workbench. It highlights software engineering decisions: identifying failure modes, establishing immutable lineage, enforcing independent verification, and building ergonomic reviewer interfaces.

---

## The Engineering Narrative (Portfolio Framing)

> *"In clinical NLP systems, high aggregate benchmark scores often mask dangerous edge cases—like dropped decimal points or misaligned negation. Rather than treating NLP output as a black box, this workbench treats extraction as an untrusted proposal. Every entity is bound to immutable character spans, checked by independent validation canaries, verified through human review with optimistic concurrency control, and sealed in a cryptographic export bundle."*

---

## Timed v1 walkthrough (about 5 minutes)

Use `data/validation_loop/v1_synthetic_note.txt`. Say explicitly that extraction is deterministic and that an independent check is not a clinical conclusion.

1. **0:00–0:30.** Show the synthetic-only notice on the upload page. State the path: source text, extraction proposal, independent check, human correction, immutable history.
2. **0:30–1:15.** Paste the fixture and open Review. Show two metformin orders, warfarin `2.5 mg`, held lisinopril, blood pressure, and the follow-up line. A field that looks right is still only a proposal.
3. **1:15–2:00.** Open Issues. The checker flags `A02_DUPLICATE_MEDICATION_CONFLICT` and `A10_NON_ACTIVE_MEDICATION` from the real extraction. Mention `data/validation_loop/v1_injected_counterexample.json` as a planted `.5 mg` / mismatched quote, not an extractor result. The checker reports `A09_DECIMAL_DOSE_LEADING_ZERO_MISSING` and `A08_EVIDENCE_QUOTE_MISMATCH` on that copy.
4. **2:00–2:45.** Edit the warfarin dose, acknowledge all four categories, save, and reload. The correction remains. The original extraction row is not rewritten.
5. **2:45–3:30.** Open Metrics, drill into the open warning, and land on this note and issue. Then use Update Transcription. The prior completion is no longer current. Replaying the old review request returns `409 STALE_REVIEW`.
6. **3:30–4:15.** Open Validation Lab for the 20-note development corpus, then Showcase for the frozen 24-image aggregate. Explain TP/FP/FN, why duplicate-aware matching matters, and why those two datasets are not one score. Qwen OCR is N/A because that arm did not produce a transcription score.
7. **4:15–5:00.** Point at one regression: an idempotent replay after a source change must not look like a current completion (`test_idempotent_replay_after_source_change_is_not_current_completion`). State the limits: synthetic data, no clinician validation, handwriting recognition not in the v1 claim. Real clinical use would need a different data policy, clinician review, and a deployment the owner has not approved.

Record the build SHA with `git rev-parse HEAD` before a screen recording. Keep large video files outside git and note the path in `docs/validation/V1_RELEASE_EVIDENCE.md`.

## Step-by-Step Demonstration Flow

### Step 1: Health Probes & Workspace Isolation
1. **Show liveness & readiness**:
   - Navigate to `http://127.0.0.1:5000/api/health/live` and `/api/health/ready`.
   - Point out: Separate probes verify that the application server is responsive and the database connection is healthy.
2. **Explain Workspace Isolation**:
   - Open two browser tabs or private windows.
   - Point out: Each reviewer receives a unique workspace authenticated via a cryptographic capability token (`X-Session-ID`). Seeded demo notes or review state in Tab 1 do not bleed into Tab 2.

### Step 2: Ingestion & Content-Addressed Storage
1. **Navigate to Upload page** (`http://localhost:5173/`):
   - Click **"Load sample note"** to load synthetic patient text into the editor.
   - Point out: The document is hashed (SHA-256) upon arrival, creating a content-addressed source asset.
2. **Click "Extract & Review"**:
   - The deterministic medSpaCy + regex pipeline processes the note and redirects to the Review workbench.

### Step 3: Source Span Grounding & Keyboard Review
1. **Interactive Review Workspace**:
   - Point to the split-screen UI: Note source on the left, structured entities on the right.
   - Click on the medication `metformin 500 mg PO BID`.
   - Show how the exact character span in the clinical note highlights in green.
2. **Keyboard Ergonomics**:
   - Press <kbd>Tab</kbd> to activate the next field.
   - Press <kbd>A</kbd> to Accept the field.
   - Show the progress bar updating dynamically in the header (`1 of 20 fields reviewed`).
   - Press <kbd>E</kbd> to inline-edit a field, type a correction, and save.

### Step 4: Quality Canaries & Operational Issues Drawer
1. **Click the "Issues" button in the review header**:
   - The slide-out Operational Issues Drawer opens.
   - Point out the active checks:
     - Span quote verification (`A08`)
     - Decimal dose formatting canaries (`A09`)
     - Missing vital sign units (`A03`)
     - Duplicate medication conflicts (`A02`)
2. **Explain the safety invariant**:
   - Critical blockers prevent final review completion until the reviewer acknowledges or dismisses them with a recorded rationale.

### Step 5: Source Text Revision & Immutability Chain
1. **Click "Update Transcription (Rev 1)"**:
   - The Transcription Revision modal appears.
   - Explain: In real workflows, OCR or audio transcription errors occur. If a reviewer fixes source text, we must NOT silently overwrite history.
   - Enter a correction (e.g. adjust a dosage) and provide a reason.
   - Submitting creates **Revision 2**, invalidates previous extractions, and resets the review baseline while preserving Revision 1 in the immutable event log.

### Step 6: Server-Derived Disposition & Cryptographic Export
1. **Complete Review & Save**:
   - Press <kbd>⌘S</kbd> or click **"Save corrections"**.
   - Explain the state machine:
     - The client sends item decisions and parent event ID.
     - The server verifies `lock_version` to prevent concurrent overwrite.
     - The server algorithmically derives the final outcome (`reviewed_unchanged` vs `reviewed_corrected`).
2. **Download Export Bundle**:
   - Click **"Export Reviewed (ZIP)"**.
   - Unpack the archive to inspect its contents:
     - `reviewed_extraction.json`
     - `original_extraction.json`
     - `item_decisions.json`
     - `manifest.json` (SHA-256 digests)
     - `summary.html` (Self-contained standalone report)

### Step 7: Validation Lab & Offline Strict Evaluation
1. **Navigate to "Validation Lab"** (`/validation-lab`):
   - Click **"Run Strict Evaluation"**.
   - Watch the offline benchmark execute across the 20 synthetic reference notes.
2. **Discuss Statistical Rigor**:
   - Explain **source-occurrence-first pairing**: the scorer pairs medications that share a source occurrence, then assigns any remaining same-name items one-to-one by span overlap. It does not use the Hungarian algorithm, and it does not pick the dose that would make the score look better. That matters when one note contains two orders for the same drug.
   - Highlight attribute-level scoring: Distinguishing between full match, dose mismatch, and route omission.
   - Point out the case-by-case error attribution table (TP, FP, FN) that helps engineers locate specific failure cases rather than relying on aggregate metrics.
