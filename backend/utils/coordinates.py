import math
from typing import Dict, Any, List, Optional, Tuple


def validate_bbox_geometry(
    bbox: Optional[List[float]],
    page_width: float,
    page_height: float,
) -> Tuple[bool, str, Optional[str]]:
    """
    Validates whether a bounding box [x0, y0, x1, y1] is well-formed
    and fits within the page dimensions.
    Returns (is_valid, code, explanation).
    """
    if bbox is None or not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return False, "MISSING_GEOMETRY", "Bounding box geometry is missing or incomplete."

    try:
        x0, y0, x1, y1 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
    except (ValueError, TypeError):
        return False, "INVALID_GEOMETRY", "Bounding box coordinates must be numeric."

    if math.isnan(x0) or math.isnan(y0) or math.isnan(x1) or math.isnan(y1):
        return False, "INVALID_GEOMETRY", "Bounding box contains NaN coordinates."

    if page_width <= 0 or page_height <= 0:
        return False, "INVALID_PAGE_DIMENSIONS", "Page width and height must be strictly positive."

    if x0 >= x1 or y0 >= y1:
        return False, "DEGENERATE_BOX", f"Non-positive dimensions: [{x0}, {y0}, {x1}, {y1}] (width={x1-x0}, height={y1-y0})."

    # Allow tiny float tolerance (e.g. 1 point or 0.5% margin)
    tolerance = max(2.0, max(page_width, page_height) * 0.01)
    if x0 < -tolerance or y0 < -tolerance or x1 > (page_width + tolerance) or y1 > (page_height + tolerance):
        return (
            False,
            "OUT_OF_BOUNDS",
            f"Bounding box [{x0:.1f}, {y0:.1f}, {x1:.1f}, {y1:.1f}] exceeds page bounds [{page_width:.1f}, {page_height:.1f}].",
        )

    return True, "VALID", None


def transform_bbox(
    bbox: List[float],
    page_width: float,
    page_height: float,
    rotation: int = 0,
    coordinate_system: str = "top_left",
) -> Dict[str, float]:
    """
    Transforms [x0, y0, x1, y1] coordinates on a page (width x height)
    under page rotation (0, 90, 180, 270 degrees clockwise) into
    normalized percentages (left_pct, top_pct, width_pct, height_pct)
    suitable for responsive CSS overlay on the rendered page.
    """
    valid, code, msg = validate_bbox_geometry(bbox, page_width, page_height)
    if not valid:
        raise ValueError(f"{code}: {msg}")

    x0, y0, x1, y1 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])

    # Convert bottom-left origin (PDF native) to top-left origin if needed
    if coordinate_system in ("bottom_left", "pdf_points_bottom_left"):
        y0_tl = page_height - y1
        y1_tl = page_height - y0
        y0, y1 = min(y0_tl, y1_tl), max(y0_tl, y1_tl)

    rot = (rotation % 360 + 360) % 360
    if rot not in (0, 90, 180, 270):
        raise ValueError(f"Unsupported rotation angle: {rotation}. Must be a multiple of 90 degrees.")

    if rot == 0:
        # Rendered dimensions match page
        left_pct = (x0 / page_width) * 100.0
        top_pct = (y0 / page_height) * 100.0
        width_pct = ((x1 - x0) / page_width) * 100.0
        height_pct = ((y1 - y0) / page_height) * 100.0
        rendered_width = page_width
        rendered_height = page_height

    elif rot == 90:
        # 90° clockwise: (x, y) -> (page_height - y, x)
        # Rendered dimensions: width' = page_height, height' = page_width
        rendered_width = page_height
        rendered_height = page_width
        x0_rot = page_height - y1
        y0_rot = x0
        w_rot = y1 - y0
        h_rot = x1 - x0
        left_pct = (x0_rot / rendered_width) * 100.0
        top_pct = (y0_rot / rendered_height) * 100.0
        width_pct = (w_rot / rendered_width) * 100.0
        height_pct = (h_rot / rendered_height) * 100.0

    elif rot == 180:
        # 180° clockwise: (x, y) -> (page_width - x, page_height - y)
        rendered_width = page_width
        rendered_height = page_height
        x0_rot = page_width - x1
        y0_rot = page_height - y1
        w_rot = x1 - x0
        h_rot = y1 - y0
        left_pct = (x0_rot / rendered_width) * 100.0
        top_pct = (y0_rot / rendered_height) * 100.0
        width_pct = (w_rot / rendered_width) * 100.0
        height_pct = (h_rot / rendered_height) * 100.0

    else:  # 270° clockwise
        # 270° clockwise: (x, y) -> (y, page_width - x)
        rendered_width = page_height
        rendered_height = page_width
        x0_rot = y0
        y0_rot = page_width - x1
        w_rot = y1 - y0
        h_rot = x1 - x0
        left_pct = (x0_rot / rendered_width) * 100.0
        top_pct = (y0_rot / rendered_height) * 100.0
        width_pct = (w_rot / rendered_width) * 100.0
        height_pct = (h_rot / rendered_height) * 100.0

    return {
        "left_pct": round(left_pct, 3),
        "top_pct": round(top_pct, 3),
        "width_pct": round(width_pct, 3),
        "height_pct": round(height_pct, 3),
        "rendered_width": round(rendered_width, 2),
        "rendered_height": round(rendered_height, 2),
        "rotation": rot,
    }


