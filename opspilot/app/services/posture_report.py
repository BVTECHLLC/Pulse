"""v1.153 Client Security Scorecard — the branded, client-ready report.

Turns the posture.scorecard() aggregation into a polished, printable HTML report
an MSP hands a client: one big A-F grade, a breakdown per security domain, the
priority fixes, and a clear "here's what we recommend" CTA. Light theme, prints
clean to PDF, BVTech-branded. Pure rendering — no new data, no DB writes."""
from __future__ import annotations

import html as _html

_GRADE_COLOR = {"A": "#1fae72", "B": "#3aa0c9", "C": "#d79a1f", "D": "#e07b2e", "F": "#d8434f"}
_DOMAIN_META = {
    "endpoints": ("Endpoints", "Devices online, protected by AV/EDR, and healthy"),
    "patching":  ("Patching", "Operating systems and apps kept up to date"),
    "identity":  ("Identity & M365", "Microsoft 365 Secure Score and risky sign-ins"),
    "threats":   ("Threats", "Open security findings across the environment"),
}


def _color(grade: str) -> str:
    return _GRADE_COLOR.get((grade or "").strip()[:1], "#8a93a6")


def _esc(v) -> str:
    return _html.escape(str(v if v is not None else ""))


def _domain_summary(key: str, d: dict) -> str:
    g = d.get
    if key == "endpoints":
        return (f"{g('online', 0)}/{g('device_count', 0)} online · "
                f"{g('av_protected', g('device_count', 0))}/{g('device_count', 0)} AV-protected")
    if key == "patching":
        return f"{g('compliance_pct', g('score', 0))}% compliant · {g('pending_total', 0)} updates pending"
    if key == "identity":
        rs = g("risky_signins", 0)
        return f"Secure Score {g('secure_score_pct', 0)}%" + (f" · {rs} risky sign-in(s)" if rs else "")
    if key == "threats":
        bs = g("by_severity", {}) or {}
        return (f"{g('open_findings', 0)} open finding(s)" +
                (f" · {bs.get('critical', 0)} critical / {bs.get('high', 0)} high"
                 if (bs.get('critical') or bs.get('high')) else ""))
    return ""


def render(sc: dict) -> str:
    score = sc.get("score")
    grade = sc.get("grade") or "—"
    gc = _color(grade)
    name = _esc(sc.get("client_name") or "Your Organization")
    gen = _esc((sc.get("generated_at") or "")[:10])
    ring = (f"conic-gradient({gc} {int(score)*3.6:.0f}deg, #e9ecf3 0deg)" if isinstance(score, (int, float)) else "#e9ecf3")

    domains = sc.get("domains") or {}
    cards = []
    for key in ("endpoints", "patching", "identity", "threats"):
        d = domains.get(key)
        label, blurb = _DOMAIN_META[key]
        if not d:
            cards.append(f'''<div class="dom dom-na"><div class="dom-h"><span class="dom-t">{label}</span>
              <span class="dom-g" style="background:#eceef3;color:#8a93a6">N/A</span></div>
              <div class="dom-b muted">Not enough data yet — connect this source to include it.</div></div>''')
            continue
        dg = d.get("grade") or "—"; dc = _color(dg); ds = int(d.get("score") or 0)
        cards.append(f'''<div class="dom"><div class="dom-h"><span class="dom-t">{label}</span>
          <span class="dom-g" style="background:{dc}">{_esc(dg)}</span></div>
          <div class="bar"><span style="width:{ds}%;background:{dc}"></span></div>
          <div class="dom-s">{ds}/100</div>
          <div class="dom-b">{_esc(_domain_summary(key, d))}</div>
          <div class="dom-blurb muted">{_esc(blurb)}</div></div>''')

    recs = sc.get("recommendations") or []
    if recs:
        rec_html = "".join(f'<li>{_esc(r)}</li>' for r in recs)
        rec_block = f'<ol class="recs">{rec_html}</ol>'
    else:
        rec_block = ('<p class="allclear">✓ No priority issues found in the data we monitor. '
                     'Great posture — we\'ll keep watching and let you know the moment anything changes.</p>')

    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Security Scorecard — {name}</title>
