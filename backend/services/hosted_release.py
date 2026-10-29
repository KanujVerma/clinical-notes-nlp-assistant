"""Fail-closed, precomputed synthetic-showcase validation.

Hosted visitors may load only the exact checked-in synthetic note inventory and
its deterministic extraction/issue fixtures. No NLP or external model runs,
patient uploads, unbounded paths, or silent skipping of missing labels.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


class HostedFixtureError(ValueError):
    """Public-safe code, never a user-supplied filename or input text."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


REQUIRED_EXTRACTION_CATEGORIES = {"metadata", "vitals", "medications", "instructions"}
VALID_SEVERITIES = {"critical_blocker", "warning", "info"}
MAX_SHOWCASE_CASES = 20
MAX_NOTE_BYTES = 256 * 1024
MAX_BUNDLE_BYTES = 4 * 1024 * 1024


def verified_scenarios(data_dir: str | Path) -> dict[str, dict]:
    """Verify full fixture inventory, source bytes and structured labels.

    The JSON bundle is not trusted simply because it is checked in. This
    function deliberately reads no directory outside the supplied data root
    and does not infer or claim clinical provenance from a hash.
    """
    root = Path(data_dir).resolve()
    note_dir = root / "showcase" / "notes"
    bundle_path = root / "precomputed_scenarios.json"
    if not note_dir.is_dir() or not bundle_path.is_file():
        raise HostedFixtureError("CURATED_FIXTURES_MISSING")
    if bundle_path.stat().st_size > MAX_BUNDLE_BYTES:
        raise HostedFixtureError("CURATED_FIXTURES_TOO_LARGE")

    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError, OSError) as exc:
        raise HostedFixtureError("CURATED_FIXTURES_INVALID") from exc
    if not isinstance(bundle, list) or not 1 <= len(bundle) <= MAX_SHOWCASE_CASES:
        raise HostedFixtureError("CURATED_FIXTURES_INVALID")

    files = {
        file.name: file for file in note_dir.iterdir()
        if file.is_file() and file.suffix == ".txt" and not file.is_symlink()
    }
    if len(files) != len(bundle):
        raise HostedFixtureError("CURATED_INVENTORY_MISMATCH")

    verified: dict[str, dict] = {}
    for item in bundle:
        if not isinstance(item, dict):
            raise HostedFixtureError("CURATED_FIXTURES_INVALID")
        name = item.get("filename")
        if (not isinstance(name, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}\.txt", name)
                or name in verified or name not in files):
            raise HostedFixtureError("CURATED_INVENTORY_MISMATCH")

        raw = item.get("raw_text")
        digest = item.get("sha256")
        extraction = item.get("extraction")
        issues = item.get("issues")
        if (not isinstance(raw, str) or not raw.strip()
                or not isinstance(digest, str)
                or not re.fullmatch(r"[a-f0-9]{64}", digest)
                or not isinstance(extraction, dict)
                or not REQUIRED_EXTRACTION_CATEGORIES.issubset(extraction)
                or not isinstance(extraction["medications"], list)
                or not all(isinstance(extraction[k], dict)
                           for k in ("vitals", "instructions", "metadata"))
                or not isinstance(issues, list) or len(issues) > 100):
            raise HostedFixtureError("CURATED_FIXTURES_INVALID")
        if not all(isinstance(m, dict) and bool(m.get("name"))
                   for m in extraction["medications"]):
            raise HostedFixtureError("CURATED_EXTRACTION_INVALID")
        if not all(
            isinstance(issue, dict)
            and issue.get("severity") in VALID_SEVERITIES
            and isinstance(issue.get("issue_code"), str)
            and isinstance(issue.get("category"), str)
            and isinstance(issue.get("safe_explanation", ""), str)
            for issue in issues
        ):
            raise HostedFixtureError("CURATED_ISSUES_INVALID")

        source = files[name].read_bytes()
        if not source or len(source) > MAX_NOTE_BYTES:
            raise HostedFixtureError("CURATED_SOURCE_INVALID")
        try:
            text = source.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HostedFixtureError("CURATED_SOURCE_INVALID") from exc
        if text != raw or hashlib.sha256(source).hexdigest() != digest:
            raise HostedFixtureError("CURATED_SOURCE_HASH_MISMATCH")
        verified[name] = item

    if set(verified) != set(files):
        raise HostedFixtureError("CURATED_INVENTORY_MISMATCH")
    return verified
