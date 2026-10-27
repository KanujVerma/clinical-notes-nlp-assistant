import uuid
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from models.base import Base


class AcquisitionRun(Base):
    __tablename__ = "acquisition_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_asset_id = Column(String(36), ForeignKey("source_assets.id"), nullable=True, index=True)
    engine = Column(String(50), nullable=False, default="pymupdf_tesseract")
    engine_version = Column(String(50), nullable=True)
    config_hash = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False, default="completed")  # pending | running | completed | partial | failed
    page_count = Column(Integer, nullable=False, default=1)
    pages_json = Column(Text, nullable=True)
    canonical_text = Column(Text, nullable=True)
    warnings_json = Column(Text, nullable=True)
    error_code = Column(String(50), nullable=True)
    started_at = Column(DateTime, server_default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)
