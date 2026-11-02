"""Frozen reading order vision_reading_order_v1.

Observations sort by top y, then left x, then original index. Invalid
geometry sorts after valid geometry and keeps its text. Equal coordinates use
strict numeric comparison, never a fuzzy distance.
"""
from __future__ import annotations

from evaluation.ocr_c3.geometry import geometry_status, pixel_rectangle
from evaluation.ocr_c3.protocol import READING_ORDER


def _box(observation: dict, width: int, height: int) -> dict:
    stored = observation.get("pixel_rectangle")
    if isinstance(stored, dict) and {"x", "y", "width", "height"} <= set(stored):
        return stored
    return pixel_rectangle(observation["normalized_rectangle"], width, height)


def _vertical_overlap(left: dict, right: dict) -> float:
    top = max(float(left["y"]), float(right["y"]))
    bottom = min(float(left["y"]) + float(left["height"]), float(right["y"]) + float(right["height"]))
    return bottom - top


def _horizontal_gap(left: dict, right: dict) -> float:
    left_end = float(left["x"]) + float(left["width"])
    right_end = float(right["x"]) + float(right["width"])
    if left_end <= float(right["x"]):
        return float(right["x"]) - left_end
    if right_end <= float(left["x"]):
        return float(left["x"]) - right_end
    return 0.0


def reading_order_uncertain(observations: list[dict], width: int, height: int) -> bool:
    boxes = []
    for observation in observations:
        box = _box(observation, width, height)
        if geometry_status(box, width, height) == "valid":
            boxes.append(box)
    for index, left in enumerate(boxes):
        for right in boxes[index + 1:]:
            shorter = min(float(left["height"]), float(right["height"]))
            if _vertical_overlap(left, right) >= 0.4 * shorter and _horizontal_gap(left, right) >= 0.15 * width:
                return True
    return False


def assemble(observations: list[dict], width: int, height: int) -> str:
    decorated = []
    for observation in observations:
        box = _box(observation, width, height)
        valid = geometry_status(box, width, height) == "valid"
        decorated.append((0 if valid else 1, float(box["y"]), float(box["x"]), int(observation["index"]), observation))
    decorated.sort()
    lines = []
    for _valid, _y, _x, _index, observation in decorated:
        text = observation.get("top_candidate")
        if not isinstance(text, str):
            candidates = observation.get("candidates") or []
            text = candidates[0].get("text") if candidates and isinstance(candidates[0], dict) else ""
        if isinstance(text, str) and text != "":
            lines.append(text)
    return "\n".join(lines)


def order_name() -> str:
    return READING_ORDER
