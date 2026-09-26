#!/usr/bin/env python3
"""Download recipe JSON assets from the Idle Fantasy game repository."""

from __future__ import annotations

import json
import os
import subprocess
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


RETRYABLE_HTTP_CODES = frozenset({403, 429, 500, 502, 503, 504})
MAX_HTTP_ATTEMPTS = 5


def _request_headers(url: str) -> dict[str, str]:
    headers = {"User-Agent": "idle-fantasy-viewer-sync"}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token and "api.github.com" in url:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _fetch(url: str, *, timeout: int = 60) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, MAX_HTTP_ATTEMPTS + 1):
        req = urllib.request.Request(url, headers=_request_headers(url))
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
    """Resolve upstream main SHA without the REST API (avoids shared-runner rate limits)."""
    url = f"https://github.com/{REPO}.git"
    try:
        proc = subprocess.run(
            ["git", "ls-remote", url, f"refs/heads/{BRANCH}"],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or exc.stdout or "").strip()
        raise SystemExit(f"Failed to resolve upstream ref via git ls-remote: {stderr}") from exc
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        raise SystemExit(f"Upstream branch {BRANCH} not found in {REPO}")
    return lines[0].split()[0]


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
