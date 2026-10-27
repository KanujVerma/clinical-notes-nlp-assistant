import json
import zipfile
import io
import pytest
from app import create_app


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "test_routes.db"
    test_config = {
        "TESTING": True,
        "DATABASE_URL": f"sqlite:///{db_path}",
    }
    app = create_app(test_config)
    with app.test_client() as c:
        yield c


def test_health_live_and_ready(client):
    r1 = client.get("/api/health/live")
    assert r1.status_code == 200
    assert r1.json["status"] == "live"

    r2 = client.get("/api/health/ready")
    assert r2.status_code == 200
    assert r2.json["status"] == "ready"


def test_workspace_creation_and_capabilities(client):
    r1 = client.post("/api/workspaces")
    assert r1.status_code == 201
    data = r1.json
    assert "workspace_id" in data
    assert "token" in data

    r2 = client.get("/api/capabilities")
    assert r2.status_code == 200
    assert "mode" in r2.json


def test_note_lifecycle_revisions_and_review_export(client):
    # 1. Create workspace
    ws_res = client.post("/api/workspaces")
    ws_id = ws_res.json["workspace_id"]
    token = ws_res.json["token"]
    headers = {"X-Workspace-ID": ws_id, "X-Workspace-Token": token}

    # 2. Create note
    raw_note = "Patient was prescribed Lisinopril 10 mg daily for hypertension."
    note_res = client.post("/api/notes", headers=headers, json={"text": raw_note})
    assert note_res.status_code == 201
    note_data = note_res.json
    note_id = note_data["note_id"]
    rev_id = note_data["revision_id"]
    ext_id = note_data["extraction_id"]

    # 3. Get note source
    src_res = client.get(f"/api/notes/{note_id}/source", headers=headers)
    assert src_res.status_code == 200
    assert src_res.json["raw_text"] == raw_note

    # 4. Check issues endpoint
    issues_res = client.get(f"/api/issues?note_id={note_id}", headers=headers)
    assert issues_res.status_code == 200
    assert isinstance(issues_res.json, list)

    # 5. Complete review via /api/extractions/<id>/reviews
    src_hash = src_res.json["sha256"]
    review_payload = {
        "note_id": note_id,
        "source_revision_id": rev_id,
        "extraction_id": ext_id,
        "source_hash": src_hash,
        "expected_lock_version": 0,
        "event_kind": "review_completed",
        "item_decisions": {"med_lisinopril": {"decision": "accept"}},
        "category_acknowledgments": {
            "metadata": True,
            "vitals": True,
            "medications": True,
            "instructions": True,
        },
        "idempotency_key": "idemp-test-001",
    }
    rev_res = client.post(
        f"/api/extractions/{ext_id}/reviews",
        headers=headers,
        json=review_payload,
    )
    assert rev_res.status_code == 201
    event_id = rev_res.json["event_id"]
    assert rev_res.json["derived_outcome"] in ("reviewed_unchanged", "reviewed_corrected")

    # 6. Idempotent replay check
    replay_res = client.post(
        f"/api/extractions/{ext_id}/reviews",
        headers=headers,
        json=review_payload,
    )
    assert replay_res.status_code == 200
    assert replay_res.json["is_replay"] is True

    # 7. Check export ZIP
    export_res = client.get(f"/api/review-events/{event_id}/export", headers=headers)
    assert export_res.status_code == 200
    assert export_res.headers["Content-Type"] == "application/zip"

    # Verify ZIP contents and manifest
    zip_buf = io.BytesIO(export_res.data)
    with zipfile.ZipFile(zip_buf, "r") as zf:
        namelist = zf.namelist()
        assert "reviewed_extraction.json" in namelist
        assert "original_extraction.json" in namelist
        assert "review_decisions.json" in namelist
        assert "source_revision.json" in namelist
        assert "summary.html" in namelist
        assert "manifest.json" in namelist

        manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert "reviewed_extraction.json" in manifest_data

    # 8. Append a new source revision (transcription fix)
    edited_note = "Patient was prescribed Lisinopril 20 mg daily for hypertension."
    edit_res = client.post(
        f"/api/notes/{note_id}/revisions",
        headers=headers,
        json={
            "raw_text": edited_note,
            "reason": "transcription_fix",
            "expected_source_revision_id": rev_id,
            "expected_lock_version": 1,
        },
    )
    assert edit_res.status_code == 201
    assert edit_res.json["revision_number"] == 2
    assert edit_res.json["status"] == "needs_review"  # Rule A16: Invalidate completed review!

    # 9. Verify Note state shows needs_review and review_head is cleared
    note_check = client.get(f"/api/notes/{note_id}", headers=headers)
    assert note_check.status_code == 200
    assert note_check.json["status"] == "needs_review"
    assert note_check.json["review_head"] is None
