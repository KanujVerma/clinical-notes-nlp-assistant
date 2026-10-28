# Software Engineering Demonstration Script

This demonstration script is designed for an end-to-end walkthrough of the Clinical Notes NLP Assistant & Validation Workbench. It highlights software engineering decisions: identifying failure modes, establishing immutable lineage, enforcing independent verification, and building ergonomic reviewer interfaces.

---

## The Engineering Narrative (Portfolio Framing)

> *"In clinical NLP systems, high aggregate benchmark scores often mask dangerous edge cases—like dropped decimal points or misaligned negation. Rather than treating NLP output as a black box, this workbench treats extraction as an untrusted proposal. Every entity is bound to immutable character spans, checked by independent validation canaries, verified through human review with optimistic concurrency control, and sealed in a cryptographic export bundle."*

---

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
   - Explain the **Multiset Pairwise Alignment**: Using the Hungarian algorithm to match predicted medications to ground truth prevents false score inflation from greedy name matching.
   - Highlight attribute-level scoring: Distinguishing between full match, dose mismatch, and route omission.
   - Point out the case-by-case error attribution table (TP, FP, FN) that helps engineers locate specific failure cases rather than relying on aggregate metrics.
