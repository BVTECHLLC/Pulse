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
# Pull the agent from GitHub raw first (Cloudflare-free); fall back to the portal.
AGENT_RAW="{_s.AGENT_SOURCE_RAW_URL}"
UA="Mozilla/5.0 (X11; Linux x86_64) OpsPilotInstaller"
get() {{ if command -v curl >/dev/null 2>&1; then curl -fsSL -A "$UA" "$1" -o "$2"; else wget -q -U "$UA" -O "$2" "$1"; fi; }}
if ! get "$AGENT_RAW" "$DEST/opspilot_agent.py"; then get "$PULSE_URL/download/agent" "$DEST/opspilot_agent.py"; fi
if [ ! -s "$DEST/opspilot_agent.py" ] || ! head -1 "$DEST/opspilot_agent.py" | grep -q python; then
  echo "ERROR: could not download the agent (check internet access to github.com)." >&2; exit 1
fi
python3 -m pip install --user psutil >/dev/null 2>&1 || true
cd "$DEST"
if [ -n "$TOKEN" ]; then
  if ! PULSE_URL="$PULSE_URL" python3 opspilot_agent.py enroll "$TOKEN" --url "$PULSE_URL" --no-run; then
    echo "ERROR: enrollment failed (token expired, or the portal API is blocked by Cloudflare)." >&2; exit 1
  fi
