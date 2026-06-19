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
        CREATE TABLE IF NOT EXISTS goal_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER REFERENCES goal_groups(id) ON DELETE SET NULL,
            item_key TEXT NOT NULL UNIQUE,
            item_name TEXT NOT NULL,
            category TEXT NOT NULL,
            target_qty INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT
        );
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

    goals_result = check_goals_after_import(snapshot_id, conn=conn, db_path=db_path)

    if own_conn:
        conn.close()

    return {
        "imported": True,
        "snapshot_id": snapshot_id,
        "import_report": import_report,
        "import_summary": meta.get("import_summary"),
        **goals_result,
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


def _latest_snapshot_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute(
        "SELECT id FROM snapshots ORDER BY exported_at DESC, id DESC LIMIT 1"
    ).fetchone()
    return row["id"] if row else None


def _inventory_qty_for_snapshot(conn: sqlite3.Connection, snapshot_id: int, item_key: str) -> int:
    row = conn.execute(
        "SELECT qty FROM inventory_snapshots WHERE snapshot_id = ? AND item_key = ?",
        (snapshot_id, item_key),
    ).fetchone()
    return row["qty"] if row else 0


def _goal_row_to_dict(row: sqlite3.Row, current_qty: int) -> dict[str, Any]:
    target = row["target_qty"]
    progress_pct = min(100, int(current_qty / target * 100)) if target > 0 else 0
    return {
        "id": row["id"],
        "group_id": row["group_id"],
        "group_name": row["group_name"],
        "item_key": row["item_key"],
        "item_name": row["item_name"],
        "category": row["category"],
        "target_qty": target,
        "current_qty": current_qty,
        "progress_pct": progress_pct,
        "completed_at": row["completed_at"],
        "created_at": row["created_at"],
    }


def list_goal_groups(db_path: Path | str = DEFAULT_DB) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    init_db(conn)
    rows = conn.execute(
        """
        SELECT g.id, g.name, g.created_at,
               COUNT(go.id) AS total,
               SUM(CASE WHEN go.completed_at IS NOT NULL THEN 1 ELSE 0 END) AS completed
        FROM goal_groups g
        LEFT JOIN goals go ON go.group_id = g.id
        GROUP BY g.id
        ORDER BY g.created_at ASC, g.id ASC
        """
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        total = r["total"] or 0
        completed = r["completed"] or 0
        result.append({
            "id": r["id"],
            "name": r["name"],
            "created_at": r["created_at"],
            "total": total,
            "completed": completed,
            "open": total - completed,
        })
    return result


def create_goal_group(name: str, db_path: Path | str = DEFAULT_DB) -> dict[str, Any]:
    name = name.strip()
    if not name:
        raise ValueError("Group name is required")
    conn = get_connection(db_path)
    init_db(conn)
    cur = conn.execute(
        "INSERT INTO goal_groups (name, created_at) VALUES (?, ?)",
        (name, _utc_now_iso()),
    )
    group_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {"id": group_id, "name": name, "total": 0, "completed": 0, "open": 0}


def delete_goal_group(group_id: int, db_path: Path | str = DEFAULT_DB) -> bool:
    conn = get_connection(db_path)
    init_db(conn)
    row = conn.execute("SELECT id FROM goal_groups WHERE id = ?", (group_id,)).fetchone()
    if not row:
        conn.close()
        return False
    conn.execute("UPDATE goals SET group_id = NULL WHERE group_id = ?", (group_id,))
    conn.execute("DELETE FROM goal_groups WHERE id = ?", (group_id,))
    conn.commit()
    conn.close()
    return True


def _fetch_goals_with_qty(conn: sqlite3.Connection, snapshot_id: int | None) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT go.id, go.group_id, gg.name AS group_name, go.item_key, go.item_name,
               go.category, go.target_qty, go.created_at, go.completed_at
        FROM goals go
        LEFT JOIN goal_groups gg ON gg.id = go.group_id
        ORDER BY go.created_at ASC, go.id ASC
        """
    ).fetchall()
    goals = []
    for row in rows:
        current_qty = _inventory_qty_for_snapshot(conn, snapshot_id, row["item_key"]) if snapshot_id else 0
        goals.append(_goal_row_to_dict(row, current_qty))
    return goals


def list_goals_structured(db_path: Path | str = DEFAULT_DB) -> dict[str, Any]:
    conn = get_connection(db_path)
    init_db(conn)
    snapshot_id = _latest_snapshot_id(conn)
    all_goals = _fetch_goals_with_qty(conn, snapshot_id)

    groups_map: dict[int, dict[str, Any]] = {}
    ungrouped: list[dict[str, Any]] = []

    for goal in all_goals:
        if goal["group_id"] is None:
            ungrouped.append(goal)
            continue
        gid = goal["group_id"]
        if gid not in groups_map:
            groups_map[gid] = {
                "id": gid,
                "name": goal["group_name"],
                "total": 0,
                "completed": 0,
                "goals": [],
            }
        groups_map[gid]["goals"].append(goal)
        groups_map[gid]["total"] += 1
        if goal["completed_at"]:
            groups_map[gid]["completed"] += 1

    empty_groups = conn.execute(
        "SELECT id, name FROM goal_groups ORDER BY created_at ASC, id ASC"
    ).fetchall()
    for row in empty_groups:
        gid = row["id"]
        if gid not in groups_map:
            groups_map[gid] = {
                "id": gid,
                "name": row["name"],
                "total": 0,
                "completed": 0,
                "goals": [],
            }

    conn.close()
    return {
        "groups": list(groups_map.values()),
        "ungrouped": ungrouped,
    }


def _resolve_item_from_latest(
    conn: sqlite3.Connection, item_key: str
) -> dict[str, str] | None:
    snapshot_id = _latest_snapshot_id(conn)
    if not snapshot_id:
        return None
    row = conn.execute(
        "SELECT item_key, qty, category FROM inventory_snapshots WHERE snapshot_id = ? AND item_key = ?",
        (snapshot_id, item_key),
    ).fetchone()
    if not row:
        return None
    latest = get_latest_snapshot(conn=conn)
    item_name = item_key.replace("_", " ").title()
    if latest:
        for item in latest.get("inventory", []):
            if item["key"] == item_key:
                item_name = item["name"]
                break
    return {"item_key": item_key, "item_name": item_name, "category": row["category"], "qty": row["qty"]}


def create_goal(
    item_key: str,
    target_qty: int,
    group_id: int | None = None,
    db_path: Path | str = DEFAULT_DB,
) -> dict[str, Any]:
    if target_qty <= 0:
        raise ValueError("Target quantity must be positive")

    conn = get_connection(db_path)
    init_db(conn)

    existing = conn.execute("SELECT id FROM goals WHERE item_key = ?", (item_key,)).fetchone()
    if existing:
        conn.close()
        raise ValueError("A goal for this item already exists")

    if group_id is not None:
        group = conn.execute("SELECT id FROM goal_groups WHERE id = ?", (group_id,)).fetchone()
        if not group:
            conn.close()
            raise ValueError("Goal group not found")

    item = _resolve_item_from_latest(conn, item_key)
    if not item:
        conn.close()
        raise ValueError("Item not found in current inventory")

    now = _utc_now_iso()
    completed_at = now if item["qty"] >= target_qty else None
    cur = conn.execute(
        """
        INSERT INTO goals (group_id, item_key, item_name, category, target_qty, created_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (group_id, item_key, item["item_name"], item["category"], target_qty, now, completed_at),
    )
    goal_id = cur.lastrowid
    conn.commit()

    row = conn.execute(
        """
        SELECT go.id, go.group_id, gg.name AS group_name, go.item_key, go.item_name,
               go.category, go.target_qty, go.created_at, go.completed_at
        FROM goals go
        LEFT JOIN goal_groups gg ON gg.id = go.group_id
        WHERE go.id = ?
        """,
        (goal_id,),
    ).fetchone()
    conn.close()
    return _goal_row_to_dict(row, item["qty"])


def delete_goal(goal_id: int, db_path: Path | str = DEFAULT_DB) -> bool:
    conn = get_connection(db_path)
    init_db(conn)
    cur = conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def check_goals_after_import(
    snapshot_id: int,
    conn: sqlite3.Connection | None = None,
    db_path: Path | str = DEFAULT_DB,
) -> dict[str, Any]:
    own_conn = conn is None
    if own_conn:
        conn = get_connection(db_path)
        init_db(conn)

    open_goals = conn.execute(
        """
        SELECT go.id, go.group_id, gg.name AS group_name, go.item_key, go.item_name,
               go.target_qty
        FROM goals go
        LEFT JOIN goal_groups gg ON gg.id = go.group_id
        WHERE go.completed_at IS NULL
        """
    ).fetchall()

    now = _utc_now_iso()
    goals_completed: list[dict[str, Any]] = []
    groups_touched: set[int] = set()

    for goal in open_goals:
        current_qty = _inventory_qty_for_snapshot(conn, snapshot_id, goal["item_key"])
        if current_qty >= goal["target_qty"]:
            conn.execute(
                "UPDATE goals SET completed_at = ? WHERE id = ?",
                (now, goal["id"]),
            )
            entry = {
                "id": goal["id"],
                "item_key": goal["item_key"],
                "item_name": goal["item_name"],
                "target_qty": goal["target_qty"],
                "current_qty": current_qty,
                "group_id": goal["group_id"],
                "group_name": goal["group_name"],
            }
            goals_completed.append(entry)
            if goal["group_id"] is not None:
                groups_touched.add(goal["group_id"])

    groups_completed: list[dict[str, Any]] = []
    for gid in groups_touched:
        stats = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN completed_at IS NOT NULL THEN 1 ELSE 0 END) AS completed
            FROM goals WHERE group_id = ?
            """,
            (gid,),
        ).fetchone()
        if stats and stats["total"] and stats["total"] == stats["completed"]:
            g = conn.execute("SELECT id, name FROM goal_groups WHERE id = ?", (gid,)).fetchone()
            if g:
                groups_completed.append({"id": g["id"], "name": g["name"]})

    conn.commit()
    if own_conn:
        conn.close()

    return {
        "goals_completed": goals_completed,
        "groups_completed": groups_completed,
    }
