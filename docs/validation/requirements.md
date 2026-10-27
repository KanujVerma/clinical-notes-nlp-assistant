# Product Requirements & Operational Boundaries

## 1. Objective & Purpose

The **Clinical Notes NLP Assistant & Validation Workbench** is an engineering portfolio platform demonstrating source-grounded extraction, human-in-the-loop review workflows, and independent verification of clinical natural language processing pipelines using synthetic clinical documents.

---

## 2. Functional Requirements

### Document Ingestion & Acquisition
- **FR01 (Multi-Format Support)**: System shall accept text notes (`.txt`), native PDF documents (`.pdf`), and scanned image notes (`.png`, `.jpg`).
- **FR02 (Content-Addressed Storage)**: System shall store original documents in content-addressed storage indexed by SHA-256 digest.
- **FR03 (Source Lineage)**: System shall preserve pagewise native text and coordinates from PDFs, falling back to OCR only on image-based pages.
- **FR04 (Transcription Revisions)**: System shall support editing note text, producing an immutable `NoteRevision` chain with human-provided rationale.

### Deterministic Extraction
- **FR05 (Clinical Entity Extraction)**: System shall extract vital signs, medications, discharge instructions, and document metadata using deterministic rules and medSpaCy.
- **FR06 (Exact Coordinate Spans)**: System shall bind all extracted entities to exact half-open character offsets (`[start, end)`) matching note source text.
- **FR07 (Attribute Disaggregation)**: System shall parse medication attributes into discrete fields: name, dose, route, frequency, duration, qualifier.

### Independent Verification & Operational Checks
- **FR08 (Span Text Integrity)**: System shall verify that `note[start:end]` exactly equals the quoted entity text.
- **FR09 (Safety Canaries)**: System shall flag dangerous prescription formatting patterns, such as unanchored decimal doses (`.5 mg` / `5.0 mg`).
- **FR10 (Consistency Checks)**: System shall detect conflicting duplicate medications and missing vital sign units.
- **FR11 (Blocker Enforcement)**: System shall enforce resolution of critical blocker issues before permitting final review completion.

### Human-in-the-Loop Review Workbench
- **FR12 (Reviewer Actions)**: Reviewers shall be able to Accept (`A`), Edit (`E`), or Remove (`R`) extracted entities.
- **FR13 (Keyboard Ergonomics)**: Full review workflow shall be controllable via keyboard shortcuts without trapped focus.
- **FR14 (Visual Coordinate Highlighting)**: Selecting or hovering an entity card shall highlight the exact source text span in the note view.
- **FR15 (Local AI Proposals)**: Reviewers may optionally query a local Ollama model to generate proposal candidates and highlight discrepancies against rule extractions.
- **FR16 (Category Completeness)**: Review submission shall require affirmative verification of all entity categories.

### Immutability & Export
- **FR17 (Append-Only Event Store)**: Review mutations shall be recorded into an append-only event store.
- **FR18 (Optimistic Concurrency)**: Concurrent mutations shall be protected via `lock_version` and revision bindings.
- **FR19 (Cryptographic Audit Export)**: Reviewers shall be able to download a ZIP archive containing reviewed extractions, original extractions, item decisions, and a SHA-256 manifest.

### Offline Evaluation Lab
- **FR20 (Deterministic Benchmark)**: System shall evaluate extraction performance against 20 ground-truth reference notes using pairwise multiset matching and attribute-level precision, recall, and F1.

---

## 3. Non-Functional Requirements

- **NFR01 (Offline Execution)**: 100% of pipeline and workbench operations shall execute locally with zero external network dependencies.
- **NFR02 (Auditability)**: Every extracted entity and review decision shall be cryptographically traceable to its source document and rule version.
- **NFR03 (Concurrency Safety)**: Multiple reviewers or browser tabs shall be protected against race conditions and lost updates.
- **NFR04 (Zero Cost)**: System shall not require paid API subscriptions or metered cloud infrastructure.
- **NFR05 (Responsive UI)**: Frontend interactions shall render under 100ms with smooth transition animations and clear error states.

---

## 4. Operational Boundaries & Non-Goals

1. **Not a Medical Device**: This software is not intended for real patient care, diagnosis, clinical decision support, or treatment planning.
2. **Synthetic Data Only**: All demo notes, benchmarks, and test fixtures utilize purely synthetic, fictional clinical scenarios. No real Protected Health Information (PHI) is processed or stored.
3. **No EHR Writeback**: The application does not integrate with electronic health records (EHRs) or perform prescription ordering.
4. **Portfolio Artifact**: The platform is built to demonstrate rigorous software engineering practices, verification methodology, and defensive systems design.
