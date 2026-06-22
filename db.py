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
SKILL_GOAL_PREFIX = "__skill__:"


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
            goal_type TEXT NOT NULL DEFAULT 'item',
            mode TEXT NOT NULL DEFAULT 'absolute',
            item_key TEXT NOT NULL UNIQUE,
            item_name TEXT NOT NULL,
            category TEXT NOT NULL,
            target_qty INTEGER NOT NULL,
            baseline_qty INTEGER,
            created_at TEXT NOT NULL,
            completed_at TEXT
        );
    """)
    _migrate_schema(conn)
    conn.commit()


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Add columns introduced after initial goals release."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(goals)")}
    if "goal_type" not in cols:
        conn.execute("ALTER TABLE goals ADD COLUMN goal_type TEXT NOT NULL DEFAULT 'item'")
    if "mode" not in cols:
        conn.execute("ALTER TABLE goals ADD COLUMN mode TEXT NOT NULL DEFAULT 'absolute'")
    if "baseline_qty" not in cols:
        conn.execute("ALTER TABLE goals ADD COLUMN baseline_qty INTEGER")


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
    import_changes = summarize_import_changes(snapshot_id, conn=conn)

    if own_conn:
        conn.close()

    return {
        "imported": True,
        "snapshot_id": snapshot_id,
        "import_report": import_report,
        "import_summary": meta.get("import_summary"),
        "import_changes": import_changes,
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
        SELECT s.id, s.imported_at, s.exported_at, s.coins, s.total_level, s.character_name, s.source_file
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
        SELECT id, imported_at, exported_at FROM snapshots
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


def _skill_goal_storage_key(skill_key: str) -> str:
    return f"{SKILL_GOAL_PREFIX}{skill_key}"


def _skill_key_from_storage(storage_key: str) -> str | None:
    if storage_key.startswith(SKILL_GOAL_PREFIX):
        return storage_key[len(SKILL_GOAL_PREFIX):]
    return None


def _skill_level_for_snapshot(conn: sqlite3.Connection, snapshot_id: int, skill_key: str) -> int:
    row = conn.execute(
        "SELECT level FROM skill_snapshots WHERE snapshot_id = ? AND skill_key = ?",
        (snapshot_id, skill_key),
    ).fetchone()
    return row["level"] if row else 0


def _goal_is_complete(
    goal_type: str,
    mode: str,
    target: int,
    baseline: int | None,
    *,
    current_item_qty: int = 0,
    current_skill_level: int = 0,
) -> bool:
    base = baseline or 0
    if goal_type == "skill":
        current = current_skill_level
    else:
        current = current_item_qty
    if mode == "relative":
        return max(0, current - base) >= target
    return current >= target


def _goal_progress_values(
    row: sqlite3.Row,
    *,
    current_item_qty: int = 0,
    current_skill_level: int = 0,
) -> tuple[int, int, int, bool]:
    goal_type = row["goal_type"] if row["goal_type"] else "item"
    mode = row["mode"] if row["mode"] else "absolute"
    target = row["target_qty"]
    baseline = row["baseline_qty"] if row["baseline_qty"] is not None else 0

    if goal_type == "skill":
        current = current_skill_level
        if mode == "relative":
            progress_val = max(0, current - baseline)
            completed = progress_val >= target
            display_current = progress_val
            display_target = target
        else:
            progress_val = current
            completed = current >= target
            display_current = current
            display_target = target
    else:
        current = current_item_qty
        if mode == "relative":
            progress_val = max(0, current - baseline)
            completed = progress_val >= target
            display_current = progress_val
            display_target = target
        else:
            progress_val = current
            completed = current >= target
            display_current = current
            display_target = target

    progress_pct = min(100, int(progress_val / target * 100)) if target > 0 else (100 if completed else 0)
    return display_current, display_target, progress_pct, completed


def _goal_row_to_dict(
    row: sqlite3.Row,
    *,
    current_item_qty: int = 0,
    current_skill_level: int = 0,
    rate_per_snapshot: float | None = None,
) -> dict[str, Any]:
    display_current, display_target, progress_pct, completed = _goal_progress_values(
        row,
        current_item_qty=current_item_qty,
        current_skill_level=current_skill_level,
    )
    goal_type = row["goal_type"] if row["goal_type"] else "item"
    mode = row["mode"] if row["mode"] else "absolute"
    skill_key = _skill_key_from_storage(row["item_key"]) if goal_type == "skill" else None
    missing = max(0, display_target - display_current) if not row["completed_at"] else 0
    eta_snapshots = None
    if missing > 0 and rate_per_snapshot and rate_per_snapshot > 0:
        eta_snapshots = max(1, int((missing + rate_per_snapshot - 1) // rate_per_snapshot))

    return {
        "id": row["id"],
        "group_id": row["group_id"],
        "group_name": row["group_name"],
        "goal_type": goal_type,
        "mode": mode,
        "item_key": row["item_key"] if goal_type == "item" else skill_key,
        "skill_key": skill_key,
        "item_name": row["item_name"],
        "category": row["category"],
        "target_qty": row["target_qty"],
        "baseline_qty": row["baseline_qty"],
        "current_qty": display_current,
        "target_display": display_target,
        "raw_current_qty": current_item_qty,
        "raw_skill_level": current_skill_level,
        "missing_qty": missing,
        "progress_pct": progress_pct,
        "eta_snapshots": eta_snapshots,
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


def rename_goal_group(group_id: int, name: str, db_path: Path | str = DEFAULT_DB) -> bool:
    name = name.strip()
    if not name:
        raise ValueError("Group name is required")
    conn = get_connection(db_path)
    init_db(conn)
    cur = conn.execute(
        "UPDATE goal_groups SET name = ? WHERE id = ?",
        (name, group_id),
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def _goal_item_rates(conn: sqlite3.Connection) -> dict[str, float]:
    """Average qty gain per snapshot for item goals (last segments)."""
    snap_rows = conn.execute(
        "SELECT id FROM snapshots ORDER BY exported_at ASC, id ASC"
    ).fetchall()
    if len(snap_rows) < 2:
        return {}
    snap_index = {row["id"]: idx for idx, row in enumerate(snap_rows)}
    inv_rows = conn.execute(
        "SELECT snapshot_id, item_key, qty FROM inventory_snapshots"
    ).fetchall()
    series: dict[str, list[int]] = {}
    n = len(snap_rows)
    for row in inv_rows:
        key = row["item_key"]
        if key not in series:
            series[key] = [0] * n
        idx = snap_index.get(row["snapshot_id"])
        if idx is not None:
            series[key][idx] = row["qty"]
    rates: dict[str, float] = {}
    for key, values in series.items():
        deltas = [values[i] - values[i - 1] for i in range(1, len(values))]
        positive = [d for d in deltas if d > 0]
        if positive:
            rates[key] = sum(positive) / len(positive)
    return rates


def _fetch_goals_with_qty(conn: sqlite3.Connection, snapshot_id: int | None) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT go.id, go.group_id, gg.name AS group_name, go.goal_type, go.mode,
               go.item_key, go.item_name, go.category, go.target_qty, go.baseline_qty,
               go.created_at, go.completed_at
        FROM goals go
        LEFT JOIN goal_groups gg ON gg.id = go.group_id
        ORDER BY go.created_at ASC, go.id ASC
        """
    ).fetchall()
    rates = _goal_item_rates(conn) if snapshot_id else {}
    goals = []
    for row in rows:
        goal_type = row["goal_type"] if row["goal_type"] else "item"
        rate = None
        if goal_type == "item":
            current_item_qty = _inventory_qty_for_snapshot(conn, snapshot_id, row["item_key"]) if snapshot_id else 0
            current_skill_level = 0
            rate = rates.get(row["item_key"])
        else:
            skill_key = _skill_key_from_storage(row["item_key"]) or ""
            current_item_qty = 0
            current_skill_level = _skill_level_for_snapshot(conn, snapshot_id, skill_key) if snapshot_id else 0
        goals.append(_goal_row_to_dict(
            row,
            current_item_qty=current_item_qty,
            current_skill_level=current_skill_level,
            rate_per_snapshot=rate,
        ))
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


