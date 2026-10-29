"""Real Flask hosted-mode integration with already-migrated disposable database.

No mocked HTTP endpoints, no paid inference, no external database and no
synthetic evaluation model output passed off as recorded AI evidence.
"""
import hashlib
import json

import pytest

from app import create_app
from config import Config
from models import Extraction, Note
from services.hosted_release import HostedFixtureError, verified_scenarios
from utils.db import get_engine, get_session, init_db


def _temp_fixture(root):
    d = root / "showcase" / "notes"
    d.mkdir(parents=True)
    text = "Synthetic demo: Metformin 500 mg PO BID.\n"
    (d / "case_001.txt").write_text(text, encoding="utf-8")
    content = [{
        "filename": "case_001.txt",
        "raw_text": text,
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "extraction": {
            "metadata": {}, "vitals": {},
            "instructions": {}, "medications": [],
        },
        "issues": [],
    }]
    (root / "precomputed_scenarios.json").write_text(json.dumps(content), encoding="utf-8")
    return content


def test_curated_inventory_rejects_missing_tampered_and_orphan_sources(tmp_path):
    content = _temp_fixture(tmp_path)
    assert list(verified_scenarios(tmp_path)) == ["case_001.txt"]

    source = tmp_path / "showcase" / "notes" / "case_001.txt"
    source.write_text("Modified synthetic text\n", encoding="utf-8")
    with pytest.raises(HostedFixtureError, match="CURATED_SOURCE_HASH_MISMATCH"):
        verified_scenarios(tmp_path)

    source.write_text(content[0]["raw_text"], encoding="utf-8")
    (source.parent / "orphan.txt").write_text("Orphan fixture\n", encoding="utf-8")
    with pytest.raises(HostedFixtureError, match="CURATED_INVENTORY_MISMATCH"):
        verified_scenarios(tmp_path)


def test_curated_inventory_rejects_duplicate_and_unstructured_labels(tmp_path):
    content = _temp_fixture(tmp_path)
    bundle = tmp_path / "precomputed_scenarios.json"
    bundle.write_text(json.dumps(content + content), encoding="utf-8")
    with pytest.raises(HostedFixtureError):
        verified_scenarios(tmp_path)

    content[0]["extraction"]["medications"] = "not a structured medication array"
    bundle.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(HostedFixtureError, match="CURATED_FIXTURES_INVALID"):
        verified_scenarios(tmp_path)


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Pre-migrate on a disposable database *before* creating hosted Flask.
    db_url = f"sqlite:///{tmp_path / 'hosted_release_test.db'}"
    engine = get_engine(db_url)
    init_db(engine, migrate=True)
    engine.dispose()
    monkeypatch.setattr(Config, "APP_MODE", "hosted_demo")
    monkeypatch.setattr(Config, "FRONTEND_URL", "http://localhost:5173")
    monkeypatch.setattr(Config, "ENABLE_EXTERNAL_EXPLAINER", False)
    app = create_app({"DATABASE_URL": db_url, "TESTING": False})
    return app.test_client()


def _create_workspace(client):
    created = client.post("/api/workspaces")
    assert created.status_code == 201, created.json
    return {
        "X-Workspace-ID": created.json["workspace_id"],
        "X-Workspace-Token": created.json["token"],
    }


