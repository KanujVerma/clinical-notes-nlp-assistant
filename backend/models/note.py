from sqlalchemy import Column, Integer, String, Text, DateTime, Float
from sqlalchemy.sql import func
from models.base import Base


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True)
    filename = Column(String, nullable=True)
    raw_text = Column(Text, nullable=False)
    source = Column(String, nullable=False)  # paste|txt|pdf|ocr|demo
    ocr_confidence = Column(Float, nullable=True)
    session_id = Column(String(36), nullable=True, index=True)
    workspace_id = Column(String(36), nullable=True, index=True)
    current_source_revision_id = Column(String(36), nullable=True)
    current_extraction_id = Column(String(36), nullable=True)
    review_head_event_id = Column(String(36), nullable=True)
    lock_version = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="needs_review")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
