"""Per-viewer isolation via secret URL tokens (no login)."""

from __future__ import annotations

import re
import secrets
from pathlib import Path

from db import get_connection, init_db

VIEWER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
LOCAL_VIEWER_ID = "local"


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