def goals_overview(db_path: Path | str = DEFAULT_DB) -> dict[str, int]:
    structured = list_goals_structured(db_path)
    all_goals = structured["ungrouped"] + [
        g for group in structured["groups"] for g in group.get("goals", [])
    ]
    open_count = sum(1 for g in all_goals if not g["completed_at"])
    done_count = sum(1 for g in all_goals if g["completed_at"])
    return {"open": open_count, "completed": done_count, "total": len(all_goals)}


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
    mode: str = "absolute",
    db_path: Path | str = DEFAULT_DB,
) -> dict[str, Any]:
    if target_qty <= 0:
        raise ValueError("Target quantity must be positive")
    if mode not in ("absolute", "relative"):
        raise ValueError("Invalid goal mode")

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

    baseline = item["qty"] if mode == "relative" else None
    now = _utc_now_iso()
    completed = _goal_is_complete(
        "item", mode, target_qty, baseline, current_item_qty=item["qty"]
    )
    completed_at = now if completed else None
    cur = conn.execute(
        """
        INSERT INTO goals
            (group_id, goal_type, mode, item_key, item_name, category, target_qty, baseline_qty, created_at, completed_at)
        VALUES (?, 'item', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (group_id, mode, item_key, item["item_name"], item["category"], target_qty, baseline, now, completed_at),
    )
    goal_id = cur.lastrowid
    conn.commit()

    row = conn.execute(
        """
        SELECT go.id, go.group_id, gg.name AS group_name, go.goal_type, go.mode,
               go.item_key, go.item_name, go.category, go.target_qty, go.baseline_qty,
               go.created_at, go.completed_at
        FROM goals go
        LEFT JOIN goal_groups gg ON gg.id = go.group_id
        WHERE go.id = ?
        """,
        (goal_id,),
    ).fetchone()
    conn.close()
    return _goal_row_to_dict(row, current_item_qty=item["qty"])


def create_skill_goal(
    skill_key: str,
    target_level: int,
    group_id: int | None = None,
    mode: str = "absolute",
    db_path: Path | str = DEFAULT_DB,
) -> dict[str, Any]:
    if target_level <= 0:
        raise ValueError("Target level must be positive")
    if mode not in ("absolute", "relative"):
        raise ValueError("Invalid goal mode")

    conn = get_connection(db_path)
    init_db(conn)
    storage_key = _skill_goal_storage_key(skill_key)

    existing = conn.execute("SELECT id FROM goals WHERE item_key = ?", (storage_key,)).fetchone()
    if existing:
        conn.close()
        raise ValueError("A goal for this skill already exists")

    if group_id is not None:
        group = conn.execute("SELECT id FROM goal_groups WHERE id = ?", (group_id,)).fetchone()
        if not group:
            conn.close()
            raise ValueError("Goal group not found")

    snapshot_id = _latest_snapshot_id(conn)
    if not snapshot_id:
        conn.close()
        raise ValueError("No snapshots imported yet")

    current_level = _skill_level_for_snapshot(conn, snapshot_id, skill_key)
    latest = get_latest_snapshot(conn=conn)
    skill_name = skill_key.replace("_", " ").title()
    if latest:
        for sk in latest.get("skills", []):
            if sk["key"] == skill_key:
                skill_name = sk["name"]
                break

    baseline = current_level if mode == "relative" else None
    now = _utc_now_iso()
    completed = _goal_is_complete(
        "skill", mode, target_level, baseline, current_skill_level=current_level
    )
    completed_at = now if completed else None
    cur = conn.execute(
        """
        INSERT INTO goals
            (group_id, goal_type, mode, item_key, item_name, category, target_qty, baseline_qty, created_at, completed_at)
        VALUES (?, 'skill', ?, ?, ?, 'Skill', ?, ?, ?, ?)
        """,
        (group_id, mode, storage_key, skill_name, target_level, baseline, now, completed_at),
    )
    goal_id = cur.lastrowid
    conn.commit()

    row = conn.execute(
        """
        SELECT go.id, go.group_id, gg.name AS group_name, go.goal_type, go.mode,
               go.item_key, go.item_name, go.category, go.target_qty, go.baseline_qty,
               go.created_at, go.completed_at
        FROM goals go
        LEFT JOIN goal_groups gg ON gg.id = go.group_id
        WHERE go.id = ?
        """,
        (goal_id,),
    ).fetchone()
    conn.close()
    return _goal_row_to_dict(row, current_skill_level=current_level)


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
        SELECT go.id, go.group_id, gg.name AS group_name, go.goal_type, go.mode,
               go.item_key, go.item_name, go.target_qty, go.baseline_qty
        FROM goals go
        LEFT JOIN goal_groups gg ON gg.id = go.group_id
        WHERE go.completed_at IS NULL
        """
    ).fetchall()

    now = _utc_now_iso()
    goals_completed: list[dict[str, Any]] = []
    groups_touched: set[int] = set()

    for goal in open_goals:
        goal_type = goal["goal_type"] if goal["goal_type"] else "item"
        mode = goal["mode"] if goal["mode"] else "absolute"
        if goal_type == "skill":
            skill_key = _skill_key_from_storage(goal["item_key"]) or ""
            current_item_qty = 0
            current_skill_level = _skill_level_for_snapshot(conn, snapshot_id, skill_key)
            current_display = current_skill_level
        else:
            current_item_qty = _inventory_qty_for_snapshot(conn, snapshot_id, goal["item_key"])
            current_skill_level = 0
            current_display = current_item_qty

        if not _goal_is_complete(
            goal_type, mode, goal["target_qty"], goal["baseline_qty"],
            current_item_qty=current_item_qty,
            current_skill_level=current_skill_level,
        ):
            continue

        conn.execute(
            "UPDATE goals SET completed_at = ? WHERE id = ?",
            (now, goal["id"]),
        )
        entry = {
            "id": goal["id"],
            "goal_type": goal_type,
            "item_key": goal["item_key"],
            "item_name": goal["item_name"],
            "target_qty": goal["target_qty"],
            "current_qty": current_display,
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


def summarize_import_changes(
    snapshot_id: int,
    conn: sqlite3.Connection | None = None,
    db_path: Path | str = DEFAULT_DB,
) -> dict[str, Any]:
    own_conn = conn is None
    if own_conn:
        conn = get_connection(db_path)
        init_db(conn)

    rows = conn.execute(
        """
        SELECT id FROM snapshots
        WHERE id < ?
        ORDER BY exported_at DESC, id DESC
        LIMIT 1
        """,
        (snapshot_id,),
    ).fetchone()

    if not rows:
        if own_conn:
            conn.close()
        return {"has_previous": False}

    older_id = rows["id"]
    try:
        diff = diff_snapshots(older_id, snapshot_id, conn=conn, db_path=db_path)
    except ValueError:
        if own_conn:
            conn.close()
        return {"has_previous": False}

    older_data = get_snapshot(older_id, conn=conn, db_path=db_path) or {}
    newer_data = get_snapshot(snapshot_id, conn=conn, db_path=db_path) or {}

    quests_completed = 0
    old_story = {q.get("name"): q.get("completed") for q in (older_data.get("quests") or {}).get("story", [])}
    for q in (newer_data.get("quests") or {}).get("story", []):
        name = q.get("name")
        if name and q.get("completed") and not old_story.get(name):
            quests_completed += 1

    slayer_delta = 0
    old_slayer = (older_data.get("combat") or {}).get("slayer_task") or {}
    new_slayer = (newer_data.get("combat") or {}).get("slayer_task") or {}
    if old_slayer.get("display_name") == new_slayer.get("display_name"):
        slayer_delta = (new_slayer.get("kills_completed") or 0) - (old_slayer.get("kills_completed") or 0)

    dungeon_delta = 0
    old_runs = (older_data.get("combat") or {}).get("dungeon_runs") or {}
    new_runs = (newer_data.get("combat") or {}).get("dungeon_runs") or {}
    for key, val in new_runs.items():
        dungeon_delta += max(0, val - old_runs.get(key, 0))

    if own_conn:
        conn.close()

    return {
        "has_previous": True,
        "older_id": older_id,
        "newer_id": snapshot_id,
        "coins_delta": diff["summary"]["coins_delta"],
        "total_level_delta": diff["summary"]["total_level_delta"],
        "inventory_changes": len(diff["inventory_changes"]),
        "skill_changes": len(diff["skill_changes"]),
        "quests_completed": quests_completed,
        "slayer_kills_delta": max(0, slayer_delta),
        "dungeon_runs_delta": dungeon_delta,
        "top_inventory": diff["inventory_changes"][:5],
        "top_skills": diff["skill_changes"][:5],
    }


def skill_timeline(db_path: Path | str = DEFAULT_DB) -> dict[str, Any]:
    """Per-skill level series aligned to snapshots (oldest → newest)."""
    conn = get_connection(db_path)
    init_db(conn)
    snap_rows = conn.execute(
        """
        SELECT id, imported_at, exported_at FROM snapshots
        ORDER BY exported_at ASC, id ASC
        """
    ).fetchall()
    snapshots = [dict(r) for r in snap_rows]
    if not snapshots:
        conn.close()
        return {"snapshots": [], "series": {}}

    snap_index = {row["id"]: idx for idx, row in enumerate(snapshots)}
    skill_rows = conn.execute(
        "SELECT snapshot_id, skill_key, level FROM skill_snapshots"
    ).fetchall()
    conn.close()

    series: dict[str, list[int]] = {}
    n = len(snapshots)
    for row in skill_rows:
        key = row["skill_key"]
        if key not in series:
            series[key] = [0] * n
        idx = snap_index.get(row["snapshot_id"])
        if idx is not None:
            series[key][idx] = row["level"]

    for key in series:
        last = 0
        for i in range(n):
            if series[key][i] > 0:
                last = series[key][i]
            elif last > 0:
                series[key][i] = last

    return {"snapshots": snapshots, "series": series}


def _forward_fill_positive(series: dict[str, list[int]]) -> None:
    for key in series:
        last = 0
        for i in range(len(series[key])):
            if series[key][i] > 0:
                last = series[key][i]
            elif last > 0:
                series[key][i] = last


def combat_timeline(db_path: Path | str = DEFAULT_DB) -> dict[str, Any]:
    """Enemy-kill and dungeon-run series aligned to snapshots (oldest → newest)."""
    conn = get_connection(db_path)
    init_db(conn)
    snap_rows = conn.execute(
        """
        SELECT id, imported_at, exported_at, raw_json FROM snapshots
        ORDER BY exported_at ASC, id ASC
        """
    ).fetchall()
    conn.close()

    snapshots = [
        {"id": r["id"], "imported_at": r["imported_at"], "exported_at": r["exported_at"]}
        for r in snap_rows
    ]
    if not snapshots:
        return {"snapshots": [], "enemy_kills": {}, "dungeon_runs": {}}

    n = len(snapshots)
    enemy_kills: dict[str, list[int]] = {}
    dungeon_runs: dict[str, list[int]] = {}

    for idx, row in enumerate(snap_rows):
        try:
            data = json.loads(row["raw_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        combat = data.get("combat") or {}
        for key, qty in (combat.get("enemy_kills") or {}).items():
            if key not in enemy_kills:
                enemy_kills[key] = [0] * n
            enemy_kills[key][idx] = int(qty) if qty else 0
        for key, qty in (combat.get("dungeon_runs") or {}).items():
            if key not in dungeon_runs:
                dungeon_runs[key] = [0] * n
            dungeon_runs[key][idx] = int(qty) if qty else 0

    _forward_fill_positive(enemy_kills)
    _forward_fill_positive(dungeon_runs)

    return {"snapshots": snapshots, "enemy_kills": enemy_kills, "dungeon_runs": dungeon_runs}


def delete_snapshot(snapshot_id: int, db_path: Path | str = DEFAULT_DB) -> bool:
    conn = get_connection(db_path)
    init_db(conn)
    cur = conn.execute("DELETE FROM snapshots WHERE id = ?", (snapshot_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted
