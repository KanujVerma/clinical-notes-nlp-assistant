# Hosted synthetic demo: manual release gate (PR #2)

**State:** implementation for testing, NOT deployed. Production Vercel and Render
auto-deploys remain disabled. Use disposable staging PostgreSQL first.
This is a curated synthetic portfolio demonstration, not clinical software.

## Intended topology

- Vercel: static React/Vite app only; API calls must route to the verified
  Render Flask backend through a separately audited routing configuration.
- Render: Flask + gunicorn in APP_MODE=hosted_demo, no local AI process, no
  runtime DDL and no arbitrary clinical text/attachments/inference.
- PostgreSQL 15+: capability-token-hashed workspaces, bounded two-hour
  retention, 50 active hosted workspaces maximum (not a distributed rate
  limit), immutable note/review history, sanitized errors.
- Curated note files and pinned extraction/issue bundle committed in
  data/showcase/notes and data/precomputed_scenarios.json.
- No external AI API keys or real patient information.

## Before any deployment

1. Run the read-only fixture/config preflight from repo root:

       APP_MODE=hosted_demo FRONTEND_URL=http://localhost:5173 \
         ENABLE_EXTERNAL_EXPLAINER=false \
         python scripts/hosted_preflight.py

2. Create a **disposable PostgreSQL 15 database**, separate from production.
   Explicitly apply Alembic 001 -> 002 -> 003 to that disposable database.
   Do not run production DDL or point a test at the current Supabase project.
   Never display the database connection string in logs.

3. Run the migration/schema preflight against the already migrated
   disposable connection:

       APP_MODE=hosted_demo FRONTEND_URL=http://localhost:5173 \
         ENABLE_EXTERNAL_EXPLAINER=false \
         python scripts/hosted_preflight.py --check-db

   This script does SELECT-only migration/schema checks and does not execute
   Alembic upgrades.

4. Run backend/tests/test_hosted_release.py and Playwright
   frontend/e2e/hosted-real.spec.ts against an **actual hosted-mode server**.
   This test does NOT stub capabilities, workspaces, note sources, or auth.
   The repository's existing hosted-mode.spec.ts **does mock API routes**;
   passing it does not substitute for this test.
   CI workflow: .github/workflows/hosted-release-gate.yml (no deployment).

5. Confirm the following server failures in browser and raw API requests:
   cross-workspace reads/writes, arbitrary pasted text, uploads, local/paid
   AI, jobs, transcription edits, evaluations, free-text issue disposition.
   Verify workspace expiration and precomputed-data hash rejection.
   Verify successful curated seed -> review completion -> queue/history.
   Verify Cache-Control: no-store and absence of credentials in URLs.
   Do not confuse a checksum with independently verified clinical content.

6. Review production integration separately. The current Vercel repository
   configuration rewrites all paths to index.html, and the local Vite proxy
   is development-only. Before publication, configure and test the **actual
   production /api routing path** to Render, with correct CORS
   FRONTEND_URL and no browser-exposed database or provider secrets.
   Do not claim the public demo works merely because local Vite tests passed.

7. Back up the actual hosted database before any manually approved migration.
   Review deployed revision, migration plan, operational impact, privileges,
   data retention and backup restoration. The provenance backfill is
   intentionally irreversible; a schema rollback alone is not a safe undo.
   Plan application rollback plus **restoration from an encrypted backup**.
   Obtain a separate owner approval for staging promotion / production DDL.

8. Only after approval and completed smoke tests: manually deploy the
   backend, confirm /api/health/ready and origin/security rules, then
   deploy/publish the matching frontend build. Monitor 4xx/5xx, cold
   starts, memory, hosted workspace quotas, and cost. Maintain the ability
   to switch to the last known-good frontend/backend without rewriting data.

## PR #2 acceptance evidence

- Source/fixture manifest validation: all curated source bytes match exact
  SHA-256s; no orphan/missing cases, no expensive NLP in hosted seeding.
- Real PostgreSQL migration preflight and real Chrome hosted integration.
- Cross-workspace bearer token enforcement and idempotent scenario replay.
- No live paid, local or remote models in hosted public mode.
- No accidental production deploy from feature branch or main.
- Production routing, provider configuration and backup/rollback readiness
  must be separately signed off before public promotion.

## Explicit exclusions

No recorded hosted AI outputs yet (original A43 / PR #4). No real model
handwriting assessment (PR #3). No EHR, PHI, HIPAA, diagnostic or clinical
accuracy claims. These exclusions do not block local synthetic reviewer use,
but they must be disclosed in a public portfolio demonstration.
