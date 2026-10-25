@echo off
setlocal
cd /d "%~dp0"
where node >nul 2>&1
if errorlevel 1 (
  echo Node.js 24 LTS is required. Install it from https://nodejs.org/
  echo Then run this file again.
  pause
  exit /b 1
)
echo =================================================
echo             SIGNAL 199X
echo =================================================
echo.
echo Your local game will open at http://localhost:3000
start "" "http://localhost:3000"
node server.mjs
echo.
echo Game server stopped.
pause
