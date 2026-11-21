@echo off
setlocal
cd /d "%~dp0src\web"
set "workbench_url=http://127.0.0.1:5174/"
node -e "const fs=require('node:fs'); const title=fs.readFileSync('index.html','utf8').match(/<title>.*?<\/title>/)[0]; fetch(process.env.workbench_url,{signal:AbortSignal.timeout(1500)}).then(async r=>{const page=await r.text(); process.exitCode=r.ok && page.includes(title) && page.includes('/@vite/client') ? 0 : 1}).catch(()=>{process.exitCode=1})"
if not errorlevel 1 (
  echo Workbench already running at %workbench_url%
  start "" "%workbench_url%"
  exit /b 0
)
if not exist node_modules\.bin\vite.cmd (
  call npm ci
  if errorlevel 1 goto failed
)
call npm run dev
if errorlevel 1 goto failed
exit /b 0

:failed
echo Frontend startup failed. See the message above.
pause
exit /b 1

