#!/usr/bin/env python3
"""Texas Roots — Plant Database generator.
Builds: /database/index.html, /database/<slug>.html for each plant, /database/identify.html
Run from site root: python3 generator/build_plants.py
Shares chrome helpers with build.py-style head/nav/footer but root-relative for /database/.
"""
import os, html, json, sys
sys.path.insert(0, os.path.dirname(__file__))
from plants_data import ALL_PLANTS as PLANTS, PLANT_CATS
from propagation import propagation_sections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "database")
os.makedirs(DB, exist_ok=True)
SITE = "https://tx-plants.com"
def esc(s): return html.escape(str(s), quote=True)

FONTS = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;0,9..144,900;1,9..144,400;1,9..144,500&family=Spline+Sans:wght@400;500;600;700&family=Spline+Sans+Mono:wght@400;500&display=swap" rel="stylesheet">'

FAVICON = '''<link rel="icon" href="../favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="../assets/favicon/favicon-32.png">
<link rel="icon" type="image/png" sizes="16x16" href="../assets/favicon/favicon-16.png">
<link rel="apple-touch-icon" href="../assets/favicon/apple-touch-icon.png">
<link rel="manifest" href="../site.webmanifest">
<meta name="theme-color" content="#1B2B22">'''

def head(title, desc, canonical, schema_blocks=None, extra_css=""):
    schema = ""
    for s in (schema_blocks or []):
        schema += f'<script type="application/ld+json">{json.dumps(s)}</script>\n'
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="author" content="Jordan Polasek">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="article"><meta property="og:url" content="{canonical}">
<meta property="og:image" content="{SITE}/assets/img/tunnel-entrance.jpg">
{FAVICON}
{FONTS}
<link rel="stylesheet" href="../assets/styles.css">
<style>{extra_css}</style>
{schema}</head>
<body>'''

def nav(active=""):
    def cls(x): return ' class="active"' if x==active else ''
    return f'''<header class="nav"><div class="wrap nav-inner">
  <a href="../index.html" class="brand"><svg viewBox="0 0 40 40" fill="none"><path d="M20 36V16" stroke="#5C8A3A" stroke-width="2.4" stroke-linecap="round"/><path d="M20 22C20 14 12 10 6 11c-1 7 5 14 14 11Z" fill="#5C8A3A" fill-opacity="0.85"/><path d="M20 18C20 11 27 7 33 9c1 6-4 12-13 9Z" fill="#1B2B22"/><circle cx="20" cy="36" r="2.4" fill="#C99A3B"/></svg><span class="name">Texas <b>Roots</b></span></a>
  <nav class="nav-links" id="navLinks"><a href="../start-here.html">Start Here</a><a href="index.html"{cls("database")}>Plant Database</a><a href="../almanac/index.html">Almanac</a><a href="../blog/index.html">Blog</a><a href="../weather.html">Weather</a><a href="../shop.html">Shop</a><a href="../community/index.html">Community</a><a href="../nomad.html">Go Offline</a><a href="../order.html" class="nav-cta">Order Now</a></nav>
  <button class="burger" id="burger" aria-label="Menu"><span></span><span></span><span></span></button>
</div></header>'''

def footer():
    return '''<footer><div class="wrap">
  <div class="foot-grid">
    <div class="foot-brand"><a href="../index.html" class="brand"><svg viewBox="0 0 40 40" fill="none"><path d="M20 36V16" stroke="#7CB342" stroke-width="2.4" stroke-linecap="round"/><path d="M20 22C20 14 12 10 6 11c-1 7 5 14 14 11Z" fill="#7CB342" fill-opacity="0.85"/><path d="M20 18C20 11 27 7 33 9c1 6-4 12-13 9Z" fill="#EAE2CF"/><circle cx="20" cy="36" r="2.4" fill="#C99A3B"/></svg><span class="name" style="color:#F3EEE2">Texas <b style="color:#7CB342">Roots</b></span></a><p>Heirloom seeds &amp; rooted cuttings, grown and mailed by hand from El Campo, Texas. A free plant database &amp; knowledge base for growers everywhere. Founded &amp; built by Jordan Polasek.</p></div>
    <div class="foot-col"><h4>Plant Database</h4><a href="index.html">Browse all plants</a><a href="identify.html">Identify a plant</a><a href="index.html#survival">Survival crops</a><a href="index.html#wild">Wild &amp; foraged</a></div>
    <div class="foot-col"><h4>Texas Roots</h4><a href="../shop.html">Shop seeds &amp; cuttings</a><a href="../almanac/index.html">The Almanac</a><a href="../weather.html">Garden weather</a><a href="../about.html">Our story</a></div>
    <div class="foot-col"><h4>More</h4><a href="../faq.html">FAQ</a><a href="../nomad.html">Go offline</a><a href="../vault.html">Knowledge Vault</a><a href="https://jordanpolasek.com">JordanPolasek.com</a><a href="https://bvtech.org">BVTech.org</a><a href="https://autumnpolasek.com">In Remembrance of Autumn 🐾</a></div>
  </div>
  <div class="foot-scripture" style="text-align:center;color:rgba(243,238,226,.55);font-style:italic;padding:0 0 18px;font-size:.9rem">&ldquo;So neither he who plants nor he who waters is anything, but only God, who gives the growth.&rdquo; &mdash; 1 Corinthians 3:7</div><div class="foot-bottom"><span>© <span id="yr"></span> Texas Roots · El Campo, TX · tx-plants.com</span><span>Written &amp; built by <a href="https://jordanpolasek.com">Jordan Polasek</a></span></div>
