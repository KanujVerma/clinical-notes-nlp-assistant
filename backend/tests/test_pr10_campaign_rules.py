"""Promotion rules and candidate diffs. No model calls."""
from __future__ import annotations

import io

from PIL import Image

from evaluation.pr10_candidate import historical_specs, mutation_queue, render_regions
from evaluation.pr10_replay import decide_screen
from evaluation.public_amr_benchmark import infer_image

TRACKED = (
    "encode", "contrast", "grayscale", "gamma", "sharpen", "denoise", "trim",
    "longest", "num_ctx", "prompt", "dedupe_lines", "collapse_spaces",
    "second_pass", "segment", "jpeg_quality",
)


def _view(**overrides):
    base = {
        "scored": 8, "fp": 1, "paired_cer": 0.40, "paired_hits": 7,
        "paired_fp": 1, "paired_p95": 8000, "rx_cer": 0.37,
    }
    base.update(overrides)
    return base


def test_coverage_gain_with_unchanged_paired_quality_is_kept():
    decision = decide_screen(_view(scored=2), _view(scored=8))
    assert decision["status"] == "keep"


def test_paired_error_or_coverage_loss_is_discarded():
    assert decide_screen(_view(), _view(paired_cer=0.50))["status"] == "discard"
    assert decide_screen(_view(), _view(scored=7))["status"] == "discard"
    assert decide_screen(_view(), _view())["status"] == "discard"


def test_each_mutation_changes_one_tracked_field():
    parent = historical_specs()["jpeg_ctx8192"]
    children = mutation_queue(parent)
    assert len(children) >= 15
    families = {child["family"] for child in children}
    assert {"A", "B", "C", "D", "E"} <= families
    for child in children:
        changed = [key for key in TRACKED if child.get(key) != parent.get(key)]
        assert changed, child["name"]
        assert len(changed) == 1, (child["name"], changed)


def test_untouched_jpeg_matches_the_frozen_encoder():
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(buffer, format="PNG")
    original = buffer.getvalue()
    assert render_regions(historical_specs()["jpeg_baseline"], original) == [infer_image(original)]
    assert render_regions(historical_specs()["jpeg_ctx8192"], original) == [infer_image(original)]
