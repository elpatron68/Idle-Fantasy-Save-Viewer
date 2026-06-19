"""SQLite persistence for save snapshots and history analysis."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from parser import SaveParseError, normalize_save, load_save

DEFAULT_DB = Path(__file__).parent / "data" / "history.db"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection(db_path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            imported_at TEXT NOT NULL,
            source_file TEXT NOT NULL,
            file_hash TEXT NOT NULL UNIQUE,
            exported_at INTEGER,
            character_name TEXT,
            coins INTEGER,
            total_level INTEGER,
            raw_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS inventory_snapshots (
            snapshot_id INTEGER NOT NULL,
            item_key TEXT NOT NULL,
            qty INTEGER NOT NULL,
            category TEXT NOT NULL,
            PRIMARY KEY (snapshot_id, item_key),
            FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS skill_snapshots (
            snapshot_id INTEGER NOT NULL,
            skill_key TEXT NOT NULL,
            level INTEGER NOT NULL,
            xp INTEGER NOT NULL,
            PRIMARY KEY (snapshot_id, skill_key),
            FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_snapshots_exported ON snapshots(exported_at);
    """)
    conn.commit()


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def import_save(
    path: str | Path,
    conn: sqlite3.Connection | None = None,
    db_path: Path | str = DEFAULT_DB,
) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    digest = file_hash(path)
    own_conn = conn is None
    if own_conn:
        conn = get_connection(db_path)
        init_db(conn)

    existing = conn.execute(
        "SELECT id FROM snapshots WHERE file_hash = ?", (digest,)
    ).fetchone()
    if existing:
        result = {
            "imported": False,
            "snapshot_id": existing["id"],
            "reason": "duplicate",
            "import_report": [],
        }
        if own_conn:
            conn.close()
        return result

    try:
        raw, failures = load_save(path)
        normalized = normalize_save(raw, source_file=path.name, nested_failures=failures)
    except SaveParseError as exc:
        if own_conn:
            conn.close()
        return {
            "imported": False,
            "error": str(exc),
            "import_report": exc.issues,
        }

    import_report = normalized["meta"].get("import_report", [])
    character = normalized["character"]
    meta = normalized["meta"]

    cur = conn.execute(
        """
        INSERT INTO snapshots
            (imported_at, source_file, file_hash, exported_at, character_name, coins, total_level, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _utc_now_iso(),
            path.name,
            digest,
            meta.get("exported_at"),
            character.get("name"),
            meta.get("coins"),
            meta.get("total_level"),
            json.dumps(normalized),
        ),
    )
    snapshot_id = cur.lastrowid

    conn.executemany(
        "INSERT INTO inventory_snapshots (snapshot_id, item_key, qty, category) VALUES (?, ?, ?, ?)",
        [(snapshot_id, i["key"], i["qty"], i["category"]) for i in normalized["inventory"]],
    )
    conn.executemany(
        "INSERT INTO skill_snapshots (snapshot_id, skill_key, level, xp) VALUES (?, ?, ?, ?)",
        [(snapshot_id, s["key"], s["level"], s["xp"]) for s in normalized["skills"]],
    )
    conn.commit()

    if own_conn:
        conn.close()

    return {
        "imported": True,
        "snapshot_id": snapshot_id,
        "import_report": import_report,
        "import_summary": meta.get("import_summary"),
    }


def list_snapshots(conn: sqlite3.Connection | None = None, db_path: Path | str = DEFAULT_DB) -> list[dict]:
    own_conn = conn is None
    if own_conn:
        conn = get_connection(db_path)
        init_db(conn)

    rows = conn.execute(
        """
        SELECT id, imported_at, source_file, exported_at, character_name, coins, total_level
        FROM snapshots ORDER BY exported_at DESC, id DESC
        """
    ).fetchall()

    if own_conn:
        conn.close()

    return [dict(r) for r in rows]


def get_snapshot(snapshot_id: int, conn: sqlite3.Connection | None = None, db_path: Path | str = DEFAULT_DB) -> dict | None:
    own_conn = conn is None
    if own_conn:
        conn = get_connection(db_path)
        init_db(conn)

    row = conn.execute("SELECT raw_json FROM snapshots WHERE id = ?", (snapshot_id,)).fetchone()
    if own_conn:
        conn.close()

    if not row:
        return None
    return json.loads(row["raw_json"])


def get_latest_snapshot(conn: sqlite3.Connection | None = None, db_path: Path | str = DEFAULT_DB) -> dict | None:
    own_conn = conn is None
    if own_conn:
        conn = get_connection(db_path)
        init_db(conn)

    row = conn.execute(
        "SELECT raw_json FROM snapshots ORDER BY exported_at DESC, id DESC LIMIT 1"
    ).fetchone()

    if own_conn:
        conn.close()

    if not row:
        return None
    return json.loads(row["raw_json"])


def diff_snapshots(
    older_id: int,
    newer_id: int,
    conn: sqlite3.Connection | None = None,
    db_path: Path | str = DEFAULT_DB,
) -> dict[str, Any]:
    own_conn = conn is None
    if own_conn:
        conn = get_connection(db_path)
        init_db(conn)

    meta_rows = conn.execute(
        "SELECT id, character_name, coins, total_level, exported_at, source_file FROM snapshots WHERE id IN (?, ?)",
        (older_id, newer_id),
    ).fetchall()
    meta_by_id = {r["id"]: dict(r) for r in meta_rows}

    if older_id not in meta_by_id or newer_id not in meta_by_id:
        if own_conn:
            conn.close()
        raise ValueError("Snapshot not found")

    older_meta = meta_by_id[older_id]
    newer_meta = meta_by_id[newer_id]

    def _inventory(sid: int) -> dict[str, dict]:
        rows = conn.execute(
            "SELECT item_key, qty, category FROM inventory_snapshots WHERE snapshot_id = ?",
            (sid,),
        ).fetchall()
        return {r["item_key"]: {"qty": r["qty"], "category": r["category"]} for r in rows}

    def _skills(sid: int) -> dict[str, dict]:
        rows = conn.execute(
            "SELECT skill_key, level, xp FROM skill_snapshots WHERE snapshot_id = ?",
            (sid,),
        ).fetchall()
        return {r["skill_key"]: {"level": r["level"], "xp": r["xp"]} for r in rows}

    old_inv, new_inv = _inventory(older_id), _inventory(newer_id)
    old_sk, new_sk = _skills(older_id), _skills(newer_id)

    all_items = set(old_inv) | set(new_inv)
    inventory_changes = []
    for key in sorted(all_items):
        old_qty = old_inv.get(key, {}).get("qty", 0)
        new_qty = new_inv.get(key, {}).get("qty", 0)
        delta = new_qty - old_qty
        if delta != 0:
            cat = new_inv.get(key, old_inv.get(key, {})).get("category", "Misc")
            inventory_changes.append({
                "key": key,
                "name": key.replace("_", " ").title(),
                "category": cat,
                "old_qty": old_qty,
                "new_qty": new_qty,
                "delta": delta,
            })

    all_skills = set(old_sk) | set(new_sk)
    skill_changes = []
    for key in sorted(all_skills):
        old_s = old_sk.get(key, {"level": 0, "xp": 0})
        new_s = new_sk.get(key, {"level": 0, "xp": 0})
        if old_s["level"] != new_s["level"] or old_s["xp"] != new_s["xp"]:
            skill_changes.append({
                "key": key,
                "name": key.replace("_", " ").title(),
                "old_level": old_s["level"],
                "new_level": new_s["level"],
                "level_delta": new_s["level"] - old_s["level"],
                "old_xp": old_s["xp"],
                "new_xp": new_s["xp"],
                "xp_delta": new_s["xp"] - old_s["xp"],
            })

    if own_conn:
        conn.close()

    return {
        "older": older_meta,
        "newer": newer_meta,
        "summary": {
            "coins_delta": newer_meta["coins"] - older_meta["coins"],
            "total_level_delta": newer_meta["total_level"] - older_meta["total_level"],
        },
        "inventory_changes": inventory_changes,
        "skill_changes": skill_changes,
    }


def timeline(db_path: Path | str = DEFAULT_DB) -> list[dict]:
    conn = get_connection(db_path)
    init_db(conn)
    rows = conn.execute(
        """
        SELECT s.id, s.exported_at, s.coins, s.total_level, s.character_name, s.source_file
        FROM snapshots s ORDER BY s.exported_at ASC, s.id ASC
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def inventory_timeline(db_path: Path | str = DEFAULT_DB) -> dict[str, Any]:
    """Per-item quantity series aligned to snapshots (oldest → newest)."""
    conn = get_connection(db_path)
    init_db(conn)
    snap_rows = conn.execute(
        """
        SELECT id, exported_at FROM snapshots
        ORDER BY exported_at ASC, id ASC
        """
    ).fetchall()
    snapshots = [dict(r) for r in snap_rows]
    if not snapshots:
        conn.close()
        return {"snapshots": [], "series": {}}

    snap_index = {row["id"]: idx for idx, row in enumerate(snapshots)}
    inv_rows = conn.execute(
        "SELECT snapshot_id, item_key, qty FROM inventory_snapshots"
    ).fetchall()
    conn.close()

    series: dict[str, list[int]] = {}
    n = len(snapshots)
    for row in inv_rows:
        key = row["item_key"]
        if key not in series:
            series[key] = [0] * n
        idx = snap_index.get(row["snapshot_id"])
        if idx is not None:
            series[key][idx] = row["qty"]

    return {"snapshots": snapshots, "series": series}
