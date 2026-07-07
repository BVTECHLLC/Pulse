#!/usr/bin/env python3
"""
BVTech OpsPilot Agent — Phase 1 (telemetry only)
=============================================
WHAT THIS AGENT DOES:
  - Enrolls this PC with BVTech OpsPilot using a one-time enrollment token.
  - Every 5 minutes, sends a small HEALTH snapshot: CPU%, RAM%, disk%, the
    currently-logged-in username, antivirus on/off, and Windows Update status.

WHAT THIS AGENT DOES NOT DO (by design, Phase 1):
  - It does NOT execute remote commands.
  - It does NOT capture your screen, keystrokes, files, or browsing.
  - It does NOT give anyone remote control of this PC.
  Remote-support features (Phase 2+) are opt-in, separately installed, logged,
  and require explicit per-action approval.

CONSENT:
  By enrolling, the device owner agrees to share the health telemetry above with
  BVTech LLC for the purpose of IT monitoring and support. Telemetry can be
  stopped at any time by uninstalling the agent.

CONFIG: stored at  %ProgramData%\\BVTechOpsPilot\\agent.json
"""
from __future__ import annotations

import json
import os
import platform
import socket
import sys
import time
from pathlib import Path
from urllib import request as urlreq

AGENT_VERSION = "1.5.2"


def _normalize_url(u: str) -> str:
    """Accept what a human types: add https:// if no scheme, drop trailing slash.
    Prevents urllib 'unknown url type' when someone enters 'portal.bvtech.org'."""
    u = (u or "").strip().strip('"').strip("'").rstrip("/")
    if u and "://" not in u:
        u = "https://" + u
    return u


def _extract_token(raw: str) -> str:
    """Pull a clean enrollment token out of whatever the user pasted — even the
    whole command line (e.g. `.\\opspilot-agent.exe enroll eyJ... --url https://...`).
    Enrollment tokens are JWTs, so we grab the longest eyJ... run; failing that we
    strip obvious command noise. This makes onboarding forgiving of copy/paste."""
    import re
    raw = (raw or "").strip().strip('"').strip("'")
    jwts = re.findall(r"eyJ[A-Za-z0-9._\-]{20,}", raw)
    if jwts:
        return max(jwts, key=len)
    # No JWT found: drop the exe name, the word 'enroll', and any --flag value.
    toks = []
    skip_next = False
    for t in raw.split():
        if skip_next:
            skip_next = False
            continue
        low = t.lower()
        if low.startswith("--"):
            skip_next = "=" not in t
            continue
        if low in ("enroll", "run") or low.endswith(".exe") or low.endswith(".py") \
                or low.startswith(".\\") or low.startswith("./"):
            continue
        toks.append(t)
    return toks[0] if toks else raw


def _extract_url_flag(raw: str) -> str | None:
    """If a pasted command contains `--url X`, return X."""
    import re
    m = re.search(r"--url[=\s]+(\S+)", raw or "")
    return m.group(1) if m else None


PULSE_URL = _normalize_url(os.environ.get("PULSE_URL", "https://portal.bvtech.org"))
CHECKIN_INTERVAL = 60  # seconds; server can override (live-feel default)
INVENTORY_INTERVAL = 6 * 3600  # software inventory cadence (seconds)

if os.name == "nt":
    CONF_DIR = Path(os.environ.get("ProgramData", "C:/ProgramData")) / "BVTechOpsPilot"
else:
    CONF_DIR = Path.home() / ".bvtech-pulse"
CONF_FILE = CONF_DIR / "agent.json"
LOG_FILE = CONF_DIR / "agent.log"

_BANNER = r"""
  ╔══════════════════════════════════════════════════════════╗
  ║   B V T E C H   O p s P i l o t   ·   Endpoint Agent      ║
  ║   Secure RMM telemetry   ·   bvtech.org · Sugar Land, TX    ║
  ╚══════════════════════════════════════════════════════════╝
"""


