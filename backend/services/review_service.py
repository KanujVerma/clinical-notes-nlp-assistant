import json
import hashlib
from typing import Dict, Any, Optional, Tuple
from sqlalchemy import update, and_
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
                OperationalIssue.extraction_id == ext.public_id,
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

    # 6. Server-derived outcome
    # Check decisions: if any edit, remove, or add exists -> reviewed_corrected; else reviewed_unchanged
    has_corrections = False
    for item_id, decision_info in req.item_decisions.items():
        if isinstance(decision_info, dict):
            dec = decision_info.get("decision", "accept")
            attr_decisions = decision_info.get("attribute_decisions") or {}
            if dec in ("edit", "remove", "add"):
                has_corrections = True
                break
            for attr_name, attr_dec in attr_decisions.items():
                if attr_dec.get("decision") in ("edit", "remove", "add"):
                    has_corrections = True
                    break
        elif isinstance(decision_info, str) and decision_info in ("edit", "remove", "add"):
            has_corrections = True
            break

    if req.event_kind == "draft_saved":
        derived_outcome = "draft"
        new_note_status = "draft"
    elif req.event_kind == "review_reopened":
        derived_outcome = "needs_review"
        new_note_status = "needs_review"
    else:
        derived_outcome = "reviewed_corrected" if has_corrections else "reviewed_unchanged"
        new_note_status = derived_outcome

    # 7. Create ReviewEvent
    review_event = ReviewEvent(
        workspace_id=workspace_id,
        note_id=note.id,
        source_revision_id=rev.id,
        extraction_id=req.extraction_id,
        source_hash=rev.sha256,
        parent_event_id=req.expected_head_event_id,
        event_kind=req.event_kind,
        reviewed_snapshot_json=json.dumps(req.reviewed_snapshot or {}),
        item_decisions_json=json.dumps(req.item_decisions or {}),
        category_acknowledgments_json=json.dumps(req.category_acknowledgments or {}),
        issue_dispositions_json=json.dumps({k: v.model_dump() for k, v in req.issue_dispositions.items()} if req.issue_dispositions else {}),
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
