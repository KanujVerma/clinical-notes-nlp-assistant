import json
import hashlib
from typing import Dict, Any, Optional, Tuple
from sqlalchemy import update, and_, or_
from sqlalchemy.orm import Session
from models import Note, NoteRevision, Extraction, ReviewEvent, OperationalIssue, IssueEvent
from schemas.review import ReviewMutationRequest
from validation.checker import check_extraction


class StaleReviewError(Exception):
    """Raised when lock_version or review_head_event_id does not match."""
    pass


class IdempotencyConflictError(Exception):
    """Raised when an idempotency key is reused with a different request body."""
    pass


class IncompleteReviewError(Exception):
    """Raised when required categories are not acknowledged or items have no decision."""
    pass


class BlockedReviewError(Exception):
    """Raised when critical blocker issues remain open."""
    pass


class InvalidReviewPayloadError(Exception):
    """Raised when client review payload contains invalid actions, malformed values, unsupported evidence, or invented items."""
    pass


def _get_decision_str(d: Any) -> str:
    if isinstance(d, dict):
        # A JSON object lacking an explicit action must never default to
        # acceptance, even when it contains an unrelated "action" key.
        return str(d.get("decision", "")).strip().lower()
    if hasattr(d, "decision"):
        return str(getattr(d, "decision", "accept")).strip().lower()
    if isinstance(d, str):
        return d.strip().lower()
    return ""


def _get_decision_val(d: Any) -> Any:
    if isinstance(d, dict):
        return d.get("value")
    if hasattr(d, "value"):
        return getattr(d, "value")
    return None


def _validate_decision_coverage(extracted_data: Dict[str, Any], decisions: Dict[str, Any], completing: bool) -> None:
    """Reject undocumented decisions and enforce explicit review of all present fields.

    Medication occurrence identities are immutable within their bound
    extraction. Parent-level 'accept' may explicitly accept the whole record;
    an edit/remove/add on a child must be separately specified.
    """
    allowed = set()
    required = []

    def scalar(category: str, aliases: tuple[str, ...]) -> None:
        items = extracted_data.get(category) or {}
        if not isinstance(items, dict):
            raise InvalidReviewPayloadError(f"Invalid {category} extraction structure")
        for name, value in items.items():
            if value is None:
                continue
            keys = [f"{p}.{name}" for p in aliases]
            allowed.update(keys)
            # Do not accept bare ambiguous field-name aliases from the client.
            required.append((f"{category}.{name}", keys, []))

    scalar("vitals", ("vitals",))
    scalar("instructions", ("instructions", "instr"))
    scalar("metadata", ("metadata", "meta"))

    meds = extracted_data.get("medications") or []
    if not isinstance(meds, list):
        raise InvalidReviewPayloadError("Invalid medication extraction structure")

    seen_med_ids = set()
    for idx, med in enumerate(meds):
        if not isinstance(med, dict):
            raise InvalidReviewPayloadError("Invalid medication occurrence")
        med_id = med.get("id") or med.get("source_occurrence_id") or f"med_{idx}"
        if med_id in seen_med_ids:
            raise InvalidReviewPayloadError("Duplicate medication occurrence identifier")
        seen_med_ids.add(med_id)
        parents = (str(med_id), f"med.{med_id}", f"medications.{med_id}",
                   f"med.{idx}", f"medications.{idx}")
        allowed.update(parents)
        parent_obj = next((decisions[p] for p in parents if p in decisions), None)
        nested = parent_obj.get("attribute_decisions") if isinstance(parent_obj, dict) else None
        if nested is not None:
            if not isinstance(nested, dict) or set(nested) - {
                "name", "dose", "route", "frequency", "duration", "qualifier",
                "prn", "action", "status", "temporal_status"
            }:
                raise InvalidReviewPayloadError("Unknown medication child attribute")
            for child_attr, val in nested.items():
                child_action = _get_decision_str(val)
                if child_action not in ("accept", "edit", "remove", "pending"):
                    raise InvalidReviewPayloadError("Invalid medication child decision")
                if child_action == "edit":
                    child_val = _get_decision_val(val)
                    if not isinstance(child_val, str) or not child_val.strip() or len(child_val) > 4096:
                        raise InvalidReviewPayloadError(f"Edit '{med_id}.{child_attr}' requires a nonempty bounded string value")
        for attr, val in med.items():
            if attr not in ("name", "dose", "route", "frequency", "duration",
                            "qualifier", "prn", "action", "status", "temporal_status"):
                continue
            if val is None or val == "":
                continue
            keys = [
                f"{med_id}.{attr}", f"med.{med_id}.{attr}",
                f"medications.{med_id}.{attr}", f"med.{idx}.{attr}",
                f"medications.{idx}.{attr}",
            ]
            allowed.update(keys)
            if completing:
                child = next((decisions[k] for k in keys if k in decisions), None)
                if child is None and isinstance(nested, dict):
                    child = nested.get(attr)
                parent_action = _get_decision_str(parent_obj) if parent_obj is not None else None
                if child is None and parent_action not in ("accept", "remove"):
                    raise IncompleteReviewError(f"Missing explicit decision for medication {med_id}.{attr}")
                if child is not None and _get_decision_str(child) == "pending":
                    raise IncompleteReviewError(f"Pending decision for medication {med_id}.{attr}")
        if completing and not any(p in decisions for p in parents):
            # A child-level decision for each present attr is sufficient.
            if not any(k.startswith(f"{med_id}.") or k.startswith(f"med.{med_id}.") or k.startswith(f"medications.{med_id}.")
                       or k.startswith(f"med.{idx}.") or k.startswith(f"medications.{idx}.") for k in decisions):
                raise IncompleteReviewError(f"Medication {med_id} has no review decision")

    for name, keys, _ in required:
        selected = next((decisions[key] for key in keys if key in decisions), None)
        if completing and (selected is None or _get_decision_str(selected) == "pending"):
            raise IncompleteReviewError(f"Missing or pending field decision: {name}")

    for key, decision in decisions.items():
        action = _get_decision_str(decision)
        if action == "edit":
            value = _get_decision_val(decision)
            if not isinstance(value, str) or not value.strip() or len(value) > 4096:
                raise InvalidReviewPayloadError(f"Edit '{key}' requires a nonempty bounded string value")
        if key in allowed:
            if action == "add":
                raise InvalidReviewPayloadError(f"Cannot add over an existing extraction field: {key}")
            if action not in ("accept", "edit", "remove", "pending"):
                raise InvalidReviewPayloadError(f"Invalid action for {key}")
        elif action != "add":
            raise InvalidReviewPayloadError(f"Unknown extraction field/decision key: {key}")
        elif not (key.startswith(("med.", "vitals.", "instr.", "instructions.",
                                  "meta.", "metadata."))):
            raise InvalidReviewPayloadError(f"Unknown addition category: {key}")


