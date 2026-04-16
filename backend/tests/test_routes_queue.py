import sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DB_PATH": str(tmp_path / "test.db")})
    with app.test_client() as c:
        yield c


def _create_note(client, text="BP: 120/80. HR: 72."):
    """Helper: create a note via POST /api/notes and return the note_id."""
    resp = client.post("/api/notes", json={"text": text})
    assert resp.status_code == 201
    return resp.get_json()["note_id"]


def _validate_note(client, note_id):
    """Helper: submit a validation for a note so it leaves the queue."""
    resp = client.post(
        "/api/validate",
        json={
            "note_id": note_id,
            "validated_json": {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}},
            "status": "accepted",
            "review_duration_ms": 100,
        },
    )
    return resp


def test_queue_empty_initially(client):
    resp = client.get("/api/queue")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["notes"] == []
    assert data["count"] == 0


def test_queue_returns_pending_notes(client):
    note_id = _create_note(client)
    resp = client.get("/api/queue")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 1
    assert data["notes"][0]["id"] == note_id
    assert "filename" in data["notes"][0]
    assert "source" in data["notes"][0]
    assert "created_at" in data["notes"][0]


def test_queue_returns_multiple_notes_in_order(client):
    id1 = _create_note(client, "BP: 110/70.")
    id2 = _create_note(client, "HR: 88.")
    resp = client.get("/api/queue")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 2
    # Should come back in ASC order (id1 was created first)
    ids = [n["id"] for n in data["notes"]]
    assert ids == sorted(ids)
    assert id1 in ids
    assert id2 in ids


def test_queue_excludes_validated_notes(client):
    id1 = _create_note(client, "BP: 120/80.")
    id2 = _create_note(client, "HR: 60.")
    # Validate id1 — it should leave the queue
    vresp = _validate_note(client, id1)
    assert vresp.status_code in (200, 201)

    resp = client.get("/api/queue")
    data = resp.get_json()
    ids = [n["id"] for n in data["notes"]]
    assert id1 not in ids
    assert id2 in ids
    assert data["count"] == 1


def test_queue_note_fields(client):
    _create_note(client, "BP: 130/85.")
    resp = client.get("/api/queue")
    note = resp.get_json()["notes"][0]
    assert set(note.keys()) >= {"id", "filename", "source", "created_at"}
