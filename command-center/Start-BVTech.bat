@echo off
setlocal enabledelayedexpansion
title BVTech Command Center v19
cd /d "%~dp0"

:: v19: Kill any previous instance first — with proper wait
echo Checking for previous instances...

:: Kill by EXE name
taskkill /F /IM BVTech-CommandCenter.exe >nul 2>nul

:: Kill by port
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5678 ^| findstr LISTENING 2^>nul') do (
    echo Killing previous instance (PID %%a)...
    taskkill /F /PID %%a >nul 2>nul
)

:: Wait for port release (up to 5 seconds)
for /L %%i in (1,1,5) do (
    netstat -aon 2>nul | findstr ":5678.*LISTENING" >nul 2>nul
    if not errorlevel 1 (
        timeout /t 1 >nul 2>nul
    )
)

:: Try EXE first, fallback to Python
if exist "%~dp0BVTech-CommandCenter.exe" (
    start "" "%~dp0BVTech-CommandCenter.exe"
) else (
    echo Starting BVTech Command Center v19...
    echo.
    :: Find Python
    where python >nul 2>nul && (
        python bvtech_app.py
        goto :done
    )
    where py >nul 2>nul && (
        py bvtech_app.py
        goto :done
    )
    where python3 >nul 2>nul && (
        python3 bvtech_app.py
        goto :done
    )
    echo ERROR: Python not found. Install from https://python.org
    pause
)

:done
endlocal
