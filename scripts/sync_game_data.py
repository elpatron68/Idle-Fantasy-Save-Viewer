#!/usr/bin/env python3
"""Download recipe JSON assets from the Idle Fantasy game repository."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = "tristinbaker/IdleFantasy"
BRANCH = "main"
DATA_PREFIX = f"app/src/main/assets/data/recipes"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"

RECIPE_FILES = (
    "smithing.json",
    "crafting.json",
    "cooking.json",
    "fletching.json",
    "herblore.json",
    "construction.json",
)

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "game_data" / "recipes"
MANIFEST = ROOT / "game_data" / "manifest.json"


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "idle-fantasy-viewer-sync"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def _resolve_sha() -> str:
    api = f"https://api.github.com/repos/{REPO}/commits/{BRANCH}"
    req = urllib.request.Request(api, headers={"User-Agent": "idle-fantasy-viewer-sync"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return data["sha"]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sha = _resolve_sha()
    synced: list[str] = []

    for name in RECIPE_FILES:
        url = f"{RAW_BASE}/{DATA_PREFIX}/{name}"
        try:
            payload = _fetch(url)
        except urllib.error.HTTPError as exc:
            raise SystemExit(f"Failed to download {name}: HTTP {exc.code}") from exc
        json.loads(payload)
        (OUT_DIR / name).write_bytes(payload)
        synced.append(name)
        print(f"  {name}")

    MANIFEST.write_text(
        json.dumps(
            {
                "source_repo": f"https://github.com/{REPO}",
                "source_ref": BRANCH,
                "source_sha": sha,
                "synced_at": datetime.now(timezone.utc).isoformat(),
                "files": synced,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Synced {len(synced)} files -> {OUT_DIR}")
    print(f"Manifest: {MANIFEST} (sha {sha[:12]})")


if __name__ == "__main__":
    main()