</div></footer>
<script>document.getElementById('yr').textContent=new Date().getFullYear();const burger=document.getElementById('burger'),navLinks=document.getElementById('navLinks');burger.addEventListener('click',()=>navLinks.classList.toggle('open'));navLinks.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>navLinks.classList.remove('open')));const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target)}}),{threshold:.12});document.querySelectorAll('.reveal').forEach(el=>io.observe(el));</script>
</body></html>'''

TAG_LABELS = {
 "edible":"Edible","medicinal":"Medicinal","native-tx":"Texas native","drought":"Drought-tough",
 "survival":"Survival crop","perennial":"Perennial","annual":"Annual","full-sun":"Full sun",
 "part-shade":"Part shade","beginner":"Beginner-friendly","container":"Container-friendly",
 "in-shop":"We sell it","storage-crop":"Stores well","staple-calorie":"Staple calories",
 "nitrogen-fixer":"Fixes nitrogen","cover-crop":"Cover crop","pollinator":"Pollinator",
 "heat-lover":"Heat-lover","cool-season":"Cool-season","wild":"Wild / foraged","forage":"Foraged",
 "soil-builder":"Builds soil","cut-and-come-again":"Cut-and-come-again","vigorous":"Vigorous",
 "nutrient-dense":"Nutrient-dense","beginner-forage":"Safe first forage","native-adjacent":"Tough as a native",
 "low-water":"Low water",
}
def tag_label(t): return TAG_LABELS.get(t, t.replace("-"," ").title())

# ---------- PLANT PAGE CSS ----------
PLANT_CSS = """
.pl-crumbs{font-family:'Spline Sans Mono',monospace;font-size:.78rem;color:var(--ink-faint);padding:24px 0 0}
.pl-crumbs a{color:var(--sprout);text-decoration:none}
.pl-hero{display:grid;grid-template-columns:1fr 1fr;gap:44px;align-items:center;padding:30px 0 44px;border-bottom:1px solid var(--line)}
.pl-hero .cat-pill{display:inline-block;font-family:'Spline Sans Mono',monospace;font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;padding:5px 12px;border-radius:30px;color:#fff;margin-bottom:16px}
.pl-hero h1{font-size:clamp(2.1rem,4.2vw,3.2rem);line-height:1.05;margin-bottom:6px}
.pl-hero .latin{font-family:'Fraunces',serif;font-style:italic;font-size:1.2rem;color:var(--ink-faint);margin-bottom:4px}
.pl-hero .fam{font-family:'Spline Sans Mono',monospace;font-size:.8rem;color:var(--ink-faint);margin-bottom:16px}
.pl-hero .summary{font-size:1.12rem;color:var(--ink-soft);line-height:1.6;margin-bottom:18px}
.pl-hero .pl-illus{width:100%;border:1px solid var(--line);border-radius:6px}
.pl-tags{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px}
.pl-tag{font-family:'Spline Sans Mono',monospace;font-size:.7rem;letter-spacing:.04em;text-transform:uppercase;background:var(--paper-warm);border:1px solid var(--line);color:var(--ink-soft);padding:5px 10px;border-radius:20px}
.pl-tag.shop{background:var(--sprout);color:#fff;border-color:var(--sprout)}
.quick-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;background:var(--line);border:1px solid var(--line);border-radius:6px;overflow:hidden;margin:36px 0}
.quick-cell{background:var(--paper-card);padding:16px 18px}
.quick-cell .k{font-family:'Spline Sans Mono',monospace;font-size:.66rem;letter-spacing:.07em;text-transform:uppercase;color:var(--clay);margin-bottom:5px}
.quick-cell .v{font-size:1rem;color:var(--ink);font-weight:500;line-height:1.3}
.pl-layout{display:grid;grid-template-columns:1fr 290px;gap:50px;padding:44px 0 70px;align-items:start}
.pl-body h2{font-size:1.55rem;margin:34px 0 12px}
.pl-body h2:first-child{margin-top:0}
.pl-body p{margin-bottom:16px;color:var(--ink-soft);font-size:1.06rem;line-height:1.72}
.idbox{background:var(--paper-warm);border:1px solid var(--line);border-left:4px solid var(--sprout);border-radius:0 6px 6px 0;padding:20px 24px;margin:30px 0}
.idbox h3{font-size:1.2rem;margin-bottom:12px;display:flex;align-items:center;gap:9px}
.idbox ul{margin:0 0 0 4px;list-style:none}
.idbox li{padding:7px 0 7px 26px;position:relative;color:var(--ink-soft);border-bottom:1px dashed var(--line-soft)}
.idbox li:last-child{border-bottom:0}
.idbox li::before{content:"✦";position:absolute;left:0;color:var(--sprout)}
.lookbox{background:rgba(181,85,47,.07);border:1px solid rgba(181,85,47,.3);border-left:4px solid var(--clay);border-radius:0 6px 6px 0;padding:20px 24px;margin:30px 0}
.lookbox h3{font-size:1.2rem;margin-bottom:12px;color:var(--clay);display:flex;align-items:center;gap:9px}
.lookbox .look{padding:10px 0;border-bottom:1px solid rgba(181,85,47,.18)}
.lookbox .look:last-child{border-bottom:0}
.lookbox .look b{color:var(--ink);font-family:'Fraunces',serif}
.lookbox .look p{margin:4px 0 0;font-size:.97rem;color:var(--ink-soft)}
.edbox{background:rgba(124,179,66,.1);border:1px solid rgba(92,138,58,.3);border-radius:6px;padding:20px 24px;margin:30px 0}
.edbox h3{font-size:1.2rem;margin-bottom:12px;color:var(--sprout)}
.edbox .row{display:flex;gap:12px;padding:7px 0;font-size:.98rem}
.edbox .row .lbl{font-family:'Spline Sans Mono',monospace;font-size:.7rem;letter-spacing:.05em;text-transform:uppercase;color:var(--ink-faint);min-width:64px;padding-top:3px}
.edbox .caution{color:var(--clay);font-weight:500}
.pl-side .card{background:var(--paper-warm);border:1px solid var(--line);border-radius:6px;padding:22px;margin-bottom:18px}
.pl-side .card h4{font-family:'Spline Sans Mono',monospace;font-size:.72rem;letter-spacing:.07em;text-transform:uppercase;color:var(--clay);margin-bottom:12px}
.pl-side .card a{display:block;color:var(--ink-soft);text-decoration:none;font-size:.93rem;padding:7px 0;border-bottom:1px solid var(--line);transition:color .2s}
.pl-side .card a:last-child{border-bottom:0}.pl-side .card a:hover{color:var(--sprout)}
.pl-side .companions span{display:inline-block;background:var(--paper-card);border:1px solid var(--line);border-radius:20px;padding:4px 11px;font-size:.84rem;margin:0 6px 6px 0;color:var(--ink-soft)}
.shop-cta{background:var(--ink);color:var(--paper);border-radius:6px;padding:24px;position:sticky;top:90px}
.shop-cta h4{color:var(--gold);font-family:'Spline Sans Mono',monospace;font-size:.72rem;letter-spacing:.07em;text-transform:uppercase;margin-bottom:10px}
.shop-cta p{font-size:.95rem;color:rgba(243,238,226,.82);margin-bottom:16px;line-height:1.55}
.shop-cta .btn{width:100%;justify-content:center}
.weather-nudge{background:var(--paper-warm);border:1px dashed var(--sprout);border-radius:6px;padding:16px 18px;margin:24px 0;font-size:.95rem;color:var(--ink-soft)}
.weather-nudge a{color:var(--sprout);font-weight:600;text-decoration:none}
.pl-related{background:var(--paper-warm);padding:56px 0;border-top:1px solid var(--line)}
.pl-related h3{font-size:1.5rem;margin-bottom:22px}
.plr-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
.growguide{margin:38px 0 0;padding:34px 0 0;border-top:2px solid var(--sprout)}
.growguide>.gg-eyebrow{font-family:'Spline Sans Mono',monospace;font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:var(--sprout);margin-bottom:6px}
.growguide>h2{font-size:1.7rem;margin:0 0 8px}
.growguide>.gg-intro{color:var(--ink-soft);font-size:1.05rem;margin-bottom:8px}
.gg-block{margin:26px 0}
.gg-block h3{font-size:1.3rem;margin:0 0 10px;color:var(--ink);display:flex;align-items:center;gap:10px}
.gg-block h3 .gg-ic{width:26px;height:26px;flex:none;color:var(--sprout)}
.gg-block p{margin:0 0 14px;color:var(--ink-soft);font-size:1.05rem;line-height:1.72}
.gg-block p:last-child{margin-bottom:0}
.nomad-callout{background:linear-gradient(135deg,#141F19,#1B2B22);color:var(--paper);border-radius:8px;padding:26px 28px;margin:34px 0;border:1px solid rgba(124,179,66,.3)}
.nomad-callout .nc-tag{font-family:'Spline Sans Mono',monospace;font-size:.68rem;letter-spacing:.1em;text-transform:uppercase;color:var(--gold);margin-bottom:10px}
.nomad-callout h3{color:var(--paper);font-size:1.35rem;margin-bottom:10px}
.nomad-callout p{color:rgba(243,238,226,.84);font-size:1rem;line-height:1.6;margin-bottom:16px}
.nomad-callout a{color:var(--sprout-bright);font-weight:600;text-decoration:none;border-bottom:1px solid rgba(124,179,66,.4)}
.nomad-callout a:hover{color:var(--paper)}
.plr-card{background:var(--paper-card);border:1px solid var(--line);border-radius:6px;overflow:hidden;text-decoration:none;color:inherit;transition:transform .2s,box-shadow .2s}
.plr-card:hover{transform:translateY(-4px);box-shadow:5px 7px 0 var(--shadow)}
.plr-card img{width:100%;height:120px;object-fit:cover}
.plr-card .b{padding:16px}
.plr-card .b .c{font-family:'Spline Sans Mono',monospace;font-size:.66rem;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px}
.plr-card .b h4{font-size:1.05rem;line-height:1.2;margin-bottom:5px}
.plr-card .b .l{font-style:italic;font-family:'Fraunces',serif;font-size:.85rem;color:var(--ink-faint)}
@media(max-width:900px){.pl-hero{grid-template-columns:1fr;gap:24px}.pl-layout{grid-template-columns:1fr;gap:30px}.shop-cta{position:static}.plr-grid{grid-template-columns:1fr}}
"""

def plant_schema(p):
    cat = PLANT_CATS[p["category"]]
    blocks = []
    art = {"@context":"https://schema.org","@type":"Article",
        "headline":f"{p['common']} ({p['latin']}) — Growing & Identification Guide",
        "description":p["summary"],
        "author":{"@type":"Person","name":"Jordan Polasek","url":"https://jordanpolasek.com"},
        "publisher":{"@type":"Organization","name":"Texas Roots","url":SITE},
        "about":{"@type":"Thing","name":p["common"],"alternateName":p["latin"]},
        "mainEntityOfPage":f"{SITE}/database/{p['slug']}.html","inLanguage":"en-US",
        "image":{"@type":"ImageObject","url":f"{SITE}/assets/img/plants/{p['category']}.svg",
                 "caption":f"{p['common']} growing & identification guide — Texas Roots, written by Jordan Polasek"}}
    blocks.append(art)
    crumb = {"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[
        {"@type":"ListItem","position":1,"name":"Plant Database","item":f"{SITE}/database/"},
        {"@type":"ListItem","position":2,"name":cat["name"],"item":f"{SITE}/database/#{p['category']}"},
        {"@type":"ListItem","position":3,"name":p["common"],"item":f"{SITE}/database/{p['slug']}.html"}]}
    blocks.append(crumb)
    # HowTo schema from the propagation/cultivation method steps
    _, methods = propagation_sections(p)
    if methods:
        howto = {"@context":"https://schema.org","@type":"HowTo",
            "name":f"How to Grow & Propagate {p['common']}",
            "description":f"How to propagate, grow, harvest, and save {p['common']} ({p['latin']}) in Texas and the Gulf Coast.",
            "author":{"@type":"Person","name":"Jordan Polasek","url":"https://jordanpolasek.com"},
            "step":[{"@type":"HowToStep","name":n,"text":t} for n,t in methods]}
        blocks.append(howto)
    return blocks

def build_plant(p):
    cat = PLANT_CATS[p["category"]]
    url = f"{SITE}/database/{p['slug']}.html"
    quick = "".join(f'<div class="quick-cell"><div class="k">{esc(k)}</div><div class="v">{esc(v)}</div></div>' for k,v in p["quick"].items())
    tags = "".join(f'<span class="pl-tag{" shop" if t=="in-shop" else ""}">{esc(tag_label(t))}</span>' for t in p["tags"])
    sections = "".join(f'<h2>{esc(h)}</h2><p>{esc(t)}</p>' for h,t in p["sections"])

    # ---- v5: deep grow & propagation guide ----
    gg_secs, _ = propagation_sections(p)
    ICONS = {
        "propagate":'<svg class="gg-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22V12M12 12C12 8 9 5 4 5c0 5 3 8 8 8M12 12c0-4 3-7 8-7 0 5-3 7-8 7" stroke-linecap="round"/></svg>',
        "growing":'<svg class="gg-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M12 12v9M8 16l4 2 4-2" stroke-linecap="round"/></svg>',
        "harvest":'<svg class="gg-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 20c6-2 10-6 14-14M9 13c-2-1-4-1-5 1 2 1 4 1 5-1ZM15 7c1-2 3-3 5-2-1 2-3 3-5 2Z" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        "free":'<svg class="gg-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M9 9h4a2 2 0 010 4H9m0 0v3m0-7V6" stroke-linecap="round"/></svg>',
        "forage":'<svg class="gg-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v18M12 3l4 3M12 3l-4 3M5 21h14" stroke-linecap="round"/></svg>',
    }
    def gg_icon(heading):
        h = heading.lower()
        if "propagate" in h: return ICONS["propagate"]
        if "growing" in h: return ICONS["growing"]
        if "harvest" in h: return ICONS["harvest"]
        if "free" in h: return ICONS["free"]
        if "forage" in h: return ICONS["forage"]
        return ICONS["growing"]
    gg_blocks = "".join(
        f'<div class="gg-block"><h3>{gg_icon(h)}{esc(h)}</h3>' +
        "".join(f'<p>{esc(par)}</p>' for par in paras) + '</div>'
        for h, paras in gg_secs)
    growguide = (f'<section class="growguide"><div class="gg-eyebrow">The grow guide</div>'
                 f'<h2>How to grow &amp; propagate {esc(p["common"].lower())}</h2>'
                 f'<p class="gg-intro">Everything I\'ve worked out about starting this one, '
                 f'keeping it alive through a Texas year, and turning one plant into many — free.</p>'
                 f'{gg_blocks}</section>')

    # ---- v5: NOMAD callout on survival/staple plants ----
    nomad = ""
    if any(t in p["tags"] for t in ("survival","staple-calorie","storage-crop","medicinal")):
        nomad = ('<div class="nomad-callout"><div class="nc-tag">When the grid is down</div>'
                 f'<h3>Keep this knowledge offline</h3>'
                 f'<p>A garden full of {esc(p["common"].lower())} is a real asset when times get '
                 'hard — but the know-how to grow, store, and use it shouldn\'t live only on a '
                 'website you can\'t reach. That\'s why I keep a copy of the references I rely on '
                 'on a local server at home. <a href="../nomad.html">Project NOMAD</a> is a free, '
                 'open-source way to run Wikipedia, survival and medical guides, maps, and even a '
                 'private AI on your own hardware — knowledge that keeps working with no internet, '
                 'no cloud, no signal.</p>'
                 '<a href="../nomad.html">See how I keep my library offline →</a></div>')

    idbox = ""
    if p.get("id_marks"):
        items = "".join(f'<li>{esc(m)}</li>' for m in p["id_marks"])
        idbox = f'<div class="idbox"><h3>🔎 How to identify it</h3><ul>{items}</ul></div>'

    lookbox = ""
    if p.get("lookalikes"):
        looks = "".join(f'<div class="look"><b>{esc(n)}</b><p>{esc(d)}</p></div>' for n,d in p["lookalikes"])
        lookbox = f'<div class="lookbox"><h3>⚠ Lookalikes &amp; safety</h3>{looks}</div>'

    edbox = ""
    if p.get("edible"):
        e = p["edible"]
        edbox = (f'<div class="edbox"><h3>Edibility</h3>'
                 f'<div class="row"><span class="lbl">Parts</span><span>{esc(e["parts"])}</span></div>'
                 f'<div class="row"><span class="lbl">Uses</span><span>{esc(e["uses"])}</span></div>'
                 f'<div class="row"><span class="lbl">Caution</span><span class="caution">{esc(e["caution"])}</span></div></div>')
    elif p.get("edible") is None and "edible" not in p["tags"]:
        edbox = '<div class="edbox" style="background:rgba(90,107,114,.08);border-color:rgba(90,107,114,.3)"><h3 style="color:var(--ink-soft)">Not for eating</h3><div class="row"><span>Grown for the garden, soil, or pollinators — not as food.</span></div></div>'

    # weather nudge
    weather = '<div class="weather-nudge">🌤 Before you plant: check the <a href="../weather.html">live 7-day garden weather</a> to time it right for frost and heat.</div>'

    # shop CTA
    if p.get("in_shop"):
        shop = (f'<div class="shop-cta"><h4>Grow this one</h4>'
                f'<p>We grow and mail {esc(p["common"].lower())} from the El Campo greenhouse — {esc(p.get("sku_hint","seed &amp; cuttings"))}, packed by hand.</p>'
                f'<a class="btn btn-light" href="../shop.html">Shop the catalog →</a></div>')
    else:
        shop = (f'<div class="shop-cta"><h4>Start your garden</h4>'
                f'<p>Heirloom seeds &amp; rooted cuttings, grown in living soil and mailed flat-rate from Texas.</p>'
                f'<a class="btn btn-light" href="../shop.html">Browse the catalog →</a></div>')

    # companions
    comp = ""
    if p.get("companion"):
        chips = "".join(f'<span>{esc(c)}</span>' for c in p["companion"])
        comp = f'<div class="card companions"><h4>Plant it with</h4>{chips}</div>'

    # related: same category
    same = [x for x in PLANTS if x["category"]==p["category"] and x["slug"]!=p["slug"]]
    rel = (same + [x for x in PLANTS if x["category"]!=p["category"]])[:3]
    rel_html = "".join(
        f'<a class="plr-card" href="{r["slug"]}.html"><img src="../assets/img/plants/{r["category"]}.svg" alt="{esc(r["common"])} ({esc(r["latin"])}) — Texas Roots plant database, by Jordan Polasek" loading="lazy"><div class="b"><div class="c" style="color:{PLANT_CATS[r["category"]]["color"]}">{esc(PLANT_CATS[r["category"]]["name"])}</div><h4>{esc(r["common"])}</h4><div class="l">{esc(r["latin"])}</div></div></a>'
        for r in rel)

    # side: more in category
    side_links = "".join(f'<a href="{x["slug"]}.html"{" style=font-weight:600;color:var(--sprout)" if x["slug"]==p["slug"] else ""}>{esc(x["common"])}</a>' for x in [y for y in PLANTS if y["category"]==p["category"]])

    page = head(f"{p['common']} ({p['latin']}) — Growing, Identification & Edibility | Texas Roots Plant Database",
                f"{p['summary']} Free growing data, identification marks, lookalikes, and edibility for {p['common']} — from the Texas Roots plant database.",
                url, plant_schema(p), PLANT_CSS)
    page += nav("database")
    page += f'''<div class="wrap"><div class="pl-crumbs"><a href="index.html">Plant Database</a> / <a href="index.html#{p['category']}">{esc(cat['name'])}</a> / {esc(p['common'])}</div></div>
