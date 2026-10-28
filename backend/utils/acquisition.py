import os
import re
import json
import uuid
import hashlib
import tempfile
from typing import Dict, Any, List, Tuple, Optional
import fitz  # PyMuPDF
import pytesseract
from pytesseract import Output
from PIL import Image, ImageOps, ImageFilter
from models import SourceAsset, AcquisitionRun, NoteRevision


def _preprocess_image_for_ocr(img: Image.Image) -> Image.Image:
    out = img.convert("L")
    out = ImageOps.autocontrast(out)
    out = out.point(lambda p: 255 if p >= 128 else 0)
    try:
        osd = pytesseract.image_to_osd(out, config="--psm 0 -c min_characters_to_try=5")
        for line in osd.splitlines():
            if "Rotate:" in line:
                angle = int(line.split(":")[-1].strip())
                if angle != 0:
                    out = out.rotate(-angle, expand=True)
                break
    except Exception:
        pass
    out = out.filter(ImageFilter.MedianFilter(size=3))
    return out


def acquire_document(
    file_bytes: bytes,
    original_filename: str,
    mime_type: str,
    workspace_id: str,
    storage_root: str,
) -> Tuple[SourceAsset, AcquisitionRun, Dict[str, Any]]:
    """
    Acquires binary source asset, stores it in content-addressed storage,
    runs pagewise text extraction and OCR fallback, and builds geometry.
    """
    # Bound file/page/image work before rasterization or OCR. Unsupported
    # multi-frame formats must fail explicitly rather than losing pages.
    max_bytes = 10 * 1024 * 1024
    max_pages = 20
    max_pixels = 20_000_000
    if not file_bytes or len(file_bytes) > max_bytes:
        raise ValueError("Document is empty or exceeds the 10 MiB size limit")
    sha256 = hashlib.sha256(file_bytes).hexdigest()
    storage_dir = os.path.join(storage_root, sha256[:2])
    os.makedirs(storage_dir, exist_ok=True)
    storage_path = os.path.join(storage_dir, f"{sha256}.bin")

    if not os.path.exists(storage_path):
        with tempfile.NamedTemporaryFile(dir=storage_dir, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        os.replace(tmp_path, storage_path)

    asset = SourceAsset(
        workspace_id=workspace_id,
        sha256=sha256,
        storage_key=storage_path,
        mime_type=mime_type,
        byte_size=len(file_bytes),
        original_filename=os.path.basename(original_filename or "document"),
        acquisition_kind="upload",
    )

    # 2. Pagewise text extraction
    pages_data: List[Dict[str, Any]] = []
    canonical_text_parts: List[str] = []
    current_char_offset = 0
    warnings: List[str] = []

    ext = os.path.splitext(original_filename.lower())[1]

    if ext == ".pdf" or mime_type == "application/pdf":
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        asset.page_count = len(doc)
        if not (1 <= asset.page_count <= max_pages):
            doc.close()
            raise ValueError("PDF page count exceeds the supported limit")

        for page_idx, page in enumerate(doc):
            rect = page.rect
            width, height = rect.width, rect.height
            page_text = page.get_text()

            # Inspect word blocks and bboxes
            words = page.get_text("words")  # [x0, y0, x1, y1, word, block_no, line_no, word_no]
            char_boxes = []
            for w in words:
                char_boxes.append({
                    "text": w[4],
                    "bbox": [round(w[0], 2), round(w[1], 2), round(w[2], 2), round(w[3], 2)],
                })

            if len(page_text.strip()) >= 50:
                method = "native_pdf"
                conf = 1.0
            else:
                # OCR fallback for this page
                method = "tesseract_ocr"
                # PyMuPDF page.rect uses points; estimate raster pixels before
                # allocating the pixmap at 200 DPI.
                est_pixels = (width * 200.0 / 72.0) * (height * 200.0 / 72.0)
                if est_pixels > max_pixels:
                    doc.close()
                    raise ValueError("PDF page exceeds decoded pixel limit")
                pix = page.get_pixmap(dpi=200)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                preproc = _preprocess_image_for_ocr(img)
                tess_data = pytesseract.image_to_data(
                    preproc,
                    config="--psm 6 -l eng",
                    output_type=Output.DICT,
                )
                confs = [c for c in tess_data["conf"] if c != -1]
                conf = (sum(confs) / len(confs) / 100.0) if confs else 0.0

                scale_x = width / float(preproc.width) if preproc.width > 0 else 1.0
                scale_y = height / float(preproc.height) if preproc.height > 0 else 1.0

                ocr_words = []
                for i in range(len(tess_data["text"])):
                    txt = tess_data["text"][i].strip()
                    if txt:
                        ocr_words.append(txt)
                        x0_scaled = round(tess_data["left"][i] * scale_x, 2)
                        y0_scaled = round(tess_data["top"][i] * scale_y, 2)
                        x1_scaled = round((tess_data["left"][i] + tess_data["width"][i]) * scale_x, 2)
                        y1_scaled = round((tess_data["top"][i] + tess_data["height"][i]) * scale_y, 2)
                        char_boxes.append({
                            "text": txt,
                            "bbox": [x0_scaled, y0_scaled, x1_scaled, y1_scaled],
                        })
                page_text = " ".join(ocr_words)

            page_len = len(page_text)
            start_off = current_char_offset
            end_off = start_off + page_len

            pages_data.append({
                "page_number": page_idx + 1,
                "acquisition_method": method,
                "confidence": round(conf, 3),
                "width": round(width, 2),
                "height": round(height, 2),
                "start_offset": start_off,
                "end_offset": end_off,
                "text_hash": hashlib.sha256(page_text.encode("utf-8")).hexdigest(),
                "boxes": char_boxes,
            })
            canonical_text_parts.append(page_text)
            current_char_offset = end_off + 2  # account for "\n\n"

        doc.close()

    elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".tif") or mime_type.startswith("image/"):
        asset.page_count = 1
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            with Image.open(tmp_path) as img:
                width, height = img.size
                if width * height > max_pixels:
                    raise ValueError("Image exceeds decoded pixel limit")
                if getattr(img, "n_frames", 1) != 1:
                    raise ValueError("Multi-frame image requires explicit framewise acquisition")
                preproc = _preprocess_image_for_ocr(img)
                tess_data = pytesseract.image_to_data(
                    preproc,
                    config="--psm 6 -l eng",
                    output_type=Output.DICT,
                )
                confs = [c for c in tess_data["conf"] if c != -1]
                conf = (sum(confs) / len(confs) / 100.0) if confs else 0.0
                char_boxes = []
                ocr_words = []
                for i in range(len(tess_data["text"])):
                    txt = tess_data["text"][i].strip()
                    if txt:
                        ocr_words.append(txt)
                        char_boxes.append({
                            "text": txt,
                            "bbox": [
                                tess_data["left"][i],
                                tess_data["top"][i],
                                tess_data["left"][i] + tess_data["width"][i],
                                tess_data["top"][i] + tess_data["height"][i],
                            ]
                        })
                page_text = " ".join(ocr_words)
                pages_data.append({
                    "page_number": 1,
                    "acquisition_method": "tesseract_ocr",
                    "confidence": round(conf, 3),
                    "width": width,
                    "height": height,
                    "start_offset": 0,
                    "end_offset": len(page_text),
                    "text_hash": hashlib.sha256(page_text.encode("utf-8")).hexdigest(),
                    "boxes": char_boxes,
                })
                canonical_text_parts.append(page_text)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    else:
        # Plain text
        page_text = file_bytes.decode("utf-8", errors="replace")
        asset.page_count = 1
        pages_data.append({
            "page_number": 1,
            "acquisition_method": "text_utf8",
            "confidence": 1.0,
            "width": 800,
            "height": 1100,
            "start_offset": 0,
            "end_offset": len(page_text),
            "text_hash": hashlib.sha256(page_text.encode("utf-8")).hexdigest(),
            "boxes": [],
        })
        canonical_text_parts.append(page_text)

    canonical_text = "\n\n".join(canonical_text_parts)

    acq_run = AcquisitionRun(
        source_asset_id=asset.id,
        engine="pymupdf_tesseract",
        status="completed",
        page_count=asset.page_count,
        pages_json=json.dumps(pages_data),
        canonical_text=canonical_text,
        warnings_json=json.dumps(warnings),
    )

    metadata = {
        "pages": pages_data,
        "canonical_text": canonical_text,
        "warnings": warnings,
    }
    return asset, acq_run, metadata