def _validate_client_snapshot(snapshot: Dict[str, Any], derived: Dict[str, Any]) -> None:
    """Prevent silent discrepancies, including same-name altered-dose claims."""
    if not isinstance(snapshot, dict):
        raise InvalidReviewPayloadError("Reviewed snapshot must be an object")
    for category in ("vitals", "instructions", "metadata"):
        supplied = snapshot.get(category) or {}
        expected = derived.get(category) or {}
        if not isinstance(supplied, dict) or set(supplied) != set(expected):
            raise InvalidReviewPayloadError(f"Client {category} snapshot differs from server decisions")
        for key in expected:
            left, right = supplied[key], expected[key]
            left_value = left.get("value") if isinstance(left, dict) else left
            right_value = right.get("value") if isinstance(right, dict) else right
            if left_value != right_value:
                raise InvalidReviewPayloadError(f"Unbacked reviewed value: {category}.{key}")

    supplied = snapshot.get("medications") or []
    expected = derived.get("medications") or []
    if not isinstance(supplied, list) or len(supplied) != len(expected):
        raise InvalidReviewPayloadError("Client medication instances differ from reviewed decisions")

    keys = ("name", "dose", "route", "frequency", "duration", "qualifier",
            "prn", "action", "status", "temporal_status")
    def identity(item: Dict[str, Any], index: int) -> str:
        return str(item.get("id") or item.get("source_occurrence_id") or f"med_{index}")

    known = {}
    for idx, item in enumerate(expected):
        if not isinstance(item, dict):
            raise InvalidReviewPayloadError("Invalid server medication")
        item_id = identity(item, idx)
        if item_id in known:
            raise InvalidReviewPayloadError("Duplicate medication identity in reviewed result")
        known[item_id] = item
    seen = set()
    for idx, item in enumerate(supplied):
        if not isinstance(item, dict):
            raise InvalidReviewPayloadError("Invalid client medication")
        item_id = identity(item, idx)
        if item_id not in known or item_id in seen:
            raise InvalidReviewPayloadError("Client medication identity is unbacked")
        seen.add(item_id)
        counterpart = known[item_id]
        for key in keys:
            if item.get(key) != counterpart.get(key):
                raise InvalidReviewPayloadError(f"Client medication {item_id}.{key} conflicts with decisions")


