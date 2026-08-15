#!/usr/bin/env bash
# Deploy Idle Fantasy Save Viewer via SSH from CI.
#
# GitHub-hosted runners: bring up WireGuard (DEPLOY_WG_CONF), then SSH to the LXC.
#
# Required env:
#   DEPLOY_SSH_KEY     OpenSSH private key (PEM) OR base64 of that PEM (one line)
#   DEPLOY_HOST        host or user@host (WG/LAN address of the LXC)
#   DEPLOY_DIR         absolute path to git checkout on the LXC
# Optional:
#   DEPLOY_USER        SSH user if DEPLOY_HOST has no user@ (default: root)
#   DEPLOY_WG_CONF     wg-quick config — required on GitHub-hosted runners
#   DEPLOY_SERVICE     compose service (default: viewer)
#   DEPLOY_BRANCH      branch (default: master)
#   EXPECTED_SHA       commit to deploy (default: git rev-parse HEAD)
#   DEPLOY_SSH_PORT    default 22
#   DEPLOY_HEALTH_RETRIES / DEPLOY_HEALTH_INTERVAL
#   DEPLOY_SSH_KNOWN_HOSTS
#   DEPLOY_GIT_REMOTE  origin URL on the LXC (default: GitHub HTTPS)
#   DEPLOY_REMOTE_SCRIPT  path to deploy-remote.sh (default: beside this script)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

: "${DEPLOY_SSH_KEY:?DEPLOY_SSH_KEY secret missing}"
: "${DEPLOY_HOST:?DEPLOY_HOST secret missing}"
: "${DEPLOY_DIR:?DEPLOY_DIR secret missing}"

DEPLOY_SSH_PORT="${DEPLOY_SSH_PORT:-22}"
SERVICE="${DEPLOY_SERVICE:-viewer}"
BRANCH="${DEPLOY_BRANCH:-master}"
HEALTH_RETRIES="${DEPLOY_HEALTH_RETRIES:-30}"
HEALTH_INTERVAL="${DEPLOY_HEALTH_INTERVAL:-2}"
WG_IFACE="${DEPLOY_WG_IFACE:-wgci0}"
GIT_REMOTE="${DEPLOY_GIT_REMOTE:-https://github.com/elpatron68/Idle-Fantasy-Save-Viewer.git}"
REMOTE_SCRIPT="${DEPLOY_REMOTE_SCRIPT:-$SCRIPT_DIR/deploy-remote.sh}"
WG_UP=0
SSH_DIR=""

# user@host or host + DEPLOY_USER
if [[ "$DEPLOY_HOST" == *@* ]]; then
  SSH_TARGET="$DEPLOY_HOST"
  SSH_HOST="${DEPLOY_HOST##*@}"
else
  SSH_USER="${DEPLOY_USER:-root}"
  SSH_TARGET="${SSH_USER}@${DEPLOY_HOST}"
  SSH_HOST="$DEPLOY_HOST"
fi

if [[ -n "${EXPECTED_SHA:-}" ]]; then
  SHA="$EXPECTED_SHA"
elif command -v git >/dev/null 2>&1 && git rev-parse HEAD >/dev/null 2>&1; then
  SHA="$(git rev-parse HEAD)"
else
  die "EXPECTED_SHA not set and git HEAD unavailable"
fi

cleanup() {
  local code=$?
  set +e
  if [[ "$WG_UP" -eq 1 && -f "/etc/wireguard/${WG_IFACE}.conf" ]]; then
    log "bringing WireGuard down ($WG_IFACE)"
    wg-quick down "$WG_IFACE" >/dev/null 2>&1 || true
  fi
  if [[ -n "$SSH_DIR" ]]; then
    rm -rf "$SSH_DIR"
  fi
  exit "$code"
}
trap cleanup EXIT

host_reachable() {
  timeout 3 bash -c "exec 3<>/dev/tcp/${SSH_HOST}/${DEPLOY_SSH_PORT}" 2>/dev/null
}

decode_ssh_key() {
  local raw=$1
  if [[ "$raw" == *"BEGIN "* ]]; then
    printf '%b\n' "$raw"
    return
  fi
  local decoded
  if decoded="$(printf '%s' "$raw" | base64 -d 2>/dev/null)" \
    && [[ "$decoded" == *"BEGIN "* ]]; then
    printf '%s\n' "$decoded"
    return
  fi
  die "DEPLOY_SSH_KEY is neither PEM nor base64(PEM)"
}

