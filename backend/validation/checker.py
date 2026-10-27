import re
import uuid
import hashlib
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ValidationIssue(BaseModel):
    id: str = Field(default_factory=lambda: f"iss_{uuid.uuid4().hex[:12]}")
    issue_code: str
    severity: str  # critical_blocker | warning | info
    category: str  # clinical_canary | ocr_transcription | evidence_mismatch | pipeline_anomaly
    item_id: Optional[str] = None
    field_path: Optional[str] = None
    evidence_span: Optional[Dict[str, Any]] = None
    safe_explanation: str
    check_policy_version: str = "1.0.0"


def check_extraction(
    source_revision: Any,  # NoteRevision or dict
    extraction: Any,       # Extraction or dict
    policy_version: str = "1.0.0"
) -> List[ValidationIssue]:
    """Pure validation function that inspects extracted fields against source text and clinical-safety rules.
    Does NOT call the extractor itself."""
    issues: List[ValidationIssue] = []

    # 1. Resolve raw text and hash
    raw_text = getattr(source_revision, "raw_text", None)
    if raw_text is None and isinstance(source_revision, dict):
        raw_text = source_revision.get("raw_text", "")
    raw_text = raw_text or ""

    expected_hash = getattr(source_revision, "sha256", None)
    if expected_hash is None and isinstance(source_revision, dict):
        expected_hash = source_revision.get("sha256")
    actual_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    # Rule A05: Hash mismatch / integrity
    if expected_hash and expected_hash != actual_hash:
        issues.append(ValidationIssue(
            issue_code="A05_SOURCE_HASH_MISMATCH",
            severity="critical_blocker",
            category="pipeline_anomaly",
            safe_explanation=f"Source text SHA-256 hash mismatch: expected {expected_hash}, calculated {actual_hash}",
            check_policy_version=policy_version,
        ))

    # Bind the extraction record to the *same* exact source revision and
    # hash. Matching only a text quote is not sufficient source provenance.
    revision_id = getattr(source_revision, "id", None)
    if revision_id is None and isinstance(source_revision, dict):
        revision_id = source_revision.get("id")
    extraction_revision_id = getattr(extraction, "source_revision_id", None)
    if extraction_revision_id is None and isinstance(extraction, dict):
        extraction_revision_id = extraction.get("source_revision_id")
    extraction_hash = getattr(extraction, "source_text_hash", None)
    if extraction_hash is None and isinstance(extraction, dict):
        extraction_hash = extraction.get("source_text_hash")
    if revision_id and extraction_revision_id and revision_id != extraction_revision_id:
        issues.append(ValidationIssue(
            issue_code="SOURCE_BINDING_MISMATCH",
            severity="critical_blocker",
            category="pipeline_anomaly",
            safe_explanation="Extraction references a different source revision",
            check_policy_version=policy_version,
        ))
    if extraction_hash and extraction_hash != actual_hash:
        issues.append(ValidationIssue(
            issue_code="SOURCE_BINDING_MISMATCH",
            severity="critical_blocker",
            category="pipeline_anomaly",
            safe_explanation="Extraction source hash does not match the acquired text",
            check_policy_version=policy_version,
        ))

    # 2. Parse extraction data
    extracted_data = getattr(extraction, "extracted_json", None)
    if extracted_data is None and isinstance(extraction, dict):
        extracted_data = extraction.get("extracted_json") or extraction.get("structured_data")

    if isinstance(extracted_data, str):
        import json
        try:
            data = json.loads(extracted_data)
        except Exception as e:
            issues.append(ValidationIssue(
                issue_code="A05_MALFORMED_EXTRACTION_JSON",
                severity="critical_blocker",
                category="pipeline_anomaly",
                safe_explanation=f"Extraction payload is not valid JSON: {str(e)}",
                check_policy_version=policy_version,
            ))
            return issues
    elif isinstance(extracted_data, dict):
        data = extracted_data
    else:
        data = {}

    medications = data.get("medications") or []
    vitals_raw = data.get("vitals") or []
    instructions_raw = data.get("instructions") or []
    metadata = data.get("metadata") or {}

    # Normalize vitals to list of dicts
    vitals = []
    if isinstance(vitals_raw, dict):
        for k, v in vitals_raw.items():
            if isinstance(v, dict):
                vitals.append({"vital_type": k, **v})
            else:
                vitals.append({"vital_type": k, "value": str(v)})
    elif isinstance(vitals_raw, list):
        for item in vitals_raw:
            if isinstance(item, dict):
                vitals.append(item)
            else:
                vitals.append({"vital_type": "unknown", "value": str(item)})

    # Normalize instructions to list of dicts
    instructions = []
    if isinstance(instructions_raw, dict):
        for k, v in instructions_raw.items():
            if isinstance(v, dict):
                instructions.append({"category": k, **v})
            else:
                instructions.append({"category": k, "text": str(v)})
    elif isinstance(instructions_raw, list):
        for item in instructions_raw:
            if isinstance(item, dict):
                instructions.append(item)
            else:
                instructions.append({"category": "unknown", "text": str(item)})

    # 3. Evidence Spans & Exact Quotes (Rule A08)
    def verify_evidence(ev_or_item: Any, item_id: str, field_path: str):
        if not ev_or_item:
            return
        start = None
        end = None
        raw_quote = None

        if isinstance(ev_or_item, dict):
            sub_ev = ev_or_item.get("evidence")
            if isinstance(sub_ev, dict):
                start = sub_ev.get("start")
                end = sub_ev.get("end")
                raw_quote = sub_ev.get("raw_quote") or sub_ev.get("text")
            elif "start" in ev_or_item and "end" in ev_or_item:
                start = ev_or_item.get("start")
                end = ev_or_item.get("end")
                raw_quote = ev_or_item.get("raw_quote") or ev_or_item.get("text")
            elif isinstance(ev_or_item.get("span"), (list, tuple)) and len(ev_or_item["span"]) == 2:
                # Native pipeline entity span: check bounds
                start = ev_or_item["span"][0]
                end = ev_or_item["span"][1]
                raw_quote = None
        elif isinstance(ev_or_item, (list, tuple)) and len(ev_or_item) == 2:
            start = ev_or_item[0]
            end = ev_or_item[1]
            raw_quote = None

        if start is None or end is None:
            return

        # Check bounds (Rule A08)
        if not (type(start) is int and type(end) is int
                and 0 <= start < end <= len(raw_text)):
            issues.append(ValidationIssue(
                issue_code="A08_EVIDENCE_OUT_OF_BOUNDS",
                severity="critical_blocker",
                category="evidence_mismatch",
                item_id=item_id,
                field_path=field_path,
                evidence_span={"start": start, "end": end, "raw_quote": raw_quote},
                safe_explanation=f"Evidence span [{start}:{end}] is out of bounds for source text of length {len(raw_text)}",
                check_policy_version=policy_version,
            ))
            return

        # Check quote match if explicit quote claimed
        if raw_quote is not None:
            actual_slice = raw_text[start:end]
            # TextEvidence.raw_quote is an exact source substring. Neither
            # whitespace-normalized matching nor substring containment proves
            # this invariant (especially for decimal medication doses).
            if actual_slice != raw_quote:
                issues.append(ValidationIssue(
                    issue_code="A08_EVIDENCE_QUOTE_MISMATCH",
                    severity="critical_blocker",
                    category="evidence_mismatch",
                    item_id=item_id,
                    field_path=field_path,
                    evidence_span={"start": start, "end": end, "raw_quote": raw_quote},
                    safe_explanation=f"Evidence quote mismatch: span [{start}:{end}] contains '{actual_slice}', but quote claims '{raw_quote}'",
                    check_policy_version=policy_version,
                ))

    # 4. Inspect Medications
    med_names: Dict[str, List[Dict[str, Any]]] = {}
    for med in medications:
        m_id = med.get("id") or str(uuid.uuid4())
        name = (med.get("name") or "").strip().lower()
        dose = med.get("dose")
        route = med.get("route")
        freq = med.get("frequency")
        action = (med.get("action") or "unspecified").lower()
        verify_evidence(med.get("evidence") or med, m_id, f"medications.{name}.evidence")

        # Track name duplicates (Rule A02)
        if name:
            med_names.setdefault(name, []).append(med)

        # Decimal dose check (Rule A09 / A01)
        if dose:
            dose_str = str(dose)
            # Detect leading decimal point without leading zero (e.g. .5 mg)
            if re.search(r'(?<!\d)\.\d+', dose_str):
                issues.append(ValidationIssue(
                    issue_code="A09_DECIMAL_DOSE_LEADING_ZERO_MISSING",
                    severity="warning",
                    category="clinical_canary",
                    item_id=m_id,
                    field_path="dose",
                    safe_explanation=f"Medication '{name}' dose '{dose_str}' lacks a leading zero before decimal (risk of 10x dosing error)",
                    check_policy_version=policy_version,
                ))
            # Detect trailing zero after decimal (e.g. 5.0 mg)
            if re.search(r'\.\d*0\b', dose_str):
                issues.append(ValidationIssue(
                    issue_code="A09_DECIMAL_DOSE_TRAILING_ZERO",
                    severity="info",
                    category="clinical_canary",
                    item_id=m_id,
                    field_path="dose",
                    safe_explanation=f"Medication '{name}' dose '{dose_str}' has a trailing zero (e.g. 5.0 mg, risk of reading as 50 mg)",
                    check_policy_version=policy_version,
                ))

        # Missing route / frequency check (Rule A01)
        if not route and action in ("start", "continue", "modify"):
            issues.append(ValidationIssue(
                issue_code="A01_MISSING_ROUTE",
                severity="info",
                category="clinical_canary",
                item_id=m_id,
                field_path="route",
                safe_explanation=f"Medication '{name}' has no route specified",
                check_policy_version=policy_version,
            ))

        # Conflicting or negated action (Rule A10)
        if action in ("negated", "held", "stopped", "discontinued"):
            # Check if text context near medication mentions hold or stop
            issues.append(ValidationIssue(
                issue_code="A10_NON_ACTIVE_MEDICATION",
                severity="warning",
                category="clinical_canary",
                item_id=m_id,
                field_path="action",
                safe_explanation=f"Medication '{name}' is marked as {action}; ensure it is not transcribed as active",
                check_policy_version=policy_version,
            ))

    # Duplicate medications check (Rule A02)
    for name, occurrences in med_names.items():
        if len(occurrences) > 1:
            doses = [o.get("dose") for o in occurrences if o.get("dose")]
            actions = [o.get("action") for o in occurrences if o.get("action")]
            if len(set(doses)) > 1 or len(set(actions)) > 1:
                issues.append(ValidationIssue(
                    issue_code="A02_DUPLICATE_MEDICATION_CONFLICT",
                    severity="warning",
                    category="clinical_canary",
                    field_path=f"medications.{name}",
                    safe_explanation=f"Multiple entries for medication '{name}' have conflicting doses ({doses}) or actions ({actions})",
                    check_policy_version=policy_version,
                ))

    # Attribute borrowing check: check if two medications appear in the same sentence (Rule A09)
    sentences = re.split(r'[.\n]+', raw_text)
    for sent in sentences:
        found_meds = [m for m in med_names.keys() if m in sent.lower()]
        if len(found_meds) >= 2:
            issues.append(ValidationIssue(
                issue_code="A09_MULTIPLE_MEDICATIONS_IN_SENTENCE",
                severity="info",
                category="clinical_canary",
                safe_explanation=f"Sentence contains multiple medications ({', '.join(found_meds)}). Verify dose/route are not cross-borrowed.",
                check_policy_version=policy_version,
            ))

    # 5. Inspect Vitals (Rule A03, A11)
    vital_types_found: Dict[str, List[Any]] = {}
    for vit in vitals:
        v_id = vit.get("id") or str(uuid.uuid4())
        v_type = vit.get("vital_type") or vit.get("type") or "unknown"
        val = vit.get("value")
        unit = vit.get("unit")
        verify_evidence(vit.get("evidence") or vit, v_id, f"vitals.{v_type}")

        vital_types_found.setdefault(v_type, []).append(vit)

        # Missing unit check
        if val and not unit and v_type in ("weight", "temperature"):
            issues.append(ValidationIssue(
                issue_code="A03_MISSING_VITAL_UNIT",
                severity="warning",
                category="clinical_canary",
                item_id=v_id,
                field_path=f"vitals.{v_type}.unit",
                safe_explanation=f"Vital '{v_type}' has value '{val}' but missing unit (e.g. kg vs lbs or C vs F)",
                check_policy_version=policy_version,
            ))

    # Conflicting duplicate vitals in note (Rule A11)
    for v_type, instances in vital_types_found.items():
        if len(instances) > 1:
            vals = [i.get("value") for i in instances]
            if len(set(vals)) > 1:
                issues.append(ValidationIssue(
                    issue_code="A11_CONFLICTING_VITALS",
                    severity="warning",
                    category="clinical_canary",
                    field_path=f"vitals.{v_type}",
                    safe_explanation=f"Conflicting values found for vital '{v_type}': {vals}",
                    check_policy_version=policy_version,
                ))

    # 6. Inspect Instructions (Rule A04, A12)
    for inst in instructions:
        if not isinstance(inst, dict):
            continue
        i_id = inst.get("id") or str(uuid.uuid4())
        cat = inst.get("category") or "unknown"
        txt = inst.get("text") or inst.get("value") or ""
        verify_evidence(inst.get("evidence") or inst, i_id, f"instructions.{cat}")

        # Contradictory instructions canary (Rule A04)
        if re.search(r'\b(do not|avoid|discontinue|stop)\b', txt, re.I) and re.search(r'\b(resume|continue|start)\b', txt, re.I):
            issues.append(ValidationIssue(
                issue_code="A04_CONTRADICTORY_INSTRUCTION",
                severity="warning",
                category="clinical_canary",
                item_id=i_id,
                field_path="text",
                safe_explanation=f"Instruction contains potentially contradictory action words: '{txt}'",
                check_policy_version=policy_version,
            ))

    # 7. Inspect Metadata
    if isinstance(metadata, dict):
        for k, v in metadata.items():
            if isinstance(v, dict):
                ev = v.get("evidence") or {}
                val = v.get("value")
                verify_evidence(ev, f"meta_{k}", f"metadata.{k}")
            elif isinstance(v, str):
                pass

    return issues
