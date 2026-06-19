# Deploy Idle Fantasy Save Viewer to production.
# Usage (from repo root): .\scripts\deploy.ps1

$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
    Write-Host "==> $Message"
}

function Fail([string]$Message) {
    Write-Error $Message
    exit 1
}

$RepoRoot = git rev-parse --show-toplevel 2>$null
if (-not $RepoRoot) { Fail "Not inside a git repository." }
Set-Location $RepoRoot

# On Windows use native OpenSSH (same client as interactive "ssh" in PowerShell).
# Git Bash ships its own ssh/known_hosts and breaks host key verification.
$OnWindows = ($env:OS -match "Windows") -or ($PSVersionTable.PSPlatform -eq "Win32NT")
if (-not $OnWindows -and (Get-Command bash -ErrorAction SilentlyContinue)) {
    & bash "./scripts/deploy.sh"
    exit $LASTEXITCODE
}

$DeployHost = if ($env:DEPLOY_HOST) { $env:DEPLOY_HOST } else { "root@10.0.0.5" }
$DeployDir = if ($env:DEPLOY_DIR) { $env:DEPLOY_DIR } else { "/opt/apps/Idle-Fantasy-Save-Viewer" }
$HealthUrl = if ($env:DEPLOY_HEALTH_URL) { $env:DEPLOY_HEALTH_URL } else { "http://127.0.0.1:5000/" }
$HealthRetries = if ($env:DEPLOY_HEALTH_RETRIES) { [int]$env:DEPLOY_HEALTH_RETRIES } else { 20 }
$HealthInterval = if ($env:DEPLOY_HEALTH_INTERVAL) { [int]$env:DEPLOY_HEALTH_INTERVAL } else { 2 }
$SshOpts = @("-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new")

$Branch = git rev-parse --abbrev-ref HEAD
if ($Branch -eq "HEAD") { Fail "Detached HEAD – checkout a branch before deploying." }

$Status = git status --porcelain
if ($Status) { Fail "Working tree is not clean. Commit or stash changes before deploying." }

$Upstream = git rev-parse --abbrev-ref --symbolic-full-name "@{u}" 2>$null
if (-not $Upstream) { Fail "Branch '$Branch' has no upstream. Run: git push -u origin $Branch" }

$LocalSha = git rev-parse HEAD
Write-Step "Local branch: $Branch ($LocalSha)"
Write-Step "Pushing $Branch to origin…"
git push origin $Branch
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Step "Deploying to ${DeployHost}:${DeployDir}"

$RemoteScript = @'
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
  if curl -fsS -o /dev/null "$HEALTH_URL"; then
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
'@

$RemoteScript | & ssh @SshOpts $DeployHost bash -s -- `
    $DeployDir `
    $Branch `
    $LocalSha `
    $HealthUrl `
    "$HealthRetries" `
    "$HealthInterval"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Step "Deployment finished successfully."
