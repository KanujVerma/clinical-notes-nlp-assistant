# API Contract & Endpoint Reference

The Clinical Notes NLP Assistant & Validation Workbench exposes a unified REST API across 21 endpoints, supporting both legacy review operations and the enhanced immutable provenance architecture.

---

## 1. System & Health Endpoints

### `GET /api/health/live`
- **Purpose**: Liveness probe verifying Flask web engine is responding.
- **Response**: `200 OK`
  ```json
  { "status": "live", "pipeline_version": "0.1.0" }
  ```

### `GET /api/health/ready`
- **Purpose**: Readiness probe verifying database connectivity.
- **Response**: `200 OK`
  ```json
  { "status": "ready", "database": "connected" }
  ```

---

## 2. Workspace & Capability Management

### `POST /api/workspaces`
- **Purpose**: Provision an isolated review workspace with a cryptographic capability token.
- **Request Body**:
  ```json
  { "mode": "demo" }
  ```
- **Response**: `201 Created`
  ```json
  {
    "workspace_id": "c1a7d65b-...",
    "mode": "demo",
    "capability_token": "a1f9e...",
    "created_at": "2026-10-27T12:00:00Z"
  }
  ```

### `GET /api/capabilities`
- **Purpose**: Verify caller's capability token or active session.
- **Headers**: `X-Session-ID: <token>`
- **Response**: `200 OK`
  ```json
  { "workspace_id": "c1a7d65b-...", "mode": "demo", "role": "reviewer" }
  ```

---

## 3. Note Ingestion & Source Revisions

### `POST /api/upload`
- **Purpose**: Upload PDF, image, or text clinical note. Acquires content-addressed storage asset and runs initial extraction pipeline.
- **Request**: Multipart Form Data (`file`)
- **Response**: `200 OK`
  ```json
  { "note_id": 1, "filename": "sample.pdf", "extracted": { ... } }
  ```

### `POST /api/extract`
- **Purpose**: Ingest pasted text note and return extracted entities.
- **Request Body**:
  ```json
  { "text": "Patient on metformin 500 mg...", "filename": "pasted_note.txt" }
  ```
- **Response**: `200 OK`
  ```json
  { "note_id": 1, "extracted_json": { ... } }
  ```

### `GET /api/notes/<note_id>/source`
- **Purpose**: Retrieve current source text and revision metadata.
- **Response**: `200 OK`
  ```json
  {
    "note_id": 1,
    "revision_id": "r-8f7b...",
    "revision_number": 1,
    "sha256": "4a71...",
    "raw_text": "...",
    "created_at": "2026-10-27T12:00:00Z"
  }
  ```

### `POST /api/notes/<note_id>/revisions`
- **Purpose**: Create a new immutable source text revision, invalidating prior extractions and triggering re-extraction.
- **Request Body**:
  ```json
  {
    "raw_text": "Updated clinical transcription text...",
    "reason": "Corrected dosage transcription error from audio"
  }
  ```
- **Response**: `201 Created`
  ```json
  {
    "revision_id": "r-9a2c...",
    "revision_number": 2,
    "sha256": "8f3e...",
    "note_id": 1,
    "created_at": "2026-10-27T12:05:00Z"
  }
  ```

---

## 4. Immutable Review State Machine

### `POST /api/extractions/<extraction_id>/reviews`
- **Purpose**: Submit atomic, immutable human review event. Enforces optimistic concurrency (`lock_version`), category completeness, and blocker disposition.
- **Request Body**:
  ```json
  {
    "schema_version": "2.0.0",
    "note_id": 1,
    "source_revision_id": "r-8f7b...",
    "expected_lock_version": 0,
    "parent_event_id": null,
    "idempotency_key": "user-uuid-key-12345",
    "item_decisions": {
      "med.0.name": { "decision": "accept", "value": "metformin" },
      "med.0.dose": { "decision": "edit", "value": "1000 mg" }
    },
    "issue_dispositions": {
      "iss-001": { "disposition": "acknowledged", "reason": "Verified against source lab" }
    },
    "category_acknowledgments": {
      "metadata": true,
      "vitals": true,
      "medications": true,
      "instructions": true
    }
  }
  ```
