$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
$pnpm = (Get-Command 'pnpm.cmd' -ErrorAction Stop).Source

if (-not (Test-Path $python)) {
    py -3 -m venv (Join-Path $root 'backend\.venv')
    & $python -m pip install -r (Join-Path $root 'backend\requirements.txt')
}

docker compose --project-directory $root up -d redis
$backendRunning = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue
$frontendRunning = Get-NetTCPConnection -State Listen -LocalPort 5173 -ErrorAction SilentlyContinue

if (-not $backendRunning) {
    Start-Process -FilePath $python -ArgumentList '-m','uvicorn','app.main:app','--reload','--port','8000' -WorkingDirectory (Join-Path $root 'backend') -WindowStyle Hidden
}

if (-not $frontendRunning) {
    Start-Process -FilePath $pnpm -ArgumentList 'dev' -WorkingDirectory $root -WindowStyle Hidden
}

Write-Host 'SkillScope démarre sur http://localhost:5173' -ForegroundColor Cyan
