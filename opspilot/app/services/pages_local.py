"""Local service-area landing pages for BVTech (v1.118) — the biggest local-SEO
lever for an MSP that wants the phone ringing in Houston, Austin and San Antonio.

Each city gets its own page at /managed-it-<city>/ because one generic page can't
rank across multiple metros. Every page is built for three audiences at once:

  * People searching Google ("managed IT services Houston") — a dedicated,
    keyword-aligned page with the city in the title, H1, URL and copy, plus
    LocalBusiness + FAQPage JSON-LD (added by destination.build_page).
  * AI answer engines (ChatGPT / Perplexity / Google AI Overviews) — a
    self-contained 40-60 word direct answer in the first paragraph and a visible
    Q&A block, the formats GEO/AEO research says engines lift verbatim.
  * Humans — a clean, fast page with a real, spam-proof contact form (the
    bvHuman proof-of-work widget is injected site-wide by the publisher).

Deterministic, no LLM tokens. Wired into destination._pages() so it ships, gets
a sitemap entry and an IndexNow ping with every destination publish.
"""
from __future__ import annotations

from . import captcha

SITE = "https://bvtech.org"
PHONE_NOTE = "help@bvtech.org"   # email CTA; no phone fabricated

# Core services pitched on every city page.
SERVICES = [
    ("🛟", "Managed IT & Helpdesk", "Flat-rate support, monitoring and maintenance that keeps your team working — fast answers from real Texas technicians."),
    ("🛡️", "Cybersecurity", "Endpoint protection, email security, MFA, patching and employee training to stop the attacks that actually hit small businesses."),
    ("☁️", "Cloud & Microsoft 365", "Migration, management and backup for Microsoft 365, Google Workspace and your line-of-business apps."),
    ("🔒", "Compliance", "Practical help with HIPAA, PCI, CMMC and cyber-insurance questionnaires — documented, audit-ready, no jargon."),
    ("💾", "Backup & Disaster Recovery", "Tested backups and a real recovery plan so a ransomware hit or dead server is an inconvenience, not a closure."),
    ("🧭", "vCIO & IT Strategy", "A technology roadmap and budget that fits your business, reviewed with you — not a sales pitch."),
]

# (slug, City, blurb about the metro, nearby areas) — local relevance signals.
CITIES = [
    ("houston", "Houston",
     "From the Energy Corridor and Downtown to Sugar Land, Katy and The Woodlands, "
     "Houston small businesses run on uptime. BVTech keeps your IT secure, backed up "
     "and supported so you can focus on the work.",
     ["Sugar Land", "Katy", "The Woodlands", "Pearland", "Cypress", "Energy Corridor"]),
    ("austin", "Austin",
     "Austin moves fast — startups, clinics, law firms and shops that can't afford "
     "downtime or a breach. BVTech delivers enterprise-grade IT and cybersecurity "
     "sized and priced for a growing Central Texas business.",
     ["Round Rock", "Cedar Park", "Georgetown", "Pflugerville", "San Marcos", "Domain"]),
    ("san-antonio", "San Antonio",
     "San Antonio businesses — from the Medical Center to downtown and the suburbs — "
     "trust BVTech for responsive IT support and serious security, including the "
     "compliance that healthcare, finance and government contractors need.",
     ["New Braunfels", "Schertz", "Boerne", "Stone Oak", "Alamo Heights", "Medical Center"]),
]


def _direct_answer(city: str) -> str:
    # 40-60 word self-contained answer engines can quote verbatim (GEO/AEO).
    return (f"BVTech LLC is a Texas-based managed IT services provider (MSP) and "
            f"cybersecurity company serving {city} small and mid-sized businesses. "
            f"We provide managed IT support, cybersecurity, Microsoft 365 and cloud, "
            f"compliance, and backup &amp; disaster recovery — flat-rate and local, "
            f"with fast response from real technicians. Contact BVTech at {PHONE_NOTE}.")


def _faqs(city: str) -> list[tuple[str, str]]:
    return [
        (f"Does BVTech provide managed IT services in {city}?",
         f"Yes. BVTech provides managed IT services, helpdesk support, cybersecurity, "
         f"Microsoft 365 and cloud, compliance and backup/disaster recovery for small "
         f"and mid-sized businesses throughout {city} and the surrounding area."),
        (f"How much do managed IT services cost in {city}?",
         "Most small businesses are on a simple flat monthly rate based on the number "
         "of users and devices, so your IT cost is predictable with no surprise hourly "
         "bills. Email help@bvtech.org for a free, no-pressure quote."),
        (f"How fast does BVTech respond to {city} support requests?",
         "Support requests are answered quickly by real technicians during business "
         "hours, with monitoring and automated maintenance running around the clock to "
         "prevent problems before they reach you."),
        ("What size businesses does BVTech work with?",
         "BVTech specializes in small and mid-sized Texas businesses — typically 5 to "
         "250 employees — including clinics, law firms, nonprofits, trades and "
         "professional-services companies."),
    ]


