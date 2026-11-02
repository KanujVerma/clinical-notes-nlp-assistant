"""Vision normalized rectangles to top-left pixel coordinates."""
from __future__ import annotations

import math


def pixel_rectangle(normalized: dict, width: int, height: int) -> dict:
    return {
        "x": float(normalized["x"]) * width,
        "y": (1.0 - float(normalized["y"]) - float(normalized["height"])) * height,
        "width": float(normalized["width"]) * width,
        "height": float(normalized["height"]) * height,
    }


def geometry_status(box: dict, width: int, height: int) -> str:
    values = [box.get("x"), box.get("y"), box.get("width"), box.get("height")]
    if any(not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in values):
        return "invalid"
    x, y, w, h = (float(value) for value in values)
    if w <= 0 or h <= 0:
        return "invalid"
    if x < -0.5 or y < -0.5 or x + w > width + 0.5 or y + h > height + 0.5:
        return "invalid"
    return "valid"
