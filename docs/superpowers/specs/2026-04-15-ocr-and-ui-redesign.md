# OCR Support + UI Redesign — Design Spec

**Date:** 2026-04-15
**Status:** Approved
**Project:** Clinical Notes NLP Assistant

---

## Context

Two improvements to the existing clinical notes app:

1. **OCR support** — the current upload path rejects scanned PDFs and images entirely. Users need to upload handwritten or photographed clinical notes (PNG/JPG/TIFF) and scanned PDFs that have no embedded text layer. Tesseract (via pytesseract) will provide local, cost-free OCR as a fallback.

2. **UI redesign** — the existing UI is functional but visually dense and hard to use as a reviewer. The primary pain points are: (a) no visual connection between highlighted spans in the note and the corresponding field cards on the right, (b) all field cards are equally visually heavy which makes the page busy, (c) no way to add a field the NLP missed. The redesign addresses all three in priority order.

Design direction: **Clean & Clinical** — dark nav bar (`#1e293b`), white card panels, left-border category color coding, slate/blue palette. No dark mode. No major layout changes — the two-pane reviewer stays.

---

## Part 1: OCR Backend

### Supported file types after this change

| Extension | Existing behaviour | New behaviour |
|---|---|---|
| `.txt` | ✓ text extraction | unchanged |
| `.pdf` (text layer) | ✓ PyMuPDF | unchanged |
| `.pdf` (image-only) | ✗ 400 error | ✓ Tesseract OCR fallback |
| `.png`, `.jpg`, `.jpeg`, `.tiff`, `.tif` | ✗ unsupported | ✓ Tesseract OCR |

### Backend changes

**`backend/utils/pdf.py`**
- `extract_text_from_pdf(filepath)` already raises `ValueError` when PyMuPDF finds fewer than 50 characters. Change: instead of raising, fall through to a new `_ocr_pdf(filepath) -> str` helper that converts each PDF page to an image (via `pdf2image`) and runs Tesseract on it, joining pages with `\n\n`.
- Add `extract_text_from_image(filepath: str) -> str` — runs Tesseract directly on a PNG/JPG/TIFF file.
- Both helpers raise `ValueError("OCR produced no readable text.")` if Tesseract output is under 50 characters after stripping.

**`backend/routes/upload.py`**
- Expand `_ALLOWED` to include `.png`, `.jpg`, `.jpeg`, `.tiff`, `.tif`.
- For image files: call `extract_text_from_image(tmp_path)`, set `source = "ocr"`.
- For PDF files: call `text, source = extract_text_from_pdf(tmp_path)` — the function returns a tuple and the route unpacks it directly. `source` will be `"pdf"` if PyMuPDF found a text layer, or `"ocr"` if Tesseract was used.
- The rest of the route (pipeline, persist, return) is unchanged.

**`backend/models/note.py`**
- `source` comment updated to `paste|txt|pdf|ocr|demo`. No schema migration needed — SQLite stores it as text.

**`requirements.txt`**
- Add `pytesseract>=0.3.10` and `pdf2image>=1.17.0`.
- Add a comment that `tesseract-ocr` and `poppler-utils` must be installed at the OS level (macOS: `brew install tesseract poppler`; Docker: apt packages).

**`Dockerfile`**
- Add `tesseract-ocr` and `poppler-utils` to the `apt-get install` line in Stage 2.

**`backend/utils/pdf.py` — full interface after change:**
```python
def extract_text_from_pdf(filepath: str) -> tuple[str, str]:
    """Returns (text, source) where source is 'pdf' or 'ocr'."""

def extract_text_from_image(filepath: str) -> str:
    """Returns OCR text from a PNG/JPG/TIFF image."""
```

### Error handling

- Tesseract not installed → catch `pytesseract.TesseractNotFoundError`, return `{"error": "OCR engine not available. Install tesseract-ocr.", "code": "OCR_UNAVAILABLE"}` with 503.
- OCR produces too little text → return `{"error": "OCR produced no readable text.", "code": "OCR_EMPTY"}` with 400.

### Frontend changes for OCR

**`frontend/src/pages/Home.tsx`**
- Drag-drop zone: update `accept=".txt,.pdf"` → `accept=".txt,.pdf,.png,.jpg,.jpeg,.tiff,.tif"`.
- Update the hint text to: "Drop a .txt, .pdf, or image file here, or click to browse".
- No other changes — `handleFile` calls `api.uploadFile` which already handles the rest.

**`frontend/src/components/StatusBadge.tsx` (or a new `SourceBadge`)**
- The Review page header already shows a source badge. Add `"ocr"` as a recognised source with a distinct teal/cyan treatment (`background: #0f172a; color: #38bdf8; border: 1px solid #164e63`).

---

## Part 2: UI Redesign

### Design system tokens (Tailwind classes throughout)

