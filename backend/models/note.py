from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from models.base import Base

class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True)
    filename = Column(String, nullable=True)
    raw_text = Column(Text, nullable=False)
    source = Column(String, nullable=False)  # paste|txt|pdf|ocr|demo
    created_at = Column(DateTime, server_default=func.now())
