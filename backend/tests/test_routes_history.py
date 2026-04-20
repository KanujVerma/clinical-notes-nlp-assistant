import sys, os, json, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import create_app

SID = "test-session-abc"
SID2 = "other-session-xyz"

@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE_URL": "sqlite:///" + str(tmp_path / "test.db")})
    with app.test_client() as c:
        yield c

@pytest.fixture
def seeded_client(client):
    client.post("/api/notes", json={"text": "BP: 120/80. HR: 72."}, headers={"X-Session-ID": SID})
    return client

def test_history_missing_session_returns_400(client):
    resp = client.get("/api/history")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_SESSION_ID"

def test_history_detail_missing_session_returns_400(client):
    resp = client.get("/api/history/1")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_SESSION_ID"

def test_history_returns_list(seeded_client):
    resp = seeded_client.get("/api/history", headers={"X-Session-ID": SID})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "notes" in data
    assert isinstance(data["notes"], list)
    assert len(data["notes"]) == 1

def test_history_note_has_required_fields(seeded_client):
    resp = seeded_client.get("/api/history", headers={"X-Session-ID": SID})
    note = resp.get_json()["notes"][0]
    for field in ["id", "filename", "source", "created_at", "status", "correction_count"]:
        assert field in note

def test_history_detail_returns_full_record(seeded_client):
    list_resp = seeded_client.get("/api/history", headers={"X-Session-ID": SID})
    note_id = list_resp.get_json()["notes"][0]["id"]
    resp = seeded_client.get(f"/api/history/{note_id}", headers={"X-Session-ID": SID})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "raw_text" in data
    assert "extracted_json" in data

def test_history_detail_404_for_missing(client):
    resp = client.get("/api/history/9999", headers={"X-Session-ID": SID})
    assert resp.status_code == 404

def test_history_isolates_by_session(client):
    # SID creates a note; SID2 should not see it in history
    client.post("/api/notes", json={"text": "BP: 120/80."}, headers={"X-Session-ID": SID})
    resp = client.get("/api/history", headers={"X-Session-ID": SID2})
    assert resp.get_json()["notes"] == []

def test_history_detail_forbidden_for_other_session(client):
    # SID creates a note; SID2 cannot access its detail
    note_resp = client.post("/api/notes", json={"text": "BP: 120/80."}, headers={"X-Session-ID": SID})
    note_id = note_resp.get_json()["note_id"]
    resp = client.get(f"/api/history/{note_id}", headers={"X-Session-ID": SID2})
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "FORBIDDEN"