<div class="wrap"><div class="pl-hero">
<div>
<span class="cat-pill" style="background:{cat['color']}">{esc(cat['name'])}</span>
<h1>{esc(p['common'])}</h1>
<div class="latin">{esc(p['latin'])}</div>
<div class="fam">{esc(p['family'])}</div>
<p class="summary">{esc(p['summary'])}</p>
<div class="pl-tags">{tags}</div>
</div>
<div><img class="pl-illus" src="../assets/img/plants/{p['category']}.svg" alt="{esc(p['common'])} ({esc(p['latin'])}) illustration — Texas Roots plant database, by Jordan Polasek"></div>
</div></div>
<div class="wrap">
<div class="quick-grid">{quick}</div>
<div class="pl-layout">
<article class="pl-body">
{sections}
{idbox}
{lookbox}
{edbox}
{growguide}
{nomad}
{weather}
<hr style="border:0;border-top:1px solid var(--line);margin:34px 0 20px">
<p style="font-size:.93rem;color:var(--ink-faint)">Part of the free Texas Roots plant database, compiled by <a href="https://jordanpolasek.com" style="color:var(--sprout)">Jordan Polasek</a> from his greenhouse in El Campo, Texas. Free to read and share. If it helped, the best thanks is to <a href="../shop.html" style="color:var(--sprout)">grow something</a>.</p>
</article>
<aside class="pl-side">
{shop}
<div class="card"><h4>More in {esc(cat['name'])}</h4>{side_links}</div>
{comp}
<div class="card"><h4>Tools</h4><a href="identify.html">🔎 Identify a plant</a><a href="../weather.html">🌤 7-day garden weather</a><a href="../almanac/index.html">📖 The Almanac</a></div>
</aside>
</div></div>
<section class="pl-related"><div class="wrap"><h3>Keep exploring the database</h3><div class="plr-grid">{rel_html}</div></div></section>
'''
    page += footer()
    open(os.path.join(DB, f"{p['slug']}.html"), "w").write(page)


# ---------- DATABASE BROWSE INDEX ----------
INDEX_CSS = """
.db-hero{background:var(--ink);color:var(--paper);padding:78px 0 64px;position:relative;overflow:hidden}
.db-hero::after{content:"";position:absolute;inset:0;background:url(../assets/img/greenhouse-bags.jpg) center/cover;opacity:.13}
.db-hero .wrap{position:relative;z-index:2;max-width:74ch}
.db-hero .eyebrow{color:var(--gold)}
.db-hero h1{font-size:clamp(2.3rem,5vw,3.7rem);margin-bottom:16px;line-height:1.04}
.db-hero h1 em{color:var(--sprout-bright);font-style:italic}
.db-hero p{color:rgba(243,238,226,.85);font-size:1.14rem;max-width:60ch;line-height:1.6;margin-bottom:24px}
.db-stats{display:flex;gap:30px;flex-wrap:wrap;margin-top:24px}
.db-stat{font-family:'Spline Sans Mono',monospace}
.db-stat b{display:block;font-family:'Fraunces',serif;font-size:1.9rem;color:var(--gold)}
.db-stat span{font-size:.78rem;letter-spacing:.06em;text-transform:uppercase;color:rgba(243,238,226,.7)}
.db-toolbar{position:sticky;top:68px;z-index:40;background:rgba(243,238,226,.96);backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:18px 0}
.db-search{position:relative;margin-bottom:14px}
.db-search input{width:100%;padding:14px 18px 14px 46px;border:1.5px solid var(--line);border-radius:4px;font-size:1rem;font-family:inherit;background:var(--paper-card);color:var(--ink)}
.db-search input:focus{outline:none;border-color:var(--sprout)}
.db-search::before{content:"🔎";position:absolute;left:16px;top:50%;transform:translateY(-50%);opacity:.5}
.db-filters{display:flex;flex-wrap:wrap;gap:8px}
.db-filter{font-family:'Spline Sans Mono',monospace;font-size:.74rem;letter-spacing:.03em;text-transform:uppercase;background:var(--paper-card);border:1.5px solid var(--line);color:var(--ink-soft);padding:7px 14px;border-radius:24px;cursor:pointer;transition:all .18s}
.db-filter:hover{border-color:var(--sprout)}
.db-filter.on{background:var(--sprout);color:#fff;border-color:var(--sprout)}
.db-cat{padding:56px 0 0}
.db-cat-head{display:flex;align-items:center;gap:12px;margin-bottom:6px}
.db-cat-head .dot{width:14px;height:14px;border-radius:50%}
.db-cat-head h2{font-size:1.8rem}
.db-cat-desc{color:var(--ink-soft);margin-bottom:26px;font-size:1.04rem}
.db-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:20px}
.db-card{background:var(--paper-card);border:1px solid var(--line);border-radius:8px;overflow:hidden;text-decoration:none;color:inherit;transition:transform .2s,box-shadow .2s;display:flex;flex-direction:column}
.db-card:hover{transform:translateY(-5px);box-shadow:6px 8px 0 var(--shadow)}
.db-card .img{position:relative}
.db-card img{width:100%;height:150px;object-fit:cover}
.db-card .shopflag{position:absolute;top:10px;right:10px;background:var(--sprout);color:#fff;font-family:'Spline Sans Mono',monospace;font-size:.62rem;letter-spacing:.05em;text-transform:uppercase;padding:4px 9px;border-radius:20px}
.db-card .b{padding:18px;flex:1;display:flex;flex-direction:column}
.db-card .b h3{font-size:1.2rem;line-height:1.2;margin-bottom:3px}
.db-card .b .l{font-family:'Fraunces',serif;font-style:italic;font-size:.88rem;color:var(--ink-faint);margin-bottom:10px}
.db-card .b p{font-size:.9rem;color:var(--ink-soft);line-height:1.5;flex:1}
.db-card .b .mt{margin-top:12px;font-size:.84rem;font-weight:600;color:var(--sprout)}
.db-noresults{text-align:center;padding:60px 20px;color:var(--ink-faint);display:none}
.db-noresults h3{font-size:1.4rem;margin-bottom:8px;color:var(--ink-soft)}
.id-banner{background:var(--paper-warm);border:1px solid var(--line);border-radius:10px;padding:30px;margin:56px 0 0;display:grid;grid-template-columns:1fr auto;gap:24px;align-items:center}
.id-banner h3{font-size:1.5rem;margin-bottom:8px}
.id-banner p{color:var(--ink-soft);max-width:60ch}
@media(max-width:760px){.id-banner{grid-template-columns:1fr}}
"""

def build_index():
    url = f"{SITE}/database/"
    item_list = {"@context":"https://schema.org","@type":"ItemList","name":"Texas Roots Plant Database",
        "description":"A free, growing database of plants: how to grow them, how to identify them, their edibility and survival uses.",
        "numberOfItems":len(PLANTS),
        "itemListElement":[{"@type":"ListItem","position":i+1,"url":f"{SITE}/database/{p['slug']}.html","name":f"{p['common']} ({p['latin']})"} for i,p in enumerate(PLANTS)]}
    web = {"@context":"https://schema.org","@type":"WebSite","name":"Texas Roots Plant Database","url":SITE,
        "publisher":{"@type":"Person","name":"Jordan Polasek","url":"https://jordanpolasek.com"}}
    page = head("The Texas Roots Plant Database — Free Growing, Identification & Survival Data",
                "A free, searchable plant database: how to grow, identify, and use hundreds of plants — vegetables, herbs, fruit, Texas natives, wild edibles, and survival crops. Compiled by Jordan Polasek in El Campo, TX.",
                url, [item_list, web], INDEX_CSS)
    page += nav("database")

    # collect all filter tags actually used, in a sensible order
    order = ["edible","survival","native-tx","drought","perennial","medicinal","wild","in-shop","pollinator","beginner"]
    used = set()
    for p in PLANTS: used.update(p["tags"])
    filters = [t for t in order if t in used]

    fbtns = "".join(f'<button class="db-filter" data-filter="{t}">{esc(tag_label(t))}</button>' for t in filters)
    page += f'''<section class="db-hero"><div class="wrap">
