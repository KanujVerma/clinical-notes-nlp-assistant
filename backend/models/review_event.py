import uuid
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from models.base import Base


class ReviewEvent(Base):
    __tablename__ = "review_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String(36), nullable=False, index=True)
    note_id = Column(Integer, ForeignKey("notes.id"), nullable=False, index=True)
    source_revision_id = Column(String(36), nullable=False, index=True)
    extraction_id = Column(String(36), nullable=False, index=True)
    source_hash = Column(String(64), nullable=False)
    parent_event_id = Column(String(36), ForeignKey("review_events.id"), nullable=True)
    event_kind = Column(String(32), nullable=False)  # draft_saved | review_completed | review_reopened
    reviewed_snapshot_json = Column(Text, nullable=False)
    item_decisions_json = Column(Text, nullable=False)
    category_acknowledgments_json = Column(Text, nullable=False)
    issue_dispositions_json = Column(Text, nullable=True)
    correction_diff_json = Column(Text, nullable=True)
    diff_algorithm_version = Column(String(32), nullable=False, default="1.0.0")
    derived_outcome = Column(String(32), nullable=False)  # reviewed_unchanged | reviewed_corrected | draft
    idempotency_key = Column(String(128), nullable=True, index=True)
    request_hash = Column(String(64), nullable=True)
    expected_lock_version = Column(Integer, nullable=True)
    review_duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("workspace_id", "idempotency_key", name="uq_workspace_idempotency"),
    )
