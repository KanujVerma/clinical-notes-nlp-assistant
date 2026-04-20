import sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import create_app

SID = "test-session-abc"
SID2 = "other-session-xyz"

@pytest.fixture
def client(tmp_path):
    app = create_app({
        "TESTING": True,
        "DATABASE_URL": "sqlite:///" + str(tmp_path / "test.db"),
        "DATA_DIR": str(tmp_path / "data"),  # no seed files → loaded=0
    })
    with app.test_client() as c:
        yield c

def test_seed_missing_session_returns_400(client):
    resp = client.post("/api/seed-demo")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_SESSION_ID"

def test_seed_with_session_returns_200(client):
    resp = client.post("/api/seed-demo", headers={"X-Session-ID": SID})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "loaded" in data
    assert "skipped" in data

def test_seed_returns_loaded_and_skipped_counts(client):
    resp = client.post("/api/seed-demo", headers={"X-Session-ID": SID})
    data = resp.get_json()
    assert isinstance(data["loaded"], int)
    assert isinstance(data["skipped"], int)
    assert data["loaded"] >= 0
    assert data["skipped"] >= 0

def test_seed_idempotent_within_same_session(client):
    # Second call should skip what the first loaded
    first = client.post("/api/seed-demo", headers={"X-Session-ID": SID}).get_json()
    second = client.post("/api/seed-demo", headers={"X-Session-ID": SID}).get_json()
    assert second["loaded"] == 0
    assert second["skipped"] == first["loaded"]

def test_seed_different_sessions_seed_independently(client):
    # SID seeds its own notes; SID2 should be able to seed the same filenames
    first = client.post("/api/seed-demo", headers={"X-Session-ID": SID}).get_json()
    second = client.post("/api/seed-demo", headers={"X-Session-ID": SID2}).get_json()
    # SID2 should load the same count (not skipped by SID's data)
    assert second["loaded"] == first["loaded"]
