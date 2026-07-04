#!/usr/bin/env bash
# Register and start a Gitea Actions runner (act_runner) for gitea.elpatron.me
#
# Prerequisites: Docker, access to Gitea as admin
#
# 1. In Gitea: Site Administration → Actions → Runners → Create new Runner
#    (or: Repo → Settings → Actions → Runners)
#    Copy the registration token.
#
# 2. Run:
#      GITEA_RUNNER_TOKEN='paste-token-here' bash scripts/setup-gitea-runner.sh
#
# 3. Verify: Gitea → Administration → Actions → Runners → Status "Online"
#    Then re-run: Actions → Sync Upstream Game Data (or "Runner smoke test")
set -euo pipefail

GITEA_URL="${GITEA_URL:-https://gitea.elpatron.me}"
RUNNER_NAME="${GITEA_RUNNER_NAME:-linux-docker-$(hostname -s)}"
RUNNER_LABELS="${GITEA_RUNNER_LABELS:-ubuntu-latest:docker://catthehacker/ubuntu:act-22.04,ubuntu-22.04:docker://catthehacker/ubuntu:act-22.04}"
DATA_DIR="${GITEA_RUNNER_DATA:-$HOME/.local/gitea-act-runner}"
CONTAINER_NAME="${GITEA_RUNNER_CONTAINER:-gitea-act-runner}"

if [[ -z "${GITEA_RUNNER_TOKEN:-}" ]]; then
  echo "ERROR: Set GITEA_RUNNER_TOKEN (from Gitea → Administration → Actions → Runners)"
  echo ""
  echo "Example:"
  echo "  GITEA_RUNNER_TOKEN='...' bash scripts/setup-gitea-runner.sh"
  exit 1
fi

mkdir -p "$DATA_DIR"

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "==> Stopping existing container $CONTAINER_NAME"
  docker rm -f "$CONTAINER_NAME" >/dev/null
fi

echo "==> Starting act_runner"
echo "    Gitea:  $GITEA_URL"
echo "    Name:   $RUNNER_NAME"
echo "    Labels: $RUNNER_LABELS"
echo "    Data:   $DATA_DIR"

docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$DATA_DIR:/data" \
  -e GITEA_INSTANCE_URL="$GITEA_URL" \
  -e GITEA_RUNNER_REGISTRATION_TOKEN="$GITEA_RUNNER_TOKEN" \
  -e GITEA_RUNNER_NAME="$RUNNER_NAME" \
  -e GITEA_RUNNER_LABELS="$RUNNER_LABELS" \
  gitea/act_runner:latest

echo ""
echo "==> Logs (Ctrl+C to stop watching):"
sleep 2
docker logs -f "$CONTAINER_NAME"
