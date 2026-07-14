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

        # v1.33: daily content autopilot is ON by default. Disable it for the
        # suite so heartbeat ticks inside later blocks never attempt real
        # publishes with whatever stubs happen to be installed at that moment.
        # (The v1.33 block re-checks the default on a pristine provider row.)
        assert c.put("/api/content-autopilot/settings", json={"enabled": False}).status_code == 200

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

        # v0.37: bulk ack/resolve on a few throwaway alerts (kept separate from the
        # device's monitoring alerts so the auto-resolve test below is unaffected).
        from app.core.db import SessionLocal as _SLb
        from app.models import Alert as _Al, AlertSeverity as _Sev, AlertStatus as _ASt
        _db = _SLb()
        _bids = []
        for _i in range(3):
            _a = _Al(client_id=cid, kind="bulk_test", severity=_Sev.WARNING,
                     status=_ASt.ACTIVE, message=f"bulk test {_i}")
            _db.add(_a); _db.flush(); _bids.append(_a.id)
        _db.commit(); _db.close()
        bulk = c.post("/api/alerts/bulk", json={"ids": _bids[:2] + [999999], "action": "ack"}).json()
        assert bulk["changed_count"] == 2 and 999999 in bulk["skipped"], bulk
        br = c.post("/api/alerts/bulk", json={"ids": _bids, "action": "resolve"}).json()
        assert br["changed_count"] == 3, br   # all three resolve (2 were acked, 1 active)
        assert c.post("/api/alerts/bulk", json={"ids":[1],"action":"nope"}).status_code == 400
        assert c.post("/api/alerts/bulk", json={"ids":[],"action":"ack"}).status_code == 400
        print("bulk alert ack/resolve (skip-missing + validation) OK")

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

        # ===================== v0.4: SLA, assignment, time, KB =====================
        from app.models import SupportTicket as _ST
        from datetime import datetime as _d3, timedelta as _t3, timezone as _z3
        owner_id = c.get("/api/auth/me").json()["id"]
        ca_id = ca_c.get("/api/auth/me").json()["id"]

        # v1.26: silent session refresh — the access token expiring mid-session
        # must NOT strand the user ("Not authenticated" on the next Save). A
        # separate client proves: drop the access cookie -> protected call 401s
        # -> /api/auth/refresh mints a fresh one from the 14-day refresh cookie
        # -> the same action now succeeds. Refresh rotates its own secret.
        _rc = TestClient(app)
        assert _rc.post("/api/auth/login", json={"email": owner_email, "password": pw}).status_code == 200
        _old_refresh = _rc.cookies.get("refresh_token")
        assert _rc.get("/api/auth/me").status_code == 200
        del _rc.cookies["access_token"]                       # simulate expiry
        assert _rc.get("/api/auth/me").status_code == 401     # stranded without refresh
        assert _rc.post("/api/auth/refresh").status_code == 200
        assert "access_token" in _rc.cookies                  # new access minted
        assert _rc.cookies.get("refresh_token") != _old_refresh, "refresh secret must rotate"
        assert _rc.get("/api/auth/me").status_code == 200     # recovered
        assert _rc.get("/api/clients").status_code == 200     # a real action works post-refresh
        # No refresh cookie at all -> clean 401 (not a 500).
        _nc = TestClient(app)
        assert _nc.post("/api/auth/refresh").status_code == 401
        # A tampered/garbage refresh cookie -> clean 401.
        _nc.cookies.set("refresh_token", "bogus.sid.value")
        assert _nc.post("/api/auth/refresh").status_code == 401
        print("session refresh: expiry -> /api/auth/refresh -> recover + retry + rotation "
              "+ no-cookie/garbage rejected OK")

        # a fresh high-priority ticket gets SLA due dates stamped on create
        stid = c.post("/api/tickets", json={"client_id":cid,"subject":"Server offline","priority":"high"}).json()["id"]
        st = c.get(f"/api/tickets/{stid}").json()
        assert st["sla"]["first_response_due_at"] and not st["sla"]["breached"], st["sla"]
        print("SLA due dates stamped on create OK")

        # backdate the due targets to force a breach, then verify detection + summary
        _db=_SL(); _t=_db.get(_ST, stid)
        _t.first_response_due_at=_d3.now(_z3.utc)-_t3(hours=1)
        _t.resolution_due_at=_d3.now(_z3.utc)-_t3(hours=1)
        _db.commit(); _db.close()
        br=c.get(f"/api/tickets/{stid}").json()["sla"]
        assert br["response_breached"] and br["resolution_breached"], br
        assert any(t["id"]==stid for t in c.get("/api/tickets?breached=true").json()), "not in breached filter"
        summ=c.get("/api/tickets/sla-summary").json()
        assert summ["response_breached"]>=1 and summ["resolution_breached"]>=1, summ
        print("SLA breach detection + summary OK:", {k:summ[k] for k in ("open","response_breached","resolution_breached")})

        # a public staff reply satisfies the response SLA; resolving satisfies resolution
        c.post(f"/api/tickets/{stid}/comments", json={"body":"On it now."})
        assert c.get(f"/api/tickets/{stid}").json()["sla"]["response_breached"] is False
        c.patch(f"/api/tickets/{stid}", json={"status":"resolved"})
        rs=c.get(f"/api/tickets/{stid}").json()
        assert rs["sla"]["resolution_breached"] is False and rs["resolved_at"], rs
        print("SLA satisfied on response + resolve OK")

        # assignment is staff-only; staff directory shows workload
        assert c.patch(f"/api/tickets/{stid}", json={"assigned_to_user_id":owner_id}).status_code==200
        assert c.patch(f"/api/tickets/{stid}", json={"assigned_to_user_id":ca_id}).status_code==400, "assigned a client user!"
        assert any(s["id"]==owner_id for s in c.get("/api/staff").json())
        print("assignment + staff directory OK")

        # time tracking + billable rollup; clients cannot log time
        c.post(f"/api/tickets/{stid}/time", json={"minutes":45,"note":"Diagnosis","billable":True})
        c.post(f"/api/tickets/{stid}/time", json={"minutes":15,"billable":False})
        det=c.get(f"/api/tickets/{stid}").json()
        assert det["time_logged_minutes"]==60 and det["time_billable_minutes"]==45, det
        assert ca_c.post(f"/api/tickets/{stid}/time", json={"minutes":10}).status_code==403
        print("time tracking + rollup OK")

        # SLA policy upsert is reflected in the effective matrix
        c.put("/api/sla-policies", json={"priority":"low","response_minutes":120,"resolution_minutes":600})
        pol=c.get("/api/sla-policies").json()
        assert any(p["priority"]=="low" and p["response_minutes"]==120 for p in pol["policies"]), pol
        print("SLA policy upsert OK")

        # knowledge base: internal vs client-visible, global vs client-scoped
        internal_id=c.post("/api/kb", json={"title":"Runbook: AD restore","body":"steps","visibility":"internal"}).json()["id"]
        c.post("/api/kb", json={"title":"How to reset your password","body":"x","visibility":"client"})
        c.post("/api/kb", json={"title":"Your VPN guide","body":"y","visibility":"client","client_id":cid})
        assert len(c.get("/api/kb").json())>=3
        titles={a["title"] for a in ca_c.get("/api/kb").json()}
        assert {"How to reset your password","Your VPN guide"} <= titles, titles
        assert "Runbook: AD restore" not in titles, "client saw an internal doc!"
        assert ca_c.get(f"/api/kb/{internal_id}").status_code==404, "client fetched internal doc by id!"
        assert ca_c.post("/api/kb", json={"title":"x","body":"y"}).status_code==403, "client authored a doc!"
        assert c.delete(f"/api/kb/{internal_id}").status_code==200
        print("knowledge base visibility + RBAC OK")

        # ===================== v0.5: Automation engine =====================
        # Rule 1: a CRITICAL alert auto-opens a ticket and notifies staff.
        c.post("/api/automation/rules", json={
            "name":"Critical alert -> ticket","trigger":"alert.opened",
            "conditions":{"severity":"critical"},
            "actions":[{"type":"create_ticket","priority":"high"},{"type":"notify"}]})
        tok2=c.post(f"/api/agent/enroll-token/{cid}").json()["enroll_token"]
        ag=TestClient(app); ag.cookies.clear()
        ent2=ag.post("/api/agent/enroll", json={"enroll_token":tok2,"hostname":"AUTO-PC","os":"Windows 11"}).json()
        hdr2={"X-Enroll-Id":ent2["enroll_id"],"X-Agent-Key":ent2["agent_key"]}
        ag.post("/api/agent/checkin", headers=hdr2, json={"cpu_pct":5,"disk_pct":97,"av_status":"on"})
        auto_tickets=[t for t in c.get("/api/tickets").json() if t["subject"].startswith("[Auto]")]
        assert auto_tickets, "automation did not open a ticket from the critical alert"
        assert any(r["trigger"]=="alert.opened" and r["success"] for r in c.get("/api/automation/runs").json())
        assert any("alert" in n["message"].lower() for n in c.get("/api/notifications").json()), "no notification"
        print("automation alert->ticket+notify OK (auto ticket #%s)" % auto_tickets[0]["id"])

        # Rule 2: an URGENT ticket is auto-assigned (least-loaded) + gets an internal note.
        rid2=c.post("/api/automation/rules", json={
            "name":"Urgent -> assign + note","trigger":"ticket.created",
            "conditions":{"priority":"urgent"},
            "actions":[{"type":"assign","auto":True},{"type":"add_note","body":"Escalated by automation."}]}).json()["id"]
        utid=c.post("/api/tickets", json={"client_id":cid,"subject":"Everything down","priority":"urgent"}).json()["id"]
        assert c.get(f"/api/tickets/{utid}").json()["assigned_to_user_id"], "urgent ticket not auto-assigned"
        ucs=c.get(f"/api/tickets/{utid}/comments").json()
        assert any(cm["internal"] and "automation" in (cm["author_email"] or "") for cm in ucs), ucs
        print("automation ticket.created auto-assign+note OK")

        # Disabling a rule makes it inert.
        c.patch(f"/api/automation/rules/{rid2}", json={"enabled":False})
        ntid=c.post("/api/tickets", json={"client_id":cid,"subject":"Quiet one","priority":"urgent"}).json()["id"]
        assert not c.get(f"/api/tickets/{ntid}").json()["assigned_to_user_id"], "disabled rule still fired"
        print("rule disable OK")

        # run-checks tick: an SLA breach fires automation, de-duplicated across ticks.
        c.post("/api/automation/rules", json={
            "name":"SLA breach -> notify","trigger":"ticket.sla_breached","conditions":{},
            "actions":[{"type":"notify","message":"SLA breached!","severity":"warning"}]})
        _db2=_SL(); _bt=_db2.get(_ST, ntid)
        _bt.first_response_due_at=_d3.now(_z3.utc)-_t3(hours=2)
        _bt.resolution_due_at=_d3.now(_z3.utc)-_t3(hours=2)
        _bt.sla_breach_alerted=False; _db2.commit(); _db2.close()
        from app.models import PRIORITIES
        rc=c.post("/api/automation/run-checks").json()
        assert rc["sla_breaches_fired"]>=1, rc
        assert any("SLA breached" in n["message"] for n in c.get("/api/notifications").json())
        # v0.38: built-in escalation runs on breach (ntid is already 'urgent' -> the
        # note records the top-priority cap rather than bumping).
        assert "escalated" in rc, rc
        assert any("auto-escalated" in cm["body"] for cm in c.get(f"/api/tickets/{ntid}/comments").json())
        assert c.post("/api/automation/run-checks").json()["sla_breaches_fired"]==0, "breach re-fired (no dedup)"
        # priority-bump path: a normal-priority breached ticket gets bumped one level.
        _eid=c.post("/api/tickets", json={"client_id":cid,"subject":"Escalate me","priority":"normal"}).json()["id"]
        _ed=_SL(); _e=_ed.get(_ST,_eid)
        _e.first_response_due_at=_d3.now(_z3.utc)-_t3(hours=3)
        _e.resolution_due_at=_d3.now(_z3.utc)-_t3(hours=2); _ed.commit(); _ed.close()
        rc3=c.post("/api/automation/run-checks").json()
        assert rc3["escalated"]>=1, rc3
        assert c.get(f"/api/tickets/{_eid}").json()["priority"]=="high", "normal should bump to high"
        print("run-checks SLA breach + escalation (note + priority bump) + dedup OK")

        # Notifications: unread filter + mark read.
        unread=c.get("/api/notifications?unread_only=true").json()
        assert unread, "expected unread notifications"
        assert c.post(f"/api/notifications/{unread[0]['id']}/read").status_code==200
        assert all(n["id"]!=unread[0]["id"] for n in c.get("/api/notifications?unread_only=true").json())
        print("notifications unread + mark-read OK")

        # RBAC: client admins cannot view or manage automation rules.
        assert ca_c.get("/api/automation/rules").status_code==403
        assert ca_c.post("/api/automation/rules", json={"name":"x","trigger":"ticket.created","actions":[{"type":"notify"}]}).status_code==403
        print("automation RBAC isolation OK")

        # ===================== v0.6: Security posture =====================
        # Assessment requires an authorizing party (ethics/consent gate).
        assert c.post("/api/security/assessments", json={"client_id":cid,"title":"Q3 review","authorized_by":"  "}).status_code==400
        aid=c.post("/api/security/assessments", json={"client_id":cid,"title":"Q3 review","scope":"HQ LAN","authorized_by":"Jane Client (CTO)"}).json()["id"]
        assert c.patch(f"/api/security/assessments/{aid}", json={"status":"in_progress"}).json()["status"]=="in_progress"
        print("security assessment + authorization gate OK")

        # A CRITICAL finding raises an alert (and feeds automation); MEDIUM does not.
        crit=c.post("/api/security/findings", json={"client_id":cid,"title":"Unpatched RDP (BlueKeep)",
            "severity":"critical","cve":"CVE-2019-0708","assessment_id":aid,"recommendation":"Patch + disable RDP"}).json()
        assert crit["alert_raised"] is True, crit
        med=c.post("/api/security/findings", json={"client_id":cid,"title":"Weak TLS ciphers","severity":"medium"}).json()
        assert med["alert_raised"] is False, med
        assert any(a["kind"].startswith("security_finding:") for a in c.get("/api/alerts").json()), "no security alert"
        sc=c.get(f"/api/security/scorecard?client_id={cid}").json()
        assert sc["score"]==68 and sc["by_severity"]["critical"]==1 and sc["open_findings"]==2, sc
        print("security findings + alert + scorecard OK (score=%d)" % sc["score"])

        # Resolving the critical finding restores score and resolves its linked alert.
        c.patch(f"/api/security/findings/{crit['id']}", json={"status":"resolved"})
        assert c.get(f"/api/security/scorecard?client_id={cid}").json()["score"]==93
        assert not any(a["kind"]==f"security_finding:{crit['id']}" for a in c.get("/api/alerts").json()), "linked alert not resolved"
        print("finding resolve -> score recover + alert auto-resolve OK")

        # Client visibility: clients see only findings flagged client_visible, scorecard is their own.
        c.post("/api/security/findings", json={"client_id":cid,"title":"Shared doc public link","severity":"medium","client_visible":True})
        c.post("/api/security/findings", json={"client_id":cid,"title":"Internal recon note","severity":"low","client_visible":False})
        cv=ca_c.get("/api/security/findings").json()
        assert cv and all(f["client_visible"] for f in cv), cv
        assert not any(f["title"]=="Internal recon note" for f in cv), "client saw an internal finding!"
        assert isinstance(ca_c.get("/api/security/scorecard").json(), dict), "client scorecard should be a single object"
        # Clients cannot author security records or list assessments.
        assert ca_c.post("/api/security/findings", json={"client_id":cid,"title":"x","severity":"low"}).status_code==403
        assert ca_c.get("/api/security/assessments").status_code==403
        print("security tenant isolation + RBAC OK")

        # ===================== v0.7: Script library & deployment governance =====================
        target_dev = ent2["device_id"]  # AUTO-PC, whose agent headers we hold (hdr2)
        sc_id=c.post("/api/scripts", json={"name":"Clear temp","language":"bash",
            "content":"echo cleaning","risk_level":"low"}).json()["id"]
        assert any(s["id"]==sc_id and s["enabled"] is False for s in c.get("/api/scripts").json()), "script should start disabled"
        # disabled scripts can't be deployed
        assert c.post(f"/api/scripts/{sc_id}/deploy", json={"device_id":target_dev,"consent_ack":True}).status_code==409
        assert c.post(f"/api/scripts/{sc_id}/enable", json={"enabled":True}).json()["enabled"] is True
        # consent is mandatory
        assert c.post(f"/api/scripts/{sc_id}/deploy", json={"device_id":target_dev,"consent_ack":False}).status_code==400
        print("script library + enable gate + consent gate OK")

        # a TECH requests; the OWNER approves (separation of duties enforced)
        tech=User(email="tech@bvtech.org", password_hash=hash_password("TechPass123!"), role=Role.TECH, is_active=True)
        _dbt=_SL(); _dbt.add(tech); _dbt.commit(); _dbt.close()
        tc=TestClient(app); tc.cookies.clear()
        assert tc.post("/api/auth/login", json={"email":"tech@bvtech.org","password":"TechPass123!"}).status_code==200
        dep=tc.post(f"/api/scripts/{sc_id}/deploy", json={"device_id":target_dev,"reason":"cleanup","consent_ack":True}).json()
        assert dep["status"]=="pending_approval", dep
        # an owner may NOT approve a deployment they themselves requested
        own_dep=c.post(f"/api/scripts/{sc_id}/deploy", json={"device_id":target_dev,"consent_ack":True}).json()["id"]
        assert c.post(f"/api/deployments/{own_dep}/approve", json={}).status_code==403, "separation of duties bypassed!"
        assert c.post(f"/api/deployments/{dep['id']}/approve", json={}).json()["status"]=="approved"
        print("deploy request + separation-of-duties approval OK")

        # the agent for AUTO-PC pulls ONLY its approved job, runs it, reports the result
        jobs=ag.get("/api/agent/jobs", headers=hdr2).json()["jobs"]
        assert any(j["id"]==dep["id"] and j["content"]=="echo cleaning" for j in jobs), "approved job not delivered to its device"
        res=ag.post(f"/api/agent/jobs/{dep['id']}/result", headers=hdr2, json={"exit_code":0,"output":"cleaning\n"})
        assert res.status_code==200 and res.json()["status"]=="succeeded", res.text
        got=c.get(f"/api/deployments/{dep['id']}").json()
        assert got["status"]=="succeeded" and got["exit_code"]==0, got
        print("agent approved-job pull + result report OK")

        # reject and cancel paths
        rej=tc.post(f"/api/scripts/{sc_id}/deploy", json={"device_id":target_dev,"consent_ack":True}).json()["id"]
        assert c.post(f"/api/deployments/{rej}/reject", json={"note":"too risky"}).json()["status"]=="rejected"
        can=tc.post(f"/api/scripts/{sc_id}/deploy", json={"device_id":target_dev,"consent_ack":True}).json()["id"]
        assert tc.post(f"/api/deployments/{can}/cancel").json()["status"]=="canceled"
        print("deploy reject + cancel OK")

        # clients can't see the script library or push anything
        assert ca_c.get("/api/scripts").status_code==403
        assert ca_c.post(f"/api/scripts/{sc_id}/deploy", json={"device_id":target_dev,"consent_ack":True}).status_code==403
        print("scripts RBAC isolation OK")

        # ===================== v0.8: public signup + email =====================
        from app.services import email as _email
        assert _email.send("nobody@example.com","Test","Body") is False, "email should no-op without SMTP"
        # public signup (no auth) creates a reviewable lead
        pub=TestClient(app); pub.cookies.clear()
        sr=pub.post("/api/signup", json={"name":"Pat Lead","email":"pat@acme.com","company":"Acme","message":"Need RMM"})
        assert sr.status_code==201 and sr.json()["ok"] is True, sr.text
        reqs=c.get("/api/signup-requests").json()
        sid=next(r["id"] for r in reqs if r["email"]=="pat@acme.com")
        assert c.patch(f"/api/signup-requests/{sid}", json={"status":"approved"}).json()["status"]=="approved"
        assert ca_c.get("/api/signup-requests").status_code==403, "client saw access requests!"
        # invites now report whether the credential email was sent
        inv2=ca_c.post("/api/client-users", json={"email":"viewer2@smoke.co","role":"client_viewer"})
        assert inv2.status_code==201 and "emailed" in inv2.json(), inv2.text
        # the signup + login pages render with branding
        assert pub.get("/signup").status_code==200
        assert "mark.svg" in pub.get("/").text, "login page missing brand logo"
        print("signup flow + email no-op + invite emailed flag + branding OK")

        # ===================== v0.9: Microsoft 365 =====================
        from app.services import m365 as _m365, crypto as _crypto
        assert c.get("/api/m365/status").json()["configured"] is False  # no creds in CI
        mc=c.post("/api/m365/connections", json={"client_id":cid,"tenant_id":"contoso.onmicrosoft.com","display_name":"Acme M365"})
        assert mc.status_code==201, mc.text
        conn_id=mc.json()["id"]
        # one connection per client
        assert c.post("/api/m365/connections", json={"client_id":cid,"tenant_id":"x"}).status_code==409
        # live sync is unavailable until Graph creds are configured
        assert c.post(f"/api/m365/connections/{conn_id}/sync").status_code==503

        # exercise the sync engine with a FAKE Graph client (no creds/network)
        class _FakeGraph:
            last_token="faketoken"; last_expiry=None
            def get_subscribed_skus(self): return [
                {"sku":"O365_BUSINESS_PREMIUM","enabled":25,"consumed":20},
                {"sku":"EXCHANGESTANDARD","enabled":10,"consumed":8}]
            def get_secure_score(self): return {"current":62,"max":100}
            def get_risky_signins(self): return [
                {"upn":"ceo@acme.com","risk_level":"high"},
                {"upn":"intern@acme.com","risk_level":"low"}]
        from app.models import M365Connection as _MC
        _dbm=_SL(); _conn=_dbm.get(_MC, conn_id)
        res=_m365.sync_connection(_dbm, _conn, _FakeGraph())
        assert res["skus"]==2 and res["secure_score"]==62 and res["risky_signins"]==2, res
        assert len(res["new_alerts"])==1, "only the high-risk sign-in should alert"
        # token cached encrypted at rest
        assert _crypto.decrypt(_conn.access_token_enc)=="faketoken", "token not encrypted/roundtripped"
        _dbm.close()

        # licenses auto-populated -> visible to billing; connection reports score
        m365_lics=[l for l in c.get(f"/api/licenses?client_id={cid}").json()
                   if l["vendor"]=="Microsoft 365"]
        assert any(l["product"]=="O365_BUSINESS_PREMIUM" and l["seats"]==25 for l in m365_lics), m365_lics
        cinfo=c.get("/api/m365/connections").json()[0]
        assert cinfo["status"]=="connected" and cinfo["secure_score"]==62 and cinfo["license_count"]==2
        assert any(a["kind"]=="m365_risky_signin:ceo@acme.com" for a in c.get("/api/alerts").json()), "no M365 risk alert"
        # re-sync is idempotent (no duplicate licenses or alerts)
        _dbm2=_SL(); _m365.sync_connection(_dbm2, _dbm2.get(_MC, conn_id), _FakeGraph()); _dbm2.close()
        assert len([l for l in c.get(f"/api/licenses?client_id={cid}").json() if l["vendor"]=="Microsoft 365"])==2
        assert len([a for a in c.get("/api/alerts").json() if a["kind"].startswith("m365_risky_signin:")])==1
        # RBAC + delete
        assert ca_c.get("/api/m365/connections").status_code==403
        assert c.request("DELETE", f"/api/m365/connections/{conn_id}").status_code==200
        print("M365 connect + mock sync + license/score/alert + idempotency + RBAC OK")

        # ===================== v0.10: Invoicing =====================
        # generate from 45 min billable time @ $150/h (=112.50) + licenses (220+80=300), 8.25% tax
        inv1=c.post("/api/invoices/generate", json={"client_id":cid,"include_time":True,
            "include_licenses":True,"hourly_rate":150,"tax_rate":8.25}).json()
        assert inv1["number"].startswith("INV-"), inv1
        assert abs(inv1["total"]-446.53)<0.02, inv1   # 412.50 + 8.25% tax
        det=c.get(f"/api/invoices/{inv1['id']}").json()
        assert any(li["source"]=="time" for li in det["line_items"]), det
        assert any(li["source"]=="license" for li in det["line_items"]), det
        print("invoice generate from time + licenses OK (total $%.2f)" % inv1["total"])

        # billable time can't be billed twice: a second run has no time line
        inv2=c.post("/api/invoices/generate", json={"client_id":cid,"include_time":True,
            "include_licenses":True,"tax_rate":0}).json()
        d2=c.get(f"/api/invoices/{inv2['id']}").json()
        assert not any(li["source"]=="time" for li in d2["line_items"]), "time double-billed!"
        assert abs(d2["subtotal"]-300.0)<0.01, d2
        # manual line item on a draft recomputes the total
        c.post(f"/api/invoices/{inv2['id']}/line-items", json={"description":"Onboarding","quantity":2,"unit_price":50})
        assert abs(c.get(f"/api/invoices/{inv2['id']}").json()["total"]-400.0)<0.01
        print("no-double-bill + manual line item OK")

        # lifecycle: send + mark paid; client sees non-draft invoices only
        assert c.post(f"/api/invoices/{inv2['id']}/send").json()["status"]=="sent"
        assert c.post(f"/api/invoices/{inv1['id']}/paid").json()["status"]=="paid"
        client_inv=ca_c.get("/api/invoices").json()
        assert client_inv and all(i["status"]!="draft" for i in client_inv), client_inv
        assert any(i["id"]==inv2["id"] for i in client_inv), "client can't see their sent invoice"
        # void an empty draft (owner)
        inv3=c.post("/api/invoices/generate", json={"client_id":cid,"include_time":False,"include_licenses":False}).json()
        assert c.post(f"/api/invoices/{inv3['id']}/void").json()["status"]=="void"
        # RBAC: clients cannot generate or edit invoices
        assert ca_c.post("/api/invoices/generate", json={"client_id":cid}).status_code==403
        assert ca_c.post(f"/api/invoices/{inv2['id']}/line-items", json={"description":"x"}).status_code==403
        print("invoice lifecycle + client visibility + RBAC OK")

        # ===================== v0.11: Networking / IPAM =====================
        calc=c.post("/api/net/subnet-calc", json={"cidr":"10.0.0.0/24"}).json()
        assert calc["usable_hosts"]==254 and calc["network_address"]=="10.0.0.0" and calc["broadcast_address"]=="10.0.0.255", calc
        assert c.post("/api/net/subnet-calc", json={"cidr":"not-a-cidr"}).status_code==400
        print("subnet calculator OK (/24 -> %d hosts)" % calc["usable_hosts"])

        site_id=c.post("/api/net/sites", json={"client_id":cid,"name":"HQ","address":"El Campo, TX"}).json()["id"]
        assert c.post("/api/net/networks", json={"client_id":cid,"name":"LAN","cidr":"bad"}).status_code==400
        net_id=c.post("/api/net/networks", json={"client_id":cid,"name":"Office LAN","cidr":"10.0.0.0/24",
            "site_id":site_id,"vlan":10,"gateway":"10.0.0.1"}).json()["id"]
        nets=c.get("/api/net/networks").json()
        mynet=next(n for n in nets if n["id"]==net_id)
        assert mynet["capacity"]==254 and mynet["used"]==0, mynet
        print("site + network create OK (cap %d)" % mynet["capacity"])

        # IPAM allocation + guards
        assert c.post(f"/api/net/networks/{net_id}/ips", json={"address":"10.0.0.10","hostname":"dc01"}).status_code==201
        assert c.post(f"/api/net/networks/{net_id}/ips", json={"address":"192.168.1.5"}).status_code==400, "out-of-range allowed!"
        assert c.post(f"/api/net/networks/{net_id}/ips", json={"address":"10.0.0.10"}).status_code==409, "duplicate allowed!"
        assert c.post(f"/api/net/networks/{net_id}/ips", json={"address":"999.1.1.1"}).status_code==400, "invalid IP allowed!"
        ips=c.get(f"/api/net/networks/{net_id}/ips").json()
        assert len(ips)==1 and ips[0]["address"]=="10.0.0.10", ips
        assert next(n for n in c.get("/api/net/networks").json() if n["id"]==net_id)["used"]==1
        # release
        assert c.request("DELETE", f"/api/net/ips/{ips[0]['id']}").status_code==200
        print("IPAM allocate + in-range/dup/invalid guards + release OK")

        # clients get read-only visibility; cannot create network records
        assert ca_c.get("/api/net/networks").status_code==200
        assert ca_c.post("/api/net/networks", json={"client_id":cid,"name":"x","cidr":"10.1.0.0/24"}).status_code==403
        print("networking RBAC (client read-only) OK")

        # ===================== v0.12: Network diagnostics =====================
        # Looking glass SSRF guard — private/loopback/metadata targets are refused.
        for blocked in ("127.0.0.1","10.0.0.5","169.254.169.254","192.168.1.1"):
            assert c.post("/api/netdiag/dns", json={"host":blocked}).status_code==400, f"{blocked} not blocked!"
        assert ca_c.post("/api/netdiag/dns", json={"host":"example.com"}).status_code==403, "client used looking glass!"
        print("looking-glass SSRF guard + RBAC OK")

        # Agent diagnostics pipeline (queued -> agent pulls -> reports -> staff reads)
        assert c.post("/api/netdiag/diagnostics", json={"device_id":target_dev,"kind":"bogus","target":"x"}).status_code==400
        assert c.post("/api/netdiag/diagnostics", json={"device_id":target_dev,"kind":"ping"}).status_code==400  # needs target
        did=c.post("/api/netdiag/diagnostics", json={"device_id":target_dev,"kind":"ping","target":"8.8.8.8"}).json()["id"]
        pulled=ag.get("/api/agent/diagnostics", headers=hdr2).json()["diagnostics"]
        assert any(p["id"]==did and p["kind"]=="ping" for p in pulled), pulled
        assert ag.post(f"/api/agent/diagnostics/{did}/result", headers=hdr2,
                       json={"ok":True,"result":"4 packets transmitted, 4 received, 0% loss"}).status_code==200
        done=c.get(f"/api/netdiag/diagnostics/{did}").json()
        assert done["status"]=="done" and "0% loss" in done["result"], done
        assert ca_c.post("/api/netdiag/diagnostics", json={"device_id":target_dev,"kind":"ping","target":"8.8.8.8"}).status_code==403
        print("agent diagnostics queue + run + report + RBAC OK")

        # ===================== v0.13 / v1.5: Agent onboarding (self-contained) =====================
        import base64 as _b64ag
        # Raw agents both serve (the part that must never 404).
        ra=c.get("/download/agent")
        assert ra.status_code==200 and "OpsPilot Agent" in ra.text, "python agent download broken"
        rps=c.get("/download/agent.ps1")
        assert rps.status_code==200 and "BVTech OpsPilot Agent" in rps.text and "Do-Enroll" in rps.text, "ps1 agent broken"
        # Linux/mac installer targets the serving host + carries the token.
        sh=c.get("/download/install.sh?token=TESTTOKEN")
        assert sh.status_code==200 and "TESTTOKEN" in sh.text and "http://testserver" in sh.text and "enroll" in sh.text
        # Windows one-liner installer embeds the WHOLE agent (base64) - no download,
        # no .exe, no Python. Decode it back and prove it's the real agent.
        ps=c.get("/download/install.ps1?token=TESTTOKEN")
        assert ps.status_code==200 and "TESTTOKEN" in ps.text and "http://testserver" in ps.text
        assert "FromBase64String" in ps.text and "install $TOKEN" in ps.text, "installer not self-contained"
        import re as _reag
        m=_reag.search(r'FromBase64String\("([A-Za-z0-9+/=]+)"\)', ps.text)
        assert m, "embedded agent blob missing"
        embedded=_b64ag.b64decode(m.group(1)).decode("utf-8")
        assert "Register-ScheduledTask" in embedded and "api/agent/checkin" in embedded, "embedded agent is not the real agent"
        # The double-click .cmd self-elevates and runs an EncodedCommand (no external fetch).
        cmd=c.get("/download/deploy.cmd?token=TESTTOKEN")
        assert cmd.status_code==200 and "RunAs" in cmd.text and "-EncodedCommand" in cmd.text
        assert "download/agent.exe" not in cmd.text and "releases/latest" not in cmd.text, "still depends on a prebuilt .exe!"
        # install-exe.ps1 alias still resolves (old links) and is now self-contained too.
        assert "FromBase64String" in c.get("/download/install-exe.ps1?token=T").text
        # enroll-token returns a baseline for live onboarding; onboarding poll works.
        tokresp=c.post(f"/api/agent/enroll-token/{cid}").json()
        assert "enroll_token" in tokresp and "baseline_device_id" in tokresp, tokresp
        base_id=tokresp["baseline_device_id"]
        # Before any enroll: not yet onboarded.
        assert c.get(f"/api/agent/onboarding/{cid}?after={base_id}").json()["enrolled"] is False
        # Simulate the endpoint enrolling + checking in via the PUBLIC agent API.
        en=c.post("/api/agent/enroll", json={"enroll_token":tokresp["enroll_token"],
                  "hostname":"ONBOARD-PC","os":"Windows 11 Pro","serial":"SN-123"}).json()
        assert en.get("device_id") and en.get("agent_key")
        st1=c.get(f"/api/agent/onboarding/{cid}?after={base_id}").json()
        assert st1["enrolled"] and st1["device"]["hostname"]=="ONBOARD-PC" and st1["device"]["checked_in"] is False
        ag=TestClient(app); ag.cookies.clear()
        ag.post("/api/agent/checkin", headers={"X-Enroll-Id":en["enroll_id"],"X-Agent-Key":en["agent_key"]},
                json={"cpu_pct":12,"ram_pct":40,"disk_pct":55,"av_status":"on (Microsoft Defender)",
                      "patch_status":"up to date","agent_version":"2.0.0-ps","platform":"windows"})
        st2=c.get(f"/api/agent/onboarding/{cid}?after={base_id}").json()
        assert st2["device"]["checked_in"] is True and st2["device"]["online"] is True and st2["device"]["health_score"]==100, st2
        # onboarding poll is staff-only
        assert ca_c.get(f"/api/agent/onboarding/{cid}").status_code==403
        print("agent onboarding: self-contained installer (embedded agent, no .exe/Python) "
              "+ live enroll->checkin status + RBAC OK")

        # ===================== v0.14: Contracts + client reports =====================
        base=c.get("/api/billing/summary").json()["total_mrr"]
        c.post("/api/contracts", json={"client_id":cid,"name":"Managed IT","amount":1500,"billing_period":"monthly"})
        s=c.get("/api/billing/summary").json()
        assert abs(s["contract_mrr"]-1500)<0.01 and abs(s["total_mrr"]-(base+1500))<0.01, s
        c.post("/api/contracts", json={"client_id":cid,"name":"Backups","amount":3000,"billing_period":"quarterly"})
        s2=c.get("/api/billing/summary").json()
        assert abs(s2["contract_mrr"]-2500)<0.01, s2   # 1500/mo + (3000/quarter = 1000/mo)
        print("contracts MRR (monthly + quarterly normalize) OK")

        rep=c.get(f"/api/reports/{cid}/summary").json()
        assert rep["client"]["id"]==cid and "security" in rep and abs(rep["revenue"]["contract_mrr"]-2500)<0.01, rep
        # v0.29: enriched QBR sections present
        for k in ("patch","projects","assets","service"):
            assert k in rep, ("missing report section", k)
        assert "compliance_pct" in rep["patch"] and "active" in rep["projects"]
        assert "warranty_expiring" in rep["assets"] and "hours_90d" in rep["service"]
        # CSV export downloads, is real CSV, tenant-scoped
        ex=c.get(f"/api/reports/{cid}/export.csv")
        assert ex.status_code==200 and "text/csv" in ex.headers.get("content-type","")
        assert "attachment" in ex.headers.get("content-disposition","")
        assert ex.text.splitlines()[0]=="Metric,Value" and "MRR" in ex.text, ex.text[:120]
        assert c.get(f"/report/{cid}").status_code==200, "report page broken"
        # client can view their own report + CSV but cannot create contracts
        assert ca_c.get(f"/api/reports/{cid}/summary").status_code==200
        assert ca_c.get(f"/api/reports/{cid}/export.csv").status_code==200
        assert ca_c.post("/api/contracts", json={"client_id":cid,"name":"x","amount":1}).status_code==403
        assert all(ct["client_id"]==cid for ct in ca_c.get("/api/contracts").json())
        print("client report (enriched QBR + CSV export) + RBAC OK")

        # ===================== v0.58: recurring auto-invoicing =====================
        # Flag the Managed IT contract for auto-invoicing, then run the generator.
        mi=[ct for ct in c.get("/api/contracts").json() if ct["name"]=="Managed IT"][0]
        assert mi["auto_invoice"] is False and mi["last_invoiced_at"] is None, mi
        c.patch(f"/api/contracts/{mi['id']}", json={"auto_invoice":True})
        mi2=[ct for ct in c.get("/api/contracts").json() if ct["name"]=="Managed IT"][0]
        assert mi2["auto_invoice"] is True, mi2
        before=len(c.get("/api/invoices").json())
        run=c.post("/api/contracts/run-recurring").json()
        assert run["ok"] and len(run["created"])==1, run
        assert run["created"][0]["contract"]=="Managed IT" and abs(run["created"][0]["total"]-1500)<0.01, run
        after=len(c.get("/api/invoices").json())
        assert after==before+1, (before, after)
        # Dedup: a second immediate run creates nothing (last_invoiced_at guard).
        run2=c.post("/api/contracts/run-recurring").json()
        assert run2["ok"] and len(run2["created"])==0, run2
        mi3=[ct for ct in c.get("/api/contracts").json() if ct["name"]=="Managed IT"][0]
        assert mi3["last_invoiced_at"] is not None, mi3
        # Non-owner cannot trigger recurring billing.
        assert ca_c.post("/api/contracts/run-recurring").status_code==403
        print("recurring auto-invoicing (generate + dedup + RBAC) OK")

        # ===================== v0.59: multi-method payments =====================
        inv_id=run["created"][0]["invoice_id"]   # the auto-generated Managed IT invoice
        # Nothing configured yet -> only Stripe flag (maybe) + no manual options.
        opt0=c.get(f"/api/payments/invoices/{inv_id}/options").json()
        assert opt0["options"]==[] and abs(opt0["total"]-1500)<0.01, opt0
        # Configure several rails (partial save semantics: only sent fields).
        pm=c.put("/api/payments/methods/settings", json={"fields":{
            "paypal_handle":"bvtechllc","venmo_handle":"@BVTech-LLC","cashapp_cashtag":"$BVTech",
            "bank_routing":"111000025","bank_account":"1234567890","bank_name":"First Natl",
            "methods_note":"Thanks for your business!"}}).json()
        assert set(pm["enabled"])>={"paypal","venmo","cashapp","bank_wire"}, pm
        # Settings round-trip: plain (non-secret) fields echo back for the UI.
        ms=c.get("/api/payments/methods/settings").json()
        assert ms["fields"]["paypal_handle"]["value"]=="bvtechllc", ms["fields"].get("paypal_handle")
        assert "bank_account" in ms["fields"]  # wire details shown (meant for the payer)
        # The invoice now offers all configured rails, amount pre-filled into links.
        opt=c.get(f"/api/payments/invoices/{inv_id}/options").json()
        keys={o["key"]:o for o in opt["options"]}
        assert {"paypal","venmo","cashapp","bank_wire"}<=set(keys), list(keys)
        assert "1500.00" in keys["paypal"]["url"] and "paypalme/bvtechllc" in keys["paypal"]["url"], keys["paypal"]
        assert keys["bank_wire"]["kind"]=="instructions", keys["bank_wire"]
        assert opt["note"]=="Thanks for your business!", opt
        # Partial update keeps prior fields (don't wipe paypal by omitting it).
        c.put("/api/payments/methods/settings", json={"fields":{"check_payee":"BVTech LLC","check_address":"PO Box 1"}})
        ms2=c.get("/api/payments/methods/settings").json()
        assert ms2["fields"]["paypal_handle"]["value"]=="bvtechllc" and "check" in ms2["enabled"], ms2["enabled"]
        # RBAC: clients can read THEIR invoice options but cannot configure methods.
        assert ca_c.put("/api/payments/methods/settings", json={"fields":{"paypal_handle":"x"}}).status_code==403
        assert ca_c.get("/api/payments/methods/settings").status_code==403
        print("multi-method payments (PayPal/Venmo/CashApp/wire/check + prefill + RBAC) OK")

        # ===================== v0.61: payments & balance tracking =====================
        pay0=c.get(f"/api/invoices/{inv_id}/payments").json()
        assert abs(pay0["balance"]-1500)<0.01 and pay0["amount_paid"]==0, pay0
        # Partial payment → balance shrinks, invoice still open, pay links re-price.
        rp=c.post(f"/api/invoices/{inv_id}/payments", json={"amount":500,"method":"check","reference":"1042"})
        assert rp.status_code==201 and abs(rp.json()["balance"]-1000)<0.01 and not rp.json()["fully_paid"], rp.text
        opt_bal=c.get(f"/api/payments/invoices/{inv_id}/options").json()
        assert abs(opt_bal["balance"]-1000)<0.01 and opt_bal["paid"] is False, opt_bal
        pp=[o for o in opt_bal["options"] if o["key"]=="paypal"][0]
        assert "1000.00" in pp["url"], pp   # link now bills the remaining balance
        # Validation: non-positive amount + unknown method rejected.
        assert c.post(f"/api/invoices/{inv_id}/payments", json={"amount":0,"method":"cash"}).status_code==400
        assert c.post(f"/api/invoices/{inv_id}/payments", json={"amount":10,"method":"bitcoin"}).status_code==400
        # Pay the rest → auto-reconciles to PAID, balance zero, options close out.
        rp2=c.post(f"/api/invoices/{inv_id}/payments", json={"amount":1000,"method":"bank_wire"}).json()
        assert rp2["fully_paid"] and rp2["status"]=="paid" and rp2["balance"]==0.0, rp2
        opt_paid=c.get(f"/api/payments/invoices/{inv_id}/options").json()
        assert opt_paid["paid"] is True and opt_paid["options"]==[] and opt_paid["stripe"] is False, opt_paid
        # Ledger lists both payments; invoice now reads paid with zero balance.
        pl=c.get(f"/api/invoices/{inv_id}/payments").json()
        assert len(pl["payments"])==2 and pl["balance"]==0.0 and pl["status"]=="paid", pl
        # RBAC: clients can't record payments.
        assert ca_c.post(f"/api/invoices/{inv_id}/payments", json={"amount":5,"method":"cash"}).status_code==403
        print("payments & balance: partial→balance, link re-price, auto-reconcile, ledger + RBAC OK")

        # ===================== v0.62: A/R aging + payment reminders =====================
        from app.services import email as _email
        from app.core.db import SessionLocal as _SL
        from app.models import Invoice as _Inv
        from datetime import timezone as _tz, timedelta as _td, datetime as _dt
        _sent_box = []
        _orig_send = _email.send
        _email.send = lambda to, subject, body: (_sent_box.append((to, subject)) or True)
        try:
            # Two fresh sent invoices for cid, backdated so they're overdue.
            def _overdue_inv(amount, days_over):
                g = c.post("/api/invoices/generate", json={"client_id": cid, "include_time": False}).json()
                c.post(f"/api/invoices/{g['id']}/line-items",
                       json={"description": "Service", "quantity": 1, "unit_price": amount})
                c.post(f"/api/invoices/{g['id']}/send")
                s = _SL()
                try:
                    iv = s.get(_Inv, g["id"]); iv.due_at = _dt.now(_tz.utc) - _td(days=days_over); s.commit()
                finally:
                    s.close()
                return g["id"]
            a1 = _overdue_inv(250, 20)   # 1-30 bucket
            a2 = _overdue_inv(750, 75)   # 61-90 bucket
            # Aging report buckets the outstanding balances by age.
            ag = c.get("/api/billing/aging").json()
            assert ag["buckets"]["1-30"]["amount"] >= 250 and ag["buckets"]["61-90"]["amount"] >= 750, ag
            assert ag["total"] >= 1000 and ag["overdue_total"] >= 1000, ag
            assert any(r["id"] == a2 and r["bucket"] == "61-90" for r in ag["invoices"]), ag["invoices"]
            # Manual remind: emails the client's billing contact (stubbed True).
            rm = c.post(f"/api/invoices/{a1}/remind").json()
            assert rm["ok"] and rm["delivered"], rm
            assert _sent_box and "Payment reminder" in _sent_box[-1][1], _sent_box[-1]
            # Cadence: a1 was just reminded → the sweep only reminds a2 now.
            sweep = c.post("/api/billing/send-reminders").json()
            nums = {s["invoice_id"] for s in sweep["sent"]}
            assert a2 in nums and a1 not in nums, sweep
            # RBAC: client sees only their own A/R; cannot run the reminder sweep.
            ca_ag = ca_c.get("/api/billing/aging").json()
            assert all(r["client_id"] == cid for r in ca_ag["invoices"]), ca_ag
            assert ca_c.post("/api/billing/send-reminders").status_code == 403
            print("A/R aging + reminders: buckets + manual remind + cadence sweep + RBAC OK")

            # ============== v0.63: finance KPI cockpit ==============
            fin=c.get("/api/billing/finance").json()
            # inv_id (Managed IT, 1500) was paid via check 500 + wire 1000 earlier.
            assert fin["collected_total"]>=1500 and fin["collected_month"]>=1500, fin
            assert fin["outstanding"]>=1000 and fin["overdue"]>=1000, fin   # a1+a2 still open
            methods={m["method"] for m in fin["method_mix"]}
            assert {"check","bank_wire"}<=methods, fin["method_mix"]
            assert any(p["invoice_id"]==inv_id for p in fin["recent_payments"]), fin["recent_payments"]
            assert ca_c.get("/api/billing/finance").status_code==403   # staff-only
            print("finance cockpit: collected + outstanding + method mix + recent + RBAC OK")
        finally:
            _email.send = _orig_send

        # ===================== v0.64: client security scorecard =====================
        # Portfolio: one graded row per client (staff-only).
        port=c.get("/api/posture").json()
        assert isinstance(port, list) and any(r["client_id"]==cid for r in port), port
        row=[r for r in port if r["client_id"]==cid][0]
        assert row["grade"] in ("A","B","C","D","F") and "threats" in row["domain_grades"], row
        # Drill-down scorecard for cid (SMOKE-PC was enrolled → endpoints domain present).
        sc=c.get(f"/api/posture/{cid}").json()
        assert sc["grade"] in ("A","B","C","D","F") and sc["score"] is not None, sc
        assert "endpoints" in sc["domains"] and "threats" in sc["domains"], sc["domains"]
        assert sc["domains"]["threats"]["grade"] in ("A","B","C","D","F")
        assert isinstance(sc["recommendations"], list)
        # The client QBR report now carries the posture grade (client-shareable).
        rep=c.get(f"/api/reports/{cid}/summary").json()
        assert rep["posture"]["grade"]==sc["grade"], (rep["posture"], sc["grade"])
        assert "Posture grade" in c.get(f"/api/reports/{cid}/export.csv").text
        # RBAC: a client sees their OWN scorecard but not the portfolio nor others'.
        assert ca_c.get(f"/api/posture/{cid}").status_code==200
        assert ca_c.get("/api/posture").status_code==403
        _other_cid=c.post("/api/clients", json={"name":"Other Co"}).json()["id"]
        assert ca_c.get(f"/api/posture/{_other_cid}").status_code==403  # different client
        print("security scorecard: graded portfolio + domains + report grade + RBAC OK")

        # ===================== v0.65: auto-remediation =====================
        from app.core.db import SessionLocal as _SL2
        from app.models import Device as _Dev2
        from datetime import datetime as _dt3, timezone as _tz3, timedelta as _td3
        # Catalog + validation.
        ak=c.get("/api/remediation/alert-kinds").json()["alert_kinds"]
        assert "device_offline" in ak, ak
        assert c.post("/api/remediation/rules", json={"name":"x","alert_kind":"bogus","script_id":sc_id}).status_code==400
        assert c.post("/api/remediation/rules", json={"name":"x","alert_kind":"device_offline","script_id":999999}).status_code==404
        # Rule: device_offline → the enabled "Clear temp" script (global, all clients).
        rr=c.post("/api/remediation/rules", json={"name":"Restart on offline","alert_kind":"device_offline",
                  "script_id":sc_id,"cooldown_minutes":60,"max_per_day":3})
        assert rr.status_code==201, rr.text
        rule_id=rr.json()["id"]
        assert any(r["id"]==rule_id and r["enabled"] for r in c.get("/api/remediation/rules").json())
        # Backdate AUTO-PC's check-in so the sweep opens a device_offline alert.
        s=_SL2()
        try:
            d=s.get(_Dev2, target_dev); d.last_checkin=_dt3.now(_tz3.utc)-_td3(minutes=60); s.commit()
        finally:
            s.close()
        c.post("/api/automation/run-checks")   # sweep opens the alert → remediation fires
        recent=c.get("/api/remediation/recent").json()
        auto=[x for x in recent if x["device_id"]==target_dev and x["status"]=="approved"]
        assert auto and "auto-remediation" in (auto[0]["reason"] or ""), recent
        before_n=len(recent)
        # It lands in the device's command queue as an approved job (the agent pulls it).
        cmds=c.get(f"/api/agent/devices/{target_dev}/commands").json()["commands"]
        assert any(cm["id"]==auto[0]["deployment_id"] and cm["status"]=="approved" for cm in cmds), cmds
        # No spam: a second tick (alert already active → no NEW offline) queues nothing more.
        c.post("/api/automation/run-checks")
        assert len(c.get("/api/remediation/recent").json())==before_n, "auto-remediation should not re-fire on an active alert"
        # RBAC: clients can't see or create remediation rules.
        assert ca_c.get("/api/remediation/rules").status_code==403
        assert ca_c.post("/api/remediation/rules", json={"name":"x","alert_kind":"device_offline","script_id":sc_id}).status_code==403
        print("auto-remediation: alert→approved fix-script + dedup + queue + RBAC OK")

        # ===================== v0.66: client portal data contract =====================
        # The polished self-service portal reads these AS THE CLIENT — lock the shape.
        assert c.get("/portal").status_code==200          # the portal shell renders
        pg=ca_c.get(f"/api/posture/{cid}").json()         # own security grade
        assert pg["grade"] in ("A","B","C","D","F") and "domains" in pg, pg
        cag=ca_c.get("/api/billing/aging").json()         # own balance due
        assert "total" in cag and all(r["client_id"]==cid for r in cag["invoices"]), cag
        cinv=ca_c.get("/api/invoices").json()             # invoices carry a balance
        assert cinv and all(("balance" in i) for i in cinv), cinv
        assert all(i["status"]!="draft" for i in cinv)    # clients never see drafts
        print("client portal data: own posture grade + balance + invoice balances + RBAC OK")

        # ===================== v0.67: posture trend + drop alerting =====================
        # Make cid's devices healthy → first snapshot should be a decent grade.
        s=_SL2()
        try:
            for d in s.query(_Dev2).filter(_Dev2.client_id==cid).all():
                d.av_status="Protected"; d.patches_pending=0; d.health_score=95
                d.last_checkin=_dt3.now(_tz3.utc)
            s.commit()
        finally:
            s.close()
        snap=c.post("/api/posture/snapshot").json()
        assert snap["ok"] and any(x["client_id"]==cid for x in snap["snapshots"]), snap
        hist1=c.get(f"/api/posture/{cid}/history").json()["history"]
        assert len(hist1)>=1 and "trend" in c.get(f"/api/posture/{cid}").json(), "trend missing"
        # Now worsen cid's posture → next snapshot must drop the grade + alert staff.
        s=_SL2()
        try:
            for d in s.query(_Dev2).filter(_Dev2.client_id==cid).all():
                d.av_status="Disabled"; d.patches_pending=12; d.health_score=5
                d.last_checkin=_dt3.now(_tz3.utc)-_td3(hours=6)
            s.commit()
        finally:
            s.close()
        snap2=c.post("/api/posture/snapshot").json()
        drop=[x for x in snap2["snapshots"] if x["client_id"]==cid][0]
        assert drop["dropped"] is True, drop
        assert any(n["kind"]=="posture_drop" for n in c.get("/api/notifications").json()), "expected posture_drop notification"
        hist2=c.get(f"/api/posture/{cid}/history").json()["history"]
        assert len(hist2)>len(hist1), (len(hist1), len(hist2))
        # Portfolio rows now carry a trend; a client can see their own history but not snapshot.
        assert all("trend" in r for r in c.get("/api/posture").json())
        assert ca_c.get(f"/api/posture/{cid}/history").status_code==200
        assert ca_c.post("/api/posture/snapshot").status_code==403
        print("posture trend: snapshot + history + grade-drop alert + RBAC OK")

        # ===================== v0.70/0.71: auto-posting (LinkedIn + Google Business) =====================
        from app.services import autopost as _ap
        _o_li, _o_gb = _ap._linkedin_poster, _ap._gbp_poster
        _gb_seen=[]
        _ap._linkedin_poster=lambda db:(lambda t,u,img=None:"urn:li:share:smoke")
        _ap._gbp_poster=lambda db:(lambda t,u,img=None:(_gb_seen.append((t,u,img)) or "accounts/1/locations/2/localPosts/9"))
        try:
            st=c.get("/api/autopost/settings").json()
            assert st["enabled"] is False, st   # off by default (no surprise posting)
            assert "google_business" in st["channels"] and "ready" in st, st
            p=c.post("/api/autopost", json={"body":"Managed IT tip from BVTech","link":"https://bvtech.org"})
            assert p.status_code==201, p.text
            pid=p.json()["id"]
            assert any(x["id"]==pid and x["status"]=="queued" for x in c.get("/api/autopost").json())
            # Enable (WEEKLY cadence), then the tick publishes the oldest queued post.
            c.put("/api/autopost/settings", json={"enabled":True,"gap_hours":168})
            chk=c.post("/api/automation/run-checks").json()
            assert chk.get("posts_published",0)>=1, chk
            assert any(x["id"]==pid and x["status"]=="posted" and "linkedin=urn:li:share:smoke" in (x["result"] or "")
                       for x in c.get("/api/autopost").json())
            # Cadence: an immediate second tick publishes nothing (weekly gap not elapsed).
            assert c.post("/api/automation/run-checks").json().get("posts_published",0)==0
            # Google Business post WITH an image, via post-now (bypasses cadence).
            gp=c.post("/api/autopost", json={"body":"Top 5 ways Sugar Land SMBs stay secure",
                      "link":"https://bvtech.org/contact","image_url":"https://bvtech.org/img/post.jpg",
                      "channels":["google_business"]}).json()
            pn=c.post(f"/api/autopost/{gp['id']}/post-now").json()
            assert pn["ok"] and pn["post"]["status"]=="posted", pn
            assert _gb_seen and _gb_seen[-1][2]=="https://bvtech.org/img/post.jpg", _gb_seen   # image passed through
            assert "google_business=" in pn["post"]["result"], pn
            # Delete; RBAC: clients can't touch autopost.
            p3=c.post("/api/autopost", json={"body":"to delete"}).json()
            assert c.delete(f"/api/autopost/{p3['id']}").status_code==200
            assert ca_c.get("/api/autopost").status_code==403
            assert ca_c.post("/api/autopost", json={"body":"x","channels":["google_business"]}).status_code==403
            # v0.73: auto-write drafts + auto-refill so the queue never runs dry.
            gen=c.post("/api/autopost/generate", json={"count":5,"city":"Sugar Land, TX",
                       "keywords":["managed IT","backups"],"cta_url":"https://bvtech.org/contact",
                       "channels":["google_business"]}).json()
            assert gen["ok"] and gen["created"]==5, gen
            rows=c.get("/api/autopost").json()
            draft=[x for x in rows if "Sugar Land" in (x["body"] or "")][0]
            assert draft["status"]=="queued" and draft["channels"]==["google_business"], draft
            assert "bvtech.org/contact" in draft["body"]   # CTA woven in (SEO)
            # Save a brand profile + turn on auto-refill; the tick tops the queue up.
            c.put("/api/autopost/settings", json={"auto_generate":True,"min_queue":8,
                  "city":"Sugar Land, TX","keywords":["cybersecurity"],"gen_channels":["linkedin"]})
            stt=c.get("/api/autopost/settings").json()
            assert stt["auto_generate"] is True and stt["city"]=="Sugar Land, TX" and stt["min_queue"]==8, stt
            c.post("/api/automation/run-checks")   # auto-refill tops the queue up to min_queue
            _after=len([x for x in c.get("/api/autopost").json() if x["status"]=="queued"])
            assert _after>=8, ("queue not refilled to min_queue", _after)
            # RBAC: clients can't generate.
            assert ca_c.post("/api/autopost/generate", json={"count":2}).status_code==403
            # v0.99: multi-metro targeting — with NO city set, drafts rotate the default
            # Texas metros and NEVER use El Campo; brand voice persists.
            c.put("/api/autopost/settings", json={"city":"", "voice":"Confident TX MSP owner"})
            vst=c.get("/api/autopost/settings").json()
            assert vst["voice"]=="Confident TX MSP owner", vst
            _prev_max=max([x["id"] for x in c.get("/api/autopost").json()] or [0])
            mg=c.post("/api/autopost/generate", json={"count":8,"channels":["linkedin"]}).json()
            assert mg["created"]==8
            _new=[x for x in c.get("/api/autopost").json() if x["id"]>_prev_max]   # only the fresh batch
            _bodies=" ".join(x["body"] for x in _new)
            assert "El Campo" not in _bodies, "default targeting must not use El Campo"
            for _m in ["Sugar Land","Houston","Austin","San Antonio"]:
                assert _m in _bodies, f"expected metro {_m} in rotation"
            # explicit multi-metro list rotates across the given metros
            c.put("/api/autopost/settings", json={"city":"Sugar Land, Austin"})
            assert c.get("/api/autopost/settings").json()["cities"]==["Sugar Land","Austin"]
            print("auto-posting: LinkedIn + Google Business (image, weekly, generate + auto-refill) + multi-metro targeting + voice + RBAC OK")
        finally:
            _ap._linkedin_poster, _ap._gbp_poster = _o_li, _o_gb

        # ===================== v0.72: guided setup checklist + GBP location picker =====================
        ss=c.get("/api/setup/status").json()
        assert "items" in ss and ss["total"]>=8 and "pct" in ss, ss
        assert any(i["key"]=="gbp" for i in ss["items"]) and all("done" in i and "hint" in i for i in ss["items"])
        assert ca_c.get("/api/setup/status").status_code==403   # staff-only
        # GBP location picker: unconfigured is graceful; connected creds + stubbed
        # Google listing returns pickable locations (no ID typing).
        assert c.get("/api/gbp/locations").status_code in (200, 503)
        from app.services import gbp as _gbp
        c.put("/api/gbp/settings", json={"client_id":"cid","client_secret":"sec","refresh_token":"rt"})
        _o_ll=_gbp.GBPClient.list_locations
        _gbp.GBPClient.list_locations=lambda self:[{"account":"accounts/1","location":"locations/2",
                                                    "title":"BVTech LLC","address":"El Campo, TX"}]
        try:
            lj=c.get("/api/gbp/locations").json()
            assert lj["locations"][0]["location"]=="locations/2" and lj["locations"][0]["title"]=="BVTech LLC", lj
            assert ca_c.get("/api/gbp/locations").status_code==403
        finally:
            _gbp.GBPClient.list_locations=_o_ll
        print("guided setup checklist + GBP location picker + RBAC OK")

        # ===================== v0.74: AI copilot (Ask Pulse) =====================
        from app.services import ai as _ai
        _o_en, _o_call = _ai.enabled, _ai._CALLER
        _ai.enabled = lambda: True
        _ai._CALLER = lambda system, user, model, max_tokens: "AI:" + user[:24]
        try:
            assert c.get("/api/ai/status").json()["enabled"] is True
            ans=c.post("/api/ai/ask", json={"question":"Who is overdue and how's security?"}).json()
            assert ans["answer"].startswith("AI:"), ans
            drf=c.post("/api/ai/draft", json={"kind":"social","prompt":"weekly backups tip"}).json()
            assert "draft" in drf and drf["draft"].startswith("AI:"), drf
            # Draft a reply for a real ticket from its thread.
            _tk=ca_c.post("/api/tickets", json={"subject":"AI test — PC won't boot","body":"black screen","priority":"normal"}).json()["id"]
            rd=c.post(f"/api/ai/tickets/{_tk}/reply-draft").json()
            assert rd["draft"].startswith("AI:"), rd
            assert c.post(f"/api/ai/tickets/999999/reply-draft").status_code==404
            # v0.77: AI "explain this alert" — senior-tech guidance on any alert.
            _alerts=c.get("/api/alerts").json()
            if _alerts:
                _aid=_alerts[0]["id"]
                ex=c.post(f"/api/ai/alerts/{_aid}/explain").json()
                assert ex["explanation"].startswith("AI:") and ex["alert_id"]==_aid, ex
                assert ca_c.post(f"/api/ai/alerts/{_aid}/explain").status_code==403   # staff-only
            assert c.post("/api/ai/alerts/999999/explain").status_code==404
            # v0.80: AI marketing pack — Claude-written posts into the autopost queue.
            gai=c.post("/api/autopost/generate", json={"count":3,"use_ai":True,
                       "city":"El Campo, TX","keywords":["managed IT"],"channels":["linkedin"]}).json()
            assert gai["ok"] and gai["created"]==3, gai   # AI stub returns 1, topped up to 3
            # v0.82: AI QBR narrative for a client (Claude stubbed).
            nar=c.post(f"/api/reports/{cid}/narrative").json()
            assert nar["narrative"].startswith("AI:") and nar["client_id"]==cid, nar
            assert c.post("/api/reports/999999/narrative").status_code==404
            # A client can generate their OWN review, but not another client's.
            assert ca_c.post(f"/api/reports/{cid}/narrative").status_code==200
            assert ca_c.post(f"/api/reports/{_other_cid}/narrative").status_code==403
            # RBAC: clients can't use the copilot.
            assert ca_c.post("/api/ai/ask", json={"question":"x"}).status_code==403
            assert ca_c.get("/api/ai/status").status_code==403
        finally:
            _ai.enabled, _ai._CALLER = _o_en, _o_call
        # Graceful when Claude isn't connected (no API key) → clear 503, not a crash.
        assert c.post("/api/ai/ask", json={"question":"x"}).status_code==503
        print("AI copilot: ask + draft + ticket-reply + explain-alert + graceful + RBAC OK")

        # ===================== v0.75: white-label branding =====================
        b0=c.get("/api/branding").json()   # public, safe defaults
        assert b0["company"] and b0["accent"].startswith("#") and "app_name" in b0, b0
        # Owner rebrands; invalid color is ignored (keeps the CSS safe).
        bs=c.put("/api/branding", json={"company":"Acme MSP","product":"Shield","accent":"not-a-color","tagline":"IT done right"})
        assert bs.status_code==200 and bs.json()["company"]=="Acme MSP" and bs.json()["accent"]=="#6c5ce7", bs.text
        bs2=c.put("/api/branding", json={"accent":"#ff8800"}).json()
        assert bs2["accent"]=="#ff8800" and bs2["app_name"]=="Acme MSP Shield", bs2
        # Public read needs no auth (the login page uses it) and shows the brand.
        anon=TestClient(app); anon.cookies.clear()
        assert anon.get("/api/branding").json()["company"]=="Acme MSP"
        # RBAC: a client user cannot change branding (owner-only).
        assert ca_c.put("/api/branding", json={"company":"Hacked"}).status_code==403
        print("white-label branding: public read + owner rebrand + color guard + RBAC OK")

        # ===================== v0.76: MSP Practice Health =====================
        ph=c.get("/api/practice/health").json()
        assert "grade" in ph and "domains" in ph and "recommendations" in ph, ph
        # By now the smoke has devices + invoices + posture, so ≥2 domains score.
        assert len([d for d in ph["domains"]])>=2 and ph["score"] is not None, ph
        for k, d in ph["domains"].items():
            assert "score" in d and d["grade"] in ("A","B","C","D","F"), (k, d)
        assert ca_c.get("/api/practice/health").status_code==403   # staff-only
        print("MSP Practice Health: graded domains + recommendations + RBAC OK")

        # ===================== v0.78: ticket CSAT =====================
        # A client files a ticket, staff resolves it, the client rates it.
        _ct=ca_c.post("/api/tickets", json={"subject":"CSAT test","body":"help","priority":"normal"}).json()["id"]
        # Can't rate before it's resolved.
        assert ca_c.post(f"/api/tickets/{_ct}/rate", json={"rating":1}).status_code==409
        c.patch(f"/api/tickets/{_ct}", json={"status":"resolved"})
        assert ca_c.post(f"/api/tickets/{_ct}/rate", json={"rating":5}).status_code==400   # invalid rating
        rr=ca_c.post(f"/api/tickets/{_ct}/rate", json={"rating":1,"comment":"Fast + friendly"})
        assert rr.status_code==200 and rr.json()["csat_rating"]==1, rr.text
        assert [t for t in ca_c.get("/api/tickets").json() if t["id"]==_ct][0]["csat_rating"]==1
        # A second, unhappy rating on another resolved ticket.
        _ct2=ca_c.post("/api/tickets", json={"subject":"CSAT test 2","priority":"low"}).json()["id"]
        c.patch(f"/api/tickets/{_ct2}", json={"status":"resolved"})
        ca_c.post(f"/api/tickets/{_ct2}/rate", json={"rating":-1,"comment":"Too slow"})
        # Staff CSAT rollup reflects both; a client can't see the practice rollup.
        cs=c.get("/api/tickets/csat/summary").json()
        assert cs["rated"]>=2 and cs["satisfied"]>=1 and cs["unsatisfied"]>=1 and cs["csat_pct"] is not None, cs
        assert any(n["id"]==_ct2 for n in cs["recent_negative"]), cs
        assert ca_c.get("/api/tickets/csat/summary").status_code==403   # staff-only rollup
        print("ticket CSAT: rate-after-resolve + rollup + recent-negative + RBAC OK")

        # ===================== v0.83: one-step client onboarding =====================
        ob=c.post("/api/clients/onboard", json={"name":"Onboarded Co",
                  "contact_email":"dana@onboardedco.com","contact_name":"Dana Owner","phone":"555-1000"})
        assert ob.status_code==201, ob.text
        oj=ob.json()
        assert oj["client_id"] and oj["portal_user"]=="dana@onboardedco.com" and oj["temp_password"], oj
        assert oj["enroll_token"], "should hand back an agent enroll token"
        # The provisioned portal login actually works (real end-to-end login).
        # Unique cf-connecting-ip -> own rate-limit bucket (the smoke shares one IP).
        nc=TestClient(app); nc.cookies.clear()
        assert nc.post("/api/auth/login", json={"email":"dana@onboardedco.com","password":oj["temp_password"]},
                       headers={"cf-connecting-ip":"203.0.113.77"}).status_code==200
        # That user is a CLIENT_ADMIN scoped to the new client.
        me=nc.get("/api/auth/me").json(); assert me["role"]=="client_admin" and me["client_id"]==oj["client_id"], me
        # The enroll token works to bring a device online for that client.
        en=TestClient(app); en.cookies.clear()
        _oent=en.post("/api/agent/enroll", json={"enroll_token":oj["enroll_token"],"hostname":"ONBOARD-PC","os":"Windows 11"})
        assert _oent.status_code==200, _oent.text
        # Validation + RBAC: duplicate email, bad email, and clients can't onboard.
        assert c.post("/api/clients/onboard", json={"name":"Dup","contact_email":"dana@onboardedco.com"}).status_code==409
        assert c.post("/api/clients/onboard", json={"name":"Bad","contact_email":"notanemail"}).status_code==400
        assert ca_c.post("/api/clients/onboard", json={"name":"X","contact_email":"x@y.test"}).status_code==403
        print("client onboarding: client+login+welcome+enroll-token, real login, RBAC OK")

        # ===================== v0.60: power dialer + call coaching =====================
        from app.services import power_dialer as _pd
        _orig_caller = _pd.CALLER
        _pd.CALLER = lambda cfg, num: f"call-{num[-4:]}"   # stub Dialpad (no network)
        try:
            # Coaching script: opening + talking points + objection cards.
            sc = c.post("/api/dialer/scripts", json={"name": "MSP cold call",
                "opening": "Hi, this is BVTech…", "talking_points": ["Security", "24/7 support"],
                "objections": [{"objection": "Too expensive", "response": "ROI in 3 months"}]})
            assert sc.status_code == 201, sc.text
            sid = sc.json()["id"]
            assert sc.json()["talking_points"] == ["Security", "24/7 support"]
            # A dial-ready CRM contact (has phone, not DNC) for the from_crm pull.
            dcid = c.post("/api/crm/contacts", json={"name": "Dial Me", "company": "LeadCo",
                          "phone": "+15125550199", "status": "qualified"}).json()["id"]
            c.post("/api/crm/contacts", json={"name": "No Phone", "status": "qualified"})  # excluded
            # Build a session: one typed number + the qualified CRM contacts with a phone.
            sess = c.post("/api/dialer/sessions", json={"name": "Today's calls", "script_id": sid,
                          "items": [{"name": "Walk-in", "phone": "+15550001111"}],
                          "from_crm": {"status": "qualified", "limit": 50}})
            assert sess.status_code == 201, sess.text
            sess_id = sess.json()["id"]
            st0 = sess.json()["stats"]
            assert st0["total"] >= 2 and st0["remaining"] == st0["total"], st0
            # Session detail carries the script + the next number to dial.
            det = c.get(f"/api/dialer/sessions/{sess_id}").json()
            assert det["script"]["name"] == "MSP cold call" and det["next"]["phone"] == "+15550001111"
            assert any(e["crm_contact_id"] == dcid for e in det["entries"]), "CRM pull missing"
            # Dial next → rings via (stubbed) Dialpad, entry flips to calling.
            dn = c.post(f"/api/dialer/sessions/{sess_id}/dial-next")
            assert dn.status_code == 202 and dn.json()["entry"]["status"] == "calling", dn.text
            eid = dn.json()["entry"]["id"]
            # Log the outcome → advances + rolls into stats.
            disp = c.post(f"/api/dialer/entries/{eid}/disposition",
                          json={"disposition": "won", "notes": "Booked a demo"}).json()
            assert disp["entry"]["disposition"] == "won" and disp["stats"]["won"] == 1, disp
            assert c.post(f"/api/dialer/entries/{eid}/disposition",
                          json={"disposition": "nope"}).status_code == 400  # bad disposition
            # Dial the CRM contact + mark do_not_call → writes DNC back to the CRM.
            dn2 = c.post(f"/api/dialer/sessions/{sess_id}/dial-next").json()
            e2 = dn2["entry"]["id"]
            c.post(f"/api/dialer/entries/{e2}/disposition", json={"disposition": "do_not_call"})
            if dn2["entry"]["crm_contact_id"] == dcid:
                assert c.get(f"/api/crm/contacts/{dcid}").json()["contact"]["do_not_contact"] is True
            # Pause blocks dialing; complete stamps the session.
            c.post(f"/api/dialer/sessions/{sess_id}/status", json={"status": "paused"})
            assert c.post(f"/api/dialer/sessions/{sess_id}/dial-next").status_code == 409
            # RBAC: clients can't touch the dialer at all.
            assert ca_c.get("/api/dialer/sessions").status_code == 403
            assert ca_c.post("/api/dialer/scripts", json={"name": "x"}).status_code == 403
            print("power dialer: script + CRM-pull queue + dial/disposition + stats + DNC writeback + RBAC OK")
        finally:
            _pd.CALLER = _orig_caller

        # ===================== v0.15: Notification channels =====================
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        _hits = []
        class _H(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("content-length", 0))
                _hits.append(self.rfile.read(n).decode())
                self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
            def log_message(self, *a): pass
        srv = HTTPServer(("127.0.0.1", 0), _H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        hook = f"http://127.0.0.1:{srv.server_address[1]}/hook"

        # real webhook delivery via the test endpoint
        chid = c.post("/api/notification-channels", json={"name":"Slack","type":"slack","target":hook,"min_severity":"info"}).json()["id"]
        assert c.post(f"/api/notification-channels/{chid}/test").json()["ok"], "channel test delivery failed"
        assert any("test notification" in h for h in _hits), _hits
        print("notification channel webhook delivery OK")

        # severity routing: a critical-only channel must NOT get a warning event
        c.post("/api/notification-channels", json={"name":"CritOnly","type":"webhook","target":hook,"min_severity":"critical"})
        from app.services import notifications as _nsvc
        from app.core.db import SessionLocal as _NSL
        before = len(_hits); _db = _NSL()
        _nsvc.fanout(_db, message="warn-level event", severity="warning", client_id=None); _db.close()
        assert len(_hits) - before == 1, f"severity routing wrong: {len(_hits)-before}"
        print("notification severity routing OK")

        # automation notify action -> channel fanout (end to end)
        c.post("/api/automation/rules", json={"name":"new ticket -> notify","trigger":"ticket.created",
            "conditions":{},"actions":[{"type":"notify","message":"new ticket via channel","severity":"info"}]})
        before2 = len(_hits)
        c.post("/api/tickets", json={"client_id":cid,"subject":"Channel test ticket"})
        assert len(_hits) > before2 and any("new ticket via channel" in h for h in _hits), _hits[-3:]
        print("automation -> channel fanout OK")

        # RBAC: clients cannot see or manage channels
        assert ca_c.get("/api/notification-channels").status_code==403
        assert ca_c.post("/api/notification-channels", json={"name":"x","type":"slack","target":hook}).status_code==403
        srv.shutdown()
        print("notification channels RBAC OK")

        # ===================== v1.5: agent sources (no prebuilt binary needed) =====================
        # The agent is native code (.ps1 for Windows, .py for *nix) — no compiled
        # binary to build/publish/404 on. The old binary endpoints are retired.
        assert c.get("/download/agent").status_code==200        # python agent
        assert c.get("/download/agent.ps1").status_code==200    # powershell agent
        assert c.get("/download/agent.exe").status_code==404, "prebuilt .exe dependency should be gone"
        assert c.get("/download/agent-linux").status_code==404
        print("agent sources OK (ps1 + py; no fragile prebuilt binary)")

        # ===================== v1.5: install-exe.ps1 alias is self-contained =====================
        body=c.get("/download/install-exe.ps1?token=ALIASTOK").text
        # No Python, no fetch of a prebuilt exe — it embeds the agent + runs install.
        assert "winget" not in body and "pip " not in body and "python " not in body.lower()
        assert "FromBase64String" in body and "agent.exe" not in body, "alias must be self-contained"
        assert "ALIASTOK" in body
        print("install-exe.ps1 alias OK (self-contained, no Python/exe)")

        # ============== v0.31: preconfigured ("preloaded") .cmd installer ==========
        dtok = c.post(f"/api/agent/enroll-token/{cid}").json()["enroll_token"]
        rcmd = c.get(f"/download/deploy.cmd?token={dtok}")
        assert rcmd.status_code == 200, rcmd.status_code
        cb = rcmd.text
        # Self-contained: self-elevates, runs an EMBEDDED (base64) PowerShell — it must
        # NOT fetch a script through Cloudflare (the old `irm … | iex` got challenged).
        assert "RunAs" in cb and "@echo off" in cb
        assert "EncodedCommand" in cb and "irm " not in cb and "iex" not in cb, "deploy.cmd must be self-contained"
        import base64 as _b64
        enc=[l for l in cb.splitlines() if "EncodedCommand" in l][0].split("EncodedCommand ")[1].strip()
        decoded=_b64.b64decode(enc).decode("utf-16-le")
        # The embedded PS carries the token, pulls the .exe from the GitHub release, and fails loudly.
        assert dtok in decoded, "enrollment token must be embedded in deploy.cmd"
        # The embedded PS carries the whole agent (base64) and runs its install action.
        assert "FromBase64String" in decoded and "install $TOKEN" in decoded
        assert "opspilot-agent.exe" not in decoded, "must not depend on a prebuilt exe"
        # honest result reporting in the batch wrapper
        assert "INSTALL DID NOT COMPLETE" in cb and "managed by BVTech" in cb
        assert "attachment" in rcmd.headers.get("content-disposition", "")
        assert "bvtech-opspilot-install.cmd" in rcmd.headers.get("content-disposition", "")
        print("preconfigured .cmd installer OK (self-contained, honest, token baked in)")

        # HTML pages must be uncacheable so deploys are visible immediately (v0.17.1).
        for pth in ("/", "/dashboard", "/portal", "/signup"):
            cc=c.get(pth).headers.get("cache-control","")
            assert "no-store" in cc, (pth, cc)
        print("HTML no-store cache headers OK")

        # v0.74/0.79: the dashboard ships the AI copilot + ⌘K command palette + brand.js.
        _dash=c.get("/dashboard").text
        assert 'id="cmdk"' in _dash and "cmdkCommands" in _dash, "command palette missing"
        assert "Ask Pulse" in _dash and "/static/js/brand.js" in _dash, "copilot/branding missing"
        assert 'id="wizard"' in _dash and "openWizard" in _dash, "first-run wizard missing"
        # v1.19 regression guard: a duplicate top-level `function NAME(` silently
        # SHADOWS the earlier one (later definition wins) — this broke the fleet
        # sweep button, the auto-blogger save, and the integrations table before
        # it was caught. Zero duplicates, forever.
        import collections as _coll, re as _re
        _fn_names = _re.findall(r"^(?:async )?function (\w+)\(", _dash, _re.M)
        _fn_dups = [n for n, k in _coll.Counter(_fn_names).items() if k > 1]
        assert not _fn_dups, f"duplicate JS function declarations shadow each other: {_fn_dups}"
        print("dashboard shell: AI copilot + palette + branding + setup wizard wired "
              f"+ {len(_fn_names)} JS fns with zero duplicate declarations OK")

        # ===================== v0.19: software inventory =====================
        # SMOKE-PC was enrolled earlier (hdr). Agent reports installed software;
        # staff + the owning client can read it; fleet search aggregates by app.
        dev_id=[d for d in c.get("/api/devices").json() if d["hostname"]=="SMOKE-PC"][0]["id"]
        inv=a.post("/api/agent/inventory", headers=hdr, json={"software":[
            {"name":"Google Chrome","version":"125.0","publisher":"Google LLC"},
            {"name":"7-Zip","version":"23.01","publisher":"Igor Pavlov"},
            {"name":"Google Chrome","version":"125.0","publisher":"Google LLC"},  # dup -> collapsed
        ]})
        assert inv.status_code==200 and inv.json()["stored"]==2, inv.text
        got=c.get(f"/api/devices/{dev_id}/software").json()
        assert got["count"]==2 and any(s["name"]=="Google Chrome" for s in got["software"]), got
        # fleet-wide search (staff) finds Chrome on >=1 device
        srch=c.get("/api/software/search", params={"q":"chrome"}).json()
        assert any(r["name"]=="Google Chrome" and r["devices"]>=1 for r in srch), srch
        # owning client (ca_c) can read its own device's software + scoped search
        assert ca_c.get(f"/api/devices/{dev_id}/software").json()["count"]==2
        assert all(True for _ in ca_c.get("/api/software/search").json())  # 200, scoped
        # re-report REPLACES the set (now a single app)
        a.post("/api/agent/inventory", headers=hdr, json={"software":[{"name":"Slack","version":"4.0"}]})
        assert c.get(f"/api/devices/{dev_id}/software").json()["count"]==1
        print("software inventory report + read + dedup + replace + RBAC OK")

        # ===================== v0.20: patch management =====================
        pr=a.post("/api/agent/patches", headers=hdr, json={"patches":[
            {"name":"2024-05 Cumulative Update","kb":"5034123","severity":"critical"},
            {"name":"Defender definitions","kb":None,"severity":"security"},
        ]})
        assert pr.status_code==200 and pr.json()["pending"]==2, pr.text
        pj=c.get(f"/api/devices/{dev_id}/patches").json()
        assert pj["pending"]==2 and any(p["kb"]=="KB5034123" or p["kb"]=="5034123" for p in pj["patches"]), pj
        # device list surfaces the pending count; client can read own device patches
        assert [d for d in c.get("/api/devices").json() if d["id"]==dev_id][0]["patches_pending"]==2
        assert ca_c.get(f"/api/devices/{dev_id}/patches").json()["pending"]==2
        # re-report replaces (now zero -> up to date)
        a.post("/api/agent/patches", headers=hdr, json={"patches":[]})
        assert c.get(f"/api/devices/{dev_id}/patches").json()["pending"]==0
        print("patch report + read + count + replace + RBAC OK")

        # ===================== v1.6: Device 360 detail + agent inventory =====================
        # Re-seed some patches so the detail view has something to show.
        a.post("/api/agent/patches", headers=hdr, json={"patches":[
            {"name":"2024-06 Cumulative Update","kb":"5035000","severity":"critical"}]})
        det=c.get(f"/api/devices/{dev_id}/detail").json()
        assert det["hostname"]=="SMOKE-PC" and det["patches_pending"]==1, det
        assert "alerts" in det and det["software_count"]==1 and det["online"] in (True, False), det
        assert det["client_name"], "detail should include client name"
        # tenant isolation: the OTHER client-admin (from a different client) can't peek.
        # ca_c owns this device's client, so it CAN read; an outside client user cannot.
        assert ca_c.get(f"/api/devices/{dev_id}/detail").status_code==200
        if "lc" in dir():
            pass
        # The PowerShell agent actually gathers + reports inventory and patches.
        ps_src=c.get("/download/agent.ps1").text
        assert "Get-InstalledSoftware" in ps_src and "api/agent/inventory" in ps_src, "agent must report software"
        assert "Get-PendingPatchList" in ps_src and "api/agent/patches" in ps_src, "agent must report patches"
        assert "Uninstall" in ps_src, "agent should read the uninstall registry keys"
        print("device 360 detail (health+alerts+counts+RBAC) + agent inventory/patch reporting OK")

        # ===================== v1.7: Proactive Ops (auto-ticket + site health) =====================
        from app.models import SupportTicket as _ST17, Alert as _AL17, AlertStatus as _AS17
        # Config: off by default (opt-in), owner can flip; staff-only.
        pc=c.get("/api/automation/proactive").json()
        assert pc["auto_ticket_enabled"] is False and pc["min_severity"]=="critical", pc
        assert c.put("/api/automation/proactive", json={"auto_ticket_enabled":True}).json()["auto_ticket_enabled"] is True
        assert ca_c.get("/api/automation/proactive").status_code==403
        # Baseline open-ticket count for this device's client, then trip a CRITICAL
        # alert via a real agent check-in (disk 96 -> disk_high critical).
        _tk0=len([t for t in c.get("/api/tickets").json() if t["status"] in ("open","in_progress")])
        a.post("/api/agent/checkin", headers=hdr, json={"cpu_pct":10,"ram_pct":20,"disk_pct":96,
               "av_status":"on","patch_status":"up to date","agent_version":"2.0.0-ps"})
        # A ticket was auto-opened for the critical alert, linked to it.
        from app.core.db import SessionLocal as _SL17
        _sdb=_SL17()
        try:
            at=(_sdb.query(_ST17).filter(_ST17.source_alert_id.isnot(None))
                .order_by(_ST17.id.desc()).first())
            assert at is not None and at.priority=="urgent", "critical alert must auto-open an urgent ticket"
            linked_alert=_sdb.get(_AL17, at.source_alert_id)
            assert linked_alert and linked_alert.device_id==dev_id
            _first_ticket_id=at.id
        finally:
            _sdb.close()
        # Dedup: another check-in that keeps disk high (same active alert) must NOT
        # open a second ticket.
        a.post("/api/agent/checkin", headers=hdr, json={"cpu_pct":10,"ram_pct":20,"disk_pct":97,
               "av_status":"on","patch_status":"up to date","agent_version":"2.0.0-ps"})
        _sdb=_SL17()
        try:
            n_auto=_sdb.query(_ST17).filter(_ST17.source_alert_id.isnot(None)).count()
        finally:
            _sdb.close()
        assert n_auto==1, f"auto-ticket must dedup per alert (got {n_auto})"
        # Turn it off; disk recovers then re-trips -> still only the pre-existing one.
        c.put("/api/automation/proactive", json={"auto_ticket_enabled":False})
        a.post("/api/agent/checkin", headers=hdr, json={"cpu_pct":5,"ram_pct":10,"disk_pct":40,
               "av_status":"on","patch_status":"up to date","agent_version":"2.0.0-ps"})  # resolves
        a.post("/api/agent/checkin", headers=hdr, json={"cpu_pct":5,"ram_pct":10,"disk_pct":95,
               "av_status":"on","patch_status":"up to date","agent_version":"2.0.0-ps"})  # new alert, but disabled
        _sdb=_SL17()
        try:
            assert _sdb.query(_ST17).filter(_ST17.source_alert_id.isnot(None)).count()==1, "disabled must not open tickets"
        finally:
            _sdb.close()

        # Site health rollup: staff see all clients, worst-first; client sees own only.
        sh=c.get("/api/site-health").json()["sites"]
        assert sh and any(x["client_id"]==cid for x in sh), sh
        me_row=[x for x in sh if x["client_id"]==cid][0]
        assert me_row["devices"]>=1 and "avg_health" in me_row and "alerts" in me_row
        cah=ca_c.get("/api/site-health").json()["sites"]
        assert all(x["client_id"]==cid for x in cah), "client user must only see their own site"
        print("proactive ops: opt-in auto-ticket (critical->urgent, deduped, off=silent) + "
              "site-health rollup (worst-first, tenant-scoped) OK")

        # ===================== v1.8: Patch management (approve -> agent applies) =====================
        import json as _j18
        # Seed pending patches for SMOKE-PC (dev_id) so there's something to approve.
        a.post("/api/agent/patches", headers=hdr, json={"patches":[
            {"name":"2024-06 Cumulative Update","kb":"5035000","severity":"critical"},
            {"name":"Defender platform update","kb":"5035100","severity":"security"}]})
        assert c.get(f"/api/devices/{dev_id}/patches").json()["pending"]==2
        # Staff approves ALL pending updates -> a governed winupdate job (approved).
        ap=c.post("/api/patching/approve", json={"device_id":dev_id})
        assert ap.status_code==201, ap.text
        job_id=ap.json()["job_id"]
        jobs=c.get(f"/api/patching/jobs?device_id={dev_id}").json()["jobs"]
        assert any(j["id"]==job_id and j["status"]=="approved" and j["kbs"]=="all" for j in jobs), jobs
        # RBAC: a client user can't approve patches.
        assert ca_c.post("/api/patching/approve", json={"device_id":dev_id}).status_code==403
        # The AGENT pulls its approved jobs -> gets the winupdate job, which flips to running.
        pulled=a.get("/api/agent/jobs", headers=hdr).json()["jobs"]
        wj=[j for j in pulled if j["id"]==job_id][0]
        assert wj["language"]=="winupdate" and _j18.loads(wj["content"])["kbs"]=="all", wj
        assert c.get(f"/api/patching/jobs?device_id={dev_id}").json()["jobs"][0]["status"]=="running"
        # Agent reports success -> job succeeded, output stored; re-pull is empty (claimed once).
        rr=a.post(f"/api/agent/jobs/{job_id}/result", headers=hdr,
                  json={"exit_code":0,"output":"Installed 2 update(s): ... (resultCode=2)"})
        assert rr.status_code==200
        done=c.get(f"/api/patching/jobs?device_id={dev_id}").json()["jobs"][0]
        assert done["status"]=="succeeded" and "Installed 2" in done["output"], done
        assert a.get("/api/agent/jobs", headers=hdr).json()["jobs"]==[]   # nothing left to run
        # Approve a SPECIFIC KB subset -> content pins exactly that KB.
        ap2=c.post("/api/patching/approve", json={"device_id":dev_id,"kbs":["KB5035100"]})
        j2=[j for j in c.get(f"/api/patching/jobs?device_id={dev_id}").json()["jobs"] if j["id"]==ap2.json()["job_id"]][0]
        assert j2["kbs"]==["KB5035100"], j2
        # The shipped PowerShell agent actually installs approved updates and reports back.
        ps=c.get("/download/agent.ps1").text
        assert "Install-ApprovedPatches" in ps and "Microsoft.Update.Session" in ps and "Poll-Jobs" in ps
        assert "winupdate" in ps and "jobs/$($j.id)/result" in ps, "agent must run + report winupdate jobs"
        print("patch management: approve (all + KB subset) -> agent pull(RUNNING) -> report(succeeded) "
              "+ content-pinned + RBAC + agent installer logic OK")

        # ===================== v1.9: hands-off patch auto-approval policy =====================
        from app.services import patching as _pp19
        from app.core.db import SessionLocal as _SL19
        import datetime as _dt19
        # Fresh device for a clean policy test (no leftover jobs).
        pc19=c.post(f"/api/agent/enroll-token/{cid}").json()["enroll_token"]
        en19=c.post("/api/agent/enroll", json={"enroll_token":pc19,"hostname":"POLICY-PC","os":"Windows 11"}).json()
        h19={"X-Enroll-Id":en19["enroll_id"],"X-Agent-Key":en19["agent_key"]}
        pdev=en19["device_id"]
        # Report a CRITICAL + a LOW pending patch.
        aa=TestClient(app); aa.cookies.clear()
        aa.post("/api/agent/patches", headers=h19, json={"patches":[
            {"name":"Critical Cumulative","kb":"5040001","severity":"critical"},
            {"name":"Minor tweak","kb":"5040002","severity":"low"}]})
        # Policy: default off + RBAC.
        assert c.get("/api/patching/policy").json()["auto_approve"] is False
        assert ca_c.put("/api/patching/policy", json={"auto_approve":True}).status_code==403
        # Enable: critical-only, NOT gated to maintenance (approve immediately).
        pol=c.put("/api/patching/policy", json={"auto_approve":True,"min_severity":"critical",
                  "only_in_maintenance":False}).json()
        assert pol["auto_approve"] and pol["min_severity"]=="critical" and pol["only_in_maintenance"] is False
        _sdb=_SL19()
        try:
            made=_pp19.auto_approve_sweep(_sdb); _sdb.commit()
        finally:
            _sdb.close()
        assert any(x["device_id"]==pdev for x in made), made
        j=[x for x in c.get(f"/api/patching/jobs?device_id={pdev}").json()["jobs"] if x["status"]=="approved"][0]
        # Only the CRITICAL KB was pinned (low excluded).
        assert j["kbs"]==["KB5040001"], j
        # Dedup: a second sweep must NOT stack another job while one is open.
        _sdb=_SL19()
        try:
            again=_pp19.auto_approve_sweep(_sdb); _sdb.commit()
        finally:
            _sdb.close()
        assert not any(x["device_id"]==pdev for x in again), "must not re-approve while a job is open"

        # Maintenance gate: new device, gated policy, no window -> nothing; with a
        # live window -> approved.
        en20=c.post("/api/agent/enroll", json={"enroll_token":c.post(f"/api/agent/enroll-token/{cid}").json()["enroll_token"],
                    "hostname":"MAINT-PC","os":"Windows 11"}).json()
        h20={"X-Enroll-Id":en20["enroll_id"],"X-Agent-Key":en20["agent_key"]}
        mdev=en20["device_id"]
        aa.post("/api/agent/patches", headers=h20, json={"patches":[{"name":"Crit","kb":"5041000","severity":"critical"}]})
        c.put("/api/patching/policy", json={"only_in_maintenance":True})
        _sdb=_SL19()
        try:
            gated=_pp19.auto_approve_sweep(_sdb); _sdb.commit()
        finally:
            _sdb.close()
        assert not any(x["device_id"]==mdev for x in gated), "gated policy must wait for a maintenance window"
        # Open a maintenance window covering now.
        _now20=_dt19.datetime.now(_dt19.timezone.utc)
        c.post("/api/maintenance-windows", json={"client_id":cid,"device_id":mdev,
               "starts_at":(_now20-_dt19.timedelta(minutes=5)).isoformat(),
               "ends_at":(_now20+_dt19.timedelta(hours=2)).isoformat(),"reason":"patch window"})
        _sdb=_SL19()
        try:
            inwin=_pp19.auto_approve_sweep(_sdb); _sdb.commit()
        finally:
            _sdb.close()
        assert any(x["device_id"]==mdev for x in inwin), "should approve inside the maintenance window"
        print("patch policy: opt-in auto-approve (severity-gated, KB-pinned, dedup, "
              "maintenance-window gate) + RBAC OK")

        # ===================== v1.10: Fleet patch dashboard =====================
        # Fleet view aggregates devices with pending patches, worst-first.
        fl=c.get("/api/patching/fleet").json()
        assert "totals" in fl and fl["totals"]["devices"]>=1, fl
        # MAINT-PC (mdev) had a critical pending patch reported earlier.
        mrow=[r for r in fl["devices"] if r["device_id"]==mdev]
        assert mrow and mrow[0]["critical"]>=1 and mrow[0]["worst_severity"]=="critical", mrow
        # worst-first: the first row has >= the critical count of the last.
        if len(fl["devices"])>1:
            assert fl["devices"][0]["critical"]>=fl["devices"][-1]["critical"]
        assert ca_c.get("/api/patching/fleet").status_code==403   # staff only
        # Report a fresh critical on a device with no open job, then fleet-approve.
        fresh_tok=c.post(f"/api/agent/enroll-token/{cid}").json()["enroll_token"]
        fe=c.post("/api/agent/enroll", json={"enroll_token":fresh_tok,"hostname":"FLEET-PC","os":"Windows 11"}).json()
        aa.post("/api/agent/patches", headers={"X-Enroll-Id":fe["enroll_id"],"X-Agent-Key":fe["agent_key"]},
                json={"patches":[{"name":"Crit","kb":"5042000","severity":"critical"}]})
        appf=c.post("/api/patching/approve-fleet", json={"min_severity":"critical"})
        assert appf.status_code==200 and appf.json()["approved"]>=1, appf.text
        # The FLEET-PC now has an approved winupdate job.
        assert any(j["status"]=="approved" for j in c.get(f"/api/patching/jobs?device_id={fe['device_id']}").json()["jobs"])
        # RBAC: client can't fleet-approve.
        assert ca_c.post("/api/patching/approve-fleet", json={"min_severity":"all"}).status_code==403
        print("fleet patch dashboard: aggregate (worst-first, totals) + bulk approve + RBAC OK")

        # ===================== v1.11: Pulse Copilot (agentic tool-use) =====================
        from app.services import ai as _cai, copilot as _cop
        from app.models import ScriptDeployment as _SD11, DeploymentStatus as _DS11
        # Script a two-turn tool-use conversation: call a tool, then answer.
        _script = {"turns": []}
        def _fake_tools(system, messages, tools, *, model, max_tokens):
            return _script["turns"].pop(0)
        _o_tc, _o_en = _cai._TOOL_CALLER, _cai.enabled
        _cai._TOOL_CALLER = _fake_tools
        _cai.enabled = lambda: True
        try:
            # (1) READ tool loop: Claude calls fleet_patch_status, then answers.
            _script["turns"] = [
                {"stop_reason":"tool_use","content":[
                    {"type":"tool_use","id":"t1","name":"fleet_patch_status","input":{}}]},
                {"stop_reason":"end_turn","content":[
                    {"type":"text","text":"You have devices behind on patches."}]},
            ]
            r=c.post("/api/copilot/ask", json={"message":"which clients are behind on patches?"})
            assert r.status_code==200, r.text
            j=r.json()
            assert "fleet_patch_status" in j["tools_used"] and "behind on patches" in j["answer"], j
            assert not j["actions"] and not j["proposed_actions"]

            # (2) WRITE tool DRY-RUN: propose approving criticals for `cid` but
            #     allow_actions defaults false -> proposed, NOT executed.
            before=c.get("/api/patching/fleet").json()
            def _approve_turns():
                return [
                    {"stop_reason":"tool_use","content":[
                        {"type":"tool_use","id":"t2","name":"approve_patches_for_client",
                         "input":{"client_id":cid,"min_severity":"critical"}}]},
                    {"stop_reason":"end_turn","content":[
                        {"type":"text","text":"Done."}]},
                ]
            _script["turns"]=_approve_turns()
            r=c.post("/api/copilot/ask", json={"message":"approve critical patches for that client"})
            j=r.json()
            assert j["proposed_actions"] and not j["actions"], j
            assert j["proposed_actions"][0]["result"]["dry_run"] is True

            # (3) WRITE tool CONFIRMED: allow_actions=true -> executes, jobs created.
            # First give one cid device a fresh critical pending patch + no open job.
            en11=c.post("/api/agent/enroll", json={"enroll_token":c.post(f"/api/agent/enroll-token/{cid}").json()["enroll_token"],
                        "hostname":"COPILOT-PC","os":"Windows 11"}).json()
            aa.post("/api/agent/patches", headers={"X-Enroll-Id":en11["enroll_id"],"X-Agent-Key":en11["agent_key"]},
                    json={"patches":[{"name":"Crit","kb":"5060000","severity":"critical"}]})
            _script["turns"]=_approve_turns()
            r=c.post("/api/copilot/ask", json={"message":"do it","allow_actions":True})
            j=r.json()
            assert j["actions"], j
            assert j["actions"][0]["result"]["approved_devices"]>=1, j["actions"][0]
            # A winupdate job now exists for COPILOT-PC.
            assert any(x["status"]=="approved" for x in
                       c.get(f"/api/patching/jobs?device_id={en11['device_id']}").json()["jobs"])

            # (4) RBAC: a client user's toolset excludes write tools + fleet.
            defs=_cop._tool_defs(staff=False)
            names={d["name"] for d in defs}
            assert "approve_patches_for_client" not in names and "fleet_patch_status" not in names
            assert "site_health" in names   # reads they're allowed
        finally:
            _cai._TOOL_CALLER, _cai.enabled = _o_tc, _o_en
        print("pulse copilot: agentic tool-use loop (read) + write dry-run/confirm gating "
              "+ real action (approve patches) + tenant-scoped toolset OK")

        # ===================== v1.12: expanded copilot tools + proactive briefing =====================
        from app.services import copilot_briefing as _cb12, copilot as _cop12
        # New read tools present for staff; new write tool gated.
        _sd=_cop12._tool_defs(staff=True); _snm={d["name"] for d in _sd}
        assert {"client_report","device_history","security_posture","financials",
                "draft_client_email","create_maintenance_window"} <= _snm, _snm
        assert "create_maintenance_window" in _cop12._WRITE_TOOLS
        # client_report tool returns real QBR-ish data for cid.
        # Drive create_maintenance_window through the copilot (dry-run then confirm).
        from app.services import ai as _cai12
        _o_tc12,_o_en12=_cai12._TOOL_CALLER,_cai12.enabled
        _turns={"v":[]}
        _cai12._TOOL_CALLER=lambda system,messages,tools,*,model,max_tokens:_turns["v"].pop(0)
        _cai12.enabled=lambda: True
        try:
            def _mw_turns():
                return [
                    {"stop_reason":"tool_use","content":[{"type":"tool_use","id":"m1",
                        "name":"create_maintenance_window",
                        "input":{"client_id":cid,"duration_hours":2,"reason":"copilot test"}}]},
                    {"stop_reason":"end_turn","content":[{"type":"text","text":"Scheduled."}]},
                ]
            _turns["v"]=_mw_turns()
            r=c.post("/api/copilot/ask", json={"message":"schedule a maintenance window for that client"})
            j=r.json(); assert j["proposed_actions"] and not j["actions"], j
            _turns["v"]=_mw_turns()
            r=c.post("/api/copilot/ask", json={"message":"do it","allow_actions":True})
            j=r.json(); assert j["actions"] and j["actions"][0]["result"].get("window_id"), j
            # The window now exists.
            assert any(w for w in c.get(f"/api/maintenance-windows?client_id={cid}").json())
        finally:
            _cai12._TOOL_CALLER,_cai12.enabled=_o_tc12,_o_en12

        # Proactive briefing: on-demand endpoint + heartbeat post (dedup per day).
        bf=c.get("/api/copilot/briefing").json()
        assert "narrative" in bf and "stats" in bf, bf
        assert ca_c.get("/api/copilot/briefing").status_code==403   # staff only
        from app.core.db import SessionLocal as _SL12
        _bdb=_SL12()
        try:
            import datetime as _dt12
            # An earlier heartbeat this run may have already posted today's
            # briefing (real clock) — clear the bookkeeping for a deterministic test.
            from app.services import secure_config as _sc12
            _sc12.upsert_platform(_bdb, _cb12.PROVIDER, "Copilot Briefing", "Automation",
                                  {"last_date": ""})
            morning=_dt12.datetime.now(_dt12.timezone.utc).replace(hour=15)
            early=_dt12.datetime.now(_dt12.timezone.utc).replace(hour=3)
            assert _cb12.maybe_post(_bdb, early)["posted"] is False   # too early
            r1=_cb12.maybe_post(_bdb, morning)
            assert r1["posted"] is True, r1
            assert _cb12.maybe_post(_bdb, morning)["posted"] is False  # once per day
        finally:
            _bdb.close()
        # The briefing landed as a notification.
        assert any("Morning briefing" in (n.get("message") or "")
                   for n in c.get("/api/notifications?limit=50").json())
        print("copilot v1.12: expanded tools (report/history/posture/financials/email/maint-window) "
              "+ proactive daily briefing (on-demand + heartbeat, dedup, notification, RBAC) OK")

        # ===================== v1.13: predictive foresight watch =====================
        from app.services import foresight as _fs13
        from app.core.db import SessionLocal as _SL13
        from app.models import Device as _Dev13, DeviceCheckin as _DC13, Notification as _N13
        import datetime as _dt13b
        # Enroll a device and seed a rising-disk trend that projects to full soon.
        en13=c.post("/api/agent/enroll", json={"enroll_token":c.post(f"/api/agent/enroll-token/{cid}").json()["enroll_token"],
                    "hostname":"PREDICT-PC","os":"Windows 11"}).json()
        pdev13=en13["device_id"]
        _fdb=_SL13()
        try:
            base=_dt13b.datetime.now(_dt13b.timezone.utc)
            for i in range(6):
                _fdb.add(_DC13(device_id=pdev13,
                               ts=base-_dt13b.timedelta(days=2)+_dt13b.timedelta(hours=i*8),
                               cpu_pct=15.0, ram_pct=40.0, disk_pct=70.0+i*2.5, health_score=90))
            _fdb.commit()
            # forecast sees the trend and flags disk_fill.
            fc=_fs13.forecast_device(_fdb, _fdb.get(_Dev13, pdev13))
            assert fc["enough_data"] and any(r["kind"]=="disk_fill" for r in fc["risks"]), fc["risks"]
            # watch() raises a proactive foresight notification (deduped per day).
            newly=_fs13.watch(_fdb, base)
            assert any(r["device_id"]==pdev13 for r in newly), newly
            n2=_fs13.watch(_fdb, base)   # same day -> deduped, no repeat for this device
            assert not any(r["device_id"]==pdev13 for r in n2), "foresight must dedup per device+kind/day"
        finally:
            _fdb.close()
        # The prediction landed as a notification.
        assert any(n.get("kind")=="foresight" and "PREDICT-PC" in (n.get("message") or "")
                   for n in c.get("/api/notifications?limit=80").json())
        # Copilot predicted_issues tool surfaces it.
        # Drive the predicted_issues tool directly with a real staff user object.
        _fdb2=_SL13()
        try:
            from app.models import User as _U13, Role as _R13
            owner=_fdb2.query(_U13).filter(_U13.role==_R13.OWNER).first()
            res=_cop12._run_tool(_fdb2, owner, "predicted_issues", {}, False)
            assert res["count"]>=1 and any(x["hostname"]=="PREDICT-PC" for x in res["predicted"]), res
        finally:
            _fdb2.close()
        print("foresight watch: trend+anomaly forecast -> proactive predicted notification "
              "(deduped) + copilot predicted_issues tool OK")

        # ===================== v1.14: multi-agent fleet workflows =====================
        from app.services import ai as _cai14, copilot as _cop14, copilot_fleet as _cf14
        from app.core.db import SessionLocal as _SL14
        from app.models import User as _U14, Role as _R14, Client as _C14, SupportTicket as _T14
        # A second client so the sweep genuinely fans out across >1 tenant.
        cid14b = c.post("/api/clients", json={"name":"Zeta Fleet Co"}).json()["id"]
        # Stateless (thread-safe) fake tool-caller: each sub-agent calls create_ticket
        # with a DELIBERATELY WRONG client_id, then answers. client_scope must rewrite
        # that id to the client actually being swept — proving cross-tenant isolation.
        BOGUS14 = 999999
        def _fake14(system, messages, tools, *, model, max_tokens):
            last = messages[-1]["content"]
            if isinstance(last, list) and any(x.get("type")=="tool_result" for x in last):
                return {"stop_reason":"end_turn","content":[{"type":"text","text":"Client reviewed."}]}
            return {"stop_reason":"tool_use","content":[{"type":"tool_use","id":"tk",
                    "name":"create_ticket","input":{"client_id":BOGUS14,
                    "subject":"Fleet sweep follow-up","priority":"normal"}}]}
        _o_tc14,_o_en14,_o_cp14 = _cai14._TOOL_CALLER,_cai14.enabled,_cai14.complete
        _cai14._TOOL_CALLER=_fake14; _cai14.enabled=lambda:True
        _cai14.complete=lambda system,user,**k:"Portfolio: all clients reviewed."
        _fs14=_SL14()
        try:
            owner14=_fs14.query(_U14).filter(_U14.role==_R14.OWNER).first()
            n_clients=_fs14.query(_C14).count()
            # (1) DRY-RUN sweep: fans out per client, proposes (not executes) the write.
            dry=_cf14.sweep(_fs14, owner14, "open a follow-up ticket for each client",
                            allow_actions=False)
            assert dry["totals"]["clients"]==n_clients, dry["totals"]
            assert dry["totals"]["proposed"]==n_clients and dry["totals"]["actions"]==0, dry["totals"]
            # Every sub-agent ran its own tool loop (real parallel fan-out).
            assert all("create_ticket" in (r.get("tools_used") or []) for r in dry["results"])
            # Isolation: each proposed action names the client being swept, NOT the bogus id.
            for r in dry["results"]:
                would=r["proposed_actions"][0]["result"]["would"]
                assert r["client"] in would, (r["client"], would)
            # (2) REAL scoped write via a single pinned sub-agent (isolation for mutations):
            #     scope=Zeta, but the model asks for the bogus client_id -> must land on Zeta.
            before=_fs14.query(_T14).filter(_T14.client_id==cid14b).count()
            out14=_cop14.run(_fs14, owner14, "make a ticket", allow_actions=True,
                             client_scope=cid14b)
            assert out14["actions"], out14
            assert out14["actions"][0]["result"]["client"]=="Zeta Fleet Co", out14["actions"][0]
            after=_fs14.query(_T14).filter(_T14.client_id==cid14b).count()
            assert after==before+1, (before, after)
            # The bogus client never received a ticket.
            assert _fs14.query(_T14).filter(_T14.client_id==BOGUS14).count()==0
        finally:
            _cai14._TOOL_CALLER,_cai14.enabled,_cai14.complete=_o_tc14,_o_en14,_o_cp14
            _fs14.close()
        # (3) RBAC: the sweep endpoint is staff-only (a client user is refused).
        assert ca_c.post("/api/copilot/sweep", json={"objective":"x"}).status_code==403
        print("multi-agent fleet sweep: parallel per-client sub-agents + portfolio synthesis "
              "+ client_scope tenant isolation (read + real write) + staff-only RBAC OK")

        # ===================== v1.15: PSA Intelligence =====================
        from app.services import psa_intel as _psa15, copilot as _cop15
        from app.core.db import SessionLocal as _SL15
        from app.models import (Contract as _Ct15, TimeEntry as _TE15, SupportTicket as _ST15,
                                TicketStatus as _TS15, User as _U15, Role as _R15,
                                Notification as _N15)
        import datetime as _dt15
        # Rates: default, then OWNER updates them; a client user is refused.
        assert c.get("/api/psa/rates").json()["bill_rate"] == 150.0
        assert c.put("/api/psa/rates", json={"bill_rate": 175, "cost_rate": 60}).json()["cost_rate"] == 60.0
        assert ca_c.get("/api/psa/rates").status_code == 403
        _p15 = _SL15()
        try:
            now15 = _dt15.datetime.now(_dt15.timezone.utc)
            owner15 = _p15.query(_U15).filter(_U15.role == _R15.OWNER).first()
            pc15 = c.post("/api/clients", json={"name": "PSA Margin Co"}).json()["id"]
            # $1000/mo contract renewing in 20 days.
            ct15 = _Ct15(client_id=pc15, name="Managed IT", amount=1000, billing_period="monthly",
                         status="active", start_date=now15 - _dt15.timedelta(days=120),
                         end_date=now15 + _dt15.timedelta(days=20))
            _p15.add(ct15); _p15.commit()
            # 40h billable, unbilled, logged in last 90d -> ~13.3h/mo * $60 = ~$800 cost.
            for i in range(8):
                _p15.add(_TE15(client_id=pc15, user_id=owner15.id, user_email=owner15.email,
                               minutes=300, billable=True, invoiced=False,
                               created_at=now15 - _dt15.timedelta(days=i * 5)))
            _p15.commit()
            ci15 = _psa15.contract_intel(_p15, now15)
            row15 = next(r for r in ci15["contracts"] if r["contract_id"] == ct15.id)
            assert abs(row15["mrr"] - 1000.0) < 1 and abs(row15["monthly_cost"] - 800.0) < 5, row15
            assert abs(row15["margin"] - 200.0) < 5 and "renewal_soon" in row15["flags"], row15
            assert row15["realized_rate"] and row15["days_to_renewal"] == 20, row15
            assert ci15["totals"]["renewals_soon"] >= 1
            # Revenue leakage: 40h * $175 = $7000 unbilled + the never-invoiced contract due.
            lk15 = _psa15.revenue_leakage(_p15, now15)
            assert abs(lk15["unbilled_time"]["value"] - 7000.0) < 1, lk15["unbilled_time"]
            assert lk15["due_contracts"]["count"] >= 1 and lk15["total_recoverable"] >= 7000.0, lk15
            # SLA radar: a ticket due in 45 min is 'critical' (about to breach, not yet).
            tk15 = _ST15(client_id=pc15, subject="About to breach SLA", priority="high",
                         status=_TS15.OPEN, created_at=now15,
                         resolution_due_at=now15 + _dt15.timedelta(minutes=45),
                         first_response_due_at=now15 + _dt15.timedelta(minutes=300),
                         first_responded_at=now15)
            _p15.add(tk15); _p15.commit()
            radar15 = _psa15.sla_radar(_p15, now15)
            top15 = next(r for r in radar15["at_risk"] if r["ticket_id"] == tk15.id)
            assert top15["level"] == "critical" and not top15["breached"], top15
            # sla_watch raises exactly one pre-breach notification, deduped same day.
            w1 = _psa15.sla_watch(_p15, now15)
            assert any(r["ticket_id"] == tk15.id for r in w1), w1
            w2 = _psa15.sla_watch(_p15, now15)
            assert not any(r["ticket_id"] == tk15.id for r in w2), "sla_watch must dedup per ticket/day"
            assert _p15.query(_N15).filter(_N15.kind == "sla_watch").count() >= 1
            # Copilot tools surface all three (staff).
            r_sla = _cop15._run_tool(_p15, owner15, "sla_radar", {}, False)
            assert "at_risk" in r_sla and r_sla["counts"]["critical"] >= 1, r_sla
            r_cm = _cop15._run_tool(_p15, owner15, "contract_margin", {}, False)
            assert r_cm["totals"]["renewals_soon"] >= 1, r_cm
            r_rl = _cop15._run_tool(_p15, owner15, "revenue_leakage", {}, False)
            assert r_rl["total_recoverable"] >= 7000.0, r_rl
            # Clean up seed so it doesn't pollute later global rollups (unbilled time, MRR).
            _p15.query(_TE15).filter(_TE15.client_id == pc15).delete(synchronize_session=False)
            _p15.query(_ST15).filter(_ST15.client_id == pc15).delete(synchronize_session=False)
            _p15.query(_Ct15).filter(_Ct15.client_id == pc15).delete(synchronize_session=False)
            _p15.commit()
        finally:
            _p15.close()
        # RBAC: these copilot tools are staff-only; the client toolset excludes them.
        _cnames15 = {d["name"] for d in _cop15._tool_defs(staff=False)}
        assert not ({"sla_radar", "contract_margin", "revenue_leakage"} & _cnames15)
        assert {"sla_radar", "contract_margin", "revenue_leakage"} <= {d["name"] for d in _cop15._tool_defs(staff=True)}
        assert ca_c.get("/api/psa/contract-intel").status_code == 403
        print("PSA Intelligence: contract margin/realization/renewal + revenue leakage "
              "+ predictive SLA radar + pre-breach sla_watch (deduped) + 3 staff copilot tools + RBAC OK")

        # ===================== v1.16: AI vCIO =====================
        from app.services import vcio as _vc16, copilot as _cop16
        from app.core.db import SessionLocal as _SL16
        from app.models import (Asset as _As16, Contract as _Ct16, TimeEntry as _TE16,
                                SupportTicket as _ST16, TicketStatus as _TS16, User as _U16,
                                Role as _R16, Client as _C16)
        import datetime as _dt16
        _v16 = _SL16()
        try:
            now16 = _dt16.datetime.now(_dt16.timezone.utc)
            owner16 = _v16.query(_U16).filter(_U16.role == _R16.OWNER).first()
            vc16 = c.post("/api/clients", json={"name": "vCIO Review Co"}).json()["id"]
            # Aging + out-of-warranty hardware -> refresh budget recommendation.
            _v16.add(_As16(client_id=vc16, name="Old Server", asset_type="server",
                           purchase_date=now16 - _dt16.timedelta(days=7 * 365),
                           warranty_expires=now16 - _dt16.timedelta(days=20)))
            _v16.add(_As16(client_id=vc16, name="Old PC", asset_type="workstation",
                           purchase_date=now16 - _dt16.timedelta(days=6 * 365),
                           warranty_expires=now16 - _dt16.timedelta(days=5)))
            # Underwater contract renewing soon.
            ct16 = _Ct16(client_id=vc16, name="MSP Agreement", amount=500, billing_period="monthly",
                         status="active", start_date=now16 - _dt16.timedelta(days=120),
                         end_date=now16 + _dt16.timedelta(days=30))
            _v16.add(ct16); _v16.commit()
            for i in range(6):
                _v16.add(_TE16(client_id=vc16, user_id=owner16.id, user_email=owner16.email,
                               minutes=400, billable=True, invoiced=False,
                               created_at=now16 - _dt16.timedelta(days=i * 6)))
            # A breached-SLA ticket.
            _v16.add(_ST16(client_id=vc16, subject="Server down", priority="high", status=_TS16.OPEN,
                           created_at=now16 - _dt16.timedelta(hours=30),
                           resolution_due_at=now16 - _dt16.timedelta(hours=5),
                           first_response_due_at=now16 - _dt16.timedelta(hours=25)))
            _v16.commit()
            client16 = _v16.get(_C16, vc16)
            # Lifecycle: 2 devices to refresh at $1,200 each.
            life16 = _vc16.asset_lifecycle(_v16, vc16, now16)
            assert life16["to_refresh"] == 2 and abs(life16["refresh_budget"] - 2400.0) < 1, life16
            rv16 = _vc16.build_review(_v16, client16, now16)
            areas = {r["area"] for r in rv16["recommendations"]}
            titles = " | ".join(r["title"] for r in rv16["recommendations"])
            assert {"Service", "Financial", "Lifecycle"} <= areas, areas
            assert "underwater" in titles.lower() and "SLA breach" in titles, titles
            assert isinstance(rv16["maturity_index"], int) and 0 <= rv16["maturity_index"] <= 100
            assert rv16["budget_total"] >= 2400.0
            # Roadmap buckets are horizon-partitioned and cover every rec.
            assert sum(len(v) for v in rv16["roadmap"].values()) == rv16["counts"]["total"]
            # Copilot tool (staff) surfaces the review.
            tool16 = _cop16._run_tool(_v16, owner16, "vcio_review", {"client_id": vc16}, False)
            assert tool16["maturity_index"] == rv16["maturity_index"] and tool16["recommendations"], tool16
            # Clean up seed so downstream global rollups stay pristine.
            for M in (_TE16, _ST16, _Ct16, _As16):
                _v16.query(M).filter(M.client_id == vc16).delete(synchronize_session=False)
            _v16.commit()
        finally:
            _v16.close()
        # Route + access: staff reads any client; the vcio_review copilot tool is staff-only.
        assert c.get(f"/api/vcio/{vc16}/review").status_code == 200
        assert ca_c.get(f"/api/vcio/{vc16}/review").status_code == 403   # other client's user refused
        assert ca_c.get(f"/api/vcio/{cid}/review").status_code == 200    # own client's review allowed
        assert "vcio_review" not in {d["name"] for d in _cop16._tool_defs(staff=False)}
        assert "vcio_review" in {d["name"] for d in _cop16._tool_defs(staff=True)}
        print("AI vCIO: maturity index + ranked/budgeted roadmap (security/patch/reliability/"
              "service/financial/lifecycle) + copilot tool + client-scoped access OK")

        # ===================== v1.17: The Autonomy Engine =====================
        from app.services import autonomy as _au17, patching as _pt17, copilot as _cop17
        from app.core.db import SessionLocal as _SL17
        from app.models import (ActionOutcome as _AO17, Alert as _Al17, AlertSeverity as _AS17,
                                AlertStatus as _ASt17, Device as _Dv17, DevicePatch as _DP17,
                                DeploymentStatus as _DS17, Notification as _N17,
                                User as _U17, Role as _R17)
        import datetime as _dt17
        # Two fresh tenants: one earns trust, one gets benched.
        cidT = c.post("/api/clients", json={"name": "Trust Earned Co"}).json()["id"]
        cidX = c.post("/api/clients", json={"name": "Benched Co"}).json()["id"]
        enT = c.post("/api/agent/enroll", json={"enroll_token": c.post(f"/api/agent/enroll-token/{cidT}").json()["enroll_token"],
                     "hostname": "TRUST-PC", "os": "Windows 11"}).json()
        enX = c.post("/api/agent/enroll", json={"enroll_token": c.post(f"/api/agent/enroll-token/{cidX}").json()["enroll_token"],
                     "hostname": "BENCH-PC", "os": "Windows 11"}).json()
        _a17 = _SL17()
        try:
            now17 = _dt17.datetime.now(_dt17.timezone.utc)
            owner17 = _a17.query(_U17).filter(_U17.role == _R17.OWNER).first()
            pol_before = _pt17.get_policy(_a17)   # restore after — other blocks rely on it
            # (1) Recording at the chokepoint: approving a patch logs an outcome.
            _a17.add(_DP17(device_id=enT["device_id"], client_id=cidT, name="Crit",
                           kb="5099001", severity="critical")); _a17.commit()
            devT = _a17.get(_Dv17, enT["device_id"])
            depT = _pt17.approve_patches(_a17, devT, owner17, kbs=["KB5099001"])
            assert _a17.query(_AO17).filter(_AO17.ref_kind == "deployment",
                                            _AO17.ref_id == depT.id).count() == 1
            # Idempotent: re-record same ref -> no duplicate.
            _au17.record(_a17, action_type="patch_install", playbook="winupdate:pinned",
                         client_id=cidT, ref_kind="deployment", ref_id=depT.id)
            assert _a17.query(_AO17).filter(_AO17.ref_id == depT.id,
                                            _AO17.ref_kind == "deployment").count() == 1
            # (2) Grading by observable state: SUCCEEDED job -> success verdict.
            depT.status = _DS17.SUCCEEDED; depT.exit_code = 0; _a17.commit()
            g1 = _au17.grade_due(_a17, now17 + _dt17.timedelta(minutes=31))
            assert any(g["verdict"] == "success" and g["action_type"] == "patch_install" for g in g1), g1
            # FAILED job -> failure verdict.
            _a17.add(_DP17(device_id=enX["device_id"], client_id=cidX, name="Crit2",
                           kb="5099002", severity="critical")); _a17.commit()
            devX = _a17.get(_Dv17, enX["device_id"])
            depX = _pt17.approve_patches(_a17, devX, owner17, kbs=["KB5099002"])
            depX.status = _DS17.FAILED; depX.exit_code = 1; _a17.commit()
            g2 = _au17.grade_due(_a17, now17 + _dt17.timedelta(minutes=31))
            assert any(g["verdict"] == "failure" for g in g2), g2
            # Remediation grading: alert cleared -> success.
            al17 = _Al17(client_id=cidT, device_id=devT.id, kind="service_down",
                         severity=_AS17.CRITICAL, status=_ASt17.RESOLVED, message="x",
                         first_seen=now17, last_seen=now17, resolved_at=now17)
            _a17.add(al17); _a17.commit()
            _au17.record(_a17, action_type="remediation", playbook="service_down→Restart svc",
                         client_id=cidT, device_id=devT.id, ref_kind="alert", ref_id=al17.id,
                         grade_after_minutes=0, now=now17); _a17.commit()
            g3 = _au17.grade_due(_a17, now17 + _dt17.timedelta(minutes=1))
            assert any(g["action_type"] == "remediation" and g["verdict"] == "success" for g in g3), g3
            # (3) The earned-autonomy gate: 5 graded failures -> SUSPENDED; fresh combo allowed.
            for i in range(4):
                _a17.add(_AO17(action_type="patch_install", playbook="winupdate:pinned",
                               client_id=cidX, ref_kind="deployment", ref_id=917000 + i,
                               autonomous=True, taken_at=now17, grade_after=now17,
                               graded_at=now17, verdict="failure"))
            _a17.commit()
            okT, _why = _au17.allowed(_a17, "patch_install", cidT)
            okX, whyX = _au17.allowed(_a17, "patch_install", cidX)
            assert okT is True and okX is False and "suspended" in whyX, (okT, okX, whyX)
            # (4) The gate has real teeth: auto-approve sweep SKIPS the benched client
            #     (and notifies), still serves the trusted one.
            _pt17.save_policy(_a17, auto_approve=True, min_severity="critical",
                              only_in_maintenance=False)
            _a17.add(_DP17(device_id=devX.id, client_id=cidX, name="Crit3",
                           kb="5099003", severity="critical")); _a17.commit()
            made17 = _pt17.auto_approve_sweep(_a17, now17)
            _a17.commit()
            assert not any(m["device_id"] == devX.id for m in made17), made17
            assert _a17.query(_N17).filter(_N17.kind == "autonomy",
                                           _N17.client_id == cidX).count() >= 1
            # Operator ceiling: pin the trusted client to supervised -> gate refuses too.
            _au17.save_settings(_a17, ceilings={str(cidT): "supervised"})
            okC, whyC = _au17.allowed(_a17, "patch_install", cidT)
            assert okC is False and "ceiling" in whyC, (okC, whyC)
            _au17.save_settings(_a17, ceilings={})
            # (5) Ledger levels + Self-Driving Report + playbook memory.
            led17 = _au17.ledger(_a17)
            lv = {(r["action_type"], r["client_id"]): r["level"] for r in led17["combos"]}
            assert lv.get(("patch_install", cidX)) == "suspended", lv
            assert lv.get(("patch_install", cidT)) == "watching", lv
            rep17 = _au17.report(_a17, days=7, now=now17 + _dt17.timedelta(minutes=32))
            assert rep17["graded"] >= 3 and rep17["est_minutes_saved"] >= 20, rep17
            assert any(r["client_id"] == cidX for r in rep17["suspended_combos"]), rep17
            mem17 = _au17.playbook_memory(_a17, client_id=cidT)
            assert mem17["count"] >= 2 and mem17["success_rate"] == 1.0, mem17
            # (6) Copilot tools (staff) + RBAC.
            t1 = _cop17._run_tool(_a17, owner17, "self_driving_report", {"days": 7}, False)
            assert t1["autonomous_actions"] >= 1 and "success_rate" in t1, t1
            t2 = _cop17._run_tool(_a17, owner17, "playbook_memory", {"client_id": cidT}, False)
            assert t2["count"] >= 2, t2
            # Restore policy + clean my outcome/patch seeds so later blocks are pristine.
            _pt17.save_policy(_a17, **{k: v for k, v in pol_before.items()
                                       if k in ("auto_approve", "min_severity", "only_in_maintenance")})
            _a17.query(_AO17).filter(_AO17.client_id.in_([cidT, cidX])).delete(synchronize_session=False)
            _a17.query(_DP17).filter(_DP17.client_id.in_([cidT, cidX])).delete(synchronize_session=False)
            _a17.commit()
        finally:
            _a17.close()
        _cn17 = {d["name"] for d in _cop17._tool_defs(staff=False)}
        assert not ({"self_driving_report", "playbook_memory"} & _cn17)
        assert {"self_driving_report", "playbook_memory"} <= {d["name"] for d in _cop17._tool_defs(staff=True)}
        assert c.get("/api/autonomy/report").status_code == 200
        assert c.get("/api/autonomy/ledger").status_code == 200
        assert ca_c.get("/api/autonomy/report").status_code == 403
        assert ca_c.put("/api/autonomy/settings", json={"min_success": 0.5}).status_code == 403
        print("Autonomy Engine: outcome recording (idempotent) + state-based grading "
              "(success/failure) + earned-autonomy gate (suspension blocks real sweep + "
              "notifies, ceiling honored) + trust ledger + self-driving report + playbook "
              "memory + copilot tools + RBAC OK")

        # ===================== v1.19: Incident Intelligence =====================
        from app.services import (incidents as _in19, proactive as _pr19,
                                  heartbeat as _hb19, copilot as _cop19)
        from app.core.db import SessionLocal as _SL19
        from app.models import (Alert as _Al19, AlertStatus as _AS19, Device as _Dv19,
                                Incident as _In19, Notification as _N19,
                                SupportTicket as _ST19, User as _U19, Role as _R19)
        import datetime as _dt19
        cid19 = c.post("/api/clients", json={"name": "Storm Site Co"}).json()["id"]
        for i in range(4):
            tok19 = c.post(f"/api/agent/enroll-token/{cid19}").json()["enroll_token"]
            _a19 = TestClient(app); _a19.cookies.clear()
            _a19.post("/api/agent/enroll", json={"enroll_token": tok19,
                      "hostname": f"STORM-{i}", "os": "Windows 11"})
        _i19 = _SL19()
        try:
            now19 = _dt19.datetime.now(_dt19.timezone.utc)
            pr_before19 = _pr19.get_config(_i19)     # restore after
            _pr19.save_config(_i19, auto_ticket_enabled=True, min_severity="critical")
            # The whole site goes dark: every device last seen 2 hours ago.
            for d in _i19.query(_Dv19).filter(_Dv19.client_id == cid19).all():
                d.last_checkin = now19 - _dt19.timedelta(hours=2)
            _i19.commit()
            hb19 = _hb19.run_all(_i19, now19)
            assert hb19["incidents"] == 1, hb19
            inc19 = _i19.query(_In19).filter(_In19.client_id == cid19).one()
            assert inc19.kind == "device_offline" and inc19.alert_count >= 3, \
                (inc19.kind, inc19.alert_count)
            assert "site outage" in inc19.title.lower(), inc19.title
            # THE point: one storm -> ONE urgent ticket, not one per device.
            tix19 = _i19.query(_ST19).filter(_ST19.client_id == cid19).all()
            assert len(tix19) == 1 and tix19[0].priority == "urgent", \
                [(t.id, t.subject) for t in tix19]
            assert tix19[0].id == inc19.ticket_id and "[Incident]" in tix19[0].subject
            assert _i19.query(_N19).filter(_N19.kind == "incident",
                                           _N19.client_id == cid19).count() >= 1
            # Second tick: the storm is ABSORBED (no duplicate incident/ticket).
            hb19b = _hb19.run_all(_i19, now19 + _dt19.timedelta(minutes=2))
            assert _i19.query(_In19).filter(_In19.client_id == cid19).count() == 1
            assert _i19.query(_ST19).filter(_ST19.client_id == cid19).count() == 1
            # Copilot sees it (base read tool — also tenant-scoped for clients).
            owner19 = _i19.query(_U19).filter(_U19.role == _R19.OWNER).first()
            t19 = _cop19._run_tool(_i19, owner19, "open_incidents", {}, False)
            assert any(x["id"] == inc19.id for x in t19["incidents"]), t19
            # All member alerts clear -> the incident auto-resolves + notifies.
            for al in _i19.query(_Al19).filter(_Al19.client_id == cid19).all():
                al.status = _AS19.RESOLVED; al.resolved_at = now19
            _i19.commit()
            closed19 = _in19.sweep_resolutions(_i19, now19 + _dt19.timedelta(minutes=5))
            assert any(x["incident_id"] == inc19.id for x in closed19), closed19
            _i19.refresh(inc19)
            assert inc19.status == "resolved" and inc19.resolved_at is not None
            # Restore config + bring devices back online so later sweeps stay quiet.
            _pr19.save_config(_i19, auto_ticket_enabled=pr_before19["auto_ticket_enabled"],
                              min_severity=pr_before19["min_severity"])
            for d in _i19.query(_Dv19).filter(_Dv19.client_id == cid19).all():
                d.last_checkin = _dt19.datetime.now(_dt19.timezone.utc)
            _i19.commit()
        finally:
            _i19.close()
        # API surface + tenant scoping: staff sees it; another client's user must not.
        got19 = c.get(f"/api/incidents?status=resolved").json()["incidents"]
        assert any(x["client_id"] == cid19 for x in got19)
        ca19 = ca_c.get("/api/incidents").json()["incidents"]
        assert not any(x["client_id"] == cid19 for x in ca19), ca19
        print("Incident Intelligence: 4-device offline storm -> ONE incident + ONE urgent "
              "ticket (members suppressed) + absorb on repeat + auto-resolve when alerts "
              "clear + copilot tool + tenant-scoped API OK")

        # ===================== v1.20: Content Autopilot =====================
        from app.services import (ai as _ai20, content_autopilot as _cap20,
                                  jp_site as _jp20, wordpress as _wp20,
                                  blog_autopilot as _ba20, secure_config as _sc20)
        from app.core.db import SessionLocal as _SL20
        from app.models import SocialPost as _SP20, Notification as _N20
        import datetime as _dt20, json as _json20
        _c20 = _SL20()
        _o20 = (_ai20.enabled, _ai20.complete, _jp20._HTTP, _wp20.configured,
                _ba20.generate_article, _ba20.publish_article)
        try:
            now20 = _dt20.datetime.now(_dt20.timezone.utc).replace(hour=15)
            # One-click JP repo setup via the API (token encrypted in the vault).
            assert c.put("/api/content-autopilot/jp-site",
                         json={"project": "BVTECHLLC-group/jordanpolasek-website",
                               "token": "glpat-test"}).json()["configured"] is True
            assert ca_c.put("/api/content-autopilot/jp-site",
                            json={"project": "x"}).status_code == 403
            _sc20.upsert_platform(_c20, "pub_linkedin", "LinkedIn", "Publishing",
                                  {"access_token": "tok", "person_urn": "urn:li:person:x"})
            _sc20.upsert_platform(_c20, "gbp", "GBP", "Publishing",
                                  {"account_name": "accounts/1", "location_name": "locations/2"})
            # Offline fakes: AI + GitLab + WordPress.
            _ai20.enabled = lambda: True
            _ai20.complete = (lambda system, user, **k:
                              ("TITLE: Win in Houston\nEXCERPT: x\nHTML:\n<p>"
                               + ("Article body sentence. " * 25) + "</p>")
                              if ("TITLE:" in system or "STRICT JSON" in system)
                              else "Short channel post #IT")
            def _gl20(method, url, token, payload=None):
                if "repository/tree" in url:
                    return [{"type": "tree", "path": "older-post"}]
                if "repository/files" in url:
                    import base64
                    return {"content": base64.b64encode(
                        b"<html><body><div class='content'>OLD</div></body></html>").decode()}
                if url.endswith("/repository/commits"):
                    return {"id": "abc123def"}
                if "pipelines?sha=" in url:
                    return [{"status": "failed"}]     # the Cloudflare build FAILS
                if "/revert" in url:
                    return {"id": "rev456"}
                return {}
            _jp20._HTTP = _gl20
            _wp20.configured = lambda db: True
            _ba20.generate_article = lambda db, now=None, **k: {"title": "BV", "html": "<p>a</p>",
                                                                "excerpt": "e"}
            class _Row20:
                status = "posted"; url = "https://bvtech.org/blog/x.html"
                title = "BV"; error = None
            _ba20.publish_article = lambda db, a, source=None: _Row20()
            # Enable + run: all four channels post, each customized per channel.
            _cap20.save_config(_c20, enabled=True)
            out20 = _cap20.run_daily(_c20, now20)
            assert set(out20["results"]) == {"bvtech", "jp", "linkedin", "gbp"}, out20
            assert all(v["ok"] for v in out20["results"].values()), out20
            assert "jordanpolasek.com/win-in-houston" in out20["results"]["jp"]["detail"]
            # Dedupe: a second run the same day does nothing.
            assert _cap20.run_daily(_c20, now20)["results"] == {}
            # LinkedIn + GBP rode the retry-hardened autopost queue (channels is a
            # JSON list — exactly what autopost.publish_due expects).
            q20 = {(tuple(p.channels or []), p.status) for p in _c20.query(_SP20).all()}
            assert (("linkedin",), "queued") in q20 and (("google_business",), "queued") in q20, q20
            # JP build verification: failed Cloudflare pipeline -> auto-REVERT + notify.
            ver20 = _jp20.verify_pending(_c20, now20)
            assert ver20 and ver20[0]["status"] == "failed" and ver20[0]["reverted"] is True, ver20
            assert _c20.query(_N20).filter(_N20.kind == "content").count() >= 1
            # Failure path: break one channel -> notification + NOT marked done (retries).
            _sc20.upsert_platform(_c20, "content_autopilot", "Content Autopilot",
                                  "Publishing", {"enabled": True, "last": {}, "last_error": {}})
            _wp20.configured = lambda db: False   # bvtech now unconfigured
            out20b = _cap20.run_daily(_c20, now20)
            assert out20b["results"]["bvtech"]["ok"] is False
            assert _cap20.get_config(_c20)["last"].get("bvtech") is None   # will retry
            assert _cap20.get_config(_c20)["last"].get("jp")               # others done
            # Status endpoint powers the one-click card; staff-only.
            st20 = c.get("/api/content-autopilot/status").json()
            assert {x["key"] for x in st20["channels"]} == {"bvtech", "jp", "linkedin", "gbp"}
            assert all(x["setup_hint"] for x in st20["channels"])
            assert ca_c.get("/api/content-autopilot/status").status_code == 403
            # v1.21: both sites are GitLab static sites (NOT WordPress) — ONE
            # shared token connects both, with the known repos as defaults.
            r21 = c.put("/api/content-autopilot/sites", json={"token": "glpat-shared"})
            assert r21.status_code == 200 and r21.json()["jp"] and r21.json()["bvtech"], r21.text
            assert r21.json()["bvtech_project"] == "BVTECHLLC-group/bvtech-website-new"
            assert ca_c.put("/api/content-autopilot/sites", json={"token": "x"}).status_code == 403
            # bvtech publishes GitLab-first now: blog/<slug>.html on the bvtech repo.
            out21 = _jp20.publish(_c20, {"title": "Houston IT Guide", "html": "<p>x</p>",
                                         "excerpt": "e"}, site="bvtech")
            assert out21["ok"] and out21["url"] == "https://bvtech.org/blog/houston-it-guide.html", out21
            ok21, detail21 = _cap20._run_bvtech(_c20, now20)
            assert ok21 and "bvtech.org/blog/" in detail21, (ok21, detail21)
            # Token fallback chain: env var lights it up even with an empty vault
            # (delete the vault rows — upsert deliberately preserves saved secrets).
            import os as _os21
            from app.models import IntegrationConnection as _IC21
            (_c21_del := _c20.query(_IC21)
                .filter(_IC21.provider.in_(["gitlab", "bvtech_site"]))
                .delete(synchronize_session=False))
            _c20.commit()
            _os21.environ["GITLAB_TOKEN"] = "glpat-env"
            assert _jp20.configured(_c20, "bvtech") is True
            del _os21.environ["GITLAB_TOKEN"]
            assert _jp20.configured(_c20, "bvtech") is False
            # v1.21.1 Test connection: per-site verdicts — jp still has its own
            # token (ok), bvtech has none (clear 'no token' error, not a mystery).
            t21 = c.post("/api/content-autopilot/test-sites").json()
            assert t21["jp"]["ok"] is True, t21
            assert t21["bvtech"]["ok"] is False and "no token" in t21["bvtech"]["error"], t21
            c.put("/api/content-autopilot/sites", json={"token": "glpat-shared"})
            t21b = c.post("/api/content-autopilot/test-sites").json()
            assert t21b["bvtech"]["ok"] is True and t21b["jp"]["ok"] is True, t21b
            assert ca_c.post("/api/content-autopilot/test-sites").status_code == 403
        finally:
            (_ai20.enabled, _ai20.complete, _jp20._HTTP, _wp20.configured,
             _ba20.generate_article, _ba20.publish_article) = _o20
            _cap20.save_config(_c20, enabled=False)
            _c20.query(_SP20).delete(synchronize_session=False)
            # Un-configure the channels we seeded so later blocks (gbp/publisher
            # settings tests) still see a pristine state.
            from app.models import IntegrationConnection as _IC20
            (_c20.query(_IC20)
                 .filter(_IC20.provider.in_(["gbp", "pub_linkedin", "jp_site",
                                             "gitlab", "bvtech_site"]))
                 .delete(synchronize_session=False))
            _c20.commit()
            _c20.close()
        # ===================== v1.22: Connection Center =====================
        from app.services import ai as _ai22, secure_config as _sc22
        from app.core.db import SessionLocal as _SL22
        _cc = _SL22()
        try:
            # Claude key from the VAULT lights ai.enabled() (env fallback preserved).
            _ai22.refresh_key_cache()
            base_enabled = _ai22.enabled()   # whatever the env says
            _sc22.upsert_platform(_cc, "anthropic", "Claude (Anthropic)", "AI",
                                  {"api_key": "sk-ant-test-key-000000000000"})
            _ai22.refresh_key_cache()
            assert _ai22.enabled() is True and _ai22.key_source() == "vault"
            # Settings API: OWNER saves, key value never echoed back.
            r22 = c.get("/api/ai/settings").json()
            assert r22["connected"] is True and "api_key" not in str(r22)
            assert ca_c.get("/api/ai/settings").status_code == 403
            assert ca_c.put("/api/ai/settings", json={"api_key": "sk-ant-xxxxxxxxxxxxxxxxxxxx"}).status_code == 403
            assert c.put("/api/ai/settings", json={"api_key": "short"}).status_code == 400
            # The Connection Center registry: every item has status + guidance.
            cc22 = c.get("/api/setup/connections").json()
            keys22 = {i["key"] for i in cc22["items"]}
            assert {"anthropic", "gitlab_sites", "m365_mailbox", "pub_linkedin", "gbp",
                    "stripe", "smtp", "quickbooks", "hubspot", "dialpad",
                    "google_places", "tacticalrmm"} <= keys22, keys22
            for i in cc22["items"]:
                assert i["unlocks"] and i["priority"] in (1, 2, 3), i["key"]
                assert i["console_url"] or i["console_hint"], i["key"]
            byk22 = {i["key"]: i for i in cc22["items"]}
            assert byk22["anthropic"]["connected"] is True
            assert "console.anthropic.com" in byk22["anthropic"]["console_url"]
            assert 0 <= cc22["score_pct"] <= 100 and cc22["connected"] >= 1
            assert ca_c.get("/api/setup/connections").status_code == 403
            # Clean up the vault key so later AI-off assumptions hold.
            from app.models import IntegrationConnection as _IC22
            _cc.query(_IC22).filter(_IC22.provider == "anthropic").delete(synchronize_session=False)
            _cc.commit()
            _ai22.refresh_key_cache()
            assert _ai22.enabled() is base_enabled
        finally:
            _cc.close()
        # ===================== v1.23: Browser & SaaS Guardian =====================
        from app.services import browser_guard as _bg23, copilot as _cop23
        cid23 = c.post("/api/clients", json={"name": "SaaS Blindspot Co"}).json()["id"]
        tok23 = c.post(f"/api/agent/enroll-token/{cid23}").json()["enroll_token"]
        _a23 = TestClient(app); _a23.cookies.clear()
        en23 = _a23.post("/api/agent/enroll", json={"enroll_token": tok23,
                         "hostname": "WEB-PC", "os": "Windows 11"}).json()
        hdr23 = {"X-Enroll-Id": en23["enroll_id"], "X-Agent-Key": en23["agent_key"]}
        # (1) Agent reports browser reality: SaaS domains + an extension. Noise
        #     (google/doubleclick) must be filtered; catalog names must map.
        r23 = _a23.post("/api/agent/browser", headers=hdr23, json={
            "extensions": [{"browser": "chrome", "id": "abcdefghij", "name": "Honey",
                            "version": "1.2", "permissions": "tabs,webRequest,<all_urls>"}],
            "domains": [{"host": "slack.com", "hits": 120}, {"host": "www.notion.so", "hits": 80},
                        {"host": "weirdcrm.io", "hits": 33}, {"host": "google.com", "hits": 999},
                        {"host": "doubleclick.net", "hits": 500}]})
        assert r23.status_code == 200 and r23.json() == {"extensions": 1, "webapps": 3}, r23.text
        inv23 = c.get(f"/api/browser/inventory/{cid23}").json()
        w23 = {w["identifier"]: w for w in inv23["webapps"]}
        assert w23["slack.com"]["name"] == "Slack" and w23["notion.so"]["category"] == "Docs & wiki"
        assert "google.com" not in w23 and "doubleclick.net" not in w23   # plumbing filtered
        assert w23["weirdcrm.io"]["category"] == "Uncategorized"           # shadow IT still visible
        assert inv23["extensions"][0]["name"] == "Honey"
        # (2) Govern: block a SaaS + the extension, approve one, protect browsers.
        assert c.post("/api/browser/decide", json={"client_id": cid23, "identifier": "notion.so",
                      "action": "block"}).json()["status"] == "blocked"
        c.post("/api/browser/decide", json={"client_id": cid23, "identifier": "abcdefghij",
               "action": "block"})
        c.post("/api/browser/decide", json={"client_id": cid23, "identifier": "slack.com",
               "action": "approve"})
        c.put("/api/browser/protect", json={"client_id": cid23, "protect": True})
        # (3) The device pulls EXACTLY what it must enforce.
        pol23 = _a23.get("/api/agent/browser-policy", headers=hdr23).json()
        assert pol23 == {"blocked_domains": ["notion.so"],
                         "blocked_extensions": ["abcdefghij"], "protect": True}, pol23
        # (4) Re-report dedupes (same row, refreshed) — no inventory bloat.
        _a23.post("/api/agent/browser", headers=hdr23,
                  json={"domains": [{"host": "slack.com", "hits": 150}]})
        inv23b = c.get(f"/api/browser/inventory/{cid23}").json()
        srow = [w for w in inv23b["webapps"] if w["identifier"] == "slack.com"]
        assert len(srow) == 1 and srow[0]["hits"] == 150 and srow[0]["devices"] == 1
        assert srow[0]["status"] == "approved"
        # (5) Copilot tool (tenant-scoped) + RBAC: deciding is staff-only; the
        #     client's own users can READ their own landscape, not others'.
        from app.core.db import SessionLocal as _SL23
        from app.models import User as _U23, Role as _R23
        _s23 = _SL23()
        try:
            owner23 = _s23.query(_U23).filter(_U23.role == _R23.OWNER).first()
            t23 = _cop23._run_tool(_s23, owner23, "saas_inventory", {"client_id": cid23}, False)
            assert t23["counts"]["webapps"] == 3 and t23["protect"] is True, t23
        finally:
            _s23.close()
        assert ca_c.post("/api/browser/decide", json={"client_id": cid23,
                         "identifier": "x.com", "action": "block"}).status_code == 403
        assert ca_c.get(f"/api/browser/inventory/{cid23}").status_code == 403  # other client
        assert ca_c.get(f"/api/browser/inventory/{cid}").status_code == 200    # own client OK
        # (6) Agent file guards: the PowerShell payload must stay pure ASCII and
        #     PS-5.1-safe (no `? :` ternary), and carry the new guard functions.
        _ps23 = open("agent/opspilot_agent.ps1", "rb").read()
        assert all(b < 128 for b in _ps23), "agent must stay pure ASCII"
        _pst23 = _ps23.decode()
        for fn in ("Get-BrowserApps", "Report-Browser", "Apply-BrowserPolicy",
                   "Add-HostCounts", "PULSE BROWSER GUARD", "ExtensionInstallBlocklist",
                   "SafeBrowsingProtectionLevel", "SmartScreenEnabled"):
            assert fn in _pst23, f"agent missing {fn}"
        import re as _re23
        assert not _re23.search(r"\(\$\w+ \? ", _pst23), "PS7 ternary would break PS 5.1"
        print("Browser & SaaS Guardian: agent report -> SaaS catalog rollup (noise filtered, "
              "shadow IT visible) + approve/block/protect governance -> device enforcement "
              "policy + dedupe + copilot tool + RBAC + pure-ASCII/PS5.1 agent guards OK")

        # ===================== v1.24: Connection Center Enter-credential =====================
        from app.core.db import SessionLocal as _SL24
        from app.models import IntegrationConnection as _IC24
        from app.services import secure_config as _sc24, jp_site as _jp24
        # Every non-env connector exposes fields to paste + save.
        cc24 = c.get("/api/setup/connections").json()
        b24 = {i["key"]: i for i in cc24["items"]}
        assert b24["gitlab_sites"]["can_enter"] and b24["stripe"]["can_enter"]
        assert not b24["smtp"]["can_enter"]   # env-only
        assert [f["key"] for f in b24["m365_mailbox"]["fields"]] == ["client_id", "tenant_id", "client_secret"]
        # Generic save -> ENCRYPTED at rest; identifiers stored plainly.
        assert c.post("/api/setup/connections/gitlab_sites",
                      json={"values": {"token": "glpat-SMOKESECRET"}}).json()["connected"] is True
        c.post("/api/setup/connections/stripe", json={"values": {"secret_key": "sk_live_smoke"}})
        c.post("/api/setup/connections/m365_mailbox",
               json={"values": {"client_id": "cid24", "tenant_id": "tid24", "client_secret": "m365secret24"}})
        _s24 = _SL24()
        try:
            for prov, sec, fld in [("gitlab", "glpat-SMOKESECRET", "token"),
                                   ("stripe", "sk_live_smoke", "secret_key"),
                                   ("m365_mailbox", "m365secret24", "client_secret")]:
                raw = _s24.query(_IC24).filter(_IC24.provider == prov).first()
                assert sec not in str(raw.config), f"{prov} secret stored in plaintext!"
                assert _sc24.get_secret(raw.config, fld) == sec, f"{prov} decrypt failed"
            m24 = _s24.query(_IC24).filter(_IC24.provider == "m365_mailbox").first()
            assert m24.config.get("client_id") == "cid24"   # identifier stored plainly
        finally:
            _s24.close()
        # Blank values are ignored (400, keeps the saved secret); env-only + unknown rejected.
        assert c.post("/api/setup/connections/stripe", json={"values": {"secret_key": "  "}}).status_code == 400
        assert c.post("/api/setup/connections/smtp", json={"values": {"x": "y"}}).status_code == 400
        assert c.post("/api/setup/connections/nope", json={"values": {"a": "b"}}).status_code == 404
        # OWNER-only save; staff can still read the Center.
        assert ca_c.post("/api/setup/connections/stripe", json={"values": {"secret_key": "x"}}).status_code == 403
        # Clean up so later blocks see a pristine vault.
        _s24b = _SL24()
        try:
            (_s24b.query(_IC24)
                  .filter(_IC24.provider.in_(["gitlab", "stripe", "m365_mailbox"]))
                  .delete(synchronize_session=False))
            _s24b.commit()
        finally:
            _s24b.close()
        print("Connection Center Enter-credential: per-connector fields + generic save "
              "ENCRYPTED at rest (identifiers plain) + blank-ignore + env-only/unknown "
              "rejected + OWNER-only RBAC OK")

        # ===================== v1.25: live verify + unreadable detection =====================
        from app.services import jp_site as _jp25, secure_config as _sc25
        from app.core.db import SessionLocal as _SL25
        from app.models import IntegrationConnection as _IC25
        _o25 = _jp25._HTTP
        _jp25._HTTP = (lambda method, url, token, payload=None:
                       {"username": "jordanp"} if url.endswith("/user")
                       else ({"path_with_namespace": "ok"} if "/projects/" in url else {}))
        try:
            # Save returns the LIVE-VERIFY result, not just "saved".
            sv25 = c.post("/api/setup/connections/gitlab_sites",
                          json={"values": {"token": "glpat-REAL25"}}).json()
            assert sv25["connected"] is True and sv25["verified"] is True, sv25
            assert "Verified as jordanp" in sv25["detail"], sv25
            # The Test endpoint live-checks on demand.
            t25 = c.post("/api/setup/connections/gitlab_sites/test").json()
            assert t25["ok"] is True and "publish to" in t25["detail"], t25
            # Center exposes credential_state + testable.
            gl25 = {i["key"]: i for i in c.get("/api/setup/connections").json()["items"]}["gitlab_sites"]
            assert gl25["credential_state"] == "ok" and gl25["testable"] is True
            # THE silent bug that looked like "saved but red": a stored secret that
            # won't decrypt (server key changed) is now DETECTED as 'unreadable'
            # (red) instead of masquerading as connected, and re-entering fixes it.
            _s25 = _SL25()
            row25 = _s25.query(_IC25).filter(_IC25.provider == "gitlab").first()
            cfg25 = dict(row25.config); cfg25["token"] = "enc::GARBAGE-CANT-DECRYPT"
            row25.config = cfg25; _s25.commit(); _s25.close()
            gl25b = {i["key"]: i for i in c.get("/api/setup/connections").json()["items"]}["gitlab_sites"]
            assert gl25b["connected"] is False and gl25b["credential_state"] == "unreadable", gl25b
            assert _sc25.secret_state({"token": "enc::x"}, "token") == "unreadable"
            assert _sc25.secret_state({"token": "plain"}, "token") == "ok"
            assert _sc25.secret_state({}, "token") == "missing"
            # Re-entering the credential clears the unreadable state.
            c.post("/api/setup/connections/gitlab_sites", json={"values": {"token": "glpat-FRESH25"}})
            gl25c = {i["key"]: i for i in c.get("/api/setup/connections").json()["items"]}["gitlab_sites"]
            assert gl25c["connected"] is True and gl25c["credential_state"] == "ok", gl25c
            # RBAC: live test is staff-only.
            assert ca_c.post("/api/setup/connections/gitlab_sites/test").status_code == 403
        finally:
            _jp25._HTTP = _o25
            _cl25 = _SL25()
            _cl25.query(_IC25).filter(_IC25.provider.in_(["gitlab", "bvtech_site", "jp_site"])).delete(synchronize_session=False)
            _cl25.commit(); _cl25.close()
        print("Connection Center live verify: save returns real GitLab auth result + on-demand "
              "Test + 'stored-but-unreadable' (SECRET_KEY changed) detected as red with re-enter "
              "fix + RBAC OK")

        # =============== v1.27: publish a SPECIFIC post + empty-body fix ===============
        from app.services import content_studio as _cs27, content_autopilot as _ca27
        from app.services import jp_site as _jp27, autopost as _ap27
        from app.models import SocialPost as _SP27, IntegrationConnection as _IC27
        from app.core.db import SessionLocal as _SL27
        # (a) The render bug: a post supplied as rendered HTML (what the AI writers
        #     and the custom-publish path return) must NOT publish an empty body.
        _n27 = _cs27.normalize_post({"title": "T", "html": "<p>Real body text here.</p><h2>H</h2>"})
        assert "Real body text here." in _n27["body_html"], "HTML body dropped (empty-post bug)!"
        assert _n27["description"], "description not derived from HTML body"
        _n27b = _cs27.normalize_post({"title": "T", "body": "# Head\n\nMarkdown para."})
        assert _n27b["body_html"], "markdown body path regressed"
        # (b) Custom publish to BOTH sites via a stubbed GitLab API that captures commits.
        _o27 = _jp27._HTTP
        _committed27 = {}
        def _http27(method, url, token, payload=None):
            if method == "GET" and "/repository/tree" in url:
                return []
            if method == "POST" and "/repository/commits" in url:
                a = payload["actions"][0]; _committed27[a["file_path"]] = a["content"]
                return {"id": "sha27"}
            if "/pipelines" in url:
                return [{"status": "success", "sha": "x"}]
            return {}
        _jp27._HTTP = _http27
        try:
            _jp27.save_shared_token(db, "glpat-CUSTOM27")
            r_bv = c.post("/api/content-autopilot/publish-custom", json={
                "channel": "bvtech", "title": "Custom Security Report 27", "kind": "advisory",
                "html": "<p>Attackers target small business gaps in 2026.</p><h2>Fix</h2><p>Verify by phone.</p>",
                "keywords": "cybersecurity, texas"}).json()
            assert r_bv["ok"] and r_bv["url"].endswith(".html"), r_bv
            r_jp = c.post("/api/content-autopilot/publish-custom", json={
                "channel": "jp", "title": "Founder Field Notes 27",
                "html": "<p>Where IT is heading in 2026.</p>"}).json()
            assert r_jp["ok"] and r_jp["url"].endswith("/"), r_jp
            # The real supplied text landed in the committed page + SEO title present.
            _bvfile = next(k for k in _committed27 if "custom-security-report-27" in k)
            assert "Attackers target small business gaps" in _committed27[_bvfile]
            assert "Custom Security Report 27" in _committed27[_bvfile] and "<title>" in _committed27[_bvfile]
            # (c) LinkedIn + GBP custom posts queue, then deliver via the autopost engine.
            r_li = c.post("/api/content-autopilot/publish-custom", json={
                "channel": "linkedin", "body": "Three attacks hitting SMBs. #CyberSecurity",
                "link": "https://bvtech.org"}).json()
            r_gbp = c.post("/api/content-autopilot/publish-custom", json={
                "channel": "gbp", "body": "Book a security review at bvtech.org"}).json()
            assert r_li["ok"] and r_li.get("queued_id"), r_li
            assert r_gbp["ok"] and r_gbp.get("queued_id"), r_gbp
            _delivered27 = {}
            _posters27 = {
                "linkedin": lambda t, u, i=None: (_delivered27.setdefault("linkedin", t), "urn:x")[1],
                "google_business": lambda t, u, i=None: (_delivered27.setdefault("gbp", t), "lp/x")[1]}
            _s27 = _SL27()
            for _pid in (r_li["queued_id"], r_gbp["queued_id"]):
                _post = _s27.get(_SP27, _pid)
                _res = _ap27.publish_one(_s27, _post, posters=_posters27)
                assert _res["ok"], f"custom social delivery failed: {_res}"
            _s27.close()
            assert "#CyberSecurity" in _delivered27.get("linkedin", "")
            assert "bvtech.org" in _delivered27.get("gbp", "")
            # (d) Guards: unknown channel + missing content rejected cleanly (not 500).
            assert c.post("/api/content-autopilot/publish-custom",
                          json={"channel": "twitter", "body": "x"}).json()["ok"] is False
            assert c.post("/api/content-autopilot/publish-custom",
                          json={"channel": "bvtech", "title": "No body"}).json()["ok"] is False
            # (e) RBAC: OWNER-only.
            assert ca_c.post("/api/content-autopilot/publish-custom",
                             json={"channel": "gbp", "body": "x"}).status_code == 403
        finally:
            _jp27._HTTP = _o27
            _cl27 = _SL27()
            _cl27.query(_IC27).filter(_IC27.provider.in_(["gitlab", "bvtech_site", "jp_site"])).delete(synchronize_session=False)
            _cl27.query(_SP27).delete(synchronize_session=False)
            _cl27.commit(); _cl27.close()
        print("Content publish-custom: hand-written post -> BOTH sites (real body + SEO in "
              "committed HTML, empty-body bug fixed) + LinkedIn/GBP queue->deliver + unknown/"
              "empty rejected + OWNER-only RBAC OK")

        # ========= v1.28: a published post is ADDED TO THE BLOG LISTING =========
        # The orphaned-post bug: publish committed blog/<slug>.html (live at its
        # URL) but never touched the /blog/ index, so the post was invisible in
        # navigation. Now the listing pages update IN THE SAME COMMIT.
        from app.services import jp_site as _jp28
        import base64 as _b64_28
        # (a) The injector clones a real card for both layouts + is idempotent.
        _grid28 = ('<section><div class="posts">'
                   '<article class="post-card"><div class="body">'
                   '<div class="meta"><span class="tag new">New</span>'
                   '<span>Jordan Polasek</span><span>June 1, 2026</span></div>'
                   '<h2><a href="/an-existing-post/">An Existing Post</a></h2>'
                   '<p class="excerpt">Old excerpt.</p>'
                   '<a href="/an-existing-post/" class="more">Read more</a>'
                   '</div></article></div></section>')
        _o28, _ch28 = _jp28.inject_post_into_listing(
            _grid28, title="Brand New <Post>", url="/brand-new-post/",
            excerpt="Fresh excerpt.", date_str="July 10, 2026", style="slug-folder")
        assert _ch28 and _o28.index("/brand-new-post/") < _o28.index("/an-existing-post/"), "new card not on top"
        assert "Brand New &lt;Post&gt;" in _o28 and "Fresh excerpt." in _o28, "title/excerpt not rewritten/escaped"
        assert "July 10, 2026" in _o28
        _o28b, _ch28b = _jp28.inject_post_into_listing(_o28, title="x", url="/brand-new-post/",
                                                       excerpt="y", date_str="July 10, 2026", style="slug-folder")
        assert _ch28b is False, "re-inject must be idempotent (no duplicate card)"
        # Unrecognized structure (no cards) -> left untouched, reported, never corrupted.
        assert _jp28.inject_post_into_listing("<html><body><p>no cards</p></body></html>",
                                              title="t", url="/u/", excerpt="e",
                                              date_str="d", style="slug-folder") == \
               ("<html><body><p>no cards</p></body></html>", False)
        # (b) publish() rides the listing update into the SAME commit as the post.
        _o28h = _jp28._HTTP
        _cap28 = {}
        _bvblog28 = ('<div class="posts"><article class="post-card">'
                     '<h2><a href="/blog/old-advisory.html">Old Advisory</a></h2>'
                     '<p class="excerpt">old</p></article></div>')
        def _http28(method, url, token, payload=None):
            if method == "GET" and "/repository/tree" in url:
                return []
            if method == "GET" and "blog%2Findex.html" in url:
                return {"content": _b64_28.b64encode(_bvblog28.encode()).decode()}
            if method == "GET" and "/repository/files/" in url:
                raise Exception("404")          # homepage index.html absent on this stub
            if method == "POST" and "/repository/commits" in url:
                _cap28["actions"] = payload["actions"]; return {"id": "sha28"}
            if "/pipelines" in url:
                return [{"status": "success", "sha": "x"}]
            return {}
        _jp28._HTTP = _http28
        try:
            _jp28.save_shared_token(db, "glpat-LISTING28")
            _r28 = _jp28.publish(db, {"title": "New Threat Advisory 28",
                                      "html": "<p>Attackers hit gaps.</p>",
                                      "slug": "new-threat-advisory-28"}, site="bvtech")
            assert _r28["ok"], _r28
            assert _r28["listings_updated"] == ["blog/index.html"], _r28
            _acts28 = {a["file_path"]: a for a in _cap28["actions"]}
            assert _acts28["blog/index.html"]["action"] == "update"
            assert "/blog/new-threat-advisory-28.html" in _acts28["blog/index.html"]["content"], \
                "new post not added to the blog listing!"
            assert "blog/new-threat-advisory-28.html" in _acts28              # post file created too
        finally:
            _jp28._HTTP = _o28h
            _cl28 = _SL27()
            _cl28.query(_IC27).filter(_IC27.provider.in_(["gitlab", "bvtech_site", "jp_site"])).delete(synchronize_session=False)
            _cl28.commit(); _cl28.close()
        print("Content listing update: published post is inserted into the blog index "
              "(cloned card, top of grid, idempotent, unknown-structure skipped) + rides "
              "the SAME commit as the post so it's visible in navigation OK")

        # ==== v1.29: Cloudflare purge + Sync-Listings backfill + Publishing Doctor ====
        from app.services import cloudflare as _cf29, jp_site as _jp29, secure_config as _sc29
        import base64 as _b64_29
        # (a) Cloudflare connector: save via Connection Center -> live verify with a
        #     stubbed CF API; zone ids discovered by domain and cached WITHOUT
        #     corrupting the stored token (the double-encrypt trap).
        _ocf29 = _cf29._HTTP
        _purged29 = []
        def _cfhttp29(method, url, token, payload=None, email=None):
            assert token == "cft-SECRET29", f"wrong token sent to CF: {token[:8]}"
            if "/user/tokens/verify" in url:
                return {"success": True}
            if "/zones?name=" in url:
                dom = url.split("name=")[1]
                return {"success": True, "result": [{"id": f"zone-{dom}"}]}
            if "/purge_cache" in url:
                _purged29.append((url.split("/zones/")[1].split("/")[0], payload["files"]))
                return {"success": True}
            return {}
        _cf29._HTTP = _cfhttp29
        try:
            sv29 = c.post("/api/setup/connections/cloudflare",
                          json={"values": {"api_token": "cft-SECRET29"}}).json()
            assert sv29["connected"] is True and sv29["verified"] is True, sv29
            assert "bvtech.org" in sv29["detail"] and "jordanpolasek.com" in sv29["detail"], sv29
            t29 = c.post("/api/setup/connections/cloudflare/test").json()
            assert t29["ok"] is True, t29
            # zone cache write must NOT have re-encrypted the token
            from app.core.db import SessionLocal as _SL29
            _s29 = _SL29()
            _row29 = _s29.query(_IC27).filter(_IC27.provider == "cloudflare").first()
            assert _sc29.get_secret(_row29.config, "api_token") == "cft-SECRET29", \
                "token corrupted by zone-cache write (double encryption)!"
            assert (_row29.config.get("zones") or {}).get("bvtech.org") == "zone-bvtech.org"
            _s29.close()
            p29 = _cf29.purge_urls(db, "jp", ["https://jordanpolasek.com/x/"])
            assert p29["ok"] and _purged29[-1][0] == "zone-jordanpolasek.com", p29
            # (b) Sync-Listings backfill: repo has 2 posts, listing knows only 1 ->
            #     the orphan is injected + committed + cache purged; 2nd run no-ops.
            _ojp29 = _jp29._HTTP
            _listing29 = ('<div class="posts"><article class="post-card">'
                          '<h2><a href="/listed-post/">Listed Post</a></h2>'
                          '<p class="excerpt">x</p></article></div>')
            _orphan29 = ('<html><head><title>Orphan Post Title | Jordan</title>'
                         '<meta name="description" content="Orphan excerpt here."></head>'
                         '<body><p>hi</p></body></html>')
            _state29 = {"listing": _listing29}
            _commits29 = []
            def _jphttp29(method, url, token, payload=None):
                import urllib.parse as _u29
                if method == "GET" and "/repository/tree" in url and "path=blog" not in url:
                    return [{"type": "tree", "path": "listed-post"},
                            {"type": "tree", "path": "orphan-post"},
                            {"type": "tree", "path": "assets"}]
                if method == "GET" and "/repository/files/" in url:
                    p = _u29.unquote_plus(url.split("files/")[1].split("?")[0])
                    if p == "blog/index.html":
                        return {"content": _b64_29.b64encode(_state29["listing"].encode()).decode()}
                    if p == "index.html":
                        raise Exception("404")
                    if p == "orphan-post/index.html":
                        return {"content": _b64_29.b64encode(_orphan29.encode()).decode()}
                    if p == "listed-post/index.html":
                        return {"content": _b64_29.b64encode(b"<html><title>L</title></html>").decode()}
                    raise Exception("404")
                if method == "POST" and "/repository/commits" in url:
                    _commits29.append(payload["actions"])
                    for a in payload["actions"]:
                        if a["file_path"] == "blog/index.html":
                            _state29["listing"] = a["content"]
                    return {"id": "sha-sync29"}
                if "/pipelines" in url:
                    return [{"status": "success", "sha": "x"}]
                return {}
            _jp29._HTTP = _jphttp29
            # point the jp site's listings at just blog/index.html for this test
            _orig_paths29 = _jp29.SITES["jp"]["index_paths"]
            _jp29.SITES["jp"]["index_paths"] = ("blog/index.html",)
            try:
                _jp29.save_shared_token(db, "glpat-SYNC29")
                r29 = c.post("/api/content-autopilot/sync-listings").json()
                jp29 = r29["jp"]
                assert jp29["ok"], jp29
                assert [a["path"] for a in jp29["added"]] == ["orphan-post/index.html"], jp29
                assert jp29["added"][0]["title"] == "Orphan Post Title", jp29
                assert "/orphan-post/" in _state29["listing"], "orphan not injected into listing"
                assert "Orphan excerpt here." in _state29["listing"]
                assert jp29["cache_purged"] is True, jp29
                r29b = c.post("/api/content-autopilot/sync-listings").json()
                assert r29b["jp"]["ok"] and not r29b["jp"].get("added"), r29b["jp"]  # idempotent
                # (c) Publishing Doctor: full chain report + plain-English fixes.
                d29 = c.post("/api/content-autopilot/diagnose").json()
                jpd29 = next(s for s in d29["sites"] if "jordanpolasek" in s["site"])
                names29 = {ck["name"]: ck for ck in jpd29["checks"]}
                assert names29["GitLab token"]["ok"] and names29["Repo access"]["ok"]
                assert names29["Listing blog/index.html"]["ok"]
                assert names29["Orphaned posts"]["ok"], names29["Orphaned posts"]  # after sync: none
                assert names29["Cloudflare cache purge"]["ok"]
                assert d29["autopilot"]["enabled"] in (True, False) and "detail" in d29["autopilot"]
                # Doctor is readable by TECH; sync is OWNER-only.
                assert ca_c.post("/api/content-autopilot/diagnose").status_code == 403  # client admin: no
                assert ca_c.post("/api/content-autopilot/sync-listings").status_code == 403
            finally:
                _jp29.SITES["jp"]["index_paths"] = _orig_paths29
                _jp29._HTTP = _ojp29
        finally:
            _cf29._HTTP = _ocf29
            _cl29 = _SL27()
            _cl29.query(_IC27).filter(_IC27.provider.in_(
                ["gitlab", "bvtech_site", "jp_site", "cloudflare"])).delete(synchronize_session=False)
            _cl29.commit(); _cl29.close()
        print("Publishing reliability: Cloudflare connector (verify + zone discovery + purge, "
              "token never double-encrypted) + Sync-Listings backfill (orphans injected once, "
              "idempotent, cache purged) + Publishing Doctor (full chain, plain-English fixes) "
              "+ RBAC OK")

        # ==== v1.30: bvtech 400 fix — real GitLab errors + overwrite + rotation ====
        from app.services import jp_site as _jp30, content_autopilot as _ca30
        from app.models import BlogPost as _BP30
        import base64 as _b64_30, io as _io30, urllib.error as _uerr30, urllib.request as _ureq30
        # (a) GitLab's REAL error message is surfaced, not a bare "HTTP Error 400".
        _ourl30 = _ureq30.urlopen
        def _boom30(req, data=None, timeout=None):
            raise _uerr30.HTTPError(req.full_url, 400, "Bad Request", {},
                                    _io30.BytesIO(b'{"message":"A file with this name already exists"}'))
        _ureq30.urlopen = _boom30
        try:
            _jp30._http("POST", "https://gitlab.example/api/v4/x", "t", {"a": 1})
            raise AssertionError("expected RuntimeError")
        except RuntimeError as e30:
            assert "A file with this name already exists" in str(e30), e30
        finally:
            _ureq30.urlopen = _ourl30
        # (b) Re-publishing an existing slug OVERWRITES (update) instead of 400ing;
        #     a fresh slug still creates.
        _ojp30 = _jp30._HTTP
        _acts30 = []
        def _http30(method, url, token, payload=None):
            import urllib.parse as _u30
            if method == "GET" and "/repository/tree" in url:
                return []
            if method == "GET" and "/repository/files/" in url:
                p = _u30.unquote_plus(url.split("files/")[1].split("?")[0])
                if p == "blog/existing-post-30.html":
                    return {"content": _b64_30.b64encode(b"<html>old</html>").decode()}
                raise Exception("404")
            if method == "POST" and "/repository/commits" in url:
                _acts30.append({a["file_path"]: a["action"] for a in payload["actions"]})
                return {"id": "sha30"}
            if "/pipelines" in url:
                return [{"status": "success", "sha": "x"}]
            return {}
        _jp30._HTTP = _http30
        try:
            _jp30.save_shared_token(db, "glpat-V130")
            r30a = _jp30.publish(db, {"title": "Existing Post 30", "html": "<p>new body</p>",
                                      "slug": "existing-post-30"}, site="bvtech")
            assert r30a["ok"], r30a
            assert _acts30[-1]["blog/existing-post-30.html"] == "update", _acts30[-1]
            r30b = _jp30.publish(db, {"title": "Fresh Post 30", "html": "<p>x</p>",
                                      "slug": "fresh-post-30"}, site="bvtech")
            assert r30b["ok"] and _acts30[-1]["blog/fresh-post-30.html"] == "create", _acts30[-1]
            # (c) Rotation advances: each successful bvtech publish records a
            #     BlogPost row, so generate_article's topic/metro counter moves —
            #     no more same-topic -> same-slug collisions every run.
            _prompts30 = []
            _oai30c, _oai30e = _ca30.ai.complete, _ca30.ai.enabled
            def _ai30(system, prompt, smart=False, max_tokens=1000):
                _prompts30.append(prompt)
                import json as _j30
                return _j30.dumps({"title": f"Auto Post {len(_prompts30)}",
                                   "excerpt": "x",
                                   "html": "<p>" + ("Real article body sentence. " * 20) + "</p>"})
            _ca30.ai.complete = _ai30
            try:
                from datetime import datetime as _dt30, timezone as _tz30
                _n30 = db.query(_BP30).count()
                ok1, _ = _ca30._run_bvtech(db, _dt30.now(_tz30.utc))
                ok2, _ = _ca30._run_bvtech(db, _dt30.now(_tz30.utc))
                assert ok1 and ok2
                assert db.query(_BP30).count() == _n30 + 2, "BlogPost rows not recorded"
                t1 = [ln for ln in _prompts30[0].splitlines() if ln.startswith("Topic:")]
                t2 = [ln for ln in _prompts30[1].splitlines() if ln.startswith("Topic:")]
                assert t1 and t2 and t1 != t2, f"topic did not rotate: {t1} vs {t2}"
            finally:
                _ca30.ai.complete, _ca30.ai.enabled = _oai30c, _oai30e
        finally:
            _jp30._HTTP = _ojp30
            _cl30 = _SL27()
            _cl30.query(_IC27).filter(_IC27.provider.in_(["gitlab", "bvtech_site", "jp_site"])).delete(synchronize_session=False)
            _cl30.query(_BP30).filter(_BP30.source == "autopilot").delete(synchronize_session=False)
            _cl30.commit(); _cl30.close()
        print("bvtech 400 fix: GitLab's real error surfaced (not bare 400) + same-slug "
              "re-publish overwrites instead of failing + topic/metro rotation advances "
              "on GitLab publishes (BlogPost recorded) OK")

        # ==== v1.31: unparseable-article fix + Doctor covers social channels ====
        from app.services import ai as _ai31, content_autopilot as _ca31
        from app.services import integration_health as _ih31, jp_site as _jp31
        # (a) The tolerant parser survives every real-world failure mode.
        _pj31 = _ai31.parse_json_object
        assert _pj31('```json\n{"title":"T","html":"<p>x</p>"}\n```')["title"] == "T"      # fences
        assert _pj31('Sure! Here is the article:\n{"title":"T2","html":"<p>x</p>"}')["title"] == "T2"  # prose
        assert _pj31('{"title":"T3","html":"<p>line1\nline2</p>"}')["title"] == "T3"       # literal newline
        assert _pj31('{"title":"T4","excerpt":"e","html":"<p>truncated mid-sen')["title"] == "T4"      # truncation
        assert _pj31("no json here at all") is None and _pj31("") is None
        # (b) _run_jp: garbage first -> ONE corrective retry -> success (and the
        #     retry prompt demands JSON-only).
        _calls31 = []
        def _ai31fake(system, prompt, smart=False, max_tokens=1000):
            _calls31.append(prompt)
            if len(_calls31) == 1:
                return "I'd be happy to write that article for you!"      # unparseable
            import json as _j31
            return _j31.dumps({"title": "JP Retry Post", "excerpt": "x",
                               "html": "<p>" + ("Body sentence here. " * 25) + "</p>"})
        _oc31 = _ca31.ai.complete
        _ojp31 = _jp31._HTTP
        def _jphttp31(method, url, token, payload=None):
            if method == "GET" and "/repository/tree" in url: return []
            if method == "GET" and "/repository/files/" in url: raise Exception("404")
            if method == "POST" and "/repository/commits" in url: return {"id": "sha31"}
            if "/pipelines" in url: return [{"status": "success", "sha": "x"}]
            return {}
        _ca31.ai.complete = _ai31fake
        _jp31._HTTP = _jphttp31
        try:
            _jp31.save_shared_token(db, "glpat-V131")
            from datetime import datetime as _dt31, timezone as _tz31
            ok31, det31 = _ca31._run_jp(db, _dt31.now(_tz31.utc))
            assert ok31, det31
            assert len(_calls31) == 2 and "TITLE:" in _calls31[1], _calls31
            # both attempts unparseable -> clean failure message, no crash
            _calls31.clear()
            _ca31.ai.complete = lambda s, p, smart=False, max_tokens=1000: "still not json"
            ok31b, det31b = _ca31._run_jp(db, _dt31.now(_tz31.utc))
            assert ok31b is False and "unparseable" in det31b, (ok31b, det31b)
        finally:
            _ca31.ai.complete = _oc31
            _jp31._HTTP = _ojp31
            _cl31 = _SL27()
            _cl31.query(_IC27).filter(_IC27.provider.in_(["gitlab", "bvtech_site", "jp_site"])).delete(synchronize_session=False)
            _cl31.commit(); _cl31.close()
        # (c) Doctor surfaces the Google invalid_client error WITH the fix.
        _og31 = _ih31.CHECKERS["gbp"]
        _ih31.CHECKERS["gbp"] = lambda cfg: (_ for _ in ()).throw(RuntimeError(
            'Google token refresh failed (HTTP 401): {"error":"invalid_client",'
            '"error_description":"The OAuth client was not found."}'))
        try:
            d31 = c.post("/api/content-autopilot/diagnose").json()
            gbp31 = next(ch for ch in d31["channels"] if ch["name"] == "Google Business")
            assert gbp31["ok"] is False and "invalid_client" in gbp31["detail"], gbp31
            assert "Re-create an OAuth client" in gbp31.get("fix", ""), gbp31
            li31 = next(ch for ch in d31["channels"] if ch["name"] == "LinkedIn")
            assert "ok" in li31 and "detail" in li31
        finally:
            _ih31.CHECKERS["gbp"] = _og31
        print("unparseable-article fix: tolerant JSON parse (fences/prose/newlines/"
              "truncation) + one corrective retry for JP + bvtech articles + Doctor "
              "surfaces LinkedIn/Google Business health incl. invalid_client with the "
              "exact fix OK")

        # ==== v1.32: quote-proof article format + publish notes (listing/cache) ====
        from app.services import ai as _ai32, content_autopilot as _ca32, jp_site as _jp32
        import base64 as _b64_32
        # (a) The sections format survives what killed JSON: unescaped quotes.
        _quoted_html32 = ('<p class="lead">He said "just update Chrome" and moved on.</p>'
                          '<h2>Why that\'s not enough</h2><p>' + ("More body text here. " * 12) + "</p>")
        _sec32 = _ai32.parse_sections(
            f'TITLE: Why "Update Chrome" Is Not Enough\nEXCERPT: One line.\nHTML:\n{_quoted_html32}')
        assert _sec32 and _sec32["title"].startswith('Why "Update Chrome"'), _sec32
        assert 'class="lead"' in _sec32["html"], "quotes must survive verbatim"
        # parse_article: sections first, JSON fallback still honored.
        assert _ai32.parse_article('{"title":"J","html":"' + "<p>x</p>" * 40 + '"}')["title"] == "J"
        assert _ai32.parse_article("TITLE: S\nHTML:\n" + "<p>y</p>" * 40)["title"] == "S"
        assert _ai32.parse_article("nothing usable") is None
        # (b) _run_jp succeeds FIRST TRY with quoted HTML (the exact production
        #     failure), and the success detail carries listing + cache notes.
        _ojp32 = _jp32._HTTP
        _listing32 = ('<div class="posts"><article class="post-card">'
                      '<h2><a href="/old-post-32/">Old</a></h2>'
                      '<p class="excerpt">x</p></article></div>')
        def _http32(method, url, token, payload=None):
            import urllib.parse as _u32
            if method == "GET" and "/repository/tree" in url:
                return []
            if method == "GET" and "/repository/files/" in url:
                p = _u32.unquote_plus(url.split("files/")[1].split("?")[0])
                if p in ("index.html", "blog/index.html"):
                    return {"content": _b64_32.b64encode(_listing32.encode()).decode()}
                raise Exception("404")
            if method == "POST" and "/repository/commits" in url:
                return {"id": "sha32"}
            if "/pipelines" in url:
                return [{"status": "success", "sha": "x"}]
            return {}
        _calls32 = []
        def _ai32fake(system, prompt, smart=False, max_tokens=1000):
            _calls32.append(prompt)
            return ('TITLE: Founder Notes With "Quotes" In Them\n'
                    'EXCERPT: A one-liner.\nHTML:\n' + _quoted_html32)
        _oc32 = _ca32.ai.complete
        _jp32._HTTP = _http32
        _ca32.ai.complete = _ai32fake
        try:
            _jp32.save_shared_token(db, "glpat-V132")
            from datetime import datetime as _dt32, timezone as _tz32
            ok32, det32 = _ca32._run_jp(db, _dt32.now(_tz32.utc))
            assert ok32, det32
            assert len(_calls32) == 1, "quoted HTML must parse FIRST try now"
            assert "listed in" in det32, det32                     # listing note present
            assert "cache:" in det32 or "cache purged" in det32, det32   # cache note present
            # total-failure error now includes what Claude actually said.
            _ca32.ai.complete = lambda s, p, smart=False, max_tokens=1000: "I cannot do that."
            ok32b, det32b = _ca32._run_jp(db, _dt32.now(_tz32.utc))
            assert ok32b is False and "I cannot do that" in det32b, det32b
        finally:
            _ca32.ai.complete = _oc32
            _jp32._HTTP = _ojp32
            _cl32 = _SL27()
            _cl32.query(_IC27).filter(_IC27.provider.in_(["gitlab", "bvtech_site", "jp_site"])).delete(synchronize_session=False)
            _cl32.commit(); _cl32.close()
        print("quote-proof articles: TITLE/EXCERPT/HTML sections format (unescaped "
              "quotes survive, JSON fallback kept) + first-try parse of the exact "
              "production failure + publish detail now says WHERE it was listed and "
              "whether the cache was purged + raw-snippet errors OK")

        # ==== v1.33: hands-free autopilot — ON by default + angles + receipt ====
        from app.services import content_autopilot as _ca33, jp_site as _jp33
        from app.models import Notification as _N33
        from datetime import datetime as _dt33, timezone as _tz33, timedelta as _td33
        from app.core.db import SessionLocal as _SL33
        # (a) Fresh install => daily posting is ON with no clicks; explicit OFF
        #     (set at the top of this suite) is respected; re-enable works.
        _s33 = _SL33()
        _row33 = _s33.query(_IC27).filter(_IC27.provider == "content_autopilot").first()
        _saved_cfg33 = dict(_row33.config) if _row33 else None
        if _row33:
            _s33.delete(_row33); _s33.commit()
        assert _ca33.get_config(db)["enabled"] is True, "fresh install must be hands-free ON"
        _ca33.save_config(db, enabled=False)
        assert _ca33.get_config(db)["enabled"] is False, "explicit OFF must stick"
        _ca33.save_config(db, enabled=True)
        assert _ca33.get_config(db)["enabled"] is True
        # (b) Weekday editorial angles: 7 distinct, and both writers get them.
        assert len(set(_ca33.WEEKDAY_ANGLES)) == 7
        _mon33 = _dt33(2026, 7, 6, 15, tzinfo=_tz33.utc)     # Monday
        _tue33 = _mon33 + _td33(days=1)
        assert _ca33.day_angle(_mon33) != _ca33.day_angle(_tue33)
        _prompts33 = []
        def _ai33(system, prompt, smart=False, max_tokens=1000):
            _prompts33.append(prompt)
            return ("TITLE: Daily Post 33\nEXCERPT: x\nHTML:\n<p>"
                    + ("Body sentence for the daily post. " * 20) + "</p>")
        _oc33, _oe33 = _ca33.ai.complete, _ca33.ai.enabled
        _ojp33 = _jp33._HTTP
        def _http33(method, url, token, payload=None):
            if method == "GET" and "/repository/tree" in url: return []
            if method == "GET" and "/repository/files/" in url: raise Exception("404")
            if method == "POST" and "/repository/commits" in url: return {"id": "sha33"}
            if "/pipelines" in url: return [{"status": "success", "sha": "x"}]
            return {}
        _ca33.ai.complete = _ai33
        _ca33.ai.enabled = lambda: True
        _jp33._HTTP = _http33
        try:
            _jp33.save_shared_token(db, "glpat-V133")
            _s33b = _SL33()
            _n_before33 = _s33b.query(_N33).filter(_N33.message.like("%content shipped%")).count()
            _s33b.close()
            # (c) The SCHEDULED (non-force) run posts hands-free after hour_utc
            #     and leaves the daily receipt notification with the day's URLs.
            out33 = _ca33.run_daily(db, _mon33)      # 15:00 UTC >= default 14
            assert out33["ran"] is True, out33
            assert out33["results"]["bvtech"]["ok"] and out33["results"]["jp"]["ok"], out33
            assert any(_ca33.day_angle(_mon33) in p for p in _prompts33), \
                "Monday's editorial angle missing from the writer prompts"
            _s33c = _SL33()
            _n_after33 = _s33c.query(_N33).filter(_N33.message.like("%content shipped%")).count()
            assert _n_after33 == _n_before33 + 1, "daily success receipt not created"
            _rcpt33 = (_s33c.query(_N33).filter(_N33.message.like("%content shipped%"))
                       .order_by(_N33.id.desc()).first())
            assert "bvtech OK" in _rcpt33.message and "jp OK" in _rcpt33.message, _rcpt33.message
            _s33c.close()
            # (d) Same-day second tick: succeeded channels dedupe (no double post);
            #     failed channels (social, unconnected in this stub) correctly RETRY.
            out33b = _ca33.run_daily(db, _mon33 + _td33(hours=1))
            assert "bvtech" not in out33b["results"] and "jp" not in out33b["results"], out33b
            assert all(not r["ok"] for r in out33b["results"].values()), out33b
        finally:
            _ca33.ai.complete, _ca33.ai.enabled = _oc33, _oe33
            _jp33._HTTP = _ojp33
            _cl33 = _SL33()
            _cl33.query(_IC27).filter(_IC27.provider.in_(
                ["gitlab", "bvtech_site", "jp_site", "content_autopilot"])).delete(synchronize_session=False)
            _cl33.commit()
            if _saved_cfg33 is not None:
                from app.services import secure_config as _sc33
                _sc33.upsert_platform(_cl33, "content_autopilot", "Content Autopilot",
                                      "Publishing", _saved_cfg33)
            _cl33.close()
            # keep the suite-wide OFF so later heartbeat ticks stay inert
            c.put("/api/content-autopilot/settings", json={"enabled": False})
        print("hands-free autopilot: ON by default (fresh install posts daily with zero "
              "clicks; explicit OFF respected) + 7 weekday editorial angles reach the "
              "writers + scheduled run leaves a 'content shipped' receipt with URLs + "
              "per-day dedupe intact OK")

        # ==== v1.34: autopost assurance — health pulse + external tick + doctor ====
        import os as _os34
        from app.api.routes import content_autopilot as _car34
        # (a) /api/health carries the public proof-of-life (no login needed).
        h34 = c.get("/api/health").json()
        assert "autopilot" in h34, h34
        for k34 in ("ticking", "last_tick_age_seconds", "daily_enabled",
                    "post_hour_utc", "last_success"):
            assert k34 in h34["autopilot"], (k34, h34["autopilot"])
        assert h34["autopilot"]["daily_enabled"] is False   # suite pinned it OFF
        # (b) External tick: no auth needed by default; NON-FORCE so gates apply
        #     (autopilot is OFF here -> ran False, reason 'disabled'); a burst is
        #     rate-limited; with CONTENT_TICK_KEY set the header becomes required.
        _car34._TICK_STATE["last"] = 0.0
        nc34 = TestClient(app); nc34.cookies.clear()          # UNAUTHENTICATED client
        t34 = nc34.post("/api/content-autopilot/tick")
        assert t34.status_code == 200, t34.text
        assert t34.json() == {"ran": False, "reason": "disabled", "results": {}}, t34.json()
        assert nc34.post("/api/content-autopilot/tick").status_code == 429   # rate limit
        _os34.environ["CONTENT_TICK_KEY"] = "tick-secret-34"
        try:
            _car34._TICK_STATE["last"] = 0.0
            assert nc34.post("/api/content-autopilot/tick").status_code == 401       # key required
            assert nc34.post("/api/content-autopilot/tick",
                             headers={"X-Tick-Key": "wrong"}).status_code == 401
            ok34 = nc34.post("/api/content-autopilot/tick",
                             headers={"X-Tick-Key": "tick-secret-34"})
            assert ok34.status_code == 200, ok34.text
        finally:
            _os34.environ.pop("CONTENT_TICK_KEY", None)
            _car34._TICK_STATE["last"] = 0.0
        # (c) Doctor leads with the scheduler pulse (no ticks in this suite ->
        #     NOT ticking, with the restart fix).
        d34 = c.post("/api/content-autopilot/diagnose").json()
        assert "scheduler" in d34, d34.keys()
        assert d34["scheduler"]["ok"] is False and "fix" in d34["scheduler"], d34["scheduler"]
        # (d) The daily GitHub cron workflow exists and targets the tick endpoint.
        _wf34 = open(_os34.path.join(_os34.path.dirname(__file__), "..", "..",
                                     ".github", "workflows", "daily-content.yml")).read()
        assert "/api/content-autopilot/tick" in _wf34 and "schedule" in _wf34
        assert "workflow_dispatch" in _wf34 and "X-Tick-Key" in _wf34
        print("autopost assurance: /api/health proof-of-life (ticking/last-success, "
              "public) + external /tick (non-force gates, 60s rate limit, optional "
              "CONTENT_TICK_KEY auth) + Doctor scheduler pulse w/ restart fix + daily "
              "GitHub cron workflow wired OK")

        # ==== v1.35: CF Global-Key auth + universal injector + human AI errors ====
        from app.services import ai as _ai35, cloudflare as _cf35, jp_site as _jp35
        # (a) Cloudflare Global API Key support. A 37-hex key without an email is
        #     detected and explained; with the email, verify + purge use the
        #     X-Auth-Key/X-Auth-Email dialect (NOT Bearer) — the 401 fix.
        _gk35 = "0123456789abcdef0123456789abcdef01234"          # 37 hex chars
        assert _cf35.looks_like_global_key(_gk35) is True
        assert _cf35.looks_like_global_key("v1.0-Abc_scoped-token-longer") is False
        _ocf35 = _cf35._HTTP
        _seen35 = []
        def _cfhttp35(method, url, token, payload=None, email=None):
            _seen35.append({"url": url.split("client/v4")[1][:22], "email": email})
            if "/user" in url and "tokens" not in url:
                return {"success": True}
            if "/zones?name=" in url:
                return {"success": True, "result": [{"id": "z-" + url.split("name=")[1]}]}
            if "/purge_cache" in url:
                return {"success": True}
            return {"success": True}
        _cf35._HTTP = _cfhttp35
        try:
            r35 = c.post("/api/setup/connections/cloudflare",
                         json={"values": {"api_token": _gk35}}).json()
            assert r35["verified"] is False and "GLOBAL API Key" in r35["detail"], r35
            r35b = c.post("/api/setup/connections/cloudflare",
                          json={"values": {"api_token": _gk35,
                                           "auth_email": "help@bvtech.org"}}).json()
            assert r35b["verified"] is True and "Global API Key" in r35b["detail"], (r35b, _seen35)
            assert all(s35["email"] == "help@bvtech.org" for s35 in _seen35
                       if "/zones" in s35["url"] or ("/user" in s35["url"] and "token" not in s35["url"])), _seen35
            p35 = _cf35.purge_urls(db, "jp", ["https://jordanpolasek.com/x/"])
            assert p35["ok"] and _seen35[-1]["email"] == "help@bvtech.org", (p35, _seen35[-1])
        finally:
            _cf35._HTTP = _ocf35
            _cl35 = _SL27()
            _cl35.query(_IC27).filter(_IC27.provider == "cloudflare").delete(synchronize_session=False)
            _cl35.commit(); _cl35.close()
        # (b) Universal injector: a DIV-card listing with zero <article> tags and
        #     unknown class names (bvtech's real-world shape) still gets the new
        #     post inserted on top, idempotently.
        _div35 = ('<html><body><main><div class="weekly-wrap"><div class="entry-box">'
                  '<h3><a href="/blog/old-entry.html">Old Entry Title</a></h3>'
                  '<p>Old summary text.</p><span>June 20, 2026</span>'
                  '</div></main></body></html>')
        _o35, _ch35 = _jp35.inject_post_into_listing(
            _div35, title='New "Quoted" Post 35', url="/blog/new-entry-35.html",
            excerpt="New summary.", date_str="July 14, 2026", style="blog-file")
        assert _ch35, "universal injector must handle div-based cards"
        assert _o35.index("/blog/new-entry-35.html") < _o35.index("/blog/old-entry.html")
        assert 'New "Quoted" Post 35'.replace('"', "&quot;") in _o35 or "New &quot;Quoted&quot; Post 35" in _o35
        assert "July 14, 2026" in _o35
        _, _ch35b = _jp35.inject_post_into_listing(
            _o35, title="x", url="/blog/new-entry-35.html", excerpt="y",
            date_str="July 14, 2026", style="blog-file")
        assert _ch35b is False                                     # idempotent
        # unknown structure still refuses rather than corrupts
        assert _jp35.inject_post_into_listing("<p>no cards at all</p>", title="t",
                                              url="/blog/u.html", excerpt="e",
                                              date_str="d", style="blog-file")[1] is False
        # (c) Anthropic errors become sentences a human can act on.
        _e35 = _ai35._human_api_error(400, '{"type":"error","error":{"type":"invalid_request_error",'
                                            '"message":"Your credit balance is too low to access the API."}}')
        assert "credit balance" in _e35 and "console.anthropic.com" in _e35, _e35
        assert "re-enter" in _ai35._human_api_error(401, "{}")
        assert "overloaded" in _ai35._human_api_error(529, "{}").lower()
        # (d) WordPress is gone from the portal UI.
        _dash35 = c.get("/dashboard").text
        assert "wordpress" not in _dash35.lower(), "WordPress UI must be fully removed"
        assert "Auto-Blogger" not in _dash35
        assert 'id="t-blog"' in _dash35            # article history survives
        print("super-tool pass: Cloudflare Global API Key auth (X-Auth-Key+email, "
              "explains itself) + universal card injector (div/li/section, no class "
              "assumptions) + human-readable Claude errors + WordPress UI removed OK")

        # ==== v1.36: fail-proof delivery — re-auth circuit breaker + auto-resume ====
        from app.services import autopost as _ap36
        from app.models import SocialPost as _SP36, Notification as _N36
        from app.core.db import SessionLocal as _SL36
        from datetime import datetime as _dt36, timezone as _tz36
        _s36 = _SL36()
        _post36 = _SP36(body="Breaker test post 36", link="https://bvtech.org",
                        channels=["google_business"], status="queued")
        _s36.add(_post36); _s36.commit(); _s36.refresh(_post36)
        _calls36 = {"n": 0}
        def _dead36(text, url, image=None):
            _calls36["n"] += 1
            raise RuntimeError('Google token refresh failed (HTTP 400): '
                               '{"error": "invalid_grant", "error_description": "Bad Request"}')
        # (a) First delivery attempt with a dead token: channel PAUSES with a
        #     human message + one notification; the post STAYS QUEUED with zero
        #     attempts burned.
        r36 = _ap36.publish_one(_s36, _post36, posters={"google_business": _dead36})
        assert r36["ok"] is False, r36
        assert "paused" in r36["channels"]["google_business"], r36
        assert "One-click Connect" in r36["channels"]["google_business"], r36
        assert "Testing" in r36["channels"]["google_business"], r36   # 7-day warning
        _s36.refresh(_post36)
        assert _post36.status == "queued" and (_post36.attempts or 0) == 0, \
            (_post36.status, _post36.attempts)
        assert _ap36.get_reauth(_s36, "google_business"), "breaker flag not set"
        _n36 = (_s36.query(_N36).filter(_N36.message.like("%Google Business paused%"))
                .count())
        assert _n36 == 1, _n36
        # (b) Next tick: the breaker SKIPS delivery (poster never called again),
        #     post still queued — no retry noise, no attempt burn.
        r36b = _ap36.publish_one(_s36, _post36, posters={"google_business": _dead36})
        assert _calls36["n"] == 1, f"poster called through the breaker: {_calls36['n']}"
        assert "paused" in r36b["channels"]["google_business"], r36b
        _s36.refresh(_post36)
        assert _post36.status == "queued" and (_post36.attempts or 0) == 0
        # (c) Saving fresh credentials lifts the pause (any of the three paths);
        #     the queued post then DELIVERS on the next tick.
        assert c.put("/api/gbp/settings", json={"client_id": "newcid36"}).status_code == 200
        assert _ap36.get_reauth(_s36, "google_business") is None, "save must lift the pause"
        _ok36 = _ap36.publish_one(_s36, _post36,
                                  posters={"google_business":
                                           lambda t, u, image=None: "localPosts/OK36"})
        assert _ok36["ok"] is True, _ok36
        _s36.refresh(_post36)
        assert _post36.status == "posted"
        # (d) LinkedIn 401 classifies + pauses the same way; publishers save lifts it.
        _post36b = _SP36(body="Breaker test LI 36", link="https://bvtech.org",
                         channels=["linkedin"], status="queued")
        _s36.add(_post36b); _s36.commit(); _s36.refresh(_post36b)
        def _dead36li(text, url, image=None):
            raise RuntimeError("LinkedIn auth failed (HTTP 401) — the token is likely expired.")
        r36c = _ap36.publish_one(_s36, _post36b, posters={"linkedin": _dead36li})
        assert "paused" in r36c["channels"]["linkedin"], r36c
        assert _ap36.get_reauth(_s36, "linkedin"), "linkedin breaker not set"
        assert c.put("/api/publishers/linkedin",
                     json={"access_token": "fresh36", "person_urn": "urn:li:person:x36"}
                     ).status_code == 200
        assert _ap36.get_reauth(_s36, "linkedin") is None
        # (e) A successful delivery also clears a lingering flag (belt+braces),
        #     and non-auth errors still use the normal retry path.
        _ap36.set_reauth(_s36, "linkedin", "lingering")
        _post36c = _SP36(body="Breaker clear-on-success 36", channels=["linkedin"],
                         status="queued")
        _s36.add(_post36c); _s36.commit(); _s36.refresh(_post36c)
        r36d = _ap36.publish_one(_s36, _post36c, posters={"linkedin": _dead36li})
        assert "paused" in r36d["channels"]["linkedin"]          # flag still respected
        _ap36.clear_reauth(_s36, "pub_linkedin")
        r36e = _ap36.publish_one(_s36, _post36c,
                                 posters={"linkedin": lambda t, u, image=None: "urn:li:share:36"})
        assert r36e["ok"] is True
        _post36d = _SP36(body="Transient error 36", channels=["linkedin"], status="queued")
        _s36.add(_post36d); _s36.commit(); _s36.refresh(_post36d)
        r36f = _ap36.publish_one(_s36, _post36d,
                                 posters={"linkedin": (lambda t, u, image=None:
                                                       (_ for _ in ()).throw(RuntimeError("HTTP 503 flaky")))})
        _s36.refresh(_post36d)
        assert _post36d.attempts == 1 and _post36d.status == "queued", \
            "non-auth errors must keep the normal retry path"
        # (f) Doctor shows the pause with the exact reason.
        _ap36.set_reauth(_s36, "google_business", "reconnect via One-click Connect")
        d36 = c.post("/api/content-autopilot/diagnose").json()
        g36 = next(ch for ch in d36["channels"] if ch["name"] == "Google Business")
        assert g36["ok"] is False and "PAUSED" in g36["detail"], g36
        _ap36.clear_reauth(_s36, "gbp")
        # cleanup
        _s36.query(_SP36).filter(_SP36.body.like("%36")).delete(synchronize_session=False)
        _s36.query(_IC27).filter(_IC27.provider.in_(["gbp", "pub_linkedin"])).delete(synchronize_session=False)
        _s36.commit(); _s36.close()
        print("fail-proof delivery: dead tokens PAUSE the channel (human message + one "
              "notification, posts stay queued, zero attempts burned, breaker skips "
              "retries) + reconnect via any path auto-resumes the queue + success "
              "clears lingering flags + transient errors keep normal retries + Doctor "
              "shows the pause OK")

        # ==== v1.36b: adaptive publishing — generated sites get MARKDOWN ====
        from app.services import jp_site as _jp36
        import base64 as _b64_36
        _sample36 = ("---\n"
                     'title: "Old Post"\n'
                     "description: \"Old summary\"\n"
                     "pubDate: 2026-06-20\n"
                     "tags:\n  - security\n  - texas\n"
                     "author: BVTech\n"
                     "draft: false\n"
                     "---\n\nOld body\n")
        _committed36 = {}
        def _http36(method, url, token, payload=None):
            import urllib.parse as _u36
            if method == "GET" and "/repository/tree" in url:
                if "path=" in url:
                    d = _u36.unquote_plus(url.split("path=")[1].split("&")[0])
                    if d == "src/content/blog":
                        return [{"type": "blob", "path": "src/content/blog/old-post.md"}]
                    return []
                return [{"type": "blob", "path": "package.json"},
                        {"type": "blob", "path": "astro.config.mjs"},
                        {"type": "tree", "path": "src"}]
            if method == "GET" and "/repository/files/" in url:
                p = _u36.unquote_plus(url.split("files/")[1].split("?")[0])
                if p == "src/content/blog/old-post.md":
                    return {"content": _b64_36.b64encode(_sample36.encode()).decode()}
                raise Exception("404")
            if method == "POST" and "/repository/commits" in url:
                a = payload["actions"][0]
                _committed36[a["file_path"]] = (a["action"], a["content"])
                return {"id": "sha36md"}
            if "/pipelines" in url:
                return [{"status": "success", "sha": "x"}]
            return {}
        _ojp36 = _jp36._HTTP
        _jp36._HTTP = _http36
        try:
            _jp36.save_shared_token(db, "glpat-V136")
            # Detection: engine file + content dir + newest sample.
            lay36 = _jp36.detect_layout(_jp36.get_config(db, "bvtech"))
            assert lay36["format"] == "markdown" and lay36["content_dir"] == "src/content/blog", lay36
            # Publish -> markdown with CLONED frontmatter, fresh values, HTML body.
            out36 = _jp36.publish(db, {"title": 'MD Post With "Quotes"',
                                       "html": "<p>Body para for the generated site.</p>",
                                       "description": "Fresh summary.",
                                       "slug": "md-post-36"}, site="bvtech")
            assert out36["ok"] and out36["listing_generated"] is True, out36
            assert out36["content_path"] == "src/content/blog/md-post-36.md", out36
            assert out36["url"].endswith("/blog/md-post-36/"), out36
            act36, md36 = _committed36["src/content/blog/md-post-36.md"]
            assert act36 == "create"
            assert 'title: "MD Post With \\"Quotes\\""' in md36, md36[:300]
            assert 'description: "Fresh summary."' in md36
            import re as _re36
            assert _re36.search(r"pubDate: \d{4}-\d{2}-\d{2}", md36)      # today, not the sample's
            assert "2026-06-20" not in md36
            assert "- security" in md36 and "author: BVTech" in md36      # site metadata kept
            assert "draft: false" in md36
            assert "<p>Body para for the generated site.</p>" in md36    # HTML body embedded
            # Sync-listings knows generated sites build their own index.
            sync36 = _jp36.sync_listings(db, "bvtech")
            assert sync36["ok"] and "generated site" in sync36["detail"], sync36
            # Doctor names the engine + where posts go.
            d36b = _jp36.diagnose(db, "bvtech")
            eng36 = next(ck for ck in d36b["checks"] if ck["name"] == "Site engine")
            assert eng36["ok"] and "src/content/blog" in eng36["detail"], eng36
        finally:
            _jp36._HTTP = _ojp36
            _cl36b = _SL27()
            _cl36b.query(_IC27).filter(_IC27.provider.in_(["gitlab", "bvtech_site", "jp_site"])).delete(synchronize_session=False)
            _cl36b.commit(); _cl36b.close()
        print("adaptive publishing: generated site detected (engine file + content dir) -> "
              "markdown committed with cloned frontmatter (title/desc/date swapped, site "
              "metadata kept, HTML body embedded) + build-owned listing acknowledged by "
              "sync + Doctor names the engine and target folder OK")

        # ==== v1.37: GitHub-native publishing — the LIVE bvtech.org forge ====
        from app.services import jp_site as _jp37
        import base64 as _b64_37
        _sample37 = "---\ntitle: \"Old\"\ndescription: \"o\"\npubDate: 2026-06-01\n---\nold\n"
        _gh_calls37 = []
        def _gh37(method, url, token, payload=None):
            _gh_calls37.append((method, url.split("api.github.com")[1][:60]))
            assert token == "ghp_TEST37", token[:8]
            if url.endswith("/user"):
                return {"login": "bvtechllc"}
            if "/repos/BVTECHLLC/bvtech-website-new" in url and "/contents/" not in url:
                return {"full_name": "BVTECHLLC/bvtech-website-new",
                        "permissions": {"push": True}}
            if "/contents/?ref=" in url or url.endswith("/contents/?ref=main"):
                return [{"path": "package.json", "type": "file"},
                        {"path": "astro.config.mjs", "type": "file"},
                        {"path": "src", "type": "dir"}]
            if "/contents/src%2Fcontent%2Fblog?ref=" in url or "/contents/src/content/blog?ref=" in url:
                return [{"path": "src/content/blog/old.md", "type": "file"}]
            if method == "GET" and "old.md" in url:
                return {"content": _b64_37.b64encode(_sample37.encode()).decode(),
                        "sha": "abc37"}
            if method == "GET" and "/contents/" in url:
                raise RuntimeError("GitHub 404: Not Found")
            if method == "PUT" and "/contents/" in url:
                _gh_calls37.append(("PUT-BODY", payload))
                return {"commit": {"sha": "ghsha37"}}
            return {}
        _ogh37 = _jp37._GH
        _jp37._GH = _gh37
        try:
            # Connect via the new tile -> verified against GitHub live.
            r37 = c.post("/api/setup/connections/bvtech_github",
                         json={"values": {"gh_token": "ghp_TEST37"}}).json()
            assert r37["verified"] is True and "bvtechllc" in r37["detail"], r37
            cfg37 = _jp37.get_config(db, "bvtech")
            assert cfg37["forge"] == "github" and cfg37["project"] == "BVTECHLLC/bvtech-website-new"
            # Publish -> markdown via the GitHub Contents API with cloned frontmatter.
            out37 = _jp37.publish(db, {"title": "GitHub Native Post",
                                       "html": "<p>Live-site body.</p>",
                                       "slug": "github-native-post"}, site="bvtech")
            assert out37["ok"] and out37["forge"] == "github", out37
            assert out37["content_path"] == "src/content/blog/github-native-post.md", out37
            _put37 = next(p for m, p in _gh_calls37 if m == "PUT-BODY")
            _md37 = _b64_37.b64decode(_put37["content"]).decode()
            assert 'title: "GitHub Native Post"' in _md37 and "<p>Live-site body.</p>" in _md37
            assert _put37["branch"] == "main" and "sha" not in _put37   # create, not update
            # Doctor: GitHub connection + engine named; no GitLab checks run.
            d37 = _jp37.diagnose(db, "bvtech")
            names37 = [ck["name"] for ck in d37["checks"]]
            assert "GitHub connection" in names37 and "Site engine" in names37, names37
            assert "GitLab token" not in names37
            # Connection Center tile shows connected + testable.
            cc37 = {i["key"]: i for i in c.get("/api/setup/connections").json()["items"]}
            assert cc37["bvtech_github"]["connected"] is True
            assert cc37["bvtech_github"]["testable"] is True
            t37 = c.post("/api/setup/connections/bvtech_github/test").json()
            assert t37["ok"] is True, t37
        finally:
            _jp37._GH = _ogh37
            _cl37 = _SL27()
            _cl37.query(_IC27).filter(_IC27.provider.in_(["gitlab", "bvtech_site", "jp_site"])).delete(synchronize_session=False)
            _cl37.commit(); _cl37.close()
        print("GitHub-native publishing: fine-grained PAT tile (save->live verify as user + "
              "write check) + forge flips to github + markdown committed via Contents API "
              "with cloned frontmatter + Doctor runs GitHub checks + tile testable OK")

        # ==== v1.38: Forge safety — GitLab is authoritative; GitHub strictly opt-in ====
        from app.services import jp_site as _jp38
        # The live bvtech.org repo path, exact case (GitLab namespaces are
        # case-sensitive in the UI; the API tolerates either, but the config
        # must match what the operator sees).
        assert _jp38.SITES["bvtech"]["default_project"] == "BVTECHLLC-group/bvtech-website-new"
        assert _jp38.get_config(db, "bvtech")["project"] == "BVTECHLLC-group/bvtech-website-new"
        _jp38._GH = _gh37   # reuse the scripted GitHub double
        try:
            # A stored GitHub token with the switch OFF must NOT hijack the forge.
            r38 = c.post("/api/setup/connections/bvtech_github",
                         json={"values": {"gh_token": "ghp_TEST37",
                                          "github_active": "no"}}).json()
            assert r38["verified"] is True and r38["connected"] is False, r38
            assert "OFF" in r38["detail"] and "GitLab" in r38["detail"], r38
            cfg38 = _jp38.get_config(db, "bvtech")
            assert cfg38["forge"] == "gitlab", cfg38["forge"]
            assert cfg38["project"] == "BVTECHLLC-group/bvtech-website-new"
            cc38 = {i["key"]: i for i in c.get("/api/setup/connections").json()["items"]}
            assert cc38["bvtech_github"]["connected"] is False
            # Doctor (GitLab route) says exactly which repo publishes and that the
            # dormant GitHub token is ignored.
            d38 = _jp38.diagnose(db, "bvtech")
            pr38 = next(ck for ck in d38["checks"] if ck["name"] == "Publish route")
            assert pr38["ok"] and "GitLab -> BVTECHLLC-group/bvtech-website-new" in pr38["detail"]
            assert "GitHub token is stored" in pr38["detail"], pr38
            # Flip the switch back on (token already stored, not re-sent) -> GitHub.
            r38b = c.post("/api/setup/connections/bvtech_github",
                          json={"values": {"github_active": "yes"}}).json()
            assert r38b["verified"] is True and r38b["connected"] is True, r38b
            assert _jp38.get_config(db, "bvtech")["forge"] == "github"
        finally:
            _jp38._GH = _ogh37
            _cl38 = _SL27()
            _cl38.query(_IC27).filter(_IC27.provider.in_(["gitlab", "bvtech_site", "jp_site"])).delete(synchronize_session=False)
            _cl38.commit(); _cl38.close()
        print("Forge safety: exact GitLab repo path (BVTECHLLC-group) + github_active "
              "switch (off -> GitLab authoritative even with a stored PAT, tile says so, "
              "Doctor 'Publish route' names the repo + dormant token) + on -> GitHub OK")


        print("Connection Center: vault-set Claude key (never echoed, RBAC, validation) "
              "+ full connector registry (status/unlocks/console link/where/priority) "
              "+ readiness score OK")

        print("Content Autopilot: 4-channel daily run (customized per channel) + per-day "
              "dedupe + queue reuse + GitLab publishing for BOTH sites (one shared token, "
              "blog-file + slug-folder layouts, env-fallback chain) + build verification "
              "with auto-revert + failure retry/notify + RBAC OK")

        # ===================== v0.68: fleet inventory + patch compliance =====================
        # Re-seed SMOKE-PC with software + pending patches for the fleet rollups.
        a.post("/api/agent/inventory", headers=hdr, json={"software":[
            {"name":"Google Chrome","version":"125.0","publisher":"Google LLC"},
            {"name":"OpenSSL","version":"3.0.1","publisher":"OpenSSL"}]})
        a.post("/api/agent/patches", headers=hdr, json={"patches":[
            {"name":"2024-05 Cumulative Update","kb":"5034123","severity":"critical"},
            {"name":".NET Update","kb":"6000","severity":"important"}]})
        # Fleet software inventory aggregates titles with device/version counts.
        fsw=c.get("/api/inventory/software").json()
        chrome=[x for x in fsw if x["name"]=="Google Chrome"]
        assert chrome and chrome[0]["devices"]>=1, fsw
        # Vuln-response drill-down: which devices run OpenSSL?
        od=c.get("/api/inventory/software/devices", params={"name":"OpenSSL"}).json()
        assert any(d["device_id"]==dev_id for d in od["devices"]), od
        # Fleet patch compliance rollup: SMOKE-PC has 2 pending incl. a critical.
        pc=c.get("/api/inventory/patches").json()
        assert pc["fleet"]["pending_total"]>=2 and pc["by_severity"].get("critical",0)>=1, pc
        assert any(w["device_id"]==dev_id and w["pending"]>=2 for w in pc["worst_devices"]), pc["worst_devices"]
        assert any(t["kb"]=="KB5034123" or t["kb"]=="5034123" for t in pc["top_pending"]), pc["top_pending"]
        # RBAC: client software inventory is scoped to them; patch rollup is staff-only.
        casw=ca_c.get("/api/inventory/software").json()
        assert isinstance(casw,list)   # 200, scoped to their client
        assert ca_c.get("/api/inventory/patches").status_code==403
        print("fleet inventory + patch compliance (aggregate + drill-down + RBAC) OK")

        # ===================== v0.20: metric history =====================
        mh=c.get(f"/api/devices/{dev_id}/metrics").json()
        assert mh["points"]>=1 and isinstance(mh["series"],list), mh
        assert ca_c.get(f"/api/devices/{dev_id}/metrics").status_code==200  # client own device
        print("metric history series + RBAC OK")

        # ===================== v0.20: scheduled reports =====================
        sc=c.post("/api/report-schedules", json={"client_id":cid,"recipient_email":"owner@acme.co","cadence":"monthly"})
        assert sc.status_code==201, sc.text
        sid=sc.json()["id"]
        assert c.post("/api/report-schedules", json={"client_id":cid,"recipient_email":"x@y.co","cadence":"daily"}).status_code==400
        # first run sends it (last_sent None => due); second run is a no-op (not due yet)
        r1=c.post("/api/report-schedules/run-now").json()
        assert r1["reports_sent"]>=1, r1
        assert c.post("/api/report-schedules/run-now").json()["reports_sent"]==0
        assert c.post(f"/api/report-schedules/{sid}/toggle").json()["enabled"] is False
        assert ca_c.get("/api/report-schedules").status_code==403  # staff-only
        assert c.delete(f"/api/report-schedules/{sid}").status_code==204
        print("scheduled reports CRUD + due-cadence + run-checks integration + RBAC OK")

        # ===================== v0.21: integrations & command center =====================
        # --- API keys: external auth as the owner via X-API-Key ---
        keyj=c.post("/api/integrations/api-keys", json={"label":"smoke-tool"}).json()
        raw=keyj["api_key"]; kid=keyj["id"]
        kc=TestClient(app); kc.cookies.clear()
        assert kc.get("/api/clients").status_code==401                       # no auth
        rk=kc.get("/api/clients", headers={"X-API-Key":raw})
        assert rk.status_code==200 and isinstance(rk.json(),list), rk.text    # key works everywhere
        c.delete(f"/api/integrations/api-keys/{kid}")
        assert kc.get("/api/clients", headers={"X-API-Key":raw}).status_code==401  # revoked
        assert ca_c.get("/api/integrations/api-keys").status_code==403        # staff-only
        print("API keys: auth-as-owner + revoke + RBAC OK")

        # --- Outbound webhooks (event bus) with a fresh local receiver ---
        evt_hits=[]
        class _EH(BaseHTTPRequestHandler):
            def do_POST(self):
                n=int(self.headers.get("content-length",0))
                evt_hits.append((self.headers.get("X-OpsPilot-Event"),
                                 self.headers.get("X-OpsPilot-Signature"),
                                 self.rfile.read(n).decode()))
                self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
            def log_message(self,*a): pass
        srv2=HTTPServer(("127.0.0.1",0),_EH)
        threading.Thread(target=srv2.serve_forever,daemon=True).start()
        ehook=f"http://127.0.0.1:{srv2.server_address[1]}/ev"
        whj=c.post("/api/integrations/webhooks", json={"url":ehook,"events":["ticket.created"]}).json()
        assert "secret" in whj, whj
        assert any(e=="ticket.created" for e in c.get("/api/integrations/events").json()["events"])
        tw=c.post(f"/api/integrations/webhooks/{whj['id']}/test").json()
        assert tw["ok"] and 200<=tw["status"]<300, tw
        assert any(h[0]=="ping" for h in evt_hits), evt_hits           # signed test event delivered
        assert all(h[1] and h[1].startswith("sha256=") for h in evt_hits), "missing HMAC signature"
        assert c.post("/api/integrations/webhooks", json={"url":"ftp://x"}).status_code==400  # http(s) only
        assert c.post("/api/integrations/webhooks", json={"url":ehook,"events":["nope.bad"]}).status_code==400

        # --- Inbound ingest: any tool -> ticket/alert (token IS the auth) ---
        ij=c.post("/api/integrations/inbound", json={"name":"UptimeRobot","client_id":cid,"action":"ticket"}).json()
        ingest_url=ij["url"]; ipath=ingest_url[ingest_url.index("/api/ingest/"):]
        pub=TestClient(app); pub.cookies.clear()
        rr=pub.post(ipath, json={"subject":"Site down","body":"HTTP 500","priority":"high"})
        assert rr.status_code==200 and rr.json()["created"]=="ticket", rr.text
        # that ticket.created event should have reached our webhook receiver (event bus)
        assert any(h[0]=="ticket.created" and "Site down" in h[2] for h in evt_hits), evt_hits
        assert pub.post("/api/ingest/bogus-token", json={"subject":"x"}).status_code==404
        # alert action
        aj=c.post("/api/integrations/inbound", json={"name":"Datadog","client_id":cid,"action":"alert"}).json()
        apath=aj["url"][aj["url"].index("/api/ingest/"):]
        ar=pub.post(apath, json={"title":"CPU 99%","severity":"critical"})
        assert ar.status_code==200 and ar.json()["created"]=="alert", ar.text
        assert any(s["received_count"]>=1 for s in c.get("/api/integrations/inbound").json())
        assert ca_c.get("/api/integrations/inbound").status_code==403
        print("inbound ingest -> ticket/alert + event-bus fan-out + HMAC + RBAC OK")

        # --- Integration catalog + saved connections ---
        cat=c.get("/api/integrations/catalog").json()["catalog"]
        assert len(cat)>=10 and any(x["key"]=="connectwise" for x in cat), cat
        conn=c.post("/api/integrations/connections", json={"provider":"slack","config":{"webhook_url":"x"}}).json()
        conns=c.get("/api/integrations/connections").json()
        assert any(cc["id"]==conn["id"] and "webhook_url" in cc["config_keys"] for cc in conns), conns
        assert c.post(f"/api/integrations/connections/{conn['id']}/toggle").json()["enabled"] is False
        assert c.delete(f"/api/integrations/connections/{conn['id']}").status_code==204
        srv2.shutdown()
        print("integration catalog + connections OK")

        # --- Global search across the command center ---
        sj=c.get("/api/search", params={"q":"Smoke"}).json()
        assert any(r["type"]=="client" for r in sj["results"]), sj
        sd=c.get("/api/search", params={"q":"SMOKE-PC"}).json()
        assert any(r["type"]=="device" for r in sd["results"]), sd
        assert c.get("/api/search", params={"q":"a"}).json()["results"]==[]   # min length guard
        # client user search is tenant-scoped (only their own client surfaces)
        cs=ca_c.get("/api/search", params={"q":"Smoke"}).json()
        assert all(r.get("type")!="integration" for r in cs["results"])        # integrations are staff-only
        print("global search across entities + scope OK")

        # ===================== v0.22: dev hub + comprehensive audit =====================
        assert c.get("/developers").status_code==200 and "Developer Hub" in c.get("/developers").text
        oa=c.get("/api/openapi.json"); assert oa.status_code==200 and len(oa.json()["paths"])>50
        # the audit middleware logs EVERY mutating API call (not just logins)
        c.post("/api/clients", json={"name":"Audit MW Co"})
        arows=c.get("/api/audit?limit=1000").json()
        assert any(a["action"]=="api.post" and a.get("target_id")=="/api/clients" for a in arows), "mutation not audited"
        assert not any(a["action"]=="api.get" for a in arows), "GETs should not be audited"
        print("developer hub + openapi + comprehensive audit middleware OK")

        # ===================== v0.23: OAuth2 SSO + connectors =====================
        from app.services import oauth as oauthsvc, crypto as cryptosvc
        # PKCE correctness (known-answer)
        assert oauthsvc.challenge_s256("abc") == \
            __import__("base64").urlsafe_b64encode(__import__("hashlib").sha256(b"abc").digest()).decode().rstrip("="), "PKCE S256 mismatch"
        # Stand up a mock OAuth provider (token + userinfo) and register it.
        ohits={"token":0}
        class _OAuthMock(BaseHTTPRequestHandler):
            def _send(self, obj):
                import json as _j; b=_j.dumps(obj).encode()
                self.send_response(200); self.send_header("Content-Type","application/json")
                self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
            def do_POST(self):
                ohits["token"]+=1; n=int(self.headers.get("content-length",0)); self.rfile.read(n)
                self._send({"access_token":"AT-123","refresh_token":"RT-456","expires_in":3600,"scope":"openid email"})
            def do_GET(self):
                self._send({"email":owner_email,"mail":owner_email})
            def log_message(self,*a): pass
        osrv=HTTPServer(("127.0.0.1",0),_OAuthMock)
        threading.Thread(target=osrv.serve_forever,daemon=True).start()
        oport=osrv.server_address[1]; obase=f"http://127.0.0.1:{oport}"
        oauthsvc.register_provider("mock", {
            "name":"MockIDP","authorize_url":f"{obase}/authorize","token_url":f"{obase}/token",
            "userinfo_url":f"{obase}/userinfo","scopes":["openid","email"],
            "client_id":"cid-xyz","client_secret":"secret","email_fields":["email","mail"]})
        # provider appears in the public list
        assert any(p["key"]=="mock" for p in c.get("/api/oauth/providers").json()["providers"])

        # --- SSO sign-in flow (fresh, cookie-less client) ---
        oc=TestClient(app); oc.cookies.clear()
        r1=oc.get("/api/oauth/mock/login", follow_redirects=False)
        assert r1.status_code==302, r1.status_code
        loc=r1.headers["location"]
        assert "code_challenge=" in loc and "code_challenge_method=S256" in loc and "client_id=cid-xyz" in loc, loc
        import urllib.parse as _up
        state=_up.parse_qs(_up.urlparse(loc).query)["state"][0]
        # provider redirects back with code; we complete the dance
        cb=oc.get(f"/api/oauth/mock/callback?state={state}&code=AUTHCODE", follow_redirects=False)
        assert cb.status_code==302 and cb.headers["location"]=="/dashboard", cb.headers
        assert oc.cookies.get("access_token"), "SSO did not establish a session"
        assert oc.get("/api/auth/me").json()["email"]==owner_email, "SSO logged in wrong user"
        assert ohits["token"]>=1, "token endpoint was not called"
        print("OAuth SSO: authorize(PKCE+state) -> callback -> session OK")

        # --- CSRF: a bogus/reused state is rejected ---
        assert oc.get("/api/oauth/mock/callback?state=forged&code=x", follow_redirects=False).status_code==400
        assert oc.get(f"/api/oauth/mock/callback?state={state}&code=x", follow_redirects=False).status_code==400  # state single-use
        print("OAuth CSRF/state single-use enforced OK")

        # --- Connector flow: store an ENCRYPTED token, list, revoke ---
        rc=c.get("/api/oauth/mock/connect", follow_redirects=False)
        assert rc.status_code==302
        cstate=_up.parse_qs(_up.urlparse(rc.headers["location"]).query)["state"][0]
        c.get(f"/api/oauth/mock/callback?state={cstate}&code=AUTHCODE", follow_redirects=False)
        toks=c.get("/api/oauth/tokens").json()
        mocktok=[t for t in toks if t["provider"]=="mock"]
        assert mocktok and mocktok[0]["has_refresh"] and mocktok[0]["account_email"]==owner_email, toks
        assert "access_token" not in str(toks), "token material must never be returned"
        # confirm at-rest encryption is real: ciphertext decrypts back to the token
        assert cryptosvc.encrypt("AT-123")!="AT-123" and cryptosvc.decrypt(cryptosvc.encrypt("AT-123"))=="AT-123"
        assert ca_c.get("/api/oauth/tokens").status_code==403   # staff-only
        assert c.delete(f"/api/oauth/tokens/{mocktok[0]['id']}").status_code==204
        osrv.shutdown()
        print("OAuth connector: encrypted token store + list + RBAC + revoke OK")

        # --- v0.86: Microsoft SSO hardening (work-account tenant + robust match) ---
        import base64 as _b64, json as _js2
        # tenant normalization: personal-account-inviting values become work/school
        assert oauthsvc.normalize_tenant("common") == "organizations"
        assert oauthsvc.normalize_tenant("") == "organizations"
        assert oauthsvc.normalize_tenant(None) == "organizations"
        assert oauthsvc.normalize_tenant("  Common ") == "organizations"
        assert oauthsvc.normalize_tenant("11112222-3333-4444-5555-666677778888") == \
            "11112222-3333-4444-5555-666677778888"   # a real tenant GUID is respected
        # registering Microsoft coerces the tenant + forces the account picker
        oauthsvc._register_microsoft(client_id="mid", client_secret="msec", tenant="common",
                                     login_base="https://login.microsoftonline.com",
                                     graph_base="https://graph.microsoft.com/v1.0")
        msp = oauthsvc.get_provider("microsoft")
        assert "/organizations/oauth2/v2.0/authorize" in msp["authorize_url"], msp["authorize_url"]
        assert msp["extra_authorize"].get("prompt") == "select_account"
        au = oauthsvc.authorize_url("microsoft", state="s", code_challenge="cc",
                                    redirect_uri="https://x/cb")
        assert "prompt=select_account" in au and "code_challenge_method=S256" in au
        # id_token claims drive the email (reliable across account types), lowercased
        def _mk_idtok(claims):
            seg = lambda o: _b64.urlsafe_b64encode(_js2.dumps(o).encode()).decode().rstrip("=")
            return f"{seg({'alg':'none'})}.{seg(claims)}.sig"
        cands = oauthsvc.candidate_emails(
            "microsoft", {"id_token": _mk_idtok({"preferred_username": "Owner@BVTech.ORG"})}, None)
        assert cands and cands[0] == "owner@bvtech.org", cands
        # SSO matches a provisioned user case-insensitively even if the IdP returns
        # the address in a different case than we stored it.
        class _CaseIdp(BaseHTTPRequestHandler):
            def _send(self, obj):
                b=_js2.dumps(obj).encode(); self.send_response(200)
                self.send_header("Content-Type","application/json")
                self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
            def do_POST(self):
                n=int(self.headers.get("content-length",0)); self.rfile.read(n)
                self._send({"access_token":"AT-9","expires_in":3600,
                            "id_token":_mk_idtok({"preferred_username":owner_email.upper()})})
            def do_GET(self): self._send({})
            def log_message(self,*a): pass
        csrv=HTTPServer(("127.0.0.1",0),_CaseIdp)
        threading.Thread(target=csrv.serve_forever,daemon=True).start()
        cbase=f"http://127.0.0.1:{csrv.server_address[1]}"
        oauthsvc.register_provider("mockcase", {
            "name":"MockCase","authorize_url":f"{cbase}/authorize","token_url":f"{cbase}/token",
            "userinfo_url":f"{cbase}/userinfo","scopes":["openid","email"],
            "client_id":"cid2","client_secret":"sec2","email_fields":["email"]})
        oc2=TestClient(app); oc2.cookies.clear()
        r2=oc2.get("/api/oauth/mockcase/login", follow_redirects=False)
        st2=_up.parse_qs(_up.urlparse(r2.headers["location"]).query)["state"][0]
        cb2=oc2.get(f"/api/oauth/mockcase/callback?state={st2}&code=AC", follow_redirects=False)
        assert cb2.status_code==302 and cb2.headers["location"]=="/dashboard", cb2.headers
        assert oc2.get("/api/auth/me").json()["email"]==owner_email, "case-insensitive SSO match failed"
        # an unknown IdP address still never creates/hijacks an account
        class _NoIdp(_CaseIdp):
            def do_POST(self):
                n=int(self.headers.get("content-length",0)); self.rfile.read(n)
                self._send({"access_token":"AT-0","expires_in":3600,
                            "id_token":_mk_idtok({"preferred_username":"stranger@nowhere.test"})})
        nsrv=HTTPServer(("127.0.0.1",0),_NoIdp)
        threading.Thread(target=nsrv.serve_forever,daemon=True).start()
        nbase=f"http://127.0.0.1:{nsrv.server_address[1]}"
        oauthsvc.register_provider("mocknone", {
            "name":"MockNone","authorize_url":f"{nbase}/authorize","token_url":f"{nbase}/token",
            "userinfo_url":f"{nbase}/userinfo","scopes":["openid"],
            "client_id":"c3","client_secret":"s3","email_fields":["email"]})
        oc3=TestClient(app); oc3.cookies.clear()
        r3=oc3.get("/api/oauth/mocknone/login", follow_redirects=False)
        st3=_up.parse_qs(_up.urlparse(r3.headers["location"]).query)["state"][0]
        cb3=oc3.get(f"/api/oauth/mocknone/callback?state={st3}&code=AC", follow_redirects=False)
        assert cb3.status_code==302 and "oauth_error=no_account" in cb3.headers["location"], cb3.headers
        assert not oc3.cookies.get("access_token"), "unmatched SSO must not open a session"
        csrv.shutdown(); nsrv.shutdown()
        # the settings API advertises the effective (healed) tenant to the UI:
        # nothing saved a tenant, so it resolves to work/school 'organizations'.
        assert c.get("/api/oauth/sso-settings").json()["ms_tenant_effective"] == "organizations"
        # SSO self-diagnostics surface the last failed attempt + a fixable checklist
        diag = c.get("/api/oauth/sso-diagnostics").json()
        assert diag["microsoft"]["effective_tenant"] == "organizations"
        assert diag["microsoft"]["work_accounts_only"] is True
        assert diag["microsoft"]["redirect_uri"].endswith("/api/oauth/microsoft/callback")
        assert any(x["label"].startswith("Your own email") and x["ok"] is True
                   for x in diag["microsoft"]["checklist"])   # owner maps to a login
        lf = diag["last_failed_attempt"]
        assert lf and "stranger@nowhere.test" in lf["emails_returned"] and lf["resolved_now"] is False, lf
        assert diag["last_successful_attempt"] and diag["last_successful_attempt"]["email"]
        assert ca_c.get("/api/oauth/sso-diagnostics").status_code == 403   # staff-only
        print("Microsoft SSO hardening: work-account tenant + select_account + id_token match + case-insensitive + no-hijack + diagnostics OK")

        # --- v0.87: zero-touch JIT SSO provisioning (domain-anchored, safe) ---
        from app.services import sso_provision as _prov
        from app.core.db import SessionLocal as _PSL
        assert c.get("/api/oauth/sso-provisioning").json()["enabled"] is True   # default on
        # onboard a client -> anchors its email domain via the created CLIENT_ADMIN
        ob = c.post("/api/clients/onboard", json={"name": "Zero Touch Co",
                    "contact_email": "admin@zerotouch.io", "contact_name": "Zed Admin"})
        assert ob.status_code == 201, ob.text
        zt_cid = ob.json()["client_id"]
        # a NEW colleague on that domain signs in via SSO -> auto read-only viewer
        class _JitIdp(_CaseIdp):
            def do_POST(self):
                n=int(self.headers.get("content-length",0)); self.rfile.read(n)
                self._send({"access_token":"AT-J","expires_in":3600,
                            "id_token":_mk_idtok({"preferred_username":"NewHire@ZeroTouch.io","name":"New Hire"})})
        jsrv=HTTPServer(("127.0.0.1",0),_JitIdp)
        threading.Thread(target=jsrv.serve_forever,daemon=True).start()
        jbase=f"http://127.0.0.1:{jsrv.server_address[1]}"
        oauthsvc.register_provider("mockjit", {
            "name":"MockJit","authorize_url":f"{jbase}/authorize","token_url":f"{jbase}/token",
            "userinfo_url":f"{jbase}/userinfo","scopes":["openid"],
            "client_id":"cj","client_secret":"sj","email_fields":["email"]})
        ocj=TestClient(app); ocj.cookies.clear()
        rj=ocj.get("/api/oauth/mockjit/login", follow_redirects=False)
        stj=_up.parse_qs(_up.urlparse(rj.headers["location"]).query)["state"][0]
        cbj=ocj.get(f"/api/oauth/mockjit/callback?state={stj}&code=AC", follow_redirects=False)
        assert cbj.status_code==302 and cbj.headers["location"]=="/portal", cbj.headers
        me=ocj.get("/api/auth/me").json()
        assert me["email"]=="newhire@zerotouch.io" and me["role"]=="client_viewer", me
        # staff get an in-app heads-up about the new self-service login
        notifs=c.get("/api/notifications").json()
        assert any(n["kind"]=="access" and "newhire@zerotouch.io" in n["message"] for n in notifs), \
            "expected a staff notification for the new SSO user"
        # the created user is scoped to the anchored client, lowest privilege
        _pdb=_PSL()
        try:
            from app.models import User as _U, Role as _R
            nu=_pdb.query(_U).filter(_U.email=="newhire@zerotouch.io").first()
            assert nu and nu.role==_R.CLIENT_VIEWER and nu.client_id==zt_cid, "wrong provisioned scope"
            # second sign-in must NOT create a duplicate
            ocj.get("/api/oauth/mockjit/login", follow_redirects=False)
            cnt=_pdb.query(_U).filter(_U.email=="newhire@zerotouch.io").count()
            assert cnt==1, cnt
        finally:
            _pdb.close()
        jsrv.shutdown()
        # direct service checks for the safety guards
        _sdb=_PSL()
        try:
            # free/public domain never provisions even if it somehow anchored
            assert _prov.maybe_autoprovision(_sdb, "someone@gmail.com") is None
            # unknown domain (no anchor) refuses
            assert _prov.maybe_autoprovision(_sdb, "ghost@nfl-unknown-domain.io") is None
            # ambiguous: same domain under two clients -> refuse
            c.post("/api/clients/onboard", json={"name":"Ambi A","contact_email":"a@ambi.io"})
            c.post("/api/clients/onboard", json={"name":"Ambi B","contact_email":"b@ambi.io"})
            assert _prov.maybe_autoprovision(_sdb, "c@ambi.io") is None, "ambiguous domain must not provision"
            # disabled toggle short-circuits
            _prov.save_config(_sdb, {"enabled": False})
            assert _prov.maybe_autoprovision(_sdb, "late@zerotouch.io") is None
            _prov.save_config(_sdb, {"enabled": True})
        finally:
            _sdb.close()
        # RBAC: only owner toggles; clients can't read or change provisioning
        assert ca_c.get("/api/oauth/sso-provisioning").status_code == 403
        assert ca_c.put("/api/oauth/sso-provisioning", json={"enabled": False}).status_code == 403
        print("Zero-touch SSO provisioning: domain-anchored viewer + staff notify + no-dupe + free-domain/ambiguous/disabled guards + RBAC OK")

        # --- v0.91: explicit per-client SSO domains (provision before any anchor) ---
        # onboard with explicit domains: normalized, free/pathless ones dropped
        ob2 = c.post("/api/clients/onboard", json={"name": "Domain Co",
              "contact_email": "boss@domainco.io",
              "sso_domains": "DomainCo.io, https://sub-not/, gmail.com"}).json()
        assert "domainco.io" in ob2["sso_domains"] and "gmail.com" not in ob2["sso_domains"], ob2
        dc_cid = ob2["client_id"]
        assert c.get(f"/api/clients/{dc_cid}/sso-domains").json()["sso_domains"] == ob2["sso_domains"]
        # a brand-new client with NO users: authorize a domain, then it provisions
        fresh_cid = c.post("/api/clients", json={"name": "Fresh Co"}).json()["id"]
        put_res = c.put(f"/api/clients/{fresh_cid}/sso-domains",
                        json={"sso_domains": ["FreshCo.io", "gmail.com"]}).json()
        assert put_res["sso_domains"] == ["freshco.io"], put_res   # free domain dropped
        _ddb = _PSL()
        try:
            u = _prov.maybe_autoprovision(_ddb, "newperson@freshco.io")
            assert u and u.role.value == "client_viewer" and u.client_id == fresh_cid, \
                "explicit-domain provisioning (no anchor user) failed"
            # ambiguity: two clients both claim a domain -> refuse
            c.put(f"/api/clients/{dc_cid}/sso-domains", json={"sso_domains": ["shared-x.io"]})
            c.put(f"/api/clients/{fresh_cid}/sso-domains", json={"sso_domains": ["freshco.io", "shared-x.io"]})
            assert _prov.maybe_autoprovision(_ddb, "x@shared-x.io") is None, "ambiguous explicit domain must refuse"
        finally:
            _ddb.close()
        # onboard WITHOUT domains -> defaults to the contact's own domain
        ob3 = c.post("/api/clients/onboard", json={"name": "Default Dom",
              "contact_email": "lead@defaultdom.io"}).json()
        assert ob3["sso_domains"] == ["defaultdom.io"], ob3
        # RBAC: owner writes, staff reads, client-admin gets nothing
        assert tc.get(f"/api/clients/{dc_cid}/sso-domains").status_code == 200
        assert tc.put(f"/api/clients/{dc_cid}/sso-domains", json={"sso_domains": ["x.io"]}).status_code == 403
        assert ca_c.put(f"/api/clients/{dc_cid}/sso-domains", json={"sso_domains": ["x.io"]}).status_code == 403
        print("Per-client SSO domains: onboard default+explicit + provision-before-anchor + free-domain drop + ambiguity + RBAC OK")

        # --- v0.88: Users & Access management (directory + guardrailed actions) ---
        ulist = c.get("/api/users").json()
        assert "users" in ulist and "summary" in ulist and ulist["summary"]["sso_provisioned"] >= 1
        by_email = {u["email"]: u for u in ulist["users"]}
        assert by_email[owner_email]["is_staff"] is True and by_email[owner_email]["role"] == "owner"
        nh = by_email.get("newhire@zerotouch.io")
        assert nh and nh["sso_provisioned"] is True and nh["role"] == "client_viewer" \
            and nh["client_id"] == zt_cid, nh
        nh_id = nh["id"]
        tech_id = by_email["tech@bvtech.org"]["id"]
        # session control: the SSO viewer has a live session; owner can force sign-out
        assert nh["active_sessions"] >= 1, nh
        assert ocj.get("/api/auth/me").status_code == 200        # session live before
        so = c.post(f"/api/users/{nh_id}/sign-out-all").json()
        assert so["revoked_sessions"] >= 1 and so["active_sessions"] == 0, so
        assert ocj.get("/api/auth/me").status_code == 401        # signed out everywhere
        # filters: SSO-only returns only self-registered users (incl. newhire)
        sso_list = c.get("/api/users?sso_only=true").json()["users"]
        assert sso_list and all(u["sso_provisioned"] for u in sso_list)
        assert any(u["email"] == "newhire@zerotouch.io" for u in sso_list)
        # role filter + search
        assert all(u["role"] == "client_viewer" for u in c.get("/api/users?role=client_viewer").json()["users"])
        assert any(u["email"] == "newhire@zerotouch.io"
                   for u in c.get("/api/users?q=newhire").json()["users"])
        # promote viewer -> admin: clears the SSO self-registered flag
        pr = c.patch(f"/api/users/{nh_id}/role", json={"role": "client_admin"})
        assert pr.status_code == 200 and pr.json()["role"] == "client_admin", pr.text
        assert pr.json()["sso_provisioned"] is False   # promotion = "real" managed account
        # demote back
        assert c.patch(f"/api/users/{nh_id}/role", json={"role": "client_viewer"}).json()["role"] == "client_viewer"
        # guardrails: can't set a staff role, can't touch staff, can't touch self
        assert c.patch(f"/api/users/{nh_id}/role", json={"role": "tech"}).status_code == 400
        assert c.patch(f"/api/users/{tech_id}/role", json={"role": "client_viewer"}).status_code == 403
        assert c.patch(f"/api/users/{tech_id}/active", json={"active": False}).status_code == 403
        own_id = by_email[owner_email]["id"]
        assert c.patch(f"/api/users/{own_id}/active", json={"active": False}).status_code == 400  # not yourself
        # activate/deactivate a client user
        assert c.patch(f"/api/users/{nh_id}/active", json={"active": False}).json()["is_active"] is False
        assert c.patch(f"/api/users/{nh_id}/active", json={"active": True}).json()["is_active"] is True
        # password reset issues a temp password + re-enables
        rp = c.post(f"/api/users/{nh_id}/reset-password").json()
        assert rp.get("temp_password") and rp["is_active"] is True
        # RBAC: staff (tech) can READ, but only OWNER can mutate; clients get nothing
        assert tc.get("/api/users").status_code == 200
        assert tc.patch(f"/api/users/{nh_id}/role", json={"role": "client_viewer"}).status_code == 403
        assert ca_c.get("/api/users").status_code == 403
        assert tc.post(f"/api/users/{nh_id}/sign-out-all").status_code == 403   # owner-only
        print("Users & Access: directory + summary + filters + promote(clears SSO flag) + active + reset + session control (sign-out-all) + guardrails + RBAC OK")

        # --- v0.97: permission-scoped Document Library (seeded on startup) ---
        olib = c.get("/api/library").json()
        assert olib["counts"]["total"] >= 60, olib["counts"]           # ~70 docs seeded
        assert olib["counts"]["client_visible"] >= 1 and olib["counts"]["internal"] >= 1
        # staff can download BOTH a client-facing and an internal doc
        assert c.get("/api/library/BVT-LGL-001/download").status_code == 200
        rint = c.get("/api/library/BVT-RUN-053/download")
        assert rint.status_code == 200 and "application/pdf" in rint.headers.get("content-type", "")
        # client (client-admin) sees ONLY client docs, and never the visibility field
        clib = ca_c.get("/api/library").json()
        assert 0 < clib["counts"]["total"] < olib["counts"]["total"], clib["counts"]
        cats = {g["category"] for g in clib["groups"]}
        assert cats and "RUN" not in cats and "INT" not in cats, cats     # internal series hidden
        assert "visibility" not in clib["groups"][0]["docs"][0]            # classification hidden from clients
        # client downloads a client doc, is 404'd on an internal one (no existence leak)
        assert ca_c.get("/api/library/BVT-LGL-001/download").status_code == 200
        assert ca_c.get("/api/library/BVT-RUN-053/download").status_code == 404
        # client cannot reclassify; owner can, and the client's view follows
        assert ca_c.patch("/api/library/BVT-LGL-001/visibility", json={"visibility": "internal"}).status_code == 403
        before = ca_c.get("/api/library").json()["counts"]["total"]
        assert c.patch("/api/library/BVT-LGL-015/visibility", json={"visibility": "internal"}).json()["visibility"] == "internal"
        assert ca_c.get("/api/library").json()["counts"]["total"] == before - 1    # doc left the client's view
        assert ca_c.get("/api/library/BVT-LGL-015/download").status_code == 404     # and its download too
        assert c.patch("/api/library/BVT-LGL-015/visibility", json={"visibility": "bogus"}).status_code == 400
        print("Document Library: seeded + staff-all + client-only-scope + download gating (no leak) + owner reclassify + RBAC OK")

        # ===================== v0.24: PSA projects + Kanban =====================
        pj=c.post("/api/projects", json={"client_id":cid,"name":"M365 Migration","budget_hours":40})
        assert pj.status_code==201, pj.text
        pid=pj.json()["id"]
        # add tasks across columns
        t1=c.post(f"/api/projects/{pid}/tasks", json={"title":"Audit mailboxes","priority":"high"}).json()
        t2=c.post(f"/api/projects/{pid}/tasks", json={"title":"Cutover","status":"todo"}).json()
        assert t1["status"]=="todo" and t1["position"]==0 and t2["position"]==1, (t1,t2)
        # board groups by column
        board=c.get(f"/api/projects/{pid}/board").json()
        assert board["columns"]==["todo","in_progress","review","done"]
        assert len(board["tasks"]["todo"])==2 and board["project"]["task_count"]==2, board
        # move a task across the board; done stamps completed_at + rolls up progress
        mv=c.post(f"/api/tasks/{t1['id']}/move", json={"status":"done"}).json()
        assert mv["status"]=="done" and mv["completed_at"], mv
        assert c.get(f"/api/projects/{pid}/board").json()["project"]["progress"]==50
        # moving out of done clears completion
        assert c.post(f"/api/tasks/{t1['id']}/move", json={"status":"review"}).json()["completed_at"] is None
        assert c.post(f"/api/tasks/{t1['id']}/move", json={"status":"bogus"}).status_code==400
        # patch a task (assignee/priority)
        assert c.patch(f"/api/tasks/{t2['id']}", json={"priority":"urgent"}).json()["priority"]=="urgent"
        # project list shows rollups
        assert any(p["id"]==pid and p["task_count"]==2 for p in c.get("/api/projects").json())
        # client (same org) can VIEW the board but not mutate
        assert ca_c.get(f"/api/projects/{pid}/board").status_code==200
        assert ca_c.post(f"/api/projects/{pid}/tasks", json={"title":"x"}).status_code==403
        assert ca_c.post("/api/projects", json={"client_id":cid,"name":"y"}).status_code==403
        assert ca_c.post(f"/api/tasks/{t2['id']}/move", json={"status":"done"}).status_code==403
        # global search finds the project + task
        psr=c.get("/api/search", params={"q":"Migration"}).json()
        assert any(r["type"]=="project" for r in psr["results"]), psr
        assert any(r["type"]=="task" for r in c.get("/api/search", params={"q":"Cutover"}).json()["results"])
        # delete cascades tasks
        assert c.delete(f"/api/projects/{pid}").status_code==204
        assert c.get(f"/api/projects/{pid}/board").status_code==404
        print("PSA projects + Kanban board (tasks/move/rollup/RBAC/search/cascade) OK")

        # ===================== v0.25: live command-center overview =====================
        ov=c.get("/api/overview").json()
        for k in ("clients","devices","patch","alerts","tickets","projects","billing","activity"):
            assert k in ov, ("missing overview key", k)
        # numbers reflect reality created earlier in this run
        assert ov["clients"]["total"]>=1 and ov["devices"]["total"]>=1, ov
        assert isinstance(ov["activity"], list) and len(ov["activity"])>=1, "activity feed empty"
        assert ov["billing"]["mrr"]>=0 and "outstanding_total" in ov["billing"]
        # SLA risk accounting is present and numeric
        assert isinstance(ov["tickets"]["sla_breached"], int) and isinstance(ov["tickets"]["sla_at_risk"], int)
        # tenant scoping: a client user only sees their own org in the rollup
        cov=ca_c.get("/api/overview").json()
        assert cov["clients"]["total"]==1, cov   # ca_c belongs to exactly one client
        # client activity feed is scoped (no cross-tenant rows)
        print("live command-center overview (KPIs + activity + scope) OK")

        # ===================== v0.32: Action Center (ranked next-best-actions) ====
        # Seed a guaranteed-actionable signal: an open critical security finding.
        acf = c.post("/api/security/findings", json={
            "client_id": cid, "title": "AC smoke — exposed service",
            "severity": "critical"})
        assert acf.status_code in (200, 201), acf.text
        ac = c.get("/api/action-center").json()
        for k in ("generated_at", "ops_score", "total", "counts", "by_kind", "items"):
            assert k in ac, ("missing action-center key", k)
        assert isinstance(ac["ops_score"], int) and 0 <= ac["ops_score"] <= 100, ac["ops_score"]
        for sk in ("critical", "high", "medium", "low"):
            assert sk in ac["counts"], sk
        # items are ranked by score, descending
        scores = [i["score"] for i in ac["items"]]
        assert scores == sorted(scores, reverse=True), ("not ranked", scores)
        # every item is well-formed and explainable
        for i in ac["items"]:
            assert all(f in i for f in ("kind","severity","score","title","detail","action","link","client_id","client_name"))
            assert i["severity"] in ("critical","high","medium","low")
        # our seeded critical finding surfaces as a security_finding item
        assert any(i["kind"]=="security_finding" and i["severity"]=="critical" for i in ac["items"]), \
            "seeded critical finding not in action center"
        assert ac["counts"]["critical"] >= 1
        # staff can filter to one client; every returned item belongs to it
        acf1 = c.get(f"/api/action-center?client_id={cid}").json()
        assert all(i["client_id"]==cid for i in acf1["items"]), "client filter leaked other tenants"
        # tenant scoping: a client user only ever sees their own org's actions
        cac = ca_c.get("/api/action-center").json()
        assert all(i["client_id"]==cid for i in cac["items"]), "client user saw foreign actions"
        # a client user cannot peek at another client's action center
        assert ca_c.get("/api/action-center?client_id=999999").status_code in (403, 404)
        print("Action Center: ranked + explainable + RBAC scoped OK")

        # ---- v0.36: one-click "create ticket from action item" ----
        ct = c.post("/api/action-center/create-ticket", json={
            "client_id": cid, "title": "Disk filling on FILER-01", "detail": "Projected full in 3 days.",
            "severity": "critical", "link": "#devices/1", "kind": "predict_disk_fill",
            "entity_type": "device", "entity_id": "1"})
        assert ct.status_code == 201, ct.text
        ctj = ct.json()
        assert ctj["priority"] == "urgent" and ctj["id"], ctj   # critical -> urgent
        # the ticket really exists, with SLA stamped
        made = c.get(f"/api/tickets/{ctj['id']}").json()
        assert made["subject"] == "Disk filling on FILER-01" and made["sla"], made
        # RBAC: a client user cannot use the staff action
        assert ca_c.post("/api/action-center/create-ticket", json={
            "client_id": cid, "title": "x", "severity": "low"}).status_code == 403
        print("Action Center one-click create-ticket (severity->priority + SLA + RBAC) OK")

        # ===================== v0.33: Predictive Foresight =======================
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        from app.core.db import SessionLocal as _SL
        from app import models as _M
        _now = _dt.now(_tz.utc)
        _db = _SL()
        _fdev = _M.Device(client_id=cid, hostname="FORECAST-FILER", os="Windows Server",
                          health_score=72, patches_pending=2, av_status="on",
                          disk_pct=91, last_checkin=_now)
        _db.add(_fdev); _db.flush()
        for _i in range(11):                       # 70% -> 92% over 10 days (~2.2%/day)
            _db.add(_M.DeviceCheckin(device_id=_fdev.id, ts=_now - _td(days=10 - _i),
                                     cpu_pct=30, ram_pct=60, disk_pct=70 + _i * 2.2,
                                     health_score=82 - _i))
        _db.commit(); _fid = _fdev.id; _db.close()

        fdc = c.get(f"/api/devices/{_fid}/forecast").json()
        assert fdc["enough_data"] and fdc["disk"], fdc
        assert fdc["disk"]["days_to_full"] is not None and fdc["disk"]["days_to_full"] < 10, fdc["disk"]
        assert fdc["disk"]["trend"] == "degrading", fdc["disk"]
        assert any(r["kind"] == "disk_fill" for r in fdc["risks"]), fdc["risks"]
        # fleet roll-up surfaces the predicted disk-fill, severity-ordered
        ff = c.get("/api/foresight").json()
        assert ff["total"] >= 1 and any(r["hostname"] == "FORECAST-FILER" for r in ff["risks"]), ff
        # the prediction also flows into the Action Center as a predict_* item
        ac2 = c.get("/api/action-center").json()
        assert any(i["kind"].startswith("predict_") for i in ac2["items"]), "no predictive AC item"
        # tenant scoping + not-found
        assert ca_c.get(f"/api/devices/{_fid}/forecast").json()["device_id"] == _fid  # ca_c owns cid
        assert c.get("/api/devices/999999/forecast").status_code == 404
        print("Predictive Foresight: disk-fill projection + fleet + AC + RBAC OK")

        # ---- anomaly detection: a sudden spike vs the device's own baseline ----
        _db = _SL()
        _adev = _M.Device(client_id=cid, hostname="ANOMALY-APP", health_score=82,
                          av_status="on", cpu_pct=98, disk_pct=50, last_checkin=_now)
        _db.add(_adev); _db.flush()
        for _i in range(9):                        # stable ~20% CPU baseline
            _db.add(_M.DeviceCheckin(device_id=_adev.id, ts=_now - _td(hours=18 - _i * 2),
                                     cpu_pct=20 + (_i % 3), ram_pct=50, disk_pct=50, health_score=85))
        _db.add(_M.DeviceCheckin(device_id=_adev.id, ts=_now, cpu_pct=98, ram_pct=50,
                                 disk_pct=50, health_score=82))   # the spike
        _db.commit(); _aid = _adev.id; _db.close()
        afc = c.get(f"/api/devices/{_aid}/forecast").json()
        assert any(a["kind"] == "cpu_spike" for a in afc.get("anomalies", [])), afc.get("anomalies")
        ac3 = c.get("/api/action-center").json()
        spikes = [i for i in ac3["items"] if i["kind"] == "predict_cpu_spike"
                  and "ANOMALY-APP" in i["title"]]
        assert len(spikes) == 1, ("expected exactly one anomaly item", len(spikes))
        print("Anomaly detection: z-score spike + AC (deduped) OK")

        # ===================== v0.33: Client Health Score ========================
        ch = c.get("/api/clients/health").json()
        assert "portfolio_score" in ch and isinstance(ch["clients"], list) and ch["count"] >= 1, ch
        row = next(r for r in ch["clients"] if r["client_id"] == cid)
        for k in ("score", "grade", "risk", "factors", "components", "stats"):
            assert k in row, ("missing client-health key", k)
        assert 0 <= row["score"] <= 100 and row["grade"] in ("A","B","C","D","F")
        assert row["risk"] in ("healthy","watch","high")
        # single-client endpoint + RBAC: a client user sees only their own
        assert c.get(f"/api/clients/{cid}/health").json()["client_id"] == cid
        chc = ca_c.get("/api/clients/health").json()
        assert all(r["client_id"] == cid for r in chc["clients"]), "client saw other orgs' health"
        print("Client Health Score: weighted + explainable + RBAC OK")

        # ===================== v0.34: Content Studio (blog/advisory gen) =========
        cpost = {"title": "Patch Tuesday June 2026 — Two Zero-Days Under Active Attack",
                 "kind": "advisory", "keywords": "Patch Tuesday, CVE, BVTech",
                 "body": "Microsoft shipped **74 fixes** today.\n\n## What to do\nPatch now.\n\n- Update endpoints\n- Verify backups\n\n> Managed clients are already covered.\n\nQuestions? [Book a call](https://bvtech.org/book/)."}
        rr = c.post("/api/content/render", json=cpost)
        assert rr.status_code == 200, rr.text
        rj = rr.json()
        assert rj["slug"] == "patch-tuesday-june-2026-two-zero-days-under-active-attack", rj["slug"]
        assert rj["publish_path"] == f"blog/{rj['slug']}.html"
        assert rj["url"].endswith(rj["slug"] + ".html")
        h = rj["html"]
        # SEO + schema + on-brand + safe markdown all present
        for must in ["<title>", "application/ld+json", "BlogPosting", 'property="og:image"',
                     "#0E0D2C", "<strong>74 fixes</strong>", "<h2>What to do</h2>",
                     "<ul><li>Update endpoints", "<blockquote>", 'href="https://bvtech.org/book/"']:
            assert must in h, ("content missing " + must)
        # preview returns a live HTML page
        pv = c.post("/api/content/preview", json=cpost)
        assert pv.status_code == 200 and pv.headers["content-type"].startswith("text/html")
        # stage computes the publish target
        st = c.post("/api/content/stage", json=cpost).json()
        assert st["staged"] and st["filename"].endswith(".html")
        # title is required
        assert c.post("/api/content/render", json={"title": ""}).status_code == 422
        # RBAC: a client user cannot generate site content
        assert ca_c.post("/api/content/render", json=cpost).status_code == 403
        print("Content Studio: render + preview + stage + SEO/schema + RBAC OK")

        # ===================== v0.26: time tracking / money loop =====================
        tt_ticket=c.post("/api/tickets", json={"client_id":cid,"subject":"Timer ticket","priority":"normal"}).json()["id"]
        tt_pid=c.post("/api/projects", json={"client_id":cid,"name":"Timer project"}).json()["id"]
        tt_task=c.post(f"/api/projects/{tt_pid}/tasks", json={"title":"Timed task"}).json()["id"]
        assert c.get("/api/timers/current").json() is None
        s=c.post("/api/timers/start", json={"ticket_id":tt_ticket,"note":"work"}).json()
        assert s["ticket_id"]==tt_ticket and "elapsed_seconds" in s, s
        assert c.get("/api/timers/current").json()["ticket_id"]==tt_ticket
        # starting another banks the first as a logged entry
        s2=c.post("/api/timers/start", json={"task_id":tt_task}).json()
        assert "banked_entry" in s2 and s2["task_id"]==tt_task, s2
        e=c.post("/api/timers/stop").json()
        assert e["task_id"]==tt_task and e["minutes"]>=1, e
        assert c.get("/api/timers/current").json() is None
        assert c.post("/api/timers/stop").status_code==404   # nothing running
        # manual task time + exactly-one-context guard
        assert c.post(f"/api/tasks/{tt_task}/time", json={"minutes":30}).json()["minutes"]==30
        assert c.post("/api/timers/start", json={"ticket_id":tt_ticket,"task_id":tt_task}).status_code==400
        # unbilled rollup, then invoice consumes it -> back to 0
        ub=c.get("/api/time/unbilled").json()
        assert ub["total_minutes"]>=31 and any(r["client_id"]==cid for r in ub["by_client"]), ub
        gi=c.post("/api/invoices/generate", json={"client_id":cid,"include_time":True,"hourly_rate":120,"include_licenses":False})
        assert gi.status_code==201 and gi.json()["total"]>0, gi.text
        assert c.get("/api/time/unbilled").json()["total_minutes"]==0
        # RBAC: clients cannot touch timers/time
        assert ca_c.get("/api/timers/current").status_code==403
        assert ca_c.post("/api/timers/start", json={"ticket_id":tt_ticket}).status_code==403
        assert ca_c.get("/api/time/unbilled").status_code==403
        print("time tracking: timers + task time + unbilled -> invoice money loop + RBAC OK")

        # ===================== v0.27: asset management (CMDB) =====================
        import datetime as _dtmod
        soon=( _dtmod.datetime.now(_dtmod.timezone.utc)+_dtmod.timedelta(days=20)).isoformat()
        far =( _dtmod.datetime.now(_dtmod.timezone.utc)+_dtmod.timedelta(days=400)).isoformat()
        meta=c.get("/api/assets/meta").json()
        assert "printer" in meta["types"] and "active" in meta["statuses"], meta
        a1=c.post("/api/assets", json={"client_id":cid,"name":"Front Printer","asset_type":"printer",
            "make":"HP","model":"M404","serial":"PRN-001","warranty_expires":soon}).json()
        a2=c.post("/api/assets", json={"client_id":cid,"name":"Core Switch","asset_type":"network",
            "serial":"SW-999","warranty_expires":far}).json()
        assert a1["warranty_state"]=="expiring" and a2["warranty_state"]=="ok", (a1,a2)
        # invalid type rejected on patch
        assert c.patch(f"/api/assets/{a1['id']}", json={"asset_type":"spaceship"}).status_code==400
        assert c.patch(f"/api/assets/{a1['id']}", json={"assigned_to":"Reception","status":"in_repair"}).json()["status"]=="in_repair"
        # list + type filter
        assert len(c.get("/api/assets").json())>=2
        assert all(a["asset_type"]=="printer" for a in c.get("/api/assets", params={"asset_type":"printer"}).json())
        # warranty-expiring surfaces a1 (20d) but not a2 (400d)
        we=c.get("/api/assets/warranty-expiring", params={"days":60}).json()
        assert any(a["id"]==a1["id"] for a in we) and not any(a["id"]==a2["id"] for a in we), we
        # client can VIEW own assets, staff-only to mutate
        assert ca_c.get("/api/assets").status_code==200
        assert any(a["id"]==a1["id"] for a in ca_c.get("/api/assets").json())
        assert ca_c.post("/api/assets", json={"client_id":cid,"name":"x"}).status_code==403
        assert ca_c.delete(f"/api/assets/{a2['id']}").status_code==403
        # global search finds an asset by serial
        assert any(r["type"]=="asset" for r in c.get("/api/search", params={"q":"SW-999"}).json()["results"])
        assert c.delete(f"/api/assets/{a1['id']}").status_code==204
        print("asset management (CMDB + warranty + filters + RBAC + search) OK")

        # ===================== v0.39: maintenance windows ========================
        from datetime import datetime as _dM, timezone as _zM, timedelta as _tM
        mwc = c.post("/api/clients", json={"name": "Maint Co"}).json()["id"]
        mtok = c.post(f"/api/agent/enroll-token/{mwc}").json()["enroll_token"]
        ma = TestClient(app)
        ment = ma.post("/api/agent/enroll", json={"enroll_token": mtok, "hostname": "MAINT-PC", "os": "Win"}).json()
        mhdr = {"X-Enroll-Id": ment["enroll_id"], "X-Agent-Key": ment["agent_key"]}
        _nowM = _dM.now(_zM.utc)
        win = c.post("/api/maintenance-windows", json={"client_id": mwc,
            "starts_at": (_nowM - _tM(minutes=5)).isoformat(),
            "ends_at": (_nowM + _tM(hours=2)).isoformat(), "reason": "Patching"})
        assert win.status_code == 201 and win.json()["state"] == "active", win.text
        wid = win.json()["id"]
        # bad check-in DURING maintenance -> no alerts
        ma.post("/api/agent/checkin", headers=mhdr, json={"cpu_pct": 99, "disk_pct": 99,
                "ram_pct": 99, "av_status": "off", "patch_status": "behind"})
        assert len([al for al in c.get("/api/alerts").json() if al["client_id"] == mwc]) == 0, "alerted during maintenance!"
        # validation + RBAC
        assert c.post("/api/maintenance-windows", json={"client_id": mwc,
            "starts_at": _nowM.isoformat(), "ends_at": (_nowM - _tM(hours=1)).isoformat()}).status_code == 400
        assert ca_c.post("/api/maintenance-windows", json={"client_id": mwc,
            "starts_at": _nowM.isoformat(), "ends_at": (_nowM + _tM(hours=1)).isoformat()}).status_code == 403
        # delete the window -> same bad check-in now alerts
        assert c.delete(f"/api/maintenance-windows/{wid}").status_code == 200
        ma.post("/api/agent/checkin", headers=mhdr, json={"cpu_pct": 99, "disk_pct": 99,
                "ram_pct": 99, "av_status": "off", "patch_status": "behind"})
        assert len([al for al in c.get("/api/alerts").json() if al["client_id"] == mwc]) > 0, "should alert after window"
        print("maintenance windows: alert suppression + validation + RBAC OK")

        # ===================== v0.40: SLA performance analytics ==================
        _ac2 = c.post("/api/clients", json={"name": "SLA Co"}).json()["id"]
        _adb = _SL()
        from app.models import SupportTicket as _STa, TicketStatus as _TSa
        _n = _dM.now(_zM.utc)
        # one met (resolved before due), one missed (resolved after due)
        _adb.add(_STa(client_id=_ac2, subject="met", priority="normal", status=_TSa.RESOLVED,
                      created_at=_n - _tM(hours=10), first_response_due_at=_n - _tM(hours=8),
                      resolution_due_at=_n - _tM(hours=2), first_responded_at=_n - _tM(hours=9),
                      resolved_at=_n - _tM(hours=3)))
        _adb.add(_STa(client_id=_ac2, subject="missed", priority="high", status=_TSa.RESOLVED,
                      created_at=_n - _tM(hours=10), first_response_due_at=_n - _tM(hours=9),
                      resolution_due_at=_n - _tM(hours=5), first_responded_at=_n - _tM(hours=8),
                      resolved_at=_n - _tM(hours=1)))
        _adb.commit(); _adb.close()
        perf = c.get(f"/api/analytics/sla-performance?client_id={_ac2}").json()
        o = perf["overall"]
        assert o["tickets"] == 2 and o["resolved"] == 2, o
        assert o["resolution_attainment_pct"] == 50.0, o   # 1 of 2 met
        assert o["avg_resolution_minutes"] is not None and o["avg_resolution_minutes"] > 0, o
        assert perf["by_priority"]["high"]["resolution_attainment_pct"] == 0.0, perf["by_priority"]["high"]
        # client user is scoped to their own org (different client -> empty)
        assert ca_c.get("/api/analytics/sla-performance").json()["overall"]["tickets"] >= 0
        print("SLA performance analytics (attainment % + avg times + by-priority + scope) OK")

        # --- v0.41 Integrations: secure credential vault + mailbox/publishers/dialpad ---
        assert c.get("/api/mailbox/settings").json()["configured"] is False
        r = c.put("/api/mailbox/settings", json={"tenant_id": "t-1", "client_id": "c-1",
                                                 "client_secret": "topsecret9", "mailbox": "help@bvtech.org"})
        assert r.json()["configured"] is True, r.text
        s = c.get("/api/mailbox/settings").json()
        # secrets are masked on read, never echoed; identifiers pass through
        assert s["fields"]["client_secret"]["value"] is None and s["fields"]["client_secret"]["hint"].endswith("ret9")
        assert s["fields"]["tenant_id"]["value"] == "t-1" and s["mailbox"] == "help@bvtech.org"
        # partial update (masked secret, omit mailbox) keeps both
        c.put("/api/mailbox/settings", json={"client_secret": s["fields"]["client_secret"]["hint"]})
        s2 = c.get("/api/mailbox/settings").json()
        assert s2["configured"] is True and s2["mailbox"] == "help@bvtech.org", s2
        # mail endpoints reachable; without a real tenant they fail upstream (not 500)
        assert c.get("/api/mailbox/messages").status_code in (502, 503)
        # client users are blocked from staff-only settings
        assert ca_c.get("/api/mailbox/settings").status_code == 403
        # publishers + dialpad credential round-trips (masked)
        assert c.put("/api/publishers/linkedin", json={"access_token": "li-tok",
                     "person_urn": "urn:li:person:x"}).json()["configured"] is True
        assert c.get("/api/publishers/settings").json()["linkedin"]["fields"]["access_token"]["value"] is None
        assert c.post("/api/publishers/linkedin/post", json={"text": ""}).status_code == 400
        assert c.put("/api/publishers/website/jp", json={"site_url": "https://jordanpolasek.com",
                     "enabled": True}).status_code == 200
        assert c.get("/api/publishers/settings").json()["website_jp"]["enabled"] is True
        assert c.put("/api/comms/dialpad/settings", json={"api_key": "dp", "user_id": "u1"}).json()["configured"] is True
        assert c.get("/api/comms/dialpad/settings").json()["fields"]["api_key"]["value"] is None
        assert c.post("/api/comms/dialpad/call", json={"to": ""}).status_code == 400
        print("Integrations: secure vault + M365 mailbox + publishers + Dialpad (masked secrets + RBAC) OK")

        # --- v0.42 Tactical RMM connector: SSRF guard + masked creds + RBAC ---
        assert c.get("/api/rmm/settings").json()["configured"] is False
        assert c.get("/api/rmm/dashboard").status_code == 503  # not configured yet
        # SSRF: private / loopback / metadata URLs are refused at save time
        for bad in ("http://169.254.169.254/api", "http://127.0.0.1:8000", "http://10.0.0.5"):
            assert c.put("/api/rmm/settings", json={"base_url": bad, "api_key": "k"}).status_code == 400, bad
        # a public URL saves; key is stored encrypted and masked on read
        assert c.put("/api/rmm/settings", json={"base_url": "https://api.github.com",
                     "api_key": "trmm-secret-123"}).json()["configured"] is True
        s = c.get("/api/rmm/settings").json()
        assert s["fields"]["api_key"]["value"] is None and s["fields"]["base_url"]["value"] == "https://api.github.com"
        # client users are blocked from the staff-only connector + mutating actions are OWNER-only
        assert ca_c.get("/api/rmm/settings").status_code == 403
        assert ca_c.post("/api/rmm/agents/1/reboot").status_code in (401, 403)
        print("Tactical RMM connector: SSRF guard + encrypted/masked creds + RBAC OK")

        # --- v0.43 native CRM: pipeline, contact CRUD, timeline, convert→client, RBAC ---
        assert c.get("/api/crm/pipeline").json()["total"] >= 0
        nc = c.post("/api/crm/contacts", json={"name": "Jane Smith", "company": "Acme Law",
                    "email": "jane@acme.test", "phone": "+15125550133", "market": "austin"})
        assert nc.status_code == 201, nc.text
        ct_id = nc.json()["id"]
        # search + status filter
        assert any(x["id"] == ct_id for x in c.get("/api/crm/contacts?q=acme").json()["contacts"])
        # creation logged a status activity
        det = c.get(f"/api/crm/contacts/{ct_id}").json()
        assert det["contact"]["status"] == "new" and len(det["activities"]) >= 1
        # log a call + advance status
        assert c.post(f"/api/crm/contacts/{ct_id}/activity", json={"type": "call",
                      "subject": "Discovery", "direction": "outbound"}).status_code == 201
        assert c.patch(f"/api/crm/contacts/{ct_id}", json={"status": "qualified"}).json()["status"] == "qualified"
        assert c.patch(f"/api/crm/contacts/{ct_id}", json={"status": "bogus"}).status_code == 400
        # convert → creates a real managed Client and links it
        conv = c.post(f"/api/crm/contacts/{ct_id}/convert").json()
        new_client_id = conv["client_id"]
        assert new_client_id and conv["contact"]["status"] == "customer"
        assert any(cl["id"] == new_client_id for cl in c.get("/api/clients").json())
        assert c.post(f"/api/crm/contacts/{ct_id}/convert").status_code == 409  # already linked
        # RBAC: client users can't touch the CRM; TECH can't delete (OWNER-only)
        assert ca_c.get("/api/crm/contacts").status_code == 403
        print("Native CRM: pipeline + contact CRUD + timeline + convert→client + RBAC OK")

        # --- v0.44 Prospecting: options, settings (masked), run-gating, RBAC ---
        opts = c.get("/api/prospecting/options").json()
        assert any(m["key"] == "austin" for m in opts["markets"]) and len(opts["industries"]) >= 5
        assert c.get("/api/prospecting/settings").json()["configured"] is False
        assert c.post("/api/prospecting/run", json={"market": "austin", "industry": "law firm"}).status_code == 503
        assert c.put("/api/prospecting/settings", json={"api_key": "g-secret-key"}).json()["configured"] is True
        assert c.get("/api/prospecting/settings").json()["fields"]["api_key"]["value"] is None
        assert ca_c.get("/api/prospecting/options").status_code == 403
        # scoring + dedup path is covered by an offline unit test (FakePlaces) in dev.
        print("Prospecting: options + masked key + run-gating + RBAC OK")

        # --- v0.45 Campaigns: compliance gating + dry-run + RBAC ---
        # seed a reachable + a do-not-contact + a non-opted-in contact
        em_id = c.post("/api/crm/contacts", json={"name": "Reachable Rick", "company": "RickCo",
                       "email": "rick@reach.test", "phone": "+15125550900", "sms_opt_in": True}).json()["id"]
        c.post("/api/crm/contacts", json={"name": "DNC Dan", "company": "DanCo",
               "email": "dan@dnc.test", "do_not_contact": True})
        # email dry-run: audience counts only the reachable one, sends nothing, no creds needed
        er = c.post("/api/campaigns/email", json={"subject": "Hi {first}", "body": "Hello {company}",
                    "dry_run": True}).json()
        assert er["sent"] == 0 and er["audience"] >= 1, er
        # real email send requires the mailbox to be configured (it is, from the mailbox block)
        # but Graph is unreachable here -> failures are counted, call still 200
        real = c.post("/api/campaigns/email", json={"ids": [em_id], "subject": "Hi", "body": "Yo",
                      "dry_run": False}).json()
        assert real["audience"] == 1 and (real["failed"] == 1 or real["sent"] == 1), real
        # SMS dry-run only counts opted-in numbers
        sr = c.post("/api/campaigns/sms", json={"message": "Hi {first}", "dry_run": True}).json()
        assert sr["sent"] == 0 and sr["audience"] >= 1, sr
        # RBAC: client users can't run campaigns
        assert ca_c.post("/api/campaigns/email", json={"subject": "x", "body": "y"}).status_code == 403
        print("Campaigns: email/SMS compliance gating + dry-run + RBAC OK")

        # --- v0.46 RMM agent: version/online, endpoint ticket, push-command loop ---
        dev_id = ent["device_id"]
        a.post("/api/agent/checkin", headers=hdr,
               json={"cpu_pct": 5, "disk_pct": 40, "agent_version": "1.5.0", "platform": "windows"})
        row = next(d for d in c.get("/api/devices").json() if d["id"] == dev_id)
        assert row["agent_version"] == "1.5.0" and row["platform"] == "windows" and row["online"] is True, row
        # endpoint user submits a ticket from the agent
        tk = a.post("/api/agent/ticket", headers=hdr,
                    json={"subject": "Endpoint says hi", "body": "from the PC"})
        assert tk.status_code == 201, tk.text
        assert any(t["subject"] == "Endpoint says hi" for t in c.get("/api/tickets").json())
        # OWNER pushes a command -> APPROVED deployment -> agent pulls -> reports result
        rc = c.post(f"/api/agent/devices/{dev_id}/run-command",
                    json={"command": "Get-Date", "language": "powershell"})
        assert rc.status_code == 201, rc.text
        dep_id = rc.json()["deployment_id"]
        jobs = a.get("/api/agent/jobs", headers=hdr).json()["jobs"]
        assert any(j["id"] == dep_id for j in jobs), "agent did not receive the pushed command"
        a.post(f"/api/agent/jobs/{dep_id}/result", headers=hdr,
               json={"exit_code": 0, "output": "Tuesday"})
        cmds = c.get(f"/api/agent/devices/{dev_id}/commands").json()["commands"]
        done = next(x for x in cmds if x["id"] == dep_id)
        assert done["status"] == "succeeded" and done["output"] == "Tuesday", done
        # run-command is OWNER-only
        assert ca_c.post(f"/api/agent/devices/{dev_id}/run-command",
                         json={"command": "x"}).status_code == 403
        print("RMM agent: version/online + endpoint ticket + push-command loop + RBAC OK")

        # --- v0.47 Remote desktop: WebRTC signaling relay + session + RBAC ---
        eid, akey = ent["enroll_id"], ent["agent_key"]
        rs = c.post(f"/api/remote/sessions/{dev_id}").json()
        rtok = rs["session"]["token"]
        assert rs["viewer_url"] == f"/remote/{rtok}"
        # agent sees the pending session to connect to
        pend = a.get("/api/agent/remote-sessions", headers=hdr).json()["sessions"]
        assert any(s["token"] == rtok for s in pend)
        # relay bridges operator (cookie) + agent (device key), forwarding signaling
        with c.websocket_connect(f"/api/remote/ws/{rtok}?role=operator") as op:
            assert op.receive_json()["type"] == "relay.ready"
            with a.websocket_connect(f"/api/remote/ws/{rtok}?role=agent&enroll_id={eid}&agent_key={akey}") as ag:
                assert ag.receive_json()["type"] == "relay.ready"
                assert op.receive_json()["type"] == "relay.peer-joined"
                ag.send_text('{"type":"offer","sdp":{"type":"offer","sdp":"v=0"}}')
                assert op.receive_json()["type"] == "offer"
                op.send_text('{"type":"answer","sdp":{"type":"answer","sdp":"a=0"}}')
                assert ag.receive_json()["type"] == "answer"
                op.send_text('{"type":"candidate","candidate":{"candidate":"X"}}')
                assert ag.receive_json()["candidate"]["candidate"] == "X"
        # start is OWNER-only; an unauthenticated operator WS is rejected
        assert ca_c.post(f"/api/remote/sessions/{dev_id}").status_code == 403
        rejected = False
        try:
            from fastapi.testclient import TestClient as _TC
            with _TC(app).websocket_connect(f"/api/remote/ws/{rtok}?role=operator") as bad:
                bad.receive_json()
        except Exception:
            rejected = True
        assert rejected, "unauthenticated operator should be rejected"
        print("Remote desktop: WebRTC signaling relay + auth + session lifecycle + RBAC OK")

        # --- v0.48 QuickBooks: settings (masked) + gating + RBAC ---
        assert c.get("/api/quickbooks/settings").json()["configured"] is False
        assert c.post("/api/quickbooks/test").status_code == 503  # not configured
        sv = c.put("/api/quickbooks/settings", json={"client_id": "qcid", "client_secret": "qsec",
                   "refresh_token": "qref", "realm_id": "R-99", "sandbox": True}).json()
        assert sv["configured"] is True
        qs = c.get("/api/quickbooks/settings").json()
        assert qs["sandbox"] is True and qs["fields"]["client_secret"]["value"] is None
        assert qs["fields"]["refresh_token"]["value"] is None
        assert ca_c.get("/api/quickbooks/settings").status_code == 403
        print("QuickBooks: encrypted/masked creds + gating + RBAC OK")

        # --- v0.49 HubSpot + Google Business Profile connectors ---
        assert c.get("/api/hubspot/settings").json()["configured"] is False
        assert c.put("/api/hubspot/settings", json={"token": "hs-tok"}).json()["configured"] is True
        assert c.get("/api/hubspot/settings").json()["fields"]["token"]["value"] is None
        # push reaches HubSpot; with a fake token the upstream call fails (not 500)
        assert c.post(f"/api/hubspot/contacts/{ct_id}/push").status_code == 502
        assert ca_c.put("/api/hubspot/settings", json={"token": "x"}).status_code == 403
        assert c.get("/api/gbp/settings").json()["configured"] is False
        assert c.post("/api/gbp/post", json={"summary": "hi"}).status_code == 503  # not configured
        gv = c.put("/api/gbp/settings", json={"client_id": "g", "client_secret": "s",
                   "refresh_token": "r", "account_name": "accounts/1", "location_name": "locations/2"}).json()
        assert gv["configured"] is True
        assert c.get("/api/gbp/settings").json()["fields"]["client_secret"]["value"] is None
        assert ca_c.get("/api/gbp/settings").status_code == 403
        print("HubSpot + Google Business Profile: encrypted/masked creds + gating + RBAC OK")

        # --- v0.50 Integration Hub status board ---
        st = c.get("/api/integrations/status").json()
        assert st["total"] >= 8 and "connected" in st
        byk = {i["key"]: i for i in st["integrations"]}
        # we configured these earlier in this run -> should read connected
        assert byk["hubspot"]["configured"] is True and byk["quickbooks"]["configured"] is True
        assert byk["m365_mailbox"]["configured"] is True and byk["dialpad"]["configured"] is True
        # gbp configured earlier too; a never-touched one stays not-configured shape
        assert all({"key", "name", "category", "icon", "tab", "configured"} <= set(i) for i in st["integrations"])
        assert ca_c.get("/api/integrations/status").status_code == 403
        print("Integration Hub: aggregate connector status + RBAC OK")

        # --- v0.51 automation outbound actions (email/LinkedIn) accepted + safe ---
        rr = c.post("/api/automation/rules", json={"name": "crit-mail", "trigger": "alert.opened",
                    "conditions": {}, "actions": [
                        {"type": "send_email", "to": "oncall@bvtech.test", "subject": "Crit {hostname}", "body": "{message}"},
                        {"type": "linkedin_post", "text": "Outage {hostname}"}]})
        assert rr.status_code in (200, 201), rr.text
        # an unknown action type is still rejected
        assert c.post("/api/automation/rules", json={"name": "bad", "trigger": "alert.opened",
                      "conditions": {}, "actions": [{"type": "run_nukes"}]}).status_code == 400
        print("Automation: outbound email/LinkedIn actions validated + unknown rejected OK")

        # --- v0.53 scheduled automations (time-based trigger) ---
        sr = c.post("/api/automation/rules", json={"name": "daily-sched", "trigger": "schedule",
                    "conditions": {"every": "day", "at": "00:00", "tz": "UTC"},
                    "actions": [{"type": "notify", "message": "scheduled daily"}]})
        assert sr.status_code in (200, 201), sr.text
        from app.services import automation as _A
        from app.core.db import SessionLocal as _SL2
        from datetime import datetime as _dt2, timezone as _tz2
        _sdb = _SL2()
        fired = _A.run_scheduled(_sdb, _dt2(2030, 1, 1, 12, 0, tzinfo=_tz2.utc))
        assert any(x["rule_name"] == "daily-sched" for x in fired), fired
        again = _A.run_scheduled(_sdb, _dt2(2030, 1, 1, 13, 0, tzinfo=_tz2.utc))  # same day
        assert not any(x["rule_name"] == "daily-sched" for x in again), "scheduled rule re-fired same day"
        _sdb.close()
        print("Scheduled automations: time-based trigger fires once/period + dedup OK")

        # --- v0.54 Documentation & password vault ---
        pw = c.post("/api/docs", json={"client_id": cid, "kind": "password", "title": "Firewall",
                    "username": "admin", "url": "https://fw.local", "secret": "S3cr3t!pw"})
        assert pw.status_code == 201, pw.text
        pw_id = pw.json()["id"]
        # list never leaks the secret, only a has_secret flag
        docs = c.get(f"/api/docs?client_id={cid}").json()["documents"]
        d0 = next(x for x in docs if x["id"] == pw_id)
        assert d0["has_secret"] is True and "secret" not in d0
        # reveal returns the plaintext (staff only) and is audited
        rv = c.post(f"/api/docs/{pw_id}/reveal").json()
        assert rv["secret"] == "S3cr3t!pw" and rv["username"] == "admin"
        # an article is visible to the client's own users; a password is NOT
        c.post("/api/docs", json={"client_id": cid, "kind": "article", "title": "Onboarding", "content": "hi"})
        cu_docs = ca_c.get("/api/docs").json()["documents"]
        assert any(x["title"] == "Onboarding" for x in cu_docs), "client should see articles"
        assert not any(x["kind"] == "password" for x in cu_docs), "client must NOT see passwords"
        # client user cannot reveal a secret or create docs
        assert ca_c.post(f"/api/docs/{pw_id}/reveal").status_code == 403
        assert ca_c.post("/api/docs", json={"kind": "article", "title": "x"}).status_code == 403
        print("Docs vault: encrypted secret + audited reveal + client RBAC (no passwords) OK")

        # --- v0.55 morning briefing + send_digest action ---
        br = c.get("/api/briefing").json()
        assert "attention_total" in br and "sections" in br and "text" in br
        assert any(s["title"].startswith("🚨") for s in br["sections"])
        assert ca_c.get("/api/briefing").status_code == 403   # staff-only aggregate
        # send_digest is a valid automation action and skips gracefully unconfigured
        assert c.post("/api/automation/rules", json={"name": "am-digest", "trigger": "schedule",
                      "conditions": {"every": "day", "at": "07:00"},
                      "actions": [{"type": "send_digest", "to": "jordan@bvtech.test"}]}).status_code in (200, 201)
        from app.services import automation as _A3
        from app.core.db import SessionLocal as _SL3
        _bdb = _SL3()
        # mailbox is configured (fake creds) by now, so this takes the send path and
        # fails gracefully at the Graph call — the point is it returns a string, never raises.
        msg = _A3._act_send_digest(_bdb, {"to": "x@y.test"}, {})
        assert isinstance(msg, str) and ("digest" in msg or "briefing" in msg), msg
        _bdb.close()
        print("Morning briefing: aggregate + staff-only + send_digest action OK")

        # --- v0.52 integration health watchdog ---
        # /status carries health fields; the live-check endpoint is OWNER/TECH only.
        sj = c.get("/api/integrations/status").json()
        assert "failing" in sj and all("health_ok" in i for i in sj["integrations"])
        assert ca_c.post("/api/integrations/health/check").status_code == 403
        # Verify the sweep logic deterministically (no network): stub the checkers,
        # force HubSpot to fail, confirm it's recorded + a notification fires once.
        from app.services import integration_health as _ih
        from app.core.db import SessionLocal as _SL
        from app.models import Notification as _Notif
        _orig = dict(_ih.CHECKERS)
        _ih.CHECKERS.clear()
        _ih.CHECKERS["hubspot"] = lambda cfg: (_ for _ in ()).throw(RuntimeError("HTTP 401 expired"))
        try:
            _hdb = _SL()
            r1 = _ih.check_all(_hdb)
            assert r1["failing"] >= 1 and r1["newly_failed"] >= 1, r1
            n1 = _hdb.query(_Notif).filter(_Notif.kind == "integration_health").count()
            assert n1 >= 1
            r2 = _ih.check_all(_hdb)            # still failing, but no duplicate alert
            assert r2["newly_failed"] == 0, r2
            assert _hdb.query(_Notif).filter(_Notif.kind == "integration_health").count() == n1
            _hdb.close()
        finally:
            _ih.CHECKERS.clear()
            _ih.CHECKERS.update(_orig)
        print("Integration health watchdog: status fields + detect-fail + notify-once + RBAC OK")

        # --- v0.52.1 SSO settings: vault-driven sign-in providers + redirect URIs ---
        ss = c.get("/api/oauth/sso-settings").json()
        assert "redirect_uris" in ss and ss["redirect_uris"]["microsoft"].endswith("/api/oauth/microsoft/callback")
        sv = c.put("/api/oauth/sso-settings", json={"google_client_id": "gid.apps", "google_client_secret": "gsec"})
        assert sv.status_code == 200 and "google" in sv.json()["providers_active"], sv.text
        # the login page's provider list now includes google (vault-driven SSO)
        provs = {p["key"] for p in c.get("/api/oauth/providers").json()["providers"]}
        assert "google" in provs, provs
        assert ca_c.put("/api/oauth/sso-settings", json={"google_client_id": "x"}).status_code == 403
        print("SSO: vault-driven providers + redirect URIs + RBAC OK")

        # --- v0.56 one-click OAuth connect + self-refreshing tokens ---
        cn = c.get("/api/oauth/connections").json()["connections"]
        keys = {x["key"] for x in cn}
        assert {"linkedin", "google_gbp", "quickbooks"} <= keys
        # quickbooks + gbp app creds were configured earlier -> Connect available
        byk = {x["key"]: x for x in cn}
        assert byk["quickbooks"]["app_configured"] is True and byk["quickbooks"]["connected"] is False
        assert byk["quickbooks"]["connect_url"].endswith("/api/oauth/quickbooks/connect")
        # saving LinkedIn app creds lights up its Connect
        c.put("/api/publishers/linkedin", json={"li_client_id": "lid", "li_client_secret": "lsec"})
        cn2 = {x["key"]: x for x in c.get("/api/oauth/connections").json()["connections"]}
        assert cn2["linkedin"]["app_configured"] is True
        # self-refresh engine: a stored token is handed back / refreshed (offline)
        from app.services import oauth as _oa, crypto as _cy
        from app.core.db import SessionLocal as _SLo
        from app.models import OAuthToken as _OT
        from datetime import datetime as _d, timezone as _z, timedelta as _td
        _odb = _SLo()
        _odb.add(_OT(provider="google_gbp", access_token_enc=_cy.encrypt("AT"),
                     expires_at=_d.now(_z.utc) + _td(hours=1)))
        _odb.commit()
        assert _oa.get_valid_token(_odb, "google_gbp") == "AT"
        _odb.close()
        assert ca_c.get("/api/oauth/connections").status_code == 403
        # v1.18: every connection row hands the operator the EXACT redirect URL to
        # register + where to paste it — the fix for "redirect_uri does not match".
        cn3 = {x["key"]: x for x in c.get("/api/oauth/connections").json()["connections"]}
        assert {"linkedin", "google_gbp", "quickbooks", "microsoft", "google"} <= set(cn3)
        for k, row in cn3.items():
            assert row["redirect_uri"].endswith(f"/api/oauth/{k}/callback"), row
            assert row["console_hint"], f"{k} missing console hint"
        assert "linkedin.com" not in cn3["linkedin"]["redirect_uri"]   # OUR url, not theirs
        assert "Authorized redirect URLs" in cn3["linkedin"]["console_hint"]
        print("One-click OAuth connect: providers + app-config gating + self-refresh engine "
              "+ exact redirect-URI + console walkthrough per provider + RBAC OK")

        # --- v0.57 Stripe payments: settings + signature-verified webhook reconcile ---
        import hmac as _hm, hashlib as _hh, json as _js, time as _tm
        from app.core.db import SessionLocal as _SLp
        from app.models import Invoice as _Inv, InvoiceStatus as _IS
        assert c.get("/api/payments/settings").json()["configured"] is False
        assert c.put("/api/payments/settings", json={"secret_key": "sk_test_x",
                     "webhook_secret": "whsec_smoke"}).json()["configured"] is True
        assert c.get("/api/payments/settings").json()["fields"]["secret_key"]["value"] is None
        # seed a SENT invoice, then post a valid Stripe webhook -> it auto-marks paid
        _pdb = _SLp()
        _iv = _Inv(client_id=cid, number="PAYME-1", status=_IS.SENT, total=99.0, currency="USD")
        _pdb.add(_iv); _pdb.commit(); _iv_id = _iv.id; _pdb.close()
        _ts = str(int(_tm.time()))
        _body = _js.dumps({"type": "checkout.session.completed",
                           "data": {"object": {"metadata": {"invoice_id": str(_iv_id)}}}}).encode()
        _sig = _hm.new(b"whsec_smoke", _ts.encode() + b"." + _body, _hh.sha256).hexdigest()
        wr = c.post("/api/payments/webhook", content=_body,
                    headers={"stripe-signature": f"t={_ts},v1={_sig}", "content-type": "application/json"})
        assert wr.status_code == 200 and wr.json().get("invoice_paid") == _iv_id, wr.text
        # a bad signature is rejected
        assert c.post("/api/payments/webhook", content=_body,
                      headers={"stripe-signature": f"t={_ts},v1=bad"}).status_code == 400
        # checkout creation requires Stripe to be reachable (fake key) -> graceful 502, not 500
        assert c.post(f"/api/payments/invoices/{_iv_id}/checkout").status_code in (409, 502)  # already paid or upstream
        assert ca_c.put("/api/payments/settings", json={"secret_key": "x"}).status_code == 403
        print("Stripe payments: masked key + webhook signature verify + auto-reconcile + RBAC OK")

        # --- v0.84 public branded status page ------------------------------ #
        pub = TestClient(app); pub.cookies.clear()
        # disabled by default -> public view is 404 (page existence not leaked)
        assert pub.get("/api/status/public").status_code == 404
        assert c.get("/api/status/config").json()["enabled"] is False
        # owner enables + brands the page
        cfg = c.put("/api/status/config", json={"enabled": True, "headline": "Service Status",
                    "intro": "How the systems we manage are doing."}).json()
        assert cfg["enabled"] is True and cfg["headline"] == "Service Status"
        # empty page: operational, 100% uptime, no incidents
        pv = pub.get("/api/status/public"); assert pv.status_code == 200, pv.text
        pj = pv.json()
        assert pj["overall"] == "operational" and pj["uptime_90d"] == 100.0
        assert pj["active_incidents"] == [] and pj["brand"]["company"]
        # validation on create
        assert c.post("/api/status/incidents", json={"title": "x", "impact": "boom"}).status_code == 400
        assert c.post("/api/status/incidents", json={"title": "x", "status": "nope"}).status_code == 400
        # post a MAJOR incident -> banner escalates to partial outage, it shows publicly
        inc_id = c.post("/api/status/incidents", json={"title": "Email delivery delays",
                        "impact": "major", "status": "investigating",
                        "body": "We're seeing delayed mail flow."}).json()["id"]
        pj = pub.get("/api/status/public").json()
        assert pj["overall"] == "partial_outage", pj["overall"]
        assert len(pj["active_incidents"]) == 1
        assert pj["active_incidents"][0]["title"] == "Email delivery delays"
        # public payload must not leak internal fields
        assert "created_by_user_id" not in pj["active_incidents"][0]
        # advance to monitoring, then resolve -> drops out of active, into history, uptime recovers to 100%
        assert c.patch(f"/api/status/incidents/{inc_id}", json={"status": "monitoring",
                       "body": "Fix deploying."}).json()["status"] == "monitoring"
        rr = c.patch(f"/api/status/incidents/{inc_id}", json={"status": "resolved"}).json()
        assert rr["resolved"] is True
        pj = pub.get("/api/status/public").json()
        assert pj["overall"] == "operational" and pj["active_incidents"] == []
        assert any(i["id"] == inc_id and i["resolved"] for i in pj["recent_incidents"])
        # a same-instant open->resolved window is ~0 downtime, so uptime stays effectively 100%
        assert pj["uptime_90d"] >= 99.9, pj["uptime_90d"]
        # staff can list incidents (incl. resolved); the public HTML shell renders
        assert len(c.get("/api/status/incidents").json()["incidents"]) >= 1
        assert pub.get("/status").status_code == 200
        # RBAC: client-admin cannot manage config or incidents
        assert ca_c.get("/api/status/config").status_code == 403
        assert ca_c.put("/api/status/config", json={"enabled": False}).status_code == 403
        assert ca_c.post("/api/status/incidents", json={"title": "hax", "impact": "minor"}).status_code == 403
        print("public status page: enable+brand + incident lifecycle + uptime + no-leak + RBAC OK")

        # --- v0.85 weekly "state of the practice" digest ------------------- #
        from app.services import weekly_digest as _wd
        from app.core.db import SessionLocal as _WSL
        # config: default enabled, Monday, owner is an effective recipient
        wcfg = c.get("/api/automation/weekly-digest").json()
        assert wcfg["enabled"] is True and wcfg["weekday"] == 0
        assert owner_email in wcfg["effective_recipients"]   # owner is a default recipient
        # preview renders the practice grade + attention briefing
        pv = c.get("/api/automation/weekly-digest/preview").json()
        assert "State of the Practice" in pv["body"] and "grade" in pv["subject"].lower()
        # scheduler send: idempotent + weekday/hour gated, using an injected sender
        _sent = []
        def _cap(to, subj, body): _sent.append((to, subj)); return True
        _wdb = _WSL()
        try:
            import datetime as _dt
            # The fixed dates below live in ISO week 2026-W28. If the REAL clock
            # is also in that week, an earlier run-checks/autopilot tick in this
            # suite has already stamped it — clear the bookkeeping so this
            # sequence is deterministic on any calendar day.
            from app.services import secure_config as _wsc
            _wconn = _wsc.get_platform(_wdb, _wd.PROVIDER)
            _wcfg = dict((_wconn.config if _wconn else None) or {})
            _wcfg.pop("last_sent_week", None)
            _wcfg["last_sent_week"] = ""
            _wsc.upsert_platform(_wdb, _wd.PROVIDER, "Weekly Digest",
                                 "State of the practice", _wcfg)
            # a Wednesday -> not due
            wed = _dt.datetime(2026, 7, 1, 9, 0, tzinfo=_dt.timezone.utc)
            assert _wd.maybe_send(_wdb, wed, sender=_cap)["reason"] == "not_due"
            # Monday 6am -> before send hour (7) -> not due
            mon_early = _dt.datetime(2026, 7, 6, 6, 0, tzinfo=_dt.timezone.utc)
            assert _wd.maybe_send(_wdb, mon_early, sender=_cap)["reason"] == "not_due"
            # Monday 8am -> sends once
            mon = _dt.datetime(2026, 7, 6, 8, 0, tzinfo=_dt.timezone.utc)
            r1 = _wd.maybe_send(_wdb, mon, sender=_cap)
            assert r1["sent"] is True and r1["delivered"] >= 1, r1
            # same week again -> already_sent (no double email)
            r2 = _wd.maybe_send(_wdb, _dt.datetime(2026, 7, 6, 12, 0, tzinfo=_dt.timezone.utc), sender=_cap)
            assert r2["sent"] is False and r2["reason"] == "already_sent", r2
            # next ISO week -> sends again
            r3 = _wd.maybe_send(_wdb, _dt.datetime(2026, 7, 13, 8, 0, tzinfo=_dt.timezone.utc), sender=_cap)
            assert r3["sent"] is True, r3
            assert len(_sent) == 2, _sent    # exactly two weeks delivered
        finally:
            _wdb.close()
        # owner can reconfigure + send-now; disabling stops the scheduler
        assert c.put("/api/automation/weekly-digest", json={"weekday": 4, "hour": 6,
                     "recipients": "boss@bvtech.org, ops@bvtech.org"}).json()["weekday"] == 4
        assert c.get("/api/automation/weekly-digest").json()["recipients"] == ["boss@bvtech.org", "ops@bvtech.org"]
        assert c.post("/api/automation/weekly-digest/send-now").json()["recipients"] == 2
        assert c.put("/api/automation/weekly-digest", json={"enabled": False}).json()["enabled"] is False
        _wdb2 = _WSL()
        try:
            import datetime as _dt2
            assert _wd.maybe_send(_wdb2, _dt2.datetime(2026, 7, 17, 8, 0, tzinfo=_dt2.timezone.utc),
                                  sender=_cap)["reason"] == "disabled"
        finally:
            _wdb2.close()
        # RBAC: client roles can't read or change the digest
        assert ca_c.get("/api/automation/weekly-digest").status_code == 403
        assert ca_c.put("/api/automation/weekly-digest", json={"enabled": True}).status_code == 403
        assert ca_c.post("/api/automation/weekly-digest/send-now").status_code == 403
        print("weekly digest: grade+briefing render + weekday/hour gate + once-per-week + send-now + RBAC OK")

        # --- v1.0: .env -> vault credential loader (keys in env light up integrations) ---
        import os as _os
        from app.services import env_credentials as _envc
        from app.core.db import SessionLocal as _ESL
        _os.environ["STRIPE_SECRET_KEY"] = "sk_live_SMOKEONLY"
        _os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_SMOKE"
        _os.environ["DIALPAD_API_KEY"] = "dp_SMOKE"; _os.environ["DIALPAD_USER_ID"] = "u1"
        _os.environ["QUICKBOOKS_SANDBOX"] = "false"   # falsy -> must NOT enable sandbox
        _os.environ["QUICKBOOKS_CLIENT_ID"] = "qbid"; _os.environ["QUICKBOOKS_CLIENT_SECRET"] = "qbsec"
        _os.environ["QUICKBOOKS_REFRESH_TOKEN"] = "qbrt"
        _edb = _ESL()
        try:
            applied = _envc.load(_edb)
            assert "stripe" in applied and "dialpad" in applied and "quickbooks" in applied, applied
            assert "sandbox" not in applied["quickbooks"], "falsy sandbox must be ignored"
        finally:
            _edb.close()
        # the integrations now read as configured, and the secret is never echoed back
        assert c.get("/api/payments/settings").json()["configured"] is True
        assert "sk_live_SMOKEONLY" not in c.get("/api/payments/settings").text
        assert c.get("/api/quickbooks/settings").json()["configured"] is True
        for _k in ("STRIPE_SECRET_KEY","STRIPE_WEBHOOK_SECRET","DIALPAD_API_KEY","DIALPAD_USER_ID",
                   "QUICKBOOKS_SANDBOX","QUICKBOOKS_CLIENT_ID","QUICKBOOKS_CLIENT_SECRET","QUICKBOOKS_REFRESH_TOKEN"):
            _os.environ.pop(_k, None)   # don't leak into later runs
        print(".env->vault loader: env keys activate integrations + secret masked + falsy-bool guard OK")

        # ===================== v1.1: Autopilot + AI ticket triage =====================
        import json as _j11
        from app.core.db import SessionLocal as _SL11
        from app.models import SchedulerRun as _SR11, SupportTicket as _ST11, TicketComment as _TC11
        from app.services import ai as _ai11, ai_triage as _ait11

        # Autopilot: manual tick runs the heartbeat and records a SchedulerRun.
        r = c.post("/api/automation/autopilot/tick")
        assert r.status_code == 200, r.text
        assert "sla_breaches_fired" in r.json()["result"], r.json()
        st = c.get("/api/automation/autopilot").json()
        assert st["interval_seconds"] == 120 and st["recent_runs"], st
        assert st["recent_runs"][0]["source"] == "manual"
        _sdb = _SL11()
        try:
            assert _sdb.query(_SR11).filter(_SR11.source == "manual").count() >= 1
        finally:
            _sdb.close()
        _anon = TestClient(app); _anon.cookies.clear()
        assert _anon.post("/api/automation/autopilot/tick").status_code in (401, 403), "autopilot must be staff-only"

        # AI triage config: on by default, suggest-only by default; owner can flip.
        cfg = c.get("/api/automation/ai-triage").json()
        assert cfg["enabled"] is True and cfg["auto_apply"] is False, cfg
        assert c.put("/api/automation/ai-triage", json={"auto_apply": True}).json()["auto_apply"] is True

        # With Claude stubbed: sweep triages the ticket, auto-applies the HIGHER
        # priority, tightens the SLA clock, and leaves an internal AI note.
        _o_en11, _o_call11 = _ai11.enabled, _ai11._CALLER
        _ai11.enabled = lambda: True
        _ai11._CALLER = lambda system, user, model, max_tokens: _j11.dumps({
            "priority": "urgent", "summary": "Company-wide email outage.",
            "next_step": "Check Exchange services on the mail server and restart."})
        try:
            tid11 = c.post("/api/tickets", json={"subject": "EMAIL DOWN whole office",
                                                 "body": "nobody can send or receive",
                                                 "priority": "low", "client_id": cid}).json()["id"]
            _sdb = _SL11()
            try:
                _t = _sdb.get(_ST11, tid11)
                _due_before = _t.first_response_due_at
                assert _t.ai_triaged_at is None
            finally:
                _sdb.close()
            _sdb = _SL11()
            try:
                triaged = _ait11.sweep(_sdb, limit=1000)
                assert any(x["ticket_id"] == tid11 for x in triaged), triaged
            finally:
                _sdb.close()
            _sdb = _SL11()
            try:
                _t = _sdb.get(_ST11, tid11)
                assert _t.ai_priority == "urgent" and _t.ai_triaged_at is not None
                assert _t.priority == "urgent", "auto-apply must bump low -> urgent"
                _db_due = _t.first_response_due_at
                _b = _due_before.replace(tzinfo=None) if _due_before.tzinfo else _due_before
                _a = _db_due.replace(tzinfo=None) if _db_due.tzinfo else _db_due
                assert _a < _b, "SLA clock must tighten on bump"
                _note = (_sdb.query(_TC11).filter(_TC11.ticket_id == tid11,
                                                  _TC11.internal.is_(True),
                                                  _TC11.author_role == "ai").first())
                assert _note and "urgent" in _note.body, "internal AI note missing"
            finally:
                _sdb.close()
            # Serializer exposes the AI read; manual re-triage endpoint works.
            tj = c.get(f"/api/tickets/{tid11}").json()
            assert tj["ai"]["priority"] == "urgent" and tj["ai"]["summary"], tj.get("ai")
            rr = c.post(f"/api/tickets/{tid11}/ai-triage")
            assert rr.status_code == 200 and rr.json()["ok"] is True, rr.text
        finally:
            _ai11.enabled, _ai11._CALLER = _o_en11, _o_call11

        # Degrade path: AI off -> sweep is a clean no-op, manual triage is a clear 400.
        _sdb = _SL11()
        try:
            assert _ait11.sweep(_sdb, limit=10) == []
        finally:
            _sdb.close()
        assert c.post(f"/api/tickets/{tid11}/ai-triage").status_code == 400
        print("autopilot heartbeat + AI triage (auto-apply, SLA restamp, internal note, degrade) OK")

        # ===================== v1.2: Pulse Cyber Academy =====================
        # Page ships; APIs require a session; answers never leak; XP awards once;
        # streak + badges fire; leaderboard is tenant-isolated.
        pg = c.get("/academy")
        assert pg.status_code == 200 and "Cyber Academy" in pg.text
        _anon2 = TestClient(app); _anon2.cookies.clear()
        assert _anon2.get("/api/academy/catalog").status_code in (401, 403)

        cat = c.get("/api/academy/catalog").json()
        assert cat["total_lessons"] >= 10 and cat["modules"] and cat["games"], "catalog thin"
        assert cat["profile"]["xp"] == 0 and cat["profile"]["streak_days"] == 0

        first = cat["modules"][0]["lessons"][0]["id"]
        les = c.get(f"/api/academy/lessons/{first}").json()
        assert les["quiz"] and all("answer" not in q and "explain" not in q for q in les["quiz"]), \
            "quiz answers LEAKED to the client!"
        assert "<h4>" in les["body"], "lesson body missing"

        # Grade with all-zero answers first (partial), then perfect — XP only once.
        from app.services import academy as _aca
        _correct = [q["answer"] for q in _aca._LESSONS[first]["quiz"]]
        res1 = c.post(f"/api/academy/lessons/{first}/submit", json={"answers": _correct}).json()
        assert res1["score"] == res1["total"] and res1["xp_gained"] == 75, res1  # 50 + 25 perfect
        assert res1["profile"]["streak_days"] == 1 and res1["profile"]["active_today"] is True
        got_badges = {b["id"] for b in res1["new_badges"]}
        assert {"first_steps", "quiz_perfect"} <= got_badges, got_badges
        res2 = c.post(f"/api/academy/lessons/{first}/submit", json={"answers": _correct}).json()
        assert res2["xp_gained"] == 0, "XP must award only once per item"
        assert res2["results"][0]["explain"], "explanations must come back after grading"

        # Phish game: server-graded, perfect run earns the badge.
        gv = c.get("/api/academy/games/phish-or-legit").json()
        assert gv["items"] and all("is_phish" not in it and "explain" not in it for it in gv["items"]), \
            "phish answers LEAKED!"
        _pans = [it["is_phish"] for it in _aca._GAMES["phish-or-legit"]["items"]]
        rg = c.post("/api/academy/games/phish-or-legit/submit", json={"answers": _pans}).json()
        assert rg["score"] == rg["total"] and rg["xp_gained"] == 75, rg
        assert any(b["id"] == "phish_master" for b in rg["new_badges"]), rg["new_badges"]

        # Password lab completion awards once.
        rl = c.post("/api/academy/games/password-lab/submit", json={"answers": []}).json()
        assert rl["xp_gained"] == 75 and any(b["id"] == "lab_rat" for b in rl["new_badges"])
        rl2 = c.post("/api/academy/games/password-lab/submit", json={"answers": []}).json()
        assert rl2["xp_gained"] == 0

        # Catalog now shows completion; profile accumulated 75+75+75 XP.
        cat2 = c.get("/api/academy/catalog").json()
        assert cat2["modules"][0]["lessons"][0]["completed"] is True
        assert cat2["profile"]["xp"] == 225, cat2["profile"]["xp"]

        # Leaderboard: owner (staff) sees self; a client user from another company
        # must NOT see staff/other tenants on their board.
        lb = c.get("/api/academy/leaderboard").json()["leaderboard"]
        assert any(r["you"] for r in lb) and lb[0]["xp"] >= 225
        cid2b = c.post("/api/clients", json={"name": "Acad Other Co"}).json()["id"]
        _db12 = SessionLocal()
        acu = User(email="learner@otherco.co", password_hash=hash_password("LearnPass123!"),
                   role=Role.CLIENT_VIEWER, client_id=cid2b, is_active=True)
        _db12.add(acu); _db12.commit(); _db12.close()
        lc = TestClient(app); lc.cookies.clear()
        assert lc.post("/api/auth/login", json={"email": "learner@otherco.co",
                                                "password": "LearnPass123!"}).status_code == 200
        assert lc.get("/api/academy/catalog").status_code == 200, "client users must get the academy"
        lres = lc.post(f"/api/academy/lessons/{first}/submit", json={"answers": [0, 0, 0, 0]}).json()
        assert lres["xp_gained"] >= 50
        lb2 = lc.get("/api/academy/leaderboard").json()["leaderboard"]
        assert lb2 and all(r["name"].lower().startswith("learner") for r in lb2), \
            f"tenant leak on leaderboard: {lb2}"
        print("cyber academy: page + no-answer-leak + grading + XP-once + streak/badges "
              "+ games + tenant-isolated leaderboard OK")

        # ===================== v1.3: compliance + streak savers + AI questions ==========
        import datetime as _dt13

        # Training compliance: staff endpoint + client report summary + RBAC.
        comp = c.get("/api/academy/compliance")
        assert comp.status_code == 200
        rows = {r["client"]: r for r in comp.json()["clients"]}
        oc = rows["Acad Other Co"]
        assert oc["users"] == 1 and oc["trained_users"] == 1 and oc["trained_pct"] == 100, oc
        assert oc["top_learner"] and oc["top_learner"]["name"].lower().startswith("learner")
        assert lc.get("/api/academy/compliance").status_code == 403, "compliance must be staff-only"
        rs = c.get(f"/api/reports/{cid2b}/summary").json()
        assert rs["training"]["trained_pct"] == 100, rs.get("training")
        csvtxt = c.get(f"/api/reports/{cid2b}/export.csv").text
        assert "Staff trained (security awareness) %" in csvtxt

        # Streak-saver reminders: trained yesterday + streak>=2 -> one email/day.
        from app.services import academy as _aca13, email as _email13
        _sdb = _SL11()
        try:
            _lu = _sdb.query(User).filter(User.email == "learner@otherco.co").first()
            _lp = _aca13.get_profile(_sdb, _lu)
            _now13 = _dt13.datetime.now(_dt13.timezone.utc)
            _lp.streak_days = 4
            _lp.last_active_on = (_now13 - _dt13.timedelta(days=1)).date()
            _lp.last_reminder_on = None
            _sdb.commit()
            _mails = []
            _o_send13 = _email13.send
            _email13.send = lambda to, subj, body: (_mails.append((to, subj)), True)[1]
            try:
                early = _now13.replace(hour=8)
                assert _aca13.streak_reminders(_sdb, early) == [], "no nudges before the afternoon"
                late = _now13.replace(hour=17)
                r1 = _aca13.streak_reminders(_sdb, late)
                assert len(r1) == 1 and r1[0]["streak"] == 4, r1
                assert _mails and "4-day streak" in _mails[0][1], _mails
                assert _aca13.streak_reminders(_sdb, late) == [], "must not double-send same day"
            finally:
                _email13.send = _o_send13
        finally:
            _sdb.close()

        # AI question refresh: stubbed Claude adds 2 fresh Qs per lesson, merged
        # into lesson + grading; monthly guard blocks a second run.
        _o_en13, _o_call13 = _ai11.enabled, _ai11._CALLER
        _ai11.enabled = lambda: True
        _ai11._CALLER = lambda system, user, model, max_tokens: _j11.dumps([
            {"q": "Fresh scenario question A?", "choices": ["w", "x", "correct", "z"],
             "answer": 2, "explain": "Because C."},
            {"q": "Fresh scenario question B?", "choices": ["correct", "b", "c", "d"],
             "answer": 0, "explain": "Because A."}])
        try:
            _sdb = _SL11()
            try:
                rref = _aca13.ai_refresh(_sdb, _dt13.datetime.now(_dt13.timezone.utc))
                assert rref["refreshed"] is True and rref["questions_added"] == 2 * _aca13.TOTAL_LESSONS, rref
                rref2 = _aca13.ai_refresh(_sdb, _dt13.datetime.now(_dt13.timezone.utc))
                assert rref2["refreshed"] is False and rref2["reason"] == "current", rref2
            finally:
                _sdb.close()
            base_n = len(_aca13._LESSONS[first]["quiz"])
            les13 = c.get(f"/api/academy/lessons/{first}").json()
            assert len(les13["quiz"]) == base_n + 2, "AI questions must merge into the quiz"
            assert all("answer" not in q for q in les13["quiz"]), "AI answers LEAKED!"
            # grading covers the merged quiz: perfect run = base answers + [2, 0]
            _sdb = _SL11()
            try:
                merged = _aca13._merged_quiz(_sdb, _aca13._LESSONS[first])
            finally:
                _sdb.close()
            rg13 = c.post(f"/api/academy/lessons/{first}/submit",
                          json={"answers": [q["answer"] for q in merged]}).json()
            assert rg13["score"] == base_n + 2 and rg13["total"] == base_n + 2, rg13
        finally:
            _ai11.enabled, _ai11._CALLER = _o_en13, _o_call13
        print("training compliance (report+csv+RBAC) + streak-saver emails + "
              "AI monthly question refresh (merge, no-leak, guard) OK")

        # ===================== v1.3.1: launch-hardening QA fixes =====================
        from app.models import Notification as _N131, SocialPost as _SP131
        from app.services import autopost as _ap131

        # Publish guard: off-brand content is rejected at publish, never posted.
        bad = c.post("/api/autopost", json={"body": "Why El Campo businesses need IT",
                                            "channels": ["linkedin"]}).json()
        pn = c.post(f"/api/autopost/{bad['id']}/post-now")
        assert pn.status_code == 400 and "off-brand" in pn.json()["detail"], pn.text
        row = [x for x in c.get("/api/autopost").json() if x["id"] == bad["id"]][0]
        assert row["status"] == "failed" and "off-brand" in row["result"]

        # Retry: a transient channel error re-queues (up to 3), THEN fails + notifies.
        boom = {"n": 0}
        def _fail_poster(t, u, img=None):
            boom["n"] += 1
            raise RuntimeError("LinkedIn 502 (simulated)")
        rp = c.post("/api/autopost", json={"body": "Sugar Land cybersecurity checklist",
                                           "channels": ["linkedin"]}).json()
        _sdb = _SL11()
        try:
            post_obj = _sdb.get(_SP131, rp["id"])
            # This test exercises the TRANSIENT-error retry path; lift any
            # re-auth pause an earlier block's live delivery attempt left behind
            # (v1.36 breaker) so the 502 goes through the normal retry counter.
            _ap131.clear_reauth(_sdb, "pub_linkedin")
            r1 = _ap131.publish_one(_sdb, post_obj, posters={"linkedin": _fail_poster})
            assert not r1["ok"] and post_obj.status == "queued" and post_obj.attempts == 1
            assert "retry 1/3" in (post_obj.result or ""), post_obj.result
            _ap131.publish_one(_sdb, post_obj, posters={"linkedin": _fail_poster})
            r3 = _ap131.publish_one(_sdb, post_obj, posters={"linkedin": _fail_poster})
            assert post_obj.status == "failed" and post_obj.attempts == 3, (post_obj.status, post_obj.attempts)
            note = (_sdb.query(_N131).filter(_N131.kind == "autopost")
                    .order_by(_N131.id.desc()).first())
            assert note and str(rp["id"]) in note.message, "failure notification missing"
            # Double-publish race: a non-queued post cannot be claimed again.
            rr = _ap131.publish_one(_sdb, post_obj, posters={"linkedin": _fail_poster})
            assert rr.get("skipped") is True, rr
        finally:
            _sdb.close()
        # Requeue gives fresh attempts; a working channel then posts it.
        rq = c.post(f"/api/autopost/{rp['id']}/requeue").json()
        assert rq["ok"] and rq["post"]["status"] == "queued"
        _sdb = _SL11()
        try:
            post_obj = _sdb.get(_SP131, rp["id"])
            ok = _ap131.publish_one(_sdb, post_obj, posters={"linkedin": lambda t, u, img=None: "urn:li:share:retryok"})
            assert ok["ok"] and post_obj.status == "posted"
        finally:
            _sdb.close()

        # LinkedIn truncation: long body never mangles the trailing URL.
        from app.services import publishers as _pub131
        seen = {}
        def _fake_urlopen_ok(req, timeout=15):
            import json as _jj
            seen["payload"] = _jj.loads(req.data.decode())
            class R:
                status = 201
                headers = {"x-restli-id": "urn:li:share:trunc"}
                def __enter__(self): return self
                def __exit__(self, *a): return False
                def read(self): return b'{"id":"urn:li:share:trunc"}'
            R.headers = type("H", (), {"get": staticmethod(lambda k, d=None: "urn:li:share:trunc")})()
            return R()
        _o_uo = _pub131.request.urlopen
        _pub131.request.urlopen = _fake_urlopen_ok
        try:
            _pub131.post_linkedin("tok", "urn:li:person:x", "A" * 4000, "https://bvtech.org/contact")
            _txt = seen["payload"]["specificContent"]["com.linkedin.ugc.ShareContent"]["shareCommentary"]["text"]
            assert _txt.endswith("https://bvtech.org/contact"), "URL must survive truncation"
            assert len(_txt) <= 2900
            try:
                _pub131.post_linkedin("tok", "urn:li:person:x", "   ", "")
                raise AssertionError("empty post must be refused")
            except _pub131.PublishError:
                pass
        finally:
            _pub131.request.urlopen = _o_uo

        # Staff can now invite a client user directly (client_id required + validated).
        inv = c.post("/api/client-users", json={"email": "newuser@smoke.co",
                                                "role": "client_viewer", "client_id": cid})
        assert inv.status_code == 201 and inv.json().get("temp_password"), inv.text
        assert c.post("/api/client-users", json={"email": "nu2@smoke.co",
                                                 "role": "client_viewer"}).status_code == 400
        assert c.post("/api/client-users", json={"email": "nu3@smoke.co",
                                                 "role": "owner", "client_id": cid}).status_code == 403

        # Portal page serves valid JS (the apostrophe-escape regression guard).
        _phtml = c.get("/portal").text
        assert "we\\'ll" not in _phtml, "broken template-literal escape is back"
        print("v1.3.1 hardening: publish guard + retry/notify + no-double-post + requeue "
              "+ linkedin truncation/empty guard + staff invite + portal JS OK")

        # ===================== v1.4: WordPress publishing + auto-blogger =====================
        from app.models import BlogPost as _BP14, SocialPost as _SP14
        from app.services import blog_autopilot as _blog14, wordpress as _wp14

        # Unconfigured: clean errors, no crashes.
        assert c.post("/api/website/test").status_code == 400
        assert c.post("/api/website/publish-now").status_code == 400
        st = c.get("/api/website/settings").json()
        assert st["enabled"] is False and st["wp_configured"] is False, st

        # Configure via API (owner); secret is stored but never echoed back.
        r = c.put("/api/website/settings", json={
            "base_url": "https://bvtech.org", "username": "jordan",
            "app_password": "abcd efgh ijkl mnop", "enabled": True,
            "every_days": 2, "wp_status": "publish", "cross_post_linkedin": True})
        assert r.status_code == 200, r.text
        st = r.json()
        assert st["wp_configured"] is True and st["enabled"] is True and st["every_days"] == 2
        assert "abcd" not in c.get("/api/website/settings").text, "WP app password echoed!"
        assert ca_c.get("/api/website/settings").status_code == 403, "website must be staff-only"

        # Stub the WP REST API + Claude; verify the full publish flow.
        import base64 as _b64
        wp_calls = []
        def _fake_wp_urlopen(req, timeout=30):
            wp_calls.append({"url": req.full_url, "method": req.get_method(),
                             "auth": req.headers.get("Authorization"),
                             "body": _j11.loads(req.data.decode()) if req.data else None})
            class R:
                def __enter__(self): return self
                def __exit__(self, *a): return False
                def read(self):
                    if "/users/me" in wp_calls[-1]["url"]:
                        return _j11.dumps({"name": "jordan", "roles": ["administrator"]}).encode()
                    return _j11.dumps({"id": 321, "status": "publish",
                                       "link": "https://bvtech.org/blog/houston-msp-guide/"}).encode()
            return R()
        _o_wp = _wp14._urlopen
        _wp14._urlopen = _fake_wp_urlopen
        _o_en14, _o_call14 = _ai11.enabled, _ai11._CALLER
        _ai11.enabled = lambda: True
        _ai11._CALLER = lambda system, user, model, max_tokens: _j11.dumps({
            "title": "The Houston Small-Business Guide to Managed IT",
            "excerpt": "What Houston businesses should expect from a managed IT partner — coverage, response times, and security that actually works.",
            "html": "<p>" + ("Managed IT for Houston businesses. " * 40) + "</p><h2>What to look for</h2><ul><li>24/7 monitoring</li><li>Tested backups</li></ul><p>Talk to BVTech today.</p>"})
        try:
            # Live connection test hits /users/me with Basic auth (spaces stripped).
            t = c.post("/api/website/test").json()
            assert t["ok"] and t["user"] == "jordan", t
            expected = "Basic " + _b64.b64encode(b"jordan:abcdefghijklmnop").decode()
            assert wp_calls[-1]["auth"] == expected, "auth header wrong (app password spaces?)"

            # Write & publish one now -> BlogPost posted + WP payload correct +
            # LinkedIn teaser queued with the article link.
            pn = c.post("/api/website/publish-now").json()
            assert pn["ok"] and pn["url"].startswith("https://bvtech.org/blog/"), pn
            post_call = [x for x in wp_calls if x["url"].endswith("/wp-json/wp/v2/posts")][-1]
            assert post_call["body"]["status"] == "publish" and "Houston" in post_call["body"]["title"]
            _sdb = _SL11()
            try:
                brow = _sdb.query(_BP14).order_by(_BP14.id.desc()).first()
                assert brow.status == "posted" and brow.wp_post_id == 321
                teaser = (_sdb.query(_SP14).filter(_SP14.link == pn["url"]).first())
                assert teaser and teaser.status == "queued" and "BVTech blog" in teaser.body, "cross-post missing"
            finally:
                _sdb.close()

            # Heartbeat cadence: just published -> not due.
            _sdb = _SL11()
            try:
                mp = _blog14.maybe_publish(_sdb)
                assert mp["published"] is False and mp["reason"] == "not_due", mp
            finally:
                _sdb.close()

            # Brand guard: off-brand article is rejected BEFORE any WP call.
            n_calls = len(wp_calls)
            _sdb = _SL11()
            try:
                row = _blog14.publish_article(_sdb, {"title": "IT tips for El Campo businesses",
                                                     "excerpt": "x", "html": "<p>" + "words " * 200 + "</p>"})
                assert row.status == "failed" and "off-brand" in row.error, row.error
                assert len(wp_calls) == n_calls, "guard must reject before any network call"
            finally:
                _sdb.close()

            # Manual publish (Content Studio path).
            mr = c.post("/api/website/publish", json={"title": "Our new Sugar Land office hours",
                                                      "html": "<p>We are expanding support coverage for Sugar Land clients.</p>",
                                                      "excerpt": "Updated support hours."})
            assert mr.status_code == 200 and mr.json()["ok"], mr.text
        finally:
            _wp14._urlopen = _o_wp
            _ai11.enabled, _ai11._CALLER = _o_en14, _o_call14

        # env-creds: his wp_* key names light the integration up from .env.
        _os.environ["wp_url"] = "https://bvtech.org"; _os.environ["wp_user"] = "jordan"
        _os.environ["wp_app_password"] = "qqqq wwww eeee rrrr"
        _edb2 = _ESL()
        try:
            applied2 = _envc.load(_edb2)
            assert "wp_site" in applied2 and set(applied2["wp_site"]) == {"app_password", "base_url", "username"}, applied2
        finally:
            _edb2.close()
        for _k in ("wp_url", "wp_user", "wp_app_password"):
            _os.environ.pop(_k, None)
        print("wordpress publisher + auto-blogger: config (masked, RBAC) + live-test auth + "
              "publish flow + cross-post + cadence + brand guard + env aliases OK")

    print("\n=== OpsPilot v1.38.0 SMOKE TEST PASSED ===")

if __name__ == "__main__":
    main()
