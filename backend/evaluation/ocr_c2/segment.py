"""Deterministic page bands and line strips. The mask locates whitespace only."""
from __future__ import annotations

from PIL import Image, ImageOps

from evaluation.ocr_c2.protocol import load_protocol


def _rules() -> dict:
    return load_protocol()["segmentation"]


def otsu_threshold(gray: Image.Image) -> int:
    hist = [0] * 256
    for value in gray.tobytes():
        hist[value] += 1
    total = sum(hist)
    if total == 0:
        return 0
    sum_total = sum(index * count for index, count in enumerate(hist))
    sum_background = 0
    weight_background = 0
    best = -1.0
    threshold = 0
    for index, count in enumerate(hist):
        weight_background += count
        if weight_background == 0:
            continue
        weight_foreground = total - weight_background
        if weight_foreground == 0:
            break
        sum_background += index * count
        mean_background = sum_background / weight_background
        mean_foreground = (sum_total - sum_background) / weight_foreground
        variance = weight_background * weight_foreground * (mean_background - mean_foreground) ** 2
        if variance > best:
            best = variance
            threshold = index
    return threshold


def foreground_rows(gray: Image.Image, rules: dict | None = None) -> list[bool]:
    rules = rules or _rules()
    threshold = otsu_threshold(gray)
    width, height = gray.size
    pixels = gray.tobytes()
    marked = []
    limit = rules["low_ink_row_fraction"] * width
    for y in range(height):
        ink = sum(1 for value in pixels[y * width:(y + 1) * width] if value <= threshold)
        marked.append(ink > limit)
    return marked


def usable_gaps(ink_rows: list[bool], minimum: int) -> list[tuple[int, int]]:
    gaps = []
    start = None
    for index, ink in enumerate(ink_rows + [True]):
        if not ink and start is None:
            start = index
        elif ink and start is not None:
            if index - start >= minimum:
                gaps.append((start, index))
            start = None
    return gaps


def _center(span: tuple[int, int]) -> float:
    return (span[0] + span[1]) / 2


def _column_uncertain(gray: Image.Image, ink_rows: list[bool], rules: dict) -> bool:
    width, _height = gray.size
    nonblank = [index for index, ink in enumerate(ink_rows) if ink]
    if not nonblank:
        return False
    low = int(rules["gutter_central_low"] * width)
    high = int(rules["gutter_central_high"] * width)
    needed = rules["gutter_width_fraction"] * width
    threshold = otsu_threshold(gray)
    pixels = gray.tobytes()
    quiet = []
    for x in range(low, high):
        inky = sum(1 for y in nonblank if pixels[y * width + x] <= threshold)
        quiet.append(inky / len(nonblank) <= (1 - rules["gutter_low_ink_row_fraction"]))
    run = 0
    for flag in quiet:
        run = run + 1 if flag else 0
        if run >= needed:
            return True
    return False


def _bands(height: int, gaps: list[tuple[int, int]], rules: dict) -> tuple[list[tuple[int, int]], bool]:
    tolerance = rules["n3_target_tolerance_fraction"] * height
    targets = (height / 3, 2 * height / 3)
    chosen = []
    used = set()
    for target in targets:
        eligible = [
            gap for gap in gaps
            if gap not in used and abs(_center(gap) - target) <= tolerance
        ]
        if not eligible:
            continue
        eligible.sort(key=lambda gap: (abs(_center(gap) - target), _center(gap)))
        pick = eligible[0]
        used.add(pick)
        chosen.append(pick)
    if not chosen:
        return [(0, height)], True
    cuts = sorted(int(_center(gap)) for gap in chosen)
    bounds = [0, *cuts, height]
    spans = [(bounds[index], bounds[index + 1]) for index in range(len(bounds) - 1) if bounds[index + 1] > bounds[index]]
    return spans[: rules["maximum_bands"]], False


def _merge_short(spans: list[tuple[int, int]], minimum: int) -> list[tuple[int, int]]:
    spans = list(spans)
    while len(spans) > 1 and any(end - start < minimum for start, end in spans):
        short_at = next(index for index, (start, end) in enumerate(spans) if end - start < minimum)
        if short_at == 0:
            neighbor = 1
        elif short_at == len(spans) - 1:
            neighbor = short_at - 1
        else:
            left = spans[short_at - 1]
            right = spans[short_at + 1]
            here = spans[short_at]
            left_distance = _center(here) - _center(left)
            right_distance = _center(right) - _center(here)
            neighbor = short_at - 1 if left_distance <= right_distance else short_at + 1
        keep, drop = sorted((short_at, neighbor))
        spans[keep] = (spans[keep][0], spans[drop][1])
        del spans[drop]
    return spans


def _lines(height: int, gaps: list[tuple[int, int]], rules: dict) -> tuple[list[tuple[int, int]], bool]:
    if not gaps:
        return [(0, height)], True
    cuts = sorted(int(_center(gap)) for gap in gaps)
    bounds = [0, *cuts, height]
    spans = [(bounds[index], bounds[index + 1]) for index in range(len(bounds) - 1) if bounds[index + 1] > bounds[index]]
    spans = _merge_short(spans, rules["minimum_line_pixels"])
    if len(spans) > rules["maximum_line_regions"]:
        return [], True
    return spans, False


def _pack(spans: list[tuple[int, int]], width: int, height: int, **flags) -> dict:
    if not spans or spans[0][0] != 0 or spans[-1][1] != height:
        raise ValueError("OCR_C2_PARTITION")
    if any(spans[index][1] != spans[index + 1][0] for index in range(len(spans) - 1)):
        raise ValueError("OCR_C2_PARTITION")
    regions = [
        {"x0": 0, "y0": start, "x1": width, "y1": end, "order": index}
        for index, (start, end) in enumerate(spans)
    ]
    return {"regions": regions, "width": width, "height": height, **flags}


def segment_page(image: Image.Image, geometry: str) -> dict:
    """Return a disjoint full-width partition of the oriented page."""
    rules = _rules()
    oriented = ImageOps.exif_transpose(image).convert("RGB")
    gray = oriented.convert("L")
    width, height = gray.size
    if height == 0 or width == 0:
        raise ValueError("OCR_C2_EMPTY_IMAGE")
    ink = foreground_rows(gray, rules)
    uncertain = _column_uncertain(gray, ink, rules)
    if uncertain or geometry == "page":
        return _pack(
            [(0, height)], width, height,
            segmentation_fallback=False,
            line_segmentation_unavailable=geometry == "lines" and uncertain,
            reading_order_uncertain=uncertain,
            geometry="page" if uncertain else geometry,
        )
    gaps = usable_gaps(ink, rules["minimum_gap_rows"])
    if geometry == "bands":
        spans, fallback = _bands(height, gaps, rules)
        return _pack(
            spans, width, height,
            segmentation_fallback=fallback,
            line_segmentation_unavailable=False,
            reading_order_uncertain=False,
            geometry="bands",
        )
    if geometry == "lines":
        spans, unavailable = _lines(height, gaps, rules)
        if unavailable:
            spans, fallback = _bands(height, gaps, rules)
            return _pack(
                spans, width, height,
                segmentation_fallback=fallback,
                line_segmentation_unavailable=True,
                reading_order_uncertain=False,
                geometry="bands",
            )
        return _pack(
            spans, width, height,
            segmentation_fallback=False,
            line_segmentation_unavailable=False,
            reading_order_uncertain=False,
            geometry="lines",
        )
    raise ValueError("OCR_C2_GEOMETRY")
