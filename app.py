#!/usr/bin/env python3
"""Idle Fantasy Save Viewer – Flask server with per-viewer secret URLs."""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from pathlib import Path

from flask import Blueprint, Flask, abort, jsonify, render_template, request
from werkzeug.utils import secure_filename

from db import (
    DEFAULT_DB,
    diff_snapshots,
    get_latest_snapshot,
    get_snapshot,
    import_save,
    init_db,
    inventory_timeline,
    list_snapshots,
    get_connection,
    timeline,
)
from security import (
    IMPORT_LIMIT,
    VIEWER_CREATE_LIMIT,
    configure_app,
    external_base_url,
    limiter,
    local_viewer_disabled,
)
from viewers import (
    LOCAL_VIEWER_ID,
    create_viewer,
    ensure_local_viewer,
    is_valid_viewer_id,
    viewer_db_path,
)

app = Flask(__name__)
configure_app(app)

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent / "data"))
DB_PATH = DEFAULT_DB


def get_data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", Path(__file__).parent / "data"))


def _viewer_url(viewer_id: str) -> str:
    return f"{external_base_url()}/v/{viewer_id}/"


def _resolve_viewer_db(viewer_id: str) -> Path:
    if viewer_id == LOCAL_VIEWER_ID and local_viewer_disabled():
        abort(404)
    if not is_valid_viewer_id(viewer_id):
        abort(404)
    db_path = viewer_db_path(viewer_id, get_data_dir())
    if not db_path.exists():
        abort(404)
    return db_path


viewer_bp = Blueprint("viewer", __name__, url_prefix="/v/<viewer_id>")


@viewer_bp.route("/")
def viewer_index(viewer_id: str):
    _resolve_viewer_db(viewer_id)
    return render_template("index.html", viewer_id=viewer_id)


@viewer_bp.route("/api/snapshot/latest")
def api_latest(viewer_id: str):
    db_path = _resolve_viewer_db(viewer_id)
    data = get_latest_snapshot(db_path=db_path)
    if not data:
        return jsonify({"error": "No snapshots imported yet"}), 404
    return jsonify(data)


@viewer_bp.route("/api/snapshot/<int:snapshot_id>")
def api_snapshot(viewer_id: str, snapshot_id: int):
    db_path = _resolve_viewer_db(viewer_id)
    data = get_snapshot(snapshot_id, db_path=db_path)
    if not data:
        return jsonify({"error": "Snapshot not found"}), 404
    return jsonify(data)


@viewer_bp.route("/api/snapshots")
def api_snapshots(viewer_id: str):
    db_path = _resolve_viewer_db(viewer_id)
    return jsonify(list_snapshots(db_path=db_path))


@viewer_bp.route("/api/snapshots/<int:older_id>/diff/<int:newer_id>")
def api_diff(viewer_id: str, older_id: int, newer_id: int):
    db_path = _resolve_viewer_db(viewer_id)
    try:
        return jsonify(diff_snapshots(older_id, newer_id, db_path=db_path))
    except ValueError:
        return jsonify({"error": "Snapshot not found"}), 404


@viewer_bp.route("/api/timeline")
def api_timeline(viewer_id: str):
    db_path = _resolve_viewer_db(viewer_id)
    return jsonify(timeline(db_path=db_path))


@viewer_bp.route("/api/inventory/timeline")
def api_inventory_timeline(viewer_id: str):
    db_path = _resolve_viewer_db(viewer_id)
    return jsonify(inventory_timeline(db_path=db_path))


@viewer_bp.route("/api/import", methods=["POST"])
@limiter.limit(IMPORT_LIMIT)
def api_import(viewer_id: str):
    db_path = _resolve_viewer_db(viewer_id)

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "No file selected"}), 400

    upload_dir = get_data_dir() / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = secure_filename(f.filename) or "upload.json"
    if not safe_name.lower().endswith(".json"):
        return jsonify({"error": "Only .json files are accepted"}), 400

    tmp = upload_dir / f"_upload_{viewer_id}_{safe_name}"
    f.save(tmp)
    try:
        result = import_save(tmp, db_path=db_path)
    finally:
        tmp.unlink(missing_ok=True)
    if result.get("error"):
        return jsonify(result), 422
    return jsonify(result)


app.register_blueprint(viewer_bp)


@app.route("/")
def landing():
    return render_template("landing.html")


@app.post("/api/viewers")
@limiter.limit(VIEWER_CREATE_LIMIT)
def api_create_viewer():
    viewer_id = create_viewer(get_data_dir())
    return jsonify({
        "viewer_id": viewer_id,
        "url": _viewer_url(viewer_id),
    }), 201


@app.errorhandler(413)
def request_too_large(_exc):
    return jsonify({"error": "Upload too large"}), 413


@app.errorhandler(429)
def rate_limit_exceeded(_exc):
    return jsonify({"error": "Too many requests"}), 429


def _print_import_report(result: dict) -> None:
    report = result.get("import_report") or []
    if not report:
        return
    for item in report:
        level = item.get("level", "info").upper()
        print(f"  [{level}] {item.get('message')}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Idle Fantasy Save Viewer")
    parser.add_argument("save_file", nargs="?", help="Save JSON to import on start")
    parser.add_argument("--import", dest="import_file", metavar="FILE", help="Import save without starting server")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (use 0.0.0.0 in Docker)")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--db", type=Path, help="SQLite path (legacy single-file mode)")
    parser.add_argument("--viewer", default=LOCAL_VIEWER_ID, help="Viewer id for CLI (default: local)")
    args = parser.parse_args()

    global DATA_DIR, DB_PATH
    DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent / "data"))

    if args.db:
        DB_PATH = args.db
        db_path = DB_PATH
        viewer_id = None
    else:
        viewer_id = ensure_local_viewer(DATA_DIR) if args.viewer == LOCAL_VIEWER_ID else args.viewer
        if not is_valid_viewer_id(viewer_id):
            print(f"Error: invalid viewer id: {viewer_id}", file=sys.stderr)
            return 1
        db_path = viewer_db_path(viewer_id, DATA_DIR)
        if not db_path.exists():
            conn = get_connection(db_path)
            init_db(conn)
            conn.close()

    conn = get_connection(db_path)
    init_db(conn)
    conn.close()

    import_path = args.import_file or args.save_file
    if import_path:
        path = Path(import_path)
        if not path.exists():
            print(f"Error: file not found: {path}", file=sys.stderr)
            return 1
        result = import_save(path, db_path=db_path)
        if result.get("error"):
            print(f"Import failed: {result['error']}", file=sys.stderr)
            _print_import_report(result)
            return 1
        if result.get("imported"):
            print(f"Imported snapshot #{result['snapshot_id']} from {path.name}")
            summary = result.get("import_summary") or {}
            if summary.get("warnings") or summary.get("infos"):
                print(
                    f"Notes: {summary.get('warnings', 0)} warning(s), "
                    f"{summary.get('infos', 0)} info(s)",
                    file=sys.stderr,
                )
            _print_import_report(result)
        else:
            print(f"Skipped duplicate: {path.name} (snapshot #{result['snapshot_id']})")

    if args.import_file and not args.save_file:
        return 0

    if viewer_id:
        url = f"http://{args.host}:{args.port}/v/{viewer_id}/"
    else:
        url = f"http://{args.host}:{args.port}/"
    print(f"Starting server at {url}")
    if not args.no_browser and args.host in ("127.0.0.1", "localhost"):
        webbrowser.open(url)
    app.run(host=args.host, port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
