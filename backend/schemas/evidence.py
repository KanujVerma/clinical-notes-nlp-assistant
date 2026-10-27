from typing import Optional, List
from pydantic import BaseModel, Field, model_validator


class TextEvidence(BaseModel):
    source_revision_id: Optional[str] = None
    start: int = Field(..., ge=0)
    end: int = Field(..., gt=0)
    raw_quote: str
    page_number: Optional[int] = 1
    method: str = "regex_medspacy"
    status: str = "verified"  # verified | unverified | disputed

    @model_validator(mode="after")
    def validate_half_open_span(self):
        if self.start >= self.end:
            raise ValueError(f"Invalid span: start ({self.start}) must be strictly less than end ({self.end})")
        return self

    def verify_against_text(self, text: str) -> bool:
        """Enforce invariant: 0 <= start < end <= len(text) and text[start:end] == raw_quote"""
        if self.start < 0 or self.end > len(text):
            return False
        return text[self.start:self.end] == self.raw_quote


class ImageEvidence(BaseModel):
    source_asset_id: Optional[str] = None
    page_number: int = 1
    bounding_box: List[float] = Field(default_factory=list)  # [x0, y0, x1, y1] normalized 0..1 or points
    coordinate_system: str = "pdf_points_bottom_left"
    originating_engine: str = "pymupdf"
    verification_status: str = "unverified"
