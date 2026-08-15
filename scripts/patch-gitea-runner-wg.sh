#!/usr/bin/env bash
# Patch an existing act_runner config so job containers can run WireGuard
# (CAP_NET_ADMIN + /dev/net/tun), then restart the runner container.
#
# Usage (on the runner host):
#   bash scripts/patch-gitea-runner-wg.sh
#
# Env overrides:
#   GITEA_RUNNER_DATA      default: $HOME/.local/gitea-act-runner
#   GITEA_RUNNER_CONTAINER default: gitea-act-runner
set -euo pipefail

DATA_DIR="${GITEA_RUNNER_DATA:-$HOME/.local/gitea-act-runner}"
CONTAINER_NAME="${GITEA_RUNNER_CONTAINER:-gitea-act-runner}"
CONFIG_FILE="$DATA_DIR/config.yaml"
WG_OPTIONS='--cap-add=NET_ADMIN --device=/dev/net/tun'

mkdir -p "$DATA_DIR"

write_minimal_config() {
  cat > "$CONFIG_FILE" <<EOF
log:
  level: info

runner:
  capacity: 1
  timeout: 3h

container:
  privileged: false
  options: "$WG_OPTIONS"
  valid_volumes: []
EOF
}

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "==> No config at $CONFIG_FILE — writing a minimal WireGuard-capable config"
  write_minimal_config
else
  echo "==> Ensuring WireGuard options in $CONFIG_FILE"
  python3 - "$CONFIG_FILE" "$WG_OPTIONS" <<'PY'
import re, sys
from pathlib import Path

path = Path(sys.argv[1])
opts = sys.argv[2]
text = path.read_text(encoding="utf-8")

def ensure_options(src: str) -> str:
    if re.search(r"(?m)^[ \t]*options:[ \t]*", src):
        return re.sub(
            r"(?m)^([ \t]*options:[ \t]*).*$",
            rf'\1"{opts}"',
            src,
            count=1,
        )
    if re.search(r"(?m)^container:[ \t]*$", src):
        return re.sub(
            r"(?m)^(container:[ \t]*)$",
            rf'\1\n  options: "{opts}"',
            src,
            count=1,
        )
    return src.rstrip() + f'\n\ncontainer:\n  privileged: false\n  options: "{opts}"\n  valid_volumes: []\n'

new = ensure_options(text)
if opts not in new:
    raise SystemExit("Failed to write WireGuard options into config.yaml")
path.write_text(new, encoding="utf-8")
print(path.read_text(encoding="utf-8"))
PY
fi

if ! docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "ERROR: Docker container '$CONTAINER_NAME' not found."
  echo "Start the runner with: GITEA_RUNNER_TOKEN='…' bash scripts/setup-gitea-runner.sh"
  exit 1
fi

echo "==> Restarting $CONTAINER_NAME to reload config.yaml"
docker restart "$CONTAINER_NAME" >/dev/null
echo "==> Done. Re-run the Deploy workflow in Gitea."
