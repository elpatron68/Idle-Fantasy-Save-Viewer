#!/usr/bin/env bash
# Remote deployment steps (run on the server via bash -s or scp + bash).
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
