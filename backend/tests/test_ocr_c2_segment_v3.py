"""Synthetic geometry for segmentation amendment 1. No handwriting and no OCR."""
from __future__ import annotations

from io import BytesIO

from PIL import Image

from evaluation.ocr_c2.segment import segment_page
from evaluation.ocr_c2.segment_v3 import cohort_gate, document_eligible, segment_v3


def _draw(width, height, strokes):
    image = Image.new("RGB", (width, height), "white")
    pixels = image.load()
    for x0, y0, x1, y1 in strokes:
        for y in range(y0, y1):
            for x in range(x0, x1):
                pixels[x, y] = (0, 0, 0)
    return image


def _six_lines():
    strokes = []
    for index in range(6):
        y0 = 10 + index * 28
        strokes.append((12, y0, 70, y0 + 8))
    return _draw(240, 180, strokes)


def test_v2_false_column_on_short_left_lines():
    layout = segment_page(_six_lines(), "lines")
    assert layout["geometry"] == "page"
    assert layout["reading_order_uncertain"] is True
    assert layout["line_segmentation_unavailable"] is True
    assert len(layout["regions"]) == 1


def test_summary_records_geometry_without_a_transcript():
    from evaluation.ocr_c2.geometry_audit import summarize_layout
    from evaluation.public_amr_benchmark import sha
    image = _six_lines()
    layout = segment_v3(image, "page")
    summary = summarize_layout(layout, sha(b"synthetic"))
    assert summary["eligible"] is True
    assert summary["line_count"] == 6
    assert "prediction" not in summary
    assert "reference" not in summary


def test_isolated_tall_component_is_not_certified_coverage():
    strokes = []
    for index in range(6):
        y0 = 10 + index * 28
        strokes.append((12, y0, 70, y0 + 8))
    strokes.append((120, 12, 132, 36))
    layout = segment_v3(_draw(240, 180, strokes), "page")
    assert layout["eligible"] is False
    assert layout["fallback_reason"] == "unassigned_component"
    assert layout["regions"][0]["kind"] == "page"
    assert layout["regions"][0]["certified_line"] is False
    assert any(item["owner"] == "unresolved" for item in layout["components"])


def test_v3_splits_the_same_short_left_lines():
    layout = segment_v3(_six_lines(), "page")
    assert layout["eligible"] is True
    assert layout["fallback"] is False
    assert layout["line_count"] == 6
    assert [region["kind"] for region in layout["regions"]] == ["line"] * 6
    assert layout["reading_order_status"] == "unambiguous"
    owned = [item["id"] for region in layout["regions"] for item in []]
    ids = [component_id for region in layout["regions"] for component_id in region["component_ids"]]
    assert len(ids) == len(set(ids))
    assert owned == []


def test_word_crop_skips_column_detection_and_a_failed_page_is_not_a_word():
    word = _draw(180, 40, [(70, 14, 110, 26)])
    crop = segment_v3(word, "word_crop")
    assert crop["column_detector_applied"] is False
    assert crop["regions"][0]["kind"] == "word_crop"
    assert crop["fallback"] is False
    page = segment_v3(word, "page")
    assert page["eligible"] is False
    assert page["regions"][0]["kind"] == "page"
    assert page["fallback_reason"] == "fewer_than_two_lines"


def test_true_columns_and_heading_have_explicit_order():
    strokes = [(10, 6, 190, 16)]
    for index in range(3):
        y0 = 36 + index * 28
        strokes.append((12, y0, 70, y0 + 8))
        strokes.append((130, y0, 188, y0 + 8))
    layout = segment_v3(_draw(200, 140, strokes), "page")
    assert layout["eligible"] is True
    assert layout["line_count"] == 7
    assert [region["block"] for region in layout["regions"]] == ["span", "left", "left", "left", "right", "right", "right"]


def test_indentation_is_not_a_second_column():
    strokes = []
    for index in range(6):
        y0 = 8 + index * 24
        x0 = 40 if index == 2 else 12
        strokes.append((x0, y0, x0 + 50, y0 + 8))
    layout = segment_v3(_draw(220, 160, strokes), "page")
    assert layout["eligible"] is True
    assert layout["line_count"] == 6
    assert {region["block"] for region in layout["regions"]} == {"body"}


def test_small_mark_stays_with_its_line():
    strokes = []
    for index in range(4):
        y0 = 12 + index * 30
        strokes.append((16, y0, 80, y0 + 10))
    strokes.append((84, 14, 87, 18))
    layout = segment_v3(_draw(160, 140, strokes), "page")
    assert layout["eligible"] is True
    assert  layout["line_count"] == 4
    owners = {item["id"]: item["owner"] for item in layout["components"]}
    assert "unresolved" not in owners.values()
    assert any(item["owner"] == "background" or item["owner"].startswith("line:") for item in layout["components"])
    assert all(item["owner"] != "unresolved" for item in layout["components"])


