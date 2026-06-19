#!/usr/bin/env bash
# Deploy Idle Fantasy Save Viewer to production.
# Usage (from repo root): bash scripts/deploy.sh

set -euo pipefail

REMOTE_HOST="${DEPLOY_HOST:-root@10.0.0.5}"
REMOTE_DIR="${DEPLOY_DIR:-/opt/apps/Idle-Fantasy-Save-Viewer}"
HEALTH_URL="${DEPLOY_HEALTH_URL:-http://127.0.0.1:5000/}"
HEALTH_RETRIES="${DEPLOY_HEALTH_RETRIES:-20}"
HEALTH_INTERVAL="${DEPLOY_HEALTH_INTERVAL:-2}"
SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new)

info() { printf '==> %s\n' "$*"; }
err() { printf 'ERROR: %s\n' "$*" >&2; }

die() {
  err "$@"
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

require_cmd git
require_cmd ssh

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || die "Not inside a git repository."
cd "$ROOT"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$BRANCH" == "HEAD" ]]; then
  die "Detached HEAD – checkout a branch before deploying."
fi

if [[ -n "$(git status --porcelain)" ]]; then
  die "Working tree is not clean. Commit or stash changes before deploying."
fi

if ! git rev-parse --abbrev-ref --symbolic-full-name "@{u}" >/dev/null 2>&1; then
  die "Branch '$BRANCH' has no upstream. Run: git push -u origin $BRANCH"
fi

LOCAL_SHA="$(git rev-parse HEAD)"

info "Local branch: $BRANCH ($LOCAL_SHA)"

info "Pushing $BRANCH to origin…"
git push origin "$BRANCH"

REMOTE_SHA="$(git rev-parse HEAD)"

info "Deploying to $REMOTE_HOST:$REMOTE_DIR"

ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" bash -s -- \
  "$REMOTE_DIR" \
  "$BRANCH" \
  "$REMOTE_SHA" \
  "$HEALTH_URL" \
  "$HEALTH_RETRIES" \
  "$HEALTH_INTERVAL" <<'REMOTE_SCRIPT'
set -euo pipefail

REMOTE_DIR="$1"
BRANCH="$2"
EXPECTED_SHA="$3"
HEALTH_URL="$4"
HEALTH_RETRIES="$5"
HEALTH_INTERVAL="$6"

info() { printf '==> [remote] %s\n' "$*"; }
die() { printf 'ERROR: [remote] %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "docker not found on remote host"
docker compose version >/dev/null 2>&1 || die "docker compose not available on remote host"
command -v curl >/dev/null 2>&1 || die "curl not found on remote host"

[[ -d "$REMOTE_DIR/.git" ]] || die "Directory is not a git repo: $REMOTE_DIR"

cd "$REMOTE_DIR"

if [[ -n "$(git status --porcelain)" ]]; then
  die "Remote working tree is dirty. Resolve local changes on the server first."
fi

info "Fetching origin…"
git fetch origin

REMOTE_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$REMOTE_BRANCH" != "$BRANCH" ]]; then
  info "Checking out branch $BRANCH"
  git checkout "$BRANCH"
fi

info "Fast-forwarding to origin/$BRANCH"
git pull --ff-only origin "$BRANCH"

ACTUAL_SHA="$(git rev-parse HEAD)"
if [[ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]]; then
  die "Remote SHA mismatch after pull (expected $EXPECTED_SHA, got $ACTUAL_SHA)."
fi

info "Rebuilding and starting containers…"
docker compose up -d --build --remove-orphans

info "Waiting for health check ($HEALTH_URL)…"
ok=0
for ((i = 1; i <= HEALTH_RETRIES; i++)); do
  if curl -fsS -o /dev/null "$HEALTH_URL" 2>/dev/null; then
    ok=1
    break
  fi
  sleep "$HEALTH_INTERVAL"
done

if [[ "$ok" -ne 1 ]]; then
  die "Health check failed after $((HEALTH_RETRIES * HEALTH_INTERVAL))s."
fi

info "Health check OK"

info "Pruning stopped containers…"
docker container prune -f >/dev/null

info "Pruning dangling images…"
docker image prune -f >/dev/null

info "Service status:"
docker compose ps
REMOTE_SCRIPT

info "Deployment finished successfully."
