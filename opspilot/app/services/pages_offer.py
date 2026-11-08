"""High-converting lead-capture offer page for BVTech (v1.137) — /free-review/.

One focused landing page whose only job is to turn a visitor — or a click from a
cold email, a Google Business / LinkedIn post, or the Business mode bar — into a
booked "Free 20-Minute IT & Security Review". Tailored to general Houston /
Austin / San Antonio small businesses.

It reuses the site-wide, bvHuman-protected lead form (POST /tools-api/lead), so
every submission lands straight in the portal as a lead. No fabricated
testimonials and no invented phone number — only real, defensible claims.
Deterministic (no LLM tokens). Wired into destination._pages() so it ships,
gets a sitemap entry + FAQ schema, and is picked up by the nav/mode-bar sweep.
"""
from __future__ import annotations

from . import captcha

SITE = "https://bvtech.org"
EMAIL = "help@bvtech.org"

# What the prospect actually receives — concrete, not vague "consultation".
GET = [
    ("📧", "Email &amp; account security check",
     "We check how exposed your email, logins and Microsoft 365 are to the attacks "
     "that actually hit small businesses — phishing, stolen passwords, no MFA."),
    ("💾", "Backup &amp; recovery check",
     "We confirm whether your data is really backed up — and whether you could "
     "actually recover it after ransomware or a dead drive. Most businesses can't."),
    ("🛡️", "Your top-risks report",
     "A short, plain-English report of the 3–5 things most likely to bite your "
     "business, ranked, with exactly what to fix first."),
    ("💵", "A straight-talk quote",
     "If you want ongoing help, one simple flat-rate number — no hourly surprises, "
     "no pressure, no jargon. If you don't, keep the report and we part friends."),
]

STEPS = [
    ("1", "Book it",
     "Fill the quick form below — about 30 seconds. Tell us your business and what's "
     "been bugging you."),
    ("2", "20-minute review",
     "A real BVTech technician reviews your setup remotely — no disruption to your "
     "team, no sales pitch."),
    ("3", "Get your report",
     "You get a clear report and your top fixes. DIY it yourself, or have us handle "
     "it — your call, zero pressure."),
]

WHY = [
    ("📍", "Local &amp; licensed", "BVTech LLC — a Texas company serving Houston, Austin &amp; San Antonio."),
    ("🧑‍🔧", "Real technicians answer", "You talk to a person who fixes it, not a ticket black hole."),
    ("💳", "Flat-rate pricing", "Predictable monthly cost. No hourly surprises, ever."),
    ("🤝", "Genuinely no pressure", "The review is free and yours to keep — whether or not you hire us."),
]

FAQS = [
    ("Is the review really free?",
     "Yes — the 20-minute IT &amp; security review and your top-risks report are "
     "completely free, with no obligation. If you'd like ongoing help afterward "
     "we'll give you a simple flat-rate quote, but there's never any pressure."),
    ("What do I need to do to prepare?",
     "Nothing. Just book a time and tell us a little about your business. The review "
     "is done remotely and we'll walk you through anything we need."),
    ("Who is this for?",
     "Small and mid-sized Texas businesses — typically 3 to 250 employees — in "
     "Houston, Austin, San Antonio and the surrounding areas. Offices, clinics, law "
     "firms, trades, nonprofits and professional-services companies."),
    ("How soon will I hear back?",
     "Usually the same business day. A real BVTech technician reviews every request "
     "— you won't get an auto-responder and forget about it."),
]


def _form() -> str:
    hp = captcha.HONEYPOT_HTML
    return f"""
<form class="bv-lead" id="bv-lead" autocomplete="off" novalidate>
  <div class="bv-row">
    <input id="bv-name" type="text" name="name" placeholder="Your name" aria-label="Your name" autocomplete="name">
    <input id="bv-email" type="email" name="email" placeholder="Work email" aria-label="Work email" autocomplete="email" required>
  </div>
  <div class="bv-row">
    <input id="bv-company" type="text" name="company" placeholder="Business name (optional)" aria-label="Business name" autocomplete="organization">
    <input id="bv-phone" type="text" name="phone" placeholder="Phone (optional)" aria-label="Phone" autocomplete="tel">
  </div>
  <textarea id="bv-msg" rows="3" placeholder="What's going on? (slow computers, security worry, no IT person, just curious…)" aria-label="Message"></textarea>
  {hp}
  <button id="bv-send" type="submit">🛡️ Claim my free IT &amp; security review →</button>
  <p class="bv-note" id="bv-note">No spam, ever. A real person replies — usually the same business day.</p>
</form>
<script>
(function(){{
  var f=document.getElementById('bv-lead'), note=document.getElementById('bv-note'), btn=document.getElementById('bv-send');
  if(!f) return;
  var LABEL='🛡️ Claim my free IT &amp; security review →';
  f.addEventListener('submit',function(e){{
    e.preventDefault();
    var email=(document.getElementById('bv-email').value||'').trim();
    if(!/^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$/.test(email)){{ note.textContent='Please enter a valid work email.'; return; }}
    btn.disabled=true; btn.textContent='Sending…';
    var msg=(document.getElementById('bv-msg').value||'').trim();
    var phone=(document.getElementById('bv-phone').value||'').trim();
    if(phone) msg=(msg?msg+' · ':'')+'Phone: '+phone;
    fetch('/tools-api/lead',{{method:'POST',headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{email:email, name:(document.getElementById('bv-name').value||'').trim(),
        company:(document.getElementById('bv-company').value||'').trim(),
        tool:'Free Security Review', result:msg.slice(0,400)}})}})
      .then(function(r){{return r.json();}}).then(function(d){{
        if(d&&d.ok){{ f.innerHTML='<div class="bv-thanks"><b>You\\'re in — thank you!</b><br>Your free review request reached our team. We\\'ll reply shortly, usually the same business day. Watch your inbox (and check spam just in case).</div>'; }}
        else{{ btn.disabled=false; btn.innerHTML=LABEL; note.textContent=(d&&d.error)||'Could not send — please email help@bvtech.org.'; }}
      }}).catch(function(){{ btn.disabled=false; btn.innerHTML=LABEL; note.textContent='Could not send — please email help@bvtech.org.'; }});
  }});
}})();
</script>"""


