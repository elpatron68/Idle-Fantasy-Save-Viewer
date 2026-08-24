#!/usr/bin/env python3
"""Download recipe JSON assets from the Idle Fantasy game repository."""

from __future__ import annotations

import json
import time
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


RETRYABLE_HTTP_CODES = frozenset({429, 500, 502, 503, 504})
MAX_HTTP_ATTEMPTS = 5


def _fetch(url: str, *, timeout: int = 60) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, MAX_HTTP_ATTEMPTS + 1):
        req = urllib.request.Request(url, headers={"User-Agent": "idle-fantasy-viewer-sync"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in RETRYABLE_HTTP_CODES or attempt == MAX_HTTP_ATTEMPTS:
                raise
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt == MAX_HTTP_ATTEMPTS:
                raise
        delay = min(2 ** attempt, 30)
        print(f"  retry {attempt}/{MAX_HTTP_ATTEMPTS} in {delay}s ({last_error})")
        time.sleep(delay)
    raise SystemExit(f"Failed to fetch {url}") from last_error


def _resolve_sha() -> str:
    # /commits/{branch} intermittently 504s; /git/refs/heads/{branch} is reliable.
    api = f"https://api.github.com/repos/{REPO}/git/refs/heads/{BRANCH}"
    data = json.loads(_fetch(api, timeout=30).decode())
    return data["object"]["sha"]


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

    manifest_body = (
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
        + "\n"
    )
    with MANIFEST.open("w", encoding="utf-8", newline="\n") as manifest_file:
        manifest_file.write(manifest_body)
    print(f"Synced {len(synced)} files -> {OUT_DIR}")
    print(f"Manifest: {MANIFEST} (sha {sha[:12]})")


if __name__ == "__main__":
    main()
