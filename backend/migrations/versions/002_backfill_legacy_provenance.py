"""Import legacy note provenance without treating legacy validations as current.

Revision ID: 002_legacy_provenance
Revises: 001_prov_workbench

Original single-row Validations have no source-revision binding. Preserve them
and all original timestamps, but mark their status legacy_unverified. Existing
extraction payloads are preserved, not rewritten or silently approved.
"""
import hashlib
import uuid

import sqlalchemy as sa
from alembic import op

revision = "002_legacy_provenance"
down_revision = "001_prov_workbench"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    notes = connection.execute(sa.text("""
        SELECT id, raw_text, session_id, workspace_id,
               current_source_revision_id, current_extraction_id,
               review_head_event_id
        FROM notes ORDER BY id
    """)).mappings().all()

    for note in notes:
        note_id = note["id"]
        if note["current_source_revision_id"] is not None:
            # This may be a genuine later revision. Do not infer its age
            # or overwrite any existing source/extraction pointer.
            continue

        text = note["raw_text"] or ""
        source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        workspace_id = (
            note["workspace_id"]
            or note["session_id"]
            or f"legacy-unverified-{note_id}"
        )
        revision_id = str(uuid.uuid4())

        connection.execute(sa.text("""
            INSERT INTO note_revisions (
                id, note_id, workspace_id, revision_number, raw_text,
                normalized_text, sha256, creation_reason
            ) VALUES (
                :revision_id, :note_id, :workspace_id, 1, :source,
                :source, :hash, 'legacy_import_unverified'
            )
        """), {
            "revision_id": revision_id,
            "note_id": note_id,
            "workspace_id": workspace_id,
            "source": text,
            "hash": source_hash,
        })

        legacy_extraction = connection.execute(sa.text("""
            SELECT id, public_id FROM extractions
            WHERE note_id = :note_id
            ORDER BY extracted_at DESC, id DESC LIMIT 1
        """), {"note_id": note_id}).mappings().first()

        extraction_public_id = None
        if legacy_extraction is not None:
            extraction_public_id = legacy_extraction["public_id"] or str(uuid.uuid4())
            # Preserve the original extraction body, timestamps, and its
            # source binding as recorded. A legacy source relationship
            # cannot be promoted to verified provenance retroactively.
            connection.execute(sa.text("""
                UPDATE extractions SET
                    public_id = :public_id,
                    workspace_id = COALESCE(workspace_id, :workspace_id),
                    status = 'legacy_unverified'
                WHERE id = :id
            """), {
                "public_id": extraction_public_id,
                "workspace_id": workspace_id,
                "id": legacy_extraction["id"],
            })

        has_validation = connection.execute(sa.text("""
            SELECT id FROM validations WHERE note_id = :note_id LIMIT 1
        """), {"note_id": note_id}).first() is not None
        new_status = "legacy_unverified" if has_validation or legacy_extraction else "needs_review"

        connection.execute(sa.text("""
            UPDATE notes SET
                workspace_id = :workspace_id,
                current_source_revision_id = :revision_id,
                current_extraction_id = :extraction_public_id,
                review_head_event_id = NULL,
                lock_version = COALESCE(lock_version, 0),
                status = :status
            WHERE id = :note_id AND current_source_revision_id IS NULL
        """), {
            "workspace_id": workspace_id,
            "revision_id": revision_id,
            "extraction_public_id": extraction_public_id,
            "status": new_status,
            "note_id": note_id,
        })


def downgrade() -> None:
    raise RuntimeError("Provenance backfill is intentionally irreversible; do not delete source history")
