import sys, os, json, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import create_app

@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE_URL": "sqlite:///" + str(tmp_path / "test.db")})
    with app.test_client() as c:
        yield c

@pytest.fixture
def seeded_client(client):
    client.post("/api/notes", json={"text": "BP: 120/80. HR: 72."})
    return client

def test_history_returns_list(seeded_client):
    resp = seeded_client.get("/api/history")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "notes" in data
    assert isinstance(data["notes"], list)
    assert len(data["notes"]) == 1

def test_history_note_has_required_fields(seeded_client):
    resp = seeded_client.get("/api/history")
    note = resp.get_json()["notes"][0]
    for field in ["id", "filename", "source", "created_at", "status", "correction_count"]:
        assert field in note

def test_history_detail_returns_full_record(seeded_client):
    list_resp = seeded_client.get("/api/history")
    note_id = list_resp.get_json()["notes"][0]["id"]
    resp = seeded_client.get(f"/api/history/{note_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "raw_text" in data
    assert "extracted_json" in data

def test_history_detail_404_for_missing(client):
    resp = client.get("/api/history/9999")
    assert resp.status_code == 404
