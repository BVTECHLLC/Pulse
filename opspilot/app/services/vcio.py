"""v1.16 AI vCIO — automated technology business reviews + a prioritized roadmap.

An MSP's most valuable (and least scalable) offering is the *virtual CIO*: sit
with a client quarterly, translate their IT reality into business risk, and hand
them a ranked roadmap with budget. Pulse now does that itself.

`build_review()` pulls the client's whole picture — health, security posture,
predicted risks, SLA/tickets, contract margin, and hardware lifecycle — and runs
a deterministic recommendation engine that emits ranked, budgeted, horizon-bucketed
recommendations (immediate / this quarter / this year). A maturity index scores
where they stand. An optional AI narrative turns it into a board-ready summary,
but every recommendation and number is computed, not guessed.

Reuses the existing QBR summary (reports._build_summary), foresight, psa_intel,
and the Asset lifecycle — this is the synthesis layer that ties it together.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import Asset, Client
from . import ai

# Rough per-endpoint replacement budget for lifecycle planning (USD).
REFRESH_COST = 1200.0
AGING_YEARS = 5
_PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_HORIZONS = ("immediate", "quarter", "year")


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _rec(area, title, detail, priority, horizon, *, budget=None, effort="medium"):
    return {"area": area, "title": title, "detail": detail, "priority": priority,
            "horizon": horizon, "budget": budget, "effort": effort}


# --------------------------------------------------------------------------- #
# Hardware lifecycle
# --------------------------------------------------------------------------- #
def asset_lifecycle(db: Session, client_id: int, now: datetime) -> dict:
    """Out-of-warranty and aging (>AGING_YEARS old) assets + a refresh budget."""
    assets = db.query(Asset).filter(Asset.client_id == client_id).all()
    age_cut = now - timedelta(days=AGING_YEARS * 365)
    expired, aging = [], []
    for a in assets:
        we = _aware(a.warranty_expires)
        pd = _aware(a.purchase_date)
        if we and we < now:
            expired.append(a)
        elif pd and pd < age_cut:
            aging.append(a)
    n = len(expired) + len(aging)
    return {"assets_total": len(assets), "out_of_warranty": len(expired),
            "aging": len(aging), "to_refresh": n,
            "refresh_budget": round(n * REFRESH_COST, 2)}


# --------------------------------------------------------------------------- #
# Deterministic recommendation engine
# --------------------------------------------------------------------------- #
def recommendations(db: Session, client: Client, summary: dict, now: datetime) -> list[dict]:
    cid = client.id
    recs: list[dict] = []

    # --- Security posture ---
    posture = summary.get("posture") or {}
    p_score = posture.get("score")
    p_grade = posture.get("grade")
    sec = summary.get("security") or {}
    crit_findings = (sec.get("by_severity") or {}).get("critical", 0)
    if crit_findings:
        recs.append(_rec("Security", f"Remediate {crit_findings} critical security finding(s)",
                         "Critical findings are the fastest path to a breach — close them first.",
                         "critical", "immediate", effort="medium"))
    if p_score is not None and p_score < 70:
        recs.append(_rec("Security", f"Raise security posture (grade {p_grade})",
                         f"Overall posture scores {p_score}/100. Prioritize MFA everywhere, EDR "
                         "coverage, and closing open findings.", "high", "immediate", effort="high"))
    elif p_score is not None and p_score < 85:
        recs.append(_rec("Security", f"Strengthen security posture (grade {p_grade})",
                         f"Posture is {p_score}/100 — solid but improvable. Tighten identity and "
                         "endpoint domains to reach an A.", "medium", "quarter", effort="medium"))

    # --- Patching ---
    pc = (summary.get("patch") or {}).get("compliance_pct")
    if pc is not None and pc < 90:
        recs.append(_rec("Patching", f"Bring patch compliance to 95%+ (now {pc}%)",
                         "Unpatched endpoints are the most common ransomware entry point. Enable "
                         "auto-approval for critical/important updates.", "high", "immediate", effort="low"))

    # --- Predicted risks (foresight) ---
    try:
        from . import foresight
        risks = foresight.fleet_risks(db, [cid], now)
        risks = [r for r in risks if r.get("severity") in ("critical", "high")]
        risks.sort(key=lambda r: 0 if r.get("severity") == "critical" else 1)
        for r in risks[:3]:
            recs.append(_rec("Reliability", f"Prevent predicted issue on {r.get('hostname')}",
                             r.get("detail") or "Trend analysis projects a failure — act before it hits.",
                             "high" if r.get("severity") == "critical" else "medium",
                             "immediate", effort="medium"))
    except Exception:  # noqa: BLE001
        pass

    # --- SLA / ticket backlog ---
    tickets = summary.get("tickets") or {}
    if tickets.get("sla_breached"):
        recs.append(_rec("Service", f"Clear {tickets['sla_breached']} SLA breach(es)",
                         "Breached tickets erode trust and renewal odds. Reassign or resolve today.",
                         "high", "immediate", effort="low"))
    elif (tickets.get("open") or 0) >= 10:
        recs.append(_rec("Service", f"Work down the ticket backlog ({tickets['open']} open)",
                         "A growing backlog signals capacity or process gaps.", "medium", "quarter",
                         effort="medium"))

    # --- Contract margin & renewals ---
    try:
        from . import psa_intel
        ci = psa_intel.contract_intel(db, now, client_ids=[cid])
        for c in ci.get("contracts", []):
            flags = c.get("flags") or []
            days = c.get("days_to_renewal")
            horizon = "immediate" if (days is not None and days <= 60) else "quarter"
            if "underwater" in flags:
                recs.append(_rec("Financial", f"Reprice '{c['name']}' — it's running underwater",
                                 f"Delivering ~{c.get('monthly_hours')}h/mo at a "
                                 f"${c.get('realized_rate')} realized rate; margin is "
                                 f"${c.get('margin')}/mo. Reprice or rescope at renewal.",
                                 "high", horizon, effort="low"))
            elif "low_margin" in flags:
                recs.append(_rec("Financial", f"Improve margin on '{c['name']}'",
                                 f"Margin is {int((c.get('margin_pct') or 0)*100)}% — below a healthy "
                                 "MSP target. Review scope and rate.", "medium", "quarter", effort="low"))
            if "renewal_soon" in flags:
                recs.append(_rec("Financial", f"Prepare renewal & pricing for '{c['name']}'",
                                 f"Renews in {days} days — walk in with a value recap and a proposed "
                                 "rate.", "medium", horizon, effort="low"))
    except Exception:  # noqa: BLE001
        pass

    # --- Hardware lifecycle ---
    life = asset_lifecycle(db, cid, now)
    if life["to_refresh"]:
        recs.append(_rec("Lifecycle",
                         f"Budget hardware refresh for {life['to_refresh']} device(s)",
                         f"{life['out_of_warranty']} out of warranty, {life['aging']} over "
                         f"{AGING_YEARS} years old. Plan ~${life['refresh_budget']:,.0f} to refresh.",
                         "medium", "year", budget=life["refresh_budget"], effort="high"))

    # --- Security awareness training ---
    tr = summary.get("training") or {}
    comp = tr.get("completion_pct")
    if comp is not None and comp < 80 and (tr.get("assigned") or tr.get("enrolled") or 0):
        recs.append(_rec("People", f"Finish security-awareness training ({comp}% complete)",
                         "The human layer is the top breach vector — get the team to 100%.",
                         "medium", "quarter", effort="low"))

    recs.sort(key=lambda r: (_PRIORITY_RANK.get(r["priority"], 9),
                             _HORIZONS.index(r["horizon"]) if r["horizon"] in _HORIZONS else 9))
    return recs


def maturity_index(summary: dict, recs: list[dict]) -> int:
    """A 0-100 composite of where the client stands. Posture + patching drive it;
    open critical recommendations pull it down."""
    posture = (summary.get("posture") or {}).get("score")
    patch = (summary.get("patch") or {}).get("compliance_pct")
    parts, weights = [], []
    if posture is not None:
        parts.append(posture); weights.append(0.5)
    if patch is not None:
        parts.append(patch); weights.append(0.3)
    base = (sum(p * w for p, w in zip(parts, weights)) / sum(weights)) if parts else 70.0
    penalty = 8 * sum(1 for r in recs if r["priority"] == "critical") + \
        3 * sum(1 for r in recs if r["priority"] == "high")
    return max(0, min(100, round(base - penalty)))


def build_review(db: Session, client: Client, now: datetime | None = None, *,
                 with_narrative: bool = False) -> dict:
    """Assemble the full vCIO review: summary + ranked roadmap + maturity + budget."""
    now = now or datetime.now(timezone.utc)
    from ..api.routes.reports import _build_summary
    summary = _build_summary(db, client, now)
    recs = recommendations(db, client, summary, now)
    roadmap = {h: [r for r in recs if r["horizon"] == h] for h in _HORIZONS}
    budget_total = round(sum(r["budget"] or 0.0 for r in recs), 2)
    review = {
        "client_id": client.id, "client": client.name, "generated_at": now.isoformat(),
        "maturity_index": maturity_index(summary, recs),
        "counts": {"total": len(recs),
                   "critical": sum(1 for r in recs if r["priority"] == "critical"),
                   "high": sum(1 for r in recs if r["priority"] == "high")},
        "budget_total": budget_total,
        "recommendations": recs, "roadmap": roadmap,
        "highlights": {"posture_grade": (summary.get("posture") or {}).get("grade"),
                       "patch_compliance": (summary.get("patch") or {}).get("compliance_pct"),
                       "open_tickets": (summary.get("tickets") or {}).get("open"),
                       "mrr": (summary.get("revenue") or {}).get("mrr")},
    }
    if with_narrative and ai.enabled():
        try:
            facts = "\n".join(
                f"- [{r['priority']}/{r['horizon']}] {r['title']}: {r['detail']}" for r in recs[:12])
            review["narrative"] = ai.complete(
                "You are a virtual CIO writing a concise, executive technology business review for "
                "an SMB client of an MSP. Lead with where they stand, then the top priorities and "
                "why they matter to the business. Be direct and non-technical. Max ~10 lines.",
                f"Client: {client.name}\nMaturity index: {review['maturity_index']}/100\n"
                f"Posture grade: {review['highlights']['posture_grade']}\n"
                f"Recommendations:\n{facts}\n\nWrite the review.", max_tokens=550)
        except Exception:  # noqa: BLE001
            pass
    return review


# --------------------------------------------------------------------------- #
# Board-ready PDF scorecard (the QBR deliverable)
# --------------------------------------------------------------------------- #
_HORIZON_LABEL = {"immediate": "Do Now (0-30 days)",
                  "quarter": "This Quarter (30-90 days)",
                  "year": "This Year (planning)"}
_PRIORITY_LABEL = {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM", "low": "LOW"}


def maturity_grade(idx: int) -> tuple[str, str]:
    """Letter grade + one-line standing for a 0-100 maturity index."""
    if idx >= 90:
        return "A", "Excellent — a mature, well-defended IT environment."
    if idx >= 80:
        return "B", "Strong — solid posture with a few areas to tighten."
    if idx >= 70:
        return "C", "Fair — functional, but real gaps are raising business risk."
    if idx >= 55:
        return "D", "At risk — several priorities need attention this quarter."
    return "F", "Critical — immediate remediation is strongly advised."


def _fmt_money(v) -> str:
    try:
        return f"${float(v):,.0f}"
    except (TypeError, ValueError):
        return "-"


def scorecard_pdf(review: dict) -> bytes:
    """Render build_review() output into a branded, client-ready PDF (bytes)."""
    from .branded_pdf import (BrandedPDF, to_bytes, latin, NAVY, ACCENT, GOLD,
                              INK, SOFT, LINE, PAPER_TINT, GOOD, WARN, BAD)

    idx = int(review.get("maturity_index") or 0)
    grade, standing = maturity_grade(idx)
    hi = review.get("highlights") or {}
    gen = (review.get("generated_at") or "")[:10]

    pdf = BrandedPDF(doc_id="VCIO-QBR", title="Technology Business Review",
                     classification=f"Confidential - Prepared for {review.get('client', 'Client')}")
    pdf.add_page()
    pdf.brand_band("Virtual CIO  -  Technology Business Review")

    # ---- title block ----
    pdf.set_xy(18, 44)
    pdf.set_font("helvetica", "", 9)
    pdf.set_text_color(*ACCENT)
    pdf.cell(0, 5, latin("TECHNOLOGY BUSINESS REVIEW"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "B", 20)
    pdf.set_text_color(*NAVY)
    pdf.multi_cell(0, 8.5, latin(review.get("client", "Client")), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 9.5)
    pdf.set_text_color(*SOFT)
    pdf.cell(0, 5, latin(f"Prepared by BVTech LLC (vCIO)   -   Review date {gen}"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ---- maturity hero: score card + grade + bar ----
    y0 = pdf.get_y()
    band = GOOD if idx >= 80 else (WARN if idx >= 60 else BAD)
    # left: big score tile
    pdf.set_fill_color(*NAVY)
    pdf.rect(18, y0, 46, 30, style="F")
    pdf.set_xy(18, y0 + 3.5)
    pdf.set_font("helvetica", "B", 30)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(46, 14, latin(str(idx)), align="C")
    pdf.set_xy(18, y0 + 18.5)
    pdf.set_font("helvetica", "", 8)
    pdf.set_text_color(*GOLD)
    pdf.cell(46, 5, latin("MATURITY INDEX / 100"), align="C")
    pdf.set_xy(18, y0 + 23)
    pdf.set_font("helvetica", "B", 11)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(46, 6, latin(f"Grade {grade}"), align="C")
    # right: standing + score bar
    pdf.set_xy(70, y0 + 1)
    pdf.set_font("helvetica", "B", 11)
    pdf.set_text_color(*NAVY)
    pdf.multi_cell(pdf.w - 18 - 70, 5.6, latin(standing), new_x="LMARGIN", new_y="NEXT")
    bar_x, bar_y, bar_w = 70, y0 + 16, pdf.w - 18 - 70
    pdf.set_fill_color(*LINE)
    pdf.rect(bar_x, bar_y, bar_w, 5.5, style="F")
    pdf.set_fill_color(*band)
    pdf.rect(bar_x, bar_y, bar_w * max(0.02, min(1.0, idx / 100.0)), 5.5, style="F")
    pdf.set_xy(70, bar_y + 7)
    pdf.set_font("helvetica", "", 8)
    pdf.set_text_color(*SOFT)
    c = review.get("counts") or {}
    pdf.cell(0, 4, latin(f"{c.get('critical', 0)} critical  -  {c.get('high', 0)} high-priority  "
                         f"-  {c.get('total', 0)} total recommendations"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(y0 + 34)

    # ---- highlight metric cards ----
    cards = [("Security Grade", hi.get("posture_grade") or "-"),
             ("Patch Compliance", (f"{hi.get('patch_compliance')}%"
                                   if hi.get("patch_compliance") is not None else "-")),
             ("Open Tickets", (str(hi.get("open_tickets"))
                               if hi.get("open_tickets") is not None else "-")),
             ("Monthly Revenue", _fmt_money(hi.get("mrr")))]
    gap, cw = 4, (pdf.w - 36 - 3 * 4) / 4
    cy = pdf.get_y()
    x = 18
    for label, val in cards:
        pdf.set_fill_color(*PAPER_TINT)
        pdf.set_draw_color(*LINE)
        pdf.rect(x, cy, cw, 20, style="DF")
        pdf.set_xy(x, cy + 3)
        pdf.set_font("helvetica", "B", 15)
        pdf.set_text_color(*NAVY)
        pdf.cell(cw, 8, latin(str(val)), align="C")
        pdf.set_xy(x, cy + 12.5)
        pdf.set_font("helvetica", "", 7.5)
        pdf.set_text_color(*SOFT)
        pdf.cell(cw, 4, latin(label.upper()), align="C")
        x += cw + gap
    pdf.set_y(cy + 26)

    # ---- executive summary ----
    pdf.h1("Executive Summary")
    narrative = review.get("narrative")
    if narrative:
        for para in str(narrative).split("\n"):
            if para.strip():
                pdf.para(para.strip())
    else:
        total = (review.get("counts") or {}).get("total", 0)
        crit = (review.get("counts") or {}).get("critical", 0)
        pdf.para(
            f"{review.get('client', 'The organization')} currently scores {idx}/100 on our "
            f"technology maturity index (grade {grade}). {standing} This review identifies "
            f"{total} prioritized recommendation(s)"
            + (f", including {crit} rated critical," if crit else "")
            + " sequenced below by urgency. Each item ties a specific technology gap to the "
            "business risk it creates and the investment required to close it.")

    # ---- roadmap by horizon ----
    roadmap = review.get("roadmap") or {}
    any_rec = False
    for hz in ("immediate", "quarter", "year"):
        items = roadmap.get(hz) or []
        if not items:
            continue
        any_rec = True
        pdf.h1(_HORIZON_LABEL.get(hz, hz.title()))
        rows = []
        for r in items:
            rows.append([
                _PRIORITY_LABEL.get(r.get("priority"), (r.get("priority") or "").upper()),
                r.get("area") or "",
                f"{r.get('title', '')}. {r.get('detail', '')}".strip(),
                _fmt_money(r.get("budget")) if r.get("budget") else "-",
            ])
        pdf.table_grid(["Priority", "Area", "Recommendation", "Budget"],
                       [22, 24, pdf.w - 36 - 22 - 24 - 26, 26], rows)
    if not any_rec:
        pdf.h1("Roadmap")
        pdf.para("No open priorities at this time — the environment is meeting our operational "
                 "and security benchmarks. We will continue proactive monitoring and revisit at "
                 "the next review.")

    # ---- investment summary ----
    pdf.h1("Investment Summary")
    bt = review.get("budget_total") or 0
    if bt:
        pdf.para(f"Estimated planned capital for the recommendations above (primarily hardware "
                 f"lifecycle): {_fmt_money(bt)}. Operational and security remediations are "
                 f"delivered under your existing managed-services agreement at no additional cost.")
    else:
        pdf.para("The recommendations above are delivered under your existing managed-services "
                 "agreement — no additional capital is required at this time.")
    pdf.bullets([
        "This review is generated from live telemetry across your fleet, security posture, "
        "patching, service tickets, and contract data.",
        "Priorities are recomputed every review cycle so progress is measurable quarter over quarter.",
        "Questions or want to walk through the roadmap? Reach your BVTech vCIO at help@bvtech.org.",
    ])
    return to_bytes(pdf)