- **Response Codes**:
  - `200 OK`: Duplicate request re-delivered (idempotency key match).
  - `201 Created`: Review event committed. Returns event ID and server-derived disposition (`reviewed_unchanged` vs `reviewed_corrected`).
  - `409 Conflict`: Stale `expected_lock_version` or revision mismatch.
  - `422 Unprocessable Entity`: Incomplete categories or unresolved blockers.

### `GET /api/notes/<note_id>/review-events`
- **Purpose**: Retrieve full immutable review history for an individual note.
- **Response**: `200 OK`
  ```json
  [
    {
      "event_id": "rev-11a...",
      "event_type": "review_submitted",
      "derived_outcome": "reviewed_corrected",
      "item_decisions": { ... },
      "created_at": "2026-10-27T12:10:00Z"
    }
  ]
  ```

---

## 5. Operational Issues & Quality Canaries

### `GET /api/issues`
- **Purpose**: List active validation issues and quality canaries.
- **Query Parameters**: `note_id`, `status` (`open` | `acknowledged` | `dismissed`), `severity` (`critical_blocker` | `canary` | `info`)
- **Response**: `200 OK`
  ```json
  [
    {
      "id": "iss-001",
      "note_id": 1,
      "issue_code": "A09_DOSE_FORMAT_CANARY",
      "severity": "critical_blocker",
      "category": "safety",
      "evidence_span": { "start": 32, "end": 38, "quote": ".5 mg" },
      "safe_explanation": "Unanchored decimal point detected (.5 mg). Requires reviewer verification.",
      "status": "open",
      "created_at": "2026-10-27T12:00:00Z"
    }
  ]
  ```

### `POST /api/issues/<issue_id>/disposition`
- **Purpose**: Transition an issue's lifecycle status.
- **Request Body**:
  ```json
  {
    "disposition": "acknowledged",
    "reason": "Reviewed in EHR source; dose confirmed."
  }
  ```
- **Response**: `200 OK`
  ```json
  { "id": "iss-001", "status": "acknowledged", "resolved_at": "..." }
  ```

---

## 6. Local AI Candidates & Discrepancies

### `POST /api/notes/<note_id>/ai-candidates`
- **Purpose**: Trigger local AI proposal extraction (via local Ollama or rule mock) and detect discrepancies against deterministic extraction.
- **Response**: `200 OK`
  ```json
  {
    "note_id": 1,
    "candidates": [ ... ],
    "discrepancies": [
      {
        "type": "potential_missed_medication",
        "medication": "aspirin",
        "detail": "Local AI identified aspirin mentioned in narrative."
      }
    ]
  }
  ```

---

## 7. Cryptographic Export Bundle

### `GET /api/review-events/<event_id>/export`
- **Purpose**: Download complete cryptographic ZIP export bundle.
- **Response**: `200 OK` (`application/zip`)
  - Content:
    - `reviewed_extraction.json`
    - `original_extraction.json`
    - `item_decisions.json`
    - `issue_dispositions.json`
    - `manifest.json` (SHA-256 hashes of all bundled files)
    - `summary.html` (Self-contained, human-readable review report)

---

## 8. Validation Lab & Strict Evaluation

### `GET /api/evaluation/runs`
- **Purpose**: List historical offline benchmark evaluation runs.
- **Response**: `200 OK`

### `POST /api/evaluation/runs`
- **Purpose**: Trigger offline synthetic benchmark evaluation against the 20 ground-truth reference notes.
- **Response**: `200 OK`
  ```json
  {
    "run_id": "eval-20261027-...",
    "created_at": "...",
    "summary": {
      "overall": { "precision": 0.941, "recall": 0.895, "f1": 0.917 },
      "categories": {
        "medications": { "precision": 0.933, "recall": 0.910, "f1": 0.921, "support": 45 },
        "vitals": { "precision": 0.970, "recall": 0.950, "f1": 0.960, "support": 60 }
      }
    }
  }
  ```
