import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
_boot_log = logging.getLogger("boot")
_boot_log.info("app.py loading")

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from config import Config
from utils.db import get_engine, init_db, get_session


def create_app(test_config: dict | None = None) -> Flask:
    _boot_log.info("create_app() called")
    app = Flask(__name__, static_folder="static", static_url_path="")

    # CORS: allow all origins locally; restrict to FRONTEND_URL in production.
    allowed_origins = Config.FRONTEND_URL if Config.FRONTEND_URL else "*"
    CORS(app, origins=allowed_origins)

    # Config
    app.config["DATABASE_URL"] = Config.DATABASE_URL
    app.config["PIPELINE_VERSION"] = Config.PIPELINE_VERSION
    if test_config:
        app.config.update(test_config)

    # Hosted mode never silently enables paid providers or arbitrary origins.
    # Explicit, reviewed configuration is required before a manual rollout.
    if Config.APP_MODE == "hosted_demo":
        if Config.ENABLE_EXTERNAL_EXPLAINER:
            raise RuntimeError("Hosted sandbox must disable external AI")
        if not Config.FRONTEND_URL and not app.config.get("TESTING"):
            raise RuntimeError("Hosted sandbox requires an explicit FRONTEND_URL")

    @app.after_request
    def apply_hosted_headers(response):
        from flask import request
        if Config.APP_MODE == "hosted_demo" and request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, private"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    # DB
    engine = get_engine(app.config["DATABASE_URL"])
    # Only disposable SQLite/local or test databases are auto-migrated. Hosted
    # and PostgreSQL schemas require an explicit, preapproved migration gate.
    allow_local_migration = bool(app.config.get("TESTING")) or (
        Config.APP_MODE == "local" and engine.dialect.name == "sqlite"
    )
    try:
        init_db(engine, migrate=allow_local_migration)
    except Exception:
        # Do not start serving requests or leak database exception strings
        # when an audited migration/schema check did not complete.
        _boot_log.error("Database migration or schema readiness gate failed")
        raise RuntimeError("Database schema not ready; complete the migration gate before startup") from None
    app.config["ENGINE"] = engine

    @app.before_request
    def open_session():
        from flask import g, request
        g.db = get_session(engine)
        g.session_id = request.headers.get("X-Session-ID", "").strip()

    @app.teardown_request
    def close_session(exc):
        from flask import g
        db = g.pop("db", None)
        if db:
            db.close()

    # Health
    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "pipeline_version": app.config["PIPELINE_VERSION"]})

    @app.route("/api/health/live")
    def health_live():
        return jsonify({"status": "live", "pipeline_version": app.config["PIPELINE_VERSION"]}), 200

    @app.route("/api/health/ready")
    def health_ready():
        try:
            from sqlalchemy import text, inspect
            required = {"notes", "extractions", "note_revisions", "review_events", "workspaces"}
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                available = set(inspect(conn).get_table_names())
                if not required.issubset(available):
                    return jsonify({
                        "status": "not_ready", "code": "SCHEMA_NOT_READY",
                    }), 503
                if Config.APP_MODE == "hosted_demo":
                    # Do not promote a public backend that only ran create_all
                    # and never applied the audited versioned migration.
                    if "alembic_version" not in available:
                        return jsonify({
                            "status": "not_ready", "code": "MIGRATION_NOT_APPLIED",
                        }), 503
            return jsonify({"status": "ready", "database": "connected"}), 200
        except Exception:
            # Database drivers may include sensitive connection details in
            # exception messages. Keep readiness errors source-free.
            _boot_log.exception("Readiness probe failed")
            return jsonify({"status": "not_ready", "code": "DATABASE_UNAVAILABLE"}), 503

    # Blueprints
    from routes.extract import bp as extract_bp
    from routes.notes import bp as notes_bp
    from routes.upload import bp as upload_bp
    from routes.validate import bp as validate_bp
    from routes.history import bp as history_bp
    from routes.metrics import bp as metrics_bp
    from routes.seed import bp as seed_bp
    from routes.queue import bp as queue_bp
    from routes.reset import bp as reset_bp
    from routes.explain import bp as explain_bp
    from routes.workspaces import bp as workspaces_bp
    from routes.revisions import bp as revisions_bp
    from routes.reviews import bp as reviews_bp
    from routes.issues import bp as issues_bp
    from routes.ai_candidates import bp as ai_candidates_bp
    from routes.jobs import bp as jobs_bp
    from routes.eval_runs import bp as eval_runs_bp
    from routes.export import bp as export_bp

    app.register_blueprint(extract_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(validate_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(metrics_bp)
    app.register_blueprint(seed_bp)
    app.register_blueprint(queue_bp)
    app.register_blueprint(reset_bp)
    app.register_blueprint(explain_bp)
    app.register_blueprint(workspaces_bp)
    app.register_blueprint(revisions_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(issues_bp)
    app.register_blueprint(ai_candidates_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(eval_runs_bp)
    app.register_blueprint(export_bp)

    _boot_log.info("blueprints registered")

    # SPA catch-all (production)
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_spa(path):
        static = app.static_folder
        if static and path and os.path.exists(os.path.join(static, path)):
            return send_from_directory(static, path)
        if static and os.path.exists(os.path.join(static, "index.html")):
            return send_from_directory(static, "index.html")
        return jsonify({"error": "Not found"}), 404

    return app


if __name__ == "__main__":
    create_app().run(debug=True, port=5000)
