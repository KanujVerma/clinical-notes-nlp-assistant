import sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import create_app

SID = "test-session-abc"
SID2 = "other-session-xyz"

@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE_URL": "sqlite:///" + str(tmp_path / "test.db")})
    with app.test_client() as c:
        yield c


def _create_note(client, sid=SID, text="BP: 120/80."):
    resp = client.post("/api/notes", json={"text": text}, headers={"X-Session-ID": sid})
    assert resp.status_code == 201
    return resp.get_json()["note_id"]


def _validate_note(client, note_id, sid=SID):
    client.post("/api/validate", json={
        "note_id": note_id,
        "validated_json": {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}},
        "status": "accepted",
        "review_duration_ms": 100,
    }, headers={"X-Session-ID": sid})


def test_reset_missing_session_returns_400(client):
    resp = client.delete("/api/reset")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_SESSION_ID"


def test_reset_empty_workspace_returns_zeros(client):
    resp = client.delete("/api/reset", headers={"X-Session-ID": SID})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {"deleted_notes": 0, "deleted_extractions": 0, "deleted_validations": 0}


def test_reset_deletes_notes_and_extractions(client):
    _create_note(client)
    _create_note(client, text="HR: 72.")
    resp = client.delete("/api/reset", headers={"X-Session-ID": SID})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["deleted_notes"] == 2
    assert data["deleted_extractions"] == 2
    assert data["deleted_validations"] == 0


def test_reset_deletes_validations_too(client):
    nid = _create_note(client)
    _validate_note(client, nid)
    resp = client.delete("/api/reset", headers={"X-Session-ID": SID})
    data = resp.get_json()
    assert data["deleted_notes"] == 1
    assert data["deleted_extractions"] == 1
    assert data["deleted_validations"] == 1


def test_reset_clears_history(client):
    _create_note(client)
    client.delete("/api/reset", headers={"X-Session-ID": SID})
    resp = client.get("/api/history", headers={"X-Session-ID": SID})
    assert resp.get_json()["notes"] == []


def test_reset_idempotent(client):
    _create_note(client)
    client.delete("/api/reset", headers={"X-Session-ID": SID})
    resp = client.delete("/api/reset", headers={"X-Session-ID": SID})
    assert resp.status_code == 200
    assert resp.get_json()["deleted_notes"] == 0


def test_reset_only_deletes_own_session(client):
    # SID creates a note; SID2 resets — SID's note should survive
    _create_note(client, sid=SID)
    client.delete("/api/reset", headers={"X-Session-ID": SID2})
    resp = client.get("/api/history", headers={"X-Session-ID": SID})
    assert len(resp.get_json()["notes"]) == 1
