from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class ItemDecision(BaseModel):
    decision: str  # accept | edit | remove | add
    value: Optional[Any] = None
    attribute_decisions: Optional[Dict[str, Dict[str, Any]]] = None  # for medication child attributes
    evidence: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None


class IssueDisposition(BaseModel):
    disposition: str  # acknowledged | dismissed | resolved
    reason: Optional[str] = None


class ReviewMutationRequest(BaseModel):
    schema_version: str = "2.0.0"
    note_id: int
    source_revision_id: str
    extraction_id: str
    source_hash: str
    expected_lock_version: int
    expected_head_event_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    event_kind: str = "review_completed"  # draft_saved | review_completed | review_reopened
    item_decisions: Dict[str, Any] = Field(default_factory=dict)
    category_acknowledgments: Dict[str, bool] = Field(default_factory=dict)
    issue_dispositions: Dict[str, IssueDisposition] = Field(default_factory=dict)
    reviewed_snapshot: Optional[Dict[str, Any]] = None
    review_duration_ms: Optional[int] = None
