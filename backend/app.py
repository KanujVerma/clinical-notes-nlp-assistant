import os
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from config import Config
from utils.db import get_engine, init_db, get_session


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="")

    # CORS: allow all origins locally; restrict to FRONTEND_URL in production.
    allowed_origins = Config.FRONTEND_URL if Config.FRONTEND_URL else "*"
    CORS(app, origins=allowed_origins)

    # Config
    app.config["DATABASE_URL"] = Config.DATABASE_URL
    app.config["PIPELINE_VERSION"] = Config.PIPELINE_VERSION
    if test_config:
        app.config.update(test_config)

    # DB
    engine = get_engine(app.config["DATABASE_URL"])
    try:
        init_db(engine)
    except Exception as exc:
        import logging
        logging.warning("DB init failed on startup (will retry per-request): %s", exc)
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
