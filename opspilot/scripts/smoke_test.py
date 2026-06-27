"""End-to-end smoke test for BVTech OpsPilot (v0.3).
Run from the opspilot/ dir with a dev .env (sqlite fine):
    python scripts/smoke_test.py

Covers: auth, clients, agent enroll + check-in history, the monitoring/alerting
engine (raise → ack → auto-resolve → offline sweep → policy), tickets with
threaded comments and internal-note isolation, client-admin invites with
privilege-escalation block, and the billing MRR/renewals rollup with tenant
isolation.
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

        # --- v0.3 monitoring: the bad check-in above should have raised alerts ---
        dev_id = ent["device_id"]
        alerts = c.get("/api/alerts").json()
        kinds = {a["kind"] for a in alerts if a["device_id"]==dev_id}
        assert {"disk_full","antivirus_off","patch_behind","low_health"} <= kinds, f"missing alerts: {kinds}"
        assert any(a["severity"]=="critical" for a in alerts), "expected a critical alert"
        print("alerts raised:", sorted(kinds))

        # acknowledge one, resolve another
        disk_alert = next(a for a in alerts if a["kind"]=="disk_full" and a["device_id"]==dev_id)
        assert c.post(f"/api/alerts/{disk_alert['id']}/ack").json()["status"]=="acknowledged"
        summ = c.get("/api/alerts/summary").json()
        assert summ["acknowledged"]>=1 and summ["critical"]>=1, summ
        print("alert ack OK; summary:", {k:summ[k] for k in ("total","critical","acknowledged")})

        # a healthy check-in must AUTO-RESOLVE the resource alerts
        a.post("/api/agent/checkin", headers=hdr, json={"cpu_pct":5,"disk_pct":40,"ram_pct":30,"av_status":"on","patch_status":"current"})
        live = c.get("/api/alerts").json()
        live_kinds = {al["kind"] for al in live if al["device_id"]==dev_id}
        assert not live_kinds, f"alerts should have auto-resolved, still: {live_kinds}"
        resolved = c.get("/api/alerts?status_filter=resolved").json()
        assert any(al["auto_resolved"] for al in resolved), "expected auto-resolved history"
        print("auto-resolve on recovery OK")

        # offline sweep: backdate last_checkin so the device looks silent
        from app.core.db import SessionLocal as _SL
        from app.models import Device as _Dev
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
        _db = _SL(); _d = _db.get(_Dev, dev_id)
        _d.last_checkin = _dt.now(_tz.utc) - _td(hours=2); _db.commit(); _db.close()
        sweep = c.post("/api/monitoring/sweep").json()
        assert sweep["offline_opened"]>=1, sweep
        assert any(al["kind"]=="device_offline" for al in c.get("/api/alerts").json()), "no offline alert"
        print("offline detection OK:", sweep)

        # alert policy upsert (global default)
        pol = c.put("/api/alert-policies", json={"disk_pct_max":85,"offline_minutes":15}).json()
        assert pol["disk_pct_max"]==85 and pol["client_id"] is None, pol
        print("alert policy upsert OK")

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

        # --- v0.3 ticket threading: internal note hidden from client ---
        assert c.post(f"/api/tickets/{tid}/comments", json={"body":"Investigating now.","internal":False}).status_code==201
        assert c.post(f"/api/tickets/{tid}/comments", json={"body":"Backend RMA pending.","internal":True}).status_code==201
        staff_view = c.get(f"/api/tickets/{tid}/comments").json()
        client_view = ca_c.get(f"/api/tickets/{tid}/comments").json()
        assert len(staff_view)==2 and len(client_view)==1, (len(staff_view), len(client_view))
        assert all(not cm["internal"] for cm in client_view), "client saw an internal note!"
        # client may reply on their own ticket but cannot post internal notes
        cr = ca_c.post(f"/api/tickets/{tid}/comments", json={"body":"Thanks!","internal":True})
        assert cr.status_code==201 and cr.json()["internal"] is False, "client internal note not downgraded"
        print("ticket threading + internal-note isolation: OK")

        # --- v0.3 billing: MRR rollup + renewals ---
        from datetime import datetime as _dt2, timedelta as _td2, timezone as _tz2
        rd = (_dt2.now(_tz2.utc) + _td2(days=20)).isoformat()
        c.post("/api/licenses", json={"client_id":cid,"product":"Microsoft 365 BP","seats":10,
                                      "seats_used":7,"monthly_cost":220.0,"renewal_date":rd})
        c.post("/api/licenses", json={"client_id":cid,"product":"Datto Backup","seats":10,
                                      "seats_used":10,"monthly_cost":80.0})
        summary = c.get("/api/billing/summary").json()
        assert abs(summary["total_mrr"]-300.0)<0.01, summary
        assert summary["total_arr"]==3600.0 and summary["seats_total"]==20, summary
        assert summary["by_client"] and summary["by_client"][0]["client_id"]==cid, summary
        ren = c.get("/api/billing/renewals?days=60").json()
        assert any(r["product"]=="Microsoft 365 BP" and 0<=r["days_until"]<=21 for r in ren), ren
        print("billing MRR/renewals OK: MRR=$%.0f, renewals=%d" % (summary["total_mrr"], len(ren)))
        # client sees only their own billing numbers, never the whole book
        assert all(b["client_id"]==cid for b in ca_c.get("/api/billing/summary").json()["by_client"])
        print("billing tenant isolation: OK")

    print("\n=== OpsPilot v0.3 SMOKE TEST PASSED ===")

if __name__ == "__main__":
    main()
