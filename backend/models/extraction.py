from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from models.base import Base

class Extraction(Base):
    __tablename__ = "extractions"
    id = Column(Integer, primary_key=True)
    note_id = Column(Integer, ForeignKey("notes.id"), nullable=False)
    extracted_json = Column(Text, nullable=False)
    pipeline_version = Column(String, nullable=False)
    extracted_at = Column(DateTime, server_default=func.now())
