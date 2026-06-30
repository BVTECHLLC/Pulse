"""Agent download & one-click install endpoints.

The agent script and install helpers are public (the agent code isn't secret —
security lives in the time-limited, signed, client-scoped *enrollment token*).
The install scripts auto-target whatever host served them, so an agent installed
from portal.bvtech.org reports back to portal.bvtech.org with no manual config.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse

from ...core.config import get_settings

router = APIRouter(prefix="/download", tags=["agent-download"])
_s = get_settings()


def _agent_path() -> Path | None:
    """Find the agent script across dev + container layouts (robust to where the
    app is mounted)."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "agent" / "opspilot_agent.py",   # /app/agent (container) & repo
        here.parents[2] / "agent" / "opspilot_agent.py",   # app/agent fallback
        Path("/app/agent/opspilot_agent.py"),
        Path.cwd() / "agent" / "opspilot_agent.py",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _base_url(request: Request) -> str:
    # Honor the proxy (Cloudflare Tunnel / Caddy) so we emit the public https URL.
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}".rstrip("/")


@router.get("/agent")
def download_agent():
    """The raw agent script."""
    path = _agent_path()
    if not path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent file not found on server")
    return FileResponse(str(path), media_type="text/x-python", filename="opspilot_agent.py")


def _binary_path(name: str) -> Path | None:
    """Built standalone binaries live in agent/dist/ (populated by CI or synced
    from a release). Returns the path if present."""
    here = Path(__file__).resolve()
    for root in (here.parents[3], here.parents[2], Path("/app"), Path.cwd()):
        p = root / "agent" / "dist" / name
        if p.is_file():
            return p
    return None


@router.get("/agent.exe")
def download_agent_exe():
    """Standalone Windows binary (no Python needed). Served from agent/dist/ if
    present; otherwise we redirect to the published GitHub release asset (the repo
    is public, so the `latest` URL downloads without auth). This means the .exe
    works the moment the build-agent workflow publishes it — no server sync."""
    p = _binary_path("opspilot-agent.exe")
    if p:
        return FileResponse(str(p), media_type="application/vnd.microsoft.portable-executable",
                            filename="opspilot-agent.exe")
    return RedirectResponse(f"{_s.AGENT_RELEASE_BASE}/opspilot-agent.exe", status_code=302)


@router.get("/agent-linux")
def download_agent_linux():
    """Standalone Linux binary (no Python needed). Same strategy as agent.exe."""
    p = _binary_path("opspilot-agent")
    if p:
        return FileResponse(str(p), media_type="application/octet-stream",
                            filename="opspilot-agent")
    return RedirectResponse(f"{_s.AGENT_RELEASE_BASE}/opspilot-agent", status_code=302)


@router.get("/install.sh", response_class=PlainTextResponse)
def install_sh(request: Request, token: str = ""):
    base = _base_url(request)
    script = f"""#!/usr/bin/env bash
# BVTech OpsPilot — agent installer (Linux/macOS)
set -e
PULSE_URL="{base}"
TOKEN="{token}"
DEST="${{HOME}}/.bvtech-pulse"
echo "Installing BVTech OpsPilot agent from $PULSE_URL ..."
mkdir -p "$DEST"
if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$PULSE_URL/download/agent" -o "$DEST/opspilot_agent.py"
else
  wget -qO "$DEST/opspilot_agent.py" "$PULSE_URL/download/agent"
fi
python3 -m pip install --user psutil >/dev/null 2>&1 || true
cd "$DEST"
if [ -n "$TOKEN" ]; then
  PULSE_URL="$PULSE_URL" python3 opspilot_agent.py enroll "$TOKEN" --url "$PULSE_URL"
fi
# Run in the background (for a permanent install, wrap this in a systemd unit).
PULSE_URL="$PULSE_URL" nohup python3 opspilot_agent.py run --url "$PULSE_URL" >/dev/null 2>&1 &
echo "BVTech OpsPilot agent installed and reporting to $PULSE_URL."
"""
    return script


