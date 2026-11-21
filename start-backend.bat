@echo off
setlocal
cd /d "%~dp0"
docker compose up -d --wait db
if errorlevel 1 exit /b 1
if not exist ".venv\Scripts\python.exe" (
  uv venv .venv --python 3.12
  if errorlevel 1 exit /b 1
)
uv pip install --python ".venv\Scripts\python.exe" -r src\api\requirements.txt
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m scripts.dev_backend

