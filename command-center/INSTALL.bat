@echo off
setlocal enabledelayedexpansion
title BVTech v32 Installer
color 0A
echo.
echo  ============================================================
echo   BVTech MSP Command Center v32.0 — POLISH EDITION
echo  ============================================================
echo.
echo   v32 includes:
echo     - Channel-specific content rewrites (4 voices from 1 article)
echo     - Staggered scheduler (Mon/Wed/Fri/Sat per-channel publishing)
echo     - Post queue manager
echo     - HubSpot v3 Engagements API tracking
echo     - Local SQLite event log + Windows Task Scheduler integration
echo     - Google Business Profile OAuth + localPosts
echo     - Cloudflare Pages Direct Upload (full site walk)
echo     - Forward-only cross-linking + retroactive backlinks script
echo.
echo   This installer will:
echo     1. Kill any running BVTech instances
echo     2. Verify Python is installed
echo     3. Install Python dependencies (flask + requests)
echo     4. Migrate config from previous version (if found)
echo     5. Compile BVTech-CommandCenter.exe (optional)
echo     6. Create a desktop shortcut
echo     7. Launch the app
echo.
echo   Press any key to begin, or close this window to cancel.
pause >nul

echo.
echo  [0/6] Killing any previous BVTech instances...
echo  -----------------------------------------------------
taskkill /F /IM BVTech-CommandCenter.exe >nul 2>nul
taskkill /F /FI "WINDOWTITLE eq BVTech*" >nul 2>nul

for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5678 ^| findstr LISTENING 2^>nul') do (
    echo  Killing PID %%a on port 5678...
    taskkill /F /PID %%a >nul 2>nul
)

echo  Waiting for port 5678 to be released...
set "PORT_FREE=0"
for /L %%i in (1,1,10) do (
    if "!PORT_FREE!"=="0" (
        netstat -aon 2>nul | findstr ":5678.*LISTENING" >nul 2>nul
        if errorlevel 1 (
            set "PORT_FREE=1"
            echo  Port 5678 is free.
        ) else (
            timeout /t 1 >nul 2>nul
        )
    )
)
if "!PORT_FREE!"=="0" (
    echo  Port 5678 may still be busy — the app will retry on startup.
)
echo  Previous instances cleared.
echo.

echo  [1/6] Checking Python installation...
echo  -----------------------------------------------------

set "PYTHON_CMD="
where python >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    goto :found_python
)
where python3 >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=python3"
    goto :found_python
)
where py >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=py"
    goto :found_python
)

echo.
echo  ERROR: Python is not installed or not in PATH.
echo  Please install Python 3.10+ from https://python.org
echo  Make sure to check "Add Python to PATH" during install.
echo.
pause
exit /b 1

:found_python
echo  Found Python: %PYTHON_CMD%
%PYTHON_CMD% --version 2>nul
echo.

echo  [2/6] Installing Python dependencies...
echo  -----------------------------------------------------

%PYTHON_CMD% -m pip install --upgrade pip >nul 2>nul
%PYTHON_CMD% -m pip install flask requests
if errorlevel 1 (
    echo.
    echo  pip install had warnings — this is usually OK.
    echo  If the app fails to start, run manually:
    echo    %PYTHON_CMD% -m pip install flask requests
)

%PYTHON_CMD% -m pip install pyinstaller >nul 2>nul
echo  Dependencies installed.
echo.

echo  [3/6] Migrating settings from previous version...
echo  -----------------------------------------------------
set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"

for %%d in ("..\BVTech_v31" "..\BVTech_v30" "..\BVTech_v29" "..\BVTech_v28" "..\BVTech_v27") do (
    if exist "%%d\bvtech_config.json" (
        if not exist "%APP_DIR%bvtech_config.json" (
            echo  Found config in %%d — migrating...
            copy /Y "%%d\bvtech_config.json" "%APP_DIR%bvtech_config.json" >nul
            if exist "%%d\posts_index.json" (
                copy /Y "%%d\posts_index.json" "%APP_DIR%posts_index.json" >nul
                echo  Migrated posts_index.json
            )
            if exist "%%d\local_events.db" (
                copy /Y "%%d\local_events.db" "%APP_DIR%local_events.db" >nul
                echo  Migrated local_events.db
            )
        ) else (
            echo  Config already exists — keeping current settings.
        )
        goto :config_done
    )
)
:config_done
echo  Settings migration complete.
echo.

echo  [4/6] Compiling BVTech-CommandCenter.exe (optional)...
echo  -----------------------------------------------------
echo  Compiling takes 1-2 minutes. Press Ctrl+C in 5 seconds to skip.
timeout /t 5 >nul

if exist "%APP_DIR%bvtech.ico" (
    set "ICON_FLAG=--icon=%APP_DIR%bvtech.ico"
) else (
    set "ICON_FLAG="
)