@router.get("/install-exe.ps1", response_class=PlainTextResponse)
def install_exe_ps1(request: Request, token: str = ""):
    """No-Python Windows installer: pulls the standalone .exe and runs it as a
    boot-time Scheduled Task. Endpoints need nothing pre-installed."""
    base = _base_url(request)
    script = f"""# BVTech OpsPilot - standalone agent installer (Windows, run as Administrator)
# Python-free - uses the prebuilt opspilot-agent.exe.
$ErrorActionPreference = "Stop"
$PULSE_URL = "{base}"
$TOKEN = "{token}"
$dest = "$env:ProgramData\\BVTechOpsPilot"
$exe  = "$dest\\opspilot-agent.exe"
Write-Host "Installing BVTech OpsPilot standalone agent from $PULSE_URL ..."
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Invoke-WebRequest -Uri "$PULSE_URL/download/agent.exe" -OutFile $exe
$env:PULSE_URL = $PULSE_URL
if ($TOKEN -ne "") {{
  # Drop a single-use token file beside the exe so the boot task self-enrolls
  # even if this direct enroll is interrupted (the agent deletes it after use).
  @{{ token = $TOKEN; url = $PULSE_URL }} | ConvertTo-Json | Set-Content -Encoding ascii "$dest\\opspilot-enroll.json"
  & $exe enroll $TOKEN --url $PULSE_URL
}}
# Auto-start at boot via Scheduled Task (SYSTEM), and start it now.
$action = "cmd /c set PULSE_URL=$PULSE_URL && `"$exe`" run"
schtasks /Create /TN "BVTechOpsPilot" /TR $action /SC ONSTART /RU SYSTEM /F | Out-Null
Start-Process -WindowStyle Hidden $exe -ArgumentList "run --url $PULSE_URL"
Write-Host "BVTech OpsPilot standalone agent installed and reporting to $PULSE_URL."
"""
    return script


@router.get("/deploy.cmd", response_class=PlainTextResponse)
def deploy_cmd(request: Request, token: str = ""):
    """Preconfigured ("preloaded") one-file installer: a Windows batch file with
    the client's enrollment token baked in. The client just double-clicks it —
    no copy-paste, no token to enter. It self-elevates to Administrator, then
    hands off to the proven install-exe.ps1 (downloads the standalone .exe,
    enrolls with the embedded token, and registers the boot Scheduled Task).
    Generated per-client from the dashboard's Deploy Agent card."""
    base = _base_url(request)
    # Batch needs the literal token; install-exe.ps1 does the real work.
    script = (
        "@echo off\r\n"
        "REM BVTech OpsPilot - preconfigured agent installer (just double-click)\r\n"
        f"REM Portal: {base}\r\n"
        "setlocal\r\n"
        f'set "PULSE_URL={base}"\r\n'
        f'set "OPSPILOT_ENROLL_TOKEN={token}"\r\n'
        "echo Installing BVTech OpsPilot agent (this computer will connect to %PULSE_URL%) ...\r\n"
        "REM Self-elevate to Administrator if needed.\r\n"
        'net session >nul 2>&1\r\n'
        "if %errorlevel% NEQ 0 (\r\n"
        "  echo Requesting administrator rights...\r\n"
        "  powershell -NoProfile -Command \"Start-Process -Verb RunAs -FilePath '%~f0'\"\r\n"
        "  exit /b\r\n"
        ")\r\n"
        "powershell -ExecutionPolicy Bypass -NoProfile -Command "
        f"\"irm '{base}/download/install-exe.ps1?token={token}' | iex\"\r\n"
        "echo.\r\n"
        "echo BVTech OpsPilot agent installed. This window can be closed.\r\n"
        "pause\r\n"
    )
    return PlainTextResponse(
        script,
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="bvtech-opspilot-install.cmd"'},
    )


@router.get("/install.ps1", response_class=PlainTextResponse)
def install_ps1(request: Request, token: str = ""):
    base = _base_url(request)
    script = f"""# BVTech OpsPilot - agent installer (Windows PowerShell, run as Administrator)
$ErrorActionPreference = "Stop"
$PULSE_URL = "{base}"
$TOKEN = "{token}"
$dest = "$env:ProgramData\\BVTechOpsPilot"
Write-Host "Installing BVTech OpsPilot agent from $PULSE_URL ..."
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Invoke-WebRequest -Uri "$PULSE_URL/download/agent" -OutFile "$dest\\opspilot_agent.py"
$py = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $py) {{
  Write-Host "Python not found - installing it automatically via winget..."
  try {{
    winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
  }} catch {{ }}
  $py = (Get-Command python -ErrorAction SilentlyContinue)
  if (-not $py) {{
    Write-Host "Could not auto-install Python. Install it once with:  winget install -e --id Python.Python.3.12  then re-run this command."
    exit 1
  }}
}}
python -m pip install psutil 2>$null
$env:PULSE_URL = $PULSE_URL
if ($TOKEN -ne "") {{ python "$dest\\opspilot_agent.py" enroll $TOKEN --url $PULSE_URL }}
# Auto-start at boot via Scheduled Task, and start it now.
$action = "cmd /c set PULSE_URL=$PULSE_URL && python `"$dest\\opspilot_agent.py`" run"
schtasks /Create /TN "BVTechOpsPilot" /TR $action /SC ONSTART /RU SYSTEM /F | Out-Null
Start-Process -WindowStyle Hidden python -ArgumentList "`"$dest\\opspilot_agent.py`" run --url $PULSE_URL"
Write-Host "BVTech OpsPilot agent installed and reporting to $PULSE_URL."
"""
    return script
