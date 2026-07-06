"""Agent download & one-click install endpoints.

The agent is a native PowerShell script (zero dependencies — no Python, no
prebuilt .exe, no external downloads). Security lives entirely in the
time-limited, signed, client-scoped *enrollment token*, so the agent code and
installers are public. The Windows one-click installer EMBEDS the agent inside
itself (base64), so once the client downloads the single .cmd there is nothing
else to fetch — it can't be broken by a missing release asset or a Cloudflare
challenge. Installers auto-target whatever host served them.
"""
from __future__ import annotations

import base64
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, PlainTextResponse

from ...core.config import get_settings

router = APIRouter(prefix="/download", tags=["agent-download"])
_s = get_settings()


def _agent_dir() -> Path:
    here = Path(__file__).resolve()
    for root in (here.parents[3], here.parents[2], Path("/app"), Path.cwd()):
        if (root / "agent").is_dir():
            return root / "agent"
    return here.parents[3] / "agent"


def _agent_ps1() -> str | None:
    p = _agent_dir() / "opspilot_agent.ps1"
    return p.read_text(encoding="utf-8") if p.is_file() else None


def _agent_py() -> Path | None:
    p = _agent_dir() / "opspilot_agent.py"
    return p if p.is_file() else None


def _base_url(request: Request) -> str:
    # Honor the proxy (Cloudflare Tunnel / Caddy) so we emit the public https URL.
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}".rstrip("/")


# --------------------------------------------------------------------------- #
# Raw agent sources
# --------------------------------------------------------------------------- #
@router.get("/agent.ps1", response_class=PlainTextResponse)
def download_agent_ps1():
    """The native PowerShell agent (Windows). Zero dependencies."""
    src = _agent_ps1()
    if src is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent file not found on server")
    return PlainTextResponse(src, media_type="text/plain",
                             headers={"Content-Disposition": 'attachment; filename="opspilot_agent.ps1"'})


@router.get("/agent")
def download_agent():
    """The raw Python agent (Linux/macOS)."""
    path = _agent_py()
    if not path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent file not found on server")
    return FileResponse(str(path), media_type="text/x-python", filename="opspilot_agent.py")


# --------------------------------------------------------------------------- #
# Windows one-click installer — the agent is EMBEDDED, nothing is downloaded.
# --------------------------------------------------------------------------- #
def _windows_bootstrap_ps(base: str, token: str) -> str:
    """A self-contained PowerShell installer: it carries the whole agent as a
    base64 blob, writes it to %ProgramData%, then runs the agent's `install`
    action (enroll + schedule + first check-in). No network fetch of the agent,
    so it can never fail on a missing release asset or a proxy challenge."""
    src = _agent_ps1()
    if src is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent file not found on server")
    agent_b64 = base64.b64encode(src.encode("utf-8")).decode("ascii")
    return f"""$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$PULSE_URL = "{base}"
$TOKEN = "{token}"
$dest = Join-Path $env:ProgramData "BVTechOpsPilot"
$agent = Join-Path $dest "agent.ps1"
Write-Host "Installing BVTech OpsPilot agent -> $PULSE_URL"
New-Item -ItemType Directory -Force -Path $dest | Out-Null

# Decode the embedded agent (base64) straight to disk — nothing is downloaded.
$bytes = [Convert]::FromBase64String("{agent_b64}")
[System.IO.File]::WriteAllBytes($agent, $bytes)

# Enroll + register the scheduled task + first check-in, in one shot.
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $agent install $TOKEN -Url $PULSE_URL
if ($LASTEXITCODE -ne 0) {{
  throw "Enrollment failed - the token may be expired (72h) or the portal is unreachable from this PC. Generate a fresh installer from Devices -> Onboard a device."
}}
Write-Host "SUCCESS: BVTech OpsPilot agent installed and enrolled. This device will appear under Devices within a few seconds."
"""


