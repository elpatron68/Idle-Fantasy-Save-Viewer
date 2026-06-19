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

function Invoke-RemoteDeploy {
    param(
        [string[]]$SshOptions,
        [string]$TargetHost,
        [string]$ScriptPath,
        [string]$RemoteDir,
        [string]$Branch,
        [string]$ExpectedSha,
        [string]$HealthUrl,
        [int]$HealthRetries,
        [int]$HealthInterval
    )

    if (-not (Get-Command scp -ErrorAction SilentlyContinue)) {
        Fail "scp not found. Install OpenSSH client or use Git Bash with scripts/deploy.sh"
    }

    $remoteScript = "/tmp/if-viewer-deploy-$PID.sh"
    $quoted = @(
        $RemoteDir,
        $Branch,
        $ExpectedSha,
        $HealthUrl,
        "$HealthRetries",
        "$HealthInterval"
    ) | ForEach-Object { "'" + ($_ -replace "'", "'\\''") + "'" }

    $remoteArgs = $quoted -join " "
    $remoteRun = "bash $remoteScript $remoteArgs; rc=`$?; rm -f $remoteScript; exit `$rc"

    & scp @SshOptions $ScriptPath "${TargetHost}:${remoteScript}"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    & ssh @SshOptions $TargetHost $remoteRun
    return $LASTEXITCODE
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RemoteScriptPath = Join-Path $ScriptDir "deploy-remote.sh"

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
if ($Branch -eq "HEAD") { Fail "Detached HEAD - checkout a branch before deploying." }

$Status = git status --porcelain
if ($Status) { Fail "Working tree is not clean. Commit or stash changes before deploying." }

$Upstream = git rev-parse --abbrev-ref --symbolic-full-name "@{u}" 2>$null
if (-not $Upstream) { Fail "Branch '$Branch' has no upstream. Run: git push -u origin $Branch" }

$LocalSha = git rev-parse HEAD
Write-Step "Local branch: $Branch ($LocalSha)"
Write-Step "Pushing $Branch to origin..."
git push origin $Branch
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Step "Deploying to ${DeployHost}:${DeployDir}"

$exitCode = Invoke-RemoteDeploy `
    -SshOptions $SshOpts `
    -TargetHost $DeployHost `
    -ScriptPath $RemoteScriptPath `
    -RemoteDir $DeployDir `
    -Branch $Branch `
    -ExpectedSha $LocalSha `
    -HealthUrl $HealthUrl `
    -HealthRetries $HealthRetries `
    -HealthInterval $HealthInterval
if ($exitCode -ne 0) { exit $exitCode }

Write-Step "Deployment finished successfully."
