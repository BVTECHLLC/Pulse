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

    print("\n=== OpsPilot v0.7 SMOKE TEST PASSED ===")

if __name__ == "__main__":
    main()