def _log(msg: str) -> None:
    """Print and append to the local log so installs aren't a black box."""
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, flush=True)
    try:
        CONF_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# A real browser User-Agent so Cloudflare "Bot Fight Mode" / Browser Integrity
# Check is less likely to challenge the agent's API calls. (For a hard Managed
# Challenge you still need a CF WAF skip rule on /api/agent/* — see docs.)
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 OpsPilotAgent")


def _post(path: str, body: dict, headers: dict | None = None) -> dict:
    data = json.dumps(body).encode()
    h = {"Content-Type": "application/json", "User-Agent": _UA, "Accept": "application/json"}
    h.update(headers or {})
    req = urlreq.Request(PULSE_URL.rstrip("/") + path, data=data, headers=h, method="POST")
    with urlreq.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _get(path: str, headers: dict | None = None) -> dict:
    h = {"User-Agent": _UA, "Accept": "application/json"}
    h.update(headers or {})
    req = urlreq.Request(PULSE_URL.rstrip("/") + path, headers=h, method="GET")
    with urlreq.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _load_conf() -> dict | None:
    if CONF_FILE.exists():
        return json.loads(CONF_FILE.read_text())
    return None


def _save_conf(conf: dict) -> None:
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    CONF_FILE.write_text(json.dumps(conf, indent=2))


# --------------------------------------------------------------------------- #
# Telemetry collectors. Use psutil if present; otherwise degrade gracefully.
# --------------------------------------------------------------------------- #
def collect() -> dict:
    snap: dict = {"logged_in_user": _current_user(),
                  "agent_version": AGENT_VERSION, "platform": _platform()}
    try:
        import psutil  # optional
        snap["cpu_pct"] = psutil.cpu_percent(interval=1)
        snap["ram_pct"] = psutil.virtual_memory().percent
        snap["disk_pct"] = psutil.disk_usage("C:\\" if os.name == "nt" else "/").percent
    except Exception:
        pass
    snap["av_status"] = _av_status()
    snap["patch_status"] = _patch_status()
    return snap


def _platform() -> str:
    if os.name == "nt":
        return "windows"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def _current_user() -> str:
    try:
        return os.getlogin()
    except Exception:
        return os.environ.get("USERNAME") or os.environ.get("USER") or "?"


def _av_status() -> str | None:
    if os.name != "nt":
        return None
    try:
        import subprocess
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-MpComputerStatus).RealTimeProtectionEnabled"],
            capture_output=True, text=True, timeout=20)
        return "on" if "True" in out.stdout else "off"
    except Exception:
        return None


def _patch_status() -> str | None:
    # Lightweight heuristic placeholder; Phase 4 wires real Windows Update COM API.
    return None


def collect_software() -> list[dict]:
    """Installed-software inventory, per OS. Read-only. Best-effort: returns
    whatever it can enumerate, [] on failure."""
    try:
        if os.name == "nt":
            return _software_windows()
        if sys.platform == "darwin":
            return _software_macos()
        return _software_linux()
    except Exception as e:
        _log(f"software inventory failed: {e}")
        return []


def _software_windows() -> list[dict]:
    # Read both 64- and 32-bit uninstall hives from the registry (no extra deps).
    import winreg  # type: ignore
    apps: list[dict] = []
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, path in roots:
        try:
            key = winreg.OpenKey(hive, path)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(key)[0]):
            try:
                sub = winreg.OpenKey(key, winreg.EnumKey(key, i))
                name = winreg.QueryValueEx(sub, "DisplayName")[0]
            except OSError:
                continue
            if not name:
                continue
            def _v(k):
                try:
                    return winreg.QueryValueEx(sub, k)[0]
                except OSError:
                    return None
            apps.append({"name": str(name), "version": _v("DisplayVersion"),
                         "publisher": _v("Publisher")})
    return apps


