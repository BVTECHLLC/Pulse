@echo off
title BVTech v19 — EXE Compiler
color 0B
cd /d "%~dp0"

echo.
echo  Building BVTech-CommandCenter.exe (v19)...
echo  This may take 1-2 minutes.
echo.

:: Find Python
set "PY=python"
where python >nul 2>nul || set "PY=py"

if exist "%~dp0bvtech.ico" (
    set "ICON_FLAG=--icon=%~dp0bvtech.ico"
) else (
    set "ICON_FLAG="
)

:: v19: --hidden-import so modules are importable inside the bundle
::      --add-data so subprocess can find .py files in _MEIPASS
%PY% -m PyInstaller --onefile --noconsole --name BVTech-CommandCenter %ICON_FLAG% ^
    --add-data "bvtech_config.json;." ^
    --add-data "favicon.png;." ^
    --hidden-import "tacticalrmm_integration" ^
    --hidden-import "autoclaude" ^
    --hidden-import "autopilot" ^
    --hidden-import "prospect_scraper" ^
    --hidden-import "email_campaign" ^
    --hidden-import "sms_campaign" ^
    --hidden-import "power_dialer" ^
    --hidden-import "dialpad_integration" ^
    --hidden-import "generate_prospects" ^
    --add-data "tacticalrmm_integration.py;." ^
    --add-data "autoclaude.py;." ^
    --add-data "autopilot.py;." ^
    --add-data "prospect_scraper.py;." ^
    --add-data "email_campaign.py;." ^
    --add-data "sms_campaign.py;." ^
    --add-data "power_dialer.py;." ^
    --add-data "dialpad_integration.py;." ^
    --add-data "generate_prospects.py;." ^
    --clean --noconfirm bvtech_app.py

if exist "dist\BVTech-CommandCenter.exe" (
    copy /Y "dist\BVTech-CommandCenter.exe" "BVTech-CommandCenter.exe" >nul
    echo.
    echo  ✅ BVTech-CommandCenter.exe compiled successfully!
    echo  File: %~dp0BVTech-CommandCenter.exe
) else (
    echo.
    echo  ⚠ Build failed. Run with: %PY% bvtech_app.py
)

echo.
pause
