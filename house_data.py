"""Load vendored Idle Fantasy house tile metadata."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

GAME_DATA_ROOT = Path(__file__).parent / "game_data"
HOUSE_TILES_PATH = GAME_DATA_ROOT / "house_tiles.json"
BANNER_PREFIX = "banner:"


def _format_key(key: str) -> str:
    return str(key).replace("_", " ").title()


@lru_cache(maxsize=1)
def _load_house_tiles() -> dict[str, Any]:
    if not HOUSE_TILES_PATH.is_file():
        return {}
    return json.loads(HOUSE_TILES_PATH.read_text(encoding="utf-8"))


def house_item_def(item_key: str) -> dict[str, Any] | None:
    key = str(item_key or "")
    if key.startswith(BANNER_PREFIX):
        return {
            "footprint_w": 1,
            "footprint_h": 1,
            "wall_mounted": True,
            "category": "banner",
            "anchor": "center",
        }
    items = _load_house_tiles().get("items") or {}
    defn = items.get(key)
    return defn if isinstance(defn, dict) else None


def house_item_name(item_key: str) -> str:
    key = str(item_key or "")
    if key.startswith(BANNER_PREFIX):
        return _format_key(key[len(BANNER_PREFIX):])
    defn = house_item_def(key)
    if defn:
        name_key = defn.get("name_key")
        if name_key:
            key = str(name_key)
    return _format_key(key)


def house_item_meta(item_key: str) -> dict[str, Any]:
    defn = house_item_def(item_key) or {}
    return {
        "category": str(defn.get("category") or "furniture"),
        "footprint_w": int(defn.get("footprint_w") or 1),
        "footprint_h": int(defn.get("footprint_h") or 1),
        "wall_mounted": bool(defn.get("wall_mounted")),
        "anchor": str(defn.get("anchor") or "center"),
        "level_required": int(defn.get("level_required") or 1),
    }


def house_ground_name(ground_key: str) -> str:
    return _format_key(str(ground_key or "ground_1"))


def house_max_rooms() -> int:
    rooms = _load_house_tiles().get("rooms") or []
    return 1 + len(rooms)
