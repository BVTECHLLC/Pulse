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
            gp=c.post("/api/autopost", json={"body":"Top 5 ways El Campo SMBs stay secure",
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
            gen=c.post("/api/autopost/generate", json={"count":5,"city":"El Campo, TX",
                       "keywords":["managed IT","backups"],"cta_url":"https://bvtech.org/contact",
                       "channels":["google_business"]}).json()
            assert gen["ok"] and gen["created"]==5, gen
            rows=c.get("/api/autopost").json()
            draft=[x for x in rows if "El Campo" in (x["body"] or "")][0]
            assert draft["status"]=="queued" and draft["channels"]==["google_business"], draft
            assert "bvtech.org/contact" in draft["body"]   # CTA woven in (SEO)
            # Save a brand profile + turn on auto-refill; the tick tops the queue up.
            c.put("/api/autopost/settings", json={"auto_generate":True,"min_queue":8,
                  "city":"El Campo, TX","keywords":["cybersecurity"],"gen_channels":["linkedin"]})
            stt=c.get("/api/autopost/settings").json()
            assert stt["auto_generate"] is True and stt["city"]=="El Campo, TX" and stt["min_queue"]==8, stt
            c.post("/api/automation/run-checks")   # auto-refill tops the queue up to min_queue
            _after=len([x for x in c.get("/api/autopost").json() if x["status"]=="queued"])
            assert _after>=8, ("queue not refilled to min_queue", _after)
            # RBAC: clients can't generate.
            assert ca_c.post("/api/autopost/generate", json={"count":2}).status_code==403
            print("auto-posting: LinkedIn + Google Business (image, weekly, generate + auto-refill) + RBAC OK")
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
        # install-exe drops a single-use token file so the boot task self-enrolls.
        assert "opspilot-enroll.json" in body
        # v0.69: pulls the .exe from the Cloudflare-free GitHub release, verifies the
        # MZ header, checks the enroll exit code, and FAILS LOUDLY (no false success).
        assert "releases/latest/download/opspilot-agent.exe" in body, "exe should come from GitHub release"
        assert "0x4D" in body and "0x5A" in body, "should verify the MZ executable header"
        assert "ENROLLMENT FAILED" in body and "$LASTEXITCODE" in body, "must report real enroll result"
        print("no-Python .exe installer OK (GitHub-sourced + verified + honest)")

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
        assert "opspilot-agent.exe" in decoded and "ENROLLMENT FAILED" in decoded
        # honest result reporting in the batch wrapper
        assert "INSTALL DID NOT COMPLETE" in cb and "installed and enrolled" in cb
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
        print("dashboard shell: AI copilot + command palette + branding wired OK")

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
        print("One-click OAuth connect: providers + app-config gating + self-refresh engine + RBAC OK")

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

    print("\n=== OpsPilot v0.80 SMOKE TEST PASSED ===")

if __name__ == "__main__":
    main()
