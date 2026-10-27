"""001_provenance_and_validation_workbench

Revision ID: 001_prov_workbench
Revises: 
Create Date: 2026-10-27

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = '001_prov_workbench'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()

    # 1. workspaces
    if "workspaces" not in tables:
        op.create_table(
            "workspaces",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("capability_token_hash", sa.String(64), nullable=True),
            sa.Column("mode", sa.String(32), nullable=False, server_default="normal"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("last_activity_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("state", sa.String(32), nullable=False, server_default="active"),
            sa.Column("schema_version", sa.String(32), nullable=False, server_default="1.0.0"),
        )
        op.create_index("ix_workspaces_token_hash", "workspaces", ["capability_token_hash"])

    # 2. source_assets
    if "source_assets" not in tables:
        op.create_table(
            "source_assets",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("workspace_id", sa.String(36), nullable=False),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column("storage_key", sa.String(255), nullable=False),
            sa.Column("mime_type", sa.String(100), nullable=False),
            sa.Column("byte_size", sa.Integer(), nullable=False),
            sa.Column("original_filename", sa.String(255), nullable=True),
            sa.Column("page_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("acquisition_kind", sa.String(50), nullable=False, server_default="upload"),
            sa.Column("schema_version", sa.String(32), nullable=False, server_default="1.0.0"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_source_assets_workspace_id", "source_assets", ["workspace_id"])
        op.create_index("ix_source_assets_sha256", "source_assets", ["sha256"])

    # 3. acquisition_runs
    if "acquisition_runs" not in tables:
        op.create_table(
            "acquisition_runs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("source_asset_id", sa.String(36), sa.ForeignKey("source_assets.id"), nullable=True),
            sa.Column("engine", sa.String(50), nullable=False, server_default="pymupdf_tesseract"),
            sa.Column("engine_version", sa.String(50), nullable=True),
            sa.Column("config_hash", sa.String(64), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="completed"),
            sa.Column("page_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("pages_json", sa.Text(), nullable=True),
            sa.Column("canonical_text", sa.Text(), nullable=True),
            sa.Column("warnings_json", sa.Text(), nullable=True),
            sa.Column("error_code", sa.String(50), nullable=True),
            sa.Column("started_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )

    # 4. note_revisions
    if "note_revisions" not in tables:
        op.create_table(
            "note_revisions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("note_id", sa.Integer(), sa.ForeignKey("notes.id"), nullable=False),
            sa.Column("workspace_id", sa.String(36), nullable=False),
            sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("parent_revision_id", sa.String(36), sa.ForeignKey("note_revisions.id"), nullable=True),
            sa.Column("source_asset_id", sa.String(36), sa.ForeignKey("source_assets.id"), nullable=True),
            sa.Column("acquisition_run_id", sa.String(36), sa.ForeignKey("acquisition_runs.id"), nullable=True),
            sa.Column("raw_text", sa.Text(), nullable=False),
            sa.Column("normalized_text", sa.Text(), nullable=False),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column("normalization_version", sa.String(32), nullable=False, server_default="1.0.0"),
            sa.Column("offset_map_json", sa.Text(), nullable=True),
            sa.Column("pages_json", sa.Text(), nullable=True),
            sa.Column("creation_reason", sa.String(50), nullable=False, server_default="acquisition"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_note_revisions_note_id", "note_revisions", ["note_id"])
        op.create_index("ix_note_revisions_workspace_id", "note_revisions", ["workspace_id"])
        op.create_index("ix_note_revisions_sha256", "note_revisions", ["sha256"])

    # 5. review_events
    if "review_events" not in tables:
        op.create_table(
            "review_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("workspace_id", sa.String(36), nullable=False),
            sa.Column("note_id", sa.Integer(), sa.ForeignKey("notes.id"), nullable=False),
            sa.Column("source_revision_id", sa.String(36), nullable=False),
            sa.Column("extraction_id", sa.String(36), nullable=False),
            sa.Column("source_hash", sa.String(64), nullable=False),
            sa.Column("parent_event_id", sa.String(36), sa.ForeignKey("review_events.id"), nullable=True),
            sa.Column("event_kind", sa.String(32), nullable=False),
            sa.Column("reviewed_snapshot_json", sa.Text(), nullable=False),
            sa.Column("item_decisions_json", sa.Text(), nullable=False),
            sa.Column("category_acknowledgments_json", sa.Text(), nullable=False),
            sa.Column("issue_dispositions_json", sa.Text(), nullable=True),
            sa.Column("correction_diff_json", sa.Text(), nullable=True),
            sa.Column("diff_algorithm_version", sa.String(32), nullable=False, server_default="1.0.0"),
            sa.Column("derived_outcome", sa.String(32), nullable=False),
            sa.Column("idempotency_key", sa.String(128), nullable=True),
            sa.Column("request_hash", sa.String(64), nullable=True),
            sa.Column("expected_lock_version", sa.Integer(), nullable=True),
            sa.Column("review_duration_ms", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("workspace_id", "idempotency_key", name="uq_workspace_idempotency"),
        )
        op.create_index("ix_review_events_workspace_id", "review_events", ["workspace_id"])
        op.create_index("ix_review_events_note_id", "review_events", ["note_id"])
        op.create_index("ix_review_events_idempotency_key", "review_events", ["idempotency_key"])

    # 6. operational_issues
    if "operational_issues" not in tables:
        op.create_table(
            "operational_issues",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("workspace_id", sa.String(36), nullable=False),
            sa.Column("note_id", sa.Integer(), sa.ForeignKey("notes.id"), nullable=False),
            sa.Column("source_revision_id", sa.String(36), nullable=False),
            sa.Column("extraction_id", sa.String(36), nullable=True),
            sa.Column("issue_code", sa.String(64), nullable=False),
            sa.Column("severity", sa.String(32), nullable=False),
            sa.Column("category", sa.String(50), nullable=False),
            sa.Column("item_id", sa.String(64), nullable=True),
            sa.Column("field_path", sa.String(100), nullable=True),
            sa.Column("evidence_span_json", sa.Text(), nullable=True),
            sa.Column("safe_explanation", sa.Text(), nullable=False),
            sa.Column("check_policy_version", sa.String(32), nullable=False, server_default="1.0.0"),
            sa.Column("status", sa.String(32), nullable=False, server_default="open"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_operational_issues_workspace_id", "operational_issues", ["workspace_id"])
        op.create_index("ix_operational_issues_note_id", "operational_issues", ["note_id"])
        op.create_index("ix_operational_issues_issue_code", "operational_issues", ["issue_code"])

    # 7. issue_events
    if "issue_events" not in tables:
        op.create_table(
            "issue_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("issue_id", sa.String(36), sa.ForeignKey("operational_issues.id"), nullable=False),
            sa.Column("action", sa.String(32), nullable=False),
            sa.Column("actor", sa.String(64), nullable=False, server_default="reviewer"),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("bound_review_event_id", sa.String(36), sa.ForeignKey("review_events.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_issue_events_issue_id", "issue_events", ["issue_id"])

    # 8. inference_runs
    if "inference_runs" not in tables:
        op.create_table(
            "inference_runs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("workspace_id", sa.String(36), nullable=False),
            sa.Column("note_id", sa.Integer(), sa.ForeignKey("notes.id"), nullable=False),
            sa.Column("source_revision_id", sa.String(36), nullable=False),
            sa.Column("task_type", sa.String(50), nullable=False),
            sa.Column("model_name", sa.String(100), nullable=False),
            sa.Column("model_digest", sa.String(128), nullable=True),
            sa.Column("prompt_template_hash", sa.String(64), nullable=True),
            sa.Column("config_hash", sa.String(64), nullable=True),
            sa.Column("input_hash", sa.String(64), nullable=True),
            sa.Column("raw_candidate_json", sa.Text(), nullable=True),
            sa.Column("parsed_candidate_json", sa.Text(), nullable=True),
            sa.Column("alignment_results_json", sa.Text(), nullable=True),
            sa.Column("discrepancies_json", sa.Text(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="completed"),
            sa.Column("error_code", sa.String(50), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_inference_runs_workspace_id", "inference_runs", ["workspace_id"])
        op.create_index("ix_inference_runs_note_id", "inference_runs", ["note_id"])

    # 9. jobs
    if "jobs" not in tables:
        op.create_table(
            "jobs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("workspace_id", sa.String(36), nullable=False),
            sa.Column("kind", sa.String(50), nullable=False),
            sa.Column("note_id", sa.Integer(), nullable=True),
            sa.Column("source_revision_id", sa.String(36), nullable=True),
            sa.Column("idempotency_key", sa.String(128), nullable=True),
            sa.Column("request_hash", sa.String(64), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
            sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("lease_owner", sa.String(64), nullable=True),
            sa.Column("lease_expiry", sa.DateTime(), nullable=True),
            sa.Column("progress", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("payload_json", sa.Text(), nullable=True),
            sa.Column("result_json", sa.Text(), nullable=True),
            sa.Column("error_code", sa.String(50), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_jobs_workspace_id", "jobs", ["workspace_id"])
        op.create_index("ix_jobs_status", "jobs", ["status"])

    # 10. Update notes columns if not present
    note_cols = [c["name"] for c in inspector.get_columns("notes")] if "notes" in tables else []
    if "workspace_id" not in note_cols:
        op.add_column("notes", sa.Column("workspace_id", sa.String(36), nullable=True))
        op.create_index("ix_notes_workspace_id", "notes", ["workspace_id"])
    if "current_source_revision_id" not in note_cols:
        op.add_column("notes", sa.Column("current_source_revision_id", sa.String(36), nullable=True))
    if "current_extraction_id" not in note_cols:
        op.add_column("notes", sa.Column("current_extraction_id", sa.String(36), nullable=True))
    if "review_head_event_id" not in note_cols:
        op.add_column("notes", sa.Column("review_head_event_id", sa.String(36), nullable=True))
    if "lock_version" not in note_cols:
        op.add_column("notes", sa.Column("lock_version", sa.Integer(), nullable=False, server_default="0"))
    if "status" not in note_cols:
        op.add_column("notes", sa.Column("status", sa.String(32), nullable=False, server_default="needs_review"))
    if "updated_at" not in note_cols:
        op.add_column("notes", sa.Column("updated_at", sa.DateTime(), nullable=True))

    # 11. Update extractions columns if not present
    ext_cols = [c["name"] for c in inspector.get_columns("extractions")] if "extractions" in tables else []
    if "public_id" not in ext_cols:
        op.add_column("extractions", sa.Column("public_id", sa.String(36), nullable=True))
        op.create_index("ix_extractions_public_id", "extractions", ["public_id"])
    if "workspace_id" not in ext_cols:
        op.add_column("extractions", sa.Column("workspace_id", sa.String(36), nullable=True))
        op.create_index("ix_extractions_workspace_id", "extractions", ["workspace_id"])
    if "source_revision_id" not in ext_cols:
        op.add_column("extractions", sa.Column("source_revision_id", sa.String(36), nullable=True))
    if "source_text_hash" not in ext_cols:
        op.add_column("extractions", sa.Column("source_text_hash", sa.String(64), nullable=True))
    if "rules_hash" not in ext_cols:
        op.add_column("extractions", sa.Column("rules_hash", sa.String(64), nullable=True))
    if "vocabulary_hash" not in ext_cols:
        op.add_column("extractions", sa.Column("vocabulary_hash", sa.String(64), nullable=True))
    if "schema_version" not in ext_cols:
        op.add_column("extractions", sa.Column("schema_version", sa.String(32), nullable=False, server_default="2.0.0"))
    if "status" not in ext_cols:
        op.add_column("extractions", sa.Column("status", sa.String(32), nullable=False, server_default="completed"))
    if "check_policy_version" not in ext_cols:
        op.add_column("extractions", sa.Column("check_policy_version", sa.String(32), nullable=False, server_default="1.0.0"))
    if "error_metadata_json" not in ext_cols:
        op.add_column("extractions", sa.Column("error_metadata_json", sa.Text(), nullable=True))


def downgrade() -> None:
    pass