| Token | Value | Usage |
|---|---|---|
| Nav background | `bg-slate-800` (`#1e293b`) | Top bar on all pages |
| Page background | `bg-slate-50` | Body |
| Panel background | `bg-white` | Cards, panels |
| Body text | `text-slate-900` (`#0f172a`) | Note text, card values |
| Muted text | `text-slate-400` (`#94a3b8`) | Labels, hints |
| Border | `border-slate-200` | Card borders |
| Vitals accent | `border-l-blue-500` / `bg-blue-50` span | Left border + span highlight |
| Meds accent | `border-l-green-500` / `bg-green-100` span | |
| Instructions accent | `border-l-amber-400` / `bg-amber-100` span | |
| Metadata accent | `border-l-violet-400` / `bg-violet-100` span | |

### Global nav (all pages)

Replace the current white `<header>` with a dark slate bar:
```
bg-slate-800, text-slate-100, px-6 py-2.5
Left: "← Back" link (text-slate-500, hover text-slate-300) + page title (font-semibold text-white)
Right: contextual badges + nav links (text-slate-400, hover text-slate-200)
```

---

### Review page — detailed spec

This is the primary target of the redesign. The visual reference mockup is at `.superpowers/brainstorm/` (not committed). The spec text below is self-contained and fully specifies the implementation — the mockup file is supplementary only.

#### Left pane — NoteViewer

- **Section blocks:** The rendered note is split into semantic sections by a thin horizontal rule (`border-slate-100`) with a `9px uppercase tracking-widest text-slate-400` section label above each block (METADATA / VITALS / MEDICATIONS / INSTRUCTIONS). Sections are derived from the same Sectionizer output used for extraction — if sections are absent, the note renders as a single unsectioned block.
- **Typography:** `font-mono text-[11.5px] leading-[2] text-slate-900` — high contrast, generous line height, easy to scan.
- **Padding:** `px-5 py-3.5` per section block.
- **Span highlights:** unchanged category colors, bottom border `border-b-2` in category color. Non-highlighted text is the same high-contrast slate.
- **Active span (linked from hovered/selected field):** adds `ring-2 ring-offset-0` in the category color and `font-semibold`. CSS transition `transition-all duration-150`.
- **Cursor:** `cursor-pointer` on all spans. On click → emit `onSpanClick(fieldKey)` → Review parent scrolls right panel to that field and sets it as active.

#### Right pane — FieldEditor cards

**Four card states:**

**Active state uses the full-saturation version of the card's own category color — it does not override to blue.** A vitals card active = full-saturation blue; a meds card active = full-saturation green; instructions = amber; metadata = violet. The light/faded version of each category color is used for Pending state.

| State | Background | Left border | Label color | Value color | Buttons |
|---|---|---|---|---|---|
| Pending (inactive) | `bg-white` | category light (e.g. `border-blue-200` for vitals) | `text-slate-400` | `text-slate-700` | Hidden; appear on hover via `group-hover:flex` |
| Active (hovered/clicked) | category tint (e.g. `bg-blue-50/40` for vitals) | category full (e.g. `border-blue-500` for vitals) | category full text (e.g. `text-blue-600`) | `text-slate-800 font-medium` | Visible: Accept / Edit / ✕ |
| Accepted | `bg-green-50` | `border-l-green-500` | `text-green-300` | `text-green-800` | None; circled checkmark icon + "accepted" badge |
| Corrected | `bg-amber-50` | `border-l-amber-400` | `text-amber-600` | old value strikethrough + new value | "corrected" badge |

All cards: `rounded-lg border border-slate-200 px-3 py-2.5 transition-all duration-150`.

**Hover-to-reveal buttons:** wrap the card in `group`. The action buttons div uses `hidden group-hover:flex` so inactive cards are quiet but obviously clickable when hovered.

**Active card:** triggered by either (a) user hovering the card itself, or (b) `onSpanClick` from the left pane. Stored as `activeKey: string | null` in Review state. The active card renders with full saturation border, tinted background, and visible buttons. On mouse leave from the card, `activeKey` is cleared after a 200ms debounce (prevents flicker when moving between card and button).

**Span↔field linking — implementation:**
```
Review.tsx state:
  activeKey: string | null  (e.g. "vitals.blood_pressure")

NoteViewer props:
  activeKey: string | null
  onSpanClick: (key: string) => void

FieldEditor props:
  isActive: boolean
  onActivate: () => void   // fired on mouseEnter of the card div
  // No onDeactivate prop — deactivation is managed entirely by the Review parent.
  // On mouse leave from a card, Review clears activeKey after a 200ms debounce
  // (prevents flicker when the cursor moves from the card to its own action buttons).
  // FieldEditor does not need to signal deactivation — Review attaches the
  // onMouseLeave handler directly to the card wrapper element via a ref.
```
When `activeKey` changes, Review uses a `ref` map of card elements and calls `cardRefs[activeKey]?.scrollIntoView({ behavior: "smooth", block: "nearest" })`.

#### Add field