<div class="eyebrow">A free plant library · compiled by Jordan Polasek</div>
<h1>The Texas Roots <em>Plant Database</em></h1>
<p>How to grow it, how to spot it in the wild, whether you can eat it, and how it earns its place in a self-sufficient garden. A free, open reference we keep adding to — no paywall, no email gate, ever.</p>
<div class="db-stats">
<div class="db-stat"><b>{len(PLANTS)}</b><span>plants &amp; growing</span></div>
<div class="db-stat"><b>{len(PLANT_CATS)}</b><span>categories</span></div>
<div class="db-stat"><b>100%</b><span>free forever</span></div>
</div>
</div></section>
<div class="db-toolbar"><div class="wrap">
<div class="db-search"><input type="search" id="dbSearch" placeholder="Search the database… (tomato, drought, edible, survival, native)" aria-label="Search plants"></div>
<div class="db-filters"><button class="db-filter on" data-filter="all">All plants</button>{fbtns}</div>
</div></div>
<div class="wrap">
<div class="db-noresults" id="dbNoResults"><h3>No plants match that.</h3><p>Try a different word or clear your filters.</p></div>
'''
    for k, cat in PLANT_CATS.items():
        plants = [p for p in PLANTS if p["category"]==k]
        if not plants: continue
        cards = ""
        for p in plants:
            search = (p["common"]+" "+p["latin"]+" "+p["family"]+" "+p["summary"]+" "+" ".join(p["tags"])+" "+" ".join(tag_label(t) for t in p["tags"])).lower()
            shopflag = '<span class="shopflag">We grow it</span>' if p.get("in_shop") else ''
            cards += f'''<a href="{p['slug']}.html" class="db-card" data-search="{esc(search)}" data-tags="{esc(' '.join(p['tags']))}">