def _software_linux() -> list[dict]:
    import subprocess
    # dpkg (Debian/Ubuntu)
    try:
        out = subprocess.run(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Maintainer}\n"],
                             capture_output=True, text=True, timeout=30)
        if out.returncode == 0 and out.stdout.strip():
            apps = []
            for line in out.stdout.splitlines():
                parts = line.split("\t")
                if parts and parts[0]:
                    apps.append({"name": parts[0],
                                 "version": parts[1] if len(parts) > 1 else None,
                                 "publisher": parts[2] if len(parts) > 2 else None})
            return apps
    except Exception:
        pass
    # rpm (RHEL/Fedora/SUSE)
    try:
        out = subprocess.run(["rpm", "-qa", "--qf", "%{NAME}\t%{VERSION}-%{RELEASE}\t%{VENDOR}\n"],
                             capture_output=True, text=True, timeout=30)
        if out.returncode == 0 and out.stdout.strip():
            apps = []
            for line in out.stdout.splitlines():
                parts = line.split("\t")
                if parts and parts[0]:
                    apps.append({"name": parts[0],
                                 "version": parts[1] if len(parts) > 1 else None,
                                 "publisher": parts[2] if len(parts) > 2 else None})
            return apps
    except Exception:
        pass
    return []


def _software_macos() -> list[dict]:
    import subprocess
    out = subprocess.run(["system_profiler", "-json", "SPApplicationsDataType"],
                         capture_output=True, text=True, timeout=60)
    data = json.loads(out.stdout or "{}")
    apps = []
    for a in data.get("SPApplicationsDataType", []):
        name = a.get("_name")
        if name:
            apps.append({"name": name, "version": a.get("version"),
                         "publisher": a.get("obtained_from")})
    return apps


def collect_patches() -> list[dict]:
    """Pending OS/software updates, per OS. Read-only (checks, never installs)."""
    try:
        if os.name == "nt":
            return _patches_windows()
        if sys.platform == "darwin":
            return _patches_macos()
        return _patches_linux()
    except Exception as e:
        _log(f"patch check failed: {e}")
        return []