def derive_reviewed_snapshot(
    extracted_data: Dict[str, Any],
    item_decisions: Dict[str, Any],
    category_acknowledgments: Dict[str, bool],
    is_completing: bool,
    raw_text: str = "",
    client_snapshot: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], bool]:
    decisions = item_decisions or {}
    _validate_decision_coverage(extracted_data, decisions, is_completing)
    has_corrections = False
    valid_actions = {"accept", "edit", "remove", "add", "pending"}

    # 1. Validate decision actions
    for k, d in (item_decisions or {}).items():
        act = _get_decision_str(d)
        if act not in valid_actions:
            raise InvalidReviewPayloadError(f"Invalid decision action '{act}' for item '{k}'.")
        if is_completing and act == "pending":
            raise IncompleteReviewError(f"Item '{k}' has an uncompleted 'pending' decision.")

    # 2. Vitals
    reviewed_vitals: Dict[str, Any] = {}
    ext_vitals = extracted_data.get("vitals") or {}
    for field, field_data in ext_vitals.items():
        d = (
            (item_decisions or {}).get(f"vitals.{field}")
            or (item_decisions or {}).get(field)
        )
        if d:
            act = _get_decision_str(d)
            if act == "remove":
                has_corrections = True
            elif act == "edit":
                has_corrections = True
                val = _get_decision_val(d)
                entry = dict(field_data) if isinstance(field_data, dict) else {"value": field_data}
                entry["value"] = val
                entry["reviewed"] = True
                entry["source"] = "reviewer_edit"
                reviewed_vitals[field] = entry
            elif act == "accept":
                reviewed_vitals[field] = field_data
            elif act == "pending":
                if is_completing:
                    raise IncompleteReviewError(f"Field 'vitals.{field}' is pending.")
                reviewed_vitals[field] = field_data
        else:
            reviewed_vitals[field] = field_data

    # 3. Instructions
    reviewed_instructions: Dict[str, Any] = {}
    ext_instructions = extracted_data.get("instructions") or {}
    for field, field_data in ext_instructions.items():
        d = (
            (item_decisions or {}).get(f"instructions.{field}")
            or (item_decisions or {}).get(f"instr.{field}")
            or (item_decisions or {}).get(field)
        )
        if d:
            act = _get_decision_str(d)
            if act == "remove":
                has_corrections = True
            elif act == "edit":
                has_corrections = True
                val = _get_decision_val(d)
                entry = dict(field_data) if isinstance(field_data, dict) else {"value": field_data}
                entry["value"] = val
                entry["reviewed"] = True
                entry["source"] = "reviewer_edit"
                reviewed_instructions[field] = entry
            elif act == "accept":
                reviewed_instructions[field] = field_data
            elif act == "pending":
                if is_completing:
                    raise IncompleteReviewError(f"Field 'instructions.{field}' is pending.")
                reviewed_instructions[field] = field_data
        else:
            reviewed_instructions[field] = field_data

    # 4. Metadata
    reviewed_metadata: Dict[str, Any] = {}
    ext_metadata = extracted_data.get("metadata") or {}
    for field, field_data in ext_metadata.items():
        d = (
            (item_decisions or {}).get(f"metadata.{field}")
            or (item_decisions or {}).get(f"meta.{field}")
            or (item_decisions or {}).get(field)
        )
        if d:
            act = _get_decision_str(d)
            if act == "remove":
                has_corrections = True
            elif act == "edit":
                has_corrections = True
                val = _get_decision_val(d)
                entry = dict(field_data) if isinstance(field_data, dict) else {"value": field_data}
                entry["value"] = val
                entry["reviewed"] = True
                entry["source"] = "reviewer_edit"
                reviewed_metadata[field] = entry
            elif act == "accept":
                reviewed_metadata[field] = field_data
            elif act == "pending":
                if is_completing:
                    raise IncompleteReviewError(f"Field 'metadata.{field}' is pending.")
                reviewed_metadata[field] = field_data
        else:
            reviewed_metadata[field] = field_data

    # 5. Medications
    reviewed_meds: list = []
    ext_meds = extracted_data.get("medications") or []
    for idx, med in enumerate(ext_meds):
        med_id = med.get("id") or med.get("source_occurrence_id") or f"med_{idx}"
        med_dec = (
            (item_decisions or {}).get(med_id)
            or (item_decisions or {}).get(f"med.{med_id}")
            or (item_decisions or {}).get(f"medications.{med_id}")
            or (item_decisions or {}).get(f"med.{idx}")
            or (item_decisions or {}).get(f"medications.{idx}")
        )
        name_dec = (
            (item_decisions or {}).get(f"{med_id}.name")
            or (item_decisions or {}).get(f"med.{med_id}.name")
            or (item_decisions or {}).get(f"medications.{med_id}.name")
            or (item_decisions or {}).get(f"med.{idx}.name")
        )
        is_med_removed = False
        nested_name_dec = None
        if med_dec and isinstance(med_dec, dict) and med_dec.get("attribute_decisions"):
            nested_name_dec = med_dec["attribute_decisions"].get("name")
        elif med_dec and getattr(med_dec, "attribute_decisions", None):
            nested_name_dec = getattr(med_dec, "attribute_decisions", {}).get("name")

        if (
            (med_dec and _get_decision_str(med_dec) == "remove")
            or (name_dec and _get_decision_str(name_dec) == "remove")
            or (nested_name_dec and _get_decision_str(nested_name_dec) == "remove")
        ):
            is_med_removed = True
            has_corrections = True
        elif med_dec:
            act = _get_decision_str(med_dec)
            if act == "edit":
                has_corrections = True
            elif act == "pending" and is_completing:
                raise IncompleteReviewError(f"Medication '{med_id}' is pending.")

        if not is_med_removed:
            med_copy = dict(med)
            med_copy["id"] = med_id
            med_copy["source_occurrence_id"] = med_id

            attr_decs = {}
            if med_dec and isinstance(med_dec, dict) and med_dec.get("attribute_decisions"):
                attr_decs = med_dec["attribute_decisions"]
            elif med_dec and getattr(med_dec, "attribute_decisions", None):
                attr_decs = getattr(med_dec, "attribute_decisions")

            for attr in ("name", "dose", "route", "frequency", "duration", "qualifier", "prn", "action", "status", "temporal_status"):
                a_dec = attr_decs.get(attr)
                if not a_dec:
                    a_dec = (
                        (item_decisions or {}).get(f"{med_id}.{attr}")
                        or (item_decisions or {}).get(f"med.{med_id}.{attr}")
                        or (item_decisions or {}).get(f"medications.{med_id}.{attr}")
                        or (item_decisions or {}).get(f"med.{idx}.{attr}")
                        or (item_decisions or {}).get(f"medications.{idx}.{attr}")
                    )
                if a_dec:
                    a_act = _get_decision_str(a_dec)
                    if a_act == "remove":
                        if attr == "name":
                            is_med_removed = True
                            has_corrections = True
                            break
                        med_copy.pop(attr, None)
                        has_corrections = True
                    elif a_act == "edit":
                        med_copy[attr] = _get_decision_val(a_dec)
                        has_corrections = True
                    elif a_act == "pending" and is_completing:
                        raise IncompleteReviewError(f"Attribute '{med_id}.{attr}' is pending.")

            if not is_med_removed:
                reviewed_meds.append(med_copy)

    # 6. Additions. Multiple child operations for a single new medication
    # are ONE new occurrence, not one medication per attribute.
    added_meds: Dict[str, Dict[str, Any]] = {}
    for key, decision in (item_decisions or {}).items():
        if _get_decision_str(decision) != "add":
            continue
        has_corrections = True
        evidence = decision.get("evidence") if isinstance(decision, dict) else getattr(decision, "evidence", None)
        reason = (decision.get("no_direct_span_reason") or decision.get("reason")) if isinstance(decision, dict) else None
        valid_evidence = False
        if isinstance(evidence, dict):
            start, end = evidence.get("start"), evidence.get("end")
            quote = evidence.get("raw_quote")
            if (type(start) is int and type(end) is int
                    and 0 <= start < end <= len(raw_text)
                    and isinstance(quote, str) and raw_text[start:end] == quote):
                valid_evidence = True
        if not valid_evidence and not (isinstance(reason, str) and reason.strip()):
            raise InvalidReviewPayloadError(
                f"Added item '{key}' requires exact source evidence or a no-direct-span reason"
            )
        value = _get_decision_val(decision)
        if not isinstance(value, (str, dict)):
            raise InvalidReviewPayloadError(f"Added item '{key}' has invalid value")

        parts = key.split(".")
        if len(parts) >= 2 and parts[0] == "med":
            med_id = parts[1]
            if not med_id.startswith("med_add_"):
                raise InvalidReviewPayloadError("Added medication needs a new opaque occurrence ID")
            if len(parts) == 2 and isinstance(value, dict):
                item = added_meds.setdefault(med_id, {"id": med_id, "source_occurrence_id": med_id})
                for attr, attr_value in value.items():
                    if attr not in ("name", "dose", "route", "frequency", "duration",
                                    "qualifier", "action", "prn"):
                        raise InvalidReviewPayloadError("Unknown added medication attribute")
                    item[attr] = attr_value
            elif len(parts) == 3 and parts[2] in ("name", "dose", "route", "frequency",
                                                 "duration", "qualifier", "action", "prn"):
                item = added_meds.setdefault(med_id, {"id": med_id, "source_occurrence_id": med_id})
                item[parts[2]] = value
            else:
                raise InvalidReviewPayloadError("Malformed added medication field")
        elif len(parts) == 2 and parts[0] in ("vitals", "instr", "instructions", "meta", "metadata"):
            target = {"vitals": reviewed_vitals, "instr": reviewed_instructions,
                      "instructions": reviewed_instructions, "meta": reviewed_metadata,
                      "metadata": reviewed_metadata}[parts[0]]
            if parts[1] in target:
                raise InvalidReviewPayloadError("Added field collides with existing field")
            target[parts[1]] = {"value": value, "source": "reviewer_added"}
        else:
            raise InvalidReviewPayloadError("Unknown added field path")

    occupied = {str(m.get("id") or m.get("source_occurrence_id"))
                for m in reviewed_meds}
    for med_id, med in added_meds.items():
        if med_id in occupied:
            raise InvalidReviewPayloadError("Duplicate added medication identity")
        if not isinstance(med.get("name"), str) or not med["name"].strip():
            raise InvalidReviewPayloadError("Added medication requires a nonempty name")
        for name, value in med.items():
            if name in ("id", "source_occurrence_id"):
                continue
            if not isinstance(value, (str, bool)) or (isinstance(value, str) and not value.strip()):
                raise InvalidReviewPayloadError(f"Added medication has invalid {name}")
        reviewed_meds.append(med)
        occupied.add(med_id)

    derived_snapshot = {
        "pipeline_version": extracted_data.get("pipeline_version", "2.0.0"),
        "vitals": reviewed_vitals,
        "medications": reviewed_meds,
        "instructions": reviewed_instructions,
        "metadata": reviewed_metadata,
    }
    if client_snapshot is not None:
        _validate_client_snapshot(client_snapshot, derived_snapshot)
    return derived_snapshot, has_corrections