@router.get("/deploy.cmd", response_class=PlainTextResponse)
def deploy_cmd(request: Request, token: str = ""):
    """The preconfigured one-file installer (double-click). Self-elevates to
    Administrator, then runs the embedded PowerShell installer (which carries the
    agent inside it). The enrollment token is baked in — nothing to type."""
    base = _base_url(request)
    ps_b64 = base64.b64encode(_windows_bootstrap_ps(base, token).encode("utf-16-le")).decode("ascii")
    script = (
        "@echo off\r\n"
        "REM BVTech OpsPilot - preconfigured agent installer (double-click to run)\r\n"
        f"REM Portal: {base}\r\n"
        "setlocal\r\n"
        "echo ============================================\r\n"
        "echo   BVTech OpsPilot - device onboarding\r\n"
        "echo ============================================\r\n"
        "net session >nul 2>&1\r\n"
        "if %errorlevel% NEQ 0 (\r\n"
        "  echo Requesting administrator rights...\r\n"
        "  powershell -NoProfile -Command \"Start-Process -Verb RunAs -FilePath '%~f0'\"\r\n"
        "  exit /b\r\n"
        ")\r\n"
        f"powershell -ExecutionPolicy Bypass -NoProfile -EncodedCommand {ps_b64}\r\n"
        "if %errorlevel% NEQ 0 (\r\n"
        "  echo.\r\n"
        "  echo *** INSTALL DID NOT COMPLETE - see the message above. ***\r\n"
        ") else (\r\n"
        "  echo.\r\n"
        "  echo This device is now managed by BVTech. You can close this window.\r\n"
        ")\r\n"
        "pause\r\n"
    )
    return PlainTextResponse(
        script, media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="bvtech-opspilot-install.cmd"'})


@router.get("/install.ps1", response_class=PlainTextResponse)
def install_ps1(request: Request, token: str = ""):
    """One-line PowerShell installer (Admin): same embedded agent, for techs who
    prefer a paste-one-line flow over a downloaded file."""
    base = _base_url(request)
    return PlainTextResponse(
        "# BVTech OpsPilot - agent installer (run in an elevated PowerShell)\r\n"
        + _windows_bootstrap_ps(base, token))


# install-exe.ps1 kept as an alias so old links/QR codes still resolve — it now
# serves the same dependency-free installer.
@router.get("/install-exe.ps1", response_class=PlainTextResponse)
def install_exe_ps1(request: Request, token: str = ""):
    return install_ps1(request, token)


@router.get("/install.sh", response_class=PlainTextResponse)
def install_sh(request: Request, token: str = ""):
    """Linux/macOS installer — uses the Python agent (Python 3 ships on macOS and
    virtually every Linux). Enrolls and runs the agent in the background."""
    base = _base_url(request)
    return f"""#!/usr/bin/env bash
# BVTech OpsPilot - agent installer (Linux/macOS)
set -e
PULSE_URL="{base}"
TOKEN="{token}"
DEST="${{HOME}}/.bvtech-pulse"
echo "Installing BVTech OpsPilot agent from $PULSE_URL ..."
mkdir -p "$DEST"
UA="Mozilla/5.0 OpsPilotInstaller"
get() {{ if command -v curl >/dev/null 2>&1; then curl -fsSL -A "$UA" "$1" -o "$2"; else wget -q -U "$UA" -O "$2" "$1"; fi; }}
get "$PULSE_URL/download/agent" "$DEST/opspilot_agent.py" || {{ echo "ERROR: could not download the agent from $PULSE_URL" >&2; exit 1; }}
if [ ! -s "$DEST/opspilot_agent.py" ]; then echo "ERROR: agent download was empty." >&2; exit 1; fi
python3 -m pip install --user psutil >/dev/null 2>&1 || true
cd "$DEST"
if [ -n "$TOKEN" ]; then
  if ! PULSE_URL="$PULSE_URL" python3 opspilot_agent.py enroll "$TOKEN" --url "$PULSE_URL" --no-run; then
    echo "ERROR: enrollment failed (token expired, or the portal API is unreachable)." >&2; exit 1
  fi
fi
PULSE_URL="$PULSE_URL" nohup python3 opspilot_agent.py run --url "$PULSE_URL" >/dev/null 2>&1 &
echo "SUCCESS: BVTech OpsPilot agent installed and enrolled - it will appear under Devices shortly."
"""
