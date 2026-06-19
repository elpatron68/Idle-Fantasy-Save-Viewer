"""Parse and normalize Idle Fantasy Android save files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from categories import categorize_item


def _maybe_parse_json(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return value
    return value


def _deep_parse(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _deep_parse(_maybe_parse_json(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_parse(_maybe_parse_json(v)) for v in obj]
    return obj


def xp_for_level(level: int) -> int:
    """Approximate cumulative XP threshold (OSRS-style curve)."""
    if level <= 1:
        return 0
    total = 0
    for lv in range(1, level):
        total += int(lv + 300 * (2 ** (lv / 7.0)))
    return total // 4


def xp_to_next_level(level: int, xp: int) -> dict[str, int]:
    current_threshold = xp_for_level(level)
    next_threshold = xp_for_level(level + 1)
    span = max(next_threshold - current_threshold, 1)
    progress = max(0, min(xp - current_threshold, span))
    return {
        "xp_in_level": progress,
        "xp_needed": span,
        "progress_pct": round(100 * progress / span, 1),
    }


def format_item_name(key: str) -> str:
    return key.replace("_", " ").title()


def format_key(key: str) -> str:
    return key.replace("_", " ").title()


def load_save(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)
    return _deep_parse(raw)


def normalize_save(raw: dict[str, Any], source_file: str = "") -> dict[str, Any]:
    flags = raw.get("flags") or {}
    skill_levels = raw.get("skillLevels") or {}
    skill_xp = raw.get("skillXp") or {}
    inventory = raw.get("inventory") or {}
    equipped = raw.get("equipped") or {}
    equipped_values = {v for v in equipped.values() if v}

    inventory_items = []
    for key, qty in sorted(inventory.items()):
        if qty <= 0:
            continue
        inventory_items.append({
            "key": key,
            "name": format_item_name(key),
            "qty": qty,
            "category": categorize_item(key),
            "equipped": key in equipped_values,
        })

    skills = []
    total_level = 0
    for key in sorted(skill_levels.keys()):
        level = int(skill_levels[key])
        xp = int(skill_xp.get(key, 0))
        total_level += level
        prog = xp_to_next_level(level, xp)
        skills.append({
            "key": key,
            "name": format_key(key),
            "level": level,
            "xp": xp,
            **prog,
        })

    equipment = []
    for slot, item_key in equipped.items():
        equipment.append({
            "slot": slot,
            "slot_name": format_key(slot),
            "key": item_key,
            "name": format_item_name(item_key) if item_key else None,
        })

    story_quests = []
    for q in raw.get("questProgress") or []:
        story_quests.append({
            "id": q.get("questId"),
            "name": format_key(q.get("questId", "")),
            "progress": q.get("progress", 0),
            "completed": bool(q.get("completed")),
            "completed_at": q.get("completedAt"),
        })

    daily_quests = _build_flag_quests(
        flags.get("daily_quest_ids") or [],
        flags.get("daily_quest_progress") or {},
        flags.get("daily_quest_claimed") or [],
    )
    weekly_quests = _build_flag_quests(
        flags.get("weekly_quest_ids") or [],
        flags.get("weekly_quest_progress") or {},
        flags.get("weekly_quest_claimed") or [],
    )
    guild_quests = _build_flag_quests(
        flags.get("guild_daily_ids") or [],
        flags.get("guild_daily_progress") or {},
        flags.get("guild_daily_claimed") or [],
    )

    sessions = []
    for s in raw.get("sessions") or []:
        frames = s.get("frames") or []
        total_xp = sum(f.get("xp_gain", 0) for f in frames) if isinstance(frames, list) else 0
        total_kills = sum(f.get("kills", 0) for f in frames) if isinstance(frames, list) else 0
        sessions.append({
            "id": s.get("session_id"),
            "skill": s.get("skill_name"),
            "activity": s.get("activity_key"),
            "started_at": s.get("started_at"),
            "ends_at": s.get("ends_at"),
            "completed": s.get("completed"),
            "total_xp": total_xp,
            "total_kills": total_kills,
            "frame_count": len(frames) if isinstance(frames, list) else 0,
        })

    return {
        "character": {
            "name": flags.get("character_name"),
            "gender": flags.get("character_gender"),
            "race": flags.get("character_race"),
            "hp": flags.get("current_hp"),
            "active_potion": flags.get("active_potion_key"),
            "active_spell": flags.get("active_spell"),
            "active_weapon_slot": flags.get("active_weapon_slot"),
            "active_blessing": flags.get("active_blessing_key"),
            "blessing_expires_at": flags.get("active_blessing_expires_at"),
            "theme": flags.get("theme_preference"),
        },
        "skills": skills,
        "inventory": inventory_items,
        "equipment": equipment,
        "quests": {
            "story": story_quests,
            "daily": daily_quests,
            "weekly": weekly_quests,
            "guild": guild_quests,
        },
        "combat": {
            "enemy_kills": flags.get("enemy_kills") or {},
            "dungeon_runs": flags.get("dungeon_runs") or {},
            "slayer_task": flags.get("active_slayer_task"),
            "slayer_points": flags.get("slayer_points", 0),
        },
        "guild_reputation": flags.get("guild_reputation") or {},
        "pets": raw.get("pets") or [],
        "farming": raw.get("farmingPatches") or [],
        "farming_fertilizer": flags.get("farming_fertilizer") or {},
        "session_queue": flags.get("session_queue") or [],
        "recent_sessions": flags.get("recent_sessions") or [],
        "sessions": sessions,
        "town_buildings": flags.get("town_building_tiers") or {},
        "meta": {
            "source_file": source_file,
            "exported_at": raw.get("exported_at"),
            "coins": raw.get("coins", 0),
            "inventory_coins": inventory.get("coins", 0),
            "total_level": total_level,
            "item_count": len(inventory_items),
            "total_items": sum(i["qty"] for i in inventory_items),
            "version_code": flags.get("last_seen_version_code"),
        },
    }


def _build_flag_quests(
    ids: list[str],
    progress: dict[str, int],
    claimed: list[str],
) -> list[dict[str, Any]]:
    claimed_set = set(claimed or [])
    result = []
    for qid in ids:
        result.append({
            "id": qid,
            "name": format_key(qid),
            "progress": progress.get(qid, 0),
            "claimed": qid in claimed_set,
        })
    return result


def parse_save_file(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    raw = load_save(path)
    return normalize_save(raw, source_file=path.name)
