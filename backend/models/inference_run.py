import uuid
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from models.base import Base


class InferenceRun(Base):
    __tablename__ = "inference_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String(36), nullable=False, index=True)
    note_id = Column(Integer, ForeignKey("notes.id"), nullable=False, index=True)
    source_revision_id = Column(String(36), nullable=False, index=True)
    task_type = Column(String(50), nullable=False)  # ocr_second_opinion | semantic_candidates | handwriting_transcription
    model_name = Column(String(100), nullable=False)
    model_digest = Column(String(128), nullable=True)
    prompt_template_hash = Column(String(64), nullable=True)
    config_hash = Column(String(64), nullable=True)
    input_hash = Column(String(64), nullable=True)
    raw_candidate_json = Column(Text, nullable=True)
    parsed_candidate_json = Column(Text, nullable=True)
    alignment_results_json = Column(Text, nullable=True)
    discrepancies_json = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    status = Column(String(32), nullable=False, default="completed")  # completed | failed | disabled
    error_code = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
