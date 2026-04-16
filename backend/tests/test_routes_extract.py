import sys, os, json, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import create_app

@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DB_PATH": str(tmp_path / "test.db")})
    with app.test_client() as c:
        yield c

def test_extract_returns_200(client):
    resp = client.post("/api/extract", json={"text": "BP: 120/80. HR: 72."})
    assert resp.status_code == 200

def test_extract_returns_pipeline_version(client):
    resp = client.post("/api/extract", json={"text": "BP: 120/80. HR: 72."})
    data = resp.get_json()
    assert "pipeline_version" in data

def test_extract_returns_vitals(client):
    resp = client.post("/api/extract", json={"text": "BP: 120/80. HR: 72."})
    data = resp.get_json()
    assert "vitals" in data
    assert "blood_pressure" in data["vitals"]

def test_extract_missing_text_returns_400(client):
    resp = client.post("/api/extract", json={})
    assert resp.status_code == 400
    assert "error" in resp.get_json()

def test_extract_no_db_write(client, tmp_path):
    client.post("/api/extract", json={"text": "BP: 120/80."})
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    conn.close()
    assert count == 0
