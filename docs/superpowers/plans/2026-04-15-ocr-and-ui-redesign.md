# OCR Support + UI Redesign — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Tesseract OCR for scanned PDFs and images, then redesign the reviewer UI with span↔field hover linking, per-category card states, and a consistent dark nav across all pages.

**Architecture:** OCR is a pure backend change in `pdf.py` and `upload.py` — no new API endpoints. The UI redesign is additive: `Review.tsx` gains `activeKey` state shared bidirectionally with `NoteViewer` (span clicks) and `FieldEditor` (hover), enabling live span↔field linking without prop-drilling beyond the direct parent.

**Tech Stack:** Python 3.11 + pytesseract + pdf2image (OCR); React 18 + TypeScript + Tailwind CSS v3 + Vite 5 (frontend); Vitest v1 + @testing-library/react (frontend tests); pytest (backend tests).

---

## File map

| File | Change | Responsibility |
|---|---|---|
| `backend/utils/pdf.py` | Full rewrite | `extract_text_from_pdf` → returns tuple; `_ocr_pdf` helper; new `extract_text_from_image` |
| `backend/routes/upload.py` | Full rewrite | Unpack tuple, handle image extensions, OCR error codes |
| `backend/models/note.py` | Comment only | Document `ocr` as valid source value |
| `requirements.txt` | Add deps | pytesseract, pdf2image, pillow |
| `Dockerfile` | Add apt packages | tesseract-ocr, poppler-utils |
| `backend/tests/test_ocr.py` | Create | Unit tests for `extract_text_from_pdf`, `extract_text_from_image` (mocked) |
| `backend/tests/test_routes_upload.py` | Extend | OCR-specific upload tests |
| `frontend/src/components/SourceBadge.tsx` | Create | Color-coded source pill: txt/pdf/ocr/paste/demo |
| `frontend/src/components/FieldEditor.tsx` | Full rewrite | 4 card states, `isActive`/`onActivate` props, category colors, group-hover buttons |
| `frontend/src/components/NoteViewer.tsx` | Full rewrite | Section headers, `activeKey` ring, `onSpanClick` callback, `fieldKey` on each span |
| `frontend/src/pages/Review.tsx` | Full rewrite | `activeKey` state, debounced deactivation, `cardRefs` + scrollIntoView, `AddFieldRow`, dark nav |
| `frontend/src/pages/Home.tsx` | Targeted edits | Dark nav, image file accept, "Processing…" label |
| `frontend/src/pages/History.tsx` | Targeted edits | Dark nav, SourceBadge in source column |
| `frontend/src/pages/Metrics.tsx` | Targeted edits | Dark nav only |
| `frontend/src/FieldEditor.test.tsx` | Extend | Add `isActive` rendering tests |

---

## Chunk 1: OCR Backend

### Task 1: Rewrite `backend/utils/pdf.py`

**Files:**
- Modify: `backend/utils/pdf.py` (full rewrite, currently 12 lines)
- Create: `backend/tests/test_ocr.py`

- [ ] **Step 1: Write failing tests — create `backend/tests/test_ocr.py`**

```python
# backend/tests/test_ocr.py
import pytest
from unittest.mock import patch, MagicMock


class TestExtractTextFromPdf:
    def test_returns_pdf_source_when_text_layer_present(self, tmp_path):
        """PyMuPDF finds text → returns (text, 'pdf') without calling OCR."""
        pdf_path = str(tmp_path / "test.pdf")
        long_text = "Patient: Jane Smith\nBP 120/80\n" * 4  # well over 50 chars
        with patch("utils.pdf.fitz.open") as mock_open, \
             patch("utils.pdf._ocr_pdf") as mock_ocr:
            mock_doc = MagicMock()
            mock_page = MagicMock()
            mock_page.get_text.return_value = long_text
            mock_doc.__iter__ = lambda s: iter([mock_page])
            mock_doc.close = MagicMock()
            mock_open.return_value = mock_doc
            text, source = extract_text_from_pdf(pdf_path)
        assert source == "pdf"
        assert "Jane Smith" in text
        mock_ocr.assert_not_called()

    def test_returns_ocr_source_when_no_text_layer(self, tmp_path):
        """PyMuPDF finds < 50 chars → falls back to OCR, returns ('text', 'ocr')."""
        pdf_path = str(tmp_path / "scan.pdf")
        ocr_text = "Patient: Jane Smith\nBP 120/80\n" * 4
        with patch("utils.pdf.fitz.open") as mock_open, \
             patch("utils.pdf._ocr_pdf") as mock_ocr:
            mock_doc = MagicMock()
            mock_page = MagicMock()
            mock_page.get_text.return_value = "   "
            mock_doc.__iter__ = lambda s: iter([mock_page])
            mock_doc.close = MagicMock()
            mock_open.return_value = mock_doc
            mock_ocr.return_value = ocr_text
            text, source = extract_text_from_pdf(pdf_path)
        assert source == "ocr"
        assert "Jane Smith" in text

    def test_raises_if_ocr_produces_no_text(self, tmp_path):
        pdf_path = str(tmp_path / "blank.pdf")
        with patch("utils.pdf.fitz.open") as mock_open, \
             patch("utils.pdf._ocr_pdf") as mock_ocr:
            mock_doc = MagicMock()
            mock_page = MagicMock()
            mock_page.get_text.return_value = ""
            mock_doc.__iter__ = lambda s: iter([mock_page])
            mock_doc.close = MagicMock()
            mock_open.return_value = mock_doc
            mock_ocr.return_value = "   "
            with pytest.raises(ValueError, match="no readable text"):
                extract_text_from_pdf(pdf_path)


class TestExtractTextFromImage:
    def test_returns_ocr_text_for_valid_image(self, tmp_path):
        img_path = str(tmp_path / "note.png")
        ocr_text = "BP 120/80\nHR 76\n" * 4
        with patch("utils.pdf.Image") as mock_Image, \
             patch("utils.pdf.pytesseract") as mock_tess:
            mock_Image.open.return_value = MagicMock()
            mock_tess.image_to_string.return_value = ocr_text
            text = extract_text_from_image(img_path)
        assert "BP" in text

    def test_raises_if_ocr_produces_no_text(self, tmp_path):
        img_path = str(tmp_path / "blank.png")
        with patch("utils.pdf.Image") as mock_Image, \
             patch("utils.pdf.pytesseract") as mock_tess:
            mock_Image.open.return_value = MagicMock()
            mock_tess.image_to_string.return_value = "  "
            with pytest.raises(ValueError, match="no readable text"):
                extract_text_from_image(img_path)


# Deferred import so tests can patch before import
from utils.pdf import extract_text_from_pdf, extract_text_from_image  # noqa: E402
```

