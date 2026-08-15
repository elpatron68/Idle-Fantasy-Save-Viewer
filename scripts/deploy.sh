#!/usr/bin/env bash
# Deploy Idle Fantasy Save Viewer to production.
# Usage (from repo root): bash scripts/deploy.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REMOTE_HOST="${DEPLOY_HOST:-root@10.0.0.5}"
REMOTE_DIR="${DEPLOY_DIR:-/opt/apps/Idle-Fantasy-Save-Viewer}"
COMPOSE_SERVICE="${DEPLOY_SERVICE:-viewer}"
HEALTH_RETRIES="${DEPLOY_HEALTH_RETRIES:-30}"
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

info "Deploying to $REMOTE_HOST:$REMOTE_DIR"

GIT_REMOTE="${DEPLOY_GIT_REMOTE:-https://github.com/elpatron68/Idle-Fantasy-Save-Viewer.git}"

ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" bash -s -- \
  "$REMOTE_DIR" \
  "$BRANCH" \
  "$LOCAL_SHA" \
  "$COMPOSE_SERVICE" \
  "$HEALTH_RETRIES" \
  "$HEALTH_INTERVAL" \
  "$GIT_REMOTE" < "$SCRIPT_DIR/deploy-remote.sh"

info "Deployment finished successfully."
