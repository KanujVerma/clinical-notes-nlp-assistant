from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from models.base import Base

class Validation(Base):
    __tablename__ = "validations"
    id = Column(Integer, primary_key=True)
    note_id = Column(Integer, ForeignKey("notes.id"), nullable=False, unique=True)
    validated_json = Column(Text, nullable=False)
    status = Column(String, nullable=False)  # pending|accepted|corrected
    review_duration_ms = Column(Integer, nullable=True)
    correction_count = Column(Integer, nullable=False, default=0)
    validated_at = Column(DateTime, server_default=func.now())
