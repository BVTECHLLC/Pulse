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

PULSE_URL = os.environ.get("PULSE_URL", "https://opspilot.bvtech.org")
CHECKIN_INTERVAL = 300  # seconds; server can override

if os.name == "nt":
    CONF_DIR = Path(os.environ.get("ProgramData", "C:/ProgramData")) / "BVTechOpsPilot"
else:
    CONF_DIR = Path.home() / ".bvtech-pulse"
CONF_FILE = CONF_DIR / "agent.json"


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


# --------------------------------------------------------------------------- #
def enroll(token: str) -> dict:
    body = {
        "enroll_token": token,
        "hostname": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "serial": _serial(),
    }
    res = _post("/api/agent/enroll", body)
    conf = {"enroll_id": res["enroll_id"], "agent_key": res["agent_key"],
            "device_id": res["device_id"]}
    _save_conf(conf)
    print(f"Enrolled. device_id={res['device_id']}. Config saved to {CONF_FILE}")
    return conf


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


def run_loop(enable_scripts: bool = False) -> None:
    conf = _load_conf()
    if not conf:
        print("Not enrolled. Run:  opspilot_agent.py enroll <TOKEN>")
        sys.exit(1)
    headers = {"X-Enroll-Id": conf["enroll_id"], "X-Agent-Key": conf["agent_key"]}
    interval = CHECKIN_INTERVAL
    print(f"BVTech OpsPilot Agent running. Reporting to {PULSE_URL} every {interval}s.")
    if enable_scripts:
        print("=" * 64)
        print("  REMOTE SCRIPT EXECUTION IS ENABLED for this agent.")
        print("  It will run ONLY scripts an OpsPilot owner approved for THIS")
        print("  device, and report the results. Disable by restarting without")
        print("  --enable-remote-scripts.")
        print("=" * 64)
    while True:
        try:
            res = _post("/api/agent/checkin", collect(), headers)
            interval = int(res.get("interval_sec", interval))
            if enable_scripts:
                _process_jobs(headers)
        except Exception as e:
            print(f"cycle failed: {e}")
        time.sleep(interval)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "enroll" and len(sys.argv) == 3:
        enroll(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "run":
        run_loop(enable_scripts="--enable-remote-scripts" in sys.argv)
    else:
        print(__doc__)
        print("Usage:\n  opspilot_agent.py enroll <ENROLLMENT_TOKEN>\n"
              "  opspilot_agent.py run [--enable-remote-scripts]")