<style>
:root{{--ink:#1a1d29;--muted:#6b7280;--line:#e7e9f0;--accent:#4440DB;--bg:#f6f7fb}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,-apple-system,sans-serif;color:var(--ink);background:var(--bg);line-height:1.55}}
.sheet{{max-width:860px;margin:24px auto;background:#fff;border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:0 10px 40px rgba(20,24,60,.07)}}
.top{{display:flex;justify-content:space-between;align-items:center;padding:22px 30px;border-bottom:1px solid var(--line)}}
.brand{{font-weight:800;font-size:1.25rem;letter-spacing:.5px}}.brand span{{color:var(--accent)}}
.top .meta{{text-align:right;font-size:.8rem;color:var(--muted)}}
.hero{{display:flex;gap:28px;align-items:center;padding:30px}}
.ring{{width:150px;height:150px;border-radius:50%;background:{ring};display:flex;align-items:center;justify-content:center;flex:0 0 auto}}
.ring .in{{width:116px;height:116px;border-radius:50%;background:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center}}
.ring .g{{font-size:3rem;font-weight:800;line-height:1;color:{gc}}}
.ring .s{{font-size:.8rem;color:var(--muted);margin-top:2px}}
.hero h1{{font-size:1.5rem;margin-bottom:4px}}
.hero .sub{{color:var(--muted);font-size:.92rem}}
.hero .tag{{display:inline-block;margin-top:10px;background:{gc}18;color:{gc};font-weight:700;
font-size:.82rem;padding:5px 12px;border-radius:20px}}
.sec{{padding:6px 30px 20px}}.sec h2{{font-size:.78rem;text-transform:uppercase;letter-spacing:1.2px;color:var(--muted);margin:16px 0 12px}}
.doms{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
@media(max-width:640px){{.doms{{grid-template-columns:1fr}}.hero{{flex-direction:column;text-align:center}}}}
.dom{{border:1px solid var(--line);border-radius:10px;padding:16px}}
.dom-h{{display:flex;justify-content:space-between;align-items:center}}
.dom-t{{font-weight:700}}
.dom-g{{color:#fff;font-weight:800;font-size:.85rem;width:30px;height:26px;border-radius:6px;display:inline-flex;align-items:center;justify-content:center}}
.bar{{height:7px;background:#eef0f5;border-radius:5px;margin:12px 0 6px;overflow:hidden}}
.bar span{{display:block;height:100%;border-radius:5px}}
.dom-s{{font-size:.78rem;color:var(--muted);font-weight:600}}
.dom-b{{font-size:.9rem;margin-top:6px}}.dom-blurb{{font-size:.78rem;margin-top:3px}}
.muted{{color:var(--muted)}}
.recs{{margin:0;padding-left:20px}}.recs li{{margin:8px 0;font-size:.95rem}}
.allclear{{background:#eafaf2;border:1px solid #c7eeda;color:#15794f;padding:14px 16px;border-radius:10px;font-size:.95rem}}
.cta{{margin:10px 30px 30px;background:linear-gradient(135deg,#4440DB,#5B57E8);color:#fff;border-radius:12px;padding:22px 26px}}
.cta h3{{font-size:1.1rem;margin-bottom:6px}}.cta p{{font-size:.92rem;opacity:.92;margin-bottom:14px}}
.cta a{{display:inline-block;background:#fff;color:#4440DB;font-weight:700;text-decoration:none;padding:10px 20px;border-radius:8px}}
.foot{{padding:18px 30px;border-top:1px solid var(--line);font-size:.75rem;color:var(--muted);display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}}
@media print{{body{{background:#fff}}.sheet{{box-shadow:none;border:none;margin:0}}.cta a{{display:none}}}}
</style></head><body>
<div class="sheet">
  <div class="top"><div class="brand">BV<span>TECH</span> · Security Scorecard</div>
    <div class="meta">Prepared for<br><b>{name}</b> · {gen}</div></div>
  <div class="hero">
    <div class="ring"><div class="in"><div class="g">{_esc(grade)}</div>
      <div class="s">{(str(int(score))+' / 100') if isinstance(score,(int,float)) else 'No data'}</div></div></div>
    <div><h1>{name}</h1>
      <div class="sub">A plain-English snapshot of your security posture across the systems BVTech monitors —
        devices, patching, Microsoft 365 identity, and open threats.</div>
      <span class="tag">Overall grade: {_esc(grade)}</span></div>
  </div>
  <div class="sec"><h2>Security domains</h2><div class="doms">{''.join(cards)}</div></div>
  <div class="sec"><h2>Priority recommendations</h2>{rec_block}</div>
  <div class="cta"><h3>Let's close these gaps together</h3>
    <p>BVTech can remediate every item above and keep this grade climbing — managed IT, patching,
       endpoint protection, and Microsoft 365 hardening, handled for you.</p>
    <a href="https://bvtech.org/contact/">Book a security review →</a></div>
  <div class="foot"><span>© BVTech LLC — Managed IT &amp; Cybersecurity</span>
    <span>Generated {gen} · (210) 538-3669 · bvtech.org</span></div>
</div></body></html>'''