- [ ] **Step 2: Run tests — expect ImportError (function doesn't exist yet)**

```bash
cd /Users/kanuj/clinical-notes-nlp-assistant
source .venv/bin/activate
python -m pytest backend/tests/test_ocr.py -v 2>&1 | head -20
```
Expected: `ImportError: cannot import name 'extract_text_from_image'`

- [ ] **Step 3: Rewrite `backend/utils/pdf.py`**

```python
# backend/utils/pdf.py
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from pdf2image import convert_from_path

_MIN_TEXT_LEN = 50


def _ocr_pdf(filepath: str) -> str:
    """Convert each PDF page to an image and run Tesseract OCR on it."""
    images = convert_from_path(filepath)
    pages = [pytesseract.image_to_string(img) for img in images]
    return "\n\n".join(pages)


def extract_text_from_pdf(filepath: str) -> tuple[str, str]:
    """Extract text from a PDF file.

    Returns:
        (text, source) where source is 'pdf' when a text layer was found,
        or 'ocr' when Tesseract was used as a fallback.

    Raises:
        ValueError: if both PyMuPDF and OCR produce fewer than 50 characters.
        pytesseract.TesseractNotFoundError: if tesseract binary is not installed.
    """
    doc = fitz.open(filepath)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    if len(text.strip()) >= _MIN_TEXT_LEN:
        return text, "pdf"
    # Fall back to Tesseract OCR
    ocr_text = _ocr_pdf(filepath)
    if len(ocr_text.strip()) < _MIN_TEXT_LEN:
        raise ValueError("OCR produced no readable text.")
    return ocr_text, "ocr"


def extract_text_from_image(filepath: str) -> str:
    """Run Tesseract OCR on a PNG/JPG/TIFF image file.

    Raises:
        ValueError: if Tesseract output is under 50 characters after stripping.
        pytesseract.TesseractNotFoundError: if tesseract binary is not installed.
    """
    img = Image.open(filepath)
    text = pytesseract.image_to_string(img)
    if len(text.strip()) < _MIN_TEXT_LEN:
        raise ValueError("OCR produced no readable text.")
    return text
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
python -m pytest backend/tests/test_ocr.py -v
```
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/utils/pdf.py backend/tests/test_ocr.py
git commit -m "feat: add OCR support in pdf.py — Tesseract fallback for scanned PDFs, image extraction"
```

---

### Task 2: Rewrite `backend/routes/upload.py`

**Files:**
- Modify: `backend/routes/upload.py` (full rewrite, currently 51 lines)
- Modify: `backend/tests/test_routes_upload.py` (add OCR tests)

- [ ] **Step 1: Add OCR tests to `backend/tests/test_routes_upload.py`**

Add `import io` at the top if not already present. Then append this class:

```python
# Add at bottom of backend/tests/test_routes_upload.py
import io
import pytesseract
from unittest.mock import patch


class TestUploadOCR:
    def test_png_upload_returns_201(self, client):
        """PNG upload with mocked OCR returns 201 and note_id."""
        fake_text = "Patient: Test\nBP 120/80\n" * 4
        with patch("routes.upload.extract_text_from_image", return_value=fake_text):
            resp = client.post(
                "/api/upload",
                data={"file": (io.BytesIO(b"fakepng"), "note.png")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 201
        assert "note_id" in resp.get_json()

    def test_jpg_upload_returns_201(self, client):
        fake_text = "Patient: Test\nBP 120/80\n" * 4
        with patch("routes.upload.extract_text_from_image", return_value=fake_text):
            resp = client.post(
                "/api/upload",
                data={"file": (io.BytesIO(b"fakejpg"), "note.jpg")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 201

    def test_scanned_pdf_returns_201_with_ocr_source(self, client):
        """PDF with no text layer: extract_text_from_pdf returns ('text', 'ocr').
        The response must include source='ocr' so the frontend can display the badge."""
        fake_text = "Patient: Test\nBP 120/80\n" * 4
        with patch("routes.upload.extract_text_from_pdf", return_value=(fake_text, "ocr")):
            resp = client.post(
                "/api/upload",
                data={"file": (io.BytesIO(b"%PDF"), "scan.pdf")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 201
        assert resp.get_json()["source"] == "ocr"

    def test_docx_returns_400_unsupported(self, client):
        resp = client.post(
            "/api/upload",
            data={"file": (io.BytesIO(b"data"), "note.docx")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "UNSUPPORTED_FILE_TYPE"

    def test_tesseract_not_found_returns_503(self, client):
        with patch("routes.upload.extract_text_from_image",
                   side_effect=pytesseract.TesseractNotFoundError()):
            resp = client.post(
                "/api/upload",
                data={"file": (io.BytesIO(b"fakepng"), "note.png")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 503
        assert resp.get_json()["code"] == "OCR_UNAVAILABLE"

    def test_ocr_empty_returns_400(self, client):
        with patch("routes.upload.extract_text_from_image",
                   side_effect=ValueError("OCR produced no readable text.")):
            resp = client.post(
                "/api/upload",
                data={"file": (io.BytesIO(b"fakepng"), "note.png")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "OCR_EMPTY"
```

- [ ] **Step 2: Run new tests — expect failures**

```bash
python -m pytest backend/tests/test_routes_upload.py::TestUploadOCR -v
```
Expected: failures (`.png` currently rejected as unsupported file type).

- [ ] **Step 3: Rewrite `backend/routes/upload.py`**

```python
# backend/routes/upload.py
import json
import os
import tempfile

import pytesseract
from flask import Blueprint, g, jsonify, request

from config import Config
from extractors.pipeline import run_pipeline
from models.extraction import Extraction
from models.note import Note
from utils.pdf import extract_text_from_image, extract_text_from_pdf

bp = Blueprint("upload", __name__)

_ALLOWED = {".txt", ".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tiff", ".tif"}


@bp.post("/api/upload")
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided", "code": "NO_FILE"}), 400

    f = request.files["file"]
    ext = os.path.splitext(f.filename or "")[1].lower()
    if ext not in _ALLOWED:
        return jsonify(
            {"error": f"Unsupported file type: {ext}", "code": "UNSUPPORTED_FILE_TYPE"}
        ), 400

    if ext == ".pdf":
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            f.save(tmp.name)
            try:
                text, source = extract_text_from_pdf(tmp.name)
            except ValueError as e:
                return jsonify({"error": str(e), "code": "OCR_EMPTY"}), 400
            except pytesseract.TesseractNotFoundError:
                return jsonify({
                    "error": "OCR engine not available. Install tesseract-ocr.",
                    "code": "OCR_UNAVAILABLE",
                }), 503
            finally:
                os.unlink(tmp.name)

    elif ext in _IMAGE_EXTS:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            f.save(tmp.name)
            try:
                text = extract_text_from_image(tmp.name)
                source = "ocr"
            except ValueError as e:
                return jsonify({"error": str(e), "code": "OCR_EMPTY"}), 400
            except pytesseract.TesseractNotFoundError:
                return jsonify({
                    "error": "OCR engine not available. Install tesseract-ocr.",
                    "code": "OCR_UNAVAILABLE",
                }), 503
            finally:
                os.unlink(tmp.name)

    else:  # .txt
        text = f.read().decode("utf-8", errors="replace")
        source = "txt"

    extracted = run_pipeline(text)

    note = Note(filename=f.filename, raw_text=text, source=source)
    g.db.add(note)
    g.db.flush()

    extraction = Extraction(
        note_id=note.id,
        extracted_json=json.dumps(extracted),
        pipeline_version=Config.PIPELINE_VERSION,
    )
    g.db.add(extraction)
    g.db.commit()

    return jsonify({"note_id": note.id, "extracted_json": extracted, "source": source}), 201
```

- [ ] **Step 4: Run all upload tests**

```bash
python -m pytest backend/tests/test_routes_upload.py -v
```
Expected: all pass (existing + new OCR tests).

- [ ] **Step 5: Commit**

```bash
git add backend/routes/upload.py backend/tests/test_routes_upload.py
git commit -m "feat: extend upload route — image files (.png/.jpg/.tiff), OCR source, 503 for missing tesseract"
```

---

### Task 3: Dependencies and Dockerfile

**Files:**
- Modify: `requirements.txt`
- Modify: `Dockerfile`
- Modify: `backend/models/note.py` (comment only)

- [ ] **Step 1: Update `requirements.txt`**

Add after `pymupdf==1.24.3`:
```
pytesseract>=0.3.10
pdf2image>=1.17.0
pillow>=10.0.0
```

Add at the very top as a comment block:
```
# System deps required for OCR:
#   macOS:  brew install tesseract poppler
#   Docker: apt-get install -y tesseract-ocr poppler-utils  (handled in Dockerfile)
```

- [ ] **Step 2: Update `Dockerfile` — add tesseract-ocr and poppler-utils**

In Stage 2, find the `apt-get install` line and add the two packages:

```dockerfile
# Before:
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libmupdf-dev \
    && rm -rf /var/lib/apt/lists/*

# After:
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libmupdf-dev \
    tesseract-ocr poppler-utils \
    && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 3: Update `backend/models/note.py` comment**

Change the inline comment on the `source` column:
```python
# Before:
source = Column(String, nullable=False)  # paste|txt|pdf|demo

# After:
source = Column(String, nullable=False)  # paste|txt|pdf|ocr|demo
```

- [ ] **Step 4: Install new Python deps locally**

```bash
source .venv/bin/activate
pip install "pytesseract>=0.3.10" "pdf2image>=1.17.0" "pillow>=10.0.0"
```

Verify Tesseract binary is available:
```bash
tesseract --version
```
If not installed: `brew install tesseract poppler`

- [ ] **Step 5: Run full backend test suite — no regressions**

```bash
python -m pytest backend/tests/ -v --tb=short
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt Dockerfile backend/models/note.py
git commit -m "chore: add pytesseract/pdf2image deps, tesseract-ocr+poppler to Dockerfile"
```

---

## Chunk 2: Frontend Components

### Task 4: Create `SourceBadge` component

**Files:**
- Create: `frontend/src/components/SourceBadge.tsx`

- [ ] **Step 1: Create the file**

```tsx
// frontend/src/components/SourceBadge.tsx
const BADGE_STYLES: Record<string, string> = {
  txt:   "bg-slate-100 text-slate-600 border-slate-200",
  pdf:   "bg-blue-50 text-blue-600 border-blue-200",
  ocr:   "bg-slate-900 text-sky-400 border-cyan-800",
  paste: "bg-gray-100 text-gray-500 border-gray-200",
  demo:  "bg-purple-50 text-purple-600 border-purple-200",
};

export default function SourceBadge({ source }: { source: string }) {
  const style = BADGE_STYLES[source] ?? "bg-slate-100 text-slate-500 border-slate-200";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider border ${style}`}>
      {source}
    </span>
  );
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd /Users/kanuj/clinical-notes-nlp-assistant/frontend
npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/SourceBadge.tsx
git commit -m "feat: add SourceBadge component (txt/pdf/ocr/paste/demo)"
```

---

### Task 5: Redesign `FieldEditor` — four states, category colors, isActive, group-hover

**Files:**
- Modify: `frontend/src/components/FieldEditor.tsx` (full rewrite)
- Modify: `frontend/src/FieldEditor.test.tsx` (add isActive tests)

The card has four visually distinct states:
- **Pending inactive**: white bg, light category left border, label `text-slate-400`, value `text-slate-700`; action buttons hidden (`hidden group-hover:flex`); "click to review" hint visible
- **Pending active** (`isActive=true`): category-tinted bg, full-saturation left border, category label color; buttons visible
- **Accepted**: green tinted bg, circled checkmark badge, no buttons
- **Corrected**: amber tinted bg, "corrected" badge, no buttons (value shown, editable inline)
- **Removed**: gray+strikethrough, restore link

Left border color is applied via inline `style={{ borderLeft: "3px solid <color>" }}` because Tailwind v3 does not support directional border-color utilities.

- [ ] **Step 1: Add isActive tests to `frontend/src/FieldEditor.test.tsx`**

Append to the existing test file (update imports to include the new props):

```tsx
// Append to frontend/src/FieldEditor.test.tsx
it("shows action buttons when isActive is true", () => {
  render(
    <FieldEditor
      label="bp"
      value="138/88"
      status="pending"
      category="vitals"
      isActive={true}
      onActivate={vi.fn()}
      onChange={vi.fn()}
    />
  );
  expect(screen.getByRole("button", { name: /accept/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /edit/i })).toBeInTheDocument();
});

it("renders value text when isActive is false", () => {
  render(
    <FieldEditor
      label="bp"
      value="138/88"
      status="pending"
      category="vitals"
      isActive={false}
      onActivate={vi.fn()}
      onChange={vi.fn()}
    />
  );
  expect(screen.getByTestId("field-value")).toHaveTextContent("138/88");
});

it("shows accepted state with no action buttons", () => {
  render(
    <FieldEditor
      label="bp"
      value="138/88"
      status="accepted"
      category="vitals"
      isActive={false}
      onActivate={vi.fn()}
      onChange={vi.fn()}
    />
  );
  expect(screen.queryByRole("button", { name: /accept/i })).not.toBeInTheDocument();
  expect(screen.getByText(/accepted/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests — expect failures (new props don't exist yet)**

```bash
cd /Users/kanuj/clinical-notes-nlp-assistant/frontend
npm test 2>&1 | tail -20
```

- [ ] **Step 3: Rewrite `frontend/src/components/FieldEditor.tsx`**

```tsx
// frontend/src/components/FieldEditor.tsx
import { useState } from "react";

export type FieldStatus = "accepted" | "corrected" | "removed" | "pending";
export type FieldCategory = "vitals" | "med" | "instr" | "meta";

interface Props {
  label: string;
  value: string;
  status: FieldStatus;
  category: FieldCategory;
  isActive: boolean;
  onActivate: () => void;
  onChange: (value: string, status: FieldStatus) => void;
}

// Left border color per category, inactive vs active
// Uses inline style because Tailwind v3 has no directional border-color utilities
const CAT_BORDER: Record<FieldCategory, { inactive: string; active: string }> = {
  vitals: { inactive: "#93c5fd", active: "#3b82f6" },
  med:    { inactive: "#86efac", active: "#22c55e" },
  instr:  { inactive: "#fcd34d", active: "#f59e0b" },
  meta:   { inactive: "#c4b5fd", active: "#8b5cf6" },
};

const CAT_ACTIVE_BG: Record<FieldCategory, string> = {
  vitals: "bg-blue-50",
  med:    "bg-green-50",
  instr:  "bg-amber-50",
  meta:   "bg-violet-50",
};

const CAT_LABEL_ACTIVE: Record<FieldCategory, string> = {
  vitals: "text-blue-600",
  med:    "text-green-600",
  instr:  "text-amber-600",
  meta:   "text-violet-600",
};

export default function FieldEditor({
  label, value, status, category, isActive, onActivate, onChange,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  // --- REMOVED ---
  if (status === "removed") {
    return (
      <div
        className="rounded-lg border border-slate-100 px-3 py-2.5 opacity-50 bg-white"
        style={{ borderLeft: "3px solid #cbd5e1" }}
      >
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">{label}</span>
          <button onClick={() => onChange(value, "accepted")} className="text-[10px] text-blue-500 hover:underline">
            restore
          </button>
        </div>
        <p className="mt-1 text-sm text-slate-400 line-through">{value}</p>
      </div>
    );
  }

  // --- ACCEPTED ---
  if (status === "accepted") {
    return (
      <div
        className="rounded-lg border border-green-100 px-3 py-2.5 bg-green-50"
        style={{ borderLeft: "3px solid #22c55e" }}
      >
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold uppercase tracking-widest text-green-300">{label}</span>
          <span className="flex items-center gap-1 text-[10px] text-green-600">
            <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
              <circle cx="6" cy="6" r="5.5" stroke="#16a34a" strokeWidth="1" />
              <path d="M3.5 6l1.8 1.8 3-3.6" stroke="#16a34a" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            accepted
          </span>
        </div>
        <p className="mt-1 text-sm text-green-800">{value}</p>
      </div>
    );
  }

  // --- CORRECTED ---
  if (status === "corrected") {
    function save() {
      setEditing(false);
      onChange(draft, draft !== value ? "corrected" : "accepted");
    }
    return (
      <div
        className="rounded-lg border border-amber-100 px-3 py-2.5 bg-amber-50"
        style={{ borderLeft: "3px solid #f59e0b" }}
      >
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold uppercase tracking-widest text-amber-600">{label}</span>
          <span className="text-[10px] text-amber-600">corrected</span>
        </div>
        {editing ? (
          <div className="mt-1 flex gap-2">
            <input value={draft} onChange={(e) => setDraft(e.target.value)}
              className="flex-1 border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-amber-400" />
            <button onClick={save} className="text-[10px] px-3 py-1 bg-amber-500 text-white rounded hover:bg-amber-600">save</button>
            <button onClick={() => { setEditing(false); setDraft(value); }} className="text-[10px] px-2 py-1 border border-slate-300 rounded hover:bg-slate-50">cancel</button>
          </div>
        ) : (
          <p className="mt-1 text-sm text-slate-700 cursor-pointer hover:opacity-80" onClick={() => setEditing(true)}
            data-testid="field-value">{draft}</p>
        )}
      </div>
    );
  }

  // --- PENDING (inactive or active) ---
  function save() {
    setEditing(false);
    onChange(draft, draft !== value ? "corrected" : "accepted");
  }

  return (
    <div
      className={`group rounded-lg border border-slate-200 px-3 py-2.5 transition-all duration-150 cursor-pointer
        ${isActive ? CAT_ACTIVE_BG[category] : "bg-white"}`}
      style={{ borderLeft: `3px solid ${CAT_BORDER[category][isActive ? "active" : "inactive"]}` }}
      onMouseEnter={onActivate}
    >
      <div className="flex items-center justify-between min-h-[20px]">
        <span className={`text-[10px] font-semibold uppercase tracking-widest
          ${isActive ? CAT_LABEL_ACTIVE[category] : "text-slate-400"}`}>
          {label}
        </span>
        {/* Action buttons: always shown when active; revealed on group-hover when inactive */}
        <div className={`flex gap-1 ${isActive ? "flex" : "hidden group-hover:flex"}`}>
          <button onClick={(e) => { e.stopPropagation(); onChange(value, "accepted"); }}
            className="text-[10px] px-2 py-0.5 bg-white text-green-600 border border-green-200 rounded hover:bg-green-50">
            ✓ Accept
          </button>
          <button onClick={(e) => { e.stopPropagation(); setEditing(true); }}
            className="text-[10px] px-2 py-0.5 bg-white text-slate-500 border border-slate-200 rounded hover:bg-slate-50">
            Edit
          </button>
          <button onClick={(e) => { e.stopPropagation(); onChange(value, "removed"); }}
            className="text-[10px] px-2 py-0.5 bg-white text-red-500 border border-red-100 rounded hover:bg-red-50">
            ✕
          </button>
        </div>
        {/* "click to review" hint — hidden when active or on hover */}
        {!isActive && (
          <span className="text-[10px] text-slate-300 group-hover:hidden">click to review</span>
        )}
      </div>
      {editing ? (
        <div className="mt-1 flex gap-2">
          <input value={draft} onChange={(e) => setDraft(e.target.value)}
            className="flex-1 border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400" />
          <button onClick={save} className="text-[10px] px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700">save</button>
          <button onClick={() => { setEditing(false); setDraft(value); }} className="text-[10px] px-2 py-1 border border-slate-300 rounded hover:bg-slate-50">cancel</button>
        </div>
      ) : (
        <p className="mt-1 text-sm text-slate-700" data-testid="field-value">{draft}</p>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run frontend tests — expect all pass**

```bash
npm test
```
Expected: all tests pass.

- [ ] **Step 5: TypeScript check**

```bash
npx tsc --noEmit
```
Expected: errors in `Review.tsx` (missing `category`, `isActive`, `onActivate` props) — these are fixed in Task 7. That is expected at this stage.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/FieldEditor.tsx frontend/src/FieldEditor.test.tsx
git commit -m "feat: redesign FieldEditor — 4 card states, isActive, category colors, group-hover buttons"
```

---

### Task 6: Redesign `NoteViewer` — section headers, active span ring, onSpanClick

**Files:**
- Modify: `frontend/src/components/NoteViewer.tsx` (full rewrite)

The NoteViewer now takes `activeKey` and `onSpanClick` props. Each span stores a `fieldKey` matching the `FieldMap` keys in `Review.tsx` (`vitals.blood_pressure`, `med.0.name`, etc.). Section headers are inserted before the first span of each category in document order.

- [ ] **Step 1: Rewrite `frontend/src/components/NoteViewer.tsx`**

```tsx
// frontend/src/components/NoteViewer.tsx
import { ExtractionResult } from "../types";

interface Span {
  start: number;
  end: number;
  category: "vitals" | "medications" | "instructions" | "metadata";
  fieldKey: string;  // matches FieldMap key: "vitals.bp", "med.0.name", "instr.follow_up", "meta.patient_name"
  label: string;     // human-readable, for title attribute
}

const CAT_BG: Record<string, string> = {
  vitals:       "bg-blue-100 text-blue-900",
  medications:  "bg-green-100 text-green-900",
  instructions: "bg-amber-100 text-amber-900",
  metadata:     "bg-violet-100 text-violet-900",
};

const CAT_BORDER_B: Record<string, string> = {
  vitals:       "border-blue-500",
  medications:  "border-green-500",
  instructions: "border-amber-400",
  metadata:     "border-violet-400",
};

const CAT_RING: Record<string, string> = {
  vitals:       "ring-blue-400",
  medications:  "ring-green-400",
  instructions: "ring-amber-300",
  metadata:     "ring-violet-400",
};

const SECTION_LABEL: Record<string, string> = {
  metadata:     "METADATA",
  vitals:       "VITALS",
  medications:  "MEDICATIONS",
  instructions: "INSTRUCTIONS",
};

function collectSpans(extracted: ExtractionResult): Span[] {
  const spans: Span[] = [];

  Object.entries(extracted.vitals).forEach(([k, v]) => {
    if (v?.span) spans.push({
      start: v.span[0], end: v.span[1],
      category: "vitals", fieldKey: `vitals.${k}`, label: k,
    });
  });

  extracted.medications.forEach((m, i) => {
    if (m?.span) spans.push({
      start: m.span[0], end: m.span[1],
      category: "medications", fieldKey: `med.${i}.name`, label: m.name,
    });
  });

  Object.entries(extracted.instructions).forEach(([k, v]) => {
    if (v?.span) spans.push({
      start: v.span[0], end: v.span[1],
      category: "instructions", fieldKey: `instr.${k}`, label: k,
    });
  });

  Object.entries(extracted.metadata).forEach(([k, v]) => {
    if (v?.span) spans.push({
      start: v.span[0], end: v.span[1],
      category: "metadata", fieldKey: `meta.${k}`, label: k,
    });
  });

  return spans.sort((a, b) => a.start - b.start);
}

interface Props {
  rawText: string;
  extracted: ExtractionResult;
  activeKey: string | null;
  onSpanClick: (fieldKey: string) => void;
}

export default function NoteViewer({ rawText, extracted, activeKey, onSpanClick }: Props) {
  const spans = collectSpans(extracted);
  const parts: JSX.Element[] = [];
  const seenCategories = new Set<string>();
  let pos = 0;

  for (const span of spans) {
    // Insert section divider on first occurrence of each category (in document order)
    if (!seenCategories.has(span.category)) {
      seenCategories.add(span.category);
      parts.push(
        <div key={`section-${span.category}`} className="border-t border-slate-100 mt-3 pt-2 mb-1">
          <span className="text-[9px] font-bold uppercase tracking-[0.15em] text-slate-400">
            {SECTION_LABEL[span.category]}
          </span>
        </div>
      );
    }

    // Plain text before this span
    if (span.start > pos) {
      parts.push(<span key={`text-${pos}`}>{rawText.slice(pos, span.start)}</span>);
    }

    // Highlighted span
    if (span.end > span.start) {
      const isActive = activeKey === span.fieldKey;
      parts.push(
        <mark
          key={`mark-${span.start}`}
          title={`${span.category}: ${span.label}`}
          onClick={() => onSpanClick(span.fieldKey)}
          className={[
            "rounded px-0.5 border-b-2 cursor-pointer transition-all duration-150",
            CAT_BG[span.category],
            CAT_BORDER_B[span.category],
            isActive ? `ring-2 ring-offset-0 ${CAT_RING[span.category]} font-semibold` : "",
          ].join(" ")}
        >
          {rawText.slice(span.start, span.end)}
        </mark>
      );
      pos = span.end;
    }
  }

  // Remaining text after last span
  if (pos < rawText.length) {
    parts.push(<span key="text-end">{rawText.slice(pos)}</span>);
  }

  return (
    <div className="h-full overflow-y-auto px-5 py-3.5 font-mono text-[11.5px] leading-[2] text-slate-900 whitespace-pre-wrap">
      {parts}
    </div>
  );
}
```

- [ ] **Step 2: TypeScript check — expect errors only in Review.tsx**

```bash
npx tsc --noEmit 2>&1 | grep -v "Review.tsx"
```
Expected: no errors outside of `Review.tsx`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/NoteViewer.tsx
git commit -m "feat: redesign NoteViewer — section headers, active span ring, onSpanClick callback"
```

---

## Chunk 3: Pages

### Task 7: Rewrite `Review.tsx` — activeKey state, span↔field linking, add-field, dark nav

**Files:**
- Modify: `frontend/src/pages/Review.tsx` (full rewrite)

This resolves the TypeScript errors from Tasks 5 and 6. Key additions:
- `activeKey` state — set by span clicks and card hover; cleared by debounced mouse-leave
- `cardRefs` — a `ref` map of `HTMLDivElement` per field key, used for `scrollIntoView`
- `AddFieldRow` — inline component (only used in this file) handling medications' 4-input form and other categories' select+input form
- `source` state — passed from navigation state or note detail, shown as a badge in the dark nav

- [ ] **Step 1: Rewrite `frontend/src/pages/Review.tsx`**

```tsx
// frontend/src/pages/Review.tsx
import { useState, useEffect, useRef, useCallback } from "react";
import { useLocation, useParams } from "react-router-dom";
import { api } from "../api/client";
import { ExtractionResult } from "../types";
import NoteViewer from "../components/NoteViewer";
import FieldEditor, { FieldStatus, FieldCategory } from "../components/FieldEditor";

type FieldState = { value: string; status: FieldStatus };
type FieldMap = Record<string, FieldState>;

function getCategoryFromKey(key: string): FieldCategory {
  const prefix = key.split(".")[0];
  if (prefix === "vitals") return "vitals";
  if (prefix === "med") return "med";
  if (prefix === "instr") return "instr";
  return "meta";
}

const CATEGORY_DISPLAY: Record<FieldCategory, string> = {
  vitals: "Vitals", med: "Medications", instr: "Instructions", meta: "Metadata",
};

const CATEGORY_PREFIX: Record<FieldCategory, string> = {
  vitals: "vitals.", med: "med.", instr: "instr.", meta: "meta.",
};

const CATEGORIES: FieldCategory[] = ["vitals", "med", "instr", "meta"];

// Standard field names per category (for the add-field select dropdown)
const STD_FIELDS: Record<FieldCategory, string[]> = {
  vitals: ["respiratory_rate", "oxygen_saturation", "weight"],
  med:    [],  // medications use a multi-input form
  instr:  ["discharge_instructions", "follow_up", "return_precautions"],
  meta:   ["patient_name", "date_of_service", "provider_name"],
};

const CAT_DASHED_BORDER: Record<FieldCategory, string> = {
  vitals: "border-blue-200",
  med:    "border-green-200",
  instr:  "border-amber-200",
  meta:   "border-violet-200",
};

const CAT_LABEL_COLOR: Record<FieldCategory, string> = {
  vitals: "text-blue-400",
  med:    "text-green-400",
  instr:  "text-amber-400",
  meta:   "text-violet-400",
};

function AddFieldRow({
  category,
  existingKeys,
  onAdd,
}: {
  category: FieldCategory;
  existingKeys: string[];
  onAdd: (key: string, value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState("");
  const [value, setValue] = useState("");
  const [medName, setMedName] = useState("");
  const [medDose, setMedDose] = useState("");
  const [medRoute, setMedRoute] = useState("");
  const [medFreq, setMedFreq] = useState("");
  const customCount = useRef(0);

  // Only show standard fields not already in the fields map
  const categoryKeyPrefix = category === "instr" ? "instr" : category === "meta" ? "meta" : category;
  const availableStdFields = STD_FIELDS[category].filter(
    (f) => !existingKeys.includes(`${categoryKeyPrefix}.${f}`)
  );

  function handleAdd() {
    if (category === "med") {
      if (!medName.trim()) return;
      const medIndices = existingKeys
        .filter((k) => k.startsWith("med.") && /^med\.\d+\.name$/.test(k))
        .map((k) => parseInt(k.split(".")[1]));
      const nextIdx = medIndices.length > 0 ? Math.max(...medIndices) + 1 : 0;
      onAdd(`med.${nextIdx}.name`, medName.trim());
      if (medDose.trim()) onAdd(`med.${nextIdx}.dose`, medDose.trim());
      if (medRoute.trim()) onAdd(`med.${nextIdx}.route`, medRoute.trim());
      if (medFreq.trim()) onAdd(`med.${nextIdx}.frequency`, medFreq.trim());
      setMedName(""); setMedDose(""); setMedRoute(""); setMedFreq("");
    } else {
      if (!value.trim()) return;
      const fieldName = selected === "custom" || !selected
        ? `custom_${++customCount.current}`
        : selected;
      onAdd(`${categoryKeyPrefix}.${fieldName}`, value.trim());
      setValue(""); setSelected("");
    }
    setOpen(false);
  }

  const addLabel = category === "med" ? "Add Medication" : `Add ${CATEGORY_DISPLAY[category].replace(/s$/, "")}`;

  return (
    <div className={`rounded-lg border-2 border-dashed ${CAT_DASHED_BORDER[category]} px-3 py-2.5`}>
      {!open ? (
        <button
          onClick={() => setOpen(true)}
          className={`text-[10px] font-semibold uppercase tracking-widest ${CAT_LABEL_COLOR[category]} hover:opacity-70 transition-opacity`}
        >
          + {addLabel}
        </button>
      ) : category === "med" ? (
        <div>
          <p className={`text-[10px] font-semibold uppercase tracking-widest mb-2 ${CAT_LABEL_COLOR[category]}`}>
            + Add Medication
          </p>
          <div className="grid grid-cols-4 gap-1.5 mb-2">
            {[
              { ph: "name *", val: medName, set: setMedName },
              { ph: "dose", val: medDose, set: setMedDose },
              { ph: "route", val: medRoute, set: setMedRoute },
              { ph: "frequency", val: medFreq, set: setMedFreq },
            ].map(({ ph, val, set }) => (
              <input key={ph} placeholder={ph} value={val} onChange={(e) => set(e.target.value)}
                className="text-[11px] px-2 py-1.5 border border-slate-200 rounded focus:outline-none focus:ring-1 focus:ring-green-400" />
            ))}
          </div>
          <div className="flex gap-2">
            <button onClick={handleAdd} className="text-[11px] px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700 font-medium">Add</button>
            <button onClick={() => setOpen(false)} className="text-[11px] px-3 py-1 border border-slate-200 rounded hover:bg-slate-50">Cancel</button>
          </div>
        </div>
      ) : (
        <div>
          <p className={`text-[10px] font-semibold uppercase tracking-widest mb-2 ${CAT_LABEL_COLOR[category]}`}>
            + {addLabel}
          </p>
          <div className="flex gap-2 items-center">
            <select value={selected} onChange={(e) => setSelected(e.target.value)}
              className="text-[11px] px-2 py-1.5 border border-slate-200 rounded bg-white focus:outline-none focus:ring-1 focus:ring-blue-400 flex-shrink-0">
              <option value="">field…</option>
              {availableStdFields.map((f) => <option key={f} value={f}>{f}</option>)}
              <option value="custom">custom…</option>
            </select>
            <input placeholder="value" value={value} onChange={(e) => setValue(e.target.value)}
              className="flex-1 text-[11px] px-2 py-1.5 border border-slate-200 rounded focus:outline-none focus:ring-1 focus:ring-blue-400" />
            <button onClick={handleAdd}
              className="text-[11px] px-3 py-1.5 bg-blue-600 text-white rounded hover:bg-blue-700 font-medium whitespace-nowrap">
              Add
            </button>
            <button onClick={() => setOpen(false)} className="text-[11px] px-2 py-1.5 border border-slate-200 rounded hover:bg-slate-50">✕</button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function Review() {
  const location = useLocation();
  const { noteId } = useParams();
  const startTime = useRef(Date.now());

  const [rawText, setRawText] = useState("");
  const [extracted, setExtracted] = useState<ExtractionResult | null>(null);
  const [noteIdState, setNoteIdState] = useState<number | null>(null);
  const [source, setSource] = useState("");
  const [fields, setFields] = useState<FieldMap>({});
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);

  const deactivateTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // Timer
  useEffect(() => {
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - startTime.current) / 1000)), 1000);
    return () => clearInterval(id);
  }, []);

  // Load data from nav state or API
  useEffect(() => {
    const state = location.state as {
      note_id?: number; extracted_json?: ExtractionResult; raw_text?: string; source?: string;
    } | null;
    if (state?.extracted_json) {
      setRawText(state.raw_text ?? "");
      setExtracted(state.extracted_json);
      setNoteIdState(state.note_id ?? null);
      setSource(state.source ?? "");
    } else if (noteId) {
      api.getNoteDetail(Number(noteId)).then((d) => {
        setRawText(d.raw_text);
        setExtracted(d.extracted_json);
        setNoteIdState(d.id);
        setSource(d.source ?? "");
      });
    }
  }, [noteId, location.state]);

  // Flatten extracted JSON into FieldMap
  useEffect(() => {
    if (!extracted) return;
    const m: FieldMap = {};
    Object.entries(extracted.vitals).forEach(([k, v]) => {
      if (v) m[`vitals.${k}`] = { value: v.value, status: "pending" };
    });
    extracted.medications.forEach((med, i) => {
      m[`med.${i}.name`] = { value: med.name, status: "pending" };
      if (med.dose) m[`med.${i}.dose`] = { value: med.dose, status: "pending" };
      if (med.route) m[`med.${i}.route`] = { value: med.route, status: "pending" };
      if (med.frequency) m[`med.${i}.frequency`] = { value: med.frequency, status: "pending" };
    });
    Object.entries(extracted.instructions).forEach(([k, v]) => {
      if (v) m[`instr.${k}`] = { value: v.value, status: "pending" };
    });
    Object.entries(extracted.metadata).forEach(([k, v]) => {
      if (v) m[`meta.${k}`] = { value: v.value, status: "pending" };
    });
    setFields(m);
  }, [extracted]);

  // Scroll active card into view when activeKey changes
  useEffect(() => {
    if (activeKey && cardRefs.current[activeKey]) {
      cardRefs.current[activeKey]!.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [activeKey]);

  // Activate a field (from span click or card hover)
  const handleActivate = useCallback((key: string) => {
    if (deactivateTimeout.current) clearTimeout(deactivateTimeout.current);
    setActiveKey(key);
  }, []);

  // Deactivate after 200ms debounce (prevents flicker when moving cursor to a button)
  const handleDeactivate = useCallback(() => {
    deactivateTimeout.current = setTimeout(() => setActiveKey(null), 200);
  }, []);

  function handleFieldChange(key: string, value: string, status: FieldStatus) {
    setFields((prev) => ({ ...prev, [key]: { value, status } }));
  }

  function handleAddField(key: string, value: string) {
    setFields((prev) => ({ ...prev, [key]: { value, status: "corrected" } }));
  }

  async function handleSave(overallStatus: "accepted" | "corrected") {
    if (!noteIdState || !extracted) return;
    setSaving(true); setError(null);
    try {
      const validated = JSON.parse(JSON.stringify(extracted));
      const removedMedIndices = new Set<number>();
      Object.entries(fields).forEach(([key, { status }]) => {
        if (key.startsWith("med.") && status === "removed") {
          removedMedIndices.add(parseInt(key.split(".")[1]));
        }
      });
      Object.entries(fields).forEach(([key, { value, status }]) => {
        const [section, ...rest] = key.split(".");
        if (status === "removed") {
          if (section === "vitals") delete validated.vitals[rest[0]];
          else if (section === "instr") delete validated.instructions[rest[0]];
          else if (section === "meta") delete validated.metadata[rest[0]];
        } else {
          if (section === "vitals" && validated.vitals[rest[0]]) {
            validated.vitals[rest[0]].value = value;
          } else if (section === "instr" && validated.instructions[rest[0]]) {
            validated.instructions[rest[0]].value = value;
          } else if (section === "meta" && validated.metadata[rest[0]]) {
            validated.metadata[rest[0]].value = value;
          } else if (section === "med") {
            const idx = parseInt(rest[0]);
            const field = rest[1] as keyof (typeof validated.medications)[number];
            if (!removedMedIndices.has(idx) && validated.medications[idx]) {
              (validated.medications[idx] as any)[field] = value;
            }
          }
        }
      });
      validated.medications = validated.medications.filter(
        (_: unknown, i: number) => !removedMedIndices.has(i)
      );
      await api.validate({
        note_id: noteIdState,
        validated_json: validated,
        status: overallStatus,
        review_duration_ms: Date.now() - startTime.current,
      });
      setSaved(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  if (!extracted) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-400 text-sm">
        Loading...
      </div>
    );
  }

  const hasCorrected = Object.values(fields).some((f) => f.status === "corrected" || f.status === "removed");
  const correctedCount = Object.values(fields).filter((f) => f.status === "corrected" || f.status === "removed").length;
  const acceptedCount = Object.values(fields).filter((f) => f.status === "accepted").length;
  const pendingCount = Object.values(fields).filter((f) => f.status === "pending").length;

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Dark nav */}
      <header className="bg-slate-800 text-slate-100 px-6 py-2.5 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-4">
          <a href="/" className="text-slate-500 hover:text-slate-300 text-sm transition-colors">← Back</a>
          <span className="font-semibold text-sm tracking-wide">Reviewer</span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="text-slate-500">⏱ {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}</span>
          {source && (
            <span className={`px-2 py-0.5 rounded border text-[10px] uppercase tracking-wider font-medium
              ${source === "ocr"
                ? "bg-slate-900 text-sky-400 border-cyan-800"
                : source === "pdf"
                  ? "bg-blue-950 text-blue-400 border-blue-800"
                  : "bg-slate-700 text-slate-400 border-slate-600"}`}>
              {source}
            </span>
          )}
          <span className="text-slate-600 text-[10px]">v{extracted.pipeline_version}</span>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden" style={{ height: "calc(100vh - 45px)" }}>
        {/* Left: NoteViewer */}
        <div className="w-1/2 border-r border-slate-200 flex flex-col overflow-hidden bg-white">
          {/* Legend */}
          <div className="px-4 py-1.5 border-b border-slate-100 bg-slate-50 flex gap-4 flex-shrink-0">
            {[
              { label: "vitals", color: "bg-blue-400" },
              { label: "meds", color: "bg-green-400" },
              { label: "instructions", color: "bg-amber-400" },
              { label: "metadata", color: "bg-violet-400" },
            ].map(({ label, color }) => (
              <span key={label} className="flex items-center gap-1.5 text-[10px] text-slate-500">
                <span className={`w-2 h-2 rounded-sm ${color} opacity-70`} />
                {label}
              </span>
            ))}
          </div>
          <NoteViewer
            rawText={rawText}
            extracted={extracted}
            activeKey={activeKey}
            onSpanClick={handleActivate}
          />
        </div>

        {/* Right: Field cards */}
        <div className="w-1/2 flex flex-col overflow-hidden bg-slate-50">
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4">
            {CATEGORIES.map((cat) => {
              const prefix = CATEGORY_PREFIX[cat];
              const catFields = Object.entries(fields).filter(([k]) => k.startsWith(prefix));
              return (
                <section key={cat}>
                  <h3 className="text-[10px] font-bold uppercase tracking-[0.1em] text-slate-400 mb-2 px-1">
                    {CATEGORY_DISPLAY[cat]}
                  </h3>
                  <div className="space-y-1.5">
                    {catFields.map(([k, f]) => (
                      <div
                        key={k}
                        ref={(el) => { cardRefs.current[k] = el; }}
                        onMouseEnter={() => handleActivate(k)}
                        onMouseLeave={handleDeactivate}
                      >
                        <FieldEditor
                          label={k.replace(prefix, "").replace(/^\d+\./, "")}
                          value={f.value}
                          status={f.status}
                          category={getCategoryFromKey(k)}
                          isActive={activeKey === k}
                          onActivate={() => handleActivate(k)}
                          onChange={(v, s) => handleFieldChange(k, v, s)}
                        />
                      </div>
                    ))}
                    <AddFieldRow
                      category={cat}
                      existingKeys={Object.keys(fields)}
                      onAdd={handleAddField}
                    />
                  </div>
                </section>
              );
            })}
          </div>

          {/* Footer */}
          <div className="border-t border-slate-200 px-4 py-2.5 bg-white flex items-center justify-between flex-shrink-0">
            <div className="flex items-center gap-1.5 text-[11px] bg-slate-50 border border-slate-100 rounded-md px-3 py-1">
              <span className="text-amber-600 font-medium">{correctedCount} corrected</span>
              <span className="text-slate-300">|</span>
              <span className="text-green-600 font-medium">{acceptedCount} accepted</span>
              <span className="text-slate-300">|</span>
              <span className="text-slate-400">{pendingCount} pending</span>
            </div>
            <div className="flex items-center gap-2">
              {error && <p className="text-red-500 text-xs mr-2">{error}</p>}
              {saved && <p className="text-green-600 text-xs mr-2">Saved ✓</p>}
              <button
                onClick={() => handleSave("accepted")}
                disabled={saving}
                className="px-4 py-1.5 border border-green-200 text-green-700 bg-green-50 rounded-md text-sm font-medium hover:bg-green-100 disabled:opacity-50"
              >
                Accept all
              </button>
              <button
                onClick={() => handleSave("corrected")}
                disabled={saving || !hasCorrected}
                className="px-4 py-1.5 bg-blue-600 text-white rounded-md text-sm font-semibold hover:bg-blue-700 disabled:opacity-50"
              >
                {saving ? "Saving..." : "Save corrections"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: TypeScript check — expect clean**

```bash
cd /Users/kanuj/clinical-notes-nlp-assistant/frontend
npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Smoke test in browser**

Open `http://localhost:5173`. Load sample note → Extract. Verify:
- Dark slate nav bar
- Left pane: note with colored span highlights and faint section labels (VITALS, MEDICATIONS, etc.)
- Right pane: quiet field cards with "click to review" hint text
- Hover a field card: buttons appear, card highlights in category color
- Click a span in the left pane: right panel scrolls to and highlights that field card
- Footer pill: "0 corrected | 0 accepted | N pending"
- "+ Add Vitals" row at bottom of Vitals section; click opens inline form

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Review.tsx
git commit -m "feat: redesign Review page — span↔field linking, add-field, dark nav, card hierarchy"
```

---

### Task 8: Update `Home.tsx` — dark nav, image accept, Processing label

**Files:**
- Modify: `frontend/src/pages/Home.tsx`

- [ ] **Step 1: Apply targeted edits to `frontend/src/pages/Home.tsx`**

**Edit 1 — dark nav header:**
```tsx
// Replace:
<header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between">
  <div>
    <h1 className="text-xl font-semibold text-slate-800">Clinical Notes NLP Assistant</h1>
    <p className="text-xs text-amber-600 mt-0.5">Demo mode — all data is synthetic</p>
  </div>
  <nav className="flex gap-4 text-sm text-slate-600">
    <a href="/history" className="hover:text-blue-600">History</a>
    <a href="/metrics" className="hover:text-blue-600">Metrics</a>
  </nav>
</header>

// With:
<header className="bg-slate-800 text-slate-100 px-6 py-2.5 flex items-center justify-between">
  <div>
    <span className="font-semibold text-sm tracking-wide">Clinical Notes NLP Assistant</span>
    <p className="text-xs text-slate-500 mt-0.5">Demo mode — all data is synthetic</p>
  </div>
  <nav className="flex gap-4 text-sm text-slate-400">
    <a href="/history" className="hover:text-slate-200 transition-colors">History</a>
    <a href="/metrics" className="hover:text-slate-200 transition-colors">Metrics</a>
  </nav>
</header>
```

**Edit 2 — textarea contrast:**
```tsx
// Replace:
className="w-full h-48 border border-slate-300 rounded-lg p-3 font-mono text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-400"
// With:
className="w-full h-48 border border-slate-300 rounded-lg p-3 font-mono text-sm text-slate-900 leading-relaxed resize-none focus:outline-none focus:ring-2 focus:ring-blue-400"
```

**Edit 3 — drop zone hint text and accepted file types:**
```tsx
// Replace:
<p className="text-slate-500 text-sm">Drop a .txt or .pdf file here, or click to browse</p>
<input ref={fileRef} type="file" accept=".txt,.pdf" className="hidden"
// With:
<p className="text-slate-500 text-sm">Drop a .txt, .pdf, or image file here, or click to browse</p>
<input ref={fileRef} type="file" accept=".txt,.pdf,.png,.jpg,.jpeg,.tiff,.tif" className="hidden"
```

**Edit 4 — loading label:**
```tsx
// Replace:
{loading ? "Extracting..." : "Extract →"}
// With:
{loading ? "Processing..." : "Extract →"}
```

- [ ] **Step 2: TypeScript check and browser verify**

```bash
npx tsc --noEmit
```

Open `http://localhost:5173`. Verify: dark nav, updated hint text, "Processing..." when loading.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Home.tsx
git commit -m "feat: update Home — dark nav, image file accept, Processing label"
```

---

### Task 9: Update `History.tsx` — dark nav, SourceBadge

**Files:**
- Modify: `frontend/src/pages/History.tsx`

- [ ] **Step 1: Apply targeted edits to `frontend/src/pages/History.tsx`**

**Edit 1 — add import:**
```tsx
import SourceBadge from "../components/SourceBadge";
```

**Edit 2 — dark nav header:**
```tsx
// Replace:
<header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between">
  <h1 className="text-xl font-semibold text-slate-800">History</h1>
  <nav className="flex gap-4 text-sm text-slate-600">
    <a href="/" className="hover:text-blue-600">Home</a>
    <a href="/metrics" className="hover:text-blue-600">Metrics</a>
  </nav>
</header>
// With:
<header className="bg-slate-800 text-slate-100 px-6 py-2.5 flex items-center justify-between">
  <span className="font-semibold text-sm tracking-wide">History</span>
  <nav className="flex gap-4 text-sm text-slate-400">
    <a href="/" className="hover:text-slate-200 transition-colors">Home</a>
    <a href="/metrics" className="hover:text-slate-200 transition-colors">Metrics</a>
  </nav>
</header>
```

**Edit 3 — use SourceBadge in source column:**
```tsx
// Replace:
<td className="px-4 py-3 text-slate-500">{note.source}</td>
// With:
<td className="px-4 py-3"><SourceBadge source={note.source} /></td>
```

- [ ] **Step 2: TypeScript check and browser verify**

```bash
npx tsc --noEmit
```

Navigate to `http://localhost:5173/history`. Verify: dark nav, colored SourceBadge pills in the source column.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/History.tsx
git commit -m "feat: update History — dark nav, SourceBadge in source column"
```

---

### Task 10: Update `Metrics.tsx` — dark nav

**Files:**
- Modify: `frontend/src/pages/Metrics.tsx`

- [ ] **Step 1: Replace the `<header>` in `frontend/src/pages/Metrics.tsx`**

```tsx
// Replace:
<header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between">
  <h1 className="text-xl font-semibold text-slate-800">Metrics</h1>
  <nav className="flex gap-4 text-sm text-slate-600">
    <a href="/" className="hover:text-blue-600">Home</a>
    <a href="/history" className="hover:text-blue-600">History</a>
  </nav>
</header>
// With:
<header className="bg-slate-800 text-slate-100 px-6 py-2.5 flex items-center justify-between">
  <span className="font-semibold text-sm tracking-wide">Metrics</span>
  <nav className="flex gap-4 text-sm text-slate-400">
    <a href="/" className="hover:text-slate-200 transition-colors">Home</a>
    <a href="/history" className="hover:text-slate-200 transition-colors">History</a>
  </nav>
</header>
```

- [ ] **Step 2: Run full frontend test suite**

```bash
cd /Users/kanuj/clinical-notes-nlp-assistant/frontend
npm test
```
Expected: all pass.

- [ ] **Step 3: TypeScript check**

```bash
npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Metrics.tsx
git commit -m "feat: update Metrics — dark nav"
```

---

## Final Verification

- [ ] **Run full backend test suite**

```bash
cd /Users/kanuj/clinical-notes-nlp-assistant
source .venv/bin/activate
python -m pytest backend/tests/ -v --tb=short
```
Expected: all pass.

- [ ] **Run full frontend test suite**

```bash
cd frontend && npm test
```
Expected: all pass.

- [ ] **End-to-end browser smoke test**

1. `http://localhost:5173` → dark slate nav, "image file" in drop zone hint
2. Load sample note → Extract → Review page opens with dark nav
3. Hover a vitals field card → buttons appear, card glows blue; other cards stay quiet
4. Click a highlighted span in the left pane → right panel scrolls to that card and highlights it
5. Click "Accept" on one field → accepted state: green, circled checkmark, no buttons
6. Click "+ Add Vitals" → inline form expands with select + value input
7. Click "+ Add Medication" → 4-field grid form (name/dose/route/frequency)
8. Footer pill shows correct corrected/accepted/pending counts
9. Click "Save corrections" → note appears in History with status "corrected"
10. `/history` → dark nav, SourceBadge colored pills in source column
11. `/metrics` → dark nav, charts unchanged