Each category section has a `+ Add [category]` row below its cards. Renders as a `border-dashed border-[category-light-color] rounded-lg` micro-card with:
- A `10px uppercase tracking-widest text-[category-muted]` label ("+ Add vital")
- A flex row: `<select>` of standard missing field names for that category + "custom..." option + `<input placeholder="value">` + `<button>Add</button>`
- On submit: inserts a new field into `fields` state with `status: "corrected"` (it's a manual addition, always a correction). The new field uses a synthetic key `vitals.custom_N` for custom fields.
- Standard field names per category:
  - Vitals: respiratory_rate, oxygen_saturation, weight (only show fields not already present). Renders as `<select>` of missing standard names + "custom…" + a single `<input placeholder="value">` + `<button>Add</button>`. On submit, key is `vitals.<selected_name>` for standard fields or `vitals.custom_<N>` for custom (where N increments per session).
  - Medications: no `<select>` — medications are multi-field entities. The Add row shows four labelled inputs side-by-side: `name` (required), `dose`, `route`, `frequency` (all optional). On submit, appends a new medication object to `fields` at key `med.<nextIndex>.name` etc., where `nextIndex = current highest med index + 1`. The `+ Add medication` label replaces the select.
  - Instructions: `<select>` of missing standard categories (discharge_instructions, follow_up, return_precautions) + single `<input placeholder="value">` + `<button>Add</button>`. Key: `instr.<selected_category>`.
  - Metadata: `<select>` of missing fields (patient_name, date_of_service, provider_name) + single `<input placeholder="value">` + `<button>Add</button>`. Key: `meta.<selected_field>`.

#### Footer

```
border-t border-slate-200 px-4 py-2.5 bg-white
Left: pill chip — border border-slate-100 bg-slate-50 rounded-md px-3 py-1 text-[11px]
  "N corrected | N accepted | N pending" with pipe separators, each count in its status color
Right: "Accept all" (border-green-200 text-green-700 bg-green-50) + "Save corrections" (bg-blue-600 text-white)
```

---

### Home page

- Dark nav bar (consistent with other pages).
- Textarea: `font-mono text-sm text-slate-900 leading-relaxed` — higher contrast than current.
- Drag-drop zone: updated hint text to include image formats.
- Upload processing: the loading button text is determined client-side by file type before the request is sent. If the dropped/selected file is an image (`.png`, `.jpg`, `.jpeg`, `.tiff`, `.tif`) or a PDF (since PDFs may silently fall back to OCR), show "Processing..." as the single loading label — do not attempt to distinguish "Extracting" vs "Running OCR" at runtime. The backend has no mid-request status endpoint and the distinction is not meaningful to the user.
- Source badge on the submit button area: after upload, before navigate, no change needed.

### History page

- Dark nav bar.
- Source column: add a `SourceBadge` component — small pill, color-coded: `txt` (slate), `pdf` (blue), `ocr` (teal/cyan), `paste` (gray), `demo` (purple).
- Table row click behavior unchanged.

### Metrics page

- Dark nav bar.
- No structural changes — charts and cards stay the same, just the nav styling updates.

---

## Files changed

### Backend (new/modified)
- `backend/utils/pdf.py` — OCR fallback, image support
- `backend/routes/upload.py` — new file types, source="ocr"
- `backend/models/note.py` — comment update
- `requirements.txt` — pytesseract, pdf2image
- `Dockerfile` — tesseract-ocr, poppler-utils apt packages

### Frontend (modified)
- `frontend/src/pages/Home.tsx` — accept images, updated hint text, dark nav
- `frontend/src/pages/Review.tsx` — activeKey state, span↔field linking, scrollIntoView, add-field logic
- `frontend/src/pages/History.tsx` — dark nav, SourceBadge
- `frontend/src/pages/Metrics.tsx` — dark nav
- `frontend/src/components/NoteViewer.tsx` — active span ring, section block rendering, onSpanClick callback
- `frontend/src/components/FieldEditor.tsx` — four card states, group-hover buttons, isActive prop
- `frontend/src/components/SourceBadge.tsx` — new component (txt/pdf/ocr/paste/demo)

### Tests
- `backend/tests/test_routes_upload.py` — add tests for PNG/JPG/TIFF upload, OCR fallback path for scanned PDF, `source="ocr"` persisted correctly
- `backend/tests/test_ocr.py` — unit tests for `extract_text_from_image`, `_ocr_pdf` (mock pytesseract)
- `frontend/src/FieldEditor.test.tsx` — add test for isActive prop rendering

---

## Constraints and non-goals

- No new API endpoints. All changes are within the existing routes.
- No changes to the NLP pipeline, evaluation, or data model schema.
- No LLM dependency. OCR is local Tesseract only.
- No dark mode. Design direction A is light workspace + dark nav only.
- No multi-page pagination in the reviewer. Single-note review stays as-is.
- OCR quality is inherently limited by image quality. No pre-processing (deskewing, denoising) in scope.
