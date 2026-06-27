@echo off
:: ============================================================
::  BVTech OpsPilot Agent - Windows Service Installer
:: ============================================================
::  Installs the OpsPilot telemetry agent as a Windows service
::  so it runs at boot and reports health every 5 minutes.
::
::  CONSENT: By installing, the device owner agrees to share
::  health telemetry (CPU/RAM/disk, logged-in user, antivirus
::  status, patch status) with BVTech LLC for IT monitoring
::  and support. No remote control, screen capture, keystroke
::  logging, or file access is performed by this agent.
::
::  REQUIREMENTS:
::    - Python 3.10+ installed and on PATH
::    - NSSM (https://nssm.cc) placed next to this script, OR
::      run with the bundled nssm.exe
::    - An enrollment token from BVTech (one per device)
::
::  USAGE (run as Administrator):
::    install_service.bat <ENROLLMENT_TOKEN>
:: ============================================================

setlocal
set SERVICE_NAME=BVTechOpsPilotAgent
set SCRIPT_DIR=%~dp0
set AGENT=%SCRIPT_DIR%opspilot_agent.py
set TOKEN=%1

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo This installer must be run as Administrator. Right-click ^> Run as administrator.
    pause
    exit /b 1
)

if "%TOKEN%"=="" (
    echo Usage: install_service.bat ^<ENROLLMENT_TOKEN^>
    echo Get an enrollment token from BVTech OpsPilot ^(staff mints it per device^).
    pause
    exit /b 1
)

echo.
echo  ============================================================
echo   BVTech OpsPilot Agent - consent notice
echo  ============================================================
echo   This agent shares device HEALTH telemetry with BVTech LLC.
echo   It does NOT enable remote control, screen capture, key
echo   logging, or file access. You can uninstall it any time.
echo  ============================================================
echo.
set /p CONSENT="Type YES to consent and continue: "
if /i not "%CONSENT%"=="YES" (
    echo Cancelled. Nothing installed.
    exit /b 0
)

:: Ensure psutil is available for richer telemetry
python -m pip install --quiet psutil

:: Enroll first (writes config to %ProgramData%\BVTechOpsPilot\agent.json)
echo Enrolling device...
python "%AGENT%" enroll %TOKEN%
if %errorLevel% neq 0 (
    echo Enrollment failed. Check the token and network, then retry.
    pause
    exit /b 1
)

:: Install as a service via NSSM
set NSSM=%SCRIPT_DIR%nssm.exe
if not exist "%NSSM%" set NSSM=nssm

for /f "delims=" %%P in ('where python') do set PYEXE=%%P & goto :gotpy
:gotpy

"%NSSM%" install %SERVICE_NAME% "%PYEXE%" "\"%AGENT%\" run"
"%NSSM%" set %SERVICE_NAME% AppDirectory "%SCRIPT_DIR%"
"%NSSM%" set %SERVICE_NAME% DisplayName "BVTech OpsPilot Agent"
"%NSSM%" set %SERVICE_NAME% Description "Sends device health telemetry to BVTech OpsPilot. No remote control."
"%NSSM%" set %SERVICE_NAME% Start SERVICE_AUTO_START
"%NSSM%" start %SERVICE_NAME%

echo.
echo  Service installed and started: %SERVICE_NAME%
echo  To remove later:  %NSSM% remove %SERVICE_NAME% confirm
echo.
pause
endlocal