%PYTHON_CMD% -m PyInstaller --onefile --noconsole --name BVTech-CommandCenter %ICON_FLAG% ^
    --hidden-import "tacticalrmm_integration" ^
    --hidden-import "autoclaude" ^
    --hidden-import "autopilot" ^
    --hidden-import "prospect_scraper" ^
    --hidden-import "super_scraper" ^
    --hidden-import "email_campaign" ^
    --hidden-import "sms_campaign" ^
    --hidden-import "power_dialer" ^
    --hidden-import "dialpad_integration" ^
    --hidden-import "generate_prospects" ^
    --hidden-import "cloudflare_pages_deploy" ^
    --hidden-import "google_business_profile" ^
    --hidden-import "posts_index" ^
    --hidden-import "hubspot_tracker" ^
    --hidden-import "local_automation" ^
    --hidden-import "channel_rewriter" ^
    --hidden-import "post_queue" ^
    --add-data "favicon.png;." ^
    --add-data "tacticalrmm_integration.py;." ^
    --add-data "autoclaude.py;." ^
    --add-data "autopilot.py;." ^
    --add-data "prospect_scraper.py;." ^
    --add-data "super_scraper.py;." ^
    --add-data "email_campaign.py;." ^
    --add-data "sms_campaign.py;." ^
    --add-data "power_dialer.py;." ^
    --add-data "dialpad_integration.py;." ^
    --add-data "generate_prospects.py;." ^
    --add-data "cloudflare_pages_deploy.py;." ^
    --add-data "google_business_profile.py;." ^
    --add-data "posts_index.py;." ^
    --add-data "hubspot_tracker.py;." ^
    --add-data "local_automation.py;." ^
    --add-data "channel_rewriter.py;." ^
    --add-data "post_queue.py;." ^
    --clean --noconfirm bvtech_app.py

if exist "%APP_DIR%dist\BVTech-CommandCenter.exe" (
    copy /Y "%APP_DIR%dist\BVTech-CommandCenter.exe" "%APP_DIR%BVTech-CommandCenter.exe" >nul
    echo  BVTech-CommandCenter.exe compiled successfully.
) else (
    echo  Note: EXE compilation skipped or failed.
    echo  You can still run with: %PYTHON_CMD% bvtech_app.py
    echo  Or just double-click Start-BVTech.bat
)
echo.

echo  [5/6] Creating desktop shortcut...
echo  -----------------------------------------------------

set "SHORTCUT_VBS=%TEMP%\create_bvtech_shortcut.vbs"

if exist "%APP_DIR%BVTech-CommandCenter.exe" (
    set "TARGET=%APP_DIR%BVTech-CommandCenter.exe"
) else (
    set "TARGET=%APP_DIR%Start-BVTech.bat"
)

> "%SHORTCUT_VBS%" echo Set oWS = WScript.CreateObject("WScript.Shell")
>> "%SHORTCUT_VBS%" echo Set oLink = oWS.CreateShortcut(oWS.SpecialFolders("Desktop") ^& "\BVTech Command Center.lnk")
>> "%SHORTCUT_VBS%" echo oLink.TargetPath = "%TARGET%"
>> "%SHORTCUT_VBS%" echo oLink.WorkingDirectory = "%APP_DIR%"
>> "%SHORTCUT_VBS%" echo oLink.Description = "BVTech MSP Command Center v32"
if exist "%APP_DIR%bvtech.ico" (
    >> "%SHORTCUT_VBS%" echo oLink.IconLocation = "%APP_DIR%bvtech.ico"
)
>> "%SHORTCUT_VBS%" echo oLink.Save

cscript //nologo "%SHORTCUT_VBS%"
del "%SHORTCUT_VBS%" 2>nul

if exist "%USERPROFILE%\Desktop\BVTech Command Center.lnk" (
    echo  Desktop shortcut created.
) else (
    echo  Could not create shortcut. Run Start-BVTech.bat directly.
)
echo.

echo  [6/6] Launching BVTech Command Center v32...
echo  -----------------------------------------------------
echo.
echo  ============================================================
echo   INSTALL COMPLETE
echo.
echo   Your app is launching at http://localhost:5678
echo.
echo   First-run tips:
echo     1. Settings tab — paste your API keys (HubSpot, Anthropic,
echo        Google Places, Cloudflare, etc.)
echo     2. HS Track tab — paste your HubSpot BCC forwarding address
echo     3. Automation tab — review the 9 built-in tasks
echo     4. Read the What's New popup that auto-shows on first launch
echo.
echo   To run again later:
echo     Double-click "BVTech Command Center" on your desktop
echo     Or double-click Start-BVTech.bat in this folder
echo.
echo   If something crashes, check crash.log in the app folder.
echo  ============================================================
echo.

if exist "%APP_DIR%BVTech-CommandCenter.exe" (
    start "" "%APP_DIR%BVTech-CommandCenter.exe"
) else (
    start "" %PYTHON_CMD% "%APP_DIR%bvtech_app.py"
)

timeout /t 5 >nul
endlocal
