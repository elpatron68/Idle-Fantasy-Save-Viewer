"""Load vendored Idle Fantasy recipe data (synced from the game repo)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

GAME_DATA_ROOT = Path(__file__).parent / "game_data"
RECIPES_DIR = GAME_DATA_ROOT / "recipes"
MANIFEST_PATH = GAME_DATA_ROOT / "manifest.json"

RECIPE_SKILL_MAP: dict[str, str] = {
    "smithing.json": "smithing",
    "crafting.json": "crafting",
    "cooking.json": "cooking",
    "fletching.json": "fletching",
    "herblore.json": "herblore",
    "construction.json": "construction",
}


def manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.is_file():
        return {}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _load_all_recipes() -> dict[str, dict[str, dict[str, Any]]]:
    """skill_key → activity_key → recipe dict."""
    by_skill: dict[str, dict[str, dict[str, Any]]] = {}
    if not RECIPES_DIR.is_dir():
        return by_skill
    for filename, skill_key in RECIPE_SKILL_MAP.items():
        path = RECIPES_DIR / filename
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            by_skill[skill_key] = data
    return by_skill


def recipes_for_skill(skill_key: str) -> dict[str, dict[str, Any]]:
    return dict(_load_all_recipes().get(skill_key, {}))


def supported_advisor_skills() -> list[str]:
    return sorted(_load_all_recipes().keys())


def xp_per_minute(recipe: dict[str, Any]) -> float:
    xp = float(recipe.get("xp_per_item") or 0)
    seconds = float(recipe.get("time_per_item") or 60)
    if seconds <= 0:
        return 0.0
    return xp * 60.0 / seconds


def format_display_name(recipe: dict[str, Any], activity_key: str) -> str:
    name = recipe.get("display_name")
    if name:
        return str(name)
    return activity_key.replace("_", " ").title()


def find_recipe(activity_key: str) -> tuple[str, dict[str, Any]] | None:
    """Return (skill_key, recipe) for an activity/output key, if known."""
    for skill_key, recipes in _load_all_recipes().items():
        recipe = recipes.get(activity_key)
        if recipe:
            return skill_key, recipe
    return None


def recipe_display_name(activity_key: str) -> str | None:
    found = find_recipe(activity_key)
    if not found:
        return None
    _, recipe = found
    return format_display_name(recipe, activity_key)
