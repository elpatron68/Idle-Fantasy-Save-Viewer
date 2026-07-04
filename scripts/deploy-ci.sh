#!/usr/bin/env bash
# Non-interactive deploy for CI (Gitea/GitHub Actions). Requires env:
#   DEPLOY_SSH_KEY, DEPLOY_HOST, DEPLOY_DIR, DEPLOY_SERVICE
set -euo pipefail

if [[ -z "${DEPLOY_SSH_KEY:-}" ]]; then
  echo "DEPLOY_SSH_KEY not set — skipping deploy"
  exit 0
fi

HOST="${DEPLOY_HOST:-root@10.0.0.5}"
DIR="${DEPLOY_DIR:-/opt/apps/Idle-Fantasy-Save-Viewer}"
SERVICE="${DEPLOY_SERVICE:-viewer}"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
SHA="$(git rev-parse HEAD)"
KEY_FILE="$(mktemp)"
trap 'rm -f "$KEY_FILE"' EXIT
install -m 600 /dev/stdin "$KEY_FILE" <<< "$DEPLOY_SSH_KEY"

ssh -i "$KEY_FILE" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$HOST" \
  bash -s -- "$DIR" "$BRANCH" "$SHA" "$SERVICE" <<'REMOTE'
set -euo pipefail
DEPLOY_DIR="$1" BRANCH="$2" EXPECTED_SHA="$3" SERVICE="$4"
cd "$DEPLOY_DIR"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git reset --hard "origin/$BRANCH"
[[ "$(git rev-parse HEAD)" == "$EXPECTED_SHA" ]] || { echo "SHA mismatch"; exit 1; }
docker compose up -d --build "$SERVICE"
for _ in $(seq 1 30); do
  docker compose ps --format json | grep -q '"Health":"healthy"' && exit 0
  sleep 2
done
echo "Health check timed out"
exit 1
REMOTE
