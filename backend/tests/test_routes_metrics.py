import sys, os, json, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import create_app

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


def _explicit_accepts(extracted):
    result = {}
    for category in ("vitals", "instructions", "metadata"):
        for key, value in (extracted.get(category) or {}).items():
            if value is not None:
                result[f"{category}.{key}"] = {"decision": "accept"}
    for idx, med in enumerate(extracted.get("medications") or []):
        med_id = med.get("id") or med.get("source_occurrence_id") or f"med_{idx}"
        result[f"med.{med_id}"] = {"decision": "accept"}
    return result


def test_metrics_missing_session_returns_400(client):
    resp = client.get("/api/metrics")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_SESSION_ID"


def test_metrics_has_correction_rates_key(client):
    resp = client.get("/api/metrics", headers={"X-Session-ID": SID})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "correction_rates" in data["db_stats"]


def test_metrics_correction_rates_shape_when_empty(client):
    resp = client.get("/api/metrics", headers={"X-Session-ID": SID})
    rates = resp.get_json()["db_stats"]["correction_rates"]
    assert "by_category" in rates
    assert "by_field" in rates
    for cat in ("vitals", "medications", "instructions", "metadata"):
        assert cat in rates["by_category"]


def test_metrics_correction_rates_after_validation(client):
    note_resp = client.post("/api/notes", json={"text": "BP: 120/80. HR: 72."}, headers={"X-Session-ID": SID})
    note_data = note_resp.get_json()
    note_id = note_data["note_id"]
    rev_id = note_data["revision_id"]
    ext_id = note_data["extraction_id"]
    source = client.get(f"/api/notes/{note_id}/source", headers={"X-Session-ID": SID}).json

    res = client.post(f"/api/extractions/{ext_id}/reviews", json={
        "note_id": note_id,
        "source_revision_id": rev_id,
        "extraction_id": ext_id,
        "source_hash": source["sha256"],
        "expected_lock_version": 0,
        "event_kind": "review_completed",
        "item_decisions": {
            **_explicit_accepts(note_data["extracted_json"]),
            "vitals.blood_pressure": {"decision": "edit", "value": "130/85"},
        },
        "category_acknowledgments": {
            "metadata": True, "vitals": True, "medications": True, "instructions": True,
        },
    }, headers={"X-Session-ID": SID})
    assert res.status_code == 201

    resp = client.get("/api/metrics", headers={"X-Session-ID": SID})
    rates = resp.get_json()["db_stats"]["correction_rates"]
    assert "vitals.blood_pressure" in rates["by_field"]
    field_stat = rates["by_field"]["vitals.blood_pressure"]
    assert field_stat["reviewed"] >= 1
    assert field_stat["corrected"] >= 1
    cat_stat = rates["by_category"]["vitals"]
    assert cat_stat["reviewed"] >= 1
    assert cat_stat["rate"] > 0


def test_metrics_correction_rate_zero_when_no_corrections(client):
    note_resp = client.post("/api/notes", json={"text": "BP: 120/80."}, headers={"X-Session-ID": SID})
    note_data = note_resp.get_json()
    note_id = note_data["note_id"]
    rev_id = note_data["revision_id"]
    ext_id = note_data["extraction_id"]
    source = client.get(f"/api/notes/{note_id}/source", headers={"X-Session-ID": SID}).json

    res = client.post(f"/api/extractions/{ext_id}/reviews", json={
        "note_id": note_id,
        "source_revision_id": rev_id,
        "extraction_id": ext_id,
        "source_hash": source["sha256"],
        "expected_lock_version": 0,
        "event_kind": "review_completed",
        "item_decisions": {
            **_explicit_accepts(note_data["extracted_json"]),
            "vitals.blood_pressure": {"decision": "accept"},
        },
        "category_acknowledgments": {
            "metadata": True, "vitals": True, "medications": True, "instructions": True,
        },
    }, headers={"X-Session-ID": SID})
    assert res.status_code == 201

    resp = client.get("/api/metrics", headers={"X-Session-ID": SID})
    rates = resp.get_json()["db_stats"]["correction_rates"]
    for cat in ("vitals", "medications", "instructions", "metadata"):
        assert rates["by_category"][cat]["corrected"] == 0


def test_metrics_isolates_by_session(client):
    # SID2 creates and validates a note with corrections; SID should see no validations
    note_resp = client.post("/api/notes", json={"text": "BP: 120/80."}, headers={"X-Session-ID": SID2})
    note_data = note_resp.get_json()
    note_id = note_data["note_id"]
    rev_id = note_data["revision_id"]
    ext_id = note_data["extraction_id"]
    source = client.get(f"/api/notes/{note_id}/source", headers={"X-Session-ID": SID2}).json

    client.post(f"/api/extractions/{ext_id}/reviews", json={
        "note_id": note_id,
        "source_revision_id": rev_id,
        "extraction_id": ext_id,
        "source_hash": source["sha256"],
        "expected_lock_version": 0,
        "event_kind": "review_completed",
        "item_decisions": {
            **_explicit_accepts(note_data["extracted_json"]),
            "vitals.blood_pressure": {"decision": "edit", "value": "130/85"},
        },
        "category_acknowledgments": {
            "metadata": True, "vitals": True, "medications": True, "instructions": True,
        },
    }, headers={"X-Session-ID": SID2})

    resp = client.get("/api/metrics", headers={"X-Session-ID": SID})
    db_stats = resp.get_json()["db_stats"]
    assert db_stats["by_status"] == []
    for cat in ("vitals", "medications", "instructions", "metadata"):
        assert db_stats["correction_rates"]["by_category"][cat]["reviewed"] == 0
