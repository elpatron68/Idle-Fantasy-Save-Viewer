"""Load vendored heirloom item metadata."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

HEIRLOOMS_PATH = Path(__file__).parent / "game_data" / "heirlooms.json"


@lru_cache(maxsize=1)
def _load_heirlooms() -> dict[str, dict[str, str]]:
    if not HEIRLOOMS_PATH.is_file():
        return {}
    raw = json.loads(HEIRLOOMS_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    return {str(key): value for key, value in raw.items() if isinstance(value, dict)}


def is_heirloom_item(key: str) -> bool:
    return str(key) in _load_heirlooms()


def heirloom_skill(key: str) -> str | None:
    entry = _load_heirlooms().get(str(key))
    if not entry:
        return None
    skill = entry.get("skill")
    return str(skill) if skill else None
