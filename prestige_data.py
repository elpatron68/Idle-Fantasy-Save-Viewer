"""Load vendored Idle Fantasy prestige tree metadata and compute node state."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

GAME_DATA_ROOT = Path(__file__).parent / "game_data"
PRESTIGE_PATHS_PATH = GAME_DATA_ROOT / "prestige_paths.json"


def _format_key(key: str) -> str:
    return str(key).replace("_", " ").title()


@lru_cache(maxsize=1)
def _load_prestige_trees() -> dict[str, dict[str, Any]]:
    if not PRESTIGE_PATHS_PATH.is_file():
        return {}
    raw = json.loads(PRESTIGE_PATHS_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return {}
    return {str(entry["skill"]): entry for entry in raw if isinstance(entry, dict) and entry.get("skill")}


def prestige_tree_skills() -> list[str]:
    return sorted(_load_prestige_trees().keys())


def player_race(character_race: str | None) -> str:
    race = str(character_race or "human").strip().lower()
    return race or "human"


def is_node_available_to_race(node: dict[str, Any], race: str) -> bool:
    races = node.get("races")
    if not races:
        return True
    return race in races


def spent_points(skill_key: str, owned_ids: set[str]) -> int:
    tree = _load_prestige_trees().get(skill_key)
    if not tree:
        return 0
    total = 0
    for path in tree.get("paths") or []:
        if path.get("auto"):
            continue
        for node in path.get("nodes") or []:
            if str(node.get("id") or "") in owned_ids:
                total += int(node.get("cost") or 0)
    return total


def point_cap(skill_key: str, race: str, *, ironman: bool) -> int:
    tree = _load_prestige_trees().get(skill_key)
    if not tree:
        return 0
    total = 0
    for path in tree.get("paths") or []:
        if path.get("auto"):
            continue
        for node in path.get("nodes") or []:
            if not ironman or is_node_available_to_race(node, race):
                total += int(node.get("cost") or 0)
    return total


def auto_tier_count(skill_key: str) -> int:
    tree = _load_prestige_trees().get(skill_key)
    if not tree:
        return 0
    auto_paths = [path for path in tree.get("paths") or [] if path.get("auto")]
    if not auto_paths:
        return 0
    return max(len(path.get("nodes") or []) for path in auto_paths)


def active_nodes(
    skill_key: str,
    *,
    prestige_count: int,
    owned_ids: set[str],
) -> list[tuple[str, dict[str, Any]]]:
    tree = _load_prestige_trees().get(skill_key)
    if not tree:
        return []
    active: list[tuple[str, dict[str, Any]]] = []
    for path in tree.get("paths") or []:
        path_key = str(path.get("key") or "")
        nodes = path.get("nodes") or []
        if path.get("auto"):
            for node in nodes[: max(0, min(prestige_count, len(nodes)))]:
                active.append((path_key, node))
        else:
            for node in nodes:
                if str(node.get("id") or "") in owned_ids:
                    active.append((path_key, node))
    return active


def effect_totals(
    skill_key: str,
    *,
    prestige_count: int,
    owned_ids: set[str],
) -> dict[str, float]:
    per_path: dict[tuple[str, str], float] = {}
    for path_key, node in active_nodes(
        skill_key, prestige_count=prestige_count, owned_ids=owned_ids,
    ):
        effect = str(node.get("effect") or "")
        if not effect:
            continue
        value = float(node.get("value") or 0)
        key = (path_key, effect)
        per_path[key] = max(per_path.get(key, 0.0), value)

    totals: dict[str, float] = {}
    for (_path_key, effect), value in per_path.items():
        totals[effect] = totals.get(effect, 0.0) + value
    return totals


def _node_state(
    *,
    node: dict[str, Any],
    path_auto: bool,
    tier: int,
    prestige_count: int,
    owned_ids: set[str],
    race: str,
    prev_owned_for_race: bool,
    unspent: int,
) -> tuple[dict[str, Any], bool]:
    node_id = str(node.get("id") or "")
    if path_auto:
        owned = tier <= prestige_count
        return {
            "id": node_id,
            "tier": tier,
            "cost": int(node.get("cost") or 0),
            "effect": str(node.get("effect") or ""),
            "value": float(node.get("value") or 0),
            "unlock": node.get("unlock"),
            "races": node.get("races"),
            "auto": True,
            "owned": owned,
            "race_locked": False,
            "prereq_locked": not owned and tier > prestige_count,
            "affordable": False,
            "state": "owned" if owned else "locked",
        }, owned

    race_ok = is_node_available_to_race(node, race)
    owned = node_id in owned_ids
    prereq_locked = race_ok and not prev_owned_for_race and not owned
    affordable = unspent >= int(node.get("cost") or 0)
    if owned:
        state = "owned"
    elif race_ok and not prereq_locked and affordable:
        state = "available"
    elif race_ok and not prereq_locked:
        state = "unaffordable"
    elif not race_ok:
        state = "race_locked"
    else:
        state = "locked"

    next_prev = owned if race_ok else prev_owned_for_race
    return {
        "id": node_id,
        "tier": tier,
        "cost": int(node.get("cost") or 0),
        "effect": str(node.get("effect") or ""),
        "value": float(node.get("value") or 0),
        "unlock": node.get("unlock"),
        "races": node.get("races"),
        "auto": False,
        "owned": owned,
        "race_locked": not race_ok,
        "prereq_locked": prereq_locked,
        "affordable": affordable,
        "state": state,
    }, next_prev


def build_skill_prestige(
    skill_key: str,
    *,
    skill_name: str,
    skill_level: int,
    prestige_count: int,
    points_earned: int,
    owned_ids: list[str],
    respec_at: int | None,
    xp_boost_expires_at: int | None,
    race: str,
    ironman: bool,
) -> dict[str, Any] | None:
    tree = _load_prestige_trees().get(skill_key)
    if not tree:
        return None

    owned_set = {str(node_id) for node_id in owned_ids}
    spent = spent_points(skill_key, owned_set)
    unspent = max(points_earned - spent, 0)
    cap = point_cap(skill_key, race, ironman=ironman)

    paths_out: list[dict[str, Any]] = []
    for path in tree.get("paths") or []:
        path_auto = bool(path.get("auto"))
        prev_owned = True
        nodes_out: list[dict[str, Any]] = []
        for index, node in enumerate(path.get("nodes") or []):
            if not isinstance(node, dict):
                continue
            node_ui, prev_owned = _node_state(
                node=node,
                path_auto=path_auto,
                tier=index + 1,
                prestige_count=prestige_count,
                owned_ids=owned_set,
                race=race,
                prev_owned_for_race=prev_owned,
                unspent=unspent,
            )
            nodes_out.append(node_ui)
        paths_out.append({
            "key": str(path.get("key") or ""),
            "key_name": _format_key(str(path.get("key") or "")),
            "auto": path_auto,
            "nodes": nodes_out,
        })

    effects = effect_totals(skill_key, prestige_count=prestige_count, owned_ids=owned_set)
    auto_tiers = auto_tier_count(skill_key)
    has_reward = (cap > 0 and points_earned < cap) or prestige_count < auto_tiers

    return {
        "key": skill_key,
        "name": skill_name,
        "level": skill_level,
        "prestige_count": prestige_count,
        "points_earned": points_earned,
        "points_spent": spent,
        "points_unspent": unspent,
        "point_cap": cap,
        "auto_tier_count": auto_tiers,
        "can_prestige_more": has_reward,
        "respec_at": respec_at,
        "xp_boost_expires_at": xp_boost_expires_at,
        "paths": paths_out,
        "effects": [
            {"effect": effect, "total": total}
            for effect, total in sorted(effects.items())
            if total
        ],
        "purchased_count": len(owned_set),
    }


def build_prestige_bundle(
    *,
    skill_levels: dict[str, int],
    skill_prestige: dict[str, int],
    points_earned: dict[str, int],
    prestige_nodes: dict[str, list[str]],
    respec_at: dict[str, int],
    xp_boosts: dict[str, int],
    character_race: str | None,
    ironman: bool,
) -> dict[str, Any]:
    race = player_race(character_race)
    skills_out: list[dict[str, Any]] = []

    for skill_key in prestige_tree_skills():
        level = int(skill_levels.get(skill_key, 1))
        prestige_count = int(skill_prestige.get(skill_key, 0))
        earned = int(points_earned.get(skill_key, 0))
        owned = prestige_nodes.get(skill_key) or []
        if not isinstance(owned, list):
            owned = []
        if prestige_count == 0 and earned == 0 and not owned:
            continue

        built = build_skill_prestige(
            skill_key,
            skill_name=_format_key(skill_key),
            skill_level=level,
            prestige_count=prestige_count,
            points_earned=earned,
            owned_ids=[str(node_id) for node_id in owned],
            respec_at=int(respec_at.get(skill_key) or 0) or None,
            xp_boost_expires_at=int(xp_boosts.get(skill_key) or 0) or None,
            race=race,
            ironman=ironman,
        )
        if built:
            skills_out.append(built)

    skills_out.sort(
        key=lambda row: (
            -row["points_unspent"],
            -row["prestige_count"],
            -row["points_earned"],
            row["name"],
        ),
    )

    return {
        "player_race": race,
        "ironman": ironman,
        "skills": skills_out,
        "skill_count": len(skills_out),
    }
