import sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import create_app

@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DB_PATH": str(tmp_path / "test.db")})
    with app.test_client() as c:
        yield c

def test_notes_returns_note_id(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80. HR: 72."})
    assert resp.status_code == 201
    data = resp.get_json()
    assert "note_id" in data
    assert isinstance(data["note_id"], int)

def test_notes_returns_extracted_json(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80."})
    data = resp.get_json()
    assert "extracted_json" in data
    assert "pipeline_version" in data["extracted_json"]

def test_notes_persists_to_db(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80."})
    note_id = resp.get_json()["note_id"]
    resp2 = client.get(f"/api/history/{note_id}")
    assert resp2.status_code == 200

def test_notes_missing_text_returns_400(client):
    resp = client.post("/api/notes", json={})
    assert resp.status_code == 400
