"""Per-viewer isolation via secret URL tokens (no login)."""

from __future__ import annotations

import os
import re
import secrets
import shutil
import sqlite3
from pathlib import Path

from db import get_connection, init_db

VIEWER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
LOCAL_VIEWER_ID = "local"
VIEWER_DB_TABLES = frozenset({
    "snapshots",
    "inventory_snapshots",
    "skill_snapshots",
    "goals",
    "goal_groups",
})


def generate_viewer_id() -> str:
    return secrets.token_urlsafe(16)


def is_valid_viewer_id(viewer_id: str) -> bool:
    if viewer_id == LOCAL_VIEWER_ID:
        return True
    return bool(viewer_id and VIEWER_ID_RE.match(viewer_id))


def viewers_dir(data_dir: Path) -> Path:
    return data_dir / "viewers"


def viewer_db_path(viewer_id: str, data_dir: Path) -> Path:
    return viewers_dir(data_dir) / f"{viewer_id}.db"


def viewer_exists(viewer_id: str, data_dir: Path) -> bool:
    return viewer_db_path(viewer_id, data_dir).exists()


def create_viewer(data_dir: Path) -> str:
    """Create a new viewer with an empty SQLite database."""
    data_dir.mkdir(parents=True, exist_ok=True)
    viewers_dir(data_dir).mkdir(parents=True, exist_ok=True)

    for _ in range(10):
        viewer_id = generate_viewer_id()
        db_path = viewer_db_path(viewer_id, data_dir)
        if db_path.exists():
            continue
        conn = get_connection(db_path)
        init_db(conn)
        conn.close()
        return viewer_id

    raise RuntimeError("Could not allocate a unique viewer id")


def ensure_local_viewer(data_dir: Path) -> str:
    """Shared dev viewer – predictable path, not secret."""
    db_path = viewer_db_path(LOCAL_VIEWER_ID, data_dir)
    if db_path.exists():
        return LOCAL_VIEWER_ID
    conn = get_connection(db_path)
    init_db(conn)
    conn.close()
    return LOCAL_VIEWER_ID


def cli_viewer_marker(data_dir: Path) -> Path:
    return data_dir / "cli-viewer-id"


def get_or_create_cli_viewer(data_dir: Path) -> str:
    """Persistent personal viewer for local CLI starts."""
    data_dir.mkdir(parents=True, exist_ok=True)
    marker = cli_viewer_marker(data_dir)
    if marker.exists():
        viewer_id = marker.read_text(encoding="utf-8").strip()
        if is_valid_viewer_id(viewer_id) and viewer_exists(viewer_id, data_dir):
            return viewer_id

    viewer_id = create_viewer(data_dir)
    marker.write_text(viewer_id, encoding="utf-8")
    return viewer_id


def inspect_viewer_db(db_path: Path) -> dict[str, int]:
    """Validate a viewer SQLite file and apply schema migrations."""
    if not db_path.is_file():
        raise ValueError("Database file not found")
    try:
        conn = get_connection(db_path)
    except sqlite3.DatabaseError as exc:
        raise ValueError("Not a valid SQLite database") from exc
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        missing = VIEWER_DB_TABLES - tables
        if missing:
            raise ValueError("Not a valid Idle Fantasy viewer database")
        init_db(conn)
        conn.commit()
        snapshots = conn.execute("SELECT COUNT(*) AS c FROM snapshots").fetchone()["c"]
        goals = conn.execute("SELECT COUNT(*) AS c FROM goals").fetchone()["c"]
        goal_groups = conn.execute("SELECT COUNT(*) AS c FROM goal_groups").fetchone()["c"]
        return {
            "snapshots": snapshots,
            "goals": goals,
            "goal_groups": goal_groups,
        }
    finally:
        conn.close()


def restore_viewer_db(source: Path, target: Path) -> dict[str, int]:
    """Replace a viewer database with a validated copy."""
    stats = inspect_viewer_db(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_suffix(".db.importing")
    shutil.copy2(source, staging)
    try:
        os.replace(staging, target)
    except OSError:
        staging.unlink(missing_ok=True)
        raise
    return stats


def delete_viewer(viewer_id: str, data_dir: Path) -> bool:
    """Permanently delete a viewer database."""
    if viewer_id == LOCAL_VIEWER_ID:
        raise ValueError("Local viewer cannot be deleted")
    if not is_valid_viewer_id(viewer_id):
        raise ValueError("Invalid viewer id")
    db_path = viewer_db_path(viewer_id, data_dir)
    if not db_path.exists():
        return False
    db_path.unlink()
    return True