def _contact_form(city: str) -> str:
    hp = captcha.HONEYPOT_HTML
    return f"""
<form class="bv-lead" id="bv-lead" autocomplete="off" novalidate>
  <div class="bv-row">
    <input id="bv-name" type="text" name="name" placeholder="Your name" aria-label="Your name" autocomplete="name">
    <input id="bv-email" type="email" name="email" placeholder="Work email" aria-label="Work email" autocomplete="email" required>
  </div>
  <div class="bv-row">
    <input id="bv-company" type="text" name="company" placeholder="Company (optional)" aria-label="Company" autocomplete="organization">
  </div>
  <textarea id="bv-msg" rows="3" placeholder="How can we help your {city} business?" aria-label="Message"></textarea>
  {hp}
  <button id="bv-send" type="submit">Get my free IT &amp; security review →</button>
  <p class="bv-note" id="bv-note">No spam, ever. A real person replies — usually same business day.</p>
</form>
<script>
(function(){{
  var f=document.getElementById('bv-lead'), note=document.getElementById('bv-note'), btn=document.getElementById('bv-send');
  if(!f) return;
  f.addEventListener('submit',function(e){{
    e.preventDefault();
    var email=(document.getElementById('bv-email').value||'').trim();
    if(!/^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$/.test(email)){{ note.textContent='Please enter a valid work email.'; return; }}
    btn.disabled=true; btn.textContent='Sending…';
    fetch('/tools-api/lead',{{method:'POST',headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{email:email, name:(document.getElementById('bv-name').value||'').trim(),
        company:(document.getElementById('bv-company').value||'').trim(),
        tool:'Contact — {city}', result:(document.getElementById('bv-msg').value||'').trim().slice(0,400)}})}})
      .then(function(r){{return r.json();}}).then(function(d){{
        if(d&&d.ok){{ f.innerHTML='<div class="bv-thanks"><b>Thank you!</b><br>Your request reached our {city} team. We\\'ll reply shortly — usually the same business day.</div>'; }}
        else{{ btn.disabled=false; btn.textContent='Get my free IT &amp; security review →'; note.textContent=(d&&d.error)||'Could not send — please email help@bvtech.org.'; }}
      }}).catch(function(){{ btn.disabled=false; btn.textContent='Get my free IT &amp; security review →'; note.textContent='Could not send — please email help@bvtech.org.'; }});
  }});
}})();
</script>"""


