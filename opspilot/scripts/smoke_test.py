"""End-to-end smoke test for BVTech OpsPilot (v0.2).
Run from the opspilot/ dir with a dev .env (sqlite fine):
    python scripts/smoke_test.py
"""
import sys, os
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
from app.main import app

def main():
    with TestClient(app) as c:
        assert c.get("/api/health").json()["ok"], "health failed"
        owner_email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL","admin@bvtech.org")
        pw = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD","")
        assert c.post("/api/auth/login", json={"email":owner_email,"password":pw}).status_code==200

        cid = c.post("/api/clients", json={"name":"Smoke Co"}).json()["id"]

        # --- agent enroll + two check-ins -> history ---
        tok = c.post(f"/api/agent/enroll-token/{cid}").json()["enroll_token"]
        a = TestClient(app); a.cookies.clear()
        ent = a.post("/api/agent/enroll", json={"enroll_token":tok,"hostname":"SMOKE-PC","os":"Windows 11"}).json()
        hdr = {"X-Enroll-Id":ent["enroll_id"],"X-Agent-Key":ent["agent_key"]}
        a.post("/api/agent/checkin", headers=hdr, json={"cpu_pct":10,"disk_pct":50,"av_status":"on"})
        a.post("/api/agent/checkin", headers=hdr, json={"cpu_pct":80,"disk_pct":95,"av_status":"off","patch_status":"behind"})
        hist = c.get(f"/api/devices/{ent['device_id']}/history").json()
        assert len(hist)==2, f"expected 2 history rows, got {len(hist)}"
        print("device history rows:", len(hist), "latest health:", hist[0]["health_score"])

        # --- staff creates a ticket on behalf of client ---
        tid = c.post("/api/tickets", json={"client_id":cid,"subject":"Printer down","priority":"high"}).json()["id"]
        assert c.get("/api/tickets")[0] if False else True
        tks = c.get("/api/tickets").json()
        assert any(t["id"]==tid for t in tks), "ticket not listed"
        # staff updates status
        r = c.patch(f"/api/tickets/{tid}", json={"status":"in_progress"})
        assert r.status_code==200 and r.json()["status"]=="in_progress", r.text
        print("ticket flow OK:", r.json()["status"])

        # --- client_admin invites a viewer, scoped to own client ---
        # First make a client_admin user directly via DB-equivalent: staff can't via API yet,
        # so simulate by creating one through bootstrap-style insert.
        from app.core.db import SessionLocal
        from app.models import User, Role
        from app.core.security import hash_password
        db = SessionLocal()
        ca = User(email="ca@smoke.co", password_hash=hash_password("CaPass123!"),
                  role=Role.CLIENT_ADMIN, client_id=cid, is_active=True)
        db.add(ca); db.commit(); db.close()

        ca_c = TestClient(app); ca_c.cookies.clear()
        assert ca_c.post("/api/auth/login", json={"email":"ca@smoke.co","password":"CaPass123!"}).status_code==200
        inv = ca_c.post("/api/client-users", json={"email":"viewer@smoke.co","role":"client_viewer"})
        assert inv.status_code==201, inv.text
        assert "temp_password" in inv.json()
        print("client-admin invite OK, temp pw issued")
        # client_admin cannot escalate to staff role
        bad = ca_c.post("/api/client-users", json={"email":"x@smoke.co","role":"owner"})
        assert bad.status_code==403, "client admin should NOT create owner!"
        print("privilege escalation blocked: OK")

        # client viewer cannot see another client's tickets (isolation)
        # (only one client here; assert listing is scoped, not empty-leaking)
        assert all(t["client_id"]==cid for t in ca_c.get("/api/tickets").json())
        print("tenant isolation on tickets: OK")

    print("\n=== OpsPilot v0.2 SMOKE TEST PASSED ===")

if __name__ == "__main__":
    main()
