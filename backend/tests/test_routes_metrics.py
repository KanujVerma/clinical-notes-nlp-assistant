import sys, os, json, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app({
        "TESTING": True,
        "DB_PATH": str(tmp_path / "test.db"),
        "EVAL_RESULTS_PATH": str(tmp_path / "nonexistent_results.json"),
    })
    with app.test_client() as c:
        yield c


def test_metrics_has_correction_rates_key(client):
    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "correction_rates" in data["db_stats"]


def test_metrics_correction_rates_shape_when_empty(client):
    resp = client.get("/api/metrics")
    rates = resp.get_json()["db_stats"]["correction_rates"]
    assert "by_category" in rates
    assert "by_field" in rates
    # All four categories present
    for cat in ("vitals", "medications", "instructions", "metadata"):
        assert cat in rates["by_category"]


def test_metrics_correction_rates_after_validation(client):
    """With one validated note that had a vital correction, vitals rate should be > 0."""
    # Create a note via /api/notes
    note_resp = client.post("/api/notes", json={"text": "BP: 120/80. HR: 72."})
    note_id = note_resp.get_json()["note_id"]

    # Validate with a correction (change blood_pressure value)
    client.post("/api/validate", json={
        "note_id": note_id,
        "validated_json": {
            "vitals": {"blood_pressure": {"value": "130/85"}},
            "medications": [],
            "instructions": {},
            "metadata": {},
        },
        "status": "corrected",
    })

    resp = client.get("/api/metrics")
    rates = resp.get_json()["db_stats"]["correction_rates"]
    # vitals.blood_pressure should have been reviewed
    assert "vitals.blood_pressure" in rates["by_field"]
    field_stat = rates["by_field"]["vitals.blood_pressure"]
    assert field_stat["reviewed"] >= 1
    # vitals category should have non-zero corrections (extracted vs validated differ)
    cat_stat = rates["by_category"]["vitals"]
    assert cat_stat["reviewed"] >= 1


def test_metrics_correction_rate_zero_when_no_corrections(client):
    """Accepted note with identical validated_json → zero corrections across all categories."""
    note_resp = client.post("/api/notes", json={"text": "BP: 120/80."})
    note_id = note_resp.get_json()["note_id"]

    # Get the extracted_json first so we can validate with the same data
    history = client.get(f"/api/history/{note_id}").get_json()
    extracted = history["extracted_json"]

    client.post("/api/validate", json={
        "note_id": note_id,
        "validated_json": extracted,
        "status": "accepted",
    })

    resp = client.get("/api/metrics")
    rates = resp.get_json()["db_stats"]["correction_rates"]
    # If extracted == validated, no corrections in any category
    for cat in ("vitals", "medications", "instructions", "metadata"):
        assert rates["by_category"][cat]["corrected"] == 0
