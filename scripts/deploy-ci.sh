#!/usr/bin/env bash
# Non-interactive deploy for Gitea Actions over WireGuard → Proxmox LXC.
#
# Required secrets (env):
#   DEPLOY_SSH_KEY   – private SSH key (PEM / OpenSSH)
#   DEPLOY_HOST      – SSH target, e.g. root@10.66.0.10 (WireGuard IP of the LXC)
#   DEPLOY_DIR       – git checkout on the LXC, e.g. /opt/apps/Idle-Fantasy-Save-Viewer
#   DEPLOY_WG_CONF   – full WireGuard interface config (wg-quick style)
#
# Optional secrets (env):
#   DEPLOY_SERVICE            – compose service name (default: viewer)
#   DEPLOY_BRANCH             – git branch to deploy (default: current HEAD branch / master)
#   DEPLOY_SSH_PORT           – SSH port (default: 22)
#   DEPLOY_HEALTH_RETRIES     – health poll count (default: 30)
#   DEPLOY_HEALTH_INTERVAL    – seconds between polls (default: 2)
#   DEPLOY_SSH_KNOWN_HOSTS    – known_hosts entries (optional; otherwise accept-new)
#
# Runner requirements for WireGuard inside the job container:
#   /dev/net/tun + CAP_NET_ADMIN (see scripts/setup-gitea-runner.sh)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

info() { printf '==> %s\n' "$*"; }
err() { printf 'ERROR: %s\n' "$*" >&2; }
die() { err "$@"; exit 1; }

require_secret() {
  local name="$1"
  [[ -n "${!name:-}" ]] || die "Missing required secret/env: $name"
}

require_secret DEPLOY_SSH_KEY
require_secret DEPLOY_HOST
require_secret DEPLOY_DIR
require_secret DEPLOY_WG_CONF

HOST="$DEPLOY_HOST"
DIR="$DEPLOY_DIR"
SERVICE="${DEPLOY_SERVICE:-viewer}"
BRANCH="${DEPLOY_BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)}"
if [[ -z "$BRANCH" || "$BRANCH" == "HEAD" ]]; then
  BRANCH="master"
fi
SSH_PORT="${DEPLOY_SSH_PORT:-22}"
HEALTH_RETRIES="${DEPLOY_HEALTH_RETRIES:-30}"
HEALTH_INTERVAL="${DEPLOY_HEALTH_INTERVAL:-2}"
SHA="$(git rev-parse HEAD)"

WG_IFACE="${DEPLOY_WG_IFACE:-wg0}"
TMP_DIR="$(mktemp -d)"
KEY_FILE="$TMP_DIR/deploy_key"
WG_CONF="$TMP_DIR/${WG_IFACE}.conf"
KNOWN_HOSTS="$TMP_DIR/known_hosts"
WG_UP=0

cleanup() {
  set +e
  if [[ "$WG_UP" -eq 1 ]]; then
    info "Bringing WireGuard down ($WG_IFACE)…"
    wg-quick down "$WG_CONF" 2>/dev/null || true
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

command -v ssh >/dev/null 2>&1 || die "ssh not found"
command -v wg-quick >/dev/null 2>&1 || die "wg-quick not found (install wireguard-tools)"
command -v ip >/dev/null 2>&1 || die "ip not found (install iproute2)"
command -v wg >/dev/null 2>&1 || die "wg not found (install wireguard-tools)"

# Fail fast with an actionable message when the runner job lacks CAP_NET_ADMIN.
if [[ ! -e /dev/net/tun ]]; then
  err "WARN: /dev/net/tun missing (ok for kernel WireGuard; required for some setups)"
fi
if ! ip link add "wg-ci-probe-$$" type wireguard 2>/dev/null; then
  die "Cannot create WireGuard iface (need CAP_NET_ADMIN on job containers). On the runner host: bash scripts/patch-gitea-runner-wg.sh"
fi
ip link delete "wg-ci-probe-$$" 2>/dev/null || true

info "Writing SSH key and WireGuard config…"
install -m 600 /dev/stdin "$KEY_FILE" <<< "$DEPLOY_SSH_KEY"
# Normalize line endings; secrets pasted from Windows editors often break wg-quick.
# Drop DNS= — wg-quick would call resolvconf, which is absent in job images; SSH uses WG IPs.
printf '%s\n' "$DEPLOY_WG_CONF" | tr -d '\r' \
  | sed -E '/^[[:space:]]*DNS[[:space:]]*=/d' \
  > "$WG_CONF"
chmod 600 "$WG_CONF"

SSH_OPTS=(
  -i "$KEY_FILE"
  -p "$SSH_PORT"
  -o BatchMode=yes
  -o IdentitiesOnly=yes
  -o ConnectTimeout=20
)

if [[ -n "${DEPLOY_SSH_KNOWN_HOSTS:-}" ]]; then
  printf '%s\n' "$DEPLOY_SSH_KNOWN_HOSTS" | tr -d '\r' > "$KNOWN_HOSTS"
  chmod 600 "$KNOWN_HOSTS"
  SSH_OPTS+=(-o UserKnownHostsFile="$KNOWN_HOSTS" -o StrictHostKeyChecking=yes)
else
  SSH_OPTS+=(-o StrictHostKeyChecking=accept-new)
fi

# Leftover iface from a crashed prior job (shared runner netns) blocks wg-quick up.
if ip link show "$WG_IFACE" &>/dev/null; then
  info "Interface $WG_IFACE already exists; tearing down before up…"
  wg-quick down "$WG_CONF" 2>/dev/null || true
  ip link delete "$WG_IFACE" 2>/dev/null || true
fi

info "Bringing WireGuard up ($WG_IFACE)…"
if ! wg-quick up "$WG_CONF"; then
  die "WireGuard failed to start. Check job image (iproute2, wireguard-tools) and runner TUN/CAP_NET_ADMIN (see README / setup-gitea-runner.sh)."
fi
WG_UP=1

info "Waiting for SSH at $HOST:$SSH_PORT…"
ready=0
for _ in $(seq 1 30); do
  if ssh "${SSH_OPTS[@]}" "$HOST" true 2>/dev/null; then
    ready=1
    break
  fi
  sleep 2
done
[[ "$ready" -eq 1 ]] || die "SSH to $HOST timed out over WireGuard."

info "Deploying $BRANCH ($SHA) → $HOST:$DIR (service=$SERVICE)"
ssh "${SSH_OPTS[@]}" "$HOST" bash -s -- \
  "$DIR" \
  "$BRANCH" \
  "$SHA" \
  "$SERVICE" \
  "$HEALTH_RETRIES" \
  "$HEALTH_INTERVAL" < "$SCRIPT_DIR/deploy-remote.sh"

info "CI deployment finished successfully."
