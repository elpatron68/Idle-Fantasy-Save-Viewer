"""Deployed build reference (git commit), without semver."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD_REF_FILE = ROOT / "BUILD_REF"
REPO_URL = "https://gitea.elpatron.me/elpatron/Idle-Fantasy-Save-Viewer"


def _git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def build_commit() -> str | None:
    env_ref = os.environ.get("GIT_COMMIT", "").strip()
    if env_ref and env_ref != "unknown":
        return env_ref
    if BUILD_REF_FILE.is_file():
        ref = BUILD_REF_FILE.read_text(encoding="utf-8").strip()
        if ref and ref != "unknown":
            return ref
    return _git_head()


def build_info() -> dict[str, str | None]:
    commit = build_commit()
    if not commit:
        return {"ref": None, "url": None}
    short = commit if len(commit) <= 12 else commit[:7]
    return {
        "ref": short,
        "url": f"{REPO_URL}/commit/{commit}",
    }
