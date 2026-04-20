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

# --- guard tests ---

def test_create_note_missing_session_returns_400(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80."})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_SESSION_ID"

def test_update_note_text_missing_session_returns_400(client):
    note_id = client.post("/api/notes", json={"text": "BP: 120/80."},
                          headers={"X-Session-ID": SID}).get_json()["note_id"]
    resp = client.put(f"/api/notes/{note_id}/text", json={"text": "HR: 72."})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_SESSION_ID"

def test_update_note_text_wrong_session_returns_403(client):
    note_id = client.post("/api/notes", json={"text": "BP: 120/80."},
                          headers={"X-Session-ID": SID}).get_json()["note_id"]
    resp = client.put(f"/api/notes/{note_id}/text", json={"text": "HR: 72."},
                      headers={"X-Session-ID": SID2})
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "FORBIDDEN"

# --- existing tests updated with session header ---

def test_notes_returns_note_id(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80. HR: 72."},
                       headers={"X-Session-ID": SID})
    assert resp.status_code == 201
    data = resp.get_json()
    assert "note_id" in data
    assert isinstance(data["note_id"], int)

def test_notes_returns_extracted_json(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80."},
                       headers={"X-Session-ID": SID})
    data = resp.get_json()
    assert "extracted_json" in data
    assert "pipeline_version" in data["extracted_json"]

def test_notes_persists_to_db(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80."},
                       headers={"X-Session-ID": SID})
    note_id = resp.get_json()["note_id"]
    resp2 = client.get(f"/api/history/{note_id}", headers={"X-Session-ID": SID})
    assert resp2.status_code == 200

def test_notes_missing_text_returns_400(client):
    resp = client.post("/api/notes", json={}, headers={"X-Session-ID": SID})
    assert resp.status_code == 400

def test_put_note_text_updates_raw_text(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80."},
                       headers={"X-Session-ID": SID})
    note_id = resp.get_json()["note_id"]
    resp2 = client.put(f"/api/notes/{note_id}/text", json={"text": "BP: 130/85. HR: 60."},
                       headers={"X-Session-ID": SID})
    assert resp2.status_code == 200
    data = resp2.get_json()
    assert data["note_id"] == note_id
    assert "extracted_json" in data

def test_put_note_text_reruns_extraction(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80."},
                       headers={"X-Session-ID": SID})
    note_id = resp.get_json()["note_id"]
    original_bp = resp.get_json()["extracted_json"]["vitals"].get("blood_pressure", {}).get("value")
    resp2 = client.put(f"/api/notes/{note_id}/text", json={"text": "HR: 55. Temp: 98.6F."},
                       headers={"X-Session-ID": SID})
    assert resp2.status_code == 200
    new_extracted = resp2.get_json()["extracted_json"]
    assert "pipeline_version" in new_extracted
    new_bp = new_extracted["vitals"].get("blood_pressure", {}).get("value")
    assert new_bp != original_bp

def test_put_note_text_404_on_unknown_note(client):
    resp = client.put("/api/notes/99999/text", json={"text": "Some text."},
                      headers={"X-Session-ID": SID})
    assert resp.status_code == 404
    assert resp.get_json()["code"] == "NOT_FOUND"

def test_put_note_text_400_on_empty_text(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80."},
                       headers={"X-Session-ID": SID})
    note_id = resp.get_json()["note_id"]
    resp2 = client.put(f"/api/notes/{note_id}/text", json={"text": ""},
                       headers={"X-Session-ID": SID})
    assert resp2.status_code == 400
    assert resp2.get_json()["code"] == "TEXT_REQUIRED"

def test_put_note_text_400_on_missing_text_field(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80."},
                       headers={"X-Session-ID": SID})
    note_id = resp.get_json()["note_id"]
    resp2 = client.put(f"/api/notes/{note_id}/text", json={},
                       headers={"X-Session-ID": SID})
    assert resp2.status_code == 400
    assert resp2.get_json()["code"] == "TEXT_REQUIRED"

def test_put_note_text_deletes_old_extraction_and_creates_new(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80."},
                       headers={"X-Session-ID": SID})
    note_id = resp.get_json()["note_id"]
    hist = client.get(f"/api/history/{note_id}", headers={"X-Session-ID": SID}).get_json()
    assert hist["extracted_json"] is not None
    first_pipeline_version = hist["extracted_json"]["pipeline_version"]
    resp2 = client.put(f"/api/notes/{note_id}/text", json={"text": "HR: 72. Temp: 99F."},
                       headers={"X-Session-ID": SID})
    assert resp2.status_code == 200
    hist2 = client.get(f"/api/history/{note_id}", headers={"X-Session-ID": SID}).get_json()
    assert hist2["extracted_json"] is not None
    assert hist2["extracted_json"]["pipeline_version"] == first_pipeline_version
