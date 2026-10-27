import sys, os, json, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import create_app
from utils.corrections import compute_correction_count

SID = "test-session-abc"
SID2 = "other-session-xyz"

@pytest.fixture
def client(tmp_path):
    app = create_app({
        "TESTING": True,
        "DATABASE_URL": "sqlite:///" + str(tmp_path / "test.db"),
        "EVAL_RESULTS_PATH": str(tmp_path / "nonexistent_results.json"),
    })
    with app.test_client() as c:
        yield c

@pytest.fixture
def note_id(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80. HR: 72."}, headers={"X-Session-ID": SID})
    return resp.get_json()["note_id"]


def _make_payload(client, nid, headers, decisions=None, event_kind="review_completed"):
    source = client.get(f"/api/notes/{nid}/source", headers=headers).json
    note = client.get(f"/api/notes/{nid}", headers=headers).json
    ext = note["extracted_json"]
    item_decisions = {}
    for cat in ["vitals", "metadata", "instructions"]:
        for k, v in ext.get(cat, {}).items():
            if isinstance(v, dict) and "value" in v:
                item_decisions[f"{cat}.{k}"] = {"decision": "accept"}
    for med in ext.get("medications", []):
        m_id = med.get("id") or med.get("source_occurrence_id") or med.get("name", {}).get("value")
        for field in ["name", "dose", "route", "frequency", "duration", "prn"]:
            if field in med and isinstance(med[field], dict) and "value" in med[field]:
                item_decisions[f"medications.{m_id}.{field}"] = {"decision": "accept"}
    if decisions:
        item_decisions.update(decisions)
    return {
        "note_id": nid,
        "source_revision_id": note["current_source_revision_id"],
        "extraction_id": note["current_extraction_id"],
        "source_hash": source["sha256"],
        "expected_lock_version": note["lock_version"],
        "event_kind": event_kind,
        "item_decisions": item_decisions,
        "category_acknowledgments": {
            "vitals": True,
            "metadata": True,
            "medications": True,
            "instructions": True,
        },
    }


def test_validate_missing_session_returns_400(client):
    resp = client.post("/api/validate", json={
        "note_id": 1,
        "validated_json": {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}},
        "status": "accepted",
    })
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_SESSION_ID"


def test_validate_legacy_payload_returns_422(client, note_id):
    resp = client.post("/api/validate", json={
        "note_id": note_id,
        "validated_json": {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}},
        "status": "accepted",
    }, headers={"X-Session-ID": SID})
    assert resp.status_code == 422
    assert resp.get_json()["code"] == "REVIEW_BINDING_REQUIRED"


def test_validate_missing_binding_fields_returns_422(client, note_id):
    resp = client.post("/api/validate", json={"note_id": note_id}, headers={"X-Session-ID": SID})
    assert resp.status_code == 422
    assert resp.get_json()["code"] == "REVIEW_BINDING_REQUIRED"


def test_validate_returns_201_on_bound_review(client, note_id):
    payload = _make_payload(client, note_id, headers={"X-Session-ID": SID})
    resp = client.post("/api/validate", json=payload, headers={"X-Session-ID": SID})
    assert resp.status_code == 201
    assert resp.get_json()["event_kind"] == "review_completed"
    assert resp.get_json()["derived_outcome"] == "reviewed_unchanged"


def test_validate_correction_creates_new_event(client, note_id):
    payload = _make_payload(client, note_id, headers={"X-Session-ID": SID})
    resp = client.post("/api/validate", json=payload, headers={"X-Session-ID": SID})
    assert resp.status_code == 201
    first_event_id = resp.get_json()["event_id"]

    # Second review modifies blood_pressure
    decisions = {
        "vitals.blood_pressure": {
            "decision": "edit",
            "value": "130/85",
        }
    }
    payload2 = _make_payload(client, note_id, headers={"X-Session-ID": SID}, decisions=decisions)
    payload2["expected_head_event_id"] = first_event_id
    payload2["expected_lock_version"] = 1
    resp2 = client.post("/api/validate", json=payload2, headers={"X-Session-ID": SID})
    assert resp2.status_code == 201
    assert resp2.get_json()["derived_outcome"] == "reviewed_corrected"

    detail = client.get(f"/api/notes/{note_id}", headers={"X-Session-ID": SID}).get_json()
    assert detail["review_head"]["derived_outcome"] == "reviewed_corrected"


def test_validate_other_session_note_returns_error(client):
    note_resp = client.post("/api/notes", json={"text": "BP: 120/80."}, headers={"X-Session-ID": SID})
    nid = note_resp.get_json()["note_id"]
    payload = _make_payload(client, nid, headers={"X-Session-ID": SID})
    resp = client.post("/api/validate", json=payload, headers={"X-Session-ID": SID2})
    assert resp.status_code in (400, 403)


def test_validate_nonexistent_extraction_returns_400(client):
    payload = {
        "note_id": 9999,
        "source_revision_id": "rev-9999",
        "extraction_id": "nonexistent-ext",
        "source_hash": "dummyhash",
        "expected_lock_version": 0,
        "event_kind": "review_completed",
        "item_decisions": {},
        "category_acknowledgments": {
            "vitals": True,
            "metadata": True,
            "medications": True,
            "instructions": True,
        },
    }
    resp = client.post("/api/validate", json=payload, headers={"X-Session-ID": SID})
    assert resp.status_code == 400


def test_correction_count_computed():
    ext = {"vitals": {"blood_pressure": {"value": "120/80"}}, "medications": [], "instructions": {}, "metadata": {}}
    val = {"vitals": {"blood_pressure": {"value": "130/85"}}, "medications": [], "instructions": {}, "metadata": {}}
    assert compute_correction_count(ext, val) == 1


def test_metrics_null_eval_when_no_results_file(client):
    resp = client.get("/api/metrics", headers={"X-Session-ID": SID})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "eval" in data
    assert data["eval"] is None
    assert "db_stats" in data
