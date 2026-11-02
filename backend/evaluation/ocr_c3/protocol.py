"""Frozen campaign-3 protocol. Loading it does not run recognition."""
from __future__ import annotations

import json
from pathlib import Path

CAMPAIGN_ID = "ocr-c3-apple-vision-v1"
CANDIDATE = "V1_apple_vision_accurate_raw"
READING_ORDER = "vision_reading_order_v1"
ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = ROOT / "docs" / "validation" / "ocr_c3_protocol_manifest.json"
PARTITION_PATH = ROOT / "docs" / "validation" / "pr10_partition_manifest.json"
PRIVATE_ROOT = Path(
    "/Users/kanuj/Documents/projects/clinical-notes-nlp-assistant/artifacts/handwriting-private/ocr-c3-apple-vision-v1"
)


def load_protocol() -> dict:
    payload = json.loads(MANIFEST_PATH.read_text())
    if payload.get("campaign_id") != CAMPAIGN_ID:
        raise ValueError("OCR_C3_PROTOCOL")
    return payload


def partition() -> dict:
    return json.loads(PARTITION_PATH.read_text())
