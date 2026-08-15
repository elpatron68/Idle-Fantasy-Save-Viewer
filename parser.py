"""Parse and normalize Idle Fantasy Android save files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from categories import categorize_item
from validation import Issue, analyze_save, has_errors, issue


class SaveParseError(Exception):
    """Save cannot be imported."""

    def __init__(self, message: str, issues: list[Issue] | None = None):
        super().__init__(message)
        self.issues = issues or []


def _maybe_parse_json(value: Any, field_path: str, failures: list[str]) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                failures.append(field_path)
                return value
    return value


def _deep_parse(obj: Any, path: str = "", failures: list[str] | None = None) -> Any:
    failures = failures if failures is not None else []
    if isinstance(obj, dict):
        return {
            k: _deep_parse(_maybe_parse_json(v, f"{path}.{k}" if path else k, failures), f"{path}.{k}" if path else k, failures)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [
            _deep_parse(_maybe_parse_json(v, f"{path}[{i}]", failures), f"{path}[{i}]", failures)
            for i, v in enumerate(obj)
        ]
    return obj


def _ensure_dict(value: Any, field: str, issues: list[Issue]) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    issues.append(issue(
        "warning", "coerced_empty_dict",
        f'Field "{field}" is not an object – treated as empty.',
        field=field,
        params={"field": field},
    ))
    return {}


def _ensure_list(value: Any, field: str, issues: list[Issue]) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    issues.append(issue(
        "warning", "coerced_empty_list",
        f'Field "{field}" is not a list – skipped.',
        field=field,
        params={"field": field},
    ))
    return []


def _safe_int(value: Any, field: str, issues: list[Issue], default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        issues.append(issue(
            "warning", "invalid_number",
            f'Invalid number in "{field}".',
            field=field,
            params={"field": field, "detail": ""},
        ))
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        issues.append(issue(
            "warning", "invalid_number",
            f'Invalid number in "{field}": {value!r}.',
            field=field,
            params={"field": field, "detail": f": {value!r}"},
        ))
        return default


def xp_for_level(level: int) -> int:
    if level <= 1:
        return 0
    total = 0
    for lv in range(1, level):
        total += int(lv + 300 * (2 ** (lv / 7.0)))
    return total // 4


def xp_to_next_level(level: int, xp: int) -> dict[str, int | float]:
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
    return str(key).replace("_", " ").title()


def format_key(key: str) -> str:
    return str(key).replace("_", " ").title()


def _normalize_slayer_task(task: Any) -> dict[str, Any] | None:
    """Upstream dropped display_name; derive it from enemy_key when missing."""
    if not isinstance(task, dict):
        return None
    enemy_key = str(task.get("enemy_key") or "")
    display = task.get("display_name")
    if not display:
        display = format_key(enemy_key) if enemy_key else None
    return {
        "enemy_key": enemy_key or None,
        "display_name": display,
        "target_kills": int(task.get("target_kills") or 0),
        "kills_completed": int(task.get("kills_completed") or 0),
        "xp_per_kill": int(task.get("xp_per_kill") or 0),
        "task_points": int(task.get("task_points") or 0),
    }


def _normalize_worker(raw: Any, slot: int) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    tier = raw.get("tier")
    queue = raw.get("session_queue")
    return {
        "slot": slot,
        "tier": tier,
        "tier_name": format_key(str(tier)) if tier else None,
        "name": raw.get("daily_name"),
        "queue": queue if isinstance(queue, list) else [],
    }


def _normalize_loadouts(raw: Any, issues: list[Issue]) -> list[dict[str, Any]]:
    loadouts_raw = _ensure_dict(raw, "flags.armor_loadouts", issues)
    result = []
    for style, slots in loadouts_raw.items():
        if not isinstance(slots, dict):
            continue
        items = []
        for slot, item_key in slots.items():
            items.append({
                "slot": str(slot),
                "slot_name": format_key(str(slot)),
                "key": item_key,
                "name": format_item_name(str(item_key)) if item_key else None,
            })
        result.append({
            "style": str(style),
            "style_name": format_key(str(style)),
            "items": items,
        })
    return result


def _normalize_dungeon_last_runs(raw: Any, issues: list[Issue]) -> list[dict[str, Any]]:
    stats_raw = _ensure_dict(raw, "flags.dungeon_last_run_stats", issues)
    result = []
    for key, stats in stats_raw.items():
        if not isinstance(stats, dict):
            continue
        result.append({
            "key": str(key),
            "name": format_key(str(key)),
            "food_consumed": _safe_int(stats.get("food_consumed"), f"dungeon_last_run.{key}.food", issues),
            "kill_count": _safe_int(stats.get("kill_count"), f"dungeon_last_run.{key}.kills", issues),
            "survived": bool(stats.get("survived", True)),
        })
    result.sort(key=lambda row: row["kill_count"], reverse=True)
    return result


def _normalize_seasonal(flags: dict[str, Any], issues: list[Issue]) -> dict[str, Any]:
    banners_raw = flags.get("seasonal_banners_earned")
    banners = []
    if isinstance(banners_raw, list):
        for entry in banners_raw:
            if not isinstance(entry, dict):
                continue
            banners.append({
                "event_id": entry.get("event_id"),
                "name": entry.get("event_display_name") or format_key(str(entry.get("event_id") or "")),
                "display_text": entry.get("display_text"),
                "completed_at": entry.get("completed_at_ms"),
            })
    elif banners_raw is not None:
        issues.append(issue("warning", "invalid_type", 'Field "seasonal_banners_earned" is not a list.', field="flags.seasonal_banners_earned"))

    progress = _ensure_dict(flags.get("seasonal_bounty_progress"), "flags.seasonal_bounty_progress", issues)
    slots = _ensure_list(flags.get("seasonal_bounty_slots"), "flags.seasonal_bounty_slots", issues)
    bounties = []
    for slot_id in slots:
        key = str(slot_id)
        bounties.append({
            "id": key,
            "name": format_key(key),
            "progress": _safe_int(progress.get(key, progress.get(slot_id)), f"seasonal_bounty.{key}", issues),
        })

    tokens = _ensure_dict(flags.get("seasonal_tokens_by_event"), "flags.seasonal_tokens_by_event", issues)
    return {
        "event_id": flags.get("seasonal_bounty_event_id"),
        "tokens": {str(k): _safe_int(v, f"seasonal_tokens.{k}", issues) for k, v in tokens.items()},
        "bounties": bounties,
        "banners": banners,
    }


KNOWN_EXPORT_KEYS = frozenset({
    "skillLevels", "skillXp", "inventory", "equipped", "flags",
    "pets", "coins", "questProgress", "farmingPatches", "sessions",
    "exported_at", "sig",
})


def load_save(path: str | Path) -> tuple[dict[str, Any], list[str]]:
    path = Path(path)
    try:
        with path.open(encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as exc:
        raise SaveParseError(f"Invalid JSON file: {exc}") from exc
    except OSError as exc:
        raise SaveParseError(f"Could not read file: {exc}") from exc

    failures: list[str] = []
    parsed = _deep_parse(raw, failures=failures)
    if not isinstance(parsed, dict):
        raise SaveParseError("The file must contain a JSON object.")
    return parsed, failures


def normalize_save(
    raw: dict[str, Any],
    source_file: str = "",
    issues: list[Issue] | None = None,
    nested_failures: list[str] | None = None,
) -> dict[str, Any]:
    issues = list(issues or [])
    issues.extend(analyze_save(raw, nested_failures))

    if has_errors(issues):
        fatal = next(i for i in issues if i["level"] == "error")
        raise SaveParseError(fatal["message"], issues)

    flags = _ensure_dict(raw.get("flags"), "flags", issues)
    skill_levels = _ensure_dict(raw.get("skillLevels"), "skillLevels", issues)
    skill_xp = _ensure_dict(raw.get("skillXp"), "skillXp", issues)
    inventory = _ensure_dict(raw.get("inventory"), "inventory", issues)
    equipped = _ensure_dict(raw.get("equipped"), "equipped", issues)
    equipped_values = {v for v in equipped.values() if v}
    prestige_map = _ensure_dict(flags.get("skill_prestige"), "flags.skill_prestige", issues)
    fertilizer = _ensure_dict(flags.get("farming_fertilizer"), "flags.farming_fertilizer", issues)

    inventory_items = []
    for key, qty_raw in sorted(inventory.items()):
        qty = _safe_int(qty_raw, f"inventory.{key}", issues, default=-1)
        if qty <= 0:
            if qty < 0:
                continue
            continue
        item_key = str(key)
        inventory_items.append({
            "key": item_key,
            "name": format_item_name(item_key),
            "qty": qty,
            "category": categorize_item(item_key),
            "equipped": item_key in equipped_values,
        })

    all_skill_keys = set(skill_levels) | set(skill_xp)
    skills = []
    total_level = 0
    for key in sorted(all_skill_keys):
        level = _safe_int(skill_levels.get(key, 1), f"skillLevels.{key}", issues, default=1)
        xp = _safe_int(skill_xp.get(key, 0), f"skillXp.{key}", issues, default=0)
        total_level += level
        prog = xp_to_next_level(level, xp)
        skills.append({
            "key": str(key),
            "name": format_key(str(key)),
            "level": level,
            "xp": xp,
            "prestige": _safe_int(prestige_map.get(key, 0), f"skill_prestige.{key}", issues),
            **prog,
        })

    equipment = []
    for slot, item_key in equipped.items():
        equipment.append({
            "slot": str(slot),
            "slot_name": format_key(str(slot)),
            "key": item_key,
            "name": format_item_name(str(item_key)) if item_key else None,
        })

    story_quests = []
    for idx, q in enumerate(_ensure_list(raw.get("questProgress"), "questProgress", issues)):
        if not isinstance(q, dict):
            issues.append(issue(
                "warning", "invalid_quest_entry",
                f"Quest entry #{idx + 1} is not an object and was skipped.",
                field="questProgress",
                params={"index": idx + 1},
            ))
            continue
        quest_id = q.get("questId") or q.get("id") or f"unknown_{idx}"
        story_quests.append({
            "id": quest_id,
            "name": format_key(str(quest_id)),
            "progress": _safe_int(q.get("progress"), f"questProgress[{idx}].progress", issues),
            "completed": bool(q.get("completed")),
            "completed_at": q.get("completedAt"),
        })

    daily_quests = _build_flag_quests(
        flags.get("daily_quest_ids"),
        flags.get("daily_quest_progress"),
        flags.get("daily_quest_claimed"),
        "daily_quest", issues,
    )
    weekly_quests = _build_flag_quests(
        flags.get("weekly_quest_ids"),
        flags.get("weekly_quest_progress"),
        flags.get("weekly_quest_claimed"),
        "weekly_quest", issues,
    )
    guild_quests = _build_flag_quests(
        flags.get("guild_daily_ids"),
        flags.get("guild_daily_progress"),
        flags.get("guild_daily_claimed"),
        "guild_daily", issues,
    )

    sessions = []
    for idx, s in enumerate(_ensure_list(raw.get("sessions"), "sessions", issues)):
        if not isinstance(s, dict):
            issues.append(issue(
                "warning", "invalid_session_entry",
                f"Session entry #{idx + 1} is not an object and was skipped.",
                field="sessions",
                params={"index": idx + 1},
            ))
            continue
        frames = s.get("frames")
        if isinstance(frames, str):
            issues.append(issue(
                "warning", "unparsed_session_frames",
                f"Session #{idx + 1}: activity frames could not be read.",
                field="sessions",
                params={"index": idx + 1},
            ))
            frames = []
        elif not isinstance(frames, list):
            frames = []
        total_xp = sum(_safe_int(f.get("xp_gain"), f"sessions[{idx}].xp", issues) for f in frames if isinstance(f, dict))
        total_kills = sum(_safe_int(f.get("kills"), f"sessions[{idx}].kills", issues) for f in frames if isinstance(f, dict))
        sessions.append({
            "id": s.get("session_id"),
            "skill": s.get("skill_name"),
            "activity": s.get("activity_key"),
            "started_at": s.get("started_at"),
            "ends_at": s.get("ends_at"),
            "completed": s.get("completed"),
            "total_xp": total_xp,
            "total_kills": total_kills,
            "frame_count": len(frames),
            "is_worker": bool(s.get("is_worker_session")),
            "worker_slot": s.get("worker_slot"),
            "efficiency": s.get("efficiency_multiplier"),
        })

    pets_raw = raw.get("pets")
    pets: list[Any] = []
    if isinstance(pets_raw, list):
        pets = pets_raw
    elif pets_raw is not None:
        issues.append(issue("warning", "invalid_pets", 'Field "pets" is not a list.', field="pets"))

    farming = []
    for idx, patch in enumerate(_ensure_list(raw.get("farmingPatches"), "farmingPatches", issues)):
        if isinstance(patch, dict):
            patch_no = patch.get("patchNumber", idx + 1)
            fert_key = fertilizer.get(str(patch_no), fertilizer.get(patch_no))
            farming.append({
                **patch,
                "fertilizer": fert_key,
            })
        else:
            issues.append(issue(
                "warning", "invalid_farming_patch",
                f"Farming patch #{idx + 1} was skipped.",
                field="farmingPatches",
                params={"index": idx + 1},
            ))

    notes = flags.get("player_notes")
    if isinstance(notes, str):
        notes = notes.strip() or None
    else:
        notes = None

    titles_raw = flags.get("unlocked_titles")
    if isinstance(titles_raw, list):
        unlocked_titles = [format_key(str(t)) for t in titles_raw]
        unlocked_title_keys = [str(t) for t in titles_raw]
    elif isinstance(titles_raw, (set, tuple)):
        unlocked_title_keys = [str(t) for t in titles_raw]
        unlocked_titles = [format_key(k) for k in unlocked_title_keys]
    else:
        unlocked_title_keys = []
        unlocked_titles = []

    loadouts = _normalize_loadouts(flags.get("armor_loadouts"), issues)
    enemy_kills = _ensure_dict(flags.get("enemy_kills"), "flags.enemy_kills", issues)
    dungeon_runs = _ensure_dict(flags.get("dungeon_runs"), "flags.dungeon_runs", issues)
    dungeon_last_runs = _normalize_dungeon_last_runs(flags.get("dungeon_last_run_stats"), issues)
    unlocked_dungeons = [
        {"key": str(k), "name": format_key(str(k))}
        for k in _ensure_list(flags.get("unlocked_dungeons"), "flags.unlocked_dungeons", issues)
    ]
    skilling_notes = {
        str(k): _safe_int(v, f"skilling_dungeon_notes.{k}", issues)
        for k, v in _ensure_dict(flags.get("skilling_dungeon_notes"), "flags.skilling_dungeon_notes", issues).items()
    }
    slayer_points = _safe_int(flags.get("slayer_points"), "flags.slayer_points", issues)
    foretold_tasks = [
        task for task in (
            _normalize_slayer_task(entry)
            for entry in _ensure_list(flags.get("foretelled_tasks"), "flags.foretelled_tasks", issues)
        ) if task
    ]
    guild_reputation = _ensure_dict(flags.get("guild_reputation"), "flags.guild_reputation", issues)
    tower = {
        "current_floor": _safe_int(flags.get("tower_current_floor"), "flags.tower_current_floor", issues),
        "best_floor": _safe_int(flags.get("tower_best_floor"), "flags.tower_best_floor", issues),
        "milestones": [
            _safe_int(n, "flags.tower_milestones", issues)
            for n in _ensure_list(flags.get("tower_milestones"), "flags.tower_milestones", issues)
        ],
        "xp_bonus_pct": _safe_int(flags.get("tower_xp_bonus_pct"), "flags.tower_xp_bonus_pct", issues),
        "hp_bonus": _safe_int(flags.get("tower_hp_bonus"), "flags.tower_hp_bonus", issues),
        "coin_bonus_pct": _safe_int(flags.get("tower_coin_bonus_pct"), "flags.tower_coin_bonus_pct", issues),
    }
    monument = {
        "tier": _safe_int(flags.get("monument_tier"), "flags.monument_tier", issues),
        "fund": _safe_int(flags.get("monument_fund"), "flags.monument_fund", issues),
    }
    seasonal = _normalize_seasonal(flags, issues)
    session_queue = _ensure_list(flags.get("session_queue"), "flags.session_queue", issues)
    recent_sessions = _ensure_list(flags.get("recent_sessions"), "flags.recent_sessions", issues)
    town_buildings = _ensure_dict(flags.get("town_building_tiers"), "flags.town_building_tiers", issues)
    coins = _safe_int(raw.get("coins"), "coins", issues)
    inventory_coins = _safe_int(inventory.get("coins"), "inventory.coins", issues)

    if not flags.get("character_name"):
        issues.append(issue(
            "warning", "missing_character_name",
            "No character name found in save.",
            field="flags.character_name",
        ))

    dungeon_stats_raw = _ensure_dict(
        flags.get("dungeon_last_run_stats"), "flags.dungeon_last_run_stats", issues,
    )
    dungeon_stats: dict[str, dict[str, Any]] = {}
    for key, stats in dungeon_stats_raw.items():
        if not isinstance(stats, dict):
            continue
        dungeon_stats[str(key)] = {
            "food_consumed": _safe_int(
                stats.get("food_consumed"), f"flags.dungeon_last_run_stats.{key}.food_consumed", issues,
            ),
            "kill_count": _safe_int(
                stats.get("kill_count"), f"flags.dungeon_last_run_stats.{key}.kill_count", issues,
            ),
            "survived": bool(stats.get("survived")),
        }

    workers: list[dict[str, Any]] = []
    for slot, flag_key in ((1, "hired_worker"), (2, "hired_worker_2")):
        worker = flags.get(flag_key)
        if isinstance(worker, dict) and worker:
            tier = worker.get("tier")
            workers.append({
                "slot": slot,
                "tier": tier,
                "tier_name": format_key(str(tier)) if tier else None,
                "daily_name": worker.get("daily_name"),
                "name": worker.get("daily_name"),
                "session_queue": _ensure_list(
                    worker.get("session_queue"), f"flags.{flag_key}.session_queue", issues,
                ),
                "queue": _ensure_list(
                    worker.get("session_queue"), f"flags.{flag_key}.session_queue", issues,
                ),
            })

    carnival_cooldowns = {
        "ring_toss": flags.get("carnival_ring_toss_cooldown_at"),
        "hammer_strike": flags.get("carnival_hammer_strike_cooldown_at"),
        "potion_sequence": flags.get("carnival_potion_sequence_cooldown_at"),
        "item_appraisal": flags.get("carnival_item_appraisal_cooldown_at"),
        "shell_game": flags.get("carnival_shell_game_cooldown_at"),
        "higher_lower": flags.get("carnival_higher_lower_cooldown_at"),
    }

    titles_flag = flags.get("unlocked_titles")
    if titles_flag is not None and not isinstance(titles_flag, list):
        issues.append(issue(
            "warning", "invalid_titles_list",
            'Field "flags.unlocked_titles" is not a list.',
            field="flags.unlocked_titles",
        ))
        titles_flag = []
    if isinstance(titles_flag, list):
        unlocked_title_keys = [str(t) for t in titles_flag]
        unlocked_titles = [format_key(str(t)) for t in titles_flag]

    # Deduplizieren (gleicher code+field+message)
    seen = set()
    unique_issues: list[Issue] = []
    for item in issues:
        key = (item["level"], item["code"], item.get("field"), item["message"])
        if key not in seen:
            seen.add(key)
            unique_issues.append(item)

    warning_count = sum(1 for i in unique_issues if i["level"] == "warning")
    info_count = sum(1 for i in unique_issues if i["level"] == "info")

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
            "ironman": bool(flags.get("ironman")),
            "title": flags.get("equipped_title"),
            "title_name": format_key(str(flags.get("equipped_title"))) if flags.get("equipped_title") else None,
            "equipped_title": flags.get("equipped_title"),
            "unlocked_titles": unlocked_titles,
            "unlocked_title_keys": unlocked_title_keys,
            "notes": notes,
            "player_notes": notes or flags.get("player_notes"),
        },
        "skills": skills,
        "inventory": inventory_items,
        "equipment": equipment,
        "loadouts": loadouts,
        "quests": {
            "story": story_quests,
            "daily": daily_quests,
            "weekly": weekly_quests,
            "guild": guild_quests,
            "weekly_bonus_claimed": bool(flags.get("weekly_bonus_claimed")),
        },
        "combat": {
            "enemy_kills": enemy_kills,
            "dungeon_runs": dungeon_runs,
            "dungeon_last_runs": dungeon_last_runs,
            "unlocked_dungeons": unlocked_dungeons,
            "skilling_notes": skilling_notes,
            "slayer_task": _normalize_slayer_task(flags.get("active_slayer_task")),
            "slayer_points": slayer_points,
            "foretold_tasks": foretold_tasks,
        },
        "guild_reputation": guild_reputation,
        "pets": pets,
        "farming": farming,
        "farming_fertilizer": fertilizer,
        "workers": workers,
        "tower": tower,
        "monument": monument,
        "seasonal": {
            "tokens_by_event": _ensure_dict(
                flags.get("seasonal_tokens_by_event"), "flags.seasonal_tokens_by_event", issues,
            ),
            "active_event_id": flags.get("seasonal_bounty_event_id"),
            "bounty_slots": _ensure_list(flags.get("seasonal_bounty_slots"), "flags.seasonal_bounty_slots", issues),
            "bounty_progress": _ensure_dict(
                flags.get("seasonal_bounty_progress"), "flags.seasonal_bounty_progress", issues,
            ),
            "bounty_cooldowns": _ensure_dict(
                flags.get("seasonal_bounty_slot_cooldown"), "flags.seasonal_bounty_slot_cooldown", issues,
            ),
            "minigame_cooldown_at": flags.get("seasonal_minigame_cooldown_at"),
            "minigame_easy_mode": bool(flags.get("seasonal_minigame_easy_mode")),
            "banners_earned": _ensure_list(flags.get("seasonal_banners_earned"), "flags.seasonal_banners_earned", issues),
            "event_id": flags.get("seasonal_bounty_event_id"),
            "tokens": {
                str(k): _safe_int(v, f"seasonal_tokens.{k}", issues)
                for k, v in _ensure_dict(
                    flags.get("seasonal_tokens_by_event"), "flags.seasonal_tokens_by_event", issues,
                ).items()
            },
            "bounties": seasonal.get("bounties", []),
            "banners": seasonal.get("banners", []),
        },
        "carnival": {
            "tab": _safe_int(flags.get("carnival_tab"), "flags.carnival_tab", issues),
            "difficulties": _ensure_dict(flags.get("carnival_difficulties"), "flags.carnival_difficulties", issues),
            "cooldowns": carnival_cooldowns,
        },
        "titles": {
            "unlocked": unlocked_title_keys,
            "equipped": flags.get("equipped_title"),
        },
        "expeditions": {
            "unlocked": _ensure_list(flags.get("unlocked_dungeons"), "flags.unlocked_dungeons", issues),
            "notes": _ensure_dict(flags.get("skilling_dungeon_notes"), "flags.skilling_dungeon_notes", issues),
            "pity": _ensure_dict(flags.get("expedition_pity_runs"), "flags.expedition_pity_runs", issues),
        },
        "dungeon_stats": dungeon_stats,
        "session_queue": session_queue,
        "recent_sessions": recent_sessions,
        "sessions": sessions,
        "town_buildings": town_buildings,
        "meta": {
            "source_file": source_file,
            "exported_at": raw.get("exported_at"),
            "coins": coins,
            "inventory_coins": inventory_coins,
            "total_level": total_level,
            "item_count": len(inventory_items),
            "total_items": sum(i["qty"] for i in inventory_items),
            "version_code": flags.get("last_seen_version_code"),
            "signed": bool(raw.get("sig")),
            "import_report": unique_issues,
            "import_summary": {
                "ok": True,
                "warnings": warning_count,
                "infos": info_count,
            },
        },
        # Unbekannte Top-Level-Felder für spätere Auswertung durchreichen
        "extensions": {
            k: raw[k] for k in raw if k not in KNOWN_EXPORT_KEYS
        } if isinstance(raw, dict) else {},
    }


def _build_flag_quests(
    ids: Any,
    progress: Any,
    claimed: Any,
    label: str,
    issues: list[Issue],
) -> list[dict[str, Any]]:
    id_list = ids if isinstance(ids, list) else []
    if ids is not None and not isinstance(ids, list):
        issues.append(issue(
            "warning", "invalid_quest_ids",
            f"Quest IDs ({label}) are not a list.",
            field=label,
            params={"label": label},
        ))
    progress_map = progress if isinstance(progress, dict) else {}
    if progress is not None and not isinstance(progress, dict):
        issues.append(issue(
            "warning", "invalid_quest_progress",
            f"Quest progress ({label}) is not an object.",
            field=label,
            params={"label": label},
        ))
    claimed_list = claimed if isinstance(claimed, list) else []
    claimed_set = set(claimed_list)

    result = []
    for qid in id_list:
        qid_str = str(qid)
        result.append({
            "id": qid_str,
            "name": format_key(qid_str),
            "progress": _safe_int(progress_map.get(qid), f"{label}.{qid_str}", issues),
            "claimed": qid_str in claimed_set or qid in claimed_set,
        })
    return result


def parse_save_file(path: str | Path) -> tuple[dict[str, Any], list[Issue]]:
    path = Path(path)
    raw, failures = load_save(path)
    data = normalize_save(raw, source_file=path.name, nested_failures=failures)
    return data, data["meta"]["import_report"]
