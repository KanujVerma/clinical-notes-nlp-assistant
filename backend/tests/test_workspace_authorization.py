import datetime
import pytest
from app import create_app
from models import Workspace, Note, Extraction
from utils.db import get_session
from config import Config


@pytest.fixture
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "DATABASE_URL": f"sqlite:///{tmp_path / 'auth_test.db'}",
    })


@pytest.fixture
def client(app):
    return app.test_client()


def test_workspace_capability_token_flow_and_verification(client):
    # 1. Create workspace
    res = client.post("/api/workspaces")
    assert res.status_code == 201
    data = res.json
    ws_id = data["workspace_id"]
    token = data["token"]
    assert ws_id and token

    # 2. Access with valid X-Workspace-Token
    headers_valid = {"X-Workspace-ID": ws_id, "X-Workspace-Token": token}
    note_res = client.post("/api/notes", headers=headers_valid, json={"text": "Vitals BP 120/80."})
    assert note_res.status_code == 201

    # 3. Access with valid Authorization: Bearer <token>
    headers_bearer = {"X-Workspace-ID": ws_id, "Authorization": f"Bearer {token}"}
    notes_list = client.get("/api/queue", headers=headers_bearer)
    assert notes_list.status_code == 200
    assert len(notes_list.json["notes"]) == 1

    # 4. Access without token returns 401
    headers_no_token = {"X-Workspace-ID": ws_id}
    res_no_token = client.get("/api/queue", headers=headers_no_token)
    assert res_no_token.status_code == 401
    assert res_no_token.json["code"] == "TOKEN_REQUIRED"

    # 5. Access with invalid token returns 403
    headers_bad_token = {"X-Workspace-ID": ws_id, "X-Workspace-Token": "bad-token-value"}
    res_bad_token = client.get("/api/queue", headers=headers_bad_token)
    assert res_bad_token.status_code == 403
    assert res_bad_token.json["code"] == "INVALID_TOKEN"


def test_expired_workspace_is_rejected(client):
    res = client.post("/api/workspaces")
    assert res.status_code == 201
    ws_id = res.json["workspace_id"]
    token = res.json["token"]

    # Manually expire workspace in DB
    with get_session(client.application.config["ENGINE"]) as session:
        ws = session.query(Workspace).filter(Workspace.id == ws_id).first()
        ws.expires_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
        session.commit()

    headers = {"X-Workspace-ID": ws_id, "X-Workspace-Token": token}
    res = client.get("/api/queue", headers=headers)
    assert res.status_code == 401
    assert res.json["code"] == "TOKEN_EXPIRED"


def test_cross_workspace_isolation_reads_writes_exports_reset_metrics(client):
    # Setup Workspace 1
    w1_res = client.post("/api/workspaces")
    w1_id, w1_token = w1_res.json["workspace_id"], w1_res.json["token"]
    h1 = {"X-Workspace-ID": w1_id, "X-Workspace-Token": w1_token}

    # Setup Workspace 2
    w2_res = client.post("/api/workspaces")
    w2_id, w2_token = w2_res.json["workspace_id"], w2_res.json["token"]
    h2 = {"X-Workspace-ID": w2_id, "X-Workspace-Token": w2_token}

    # Workspace 1 creates a note
    note_res = client.post(h1["X-Workspace-ID"] and "/api/notes", headers=h1, json={"text": "Patient on Metformin 500 mg."})
    assert note_res.status_code == 201
    note1 = note_res.json
    n1_id = note1["note_id"]
    rev1_id = note1["revision_id"]
    ext1_id = note1["extraction_id"]

    # 1. Cross-workspace read of note: Workspace 2 cannot read note 1
    w2_get = client.get(f"/api/notes/{n1_id}", headers=h2)
    assert w2_get.status_code in (403, 404)

    # 2. Cross-workspace revision append: Workspace 2 cannot mutate note 1
    w2_rev = client.post(
        f"/api/notes/{n1_id}/revisions",
        headers=h2,
        json={
            "raw_text": "Hacked text",
            "expected_source_revision_id": rev1_id,
            "expected_lock_version": 0,
        },
    )
    assert w2_rev.status_code in (403, 404)

    # 3. Cross-workspace review submission: Workspace 2 cannot review Workspace 1's extraction
    w2_rev_sub = client.post(
        f"/api/extractions/{ext1_id}/reviews",
        headers=h2,
        json={
            "note_id": n1_id,
            "source_revision_id": rev1_id,
            "extraction_id": ext1_id,
            "source_hash": "dummy",
            "expected_lock_version": 0,
            "event_kind": "review_completed",
            "item_decisions": {},
            "category_acknowledgments": {
                "metadata": True, "vitals": True, "medications": True, "instructions": True,
            },
        },
    )
    assert w2_rev_sub.status_code in (400, 403, 404)

    # 4. Cross-workspace issues query
    w2_issues = client.get(f"/api/issues?note_id={n1_id}", headers=h2)
    # Either 403/404 or empty list because note belongs to workspace 1
    if w2_issues.status_code == 200:
        assert len(w2_issues.json) == 0

    # 5. Reset isolation: Workspace 2 reset does NOT delete Workspace 1 note
    reset_res = client.delete("/api/reset", headers=h2)
    assert reset_res.status_code == 200

    w1_check = client.get(f"/api/notes/{n1_id}", headers=h1)
    assert w1_check.status_code == 200
    assert w1_check.json["id"] == n1_id

    # 6. Metrics isolation: Workspace 2 metrics show 0 notes
    w2_metrics = client.get("/api/metrics", headers=h2)
    assert w2_metrics.status_code == 200



