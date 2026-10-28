"""Enforce atomic idempotency on background job creation.

Revision ID: 003_job_idempotency
Revises: 002_legacy_provenance
"""
import sqlalchemy as sa
from alembic import op

revision = "003_job_idempotency"
down_revision = "002_legacy_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # Never silently discard old records to manufacture uniqueness. An
    # ambiguous preexisting collision requires explicit local reconciliation.
    duplicate = conn.execute(sa.text("""
        SELECT workspace_id, idempotency_key, COUNT(*) AS n
        FROM jobs
        WHERE idempotency_key IS NOT NULL
        GROUP BY workspace_id, idempotency_key
        HAVING COUNT(*) > 1
        LIMIT 1
    """)).first()
    if duplicate is not None:
        raise RuntimeError("Existing duplicate job idempotency keys require manual reconciliation")
    op.create_index(
        "uq_jobs_workspace_idempotency", "jobs",
        ["workspace_id", "idempotency_key"], unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_jobs_workspace_idempotency", table_name="jobs")
