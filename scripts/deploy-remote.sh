#!/usr/bin/env bash
# Remote deployment steps (run on the server via bash -s or scp + bash).
set -euo pipefail

REMOTE_DIR="$1"
BRANCH="$2"
EXPECTED_SHA="$3"
COMPOSE_SERVICE="$4"
HEALTH_RETRIES="$5"
HEALTH_INTERVAL="$6"
ORIGIN_URL="${7:-https://github.com/elpatron68/Idle-Fantasy-Save-Viewer.git}"

info() { printf '==> [remote] %s\n' "$*"; }
die() { printf 'ERROR: [remote] %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "docker not found on remote host"
docker compose version >/dev/null 2>&1 || die "docker compose not available on remote host"

[[ -d "$REMOTE_DIR/.git" ]] || die "Directory is not a git repo: $REMOTE_DIR"

cd "$REMOTE_DIR"

if [[ -n "$(git status --porcelain)" ]]; then
  die "Remote working tree is dirty. Resolve local changes on the server first."
fi

current_origin="$(git remote get-url origin)"
if [[ "$current_origin" != "$ORIGIN_URL" ]]; then
  info "Switching origin from $current_origin to $ORIGIN_URL"
  git remote set-url origin "$ORIGIN_URL"
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
export GIT_COMMIT="$ACTUAL_SHA"
docker compose up -d --build --remove-orphans

wait_for_docker_health() {
  info "Waiting for Docker health check (service: $COMPOSE_SERVICE)…"
  local cid=""
  local status="starting"

  for ((i = 1; i <= HEALTH_RETRIES; i++)); do
    cid="$(docker compose ps -q "$COMPOSE_SERVICE" 2>/dev/null | head -1)"
    if [[ -z "$cid" ]]; then
      status="no container"
      sleep "$HEALTH_INTERVAL"
      continue
    fi

    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid")"

    case "$status" in
      healthy)
        info "Docker health check OK"
        return 0
        ;;
      unhealthy)
        die "Docker health check reported unhealthy."
        ;;
    esac

    sleep "$HEALTH_INTERVAL"
  done

  die "Docker health check did not become healthy after $((HEALTH_RETRIES * HEALTH_INTERVAL))s (last status: $status)."
}

wait_for_docker_health

info "Pruning stopped containers…"
docker container prune -f >/dev/null

info "Pruning dangling images…"
docker image prune -f >/dev/null

info "Service status:"
docker compose ps
