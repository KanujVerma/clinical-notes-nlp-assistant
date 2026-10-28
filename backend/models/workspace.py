import uuid
from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from models.base import Base


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    capability_token_hash = Column(String(64), nullable=True, index=True)
    mode = Column(String(32), nullable=False, default="normal")  # normal | hosted_demo
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=True)
    last_activity_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    state = Column(String(32), nullable=False, default="active")  # active | revoked | expired
    schema_version = Column(String(32), nullable=False, default="1.0.0")
