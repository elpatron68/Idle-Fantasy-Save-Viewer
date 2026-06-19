#!/usr/bin/env python3
"""Idle Fantasy Save Viewer – local Flask server."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from db import (
    DEFAULT_DB,
    diff_snapshots,
    get_latest_snapshot,
    get_snapshot,
    import_save,
    init_db,
    list_snapshots,
    get_connection,
    timeline,
)
app = Flask(__name__)
DB_PATH = DEFAULT_DB


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/snapshot/latest")
def api_latest():
    data = get_latest_snapshot(db_path=DB_PATH)
    if not data:
        return jsonify({"error": "No snapshots imported yet"}), 404
    return jsonify(data)


@app.route("/api/snapshot/<int:snapshot_id>")
def api_snapshot(snapshot_id: int):
    data = get_snapshot(snapshot_id, db_path=DB_PATH)
    if not data:
        return jsonify({"error": "Snapshot not found"}), 404
    return jsonify(data)


@app.route("/api/snapshots")
def api_snapshots():
    return jsonify(list_snapshots(db_path=DB_PATH))


@app.route("/api/snapshots/<int:older_id>/diff/<int:newer_id>")
def api_diff(older_id: int, newer_id: int):
    try:
        return jsonify(diff_snapshots(older_id, newer_id, db_path=DB_PATH))
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@app.route("/api/timeline")
def api_timeline():
    return jsonify(timeline(db_path=DB_PATH))


@app.route("/api/import", methods=["POST"])
def api_import():
    if "file" in request.files:
        f = request.files["file"]
        if not f.filename:
            return jsonify({"error": "No file selected"}), 400
        tmp = Path(DB_PATH.parent) / f"_upload_{f.filename}"
        f.save(tmp)
        try:
            result = import_save(tmp, db_path=DB_PATH)
        finally:
            tmp.unlink(missing_ok=True)
        return jsonify(result)

    body = request.get_json(silent=True) or {}
    path = body.get("path")
    if not path:
        return jsonify({"error": "Provide file upload or JSON body with path"}), 400
    path = Path(path)
    if not path.exists():
        return jsonify({"error": f"File not found: {path}"}), 404
    return jsonify(import_save(path, db_path=DB_PATH))


def main() -> int:
    parser = argparse.ArgumentParser(description="Idle Fantasy Save Viewer")
    parser.add_argument("save_file", nargs="?", help="Save JSON to import on start")
    parser.add_argument("--import", dest="import_file", metavar="FILE", help="Import save without starting server")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path")
    args = parser.parse_args()

    global DB_PATH
    DB_PATH = args.db

    conn = get_connection(DB_PATH)
    init_db(conn)
    conn.close()

    import_path = args.import_file or args.save_file
    if import_path:
        path = Path(import_path)
        if not path.exists():
            print(f"Error: file not found: {path}", file=sys.stderr)
            return 1
        result = import_save(path, db_path=DB_PATH)
        if result.get("imported"):
            print(f"Imported snapshot #{result['snapshot_id']} from {path.name}")
        else:
            print(f"Skipped duplicate: {path.name} (snapshot #{result['snapshot_id']})")

    if args.import_file and not args.save_file:
        return 0

    url = f"http://127.0.0.1:{args.port}"
    print(f"Starting server at {url}")
    if not args.no_browser:
        webbrowser.open(url)
    app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    sys.exit(main())