def check_source_image_agreement(
    span_text: str,
    bbox: Optional[List[float]],
    page_boxes: List[Dict[str, Any]],
    page_width: float,
    page_height: float,
) -> Dict[str, Any]:
    """
    Checks agreement between an extracted transcript span and *stored OCR
    words* within its page region. This is NOT independent verification of
    original image pixels, source transcription truth, or clinical correctness.
    Flags disagreements, missing geometry, and out-of-bounds anomalies.
    """
    if not span_text or not span_text.strip():
        return {
            "status": "missing_span_text",
            "agreement": False,
            "similarity": 0.0,
            "reason": "Span text is empty.",
            "ocr_text": "",
        }

    is_valid, code, msg = validate_bbox_geometry(bbox, page_width, page_height)
    if not is_valid:
        return {
            "status": "missing_geometry" if code == "MISSING_GEOMETRY" else "invalid_geometry",
            "agreement": False,
            "similarity": 0.0,
            "code": code,
            "reason": msg,
            "ocr_text": "",
        }

    x0, y0, x1, y1 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])

    # Find all words in page_boxes whose center falls inside the bbox (with slight tolerance)
    tol = 3.0
    matched_words = []
    for item in page_boxes:
        w_bbox = item.get("bbox")
        w_text = item.get("text", "").strip()
        if not w_bbox or len(w_bbox) != 4 or not w_text:
            continue
        cx = (w_bbox[0] + w_bbox[2]) / 2.0
        cy = (w_bbox[1] + w_bbox[3]) / 2.0
        if (x0 - tol) <= cx <= (x1 + tol) and (y0 - tol) <= cy <= (y1 + tol):
            matched_words.append((w_bbox[1], w_bbox[0], w_text))

    # Sort in reading order (top to bottom, left to right)
    matched_words.sort(key=lambda item: (round(item[0] / 8.0), item[1]))
    ocr_text = " ".join(item[2] for item in matched_words)

    if not ocr_text:
        return {
            "status": "empty_box_ocr",
            "agreement": False,
            "similarity": 0.0,
            "reason": "No OCR words detected inside the specified bounding box.",
            "ocr_text": "",
        }

    import re

    # 1. Check exact numeric tokens (including decimals like 0.5 vs .5 vs 5)
    def _extract_numbers(text: str) -> List[float]:
        raw = re.findall(r"(?<![\w.])(?:\d+(?:\.\d+)?|\.\d+)(?![\w.])", text)
        res = []
        for s in raw:
            try:
                res.append(float(s))
            except ValueError:
                pass
        return res

    span_numbers = _extract_numbers(span_text)
    ocr_numbers = _extract_numbers(ocr_text)
    for num in span_numbers:
        if not any(abs(num - o_num) < 1e-5 for o_num in ocr_numbers):
            return {
                "status": "disagreement",
                "agreement": False,
                "similarity": 0.0,
                "ocr_text": ocr_text,
                "span_text": span_text,
                "reason": f"Disagreement: numeric value '{num}' in transcript does not match page OCR numbers ({ocr_numbers}).",
            }

    # 2. Check clinical negation polarity
    negation_tokens = {"not", "no", "never", "discontinue", "discontinued", "stop", "stopped", "hold", "held"}
    span_tokens = set(re.findall(r"\b[a-zA-Z]+\b", span_text.lower()))
    ocr_tokens = set(re.findall(r"\b[a-zA-Z]+\b", ocr_text.lower()))
    span_neg = span_tokens.intersection(negation_tokens)
    ocr_neg = ocr_tokens.intersection(negation_tokens)
    if span_neg != ocr_neg:
        return {
            "status": "disagreement",
            "agreement": False,
            "similarity": 0.0,
            "ocr_text": ocr_text,
            "span_text": span_text,
            "reason": f"Disagreement: clinical polarity mismatch (negation tokens {span_neg or 'none'} vs {ocr_neg or 'none'}).",
        }

    # 3. Compute token and character overlap similarity
    clean_span = " ".join(re.findall(r"[a-z0-9.]+", span_text.lower()))
    clean_ocr = " ".join(re.findall(r"[a-z0-9.]+", ocr_text.lower()))

    if clean_span == clean_ocr or clean_span in clean_ocr or clean_ocr in clean_span:
        similarity = 1.0
    else:
        span_set = set(clean_span.split())
        ocr_set = set(clean_ocr.split())
        overlap = len(span_set.intersection(ocr_set))
        union = len(span_set.union(ocr_set)) or 1
        similarity = round(overlap / union, 3)

    is_agreement = similarity >= 0.60
    return {
        "status": "ocr_consistent_unverified" if is_agreement else "disagreement",
        "agreement": is_agreement,
        "similarity": similarity,
        "ocr_text": ocr_text,
        "span_text": span_text,
        "reason": None if is_agreement else f"Disagreement: span claims '{span_text}', but page OCR at box contains '{ocr_text}'.",
    }
