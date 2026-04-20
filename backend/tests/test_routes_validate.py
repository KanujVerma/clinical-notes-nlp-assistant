import sys, os, json, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import create_app
from utils.corrections import compute_correction_count

SID = "test-session-abc"
SID2 = "other-session-xyz"

@pytest.fixture
def client(tmp_path):
    app = create_app({
        "TESTING": True,
        "DATABASE_URL": "sqlite:///" + str(tmp_path / "test.db"),
        "EVAL_RESULTS_PATH": str(tmp_path / "nonexistent_results.json"),
    })
    with app.test_client() as c:
        yield c

@pytest.fixture
def note_id(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80. HR: 72."}, headers={"X-Session-ID": SID})
    return resp.get_json()["note_id"]

def test_validate_missing_session_returns_400(client):
    resp = client.post("/api/validate", json={
        "note_id": 1,
        "validated_json": {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}},
        "status": "accepted",
    })
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_SESSION_ID"

def test_validate_returns_200(client, note_id):
    resp = client.post("/api/validate", json={
        "note_id": note_id,
        "validated_json": {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}},
        "status": "accepted",
        "review_duration_ms": 5000,
    }, headers={"X-Session-ID": SID})
    assert resp.status_code == 200

def test_validate_upserts(client, note_id):
    payload = {
        "note_id": note_id,
        "validated_json": {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}},
        "status": "accepted",
        "review_duration_ms": 3000,
    }
    client.post("/api/validate", json=payload, headers={"X-Session-ID": SID})
    payload["status"] = "corrected"
    resp = client.post("/api/validate", json=payload, headers={"X-Session-ID": SID})
    assert resp.status_code == 200
    detail = client.get(f"/api/history/{note_id}", headers={"X-Session-ID": SID}).get_json()
    assert detail["validation"]["status"] == "corrected"

def test_correction_count_computed():
    ext = {"vitals": {"blood_pressure": {"value": "120/80"}}, "medications": [], "instructions": {}, "metadata": {}}
    val = {"vitals": {"blood_pressure": {"value": "130/85"}}, "medications": [], "instructions": {}, "metadata": {}}
    assert compute_correction_count(ext, val) == 1

def test_validate_missing_note_id_returns_400(client):
    resp = client.post("/api/validate", json={"status": "accepted"}, headers={"X-Session-ID": SID})
    assert resp.status_code == 400

def test_validate_nonexistent_note_returns_404(client):
    resp = client.post("/api/validate", json={
        "note_id": 9999,
        "validated_json": {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}},
        "status": "accepted",
    }, headers={"X-Session-ID": SID})
    assert resp.status_code == 404

def test_validate_other_session_note_returns_403(client):
    # SID creates a note; SID2 should not be able to validate it
    note_resp = client.post("/api/notes", json={"text": "BP: 120/80."}, headers={"X-Session-ID": SID})
    nid = note_resp.get_json()["note_id"]
    resp = client.post("/api/validate", json={
        "note_id": nid,
        "validated_json": {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}},
        "status": "accepted",
    }, headers={"X-Session-ID": SID2})
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "FORBIDDEN"

def test_metrics_null_eval_when_no_results_file(client):
    resp = client.get("/api/metrics", headers={"X-Session-ID": SID})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "eval" in data
    assert data["eval"] is None
    assert "db_stats" in data

def test_validate_response_includes_message_and_next_pending_id(client, note_id):
    resp = client.post("/api/validate", json={
        "note_id": note_id,
        "validated_json": {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}},
        "status": "accepted",
    }, headers={"X-Session-ID": SID})
    assert resp.status_code == 200
    body = resp.get_json()
    assert "message" in body
    assert "next_pending_id" in body
    assert body["next_pending_id"] is None

def test_validate_next_pending_id_returns_unvalidated_note(client):
    resp1 = client.post("/api/notes", json={"text": "BP: 120/80. HR: 72."}, headers={"X-Session-ID": SID})
    note_id_1 = resp1.get_json()["note_id"]
    resp2 = client.post("/api/notes", json={"text": "HR: 68. Weight: 150 lbs."}, headers={"X-Session-ID": SID})
    note_id_2 = resp2.get_json()["note_id"]

    resp = client.post("/api/validate", json={
        "note_id": note_id_1,
        "validated_json": {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}},
        "status": "accepted",
    }, headers={"X-Session-ID": SID})
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["next_pending_id"] == note_id_2

def test_validate_next_pending_id_ignores_other_session(client):
    # SID2 creates a pending note; SID should not see it as next_pending_id
    client.post("/api/notes", json={"text": "HR: 68."}, headers={"X-Session-ID": SID2})
    note_resp = client.post("/api/notes", json={"text": "BP: 120/80."}, headers={"X-Session-ID": SID})
    nid = note_resp.get_json()["note_id"]

    resp = client.post("/api/validate", json={
        "note_id": nid,
        "validated_json": {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}},
        "status": "accepted",
    }, headers={"X-Session-ID": SID})
    body = resp.get_json()
    assert body["next_pending_id"] is None