def body() -> str:
    get = "".join(
        f'<div class="bv-card"><div class="bv-ic">{ic}</div><h3>{name}</h3><p>{desc}</p></div>'
        for ic, name, desc in GET)
    steps = "".join(
        f'<div class="of-step"><div class="of-num">{n}</div><div><h3>{t}</h3><p>{d}</p></div></div>'
        for n, t, d in STEPS)
    why = "".join(
        f'<div class="of-why"><span class="of-wic">{ic}</span><div><b>{t}</b><span>{d}</span></div></div>'
        for ic, t, d in WHY)
    faq = "".join(
        f'<div class="bv-faq"><h3>{q}</h3><p>{a}</p></div>' for q, a in FAQS)
    return f"""
<section class="bv">
<style>
.bv{{--o:#EB6F24;--o2:#F5BE58;max-width:1060px;margin:0 auto;padding:104px 18px 90px}}
@media(max-width:700px){{.bv{{padding-top:84px}}}}
.bv *{{box-sizing:border-box}}
.bv a{{color:var(--o2);text-decoration:none}}
.bv-hero{{border-radius:20px;padding:44px 34px;margin:0 0 30px;border:1px solid rgba(245,190,88,.28);
  background:linear-gradient(135deg,rgba(235,111,36,.16),rgba(68,64,219,.12));text-align:center}}
.bv-kick{{font-size:.74rem;letter-spacing:.14em;text-transform:uppercase;color:var(--o2);font-weight:800}}
.bv-hero h1{{font-family:var(--fh);color:var(--white,#fff);font-size:clamp(1.9rem,4.6vw,3rem);margin:12px 0 14px;line-height:1.07}}
.bv-ans{{color:var(--text,#dfe3f0);font-size:1.12rem;line-height:1.6;margin:0 auto 22px;max-width:680px}}
.bv-cta{{display:inline-flex;align-items:center;gap:8px;background:linear-gradient(135deg,var(--o),var(--o2));
  color:#0E0D2C;font-weight:800;padding:15px 30px;border-radius:12px;font-size:1.05rem}}
.bv-trust{{margin:16px 0 0;color:var(--muted,#9aa0b5);font-size:.82rem}}
.bv-h{{display:flex;align-items:center;gap:10px;margin:40px 0 18px;justify-content:center}}
.bv-h .pre{{width:4px;height:22px;border-radius:3px;background:linear-gradient(var(--o),var(--o2))}}
.bv-h h2{{font-family:var(--fh);color:var(--white,#fff);font-size:1.4rem;margin:0;font-weight:800;text-align:center}}
.bv-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}
@media(max-width:820px){{.bv-grid{{grid-template-columns:1fr}}}}
.bv-card{{border:1px solid var(--border,rgba(255,255,255,.12));border-radius:16px;background:var(--card,#17163a);padding:22px}}
.bv-ic{{font-size:1.8rem}}
.bv-card h3{{font-family:var(--fh);color:var(--white,#fff);font-size:1.08rem;margin:8px 0 6px}}
.bv-card p{{color:var(--muted,#9aa0b5);font-size:.92rem;line-height:1.55;margin:0}}
.of-steps{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}}
@media(max-width:820px){{.of-steps{{grid-template-columns:1fr}}}}
.of-step{{display:flex;gap:14px;align-items:flex-start;border:1px solid var(--border,rgba(255,255,255,.12));border-radius:16px;background:var(--card,#17163a);padding:20px}}
.of-num{{flex:0 0 auto;width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  font-family:var(--fh);font-weight:800;color:#0E0D2C;background:linear-gradient(135deg,var(--o),var(--o2))}}
.of-step h3{{font-family:var(--fh);color:var(--white,#fff);font-size:1.05rem;margin:4px 0 6px}}
.of-step p{{color:var(--muted,#9aa0b5);font-size:.9rem;line-height:1.55;margin:0}}
.of-whys{{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;margin:0 auto;max-width:860px}}
@media(max-width:700px){{.of-whys{{grid-template-columns:1fr}}}}
.of-why{{display:flex;gap:12px;align-items:flex-start}}
.of-wic{{font-size:1.4rem;flex:0 0 auto}}
.of-why b{{color:var(--white,#fff);display:block;font-size:.98rem}}
.of-why span{{color:var(--muted,#9aa0b5);font-size:.88rem;line-height:1.5}}
.bv-faq{{border-top:1px solid var(--border,rgba(255,255,255,.12));padding:16px 0}}
.bv-faq h3{{color:var(--white,#fff);font-size:1.02rem;margin:0 0 6px;font-family:var(--fh)}}
.bv-faq p{{color:var(--text,#dfe3f0);font-size:.94rem;line-height:1.6;margin:0}}
.bv-form-wrap{{border-radius:20px;padding:32px 28px;margin:30px 0 0;border:1px solid rgba(245,190,88,.3);
  background:linear-gradient(135deg,rgba(68,64,219,.2),rgba(235,111,36,.12))}}
.bv-form-wrap h2{{font-family:var(--fh);color:var(--white,#fff);margin:0 0 6px;font-size:1.5rem;text-align:center}}
.bv-form-wrap .sub{{color:var(--text,#dfe3f0);margin:0 0 20px;text-align:center}}
.bv-lead .bv-row{{display:flex;gap:12px;flex-wrap:wrap;margin:0 0 12px}}
.bv-lead input,.bv-lead textarea{{flex:1 1 220px;min-width:0;padding:13px 15px;border-radius:10px;
  border:1px solid rgba(127,127,160,.4);background:rgba(255,255,255,.04);color:var(--white,#fff);font-size:1rem;font-family:inherit}}
.bv-lead textarea{{width:100%;resize:vertical}}
.bv-lead button{{width:100%;background:linear-gradient(135deg,var(--o),var(--o2));color:#0E0D2C;border:0;font-weight:800;
  padding:15px 24px;border-radius:11px;cursor:pointer;font-size:1.05rem;margin-top:4px}}
.bv-note{{color:var(--muted,#9aa0b5);font-size:.82rem;margin:10px 0 0;text-align:center}}
.bv-thanks{{color:var(--text,#dfe3f0);font-size:1.05rem;line-height:1.6;text-align:center;padding:16px}}
.bv-thanks b{{color:var(--o2)}}
.bv-foot{{color:var(--muted,#9aa0b5);font-size:.82rem;margin-top:34px;line-height:1.6;text-align:center}}
</style>

<div class="bv-hero">
  <div class="bv-kick">🤠 BVTech LLC · Texas Managed IT &amp; Cybersecurity</div>
  <h1>Free 20-Minute IT &amp; Security Review for Texas Businesses</h1>
  <p class="bv-ans">Find out — in plain English — how secure your business really is, whether your
  backups actually work, and the top few things to fix. No cost, no pressure, no jargon.
  Done remotely by a real BVTech technician.</p>
  <a class="bv-cta" href="#bv-contact">🛡️ Claim my free review →</a>
  <div class="bv-trust">Serving Houston · Austin · San Antonio &amp; surrounding Texas · Licensed BVTech LLC</div>
</div>

<div class="bv-h"><span class="pre"></span><h2>What you get — free</h2></div>
<div class="bv-grid">{get}</div>

<div class="bv-h"><span class="pre"></span><h2>How it works</h2></div>
<div class="of-steps">{steps}</div>

<div class="bv-h"><span class="pre"></span><h2>Why businesses trust BVTech</h2></div>
<div class="of-whys">{why}</div>

<div class="bv-form-wrap" id="bv-contact">
  <h2>Claim your free review</h2>
  <p class="sub">Takes 30 seconds. A real BVTech technician replies — usually the same business day.</p>
  {_form()}
</div>

<div class="bv-h"><span class="pre"></span><h2>Questions? Answered.</h2></div>
<div>{faq}</div>

<p class="bv-foot">BVTech LLC is a Texas-based managed IT services provider (MSP) and cybersecurity company
serving small and mid-sized businesses in Houston, Austin, San Antonio and the surrounding communities.
Managed IT, cybersecurity, Microsoft 365, cloud, compliance and backup. Prefer email? Reach us at
<a href="mailto:{EMAIL}">{EMAIL}</a>.</p>
</section>"""


TITLE = "Free IT &amp; Security Review for Texas Businesses | BVTech"
DESC = ("Claim a free 20-minute IT & security review for your Houston, Austin or San Antonio "
        "business. A real BVTech technician checks your email security, backups and top risks "
        "and sends a plain-English report — no cost, no pressure.")


def review_offer() -> dict:
    """Page dict for destination._pages(): path, url, title, desc, body, faqs."""
    return dict(path="free-review/index.html", url=f"{SITE}/free-review/",
                title=TITLE, desc=DESC, body=body(), faqs=FAQS)
