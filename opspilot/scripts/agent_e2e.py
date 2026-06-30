"""True end-to-end test of the endpoint agent against a LIVE server.

Starts the real FastAPI app under uvicorn, then drives the actual agent module
(opspilot_agent.py) over HTTP exactly as an installed agent would: enroll →
check-in → inventory. Asserts the device appears under /api/devices with
telemetry. This proves both sides work together.
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request as u
from pathlib import Path

PORT = 8099
B = f"http://127.0.0.1:{PORT}"
HERE = Path(__file__).resolve().parents[1]


def call(path, data=None, cookie=None, method=None, headers=None):
    h = {"Content-Type": "application/json"}
    if cookie:
        h["Cookie"] = cookie
    h.update(headers or {})
    req = u.Request(B + path, data=(json.dumps(data).encode() if data is not None else None),
                    headers=h, method=method or ("POST" if data is not None else "GET"))
    r = u.urlopen(req, timeout=20)
    return r, json.loads(r.read().decode() or "{}")


def wait_ready(timeout=40):
    for _ in range(timeout * 2):
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=1):
                pass
            r = u.urlopen(B + "/api/health", timeout=3)
            if json.loads(r.read().decode())["ok"]:
                return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    env = dict(os.environ)
    env.update(SECRET_KEY="e2ekey", AGENT_ENROLL_SECRET="e2eenroll", ENV="development",
               BOOTSTRAP_ADMIN_EMAIL="admin@bvtech.org", BOOTSTRAP_ADMIN_PASSWORD="Owner12345!",
               DATABASE_URL="sqlite+pysqlite:///./_agent_e2e.db", COOKIE_SECURE="false",
               NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost")
    for f in ("_agent_e2e.db",):
        Path(HERE / f).unlink(missing_ok=True)
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                            "--port", str(PORT), "--log-level", "warning"], cwd=str(HERE), env=env)
    try:
        assert wait_ready(), "server did not become ready"
        print("server ready ✓")
        r, _ = call("/api/auth/login", {"email": "admin@bvtech.org", "password": "Owner12345!"})
        cookie = r.headers.get("set-cookie").split(";")[0]
        _, cl = call("/api/clients", {"name": "E2E Client"}, cookie=cookie)
        cid = cl["id"]
        _, tok = call(f"/api/agent/enroll-token/{cid}", {}, cookie=cookie)
        token = tok["enroll_token"]
        print(f"client={cid} token minted ✓")

        # Drive the REAL agent module against the live server.
        agent_env = dict(env, PULSE_URL=B)
        # enroll only (writes config), then one run cycle then we inspect.
        en = subprocess.run([sys.executable, "agent/opspilot_agent.py", "enroll", token,
                             "--url", B, "--no-run"], cwd=str(HERE), env=agent_env,
                            capture_output=True, text=True, timeout=60)
        print("agent enroll stdout:", en.stdout.strip().splitlines()[-1] if en.stdout.strip() else en.stderr[-300:])
        assert en.returncode == 0, f"agent enroll failed: {en.stderr[-400:]}"

        # one run loop cycle (it loops forever; let it do a cycle then kill)
        run = subprocess.Popen([sys.executable, "agent/opspilot_agent.py", "run", "--url", B],
                               cwd=str(HERE), env=agent_env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True)
        time.sleep(7)
        run.terminate()
        try:
            run.wait(timeout=5)
        except Exception:
            run.kill()

        _, devs = call("/api/devices", cookie=cookie)
        assert devs, "NO DEVICE registered after enroll!"
        d = devs[0]
        assert d["last_checkin"], "device never checked in"
        assert d["online"] is True, "device should be online right after check-in"
        assert d["agent_version"], "agent_version not reported"
        assert d["platform"] in ("windows", "darwin", "linux"), d["platform"]
        _, sw = call(f"/api/devices/{d['id']}/software", cookie=cookie)
        print(f"\nDEVICE: '{d['hostname']}' id={d['id']} os={d['os']} v{d['agent_version']} "
              f"platform={d['platform']} online={d['online']} health={d['health_score']} "
              f"cpu={d['cpu_pct']} disk={d['disk_pct']}")
        print(f"software reported: {sw.get('count', 0)} apps")

        # --- push a command and confirm the agent runs it + returns output ---
        _, rc = call(f"/api/agent/devices/{d['id']}/run-command",
                     {"command": "echo pulse-rmm-live", "language": "bash"}, cookie=cookie)
        dep_id = rc["deployment_id"]
        # run one agent cycle to pick up + execute the approved job
        run2 = subprocess.Popen([sys.executable, "agent/opspilot_agent.py", "run", "--url", B],
                                cwd=str(HERE), env=agent_env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        deadline = time.time() + 25
        out_text = None
        while time.time() < deadline:
            time.sleep(2)
            _, cmds = call(f"/api/agent/devices/{d['id']}/commands", cookie=cookie)
            match = [c for c in cmds["commands"] if c["id"] == dep_id]
            if match and match[0]["status"] in ("succeeded", "failed"):
                out_text = match[0]["output"]
                break
        run2.terminate()
        try:
            run2.wait(timeout=5)
        except Exception:
            run2.kill()
        assert out_text is not None, "pushed command never completed"
        assert "pulse-rmm-live" in out_text, f"unexpected command output: {out_text!r}"
        print(f"push-command: ran on endpoint, output contained marker ✓")

        # --- submit a ticket from the endpoint ---
        st = subprocess.run([sys.executable, "agent/opspilot_agent.py", "submit-ticket",
                             "Printer offline", "HP on 2nd floor won't print", "--url", B],
                            cwd=str(HERE), env=agent_env, capture_output=True, text=True, timeout=30)
        assert st.returncode == 0, f"submit-ticket failed: {st.stderr[-300:]}"
        _, tickets = call("/api/tickets", cookie=cookie)
        assert any("Printer offline" == t["subject"] for t in tickets), "endpoint ticket not created"
        print("endpoint ticket submission: ticket created ✓")

        print("\nEND-TO-END RMM (enroll · telemetry · push-command · ticket): PASS ✅")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=5)
        except Exception:
            srv.kill()
        Path(HERE / "_agent_e2e.db").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
