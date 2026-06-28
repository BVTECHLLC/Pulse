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
if ($TOKEN -ne "") {{ & $exe enroll $TOKEN --url $PULSE_URL }}
# Auto-start at boot via Scheduled Task (SYSTEM), and start it now.
$action = "cmd /c set PULSE_URL=$PULSE_URL && `"$exe`" run"
schtasks /Create /TN "BVTechOpsPilot" /TR $action /SC ONSTART /RU SYSTEM /F | Out-Null
Start-Process -WindowStyle Hidden $exe -ArgumentList "run --url $PULSE_URL"
Write-Host "BVTech OpsPilot standalone agent installed and reporting to $PULSE_URL."
"""
    return script


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