fi
# Run in the background (for a permanent install, wrap this in a systemd unit).
PULSE_URL="$PULSE_URL" nohup python3 opspilot_agent.py run --url "$PULSE_URL" >/dev/null 2>&1 &
echo "SUCCESS: BVTech OpsPilot agent installed and enrolled — it will appear under Devices shortly."
"""
    return script


def _ps_install_body(base: str, token: str) -> str:
    """The shared PowerShell install logic (used by install-exe.ps1 AND inlined
    into deploy.cmd so the double-click installer never has to fetch a script
    through Cloudflare). Downloads the standalone .exe from the GitHub release
    (NOT behind the portal's Cloudflare), verifies it, enrolls, registers the
    boot task — and FAILS LOUDLY instead of pretending it worked."""
    exe_url = f"{_s.AGENT_RELEASE_BASE}/opspilot-agent.exe"
    return f"""$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$PULSE_URL = "{base}"
$TOKEN = "{token}"
$EXE_URL = "{exe_url}"
$dest = "$env:ProgramData\\BVTechOpsPilot"
$exe  = "$dest\\opspilot-agent.exe"
$UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OpsPilotInstaller"
Write-Host "Installing BVTech OpsPilot agent -> $PULSE_URL"
New-Item -ItemType Directory -Force -Path $dest | Out-Null

# 1) Download the standalone .exe from the GitHub release (Cloudflare-free),
#    with retries. Fall back to the portal's redirect only if GitHub is blocked.
$ok = $false
foreach ($src in @($EXE_URL, "$PULSE_URL/download/agent.exe")) {{
  for ($i=1; $i -le 3; $i++) {{
    try {{
      Invoke-WebRequest -Uri $src -OutFile $exe -UserAgent $UA -MaximumRedirection 5 -TimeoutSec 120
      if ((Test-Path $exe) -and ((Get-Item $exe).Length -gt 1000000)) {{ $ok = $true; break }}
    }} catch {{ Start-Sleep -Seconds ([math]::Min(2*$i,8)) }}
  }}
  if ($ok) {{ break }}
}}
if (-not $ok) {{
  throw "Could not download the agent. Check internet access to github.com (and that Cloudflare is not blocking $PULSE_URL/download/agent.exe)."
}}
# Sanity-check it's a real Windows executable (MZ header), not an HTML error page.
$fs = [System.IO.File]::OpenRead($exe); $b = New-Object byte[] 2; $null = $fs.Read($b,0,2); $fs.Close()
if ($b[0] -ne 0x4D -or $b[1] -ne 0x5A) {{ throw "Downloaded file is not a valid agent .exe (got an error/challenge page)." }}

$env:PULSE_URL = $PULSE_URL
$enrolled = $true
if ($TOKEN -ne "") {{
  # Drop a single-use token file so the boot task can still self-enroll if the
  # direct enroll below is interrupted (the agent deletes it after use).
  @{{ token = $TOKEN; url = $PULSE_URL }} | ConvertTo-Json | Set-Content -Encoding ascii "$dest\\opspilot-enroll.json"
  & $exe enroll $TOKEN --url $PULSE_URL --no-run
  if ($LASTEXITCODE -ne 0) {{ $enrolled = $false }}
}}
# Auto-start at boot via Scheduled Task (SYSTEM), and start it now.
$action = "cmd /c set PULSE_URL=$PULSE_URL && `"$exe`" run"
schtasks /Create /TN "BVTechOpsPilot" /TR $action /SC ONSTART /RU SYSTEM /F | Out-Null
Start-Process -WindowStyle Hidden $exe -ArgumentList "run --url $PULSE_URL"
if ($enrolled) {{
  Write-Host "SUCCESS: BVTech OpsPilot agent installed and enrolled. It will appear under Devices shortly."
}} else {{
  Write-Host "AGENT INSTALLED, BUT ENROLLMENT FAILED. The token may be expired (72h) or the portal API is being blocked by Cloudflare. Generate a fresh installer from Devices -> Deploy Agent, or apply the Cloudflare skip rule (see docs)."
  exit 1
}}
"""


@router.get("/install-exe.ps1", response_class=PlainTextResponse)
def install_exe_ps1(request: Request, token: str = ""):
    """No-Python Windows installer: pulls the standalone .exe from the GitHub
    release (Cloudflare-free), enrolls, and registers a boot Scheduled Task.
    Verifies the download and reports real success/failure."""
    base = _base_url(request)
    return ("# BVTech OpsPilot - standalone agent installer (Windows, run as Administrator)\n"
            "# Python-free - uses the prebuilt opspilot-agent.exe.\n"
            + _ps_install_body(base, token))


@router.get("/deploy.cmd", response_class=PlainTextResponse)
def deploy_cmd(request: Request, token: str = ""):
    """Preconfigured ("preloaded") one-file installer: a Windows batch file with
    the client's enrollment token baked in. The client just double-clicks it.

    It self-elevates to Administrator, then runs the install PowerShell that is
    **embedded directly in this file** (base64) — so it never fetches a script
    through the portal's Cloudflare (the old `irm … | iex` would get a Cloudflare
    challenge page and silently fail). The .exe still comes from the GitHub
    release. The batch reports the REAL result instead of always saying 'done'."""
    import base64
    base = _base_url(request)
    # PowerShell -EncodedCommand wants UTF-16LE base64.
    ps_b64 = base64.b64encode(_ps_install_body(base, token).encode("utf-16-le")).decode("ascii")
    script = (
        "@echo off\r\n"
        "REM BVTech OpsPilot - preconfigured agent installer (just double-click)\r\n"
        f"REM Portal: {base}\r\n"
        "setlocal\r\n"
        "echo Installing BVTech OpsPilot agent ...\r\n"
        "REM Self-elevate to Administrator if needed.\r\n"
        'net session >nul 2>&1\r\n'
        "if %errorlevel% NEQ 0 (\r\n"
        "  echo Requesting administrator rights...\r\n"
        "  powershell -NoProfile -Command \"Start-Process -Verb RunAs -FilePath '%~f0'\"\r\n"
        "  exit /b\r\n"
        ")\r\n"
        f"powershell -ExecutionPolicy Bypass -NoProfile -EncodedCommand {ps_b64}\r\n"
        "if %errorlevel% NEQ 0 (\r\n"
        "  echo.\r\n"
        "  echo *** INSTALL DID NOT COMPLETE — see the message above. ***\r\n"
        ") else (\r\n"
        "  echo.\r\n"
        "  echo BVTech OpsPilot agent installed and enrolled. You can close this window.\r\n"
        ")\r\n"
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
$AGENT_RAW = "{_s.AGENT_SOURCE_RAW_URL}"
$UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OpsPilotInstaller"
Write-Host "Installing BVTech OpsPilot agent from $PULSE_URL ..."
New-Item -ItemType Directory -Force -Path $dest | Out-Null
# Pull the agent from GitHub raw (Cloudflare-free); fall back to the portal.
try {{ Invoke-WebRequest -Uri $AGENT_RAW -OutFile "$dest\\opspilot_agent.py" -UserAgent $UA -TimeoutSec 60 }}
catch {{ Invoke-WebRequest -Uri "$PULSE_URL/download/agent" -OutFile "$dest\\opspilot_agent.py" -UserAgent $UA -TimeoutSec 60 }}
if (-not (Test-Path "$dest\\opspilot_agent.py") -or (Get-Item "$dest\\opspilot_agent.py").Length -lt 1000) {{
  Write-Host "ERROR: could not download the agent (check internet access to github.com)."; exit 1
}}
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
$enrolled = $true
if ($TOKEN -ne "") {{
  python "$dest\\opspilot_agent.py" enroll $TOKEN --url $PULSE_URL --no-run
  if ($LASTEXITCODE -ne 0) {{ $enrolled = $false }}
}}
# Auto-start at boot via Scheduled Task, and start it now.
$action = "cmd /c set PULSE_URL=$PULSE_URL && python `"$dest\\opspilot_agent.py`" run"
schtasks /Create /TN "BVTechOpsPilot" /TR $action /SC ONSTART /RU SYSTEM /F | Out-Null
Start-Process -WindowStyle Hidden python -ArgumentList "`"$dest\\opspilot_agent.py`" run --url $PULSE_URL"
if ($enrolled) {{
  Write-Host "SUCCESS: BVTech OpsPilot agent installed and enrolled — it will appear under Devices shortly."
}} else {{
  Write-Host "AGENT INSTALLED, BUT ENROLLMENT FAILED (token expired, or the portal API is blocked by Cloudflare). Generate a fresh installer or apply the Cloudflare skip rule."; exit 1
}}
"""
    return script
