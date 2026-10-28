import uuid
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from models.base import Base


class Extraction(Base):
    __tablename__ = "extractions"

    id = Column(Integer, primary_key=True)
    note_id = Column(Integer, ForeignKey("notes.id"), nullable=False, index=True)
    extracted_json = Column(Text, nullable=False)
    pipeline_version = Column(String, nullable=False)
    extracted_at = Column(DateTime, server_default=func.now())

    # Extended immutable extraction fields
    public_id = Column(String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String(36), nullable=True, index=True)
    source_revision_id = Column(String(36), nullable=True, index=True)
    source_text_hash = Column(String(64), nullable=True)
    rules_hash = Column(String(64), nullable=True)
    vocabulary_hash = Column(String(64), nullable=True)
    schema_version = Column(String(32), nullable=False, default="2.0.0")
    status = Column(String(32), nullable=False, default="completed")  # completed | failed | pending
    check_policy_version = Column(String(32), nullable=False, default="1.0.0")
    error_metadata_json = Column(Text, nullable=True)
