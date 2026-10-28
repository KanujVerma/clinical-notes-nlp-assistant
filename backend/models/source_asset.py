import uuid
from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.sql import func
from models.base import Base


class SourceAsset(Base):
    __tablename__ = "source_assets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String(36), nullable=False, index=True)
    sha256 = Column(String(64), nullable=False, index=True)
    storage_key = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=False)
    byte_size = Column(Integer, nullable=False)
    original_filename = Column(String(255), nullable=True)
    page_count = Column(Integer, nullable=False, default=1)
    acquisition_kind = Column(String(50), nullable=False, default="upload")  # upload | paste | demo | ocr
    schema_version = Column(String(32), nullable=False, default="1.0.0")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
