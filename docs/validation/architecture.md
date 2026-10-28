# System Architecture & Provenance Design

## 1. High-Level Architecture Overview

The Clinical Notes NLP Assistant & Validation Workbench is engineered around **immutable provenance**, **independent verification**, and **human-in-the-loop governance**.

```
[Source Asset (PDF/Image/Text)]
            │
            ▼
    [Acquisition Run] ──► Pagewise Content-Addressed Storage (SHA-256)
            │
            ▼
      [NoteRevision] ──► Immutable Text Snapshot (Rev 1, Rev 2...)
            │
            ▼
    [Extraction Run] ──► Deterministic NLP (medSpaCy + Rules)
            │           ↳ Bound to (source_revision_id, rules_hash)
            │
    ┌───────┴───────────────────────────────┐
    ▼                                       ▼
[Quality Checks & Canaries]         [Local AI Candidate Pass]
(Regex / Span / Unit / Dose)        (Ollama glm-ocr / qwen3-vl)
    │                                       │
    └───────────────────┬───────────────────┘
                        ▼
            [Operational Issues Engine]
            (Severity, Life-cycle, Blocker rules)
                        │
                        ▼
            [Human Review Workbench]
            (Accept, Edit, Remove, Keyboard shortcuts)
                        │
                        ▼
               [ReviewEvent Store]
            (Immutable Append-Only Log)
            • Optimistic Concurrency (lock_version)
            • Idempotency Deduplication Key
            • Cryptographic Request Hash
            • Server-Derived Disposition
                        │
            ┌───────────┴───────────┐
            ▼                       ▼
    [Audit Export ZIP]      [Strict Evaluator]
    • Reviewed JSON         • Pairwise Multiset Alignment
    • Decisions & Diffs     • Unit / Attribute Strictness
    • SHA-256 Manifest      • Zero-Support N/A Handling
    • Standalone HTML       • Immutable Artifact Bundle
```

---

## 2. Provenance & Immutability Rules

### 2.1 Content-Addressed Document Storage
- Uploaded assets (PDF, images, raw text) are stored in `.storage/assets/<sha256>`.
- Files are verified prior to ingestion. The cryptographic digest guarantees tamper-evidence and deduplication across sessions.

### 2.2 NoteRevision Chain
- A `Note` record acts as a pointer to the active `current_source_revision_id`.
- Any modification to transcription text generates an incremented, immutable `NoteRevision`.
- Prior extractions remain bound to their historical revision and cannot be silently overwritten.

### 2.3 Cryptographic Review Events
- Every human review mutation is recorded as a `ReviewEvent`.
- `ReviewEvent` records are append-only.
- The server checks:
  1. `parent_event_id`: Ensures linearized review history.
  2. `lock_version`: Atomic conditional update on the `Note` record prevents lost updates from concurrent reviewer tabs.
  3. `idempotency_key`: Unique constraint per workspace guarantees safe retries across network disconnects.
  4. `server_derived_outcome`: Review outcome (`reviewed_unchanged` vs `reviewed_corrected`) is derived algorithmically on the server, never accepted blindly from client claims.

---

## 3. Independent Quality Checks & Canaries

To protect against extraction anomalies before human signoff, pure validation functions execute independently of the extraction model:

1. **A08: Evidence Span Quote Integrity**: Validates `note_text[start:end] == quote`. Half-open intervals ensure exact character coordinate bounding.
2. **A09: Dose Format Canary**: Identifies unanchored decimal doses (e.g. `.5 mg` or `5.0 mg`), which represent known high-risk prescription error patterns.
3. **A02: Medication Conflict Canary**: Flags contradictory extractions for the same medication name with conflicting routes or dosages.
4. **A03: Vital Unit Canary**: Enforces canonical units of measurement (e.g. `mmHg`, `bpm`, `F`, `%`).
5. **A04: Instruction Contradiction**: Flags contradictory follow-up directives within the same clinical episode.

---

## 4. Strict Evaluator & Benchmark Engine

The benchmark engine implements strict statistical evaluation against 20 synthetic reference notes:

- **Multiset Pairwise Alignment**: Solves the maximum-weight bipartite matching problem (Hungarian algorithm) to match predicted medications to ground-truth entities. This eliminates distortion caused by dictionary collapsing or greedy name matching.
- **Attribute Strictness**: Medications are evaluated across individual attributes (`name`, `dose`, `route`, `frequency`, `duration`, `qualifier`). Partial attribute errors are penalized.
- **Zero-Support Handling**: In accordance with Rule A06, when support and predictions are zero, metrics evaluate to `N/A` rather than artificial `1.0` or `0.0`.
- **Immutable Run Bundles**: Every benchmark run generates an export directory containing `run_metadata.json`, `summary_metrics.json`, `case_results.json`, and `manifest.json`.

---

## 5. Security & Isolation Boundaries

- **Synthetic Only**: The platform is restricted to synthetic, de-identified clinical notes. No protected health information (PHI) is processed.
- **Workspace Isolation**: Workspaces are partitioned by UUID and authenticated via SHA-256 hashed capability tokens (`X-Session-ID`). Data in one workspace is strictly invisible to other reviewers.
- **Offline Self-Sufficiency**: The entire application (Flask, SQLite/PostgreSQL, React, spaCy, medSpaCy, PyMuPDF, Tesseract, Ollama adapter) runs 100% locally with zero external network calls.
