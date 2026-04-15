import pytest
from app import create_app

@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DB_PATH": str(tmp_path / "test.db")})
    with app.test_client() as c:
        yield c

def test_health_check(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"
