# UX Overhaul & OCR Improvements — Design Spec

**Date:** 2026-04-16
**Status:** Draft
**Builds on:** `2026-04-15-clinical-notes-nlp-assistant-design.md`, `2026-04-15-ocr-and-ui-redesign.md`

---

## Context

The core app (extraction pipeline, review UI, persistence, evaluation) is fully implemented and working. However, the user experience feels disconnected — four independent pages with no shared navigation, no post-save guidance, and no clear workflow through the pipeline. OCR uses default Tesseract settings with zero preprocessing, producing garbage on anything but pristine printed text. The tool needs to feel like a real internal clinical annotation tool, not a collection of disconnected pages.

**Goals:**
- Transform the app from "4 disconnected pages" into a unified annotation workstation
- Make the upload → review → save → next cycle seamless
- Improve OCR quality for printed/typed documents with graceful degradation for handwriting
- Add professional review UX features inspired by Prodigy, Label Studio, and CLAMP
- Surface live pipeline accuracy metrics from reviewer corrections

**Non-goals:**
- Handwriting OCR support (show limitation message instead)
- Cloud OCR integration (keep it local-first)
- Auth, multi-user, or deployment changes

---

## 1. Unified Sidebar Shell

**Replace** the current 4-page structure (each page with its own `<header>` and `<a>` tags) with a persistent sidebar layout component.

### Layout

```
┌──────────┬─────────────────────────────────────┐
│ Sidebar  │  Top bar (context for current view)  │
│          ├─────────────────────────────────────┤
│ Upload   │                                     │
│ Queue(n) │  Main content area                  │
│ History  │  (Upload / Review / History / etc.)  │
│ Metrics  │                                     │
│          ├─────────────────────────────────────┤
│ Pending: │  Footer (review actions)             │
│  note_1  │                                     │
│  note_2  │                                     │
└──────────┴─────────────────────────────────────┘
```

### Sidebar sections

- **Pipeline** group: Upload, Queue (with pending count badge)
- **Data** group: History, Metrics
- **Pending Review** list (below nav): shows the queue of unreviewed notes by filename/ID, with the currently active note highlighted. Clicking a note in this list navigates to its review.

### Implementation

- New `AppShell.tsx` layout component wrapping all routes
- React Router `<Link>` components replace all `<a href>` tags (eliminates full page reloads)
- Active nav item highlighted with left border + accent color
- Sidebar is always visible; main content area renders the active route
- Mobile: sidebar collapses to a hamburger menu (not critical for portfolio but should degrade gracefully)

### Routes (updated)

| Route | View | Notes |
|---|---|---|
| `/` | Upload | Batch file drop zone + paste textarea |
| `/queue` | Queue list | Pending unreviewed notes; click → Review |
| `/review/:noteId` | Review | The core review pane |
| `/review/:noteId/preview` | OCR Preview | Conditional; for low-confidence OCR |
| `/history` | History | All notes, paginated |
| `/metrics` | Metrics | Eval + live accuracy |

Remove the bare `/review` route (currently used for router state passing). All review access goes through `/review/:noteId`. After upload, navigate to `/review/:noteId` (or `/review/:noteId/preview` for OCR documents).

---

## 2. Queue & "Save & Next" Flow

### Queue behavior

