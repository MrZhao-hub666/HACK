@echo off
setlocal
cd /d "%~dp0"
docker compose up -d --wait db
if errorlevel 1 exit /b 1
powershell -NoProfile -Command "try { $routes=(Invoke-RestMethod 'http://127.0.0.1:8081/openapi.json' -TimeoutSec 2).paths.PSObject.Properties.Name; if ($routes -contains '/api/catalog' -and $routes -contains '/api/inquiries/{ident}/selection') { exit 0 } } catch {} exit 1"
if not errorlevel 1 (
  echo Unified API already running at http://127.0.0.1:8081
  exit /b 0
)
uv run --locked uvicorn src.api.main:app --host 127.0.0.1 --port 8081 --reload --reload-dir src/api --reload-dir src/backend/app