def canonical_hash(data: Dict[str, Any]) -> str:
    """Computes SHA-256 hash of a dictionary with sorted keys."""
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def process_review_mutation(
    session: Session,
    workspace_id: str,
    req: ReviewMutationRequest,
    raw_request_dict: Optional[Dict[str, Any]] = None,
) -> Tuple[ReviewEvent, bool]:
    """
    Executes atomic review write with optimistic concurrency and idempotency.
    Returns (ReviewEvent, is_replay).
    """
    valid_event_kinds = {"draft_saved", "review_completed", "review_reopened"}
    if req.event_kind not in valid_event_kinds:
        raise InvalidReviewPayloadError(
            f"Unsupported event_kind '{req.event_kind}'. Must be one of {valid_event_kinds}."
        )

    body_dict = raw_request_dict or req.model_dump()
    req_hash = canonical_hash(body_dict)

    # 1. Idempotency Check
    if req.idempotency_key:
        existing = (
            session.query(ReviewEvent)
            .filter(
                ReviewEvent.workspace_id == workspace_id,
                ReviewEvent.idempotency_key == req.idempotency_key,
            )
            .first()
        )
        if existing:
            if existing.request_hash == req_hash:
                # Exact identical replay
                return existing, True
            else:
                raise IdempotencyConflictError(
                    f"Idempotency key '{req.idempotency_key}' reused with conflicting request payload."
                )

    # 2. Fetch Note and verify workspace scope
    note = (
        session.query(Note)
        .filter(Note.id == req.note_id, Note.workspace_id == workspace_id)
        .first()
    )
    if not note:
        raise ValueError(f"Note {req.note_id} not found in workspace {workspace_id}")

    # 3. Verify Source Revision and Hash binding
    rev = (
        session.query(NoteRevision)
        .filter(
            NoteRevision.id == req.source_revision_id,
            NoteRevision.note_id == req.note_id,
        )
        .first()
    )
    if not rev:
        raise ValueError(f"Source revision {req.source_revision_id} does not belong to note {req.note_id}")

    if rev.sha256 != req.source_hash:
        raise ValueError(f"Source hash mismatch for revision {rev.id}")

    # 4. Verify Extraction binding
    ext = (
        session.query(Extraction)
        .filter(
            Extraction.public_id == req.extraction_id,
            Extraction.source_revision_id == rev.id,
        )
        .first()
    )
    if not ext:
        # Check by integer ID fallback
        ext = (
            session.query(Extraction)
            .filter(
                str(Extraction.id) == req.extraction_id,
                Extraction.note_id == req.note_id,
            )
            .first()
        )
    if not ext:
        raise ValueError(f"Extraction {req.extraction_id} not bound to revision {rev.id}")
    if ext.status != "completed":
        # Legacy extraction payloads may be useful for history but lack
        # independently verifiable source provenance. Re-extract first.
        raise StaleReviewError("Current extraction is not a verified completed run")

    # A historical source or extraction may be inspected, but must never be
    # completed as the current note. Verify this before checking dispositions.
    if (
        note.current_source_revision_id != rev.id
        or note.current_extraction_id != ext.public_id
        or ext.note_id != note.id
        or (ext.source_text_hash and ext.source_text_hash != rev.sha256)
        or note.lock_version != req.expected_lock_version
        or note.review_head_event_id != req.expected_head_event_id
    ):
        raise StaleReviewError("Source, extraction, or review head changed; refresh required.")

    # Critical integrity findings cannot be dismissed by review dispositions.
    # They require a corrected source, re-extraction, or blocked/unusable state.
    for issue_id in req.issue_dispositions:
        target_issue = (
            session.query(OperationalIssue)
            .filter(
                OperationalIssue.id == issue_id,
                OperationalIssue.workspace_id == workspace_id,
                OperationalIssue.note_id == note.id,
                OperationalIssue.source_revision_id == rev.id,
                OperationalIssue.extraction_id == ext.public_id,
            )
            .first()
        )
        if not target_issue:
            raise ValueError("Disposition references an issue outside this extraction.")
        if target_issue.severity == "critical_blocker":
            raise BlockedReviewError("Critical integrity issues cannot be dispositioned without remediation.")

    # 5. Review Completion Rules (only enforced when event_kind == 'review_completed')
    is_completing = (req.event_kind == "review_completed")

    if is_completing:
        # Rule A15: Completeness must be acknowledged for all categories
        categories = ["metadata", "vitals", "medications", "instructions"]
        missing_cats = [c for c in categories if not req.category_acknowledgments.get(c)]
        if missing_cats:
            raise IncompleteReviewError(
                f"Completeness must be explicitly acknowledged for all categories. Missing: {missing_cats}"
            )

        # Open critical issues always block completion, regardless of whether
        # the client submitted "resolved", "accepted_risk", or "dismissed".
        open_criticals = (
            session.query(OperationalIssue)
            .filter(
                OperationalIssue.note_id == note.id,
                OperationalIssue.source_revision_id == rev.id,
                or_(OperationalIssue.extraction_id == ext.public_id,
                    OperationalIssue.extraction_id.is_(None)),
                OperationalIssue.workspace_id == workspace_id,
                OperationalIssue.severity == "critical_blocker",
                OperationalIssue.status == "open",
            )
            .all()
        )
        if open_criticals:
            raise BlockedReviewError(
                "Cannot complete a review with an unresolved critical source/evidence issue."
            )

    # 6. Reconstruct authoritative reviewed snapshot from bound extraction + validated decisions
    extracted_data = json.loads(ext.extracted_json or "{}")
    derived_snapshot, has_corrections = derive_reviewed_snapshot(
        extracted_data=extracted_data,
        item_decisions=req.item_decisions,
        category_acknowledgments=req.category_acknowledgments,
        is_completing=is_completing,
        raw_text=rev.raw_text,
        client_snapshot=req.reviewed_snapshot,
    )

    if req.event_kind == "draft_saved":
        derived_outcome = "draft"
        new_note_status = "draft"
    elif req.event_kind == "review_reopened":
        derived_outcome = "needs_review"
        new_note_status = "needs_review"
    elif req.event_kind == "review_completed":
        derived_outcome = "reviewed_corrected" if has_corrections else "reviewed_unchanged"
        new_note_status = derived_outcome
    else:
        raise InvalidReviewPayloadError(f"Unsupported event_kind '{req.event_kind}'.")

    # 7. Create ReviewEvent (storing authoritative server-derived snapshot)
    merged_issue_dispositions = {}
    if req.issue_dispositions:
        merged_issue_dispositions = {k: v.model_dump() for k, v in req.issue_dispositions.items()}
    else:
        from models import IssueEvent
        bound_issues = (
            session.query(OperationalIssue)
            .filter(
                OperationalIssue.note_id == note.id,
                OperationalIssue.extraction_id == req.extraction_id,
                OperationalIssue.status != "open",
            )
            .all()
        )
        for iss in bound_issues:
            latest_ev = (
                session.query(IssueEvent)
                .filter(IssueEvent.issue_id == iss.id)
                .order_by(IssueEvent.created_at.desc())
                .first()
            )
            merged_issue_dispositions[iss.id] = {
                "disposition": iss.status,
                "reason": latest_ev.reason if latest_ev else "Reviewer acknowledged in workspace",
            }

    review_event = ReviewEvent(
        workspace_id=workspace_id,
        note_id=note.id,
        source_revision_id=rev.id,
        extraction_id=req.extraction_id,
        source_hash=rev.sha256,
        parent_event_id=req.expected_head_event_id,
        event_kind=req.event_kind,
        reviewed_snapshot_json=json.dumps(derived_snapshot),
        item_decisions_json=json.dumps(req.item_decisions or {}),
        category_acknowledgments_json=json.dumps(req.category_acknowledgments or {}),
        issue_dispositions_json=json.dumps(merged_issue_dispositions),
        derived_outcome=derived_outcome,
        idempotency_key=req.idempotency_key,
        request_hash=req_hash,
        expected_lock_version=req.expected_lock_version,
        review_duration_ms=req.review_duration_ms,
    )
    session.add(review_event)
    session.flush()

    # 8. Record Issue Dispositions if provided
    if req.issue_dispositions:
        for issue_id, disp in req.issue_dispositions.items():
            issue = (
                session.query(OperationalIssue)
                .filter(
                    OperationalIssue.id == issue_id,
                    OperationalIssue.workspace_id == workspace_id,
                    OperationalIssue.note_id == note.id,
                )
                .first()
            )
            if issue:
                issue.status = disp.disposition
                evt = IssueEvent(
                    issue_id=issue.id,
                    action=disp.disposition,
                    reason=disp.reason,
                    bound_review_event_id=review_event.id,
                )
                session.add(evt)

    # 9. Atomic Conditional Update on Note
    head_predicate = (
        Note.review_head_event_id.is_(None)
        if req.expected_head_event_id is None
        else (Note.review_head_event_id == req.expected_head_event_id)
    )

    stmt = (
        update(Note)
        .where(
            Note.id == req.note_id,
            Note.workspace_id == workspace_id,
            Note.current_source_revision_id == req.source_revision_id,
            Note.current_extraction_id == ext.public_id,
            Note.lock_version == req.expected_lock_version,
            head_predicate,
        )
        .values(
            review_head_event_id=review_event.id,
            lock_version=Note.lock_version + 1,
            status=new_note_status,
        )
    )

    result = session.execute(stmt)
    if result.rowcount != 1:
        session.rollback()
        raise StaleReviewError(
            f"Stale review mutation rejected: note {req.note_id} was modified concurrently "
            f"(expected lock_version {req.expected_lock_version}, expected head {req.expected_head_event_id})."
        )

    session.commit()
    return review_event, False
