"""Block-aware line geometry for segmentation amendment 1.

Detection uses a local contrast mask. Recognition crops stay on the oriented
RGB image. This module does not change ``ocr_c2_segments_v2``.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[3]
AMENDMENT_PATH = ROOT / "docs" / "validation" / "ocr_c2_segmentation_amendment.json"


def load_amendment() -> dict:
    payload = json.loads(AMENDMENT_PATH.read_text())
    if payload["amendment_id"] != "c2-segmentation-amendment-1":
        raise ValueError("OCR_C2_AMENDMENT")
    if payload["segmenter_id"] != "ocr_c2_segments_v3":
        raise ValueError("OCR_C2_SEGMENTER")
    return payload


def _rules() -> dict:
    return load_amendment()["rules"]


def orient_once(image: Image.Image) -> tuple[Image.Image, int]:
    exif = image.getexif()
    orientation = int(exif.get(274, 1)) if exif else 1
    return ImageOps.exif_transpose(image).convert("RGB"), orientation


def _percentile(hist: list[int], total: int, percent: int) -> int:
    target = max(1, (percent * total + 99) // 100)
    seen = 0
    for value, count in enumerate(hist):
        seen += count
        if seen >= target:
            return value
    return 255


def local_mask(gray: Image.Image, rules: dict) -> bytes:
    width, height = gray.size
    raw = gray.tobytes()
    block = max(int(rules["block_min_px"]), int(round(min(width, height) * rules["block_fraction"])))
    mask = bytearray(width * height)
    for y0 in range(0, height, block):
        y1 = min(height, y0 + block)
        for x0 in range(0, width, block):
            x1 = min(width, x0 + block)
            hist = [0] * 256
            for y in range(y0, y1):
                row = raw[y * width + x0:y * width + x1]
                for value in row:
                    hist[value] += 1
            total = (y1 - y0) * (x1 - x0)
            background = _percentile(hist, total, int(rules["background_percentile"]))
            margin = max(int(rules["contrast_floor"]), int(round(rules["contrast_fraction"] * background)))
            limit = background - margin
            for y in range(y0, y1):
                base = y * width
                for x in range(x0, x1):
                    if limit < 0 or raw[base + x] <= limit:
                        mask[base + x] = 1
    return bytes(mask)


def _find(parent: list[int], index: int) -> int:
    while parent[index] != index:
        parent[index] = parent[parent[index]]
        index = parent[index]
    return index


def _union(parent: list[int], left: int, right: int) -> None:
    left = _find(parent, left)
    right = _find(parent, right)
    if left == right:
        return
    if left > right:
        left, right = right, left
    parent[right] = left


def connected_components(mask: bytes, width: int, height: int) -> list[dict]:
    """8-connected components. Boxes are half-open and deterministic."""
    parent: list[int] = []
    boxes: list[list[int]] = []
    previous: list[tuple[int, int, int]] = []
    for y in range(height):
        row = y * width
        current: list[tuple[int, int, int]] = []
        x = 0
        while x < width:
            if not mask[row + x]:
                x += 1
                continue
            x0 = x
            x += 1
            while x < width and mask[row + x]:
                x += 1
            index = len(parent)
            parent.append(index)
            boxes.append([x0, y, x, y + 1, x - x0])
            current.append((x0, x, index))
        probe = 0
        for x0, x1, index in current:
            while probe < len(previous) and previous[probe][1] < x0:
                probe += 1
            cursor = probe
            while cursor < len(previous) and previous[cursor][0] <= x1:
                px0, px1, other = previous[cursor]
                if px1 >= x0 and x1 >= px0:
                    _union(parent, index, other)
                cursor += 1
        previous = current
    merged: dict[int, list[int]] = {}
    for index, box in enumerate(boxes):
        root = _find(parent, index)
        found = merged.get(root)
        if found is None:
            merged[root] = box.copy()
            continue
        found[0] = min(found[0], box[0])
        found[1] = min(found[1], box[1])
        found[2] = max(found[2], box[2])
        found[3] = max(found[3], box[3])
        found[4] += box[4]
    components = []
    for box in merged.values():
        components.append({
            "x0": box[0], "y0": box[1], "x1": box[2], "y1": box[3], "area": box[4],
            "w": box[2] - box[0], "h": box[3] - box[1],
            "cx": (box[0] + box[2]) / 2, "cy": (box[1] + box[3]) / 2,
        })
    components.sort(key=lambda item: (item["y0"], item["x0"], -item["area"], item["x1"]))
    for index, item in enumerate(components):
        item["id"] = index
        item["owner"] = "unresolved"
    return components


def _scale(components: list[dict], height: int, rules: dict) -> float:
    limit = rules["scale_max_image_fraction"] * height
    heights = sorted(
        item["h"] for item in components
        if item["area"] >= rules["scale_min_area_px"]
        and item["h"] >= rules["scale_min_height_px"]
        and item["w"] >= 2
        and item["h"] <= limit
    )
    if not heights:
        heights = sorted(item["h"] for item in components if item["h"] >= 1)
    if not heights:
        return 1.0
    drop = int(len(heights) * rules["scale_drop_low_fraction"])
    core = heights[drop:] or heights
    return float(core[len(core) // 2])


def _vertical_overlap(left: dict, right: dict) -> int:
    return min(left["y1"], right["y1"]) - max(left["y0"], right["y0"])


def _horizontal_gap_px(left: dict, right: dict) -> int:
    if left["x1"] <= right["x0"]:
        return right["x0"] - left["x1"]
    if right["x1"] <= left["x0"]:
        return left["x0"] - right["x1"]
    return 0


def _horizontal_gap(components: list[dict]) -> list[tuple[int, int]]:
    ordered = sorted(components, key=lambda item: (item["x0"], item["id"]))
    gaps = []
    for left, right in zip(ordered, ordered[1:]):
        if right["x0"] > left["x1"]:
            gaps.append((left["x1"], right["x0"]))
    return gaps


def _side_span(components: list[dict]) -> tuple[int, int] | None:
    if not components:
        return None
    return min(item["x0"] for item in components), max(item["x1"] for item in components)


def _coherent_columns(lines: list[dict], gutter: tuple[int, int], line_ids: set[int], scale: float) -> bool:
    """Both sides need a repeated text stack, not one shared word gap."""
    start, end = gutter
    by_id = {line["id"]: line for line in lines}
    left, right = [], []
    for line_id in line_ids:
        line = by_id.get(line_id)
        if line is None:
            continue
        left.append(_side_span([item for item in line["components"] if item["x1"] <= start]))
        right.append(_side_span([item for item in line["components"] if item["x0"] >= end]))
    left = [item for item in left if item]
    right = [item for item in right if item]
    if len(left) < 3 or len(right) < 3:
        return False

    def stacked(spans: list[tuple[int, int]]) -> bool:
        anchor = spans[len(spans) // 2]
        overlaps = sum(1 for span in spans if min(anchor[1], span[1]) - max(anchor[0], span[0]) >= 0.5 * scale)
        return overlaps >= len(spans) - 1

    return stacked(left) and stacked(right)


def _confirmed_gutter(lines: list[dict], scale: float, rules: dict) -> tuple[int, int] | str | None:
    minimum = rules["gutter_gap_ratio"] * scale
    gaps = []
    for line in lines:
        for start, end in _horizontal_gap(line["components"]):
            if end - start >= minimum:
                gaps.append((start, end, line["id"]))
    if not gaps:
        return None
    parent = list(range(len(gaps)))
    for index, (start, end, _line_id) in enumerate(gaps):
        for other in range(index + 1, len(gaps)):
            ostart, oend, _other_line = gaps[other]
            if start < oend and ostart < end:
                _union(parent, index, other)
    groups: dict[int, list[tuple[int, int, int]]] = {}
    for index, gap in enumerate(gaps):
        groups.setdefault(_find(parent, index), []).append(gap)
    valid = []
    for group in groups.values():
        start = max(item[0] for item in group)
        end = min(item[1] for item in group)
        lines_hit = {item[2] for item in group}
        if end - start >= rules["gutter_min_width_ratio"] * scale and len(lines_hit) >= rules["gutter_min_lines"]:
            interval = (int(start), int(end))
            if _coherent_columns(lines, interval, lines_hit, scale):
                valid.append(interval)
    if len(valid) > 1:
        return "ambiguous"
    if len(valid) == 1:
        return valid[0]
    return None


def _ranges_overlap(left: dict, right: dict, scale: float, rules: dict) -> bool:
    expand = rules["line_y_expand_ratio"] * scale
    return (
        abs(left["cy"] - right["cy"]) <= rules["line_center_ratio"] * scale
        and left["y0"] - expand <= right["y1"]
        and right["y0"] - expand <= left["y1"]
    )


def _cluster_lines(components: list[dict], scale: float, rules: dict) -> list[dict]:
    parent = list(range(len(components)))
    ordered = sorted(range(len(components)), key=lambda index: (components[index]["cy"], components[index]["x0"]))
    window: list[int] = []
    limit = rules["line_center_ratio"] * scale
    for index in ordered:
        component = components[index]
        window = [item for item in window if component["cy"] - components[item]["cy"] <= limit]
        for other in window:
            if _ranges_overlap(component, components[other], scale, rules):
                _union(parent, index, other)
        window.append(index)
    groups: dict[int, list[dict]] = {}
    for index, component in enumerate(components):
        groups.setdefault(_find(parent, index), []).append(component)
    lines = []
    for members in groups.values():
        members.sort(key=lambda item: (item["x0"], item["id"]))
        lines.append({
            "components": members,
            "x0": min(item["x0"] for item in members),
            "y0": min(item["y0"] for item in members),
            "x1": max(item["x1"] for item in members),
            "y1": max(item["y1"] for item in members),
        })
    lines.sort(key=lambda item: (item["y0"], item["x0"]))
    for index, line in enumerate(lines):
        line["id"] = index
    return lines


def _split_columns(lines: list[dict], gutter: tuple[int, int] | None) -> tuple[list[dict], list[dict], list[dict], str | None]:
    if gutter is None:
        for line in lines:
            line["block"] = "body"
            line["role"] = "line"
        return lines, [], [], None
    start, end = gutter
    spans, left, right = [], [], []
    for line in lines:
        sides = {"left": [], "right": [], "cross": []}
        for component in line["components"]:
            if component["x1"] <= start:
                sides["left"].append(component)
            elif component["x0"] >= end:
                sides["right"].append(component)
            else:
                sides["cross"].append(component)
        if sides["cross"]:
            line["block"] = "span"
            line["role"] = "heading"
            spans.append(line)
            continue
        if sides["left"] and sides["right"]:
            for side, block, bucket in (
                ("left", "left", left),
                ("right", "right", right),
            ):
                piece = {
                    "components": sides[side],
                    "block": block,
                    "role": "line",
                    "id": line["id"],
                }
                _refresh(piece)
                bucket.append(piece)
            continue
        if sides["left"]:
            line["components"] = sides["left"]
            line["block"] = "left"
            line["role"] = "line"
            _refresh(line)
            left.append(line)
        elif sides["right"]:
            line["components"] = sides["right"]
            line["block"] = "right"
            line["role"] = "line"
            _refresh(line)
            right.append(line)
    return spans, left, right, None


def _refresh(line: dict) -> None:
    members = line["components"]
    line["x0"] = min(item["x0"] for item in members)
    line["y0"] = min(item["y0"] for item in members)
    line["x1"] = max(item["x1"] for item in members)
    line["y1"] = max(item["y1"] for item in members)


def _order(spans: list[dict], left: list[dict], right: list[dict]) -> list[dict]:
    spans = sorted(spans, key=lambda item: (item["y0"], item["x0"], item["id"]))
    bins: dict[int, dict[str, list]] = {index: {"left": [], "right": []} for index in range(-1, len(spans))}

    def bucket(line: dict) -> int:
        chosen = -1
        for index, span in enumerate(spans):
            if line["y0"] >= span["y0"]:
                chosen = index
            else:
                break
        return chosen

    for line in left:
        bins[bucket(line)]["left"].append(line)
    for line in right:
        bins[bucket(line)]["right"].append(line)
    ordered = []
    for index in range(-1, len(spans)):
        if index >= 0:
            ordered.append(spans[index])
        ordered.extend(sorted(bins[index]["left"], key=lambda item: (item["y0"], item["x0"], item["id"])))
        ordered.extend(sorted(bins[index]["right"], key=lambda item: (item["y0"], item["x0"], item["id"])))
    return ordered


def _overlaps_order(lines: list[dict], scale: float, rules: dict) -> bool:
    limit = rules["overlap_order_ratio"] * scale
    for index, line in enumerate(lines):
        for other in lines[index + 1:]:
            y_overlap = min(line["y1"], other["y1"]) - max(line["y0"], other["y0"])
            x_overlap = min(line["x1"], other["x1"]) - max(line["x0"], other["x0"])
            if y_overlap > limit and x_overlap > 0 and line.get("block") == other.get("block"):
                return True
    return False


def _attach_small(small: list[dict], lines: list[dict], scale: float, rules: dict) -> str | None:
    for component in small:
        matches = []
        for line in lines:
            vertical = 0 if line["y0"] <= component["cy"] <= line["y1"] else min(
                abs(component["cy"] - line["y0"]), abs(component["cy"] - line["y1"]),
            )
            horizontal = 0 if line["x0"] <= component["cx"] <= line["x1"] else min(
                abs(component["cx"] - line["x0"]), abs(component["cx"] - line["x1"]),
            )
            if vertical <= rules["attach_vertical_ratio"] * scale and horizontal <= rules["attach_horizontal_ratio"] * scale:
                matches.append(line)
        if len(matches) == 1:
            matches[0]["components"].append(component)
            component["owner"] = f"line:{matches[0]['id']}"
            _refresh(matches[0])
        elif len(matches) > 1:
            matches.sort(key=lambda line: (
                0 if line["y0"] <= component["cy"] <= line["y1"] else min(
                    abs(component["cy"] - line["y0"]), abs(component["cy"] - line["y1"]),
                ),
                line["id"],
            ))
            nearest, second = matches[0], matches[1]
            nearest_distance = 0 if nearest["y0"] <= component["cy"] <= nearest["y1"] else min(
                abs(component["cy"] - nearest["y0"]), abs(component["cy"] - nearest["y1"]),
            )
            second_distance = 0 if second["y0"] <= component["cy"] <= second["y1"] else min(
                abs(component["cy"] - second["y0"]), abs(component["cy"] - second["y1"]),
            )
            if nearest_distance == second_distance:
                component["owner"] = "unresolved"
                return "ambiguous_mark"
            matches[0]["components"].append(component)
            component["owner"] = f"line:{matches[0]['id']}"
            _refresh(matches[0])
        else:
            area_limit = max(rules["background_min_area_px"], rules["background_area_ratio"] * scale * scale)
            component["owner"] = "background" if component["area"] <= area_limit else "unresolved"
            if component["owner"] == "unresolved":
                return "unassigned_component"
    return None


def _projection_band(mask: bytes, width: int, components: list[dict], scale: float, rules: dict) -> tuple[bool, int]:
    if not components:
        return False, 0
    y0 = min(item["y0"] for item in components)
    y1 = max(item["y1"] for item in components)
    active = []
    for y in range(y0, y1):
        ink = False
        for component in components:
            if y < component["y0"] or y >= component["y1"]:
                continue
            row = y * width
            if any(mask[row + x] for x in range(component["x0"], component["x1"])):
                ink = True
                break
        active.append(ink)
    gap_limit = max(1, int(round(rules["projection_gap_ratio"] * scale)))
    bands = []
    start = None
    gap_start = None
    for index, ink in enumerate(active):
        if ink:
            if start is None:
                start = index
            gap_start = None
        elif start is not None:
            if gap_start is None:
                gap_start = index
            if index - gap_start + 1 > gap_limit:
                bands.append((start, gap_start))
                start = None
                gap_start = None
    if start is not None:
        bands.append((start, gap_start if gap_start is not None else len(active)))
    if len(bands) != 1:
        return False, 0
    band_height = bands[0][1] - bands[0][0]
    suitable = rules["certified_band_min_ratio"] * scale <= band_height <= rules["certified_band_max_ratio"] * scale
    return suitable, band_height


def _baseline_grouped(components: list[dict], scale: float, rules: dict) -> bool:
    text = [item for item in components if not str(item.get("owner", "")).startswith("background")]
    if not text:
        return False
    centers = sorted(item["cy"] for item in text)
    median = centers[len(centers) // 2]
    return all(abs(item["cy"] - median) <= rules["baseline_spread_ratio"] * scale for item in text)


def _crop_box(line: dict, scale: float, rules: dict, width: int, height: int, others: list[dict]) -> tuple[dict, str | None]:
    pad = int(round(rules["pad_ratio"] * scale))
    for used in (pad, 0):
        box = {
            "x0": max(0, line["x0"] - used),
            "y0": max(0, line["y0"] - used),
            "x1": min(width, line["x1"] + used),
            "y1": min(height, line["y1"] + used),
        }
        conflict = False
        for other in others:
            for component in other["components"]:
                if component["x1"] <= box["x0"] or component["x0"] >= box["x1"]:
                    continue
                if component["y1"] <= box["y0"] or component["y0"] >= box["y1"]:
                    continue
                conflict = True
                break
            if conflict:
                break
        if not conflict:
            return box, None
    return {
        "x0": line["x0"], "y0": line["y0"], "x1": line["x1"], "y1": line["y1"],
    }, "neighbor_ink"


def _page_region(width: int, height: int, reason: str) -> dict:
    return {
        "id": "page",
        "order": 0,
        "kind": "page",
        "block": "page",
        "x0": 0, "y0": 0, "x1": width, "y1": height,
        "certified_line": False,
        "component_ids": [],
        "projection_single_band": False,
        "baseline_grouped": False,
        "fallback_reason": reason,
    }


def _finish(base: dict, reason: str | None, lines: list[dict] | None = None) -> dict:
    width = base["width"]
    height = base["height"]
    if reason is None:
        raise ValueError("OCR_C2_FALLBACK")
    base.update({
        "eligible": False,
        "fallback": True,
        "fallback_reason": reason,
        "reading_order_status": "ambiguous" if "ambiguous" in reason or reason == "unsupported_table" else "fallback",
        "regions": [_page_region(width, height, reason)],
        "line_count": 0,
        "attempted_lines": lines or [],
    })
    return base


def segment_v3(image: Image.Image, input_type: str = "page", rules: dict | None = None) -> dict:
    rules = rules or _rules()
    oriented, orientation = orient_once(image)
    width, height = oriented.size
    if width == 0 or height == 0:
        raise ValueError("OCR_C2_EMPTY_IMAGE")
    if input_type not in {"page", "word_crop"}:
        raise ValueError("OCR_C2_INPUT_TYPE")
    base = {
        "segmenter": "ocr_c2_segments_v3",
        "amendment_id": "c2-segmentation-amendment-1",
        "input_type": input_type,
        "width": width,
        "height": height,
        "orientation": orientation,
        "column_detector_applied": input_type == "page",
        "blank": False,
    }
    if input_type == "word_crop":
        base.update({
            "eligible": False,
            "fallback": False,
            "fallback_reason": None,
            "reading_order_status": "not_applicable",
            "component_scale_px": None,
            "line_count": 0,
            "block_count": 1,
            "components": [],
            "regions": [{
                "id": "word",
                "order": 0,
                "kind": "word_crop",
                "block": "word",
                "x0": 0, "y0": 0, "x1": width, "y1": height,
                "certified_line": False,
                "component_ids": [],
                "projection_single_band": False,
                "baseline_grouped": False,
                "fallback_reason": None,
            }],
        })
        return base
    gray = oriented.convert("L")
    mask = local_mask(gray, rules)
    components = connected_components(mask, width, height)
    base["components"] = [
        {"id": item["id"], "x0": item["x0"], "y0": item["y0"], "x1": item["x1"], "y1": item["y1"], "area": item["area"], "owner": item["owner"]}
        for item in components
    ]
    if not components:
        base["blank"] = True
        base["component_scale_px"] = None
        return _finish(base, "blank")
    if not any(item["area"] >= rules["scale_min_area_px"] for item in components):
        for component in components:
            component["owner"] = "background"
        base["blank"] = True
        base["component_scale_px"] = None
        _sync_owners(base, components)
        return _finish(base, "no_text")
    scale = _scale(components, height, rules)
    base["component_scale_px"] = scale
    rules_present = {"horizontal": False, "vertical": False}
    text, small, tall = [], [], []
    for component in components:
        density = component["area"] / max(1, component["w"] * component["h"])
        field_sized = (
            component["h"] >= rules["field_height_ratio"] * scale
            or component["w"] >= rules["field_width_fraction"] * width
        )
        if density <= rules["field_density_max"] and field_sized and component["area"] >= rules["scale_min_area_px"]:
            component["owner"] = "background_field"
            continue
        if component["h"] <= max(2, rules["rule_height_ratio"] * scale) and component["w"] >= rules["rule_width_fraction"] * width:
            component["owner"] = "background_rule"
            rules_present["horizontal"] = True
            continue
        if component["w"] <= max(2, rules["vertical_rule_width_ratio"] * scale) and component["h"] >= rules["vertical_rule_height_ratio"] * scale:
            component["owner"] = "background_rule"
            rules_present["vertical"] = True
            continue
        if component["h"] > rules["cross_line_height_ratio"] * scale:
            component["owner"] = "tall"
            tall.append(component)
            continue
        if component["area"] < rules["small_area_ratio"] * scale * scale and component["h"] < rules["small_height_ratio"] * scale:
            component["owner"] = "small"
            small.append(component)
            continue
        component["owner"] = "text"
        text.append(component)
    if rules_present["horizontal"] and rules_present["vertical"]:
        _sync_owners(base, components)
        return _finish(base, "unsupported_table")
    if not text:
        for component in small:
            component["owner"] = "background"
        base["blank"] = True
        _sync_owners(base, components)
        return _finish(base, "no_text")
    lines = _cluster_lines(text, scale, rules)
    gutter = _confirmed_gutter(lines, scale, rules)
    if gutter == "ambiguous":
        _sync_owners(base, components)
        return _finish(base, "ambiguous_layout")
    spans, left, right, split_reason = _split_columns(lines, gutter if isinstance(gutter, tuple) else None)
    if split_reason:
        _sync_owners(base, components)
        return _finish(base, split_reason)
    ordered = _order(spans, left, right) if gutter else lines
    for index, line in enumerate(ordered):
        line["id"] = index
        line["order"] = index
        if "block" not in line:
            line["block"] = "body"
            line["role"] = "line"
    for component in tall:
        hits = [
            line for line in ordered
            if _vertical_overlap(component, line) >= rules["tall_overlap_ratio"] * scale and _horizontal_gap_px(component, line) <= rules["attach_horizontal_ratio"] * scale
        ]
        if len(hits) >= 2:
            component["owner"] = "unresolved"
            _sync_owners(base, components)
            return _finish(base, "cross_line_stroke")
        component["owner"] = "marginal"
    attach_reason = _attach_small(small, ordered, scale, rules)
    if attach_reason:
        _sync_owners(base, components)
        return _finish(base, attach_reason)
    if _overlaps_order(ordered, scale, rules):
        _sync_owners(base, components)
        return _finish(base, "ambiguous_reading_order")
    regions = []
    for line in ordered:
        others = [item for item in ordered if item["id"] != line["id"]]
        others.extend(
            {"components": [component]}
            for component in tall
            if component["owner"] == "marginal"
        )
        box, crop_reason = _crop_box(line, scale, rules, width, height, others)
        if crop_reason:
            _sync_owners(base, components)
            return _finish(base, crop_reason)
        for component in line["components"]:
            component["owner"] = f"line:{line['id']}"
            if component["x0"] < box["x0"] or component["y0"] < box["y0"] or component["x1"] > box["x1"] or component["y1"] > box["y1"]:
                _sync_owners(base, components)
                return _finish(base, "clipped_component")
        projection_ok, _band = _projection_band(mask, width, line["components"], scale, rules)
        baseline_ok = _baseline_grouped(line["components"], scale, rules)
        if not projection_ok or not baseline_ok:
            _sync_owners(base, components)
            return _finish(base, "line_not_certified")
        regions.append({
            "id": f"L{line['order']}",
            "order": line["order"],
            "kind": "line",
            "block": line["block"],
            "role": line["role"],
            "x0": box["x0"], "y0": box["y0"], "x1": box["x1"], "y1": box["y1"],
            "certified_line": True,
            "component_ids": [component["id"] for component in line["components"]],
            "projection_single_band": True,
            "baseline_grouped": True,
            "fallback_reason": None,
        })
    seen = []
    for region in regions:
        seen.extend(region["component_ids"])
    if len(seen) != len(set(seen)):
        _sync_owners(base, components)
        return _finish(base, "duplicate_ownership")
    assigned = set(seen)
    for component in text:
        if component["id"] not in assigned:
            component["owner"] = "unresolved"
            _sync_owners(base, components)
            return _finish(base, "unassigned_component")
    _sync_owners(base, components)
    if len(regions) < rules["min_certified_lines"]:
        return _finish(base, "fewer_than_two_lines")
    base.update({
        "eligible": True,
        "fallback": False,
        "fallback_reason": None,
        "reading_order_status": "unambiguous",
        "regions": regions,
        "line_count": len(regions),
        "block_count": len({region["block"] for region in regions}),
        "unassigned_components": 0,
        "clipped_components": 0,
        "duplicated_components": 0,
    })
    return base


def _sync_owners(base: dict, components: list[dict]) -> None:
    owners = {item["id"]: item["owner"] for item in components}
    for record in base.get("components", []):
        record["owner"] = owners.get(record["id"], record["owner"])


def document_eligible(pages: list[dict]) -> bool:
    nonblank = [page for page in pages if not page.get("blank")]
    return bool(nonblank) and all(page.get("eligible") for page in nonblank)


def cohort_gate(documents: list[dict], minimum: int = 6) -> dict:
    eligible = [item["id"] for item in documents if document_eligible(item["pages"])]
    return {
        "documents": len(documents),
        "eligible_documents": len(eligible),
        "eligible_ids": eligible,
        "minimum": minimum,
        "passed": len(eligible) >= minimum,
    }
