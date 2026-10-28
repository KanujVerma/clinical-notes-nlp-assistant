import uuid
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from models.base import Base


class NoteRevision(Base):
    __tablename__ = "note_revisions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    note_id = Column(Integer, ForeignKey("notes.id"), nullable=False, index=True)
    workspace_id = Column(String(36), nullable=False, index=True)
    revision_number = Column(Integer, nullable=False, default=1)
    parent_revision_id = Column(String(36), ForeignKey("note_revisions.id"), nullable=True)
    source_asset_id = Column(String(36), ForeignKey("source_assets.id"), nullable=True)
    acquisition_run_id = Column(String(36), ForeignKey("acquisition_runs.id"), nullable=True)
    raw_text = Column(Text, nullable=False)
    normalized_text = Column(Text, nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    normalization_version = Column(String(32), nullable=False, default="1.0.0")
    offset_map_json = Column(Text, nullable=True)
    pages_json = Column(Text, nullable=True)
    creation_reason = Column(String(50), nullable=False, default="acquisition")  # acquisition | human_edit | ocr_rescan
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
