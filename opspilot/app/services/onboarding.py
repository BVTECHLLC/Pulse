"""v1.70 Client onboarding wizard — a guided, self-verifying setup checklist.

New clients (and the staff onboarding them) get one clear place that answers
"what's left to go live?". Every step's `done` state is COMPUTED from real data
— a user was actually invited, an agent actually checked in, a posture snapshot
actually exists — so the checklist can't drift from reality or be faked by
clicking "mark complete". It doubles as a live progress view during a rollout
and as a health check for an existing client ("are they fully set up?").

Pure read model: it inspects the DB and returns a structured wizard. The CTAs
point at the existing screens/endpoints that complete each step.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import (Client, CLIENT_ROLES, Device, PostureSnapshot,
                      ReportSchedule, SecurityFinding, User)


def _steps(db: Session, client: Client) -> list[dict]:
    cid = client.id

    # --- signals, each a cheap existence check ---
    profile_done = bool((client.primary_contact or "").strip()
                        and (client.email or "").strip())
    team_users = (db.query(func.count(User.id))
                  .filter(User.client_id == cid,
                          User.role.in_(list(CLIENT_ROLES)),
                          User.is_active.is_(True)).scalar() or 0)
    sso_done = bool(client.sso_domains)
    device_count = (db.query(func.count(Device.id))
                    .filter(Device.client_id == cid).scalar() or 0)
    checked_in = (db.query(func.count(Device.id))
                  .filter(Device.client_id == cid,
                          Device.last_checkin.isnot(None)).scalar() or 0)
    posture_done = bool(db.query(PostureSnapshot.id)
                        .filter(PostureSnapshot.client_id == cid).first()
                        or db.query(SecurityFinding.id)
                        .filter(SecurityFinding.client_id == cid).first())
    report_done = bool(db.query(ReportSchedule.id)
                       .filter(ReportSchedule.client_id == cid,
                               ReportSchedule.enabled.is_(True)).first())

    return [
        {"key": "profile", "title": "Complete the company profile",
         "desc": "Add the primary contact, email, and site details so tickets, "
                 "reports, and alerts reach the right people.",
         "done": profile_done, "optional": False,
         "cta_label": "Edit client", "cta_href": f"/dashboard#clients/{cid}"},
        {"key": "team", "title": "Invite the client's team",
         "desc": "Give the client admin and staff their own logins (SSO or email) "
                 "so they can see their dashboard, tickets, and training.",
         "done": team_users > 0, "optional": False,
         "detail": f"{team_users} user(s) active",
         "cta_label": "Users & Access", "cta_href": "/dashboard#users"},
        {"key": "sso", "title": "Authorize a sign-in domain (SSO)",
         "desc": "Add the client's email domain so their staff can sign in with "
                 "Microsoft or Google — zero-touch, no passwords to manage.",
         "done": sso_done, "optional": True,
         "cta_label": "SSO settings", "cta_href": "/dashboard#settings/sso"},
        {"key": "agent", "title": "Deploy the monitoring agent",
         "desc": "Install the OpsPilot agent on the client's endpoints to start "
                 "collecting health, security posture, and patch status.",
         "done": device_count > 0, "optional": False,
         "detail": f"{device_count} device(s) enrolled",
         "cta_label": "Get agent + token", "cta_href": "/dashboard#download"},
        {"key": "telemetry", "title": "Confirm the first check-in",
         "desc": "Verify at least one endpoint has reported in — that's the proof "
                 "monitoring is live and data is flowing.",
         "done": checked_in > 0, "optional": False,
         "detail": f"{checked_in} device(s) reporting",
         "cta_label": "View devices", "cta_href": "/dashboard#devices"},
        {"key": "assessment", "title": "Run the first security assessment",
         "desc": "Capture a baseline security posture (grade + findings) so you "
                 "can show progress and prioritize remediation from day one.",
         "done": posture_done, "optional": False,
         "cta_label": "Security posture", "cta_href": "/dashboard#security"},
        {"key": "reporting", "title": "Schedule the QBR / client report",
         "desc": "Turn on a recurring branded report (and the vCIO scorecard) so "
                 "the client sees value automatically every cycle.",
         "done": report_done, "optional": True,
         "cta_label": "Reports", "cta_href": "/dashboard#reports"},
    ]


def wizard(db: Session, client: Client) -> dict:
    """The full onboarding state for one client — computed, not stored."""
    steps = _steps(db, client)
    required = [s for s in steps if not s["optional"]]
    req_done = [s for s in required if s["done"]]
    all_done = [s for s in steps if s["done"]]
    # progress is measured against required steps (optional ones are bonus)
    total_req = len(required) or 1
    pct = round(100 * len(req_done) / total_req)
    nxt = next((s for s in steps if not s["done"]), None)
    return {
        "client_id": client.id, "client": client.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": steps,
        "required_total": len(required),
        "required_done": len(req_done),
        "steps_done": len(all_done),
        "steps_total": len(steps),
        "percent": pct,
        "complete": len(req_done) == len(required),
        "next_step": {"key": nxt["key"], "title": nxt["title"],
                      "cta_label": nxt["cta_label"], "cta_href": nxt["cta_href"]}
        if nxt else None,
    }
