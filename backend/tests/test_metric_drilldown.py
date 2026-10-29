"""Metrics must drill to *current* workspace-bound evidence, never stale rows."""
import pytest

from app import create_app
from models import Note, OperationalIssue
from utils.db import get_session


@pytest.fixture
def client(tmp_path):
    app = create_app({
        "TESTING": True,
        "DATABASE_URL": f"sqlite:///{tmp_path / 'drilldowns.db'}",
    })
    return app.test_client()


def _headers(sid):
    return {"X-Session-ID": sid}


def _note(client, sid):
    response = client.post("/api/notes", headers=_headers(sid), json={
        "text": "Synthetic document. BP: 120/80. HR: 72.",
    })
    assert response.status_code == 201, response.json
    return response.json


def _complete(client, sid, created, changed=False):
    note_id = created["note_id"]
    state = client.get(f"/api/notes/{note_id}", headers=_headers(sid)).json
    source = client.get(f"/api/notes/{note_id}/source", headers=_headers(sid)).json
    decisions = {}
    extracted = state["extracted_json"]
    for category in ("vitals", "instructions", "metadata"):
        for field, value in (extracted.get(category) or {}).items():
            if value is not None:
                decisions[f"{category}.{field}"] = {"decision": "accept"}
    for index, item in enumerate(extracted.get("medications") or []):
        med_id = item.get("id") or item.get("source_occurrence_id") or f"med_{index}"
        decisions[f"med.{med_id}"] = {"decision": "accept"}
    if changed:
        assert "blood_pressure" in extracted["vitals"]
        decisions["vitals.blood_pressure"] = {"decision": "edit", "value": "130/85"}
    payload = {
        "note_id": note_id,
        "source_revision_id": created["revision_id"],
        "extraction_id": created["extraction_id"],
        "source_hash": source["sha256"],
        "expected_lock_version": 0,
        "item_decisions": decisions,
        "category_acknowledgments": {k: True for k in ("metadata", "vitals", "instructions", "medications")},
    }
    res = client.post(
        f'/api/extractions/{created["extraction_id"]}/reviews',
        headers=_headers(sid), json=payload,
    )
    assert res.status_code == 201, res.json
    return res.json


def test_drilldown_scopes_exact_current_review_and_field_correction(client):
    a, b = "drilldown-user-a", "drilldown-user-b"
    corrected = _note(client, a)
    _complete(client, a, corrected, changed=True)
    unchanged = _note(client, a)
    _complete(client, a, unchanged, changed=False)
    external = _note(client, b)
    _complete(client, b, external, changed=True)

    res = client.get(
        "/api/metrics/drilldown?kind=corrections&field=vitals.blood_pressure",
        headers=_headers(a),
    )
    assert res.status_code == 200
    assert [r["note_id"] for r in res.json["rows"]] == [corrected["note_id"]]
    assert res.json["current_binding_only"] is True
    assert res.json["contains_raw_source"] is False
    assert "raw_text" not in res.json["rows"][0]

    category = client.get(
        "/api/metrics/drilldown?kind=corrections&category=vitals",
        headers=_headers(a),
    )
    assert [r["note_id"] for r in category.json["rows"]] == [corrected["note_id"]]

    status = client.get(
        "/api/metrics/drilldown?kind=status&status=reviewed_unchanged",
        headers=_headers(a),
    )
    assert [r["note_id"] for r in status.json["rows"]] == [unchanged["note_id"]]


def test_current_issue_only_and_stale_revision_exclusion(client):
    sid, outsider = "issue-drilldown-a", "issue-drilldown-b"
    own = _note(client, sid)
    foreign = _note(client, outsider)
    with get_session(client.application.config["ENGINE"]) as db:
        for created, workspace in ((own, sid), (foreign, outsider)):
            db.add(OperationalIssue(
                workspace_id=workspace,
                note_id=created["note_id"],
                source_revision_id=created["revision_id"],
                extraction_id=created["extraction_id"],
                issue_code="SYNTHETIC_CANARY",
                severity="warning",
                category="clinical_canary",
                status="open",
                safe_explanation="Synthetic source check requires inspection.",
            ))
        db.commit()

    url = "/api/metrics/drilldown?kind=issues&severity=warning&state=open"
    current = client.get(url, headers=_headers(sid))
    assert current.status_code == 200
    assert len(current.json["rows"]) == 1
    assert current.json["rows"][0]["note_id"] == own["note_id"]
    assert current.json["rows"][0]["issue_id"]
    assert client.get(url, headers=_headers(outsider)).json["rows"][0]["note_id"] == foreign["note_id"]

    updated = client.post(
        f'/api/notes/{own["note_id"]}/revisions',
        headers=_headers(sid),
        json={
            "raw_text": "Synthetic replacement. BP 125/80.",
            "expected_source_revision_id": own["revision_id"],
            "expected_lock_version": 0,
        },
    )
    assert updated.status_code == 201, updated.json
    assert client.get(url, headers=_headers(sid)).json["rows"] == []


@pytest.mark.parametrize("q", [
    "kind=invalid",
    "kind=issues&severity=nonexistent",
    "kind=issues&state=invalid",
    "kind=corrections",
    "kind=corrections&category=bad",
    "kind=corrections&field=meta.unsafe",
    "kind=corrections&field=vitals.blood_pressure&category=metadata",
    "kind=status&status=outdated",
])
def test_invalid_drilldown_filters_fail_closed(client, q):
    res = client.get("/api/metrics/drilldown?" + q, headers=_headers("safe-synthetic"))
    assert res.status_code == 422
    assert res.json["code"].startswith(("INVALID", "MISSING"))


def test_medication_provenance_metadata_does_not_count_as_a_correction():
    from routes.metric_drilldown import _changed_paths
    extracted = {
        "vitals": {}, "metadata": {}, "instructions": {},
        "medications": [{
            "name": "Metformin", "dose": "500 mg",
            "source_occurrence_id": "med_0", "span": [0, 10],
        }],
    }
    reviewed = {
        "vitals": {}, "metadata": {}, "instructions": {},
        "medications": [{
            "id": "med_0", "source_occurrence_id": "med_0",
            "name": "Metformin", "dose": "500 mg",
        }],
    }
    assert "medications" not in _changed_paths(extracted, reviewed)
    reviewed["medications"][0]["dose"] = "5000 mg"
    assert "medications" in _changed_paths(extracted, reviewed)


def test_metric_drilldown_requires_workspace_session(client):
    res = client.get("/api/metrics/drilldown?kind=issues")
    assert res.status_code in (400, 401, 403)
