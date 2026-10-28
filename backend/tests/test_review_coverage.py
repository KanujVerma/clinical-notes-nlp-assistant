"""Strict review-decision and source identity regression tests.

A passing schema validator is not sufficient: these tests exercise the pure
authoritative snapshot derived from the bound extraction and human decisions.
"""
import pytest
from app import create_app
from services.review_service import (
    derive_reviewed_snapshot,
    IncompleteReviewError,
    InvalidReviewPayloadError,
)


@pytest.fixture
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "DATABASE_URL": f"sqlite:///{tmp_path / 'review_cov_test.db'}",
    })


@pytest.fixture
def client(app):
    return app.test_client()


def _fixture():
    return {
        "pipeline_version": "0.1.0",
        "vitals": {"heart_rate": {"value": "72 bpm"}},
        "metadata": {},
        "instructions": {},
        "medications": [
            {"name": "Metformin", "dose": "500 mg", "frequency": "BID"},
            {"name": "Metformin", "dose": "1000 mg", "frequency": "nightly"},
        ],
    }


def test_missing_vital_decision_blocks_completion():
    ext = _fixture()
    with pytest.raises(IncompleteReviewError, match="vitals.heart_rate"):
        derive_reviewed_snapshot(
            ext, {"med.med_0": {"decision": "accept"},
                  "med.med_1": {"decision": "accept"}},
            {}, True, "Synthetic note",
        )


def test_missing_medication_child_decision_blocks_completion():
    ext = _fixture()
    with pytest.raises(IncompleteReviewError, match="med_0"):
        derive_reviewed_snapshot(
            ext, {"vitals.heart_rate": {"decision": "accept"},
                  "med.med_0.name": {"decision": "accept"},
                  "med.med_1": {"decision": "accept"}},
            {}, True, "Synthetic note",
        )


def test_unknown_key_or_implicit_accept_is_rejected():
    ext = {"vitals": {}, "metadata": {}, "instructions": {}, "medications": []}
    for bad in ({"unknown_field": {"decision": "accept"}},
                {"vitals.heart_rate": {"action": "accept"}}):
        with pytest.raises(InvalidReviewPayloadError):
            derive_reviewed_snapshot(ext, bad, {}, True, "Synthetic text")


def test_same_name_wrong_dose_is_not_accepted_from_client_snapshot():
    ext = {"vitals": {}, "metadata": {}, "instructions": {},
           "medications": [{"name": "Metformin", "dose": "500 mg"}]}
    client = {"vitals": {}, "metadata": {}, "instructions": {},
              "medications": [{"id": "med_0", "name": "Metformin", "dose": "5000 mg"}]}
    with pytest.raises(InvalidReviewPayloadError, match="dose"):
        derive_reviewed_snapshot(
            ext, {"med.med_0": {"decision": "accept"}}, {},
            True, "Metformin 500 mg", client_snapshot=client,
        )


def test_same_name_occurrences_preserve_stable_separate_decisions():
    ext = _fixture()
    decisions = {
        "vitals.heart_rate": {"decision": "accept"},
        "med.med_0": {"decision": "accept"},
        "med.med_1.name": {"decision": "accept"},
        "med.med_1.dose": {"decision": "edit", "value": "750 mg"},
        "med.med_1.frequency": {"decision": "accept"},
    }
    out, changed = derive_reviewed_snapshot(ext, decisions, {}, True, "Synthetic note")
    assert changed
    assert [m["id"] for m in out["medications"]] == ["med_0", "med_1"]
    assert [m["dose"] for m in out["medications"]] == ["500 mg", "750 mg"]


def test_child_frequency_removal_preserves_medication():
    ext = _fixture()
    decisions = {
        "vitals.heart_rate": {"decision": "accept"},
        "med.med_0.name": {"decision": "accept"},
        "med.med_0.dose": {"decision": "accept"},
        "med.med_0.frequency": {"decision": "remove"},
        "med.med_1": {"decision": "accept"},
    }
    out, changed = derive_reviewed_snapshot(ext, decisions, {}, True, "Synthetic note")
    assert changed
    assert len(out["medications"]) == 2
    assert out["medications"][0]["name"] == "Metformin"
    assert "frequency" not in out["medications"][0]