<div class="img"><img src="../assets/img/plants/{p['category']}.svg" alt="{esc(p['common'])} ({esc(p['latin'])}) — Texas Roots plant database entry, by Jordan Polasek" loading="lazy">{shopflag}</div>
<div class="b"><h3>{esc(p['common'])}</h3><div class="l">{esc(p['latin'])}</div><p>{esc(p['summary'][:120])}…</p><div class="mt">View plant →</div></div></a>'''
        page += f'''<section class="db-cat" id="{k}"><div class="db-cat-head"><span class="dot" style="background:{cat['color']}"></span><h2>{esc(cat['name'])}</h2></div>
<p class="db-cat-desc">{esc(cat['desc'])}</p>
<div class="db-grid">{cards}</div></section>'''

    page += '''<div class="id-banner">
<div><h3>Not sure what you're looking at?</h3><p>Walk through a plain-language plant identification guide — leaf shape, flowers, stems, and the safety checks that matter before you ever taste a wild plant.</p></div>
<a class="btn btn-primary" href="identify.html">Open the ID guide →</a>
</div>
</div>
<script>
const search=document.getElementById('dbSearch'),cards=document.querySelectorAll('.db-card'),noRes=document.getElementById('dbNoResults'),filters=document.querySelectorAll('.db-filter');
let activeFilter='all';
function apply(){
  const q=(search.value||'').toLowerCase().trim();let any=false;
  cards.forEach(c=>{
    const matchQ=!q||c.dataset.search.includes(q);
    const matchF=activeFilter==='all'||c.dataset.tags.split(' ').includes(activeFilter);
    const show=matchQ&&matchF;c.style.display=show?'':'none';if(show)any=true;
  });
  document.querySelectorAll('.db-cat').forEach(s=>{const vis=[...s.querySelectorAll('.db-card')].some(c=>c.style.display!=='none');s.style.display=vis?'':'none';});
  noRes.style.display=any?'none':'block';
}
search&&search.addEventListener('input',apply);
filters.forEach(b=>b.addEventListener('click',()=>{filters.forEach(x=>x.classList.remove('on'));b.classList.add('on');activeFilter=b.dataset.filter;apply();}));
</script>'''
    page += footer()
    open(os.path.join(DB, "index.html"), "w").write(page)


# ---------- PLANT IDENTIFICATION GUIDE ----------
ID_CSS = """
.idg-hero{background:var(--ink);color:var(--paper);padding:70px 0 56px;text-align:center}
.idg-hero .eyebrow{color:var(--gold);justify-content:center}
.idg-hero h1{font-size:clamp(2.1rem,4.5vw,3.3rem);margin-bottom:14px}
.idg-hero p{color:rgba(243,238,226,.84);font-size:1.1rem;max-width:58ch;margin:0 auto}
.idg-safety{background:rgba(181,85,47,.1);border:1px solid var(--clay);border-radius:8px;padding:26px 30px;margin:48px 0}
.idg-safety h2{color:var(--clay);font-size:1.4rem;margin-bottom:12px;display:flex;align-items:center;gap:10px}
.idg-safety ol{margin:0 0 0 20px;color:var(--ink-soft)}
.idg-safety li{margin-bottom:10px;padding-left:6px;line-height:1.6}
.idg-step{display:grid;grid-template-columns:64px 1fr;gap:22px;padding:30px 0;border-bottom:1px solid var(--line)}
.idg-step .n{font-family:'Fraunces',serif;font-weight:900;font-size:2.4rem;color:var(--sprout);line-height:1}
.idg-step h3{font-size:1.45rem;margin-bottom:10px}
.idg-step p{color:var(--ink-soft);margin-bottom:12px;line-height:1.7;font-size:1.05rem}
.idg-step ul{margin:0 0 0 20px;color:var(--ink-soft)}
.idg-step li{margin-bottom:7px;line-height:1.55}
.idg-cta{text-align:center;padding:56px 0}
.idg-cta h2{font-size:1.8rem;margin-bottom:12px}
.idg-cta p{color:var(--ink-soft);max-width:50ch;margin:0 auto 22px}
@media(max-width:700px){.idg-step{grid-template-columns:1fr;gap:8px}}
"""

def build_identify():
    url = f"{SITE}/database/identify.html"
    steps = [
        ("Start with the safety rule, always","Before anything else, fix this in your head: never eat a wild plant you cannot identify with total certainty. 'Probably' is not good enough — some of the most dangerous plants have safe-looking lookalikes. Identification for eating means checking every feature, not just the one that looks familiar.",
         ["Positive ID on multiple features — not one.","When in doubt, throw it out.","Cross-check against the lookalike warnings on each database entry."]),
        ("Read the leaves","Leaf shape, edges, and arrangement are the fastest narrowing tool. Note whether leaves are simple (one blade) or compound (split into leaflets), whether edges are smooth, toothed, or lobed, and how they sit on the stem — opposite each other, alternating, or all from the base in a rosette.",
         ["Simple vs compound (leaflets).","Edge: smooth, toothed, or lobed.","Arrangement: opposite, alternate, or basal rosette.","Texture and smell — crush a leaf (a mint-family square stem and scent is a classic tell)."]),
        ("Look at the flowers","Flowers are often the surest ID. Count the petals, note the color and shape, and see how they're grouped — single blooms, clusters, spikes, or flat umbels. The number of petals alone narrows huge plant families (mustards have 4, roses commonly 5, lilies in 3s or 6s).",
         ["Petal count and symmetry.","Single, clustered, spike, or umbrella-shaped grouping.","Color and any markings at the center."]),
        ("Check the stem and sap","Stems carry quiet clues. Square stems point to the mint family. Milky sap is a major flag — it separates safe purslane from toxic spurge, and appears in figs and dandelions too. Note whether the stem is woody or soft, hollow or solid, smooth or hairy.",
         ["Square vs round stem.","Milky sap vs clear (snap a stem to check — this is a key safety test).","Woody vs herbaceous; hollow vs solid."]),
        ("Note where and how it grows","Habitat and habit narrow things fast. Is it in full sun or shade, wet ground or dry gravel? Is it upright, a sprawling mat, a vine, or a shrub? A succulent mat in a sunny driveway crack behaves very differently from a woody shrub on a fence line.",
         ["Sun/shade and wet/dry.","Upright, mat, vine, or shrub.","Native habitat — roadside, woodland, disturbed ground, garden bed."]),
        ("Confirm against fruit, roots, and smell","Finish with the supporting evidence: fruit or seed type, root form (taproot, tuber, runners), and overall smell. These confirm what the leaves and flowers suggested — and for any edible, they're your last safety check before you ever taste it.",
         ["Fruit/seed type and how it attaches.","Root: taproot, tuber, bulb, or runners.","Smell of crushed leaf or root."]),
    ]
    step_html = "".join(
        f'<div class="idg-step"><div class="n">{i+1}</div><div><h3>{esc(t)}</h3><p>{esc(d)}</p><ul>{"".join(f"<li>{esc(x)}</li>" for x in pts)}</ul></div></div>'
        for i,(t,d,pts) in enumerate(steps))

    howto = {"@context":"https://schema.org","@type":"HowTo","name":"How to Identify a Plant",
        "description":"A plain-language, six-step method for identifying a plant by leaf, flower, stem, habit, and the safety checks that matter before eating any wild plant.",
        "author":{"@type":"Person","name":"Jordan Polasek","url":"https://jordanpolasek.com"},
        "step":[{"@type":"HowToStep","name":t,"text":d} for t,d,_ in steps]}

    page = head("How to Identify a Plant — A Free Step-by-Step Guide | Texas Roots Plant Database",
                "A free, plain-language plant identification guide: read leaves, flowers, stems, sap, and habit — plus the safety checks that matter before eating any wild plant. By Jordan Polasek.",
                url, [howto], ID_CSS)
    page += nav("database")
    page += f'''<section class="idg-hero"><div class="wrap"><div class="eyebrow">Free guide</div><h1>How to identify a plant</h1><p>A simple, repeatable way to work out what a plant is — by its leaves, flowers, stems, and habit — and the safety rules that matter before you ever taste a wild one.</p></div></section>
<div class="wrap">
<div class="idg-safety"><h2>⚠ The rule that comes before everything</h2>
<ol>
<li><b>Never eat a plant you can't identify with complete certainty.</b> Many toxic plants closely resemble edible ones.</li>
<li><b>Confirm on multiple features</b> — leaf, flower, stem, and habit together — not a single resemblance.</li>
<li><b>Snap a stem and check the sap.</b> Milky sap is a common toxicity flag (the purslane-vs-spurge test is the classic example).</li>
<li><b>Avoid roadsides and sprayed ground.</b> A safe plant in a contaminated spot is not safe food.</li>
<li><b>When in doubt, throw it out.</b> No wild meal is worth the risk.</li>
</ol></div>
{step_html}
<div class="idg-cta"><h2>Put it to work</h2><p>Browse the database and use the identification marks and lookalike warnings on every plant page to confirm what you're looking at.</p><a class="btn btn-primary" href="index.html">Browse the plant database →</a></div>
</div>
'''
    page += footer()
    open(os.path.join(DB, "identify.html"), "w").write(page)


if __name__ == "__main__":
    for p in PLANTS: build_plant(p)
    build_index()
    build_identify()
    print(f"Built {len(PLANTS)} plant pages + database index + ID guide")