- **Entering the queue:** Any note that has an extraction but no validation is "pending" and appears in the queue. New uploads are automatically pending. Notes in the OCR preview state (uploaded but user hasn't clicked "Proceed") also appear in the queue — there is no separate "needs OCR review" state. The queue is simply "extracted but not validated."
- **Queue ordering:** FIFO by `created_at` (oldest first).
- **Queue count:** Sidebar badge shows count of pending notes. Updated reactively after save.
- **Queue view (`/queue`):** A focused list of pending notes with filename, source badge, and created date. Clicking a row opens it in Review.

### Save & Next

After the reviewer clicks "Save" on the Review page:
1. `POST /validate` persists the validation.
2. The queue count decrements.
3. **Auto-advance:** If there are more pending notes, navigate to `/review/:nextNoteId` with a brief "Saved — loading next note" transition. The "next" note is the oldest pending note by `created_at`.
4. **Queue empty:** If no pending notes remain, show an "All reviewed" state with links to History and Metrics.

### Backend changes

- `GET /api/queue` — new endpoint. Returns `{ notes: [{id, filename, source, created_at}], count: int }`. Filters notes that have an extraction but no validation, ordered by `created_at ASC`.
- `POST /validate` response — add `next_pending_id: int | null` to the response body so the frontend can navigate without a second request.

---

## 3. Batch Upload

### Frontend

Replace the current single-file upload with a batch-capable drop zone:
- Accept multiple files via drag-and-drop or file picker (`multiple` attribute)
- Show a file list with per-file status indicators (queued → processing → done / error)
- Process files sequentially (to avoid overloading the backend)
- Include a "Cancel remaining" button that aborts the sequential upload loop; already-uploaded files remain in the queue
- On completion, show summary ("5 notes uploaded, 1 failed") and a "Start Reviewing →" button that navigates to `/review/:firstNoteId`

### Backend

- `POST /api/upload` remains single-file. The frontend calls it once per file.
- `POST /api/upload` response — add `raw_text` to the response body so the frontend doesn't need a second `GET /history/:id` call after upload.

### Paste path

Keep the textarea paste on the Upload page. "Extract & Review" button calls `POST /api/notes`, then navigates to Review.

---

## 4. OCR Improvements

### Scope

Officially support: text-layer PDFs, `.txt` files, scanned printed/typed documents. Handwritten notes are best-effort with a clear limitation message.

### Image preprocessing (`backend/utils/pdf.py`)

Add a `_preprocess_image(img: PIL.Image) -> PIL.Image` function applied before Tesseract:
1. **Convert to grayscale** (`img.convert("L")`)
2. **Contrast enhancement + binarization** (`ImageOps.autocontrast` then threshold via `img.point()`)
3. **Deskew** — detect skew angle via Tesseract's OSD (`pytesseract.image_to_osd`) and rotate to correct. If `image_to_osd` raises `TesseractError` (common on sparse text or mostly-blank pages), skip the deskew step and proceed with the un-rotated image.
4. **Noise removal** — median filter for salt-and-pepper noise

Use Pillow's `ImageFilter` and `ImageOps.autocontrast` for binarization — no OpenCV dependency. Keep the dependency footprint minimal.

### Tesseract configuration

Pass explicit config to `pytesseract.image_to_string` and `image_to_data`:
- `--psm 6` (assume uniform block of text) for full-page scans
- `--oem 1` (LSTM neural net mode)
- `-l eng` (explicit language)

### Confidence scoring

Use `pytesseract.image_to_data(output_type=Output.DICT)` instead of `image_to_string`. This returns per-word confidence scores. Compute an aggregate confidence as the mean of word-level confidences (excluding -1 values which indicate non-text regions).

### Updated function signatures

- `extract_text_from_pdf(filepath) -> tuple[str, str, float | None]` — returns `(text, source, ocr_confidence)`. `ocr_confidence` is `None` when `source == "pdf"` (text-layer extraction), and a `0.0–1.0` float when `source == "ocr"` (Tesseract fallback).
- `extract_text_from_image(filepath) -> tuple[str, float]` — returns `(text, ocr_confidence)`.
- `_ocr_pdf(filepath) -> tuple[str, float]` — returns `(text, ocr_confidence)`.

**Call site update:** `upload.py` must be updated to unpack the new tuple signatures from both functions.

Store `ocr_confidence` on the `Note` model (nullable float, only set for OCR sources).

### Conditional OCR Preview

The OCR preview step is shown **conditionally**, not for every upload:

| Condition | Behavior |
|---|---|
| `.txt` file or text-layer PDF (source = `pdf`) | Skip preview, go straight to Review |
| OCR (from PDF fallback or image) with confidence ≥ 0.7 | Skip preview, go straight to Review |
| OCR (from PDF fallback or image) with confidence < 0.7 | Show OCR Preview page |

Image files always go through OCR and follow the same confidence threshold as OCR PDFs. There is no "always show preview" rule — confidence is the sole gate.

### OCR Preview page (`/review/:noteId/preview`)

Single-pane layout (original files are not persisted after upload, so no side-by-side with the original document):
- **OCR confidence indicator** at the top showing the score (e.g., "OCR Confidence: 52%") with a color-coded bar.
- **Extracted text** in an editable textarea. User can fix OCR errors before NLP runs.
- **Warning banner** (if confidence < 0.7): "OCR confidence is low. The extracted text may contain errors. Handwritten notes are not fully supported — best results with typed/printed documents."
- **Actions:** "Proceed to Extraction →" (saves edited text via `PUT /api/notes/:id/text`, which re-runs NLP, then navigates to Review). "Skip to Review →" (proceed with current extraction without editing).

**Pipeline execution timing:** The upload endpoint (`POST /api/upload`) always runs the pipeline immediately at upload time, even for low-confidence OCR. This means every uploaded note has an extraction and appears in the queue. If the user edits OCR text on the preview page and clicks "Proceed," the `PUT /api/notes/:id/text` endpoint replaces `raw_text` and re-runs the pipeline, deleting the stale extraction. This is intentionally simple — the wasted initial extraction is cheap, and it avoids a "no extraction yet" code path.

### Backend changes

- `POST /api/upload` response — add `ocr_confidence: float | null` to the response.
- New `PUT /api/notes/:id/text` — updates `raw_text` on an existing note and re-runs the extraction pipeline. The existing `Extraction` row for this note is deleted and replaced with a new row containing the updated `extracted_json` and `pipeline_version`. Returns `{note_id, extracted_json}`. Used by the OCR Preview "Proceed" action after text edits.
- `Note` model — add `ocr_confidence` column (Float, nullable).

---

## 5. Review UX Enhancements

### Keyboard shortcuts

Global key bindings active when the Review page is focused:

| Key | Action |
|---|---|
| `A` | Accept the currently active field |
| `E` | Enter edit mode for the active field |
| `R` | Remove the active field |
| `Escape` | Cancel edit / deselect active field |
| `Tab` | Move to next field |
| `Shift+Tab` | Move to previous field |
| `Ctrl/Cmd+S` | Save review |
| `Ctrl/Cmd+→` | Save & advance to next note |

Implementation: `useEffect` with `keydown` listener on the Review page. All keyboard shortcuts (including Tab/Shift+Tab for field navigation) are disabled when an input, textarea, or select element is focused, so native form navigation and typing are not disrupted. Show a subtle shortcut hint strip below the top bar in muted text: `A Accept · E Edit · R Remove · Tab Next · ⌘S Save`.

### Review progress bar

Top bar shows: **"8 of 14 extracted fields reviewed"** with a thin progress bar underneath.

A field counts as "reviewed" when its status is anything other than `pending` (accepted, corrected, or removed).

### Diff view for corrections

When a field has been corrected, the FieldEditor card shows:
```
✎ CORRECTED
temperature
  98.6°F  →  96.8°F
  ~~~~~~~~    (strikethrough on original, bold on new)
```

Store `original_value` alongside `draft_value` in the field state so the diff can be rendered. The original value comes from the extraction; the draft is the user's edit.

### Undo for accepted fields

Add an "Undo" action on accepted field cards (currently terminal with no revert). Clicking undo returns the field to `pending` status.

### Re-review awareness

When opening an already-validated note from History:
- Load both `extracted_json` and `validated_json` from the note detail
- **Reconstruct per-field statuses by diffing:** compare each field in `extracted_json` vs `validated_json`. If a field exists in both with the same value → `accepted`. If the value differs → `corrected` (show diff). If a field exists in `validated_json` but not `extracted_json` → `corrected` (added by reviewer). If a field exists in `extracted_json` but not `validated_json` → `removed`. This avoids needing to store per-field status metadata.
- Show a banner: "This note was previously reviewed. You can re-review and save again."
- **Accumulate review time:** Frontend loads the existing `review_duration_ms` from the validation record on mount. The elapsed timer starts from this value so the display and the final `POST /validate` payload reflect cumulative time across review sessions.

### Unsaved changes warning

Before navigating away from Review with unsaved changes (any field status changed from its initial state), show a browser `beforeunload` confirmation dialog.

---

## 6. Metrics — Live Pipeline Accuracy

### Correction rate by category

New section on the Metrics page: **"Pipeline Accuracy (from reviewer corrections)"**

For each field category (vitals, medications, instructions, metadata), compute:
- **Correction rate:** `fields_corrected / fields_reviewed` — "medications are corrected 42% of the time"
- **Most-corrected fields:** within vitals, which specific field (e.g., `temperature`) is corrected most often
- **Acceptance rate:** `fields_accepted / fields_reviewed` — the inverse signal

Display as a horizontal bar chart with correction rate per category, plus a detail table showing per-field correction rates.

### Backend

- `GET /api/metrics` — expand the `db_stats` section to include per-category and per-field correction rates. Compute by comparing `extracted_json` vs `validated_json` across all validated notes.

### Review activity improvements

- Add loading and error states (currently fails silently)
- Show "No review data yet" empty state with guidance to upload and review notes

---

## 7. Navigation & Polish Fixes

These are the smaller but important UX fixes identified during exploration:

1. **React Router `<Link>` everywhere** — replace all `<a href>` tags with `<Link to>` across all pages. No more full-page reloads.
2. **Back-navigation context** — Review page "Back" should go to the referring page (History if opened from History, Queue if opened from Queue, Upload if just uploaded). Use `location.state.from` or `useNavigate(-1)`.
3. **Post-save next actions** — covered by "Save & Next" (Section 2).
4. **History pagination** — add pagination UI using the existing `page` param support in the API client.
5. **Seed demo data** — replace `window.alert()` with an inline toast notification and auto-navigate to Queue after seeding.
6. **Source badge on paste path** — ensure `source: "paste"` is included in router state when navigating from the paste upload path.
7. **Upload response includes `raw_text`** — eliminate the double API call on file upload (covered in Section 3).

---

## Data Model Changes

```sql
-- Add to notes table
ALTER TABLE notes ADD COLUMN ocr_confidence REAL NULL;

-- No changes to extractions or validations tables
```

The `source` column on `notes` has no SQL CHECK constraint; the existing code already writes `'ocr'` as a source value (added in the OCR feature). Valid values are enforced at the application level.

---

## New API Endpoints Summary

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/queue` | GET | Pending unreviewed notes list + count |
| `/api/notes/:id/text` | PUT | Update OCR text + re-extract |

### Modified endpoints

| Endpoint | Change |
|---|---|
| `POST /api/upload` | Add `raw_text` and `ocr_confidence` to response |
| `POST /api/validate` | Add `next_pending_id` to response |
| `GET /api/metrics` | Expand `db_stats` with per-category correction rates |

---

## New & Modified Frontend Files

| File | Change |
|---|---|
| `AppShell.tsx` | **New.** Sidebar layout wrapper for all routes |
| `App.tsx` | Refactor routes to nest inside `AppShell`; remove bare `/review` route; add `/queue` and `/review/:noteId/preview` |
| `pages/Upload.tsx` | **Rename from Home.tsx.** Batch drop zone, multi-file status, paste textarea |
| `pages/Queue.tsx` | **New.** Pending notes list view |
| `pages/Review.tsx` | Keyboard shortcuts, progress bar, diff view, undo, re-review awareness, unsaved warning, "Save & Next" |
| `pages/OcrPreview.tsx` | **New.** Single-pane OCR preview with editable text and confidence indicator |
| `pages/History.tsx` | Add pagination UI, use `<Link>` |
| `pages/Metrics.tsx` | Add correction rate section, loading/error states |
| `components/FieldEditor.tsx` | Diff view rendering, undo on accepted, keyboard shortcut targets |
| `components/NoteViewer.tsx` | No major changes |
| `components/SourceBadge.tsx` | No changes |
| `api/client.ts` | Add `getQueue()`, `updateNoteText()`, update response types |
| `types.ts` | Add `QueueResponse`, `OcrPreviewState`, update `UploadResponse` |

---

## Verification Checklist

1. **Sidebar shell:** All pages render inside the sidebar layout. Active nav item is highlighted. Sidebar pending list updates after saves.
2. **Batch upload:** Drop 3 files → all 3 appear in Queue with correct source badges. Failed files show error inline.
3. **Queue flow:** Queue shows pending count. Click note → Review. "Save & Next →" advances to next pending. Empty queue shows "all reviewed" state.
4. **OCR preview:** Upload a scanned PDF → OCR preview shown if confidence < 0.7. Edit text → "Proceed" → Review shows corrected text. Upload a text-layer PDF → skip preview, go straight to Review.
5. **Keyboard shortcuts:** On Review, press Tab to navigate fields, A to accept, E to edit, R to remove, Ctrl+S to save. Shortcuts disabled when editing a text input.
6. **Progress bar:** Shows "X of Y extracted fields reviewed." Updates as fields are accepted/corrected/removed.
7. **Diff view:** Correct a field → card shows strikethrough original → new value.
8. **Re-review:** Save a review → go to History → click the note → Review loads with saved validation state, not reset to pending.
9. **Unsaved changes:** Correct a field → click sidebar nav → browser warns about unsaved changes.
10. **Metrics:** Shows correction rate per category from validated notes. Loading and error states work.
11. **Navigation:** All links use React Router (no full reloads). Back button returns to referring page.
12. **Existing tests pass:** `pytest backend/tests/` and `npm test` in `frontend/` still pass.
13. **Docker build succeeds.**

---

## Critical Files

### Backend (modify)
- `backend/utils/pdf.py` — preprocessing, confidence scoring, Tesseract config
- `backend/routes/upload.py` — add `raw_text` and `ocr_confidence` to response
- `backend/routes/validate.py` — add `next_pending_id` to response
- `backend/routes/metrics.py` — expand correction rate stats
- `backend/models/note.py` — add `ocr_confidence` column

### Backend (new)
- `backend/routes/queue.py` — new queue endpoint

### Frontend (modify)
- `frontend/src/App.tsx` — route restructure
- `frontend/src/pages/Review.tsx` — keyboard shortcuts, progress, diff, re-review, unsaved warning
- `frontend/src/pages/History.tsx` — pagination, `<Link>`
- `frontend/src/pages/Metrics.tsx` — correction rates, loading/error states
- `frontend/src/components/FieldEditor.tsx` — diff view, undo
- `frontend/src/api/client.ts` — new endpoints, updated types
- `frontend/src/types.ts` — new types

### Frontend (new)
- `frontend/src/components/AppShell.tsx` — sidebar layout
- `frontend/src/pages/Upload.tsx` — batch upload (rename from Home.tsx)
- `frontend/src/pages/Queue.tsx` — pending review list
- `frontend/src/pages/OcrPreview.tsx` — conditional OCR preview
