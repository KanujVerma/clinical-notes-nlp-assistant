"""Load the preregistered campaign-2 protocol. Does not start inference."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = ROOT / "docs" / "validation" / "ocr_c2_protocol_manifest.json"
PARTITION_PATH = ROOT / "docs" / "validation" / "pr10_partition_manifest.json"
CAMPAIGN_ID = "ocr-campaign2-native-regions-v1"
IDENTITY_VERSION = "ocr_c2_identity_v3"
CANONICAL_PRIVATE = Path(
    "/Users/kanuj/Documents/projects/clinical-notes-nlp-assistant"
    "/artifacts/handwriting-private/ocr-campaign2-native-regions-v1"
)


def load_protocol() -> dict:
    payload = json.loads(MANIFEST_PATH.read_text())
    if payload["campaign_id"] != CAMPAIGN_ID:
        raise ValueError("OCR_C2_PROTOCOL_ID")
    if payload["identity_version"] != IDENTITY_VERSION:
        raise ValueError("OCR_C2_PROTOCOL_VERSION")
    return payload


def partition() -> dict:
    return json.loads(PARTITION_PATH.read_text())
