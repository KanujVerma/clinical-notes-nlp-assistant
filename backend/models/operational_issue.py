import uuid
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from models.base import Base


class OperationalIssue(Base):
    __tablename__ = "operational_issues"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String(36), nullable=False, index=True)
    note_id = Column(Integer, ForeignKey("notes.id"), nullable=False, index=True)
    source_revision_id = Column(String(36), nullable=False, index=True)
    extraction_id = Column(String(36), nullable=True, index=True)
    issue_code = Column(String(64), nullable=False, index=True)
    severity = Column(String(32), nullable=False)  # critical_blocker | warning | info
    category = Column(String(50), nullable=False)  # clinical_canary | ocr_transcription | evidence_mismatch | pipeline_anomaly
    item_id = Column(String(64), nullable=True)
    field_path = Column(String(100), nullable=True)
    evidence_span_json = Column(Text, nullable=True)
    safe_explanation = Column(Text, nullable=False)
    check_policy_version = Column(String(32), nullable=False, default="1.0.0")
    status = Column(String(32), nullable=False, default="open")  # open | acknowledged | resolved | dismissed
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class IssueEvent(Base):
    __tablename__ = "issue_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    issue_id = Column(String(36), ForeignKey("operational_issues.id"), nullable=False, index=True)
    action = Column(String(32), nullable=False)  # opened | acknowledged | resolved | dismissed
    actor = Column(String(64), nullable=False, default="reviewer")
    reason = Column(Text, nullable=True)
    bound_review_event_id = Column(String(36), ForeignKey("review_events.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
