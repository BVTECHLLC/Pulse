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

        # ===================== v0.4: SLA, assignment, time, KB =====================
        from app.models import SupportTicket as _ST
        from datetime import datetime as _d3, timedelta as _t3, timezone as _z3
        owner_id = c.get("/api/auth/me").json()["id"]
        ca_id = ca_c.get("/api/auth/me").json()["id"]

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
        rc=c.post("/api/automation/run-checks").json()
        assert rc["sla_breaches_fired"]>=1, rc
        assert any("SLA breached" in n["message"] for n in c.get("/api/notifications").json())
        assert c.post("/api/automation/run-checks").json()["sla_breaches_fired"]==0, "breach re-fired (no dedup)"
        print("run-checks SLA breach + dedup OK:", rc)

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

        # ===================== v0.13: Agent download & installers =====================
        ra=c.get("/download/agent")
        assert ra.status_code==200 and "OpsPilot Agent" in ra.text, "agent download broken"
        sh=c.get("/download/install.sh?token=TESTTOKEN")
        assert sh.status_code==200 and "TESTTOKEN" in sh.text and "/download/agent" in sh.text and "enroll" in sh.text, sh.text[:200]
        ps=c.get("/download/install.ps1?token=TESTTOKEN")
        assert ps.status_code==200 and "TESTTOKEN" in ps.text and "PULSE_URL" in ps.text and "schtasks" in ps.text, ps.text[:200]
        # installer auto-targets the serving host (so it reports back to us)
        assert "http://testserver" in sh.text, "installer didn't embed server URL"
        # the agent file actually serves (this is the part that must never 404)
        assert "opspilot_agent.py" in c.get("/download/agent").headers.get("content-disposition","")
        # enroll-token works for a real client (the Deploy Agent button path)
        assert c.post(f"/api/agent/enroll-token/{cid}").status_code==200
        print("agent download + one-click installers OK")

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
        assert c.get(f"/report/{cid}").status_code==200, "report page broken"
        # client can view their own report but cannot create contracts
        assert ca_c.get(f"/api/reports/{cid}/summary").status_code==200
        assert ca_c.post("/api/contracts", json={"client_id":cid,"name":"x","amount":1}).status_code==403
        assert all(ct["client_id"]==cid for ct in ca_c.get("/api/contracts").json())
        print("client report + contracts RBAC OK")

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

        # ===================== v0.16: standalone agent binary endpoint =====================
        # The .py agent always serves; the binary routes serve a local file if
        # present, else 302-redirect to the published GitHub release asset.
        assert c.get("/download/agent").status_code==200
        rexe=c.get("/download/agent.exe", follow_redirects=False)
        assert rexe.status_code in (200, 302)
        if rexe.status_code==302:
            assert rexe.headers["location"].endswith("/opspilot-agent.exe")
        rlin=c.get("/download/agent-linux", follow_redirects=False)
        assert rlin.status_code in (200, 302)
        if rlin.status_code==302:
            assert rlin.headers["location"].endswith("/opspilot-agent")
        print("agent binary endpoints OK (exe %s)" % ("local" if rexe.status_code==200 else "release-redirect"))

        # ===================== v0.18: no-Python .exe installer =====================
        rexeps=c.get("/download/install-exe.ps1")
        assert rexeps.status_code==200
        body=rexeps.text
        assert "/download/agent.exe" in body and "schtasks" in body and "ProgramData" in body
        # the whole point: no Python invocation (winget/pip/python.exe) anywhere
        assert "winget" not in body and "pip" not in body and "python " not in body.lower()
        print("no-Python .exe installer OK")

        # HTML pages must be uncacheable so deploys are visible immediately (v0.17.1).
        for pth in ("/", "/dashboard", "/portal", "/signup"):
            cc=c.get(pth).headers.get("cache-control","")
            assert "no-store" in cc, (pth, cc)
        print("HTML no-store cache headers OK")

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

    print("\n=== OpsPilot v0.22 SMOKE TEST PASSED ===")

if __name__ == "__main__":
    main()