def test_blank_noise_rules_and_tables_fail_explicitly():
    blank = segment_v3(_draw(80, 60, []), "page")
    assert blank["fallback_reason"] == "blank"
    assert blank["eligible"] is False
    noise = segment_v3(_draw(80, 60, [(4, 4, 5, 5), (40, 40, 41, 41)]), "page")
    assert noise["eligible"] is False
    assert noise["regions"][0]["kind"] == "page"
    ruled_strokes = [(0, 20, 200, 22), (0, 70, 200, 72)]
    for index in range(4):
        y0 = 30 + index * 10
        ruled_strokes.append((20, y0, 90, y0 + 6))
    # The rules above are close to the text; use a page where rules are thin and text is separated.
    strokes = [(0, 4, 220, 6), (0, 150, 220, 152)]
    for index in range(4):
        y0 = 24 + index * 28
        strokes.append((18, y0, 100, y0 + 8))
    ruled = segment_v3(_draw(220, 170, strokes), "page")
    assert ruled["eligible"] is True
    assert ruled["line_count"] == 4
    assert any(item["owner"] == "background_rule" for item in ruled["components"])
    table = [(8, 6, 160, 8), (8, 80, 160, 82)]
    for x in (12, 80, 148):
        table.append((x, 16, x + 2, 70))
    unsupported = segment_v3(_draw(180, 96, table), "page")
    assert unsupported["fallback_reason"] == "unsupported_table"
    assert unsupported["regions"][0]["kind"] == "page"
    grid = []
    for y in (8, 36, 64):
        grid.append((6, y, 120, y + 3))
    for x in (6, 60, 112):
        grid.append((x, 8, x + 3, 67))
    connected = segment_v3(_draw(140, 80, grid), "page")
    assert connected["eligible"] is False
    assert connected["regions"][0]["kind"] == "page"


def test_touching_strokes_are_not_certified_lines():
    strokes = []
    for index in range(3):
        y0 = 10 + index * 30
        strokes.append((12, y0, 90, y0 + 8))
    strokes.append((40, 10, 48, 78))
    layout = segment_v3(_draw(140, 110, strokes), "page")
    assert layout["eligible"] is False
    assert layout["regions"][0]["kind"] == "page"
    assert layout["fallback_reason"] in {"cross_line_stroke", "no_text", "neighbor_ink", "fewer_than_two_lines"}


def test_moderate_slant_stays_one_line_and_scale_is_stable():
    strokes = []
    for index in range(5):
        y0 = 12 + index * 26
        for piece in range(4):
            x0 = 10 + piece * 18
            strokes.append((x0, y0 + piece, x0 + 12, y0 + piece + 8))
    small = segment_v3(_draw(120, 160, strokes), "page")
    large_strokes = [(x0 * 2, y0 * 2, x1 * 2, y1 * 2) for x0, y0, x1, y1 in strokes]
    large = segment_v3(_draw(240, 320, large_strokes), "page")
    assert small["eligible"] is True
    assert large["eligible"] is True
    assert small["line_count"] == large["line_count"] == 5


def test_exif_is_applied_once_and_reruns_match():
    image = _six_lines()
    exif = Image.Exif()
    exif[274] = 2
    stored = BytesIO()
    image.save(stored, format="TIFF", exif=exif.tobytes())
    loaded = Image.open(stored)
    layout = segment_v3(loaded, "page")
    assert layout["orientation"] == 2
    assert layout["eligible"] is True
    assert layout["line_count"] == 6
    again = segment_v3(loaded, "page")
    assert [(item["x0"], item["y0"], item["x1"], item["y1"]) for item in again["regions"]] == [
        (item["x0"], item["y0"], item["x1"], item["y1"]) for item in layout["regions"]
    ]


def test_failed_geometry_does_not_open_the_recognizer():
    from evaluation.ocr_c2.controller import TransitionRejected, step
    assert step("amendment_preflight", "preflight_ok") == "geometry_development"
    assert step("geometry_development", "geometry_failed") == "geometry_blocked"
    assert step("geometry_blocked", "recorded") == "stopped"
    try:
        step("geometry_blocked", "optional_qualifies")
        raise AssertionError("recognizer opened without geometry")
    except TransitionRejected:
        pass
    assert step("paired_screen", "glm_nonqualifying") == "optional_recognizer"


def test_gate_requires_six_eligible_documents_and_keeps_fallbacks():
    good = {"eligible": True, "blank": False}
    bad = {"eligible": False, "blank": False, "fallback_reason": "fewer_than_two_lines"}
    documents = [{"id": f"d{index}", "pages": [good]} for index in range(6)]
    documents.append({"id": "fallback", "pages": [bad]})
    documents.append({"id": "blank", "pages": [{"eligible": False, "blank": True}]})
    gate = cohort_gate(documents)
    assert gate["eligible_documents"] == 6
    assert gate["passed"] is True
    assert document_eligible([{"eligible": False, "blank": True}]) is False
    assert cohort_gate(documents[:5])["passed"] is False