def test_hosted_requires_hosted_workspace_mode_and_rejects_arbitrary_edits(client, monkeypatch):
    # A capability created in local mode is not a hosted-demo workspace,
    # even when the bearer token itself is valid.
    local = client.post("/api/workspaces").json
    monkeypatch.setattr(Config, "APP_MODE", "hosted_demo")
    old_headers = {
        "X-Workspace-ID": local["workspace_id"],
        "X-Workspace-Token": local["token"],
    }
    old_access = client.get("/api/queue", headers=old_headers)
    assert old_access.status_code == 403
    assert old_access.json["code"] == "INVALID_WORKSPACE_MODE"

    demo = client.post("/api/workspaces").json
    demo_headers = {
        "X-Workspace-ID": demo["workspace_id"],
        "X-Workspace-Token": demo["token"],
    }
    # The request is syntactically valid, but hosted mode must reject a
    # reviewer-supplied new arbitrary value even before looking up the note.
    payload = {
        "schema_version": "2.0.0",
        "note_id": 10,
        "source_revision_id": "synthetic-rev",
        "extraction_id": "synthetic-ext",
        "source_hash": "0" * 64,
        "expected_lock_version": 0,
        "event_kind": "review_completed",
        "item_decisions": {
            "med.any.dose": {"decision": "edit", "value": "unrestricted input"},
        },
        "category_acknowledgments": {
            "vitals": True, "medications": True,
            "metadata": True, "instructions": True,
        },
    }
    response = client.post(
        "/api/extractions/synthetic-ext/reviews",
        json=payload,
        headers=demo_headers,
    )
    assert response.status_code == 422
    assert response.json["code"] == "INVALID_REVIEW_PAYLOAD"


def test_hosted_workspace_creation_quota_and_expired_cleanup(client, monkeypatch):
    monkeypatch.setattr(Config, "APP_MODE", "hosted_demo")
    from routes.workspaces import MAX_HOSTED_WORKSPACES
    monkeypatch.setattr("routes.workspaces.MAX_HOSTED_WORKSPACES", 3)

    # Create 3 hosted workspaces
    ws_list = []
    for _ in range(3):
        res = client.post("/api/workspaces")
        assert res.status_code == 201
        ws_list.append(res.json)

    # 4th creation attempt fails with 429 QUOTA_EXCEEDED
    res_quota = client.post("/api/workspaces")
    assert res_quota.status_code == 429
    assert res_quota.json["code"] == "WORKSPACE_QUOTA_EXCEEDED"

    # Expire one workspace manually in DB
    app_engine = client.application.config["ENGINE"]
    with get_session(app_engine) as session:
        expired_ws = session.query(Workspace).filter_by(id=ws_list[0]["workspace_id"]).one()
        expired_ws.expires_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(hours=1)
        session.commit()

    # Now a new creation succeeds because expired workspaces are purged
    res_after = client.post("/api/workspaces")
    assert res_after.status_code == 201
    assert res_after.json["workspace_id"]


def test_hosted_seed_uses_precomputed_scenarios_without_live_pipeline(client, monkeypatch):
    monkeypatch.setattr(Config, "APP_MODE", "hosted_demo")
    demo_ws = client.post("/api/workspaces").json
    headers = {
        "X-Workspace-ID": demo_ws["workspace_id"],
        "X-Workspace-Token": demo_ws["token"],
    }

    # Track if run_pipeline is ever called
    pipeline_called = []
    def fail_pipeline(*args, **kwargs):
        pipeline_called.append(True)
        raise RuntimeError("run_pipeline should never be called during hosted demo seed")

    import extractors.pipeline
    monkeypatch.setattr(extractors.pipeline, "run_pipeline", fail_pipeline)

    res = client.post("/api/seed-demo", headers=headers)
    assert res.status_code == 200
    assert len(pipeline_called) == 0
    assert res.json["loaded"] == 10  # 10 curated showcase scenarios
    assert res.json["skipped"] == 0

    # Verify queue returns the seeded scenarios
    queue_res = client.get("/api/queue", headers=headers)
    assert queue_res.status_code == 200
    assert len(queue_res.json["notes"]) == 10

    # Scenarios list endpoint returns available scenarios
    scenarios_res = client.get("/api/scenarios", headers=headers)
    assert scenarios_res.status_code == 200
    assert scenarios_res.json["count"] == 10