def test_new_medication_child_fields_form_one_occurrence():
    ext = {"vitals": {}, "metadata": {}, "instructions": {}, "medications": []}
    decisions = {
        "med.med_add_001.name": {
            "decision": "add", "value": "Drug A",
            "no_direct_span_reason": "Synthetic reviewer addition",
        },
        "med.med_add_001.dose": {
            "decision": "add", "value": "5 mg",
            "no_direct_span_reason": "Synthetic reviewer addition",
        },
        "med.med_add_001.route": {
            "decision": "add", "value": "PO",
            "no_direct_span_reason": "Synthetic reviewer addition",
        },
    }
    out, changed = derive_reviewed_snapshot(ext, decisions, {}, True, "Synthetic source")
    assert changed
    assert len(out["medications"]) == 1
    assert out["medications"][0]["id"] == "med_add_001"
    assert out["medications"][0]["name"] == "Drug A"
    assert out["medications"][0]["dose"] == "5 mg"
    assert out["medications"][0]["route"] == "PO"


def test_source_evidence_for_added_fields_requires_exact_bound_quote():
    ext = {"vitals": {}, "metadata": {}, "instructions": {}, "medications": []}
    with pytest.raises(InvalidReviewPayloadError):
        derive_reviewed_snapshot(
            ext, {
                "med.med_add_002.name": {
                    "decision": "add", "value": "Drug B",
                    "evidence": {"start": 0, "end": 6, "raw_quote": "DRUG B"},
                }
            }, {}, True, "Drug B text",
        )


def test_review_mutation_records_issue_disposition_without_unbound_local(client):
    from models import OperationalIssue, IssueEvent
    headers = {"X-Session-ID": "test-issue-disp-sess"}
    create_res = client.post(
        "/api/notes",
        headers=headers,
        json={"text": "BP 120/80 mmHg. Lisinopril 10 mg PO daily."},
    )
    assert create_res.status_code == 201
    note_id = create_res.json["note_id"]
    ext_id = create_res.json["extraction_id"]

    source_res = client.get(f"/api/notes/{note_id}/source", headers=headers)
    assert source_res.status_code == 200
    source = source_res.json
    rev_id = source["revision_id"]

    # Create a non-critical operational issue
    from utils.db import get_session
    with get_session(client.application.config["ENGINE"]) as session:
        issue = OperationalIssue(
            workspace_id="test-issue-disp-sess",
            note_id=note_id,
            extraction_id=ext_id,
            source_revision_id=rev_id,
            issue_code="POTENTIAL_WARNING",
            category="clinical_contradiction",
            severity="warning",
            safe_explanation="Synthetic test warning",
        )
        session.add(issue)
        session.commit()
        issue_id = issue.id

    decisions = {
        "vitals.blood_pressure": {"decision": "accept"},
    }
    for idx, med in enumerate(create_res.json.get("extracted_json", {}).get("medications", [])):
        med_id = med.get("id") or med.get("source_occurrence_id") or f"med_{idx}"
        decisions[f"med.{med_id}"] = {"decision": "accept"}

    payload = {
        "schema_version": "2.0.0",
        "note_id": note_id,
        "source_revision_id": rev_id,
        "source_hash": source["sha256"],
        "extraction_id": ext_id,
        "expected_head_event_id": None,
        "expected_lock_version": 0,
        "event_kind": "review_completed",
        "idempotency_key": "test-disp-idem-1",
        "category_acknowledgments": {
            "vitals": True,
            "medications": True,
            "instructions": True,
            "metadata": True,
        },
        "item_decisions": decisions,
        "issue_dispositions": {
            issue_id: {"disposition": "acknowledged", "reason": "Reviewer accepted warning"}
        },
    }

    res = client.post(f"/api/extractions/{ext_id}/reviews", headers=headers, json=payload)
    assert res.status_code == 201, res.json
    assert "event_id" in res.json

    with get_session(client.application.config["ENGINE"]) as session:
        iss = session.query(OperationalIssue).filter(OperationalIssue.id == issue_id).first()
        assert iss.status == "acknowledged"
        ev = session.query(IssueEvent).filter(IssueEvent.issue_id == issue_id).first()
        assert ev is not None
        assert ev.action == "acknowledged"
        assert ev.reason == "Reviewer accepted warning"
