"""Flask web server for blackbox log retrieval.

Routes:
  GET  /                          Main UI page
  GET  /sessions                  JSON: all sessions
  GET  /download/<session_id>/raw_flash.bbl
  GET  /download/<session_id>/manifest.json
  GET  /status                    JSON: current sync status
  DELETE /sessions/<session_id>   Delete a session from Pi
  GET  /generate_204              Android captive portal probe
  GET  /hotspot-detect.html       iOS/macOS captive portal probe
  GET  /connecttest.txt           Windows captive portal probe
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template, request, send_file

from bbsyncer.storage.manifest import list_sessions
from bbsyncer.sync.orchestrator import get_status
from bbsyncer.util.disk_space import used_and_free_gb

log = logging.getLogger(__name__)


def create_app(storage_path: str = "/mnt/bbsyncer-logs") -> Flask:
    template_dir = Path(__file__).parent / "templates"
    app = Flask(__name__, template_folder=str(template_dir))
    app.config["STORAGE_PATH"] = storage_path

    # ------------------------------------------------------------------ #
    # Captive portal endpoints (iOS, Android, Windows, macOS)             #
    # ------------------------------------------------------------------ #

    @app.route("/generate_204")       # Android
    @app.route("/gen_204")
    def android_captive() -> Response:
        return Response(_captive_html(), status=200, mimetype="text/html")

    @app.route("/hotspot-detect.html")  # iOS / macOS
    @app.route("/library/test/success.html")
    def ios_captive() -> Response:
        return Response(_captive_html(), status=200, mimetype="text/html")

    @app.route("/connecttest.txt")    # Windows
    def windows_captive() -> Response:
        return Response(_captive_html(), status=200, mimetype="text/html")

    @app.route("/ncsi.txt")           # Windows NCSI
    def windows_ncsi() -> Response:
        return Response(_captive_html(), status=200, mimetype="text/html")

    # ------------------------------------------------------------------ #
    # Main UI                                                             #
    # ------------------------------------------------------------------ #

    @app.route("/")
    def index() -> str:
        storage = Path(app.config["STORAGE_PATH"])
        sessions = list_sessions(storage) if storage.exists() else []
        try:
            used_gb, free_gb = used_and_free_gb(storage)
        except OSError:
            used_gb, free_gb = 0.0, 0.0
        status = get_status()
        return render_template(
            "index.html",
            sessions=sessions,
            used_gb=used_gb,
            free_gb=free_gb,
            status=status,
        )

    # ------------------------------------------------------------------ #
    # JSON API                                                            #
    # ------------------------------------------------------------------ #

    @app.route("/sessions")
    def api_sessions() -> Response:
        storage = Path(app.config["STORAGE_PATH"])
        sessions = list_sessions(storage) if storage.exists() else []
        return jsonify(sessions)

    @app.route("/status")
    def api_status() -> Response:
        return jsonify(get_status())

    # ------------------------------------------------------------------ #
    # File download                                                       #
    # ------------------------------------------------------------------ #

    @app.route("/download/<path:session_id>/raw_flash.bbl")
    def download_bbl(session_id: str) -> Response:
        storage = Path(app.config["STORAGE_PATH"])
        path = _resolve_session_file(storage, session_id, "raw_flash.bbl")
        return send_file(path, as_attachment=True, download_name="raw_flash.bbl")

    @app.route("/download/<path:session_id>/manifest.json")
    def download_manifest(session_id: str) -> Response:
        storage = Path(app.config["STORAGE_PATH"])
        path = _resolve_session_file(storage, session_id, "manifest.json")
        return send_file(path, as_attachment=True, download_name="manifest.json")

    # ------------------------------------------------------------------ #
    # Session deletion                                                    #
    # ------------------------------------------------------------------ #

    @app.route("/sessions/<path:session_id>", methods=["DELETE"])
    def delete_session(session_id: str) -> Response:
        storage = Path(app.config["STORAGE_PATH"])
        session_path = _resolve_session_path(storage, session_id)
        if not session_path.exists():
            abort(404)
        import shutil
        shutil.rmtree(session_path)
        log.info("Deleted session: %s", session_path)
        return jsonify({"deleted": True, "session_id": session_id})

    return app


def _resolve_session_path(storage: Path, session_id: str) -> Path:
    """Safely resolve a session_id like 'fc_BTFL_uid-abc/2026-02-26_143012'."""
    # Security: prevent path traversal
    try:
        parts = session_id.split("/")
        if len(parts) != 2:
            abort(400)
        fc_dir, session_dir = parts
        # Reject any '..' components
        if ".." in fc_dir or ".." in session_dir:
            abort(400)
        path = storage / fc_dir / session_dir
        path.resolve().relative_to(storage.resolve())  # raises if outside
        return path
    except Exception:
        abort(400)


def _resolve_session_file(storage: Path, session_id: str, filename: str) -> Path:
    session_path = _resolve_session_path(storage, session_id)
    file_path = session_path / filename
    if not file_path.exists():
        abort(404)
    return file_path


def _captive_html() -> str:
    """Minimal HTML that redirects to the main page (captive portal response)."""
    return (
        '<!DOCTYPE html><html><head>'
        '<meta http-equiv="refresh" content="0; url=/">'
        '<title>Betaflight Blackbox Syncer</title>'
        '</head><body>'
        '<p>Redirecting to <a href="/">Blackbox Syncer</a>...</p>'
        '</body></html>'
    )


def run_server(storage_path: str = "/mnt/bbsyncer-logs", port: int = 80) -> None:
    """Start the Flask development server (production: use gunicorn or waitress)."""
    app = create_app(storage_path)
    log.info("Starting web server on 0.0.0.0:%d", port)
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
