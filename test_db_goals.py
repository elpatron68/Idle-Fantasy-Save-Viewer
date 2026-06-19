"""Smoke tests for extended goals / import helpers."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from db import (
    create_goal,
    create_goal_group,
    create_skill_goal,
    delete_snapshot,
    get_connection,
    goals_overview,
    import_save,
    init_db,
    list_goals_structured,
    rename_goal_group,
    skill_timeline,
    summarize_import_changes,
)
from viewers import inspect_viewer_db, restore_viewer_db


def _minimal_save(coins: int = 100, level: int = 5) -> dict:
    return {
        "exported_at": 1_700_000_000_000 + coins,
        "coins": coins,
        "character_name": "Tester",
        "skillLevels": {"mining": 10, "woodcutting": 5},
        "skillXp": {"mining": 1000, "woodcutting": 200},
        "inventory": {"iron_ore": 50, "logs": 20},
    }


def test_relative_and_skill_goals() -> None:
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.db"
        conn = get_connection(db)
        init_db(conn)
        conn.close()

        save_path = Path(td) / "save.json"
        save_path.write_text(json.dumps(_minimal_save()), encoding="utf-8")
        r1 = import_save(save_path, db_path=db)
        assert r1["imported"]

        gid = create_goal_group("Mining", db_path=db)["id"]
        goal = create_goal("iron_ore", 20, group_id=gid, mode="relative", db_path=db)
        assert goal["mode"] == "relative"
        assert goal["baseline_qty"] == 50
        assert not goal["completed_at"]

        skill_goal = create_skill_goal("mining", 15, mode="absolute", db_path=db)
        assert skill_goal["goal_type"] == "skill"
        assert skill_goal["skill_key"] == "mining"

        overview = goals_overview(db_path=db)
        assert overview["total"] == 2
        assert overview["open"] == 2

        save_path.write_text(json.dumps(_minimal_save(coins=200, level=6)), encoding="utf-8")
        r2 = import_save(save_path, db_path=db)
        assert r2["imported"]
        assert r2["import_changes"]["has_previous"]
        assert r2["import_changes"]["coins_delta"] == 100

        structured = list_goals_structured(db_path=db)
        assert len(structured["groups"]) == 1
        assert rename_goal_group(gid, "Mining Goals", db_path=db)

        tl = skill_timeline(db_path=db)
        assert len(tl["snapshots"]) == 2
        assert "mining" in tl["series"]

        snaps = r2.get("snapshot_id")
        assert delete_snapshot(snaps - 1, db_path=db)
        changes = summarize_import_changes(snaps, db_path=db)
        assert changes["has_previous"] is False

        db2 = Path(td) / "restored.db"
        stats = restore_viewer_db(db, db2)
        assert stats["snapshots"] >= 1
        assert stats["goals"] == 2
        inspected = inspect_viewer_db(db2)
        assert inspected["goal_groups"] == 1

        print("all tests passed")


if __name__ == "__main__":
    test_relative_and_skill_goals()
