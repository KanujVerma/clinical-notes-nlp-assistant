"""Read-only hosted release gate. Does not deploy, migrate or print credentials.

Usage:
    APP_MODE=hosted_demo FRONTEND_URL=https://example.vercel.app \
      python scripts/hosted_preflight.py
    # Only with an already migrated, approved staging/disposable database:
    python scripts/hosted_preflight.py --check-db

For test-only disposable SQLite add --allow-disposable-sqlite. No flag
authorizes production database migrations; this script executes SELECTs only.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from config import Config  # noqa: E402
from services.hosted_release import HostedFixtureError, verified_scenarios  # noqa: E402


def preflight(check_db: bool = False, allow_disposable_sqlite: bool = False) -> dict:
    if Config.APP_MODE != "hosted_demo":
        raise RuntimeError("HOSTED_MODE_REQUIRED")
    if Config.ENABLE_EXTERNAL_EXPLAINER:
        raise RuntimeError("PAID_PROVIDER_MUST_BE_DISABLED")
    if not Config.FRONTEND_URL or not Config.FRONTEND_URL.startswith(("http://", "https://")):
        raise RuntimeError("EXPLICIT_FRONTEND_ORIGIN_REQUIRED")

    # These repository settings are *deployment freeze controls*. This script
    # intentionally does not remove them or trigger provider deployments.
    vercel = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    if vercel.get("git", {}).get("deploymentEnabled", {}).get("main") is not False:
        raise RuntimeError("PRODUCTION_VERCEL_DEPLOYMENT_NOT_FROZEN")
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    if "autoDeployTrigger: 'off'" not in render:
        raise RuntimeError("RENDER_AUTODEPLOY_NOT_FROZEN")

    cases = verified_scenarios(Config.DATA_DIR)
    result = {
        "status": "preflight_ok",
        "mode": "hosted_demo",
        "curated_cases": len(cases),
        "paid_ai_enabled": False,
        "production_deployments_frozen": True,
        "schema_check": "not_requested",
    }
    if check_db:
        from utils.db import get_engine, init_db
        if not Config.DATABASE_URL.startswith("postgresql"):
            if not allow_disposable_sqlite or not Config.DATABASE_URL.startswith("sqlite"):
                raise RuntimeError("DATABASE_MUST_BE_STAGING_POSTGRESQL")
        engine = get_engine(Config.DATABASE_URL)
        try:
            init_db(engine, migrate=False)  # read-only current Alembic head verification
        finally:
            engine.dispose()
        result["schema_check"] = "verified_existing_head"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-db", action="store_true")
    parser.add_argument("--allow-disposable-sqlite", action="store_true")
    args = parser.parse_args()
    try:
        result = preflight(args.check_db, args.allow_disposable_sqlite)
    except (RuntimeError, HostedFixtureError, ValueError, OSError) as exc:
        # Only emit public static error codes; never print DB URLs/credentials.
        code = exc.code if isinstance(exc, HostedFixtureError) else (
            str(exc) if str(exc).isupper() and "_" in str(exc) else "PREFLIGHT_FAILED"
        )
        print(json.dumps({"status": "blocked", "code": code}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