def test_real_hosted_endpoint_flow_seeds_review_and_isolates_workspaces(client):
    assert client.get("/api/health/ready").status_code == 200
    assert client.get("/api/capabilities").json["mode"] == "hosted_demo"
    first, second = _create_workspace(client), _create_workspace(client)

    seeded = client.post("/api/seed-demo", headers=first)
    assert seeded.status_code == 200, seeded.json
    assert seeded.json["loaded"] == 10  # real curated file bundle

    queued = client.get("/api/queue", headers=first)
    assert queued.status_code == 200
    assert queued.json["count"] == 10
    assert client.get("/api/queue", headers=second).json["count"] == 0

    # Real active fixture with no critical issue and a complete bound review.
    for row in queued.json["notes"]:
        detail = client.get(f'/api/notes/{row["id"]}', headers=first).json
        critical = [i for i in detail.get("issues", [])
                    if i["severity"] == "critical_blocker" and i["status"] == "open"]
        if not critical:
            break
    else:
        pytest.fail("Curated dataset contains no reviewable synthetic note")

    assert client.get(f'/api/notes/{row["id"]}', headers=second).status_code in (403, 404)
    decisions = {}
    extracted = detail["extracted_json"]
    for category in ("metadata", "vitals", "instructions"):
        for key, value in (extracted.get(category) or {}).items():
            if value is not None:
                decisions[f"{category}.{key}"] = {"decision": "accept"}
    for i, med in enumerate(extracted.get("medications") or []):
        med_id = med.get("id") or med.get("source_occurrence_id") or f"med_{i}"
        decisions[f"med.{med_id}"] = {"decision": "accept"}

    response = client.post(
        f'/api/extractions/{detail["current_extraction_id"]}/reviews',
        headers=first,
        json={
            "note_id": row["id"],
            "source_revision_id": detail["current_source_revision_id"],
            "source_hash": detail["source_hash"],
            "extraction_id": detail["current_extraction_id"],
            "expected_lock_version": detail["lock_version"],
            "event_kind": "review_completed",
            "item_decisions": decisions,
            "category_acknowledgments": {
                "metadata": True, "vitals": True,
                "medications": True, "instructions": True,
            },
            "idempotency_key": "hosted-synthetic-review-case-001",
        },
    )
    assert response.status_code == 201, response.json
    assert response.json["derived_outcome"] in ("reviewed_unchanged", "reviewed_corrected")
    assert client.get("/api/queue", headers=first).json["count"] == 9
    assert client.get("/api/queue", headers=second).json["count"] == 0

    # Content-bearing responses must not be stored by intermediary caches.
    note_response = client.get(f'/api/notes/{row["id"]}', headers=first)
    assert note_response.headers["Cache-Control"] == "no-store, private"
    assert note_response.headers["X-Content-Type-Options"] == "nosniff"


def test_real_hosted_denies_unauthorized_inputs_and_paid_inference(client):
    headers = _create_workspace(client)
    assert client.get("/api/queue", headers={"X-Workspace-ID": headers["X-Workspace-ID"]}).status_code == 401
    assert client.post("/api/notes", headers=headers, json={"text": "Arbitrary clinical note"}).status_code == 403
    assert client.post("/api/extract", json={"text": "Arbitrary clinical note"}).status_code == 403
    assert client.post("/api/upload", headers=headers).status_code == 403
    assert client.post("/api/evaluation/runs", headers=headers).status_code == 403
    assert client.post("/api/jobs", headers=headers, json={"kind": "eval_run"}).status_code == 403
    assert client.post("/api/explain", headers=headers, json={"value": "aspirin"}).status_code == 403
    assert client.post("/api/notes/1/ai-candidates", headers=headers, json={}).status_code == 403
    assert client.post("/api/notes/1/revisions", headers=headers, json={"text": "New"}).status_code == 403


def test_real_hosted_seed_is_idempotent_and_not_live_nlp(client, monkeypatch):
    headers = _create_workspace(client)
    import extractors.pipeline

    def deny(*args, **kwargs):
        raise AssertionError("Hosted release must never call live NLP extraction")

    monkeypatch.setattr(extractors.pipeline, "run_pipeline", deny)
    first = client.post("/api/seed-demo", headers=headers)
    second = client.post("/api/seed-demo", headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json["loaded"] == 10
    assert second.json["loaded"] == 0
    assert second.json["skipped"] == 10


def test_hosted_preflight_sanitizes_db_errors():
    import os
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    res = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "hosted_preflight.py"),
            "--check-db",
        ],
        cwd=str(root),
        env={
            **os.environ,
            "APP_MODE": "hosted_demo",
            "FRONTEND_URL": "http://localhost:5173",
            "ENABLE_EXTERNAL_EXPLAINER": "false",
            "DATABASE_URL": "postgresql://user:super_secret_password@127.0.0.1:5432/bad_db",
        },
        capture_output=True,
        text=True,
    )
    assert res.returncode == 2
    assert "super_secret_password" not in res.stderr
    assert "super_secret_password" not in res.stdout
    data = json.loads(res.stderr.strip())
    assert data["status"] == "blocked"
    assert data["code"] == "DATABASE_SCHEMA_OR_CONNECTION_FAILED"
