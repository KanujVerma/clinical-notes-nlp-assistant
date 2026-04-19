import sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app

@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE_URL": "sqlite:///" + str(tmp_path / "test.db")})
    with app.test_client() as c:
        yield c

def test_missing_session_header_on_scoped_route_returns_400(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80."})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "MISSING_SESSION_ID"

def test_empty_session_header_returns_400(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80."},
                       headers={"X-Session-ID": "   "})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_SESSION_ID"

def test_valid_session_header_allows_request(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80."},
                       headers={"X-Session-ID": "test-session-abc"})
    assert resp.status_code == 201

def test_extract_is_exempt_from_session(client):
    resp = client.post("/api/extract", json={"text": "BP: 120/80."})
    assert resp.status_code == 200

def test_health_is_exempt_from_session(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