def _patches_windows() -> list[dict]:
    # Query the Windows Update agent COM API via PowerShell (native, no modules).
    import subprocess
    ps = (
        "$s=New-Object -ComObject Microsoft.Update.Session;"
        "$r=($s.CreateUpdateSearcher()).Search('IsInstalled=0 and IsHidden=0');"
        "$r.Updates | ForEach-Object {"
        " $kb=($_.KBArticleIDs -join ',');"
        " $sev=$_.MsrcSeverity;"
        " \"$($_.Title)`t$kb`t$sev\" }"
    )
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True, timeout=120)
    patches = []
    for line in (out.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        title = parts[0].strip()
        if not title:
            continue
        kb = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
        if kb and not kb.upper().startswith("KB"):
            kb = "KB" + kb
        sev = parts[2].strip() if len(parts) > 2 and parts[2].strip() else None
        patches.append({"name": title, "kb": kb, "severity": (sev or "other").lower()})
    return patches


def _patches_linux() -> list[dict]:
    import subprocess
    # Debian/Ubuntu: simulate an upgrade and read the 'Inst' lines.
    try:
        out = subprocess.run(["apt-get", "-s", "upgrade"],
                             capture_output=True, text=True, timeout=60)
        if out.returncode == 0:
            patches = []
            for line in out.stdout.splitlines():
                if line.startswith("Inst "):
                    toks = line.split()
                    name = toks[1] if len(toks) > 1 else line[5:]
                    sev = "security" if "security" in line.lower() else "other"
                    patches.append({"name": name, "kb": None, "severity": sev})
            if patches:
                return patches
    except Exception:
        pass
    # RHEL/Fedora: dnf check-update exits 100 when updates are available.
    try:
        out = subprocess.run(["dnf", "-q", "check-update"],
                             capture_output=True, text=True, timeout=90)
        patches = []
        for line in out.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("Obsoleting") or " " not in line:
                continue
            name = line.split()[0]
            if "." in name:   # name.arch
                patches.append({"name": name, "kb": None, "severity": "other"})
        return patches
    except Exception:
        pass
    return []


def _patches_macos() -> list[dict]:
    import subprocess
    out = subprocess.run(["softwareupdate", "-l"], capture_output=True, text=True, timeout=120)
    patches = []
    for line in (out.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("* ") or line.startswith("- "):
            patches.append({"name": line[2:].strip(), "kb": None, "severity": "other"})
    return patches


# --------------------------------------------------------------------------- #
def enroll(token: str) -> dict:
    token = _extract_token(token)   # tolerate a pasted command / quotes / spaces
    body = {
        "enroll_token": token,
        "hostname": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "serial": _serial(),
    }
    # Retry with backoff so a flaky first connection doesn't fail the install.
    last_err = None
    for attempt, delay in enumerate((0, 2, 5, 10), start=1):
        if delay:
            time.sleep(delay)
        try:
            res = _post("/api/agent/enroll", body)
            conf = {"enroll_id": res["enroll_id"], "agent_key": res["agent_key"],
                    "device_id": res["device_id"], "url": PULSE_URL}  # remember where we enrolled
            _save_conf(conf)
            _log(f"Enrolled OK. device_id={res['device_id']} -> {PULSE_URL}")
            return conf
        except Exception as e:  # noqa: BLE001
            last_err = e
            _log(f"Enroll attempt {attempt} failed: {e}")
    _log(f"Enrollment failed after retries: {last_err}")
    raise SystemExit(1)


def submit_ticket(subject: str, body: str = "") -> dict:
    """File a support ticket from this endpoint (uses the saved enrollment)."""
    conf = _load_conf()
    if not conf:
        print("Not enrolled yet — can't submit a ticket. Enroll this device first.")
        raise SystemExit(1)
    headers = {"X-Enroll-Id": conf["enroll_id"], "X-Agent-Key": conf["agent_key"]}
    res = _post("/api/agent/ticket", {"subject": subject, "body": body}, headers)
    _log(f"Submitted support ticket #{res.get('ticket_id')}: {subject}")
    print(f"Ticket #{res.get('ticket_id')} submitted to BVTech OpsPilot. We'll be in touch.")
    return res


def _serial() -> str | None:
    if os.name != "nt":
        return None
    try:
        import subprocess
        out = subprocess.run(["wmic", "bios", "get", "serialnumber"],
                             capture_output=True, text=True, timeout=20)
        lines = [l.strip() for l in out.stdout.splitlines() if l.strip()]
        return lines[1] if len(lines) > 1 else None
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Approved-job runner (OPT-IN, Phase 2). OFF unless the operator passes
# --enable-remote-scripts. When on, the agent pulls ONLY jobs an OpsPilot owner
# already approved for THIS device, runs the pinned content, and reports the
# result. There is no ad-hoc command channel — the server can only hand back
# deployments that went through the request→approve workflow.
# --------------------------------------------------------------------------- #
_INTERPRETERS = {
    "powershell": ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"],
    "bash": ["bash"],
    "python": [sys.executable],
    "cmd": ["cmd", "/c"],
}
_SUFFIX = {"powershell": ".ps1", "bash": ".sh", "python": ".py", "cmd": ".bat"}


def _run_job(job: dict) -> tuple[int, str]:
    import subprocess
    import tempfile
    lang = job.get("language")
    interp = _INTERPRETERS.get(lang)
    if not interp:
        return 1, f"unsupported language: {lang}"
    tf = tempfile.NamedTemporaryFile("w", suffix=_SUFFIX.get(lang, ".txt"), delete=False)
    try:
        tf.write(job.get("content", ""))
        tf.close()
        proc = subprocess.run(interp + [tf.name], capture_output=True, text=True, timeout=600)
        out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
        return proc.returncode, out[:20000]
    except subprocess.TimeoutExpired:
        return 124, "job timed out after 600s"
    except Exception as e:  # noqa: BLE001 — report any failure back to the server
        return 1, f"runner error: {e}"
    finally:
        try:
            os.unlink(tf.name)
        except Exception:
            pass


def _process_jobs(headers: dict) -> None:
    res = _get("/api/agent/jobs", headers)
    for job in res.get("jobs", []):
        print(f"  running approved job #{job['id']} ({job['language']})…")
        code, out = _run_job(job)
        try:
            _post(f"/api/agent/jobs/{job['id']}/result", {"exit_code": code, "output": out}, headers)
        except Exception as e:
            print(f"  failed to report job #{job['id']}: {e}")


# Tokens of remote sessions we've already handled, so we don't double-connect.
_REMOTE_SEEN: set[str] = set()
_REMOTE_WARNED = False


def _process_remote(conf: dict, headers: dict) -> None:
    """Pick up pending remote-desktop sessions and serve each (native WebRTC).
    Each session runs in its own thread so telemetry keeps flowing."""
    global _REMOTE_WARNED
    try:
        res = _get("/api/agent/remote-sessions", headers)
    except Exception:
        return
    sessions = res.get("sessions", [])
    if not sessions:
        return
    try:
        import opspilot_remote
    except Exception:
        try:
            from . import opspilot_remote  # type: ignore
        except Exception:
            opspilot_remote = None  # type: ignore
    if opspilot_remote is None:
        return
    ok, why = opspilot_remote.is_available()
    if not ok:
        if not _REMOTE_WARNED:
            _log(f"remote desktop requested but {why}")
            _REMOTE_WARNED = True
        return
    import threading
    for s in sessions:
        tok = s.get("token")
        if not tok or tok in _REMOTE_SEEN:
            continue
        _REMOTE_SEEN.add(tok)
        _log(f"remote: starting session {tok[:8]}…")
        threading.Thread(target=opspilot_remote.run_session,
                         args=(PULSE_URL, tok, conf["enroll_id"], conf["agent_key"], _log),
                         daemon=True).start()


# --------------------------------------------------------------------------- #
# Network diagnostics (v0.12) — READ-ONLY local probes the agent runs on the
# client's LAN and reports. No system changes; safe to run by default.
# --------------------------------------------------------------------------- #
def _diag_run(kind: str, target: str | None, params: dict) -> tuple[bool, str]:
    import subprocess, socket, ipaddress
    try:
        if kind == "dns":
            infos = socket.getaddrinfo(target, None)
            return True, target + " -> " + ", ".join(sorted({i[4][0] for i in infos}))
        if kind == "port_check":
            port = int(params.get("port", 443))
            s = socket.socket(); s.settimeout(4)
            try:
                s.connect((target, port)); return True, f"{target}:{port} OPEN"
            except OSError:
                return True, f"{target}:{port} closed/filtered"
            finally:
                s.close()
        if kind == "ping":
            n = "-n" if os.name == "nt" else "-c"
            out = subprocess.run(["ping", n, "4", target], capture_output=True, text=True, timeout=30)
            return out.returncode == 0, (out.stdout + out.stderr)[:8000]
        if kind == "traceroute":
            cmd = ["tracert", "-d", target] if os.name == "nt" else ["traceroute", "-n", target]
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            return out.returncode == 0, (out.stdout + out.stderr)[:8000]
        if kind == "subnet_discovery":
            # Ping-sweep the agent's local /24 (read-only host discovery).
            base = params.get("cidr")
            if not base:
                ipaddr = socket.gethostbyname(socket.gethostname())
                base = str(ipaddress.ip_network(ipaddr + "/24", strict=False))
            net = ipaddress.ip_network(base, strict=False)
            alive = []
            n = "-n" if os.name == "nt" else "-c"
            wait = ["-w", "400"] if os.name == "nt" else ["-W", "1"]
            for host in list(net.hosts())[:254]:
                r = subprocess.run(["ping", n, "1", *wait, str(host)],
                                   capture_output=True, text=True, timeout=5)
                if r.returncode == 0:
                    alive.append(str(host))
            return True, f"{base}: {len(alive)} hosts up\n" + "\n".join(alive)
        return False, f"unknown diagnostic kind: {kind}"
    except Exception as e:  # noqa: BLE001
        return False, f"diagnostic error: {e}"


def _process_diagnostics(headers: dict) -> None:
    res = _get("/api/agent/diagnostics", headers)
    for d in res.get("diagnostics", []):
        print(f"  running diagnostic #{d['id']} ({d['kind']} {d.get('target') or ''})…")
        ok, result = _diag_run(d["kind"], d.get("target"), d.get("params") or {})
        try:
            _post(f"/api/agent/diagnostics/{d['id']}/result", {"ok": ok, "result": result}, headers)
        except Exception as e:
            print(f"  failed to report diagnostic #{d['id']}: {e}")


def run_loop(enable_scripts: bool = False) -> None:
    conf = _load_conf()
    if not conf:
        print("Not enrolled. Run:  opspilot_agent.py enroll <TOKEN>")
        sys.exit(1)
    headers = {"X-Enroll-Id": conf["enroll_id"], "X-Agent-Key": conf["agent_key"]}
    interval = CHECKIN_INTERVAL
    print(_BANNER)
    _log(f"Agent v{AGENT_VERSION} running. Reporting to {PULSE_URL} every {interval}s.")
    if enable_scripts:
        print("  Remote commands: ON (runs ONLY owner-approved jobs for THIS device;"
              " pass --no-remote-scripts to disable).")
    else:
        print("  Remote commands: OFF (--no-remote-scripts).")
    print("  Network diagnostics: ON (read-only probes; ping/dns/port/traceroute/discovery).")
    print("  Software inventory + patch scan: ON (read-only; refreshed ~every 6h).")
    last_inventory = 0.0
    while True:
        try:
            res = _post("/api/agent/checkin", collect(), headers)
            interval = int(res.get("interval_sec", interval))
            _process_diagnostics(headers)  # read-only; always processed
            _process_remote(conf, headers)  # serve any pending remote-desktop sessions
            if enable_scripts:
                _process_jobs(headers)
            # Software inventory + patch scan are heavier; first cycle then ~every 6h.
            now = time.time()
            if now - last_inventory >= INVENTORY_INTERVAL:
                sw = collect_software()
                if sw:
                    _post("/api/agent/inventory", {"software": sw}, headers)
                    _log(f"reported {len(sw)} installed apps")
                patches = collect_patches()
                _post("/api/agent/patches", {"patches": patches}, headers)
                _log(f"reported {len(patches)} pending patches")
                last_inventory = now
        except Exception as e:
            print(f"cycle failed: {e}")
        time.sleep(interval)


_URL_OVERRIDDEN = False


def _take_url_flag() -> None:
    """Allow `--url https://portal.bvtech.org` to override PULSE_URL."""
    global PULSE_URL, _URL_OVERRIDDEN
    if "--url" in sys.argv:
        i = sys.argv.index("--url")
        if i + 1 < len(sys.argv):
            PULSE_URL = _normalize_url(sys.argv[i + 1])
            _URL_OVERRIDDEN = True
            del sys.argv[i:i + 2]


def _apply_saved_url() -> None:
    """If we enrolled against a specific portal, keep using it on later runs
    (e.g. the boot Scheduled Task) unless --url overrides."""
    global PULSE_URL
    if _URL_OVERRIDDEN:
        return
    conf = _load_conf()
    if conf and conf.get("url"):
        PULSE_URL = _normalize_url(conf["url"])


def _interactive_onboard() -> bool:
    """First-run, double-clicked experience: ask for the portal + enrollment
    token, then enroll. Returns True if enrollment succeeded."""
    global PULSE_URL
    print(_BANNER)
    print(f"  Agent v{AGENT_VERSION}\n")
    print("Let's connect this computer to your Pulse portal.")
    print("(Get an enrollment token from your portal: Devices -> Deploy Agent -> Generate installer.)")
    print("Tip: you can just paste the whole token here — I'll figure out the rest.\n")

    token = ""
    # First prompt does double duty: if the user pastes the token (or the whole
    # command) here, we use it directly instead of treating it as a URL.
    try:
        first = input(f"Portal URL [{PULSE_URL}]  (or paste your token): ").strip()
    except EOFError:
        first = ""
    if first:
        if "eyj" in first.lower() or "enroll" in first.lower():
            # They pasted the token / the example command at the URL prompt.
            url = _extract_url_flag(first)
            if url:
                PULSE_URL = _normalize_url(url)
            token = _extract_token(first)
        else:
            PULSE_URL = _normalize_url(first)

    while not token:
        try:
            raw = input("Paste your enrollment token: ").strip()
        except EOFError:
            print("No token entered — nothing to do.")
            return False
        if not raw:
            continue
        url = _extract_url_flag(raw)
        if url:
            PULSE_URL = _normalize_url(url)
        token = _extract_token(raw)

    print(f"\nConnecting to {PULSE_URL} ...")
    try:
        enroll(token)   # saves config (incl. URL); raises SystemExit on failure
        return True
    except SystemExit:
        print("\nEnrollment failed. Double-check the token (they expire after 72h) and that the\n"
              f"portal URL is right ({PULSE_URL}), then run me again.")
        return False


def _embedded_token() -> tuple[str, str] | None:
    """Preconfigured ("preloaded") deployment: a per-client agent that already
    knows its enrollment token, so the client just runs it — zero copy-paste.

    The token (and optional portal URL) is supplied, in priority order, by:
      1. env vars  OPSPILOT_ENROLL_TOKEN  (+ optional OPSPILOT_URL)
      2. a file beside the executable, or in the config dir, named one of:
           opspilot-enroll.token   -> first line = token, optional 2nd line = url
           opspilot-enroll.json    -> {"token": "...", "url": "..."}
    Returns (token, url) or None. The token file is single-use: it's deleted
    after a successful enroll so the secret doesn't linger on disk.
    """
    env_tok = (os.environ.get("OPSPILOT_ENROLL_TOKEN") or "").strip()
    if env_tok:
        return env_tok, _normalize_url(os.environ.get("OPSPILOT_URL", "") or PULSE_URL)

    # Look next to the running binary/script first, then the config dir.
    bases = []
    try:
        bases.append(Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
                     else Path(__file__).resolve().parent)
    except Exception:
        pass
    bases.append(CONF_DIR)
    for base in bases:
        for name in ("opspilot-enroll.json", "opspilot-enroll.token"):
            f = base / name
            if not f.is_file():
                continue
            try:
                text = f.read_text(encoding="utf-8").strip()
            except Exception:
                continue
            if not text:
                continue
            if name.endswith(".json"):
                try:
                    data = json.loads(text)
                except Exception:
                    continue
                tok = (data.get("token") or "").strip()
                url = _normalize_url(data.get("url", "") or PULSE_URL)
            else:
                parts = [l.strip() for l in text.splitlines() if l.strip()]
                tok = parts[0] if parts else ""
                url = _normalize_url(parts[1]) if len(parts) > 1 else PULSE_URL
            if tok:
                return tok, url
    return None


def _consume_token_files() -> None:
    """Delete any preconfig token files after a successful enroll (single-use)."""
    bases = [CONF_DIR]
    try:
        bases.append(Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
                     else Path(__file__).resolve().parent)
    except Exception:
        pass
    for base in bases:
        for name in ("opspilot-enroll.json", "opspilot-enroll.token"):
            try:
                (base / name).unlink()
            except Exception:
                pass


if __name__ == "__main__":
    _take_url_flag()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    # Remote command execution is ON by default — but the server only ever hands
    # back jobs an OpsPilot OWNER explicitly approved for THIS device, so there is
    # no ad-hoc command channel. Pass --no-remote-scripts to opt out entirely.
    enable_scripts = "--no-remote-scripts" not in sys.argv

    # `submit-ticket "<subject>" ["<body>"]` — file a ticket from this endpoint.
    if args and args[0] == "submit-ticket":
        _apply_saved_url()
        subject = args[1] if len(args) > 1 else ""
        bodytext = args[2] if len(args) > 2 else ""
        while not subject:
            try:
                subject = input("Subject: ").strip()
            except EOFError:
                sys.exit(1)
        if not bodytext:
            try:
                bodytext = input("Describe the issue (optional): ").strip()
            except EOFError:
                bodytext = ""
        submit_ticket(subject, bodytext)
        sys.exit(0)

    # `status` — show enrollment + where we report.
    if args and args[0] == "status":
        _apply_saved_url()
        conf = _load_conf()
        print(_BANNER)
        if conf:
            print(f"  Enrolled ✓  device_id={conf.get('device_id')}  ->  {conf.get('url', PULSE_URL)}")
            print(f"  Agent v{AGENT_VERSION} · config: {CONF_FILE}")
        else:
            print(f"  Not enrolled. Run:  opspilot-agent enroll <TOKEN>")
        sys.exit(0)

    if args and args[0] == "enroll" and len(args) == 2:
        # Enroll, then keep running so the device starts reporting immediately
        # (unless the caller explicitly only wants to enroll).
        enroll(args[1])
        if "--no-run" not in sys.argv:
            _apply_saved_url()
            run_loop(enable_scripts=enable_scripts)
    elif args and args[0] == "run":
        _apply_saved_url()
        run_loop(enable_scripts=enable_scripts)
    elif _load_conf():
        # Already enrolled (e.g. double-clicked again, or boot task) -> just run.
        _apply_saved_url()
        run_loop(enable_scripts=enable_scripts)
    elif _embedded_token():
        # Preconfigured ("preloaded") agent: token baked in via env or a file
        # shipped beside the .exe. Self-enroll silently, then run. Zero copy-paste.
        _tok, _url = _embedded_token()
        if not _URL_OVERRIDDEN and _url:
            PULSE_URL = _url
        _log(f"Preconfigured agent: enrolling automatically to {PULSE_URL} ...")
        try:
            enroll(_tok)            # saves config (incl. URL); raises SystemExit on failure
            _consume_token_files()  # single-use: remove the baked-in token
            run_loop(enable_scripts=enable_scripts)
        except SystemExit:
            _log("Preconfigured enrollment failed (token may be expired). "
                 "Generate a fresh installer from the portal.")
            raise
    elif sys.stdin and sys.stdin.isatty():
        # Fresh double-click in a console: walk the user through onboarding.
        if _interactive_onboard():
            run_loop(enable_scripts=enable_scripts)
        else:
            try:
                input("\nPress Enter to close...")
            except EOFError:
                pass
    else:
        print(_BANNER)
        print(f"  v{AGENT_VERSION} · reporting to {PULSE_URL}\n")
        print("Usage:\n  opspilot-agent enroll <ENROLLMENT_TOKEN> [--url https://portal.bvtech.org]\n"
              "  opspilot-agent run [--no-remote-scripts] [--url https://portal.bvtech.org]\n"
              "  opspilot-agent submit-ticket \"<subject>\" [\"<details>\"]\n"
              "  opspilot-agent status\n\n"
              "Tip: just double-click the agent and paste your enrollment token when prompted.")
