#!/usr/bin/env bash
# Run scripts/deploy-ci.sh inside a host-network Docker sidecar (boule-score pattern).
# Job containers often cannot reach LAN/LXC; the host network can.
# Requires docker CLI + socket in the job (same Unraid act_runner as boule-score).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

: "${DEPLOY_SSH_KEY:?DEPLOY_SSH_KEY secret missing}"
: "${DEPLOY_HOST:?DEPLOY_HOST secret missing}"
: "${DEPLOY_DIR:?DEPLOY_DIR secret missing}"

if [[ -z "${EXPECTED_SHA:-}" ]]; then
  EXPECTED_SHA="$(git rev-parse HEAD)"
fi
export EXPECTED_SHA
export DEPLOY_BRANCH="${DEPLOY_BRANCH:-master}"

echo "::add-mask::${DEPLOY_SSH_KEY}"

# Host Docker cannot see the job container filesystem — pipe scripts in.
DEPLOY_REMOTE_B64="$(base64 -w0 scripts/deploy-remote.sh)"
export DEPLOY_REMOTE_B64

docker run --rm -i --network host \
  -e DEPLOY_SSH_KEY -e DEPLOY_HOST -e DEPLOY_DIR -e DEPLOY_USER \
  -e DEPLOY_WG_CONF -e DEPLOY_SERVICE -e DEPLOY_BRANCH -e EXPECTED_SHA \
  -e DEPLOY_SSH_PORT -e DEPLOY_HEALTH_RETRIES -e DEPLOY_HEALTH_INTERVAL \
  -e DEPLOY_SSH_KNOWN_HOSTS -e DEPLOY_REMOTE_B64 \
  ubuntu:22.04 \
  bash -lc 'set -euo pipefail
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq openssh-client curl >/dev/null
    printf %s "$DEPLOY_REMOTE_B64" | base64 -d > /tmp/deploy-remote.sh
    export DEPLOY_REMOTE_SCRIPT=/tmp/deploy-remote.sh
    cat > /tmp/deploy-ci.sh
    chmod +x /tmp/deploy-ci.sh /tmp/deploy-remote.sh
    exec /tmp/deploy-ci.sh
  ' < scripts/deploy-ci.sh
