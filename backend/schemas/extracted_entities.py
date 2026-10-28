import uuid
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from schemas.evidence import TextEvidence, ImageEvidence


class MetadataItem(BaseModel):
    id: str = Field(default_factory=lambda: f"meta_{uuid.uuid4().hex[:12]}")
    field_name: str  # patient_name | date_of_service | provider_name
    value: str
    evidence: Optional[TextEvidence] = None
    is_added: bool = False


class VitalItem(BaseModel):
    id: str = Field(default_factory=lambda: f"vit_{uuid.uuid4().hex[:12]}")
    vital_type: str  # bp_systolic | bp_diastolic | heart_rate | temperature | respiratory_rate | spo2 | weight
    value: str
    unit: Optional[str] = None
    evidence: Optional[TextEvidence] = None
    is_added: bool = False


class MedicationItem(BaseModel):
    id: str = Field(default_factory=lambda: f"med_{uuid.uuid4().hex[:12]}")
    name: str
    dose: Optional[str] = None
    route: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None
    prn: bool = False
    action: str = "unspecified"  # start | stop | continue | hold | modify | negated | unspecified
    evidence: Optional[TextEvidence] = None
    image_evidence: Optional[ImageEvidence] = None
    attribute_ids: Dict[str, str] = Field(default_factory=dict)  # attribute_name -> stable_attr_id
    attributes_evidence: Dict[str, TextEvidence] = Field(default_factory=dict)
    is_added: bool = False

    def model_post_init(self, __context: Any) -> None:
        # Populate stable attribute IDs if not present
        for attr in ["name", "dose", "route", "frequency", "duration", "prn", "action"]:
            if attr not in self.attribute_ids:
                self.attribute_ids[attr] = f"{self.id}_{attr}"


class InstructionItem(BaseModel):
    id: str = Field(default_factory=lambda: f"inst_{uuid.uuid4().hex[:12]}")
    category: str  # follow_up | discharge | return_precautions
    text: str
    evidence: Optional[TextEvidence] = None
    is_added: bool = False


class StructuredExtraction(BaseModel):
    schema_version: str = "2.0.0"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    vitals: List[VitalItem] = Field(default_factory=list)
    medications: List[MedicationItem] = Field(default_factory=list)
    instructions: List[InstructionItem] = Field(default_factory=list)