def _body(slug: str, city: str, blurb: str, areas: list[str]) -> str:
    svc = "".join(
        f'<div class="bv-card"><div class="bv-ic">{ic}</div><h3>{name}</h3><p>{desc}</p></div>'
        for ic, name, desc in SERVICES)
    faq = "".join(
        f'<div class="bv-faq"><h3>{q}</h3><p>{a}</p></div>' for q, a in _faqs(city))
    others = "".join(
        f'<a href="/managed-it-{s}/">Managed IT in {c}</a>'
        for s, c, _, _ in CITIES if s != slug)
    area_chips = "".join(f"<span>{a}</span>" for a in areas)
    return f"""
<section class="bv">
<style>
.bv{{--o:#EB6F24;--o2:#F5BE58;max-width:1060px;margin:0 auto;padding:104px 18px 90px}}
@media(max-width:700px){{.bv{{padding-top:84px}}}}
.bv *{{box-sizing:border-box}}
.bv a{{color:var(--o2);text-decoration:none}}
.bv-hero{{border-radius:20px;padding:40px 34px;margin:0 0 30px;border:1px solid rgba(245,190,88,.28);
  background:linear-gradient(135deg,rgba(235,111,36,.16),rgba(68,64,219,.12))}}
.bv-kick{{font-size:.74rem;letter-spacing:.14em;text-transform:uppercase;color:var(--o2);font-weight:800}}
.bv-hero h1{{font-family:var(--fh);color:var(--white,#fff);font-size:clamp(1.8rem,4.2vw,2.7rem);margin:10px 0 14px;line-height:1.08}}
.bv-ans{{color:var(--text,#dfe3f0);font-size:1.08rem;line-height:1.6;margin:0 0 20px;max-width:760px}}
.bv-cta{{display:inline-flex;align-items:center;gap:8px;background:linear-gradient(135deg,var(--o),var(--o2));
  color:#0E0D2C;font-weight:800;padding:13px 26px;border-radius:12px}}
.bv-areas{{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0 0}}
.bv-areas span{{font-size:.76rem;color:var(--muted,#9aa0b5);border:1px solid var(--border,rgba(255,255,255,.12));border-radius:999px;padding:4px 11px}}
.bv-h{{display:flex;align-items:center;gap:10px;margin:36px 0 18px}}
.bv-h .pre{{width:4px;height:22px;border-radius:3px;background:linear-gradient(var(--o),var(--o2))}}
.bv-h h2{{font-family:var(--fh);color:var(--white,#fff);font-size:1.35rem;margin:0;font-weight:800}}
.bv-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}}
@media(max-width:820px){{.bv-grid{{grid-template-columns:1fr}}}}
.bv-card{{border:1px solid var(--border,rgba(255,255,255,.12));border-radius:16px;background:var(--card,#17163a);padding:20px}}
.bv-ic{{font-size:1.7rem}}
.bv-card h3{{font-family:var(--fh);color:var(--white,#fff);font-size:1.05rem;margin:8px 0 6px}}
.bv-card p{{color:var(--muted,#9aa0b5);font-size:.9rem;line-height:1.55;margin:0}}
.bv-faq{{border-top:1px solid var(--border,rgba(255,255,255,.12));padding:16px 0}}
.bv-faq h3{{color:var(--white,#fff);font-size:1.02rem;margin:0 0 6px;font-family:var(--fh)}}
.bv-faq p{{color:var(--text,#dfe3f0);font-size:.94rem;line-height:1.6;margin:0}}
.bv-form-wrap{{border-radius:20px;padding:30px 28px;margin:28px 0 0;border:1px solid rgba(245,190,88,.3);
  background:linear-gradient(135deg,rgba(68,64,219,.2),rgba(235,111,36,.12))}}
.bv-form-wrap h2{{font-family:var(--fh);color:var(--white,#fff);margin:0 0 6px;font-size:1.4rem}}
.bv-form-wrap .sub{{color:var(--text,#dfe3f0);margin:0 0 18px}}
.bv-lead .bv-row{{display:flex;gap:12px;flex-wrap:wrap;margin:0 0 12px}}
.bv-lead input,.bv-lead textarea{{flex:1 1 220px;min-width:0;padding:13px 15px;border-radius:10px;
  border:1px solid rgba(127,127,160,.4);background:rgba(255,255,255,.04);color:var(--white,#fff);font-size:1rem;font-family:inherit}}
.bv-lead textarea{{width:100%;resize:vertical}}
.bv-lead button{{background:linear-gradient(135deg,var(--o),var(--o2));color:#0E0D2C;border:0;font-weight:800;
  padding:13px 24px;border-radius:11px;cursor:pointer;font-size:1rem;margin-top:4px}}
.bv-note{{color:var(--muted,#9aa0b5);font-size:.82rem;margin:10px 0 0}}
.bv-thanks{{color:var(--text,#dfe3f0);font-size:1.05rem;line-height:1.6;text-align:center;padding:16px}}
.bv-thanks b{{color:var(--o2)}}
.bv-other{{display:flex;flex-wrap:wrap;gap:14px;margin:30px 0 0}}
.bv-other a{{font-weight:700}}
.bv-foot{{color:var(--muted,#9aa0b5);font-size:.82rem;margin-top:30px;line-height:1.6}}
</style>

<div class="bv-hero">
  <div class="bv-kick">🤠 BVTech LLC · Texas Managed IT &amp; Cybersecurity</div>
  <h1>Managed IT Services &amp; Cybersecurity in {city}</h1>
  <p class="bv-ans">{_direct_answer(city)}</p>
  <a class="bv-cta" href="#bv-contact">Get a free IT &amp; security review →</a>
  <div class="bv-areas">{area_chips}</div>
</div>

<p class="bv-ans" style="max-width:820px">{blurb}</p>

<div class="bv-h"><span class="pre"></span><h2>What we do for {city} businesses</h2></div>
<div class="bv-grid">{svc}</div>

<div class="bv-h"><span class="pre"></span><h2>{city} IT services — common questions</h2></div>
<div>{faq}</div>

<div class="bv-form-wrap" id="bv-contact">
  <h2>Talk to a real {city} technician</h2>
  <p class="sub">Tell us what's going on. We'll give you a straight answer and a free review — no pressure, no spam.</p>
  {_contact_form(city)}
</div>

<div class="bv-h"><span class="pre"></span><h2>We also serve</h2></div>
<div class="bv-other">{others}<a href="/explore/">🧭 Explore</a><a href="/blog/">📰 BVTech Blog</a></div>

<p class="bv-foot">BVTech LLC is a Texas-based managed IT services provider (MSP) serving {city} and the surrounding communities ({", ".join(areas)}). Managed IT, cybersecurity, Microsoft 365, cloud, compliance and backup for small and mid-sized businesses. Email <a href="mailto:help@bvtech.org">help@bvtech.org</a>.</p>
</section>"""


def city_pages() -> list[dict]:
    """Page dicts for destination._pages(): path, url, title, desc, body, faqs."""
    out = []
    for slug, city, blurb, areas in CITIES:
        out.append({
            "path": f"managed-it-{slug}/index.html",
            "url": f"{SITE}/managed-it-{slug}/",
            "title": f"Managed IT Services & Cybersecurity in {city}, TX | BVTech LLC",
            "desc": (f"BVTech LLC provides managed IT services, cybersecurity, "
                     f"Microsoft 365 and compliance for small businesses in {city}, "
                     f"Texas. Flat-rate, local, fast response. Free IT & security review."),
            "body": _body(slug, city, blurb, areas),
            "faqs": _faqs(city),
        })
    return out
