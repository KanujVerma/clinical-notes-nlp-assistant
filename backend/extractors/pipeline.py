import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from typing import Any
from config import Config
from extractors.preprocess import preprocess
from extractors.sections import detect_sections
from extractors.vitals import extract_vitals
from extractors.medications import extract_medications
from extractors.instructions import extract_instructions
from extractors.metadata import extract_metadata
from extractors.normalize import normalize_output


def _remap_field(field: dict[str, Any], pr) -> dict[str, Any]:
    """Replace clean-text span with raw-text span in a field dict."""
    if "span" in field and isinstance(field["span"], (list, tuple)):
        s, e = field["span"]
        field = dict(field)
        field["span"] = list(pr.remap_span(s, e))
    return field


def run_pipeline(raw_text: str) -> dict[str, Any]:
    # 1. Preprocess
    pr = preprocess(raw_text)
    clean = pr.clean_text

    # 2. Section detection (on clean text)
    sections = detect_sections(clean)

    # 3. Extraction
    vitals_raw = extract_vitals(clean)
    meds_raw = extract_medications(clean)
    instr_raw = extract_instructions(clean, sections)
    meta_raw = extract_metadata(clean)

    # 4. Remap spans from clean → raw offsets
    vitals = {k: _remap_field(v, pr) for k, v in vitals_raw.items()}
    medications = [_remap_field(m, pr) for m in meds_raw]
    instructions = {k: _remap_field(v, pr) for k, v in instr_raw.items()}
    metadata = {k: _remap_field(v, pr) for k, v in meta_raw.items()}

    # 5. Normalize and stamp
    return normalize_output(Config.PIPELINE_VERSION, vitals, medications, instructions, metadata)
