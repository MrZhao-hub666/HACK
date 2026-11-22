@echo off
setlocal
cd /d "%~dp0"
docker compose up -d --wait db || exit /b 1
uv run --locked uvicorn src.backend.api.main:app --host 127.0.0.1 --port 8081 --reload --reload-dir src/backend/api --reload-dir src/backend/app