bring_wg_up() {
  [[ -n "${DEPLOY_WG_CONF:-}" ]] || die "${SSH_HOST}:${DEPLOY_SSH_PORT} unreachable (use host networking or set DEPLOY_WG_CONF)"
  [[ -e /dev/net/tun ]] || die "host unreachable and /dev/net/tun missing"
  if [[ "$(id -u)" -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
      exec sudo -E bash "$0"
    fi
    die "root or sudo required for WireGuard"
  fi
  if ! command -v wg-quick >/dev/null 2>&1 || ! command -v ip >/dev/null 2>&1; then
    log "installing wireguard-tools + iproute2"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq wireguard-tools iproute2 >/dev/null
  fi
  install -d -m 700 /etc/wireguard
  umask 077
  # Drop DNS= — no resolvconf in minimal images; SSH uses IPs.
  printf '%s\n' "$DEPLOY_WG_CONF" | tr -d '\r' \
    | sed -E '/^[[:space:]]*DNS[[:space:]]*=/d' \
    > "/etc/wireguard/${WG_IFACE}.conf"
  chmod 600 "/etc/wireguard/${WG_IFACE}.conf"
  if ip link show "$WG_IFACE" &>/dev/null; then
    log "interface $WG_IFACE already exists; tearing down"
    wg-quick down "$WG_IFACE" 2>/dev/null || ip link delete "$WG_IFACE" 2>/dev/null || true
  fi
  log "bringing WireGuard up ($WG_IFACE)"
  wg-quick up "$WG_IFACE"
  WG_UP=1
  local ready=0
  for _ in $(seq 1 30); do
    if host_reachable; then ready=1; break; fi
    sleep 1
  done
  [[ "$ready" -eq 1 ]] || die "${SSH_HOST} still unreachable after WireGuard up"
}

if ! host_reachable; then
  bring_wg_up
else
  log "${SSH_HOST}:${DEPLOY_SSH_PORT} reachable – skipping WireGuard"
fi

if ! command -v ssh >/dev/null 2>&1; then
  log "installing openssh-client"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq openssh-client >/dev/null
fi

[[ -f "$REMOTE_SCRIPT" ]] || die "deploy-remote.sh not found at $REMOTE_SCRIPT"

SSH_DIR="$(mktemp -d)"
KEY_FILE="${SSH_DIR}/id_ed25519"
KNOWN_HOSTS="${SSH_DIR}/known_hosts"
umask 077
decode_ssh_key "$DEPLOY_SSH_KEY" > "$KEY_FILE"
chmod 600 "$KEY_FILE"

if ! ssh-keygen -y -f "$KEY_FILE" >/dev/null 2>&1; then
  die "DEPLOY_SSH_KEY could not be parsed as an OpenSSH private key"
fi

SSH_OPTS=(
  -i "$KEY_FILE"
  -p "$DEPLOY_SSH_PORT"
  -o IdentitiesOnly=yes
  -o BatchMode=yes
  -o ConnectTimeout=15
)

if [[ -n "${DEPLOY_SSH_KNOWN_HOSTS:-}" ]]; then
  printf '%s\n' "$DEPLOY_SSH_KNOWN_HOSTS" | tr -d '\r' > "$KNOWN_HOSTS"
  chmod 600 "$KNOWN_HOSTS"
  SSH_OPTS+=(-o UserKnownHostsFile="$KNOWN_HOSTS" -o StrictHostKeyChecking=yes)
else
  SSH_OPTS+=(-o UserKnownHostsFile="$KNOWN_HOSTS" -o StrictHostKeyChecking=accept-new)
fi

log "SSH ${SSH_TARGET}:${DEPLOY_SSH_PORT} → ${DEPLOY_DIR} ($BRANCH @ ${SHA:0:7})"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" bash -s -- \
  "$DEPLOY_DIR" \
  "$BRANCH" \
  "$SHA" \
  "$SERVICE" \
  "$HEALTH_RETRIES" \
  "$HEALTH_INTERVAL" \
  "$GIT_REMOTE" < "$REMOTE_SCRIPT"

log "CI deployment finished successfully."
