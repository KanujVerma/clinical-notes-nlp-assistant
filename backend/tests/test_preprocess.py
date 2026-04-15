import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from extractors.preprocess import preprocess

def test_collapses_blank_lines():
    raw = "Line one\n\n\n\nLine two"
    result = preprocess(raw)
    assert result.clean_text.count("\n\n\n") == 0

def test_preserves_content():
    raw = "BP: 120/80\nHR: 72"
    result = preprocess(raw)
    assert "BP: 120/80" in result.clean_text
    assert "HR: 72" in result.clean_text

def test_offset_map_is_list_of_tuples():
    raw = "Hello   world"
    result = preprocess(raw)
    assert isinstance(result.offset_map, list)
    assert all(isinstance(t, tuple) and len(t) == 2 for t in result.offset_map)

def test_remap_span_returns_raw_offset():
    raw = "A\n\n\nB"
    result = preprocess(raw)
    clean_idx = result.clean_text.index("B")
    raw_idx = result.remap(clean_idx)
    assert raw[raw_idx] == "B"
