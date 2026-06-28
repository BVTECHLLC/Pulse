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

AGENT_VERSION = "1.1.0"
PULSE_URL = os.environ.get("PULSE_URL", "https://portal.bvtech.org")
CHECKIN_INTERVAL = 300  # seconds; server can override
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
  ║   Secure RMM telemetry   ·   bvtech.org · El Campo, TX    ║
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
def _post(path: str, body: dict, headers: dict | None = None) -> dict:
    data = json.dumps(body).encode()
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    req = urlreq.Request(PULSE_URL.rstrip("/") + path, data=data, headers=h, method="POST")
    with urlreq.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _get(path: str, headers: dict | None = None) -> dict:
    req = urlreq.Request(PULSE_URL.rstrip("/") + path, headers=headers or {}, method="GET")
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
    snap: dict = {"logged_in_user": _current_user()}
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


# --------------------------------------------------------------------------- #
def enroll(token: str) -> dict:
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
                    "device_id": res["device_id"]}
            _save_conf(conf)
            _log(f"Enrolled OK. device_id={res['device_id']} -> {PULSE_URL}")
            return conf
        except Exception as e:  # noqa: BLE001
            last_err = e
            _log(f"Enroll attempt {attempt} failed: {e}")
    _log(f"Enrollment failed after retries: {last_err}")
    raise SystemExit(1)


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
        print("=" * 64)
        print("  REMOTE SCRIPT EXECUTION IS ENABLED for this agent.")
        print("  It will run ONLY scripts an OpsPilot owner approved for THIS")
        print("  device, and report the results. Disable by restarting without")
        print("  --enable-remote-scripts.")
        print("=" * 64)
    print("  Network diagnostics: ON (read-only probes; ping/dns/port/traceroute/discovery).")
    print("  Software inventory: ON (installed apps; refreshed ~every 6h).")
    last_inventory = 0.0
    while True:
        try:
            res = _post("/api/agent/checkin", collect(), headers)
            interval = int(res.get("interval_sec", interval))
            _process_diagnostics(headers)  # read-only; always processed
            if enable_scripts:
                _process_jobs(headers)
            # Software inventory is heavier; report on first cycle then ~every 6h.
            now = time.time()
            if now - last_inventory >= INVENTORY_INTERVAL:
                sw = collect_software()
                if sw:
                    _post("/api/agent/inventory", {"software": sw}, headers)
                    _log(f"reported {len(sw)} installed apps")
                last_inventory = now
        except Exception as e:
            print(f"cycle failed: {e}")
        time.sleep(interval)


def _take_url_flag() -> None:
    """Allow `--url https://portal.bvtech.org` to override PULSE_URL."""
    global PULSE_URL
    if "--url" in sys.argv:
        i = sys.argv.index("--url")
        if i + 1 < len(sys.argv):
            PULSE_URL = sys.argv[i + 1].rstrip("/")
            del sys.argv[i:i + 2]


if __name__ == "__main__":
    _take_url_flag()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args and args[0] == "enroll" and len(args) == 2:
        enroll(args[1])
    elif args and args[0] == "run":
        run_loop(enable_scripts="--enable-remote-scripts" in sys.argv)
    else:
        print(_BANNER)
        print(f"  v{AGENT_VERSION} · reporting to {PULSE_URL}\n")
        print("Usage:\n  opspilot_agent.py enroll <ENROLLMENT_TOKEN> [--url https://portal.bvtech.org]\n"
              "  opspilot_agent.py run [--enable-remote-scripts] [--url https://portal.bvtech.org]")
