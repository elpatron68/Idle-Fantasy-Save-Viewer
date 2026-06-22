"""Skill training recommendations from game recipe data + save state."""

from __future__ import annotations

from typing import Any

from game_data import format_display_name, manifest, recipes_for_skill, supported_advisor_skills, xp_per_minute


def _inventory_map(snapshot: dict[str, Any]) -> dict[str, int]:
    inv: dict[str, int] = {}
    for item in snapshot.get("inventory") or []:
        key = item.get("key")
        if key:
            inv[str(key)] = int(item.get("qty") or 0)
    return inv


def _skill_state(snapshot: dict[str, Any], skill_key: str) -> dict[str, Any] | None:
    for skill in snapshot.get("skills") or []:
        if skill.get("key") == skill_key:
            return skill
    return None


def missing_materials(
    materials: dict[str, int],
    inventory: dict[str, int],
) -> dict[str, int]:
    missing: dict[str, int] = {}
    for item_key, needed in materials.items():
        need = int(needed)
        have = inventory.get(item_key, 0)
        if have < need:
            missing[item_key] = need - have
    return missing


def crafts_to_next_level(xp_remaining: int, xp_per_item: float) -> int:
    if xp_remaining <= 0 or xp_per_item <= 0:
        return 1
    return max(1, int((xp_remaining + xp_per_item - 1) // xp_per_item))


def advise_skill(
    skill_key: str,
    snapshot: dict[str, Any],
    *,
    limit: int = 8,
) -> dict[str, Any]:
    skill_key = skill_key.strip().lower()
    recipes = recipes_for_skill(skill_key)
    if not recipes:
        return {
            "skill_key": skill_key,
            "supported": False,
            "error": "unsupported_skill",
            "supported_skills": supported_advisor_skills(),
        }

    skill = _skill_state(snapshot, skill_key)
    if not skill:
        return {
            "skill_key": skill_key,
            "supported": True,
            "error": "skill_not_in_save",
        }

    level = int(skill.get("level") or 1)
    xp_in_level = int(skill.get("xp_in_level") or 0)
    xp_needed = int(skill.get("xp_needed") or 1)
    xp_remaining = max(0, xp_needed - xp_in_level)
    inventory = _inventory_map(snapshot)

    candidates: list[dict[str, Any]] = []
    for activity_key, recipe in recipes.items():
        level_required = int(recipe.get("level_required") or 1)
        if level_required > level:
            continue
        materials = {str(k): int(v) for k, v in (recipe.get("materials") or {}).items()}
        missing = missing_materials(materials, inventory)
        rate = xp_per_minute(recipe)
        if rate <= 0:
            continue
        eta_minutes = int((xp_remaining + rate - 1) // rate) if xp_remaining > 0 else 0
        craft_count = crafts_to_next_level(xp_remaining, float(recipe.get("xp_per_item") or 0))
        candidates.append({
            "activity_key": activity_key,
            "display_name": format_display_name(recipe, activity_key),
            "type": recipe.get("type"),
            "level_required": level_required,
            "xp_per_item": float(recipe.get("xp_per_item") or 0),
            "time_per_item": int(recipe.get("time_per_item") or 60),
            "xp_per_minute": round(rate, 2),
            "materials": materials,
            "can_craft": not missing,
            "missing_materials": missing,
            "eta_minutes_to_level": eta_minutes,
            "crafts_to_next_level": craft_count,
        })

    candidates.sort(
        key=lambda row: (
            0 if row["can_craft"] else 1,
            -row["xp_per_minute"],
            row["level_required"],
        ),
    )

    meta = manifest()
    return {
        "skill_key": skill_key,
        "skill_name": skill.get("name") or skill_key.replace("_", " ").title(),
        "skill_level": level,
        "xp_remaining_in_level": xp_remaining,
        "supported": True,
        "game_data_sha": meta.get("source_sha"),
        "game_data_synced_at": meta.get("synced_at"),
        "recommendations": candidates[:limit],
    }
