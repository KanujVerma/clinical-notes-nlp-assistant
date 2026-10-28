import uuid
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, Index
from sqlalchemy.sql import func
from models.base import Base


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String(36), nullable=False, index=True)
    kind = Column(String(50), nullable=False)  # ocr | extraction | eval_run | ai_inference
    note_id = Column(Integer, nullable=True, index=True)
    source_revision_id = Column(String(36), nullable=True, index=True)
    idempotency_key = Column(String(128), nullable=True, index=True)
    request_hash = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False, default="queued")  # queued | running | succeeded | partial | failed | canceled
    attempt_number = Column(Integer, nullable=False, default=0)
    lease_owner = Column(String(64), nullable=True)
    lease_expiry = Column(DateTime, nullable=True)
    progress = Column(Float, nullable=False, default=0.0)
    payload_json = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    # SQLite/PostgreSQL both permit multiple NULL keys under a unique
    # constraint but reject two active requests sharing a non-NULL key.
    __table_args__ = (
        Index("uq_jobs_workspace_idempotency", "workspace_id", "idempotency_key", unique=True),
    )
