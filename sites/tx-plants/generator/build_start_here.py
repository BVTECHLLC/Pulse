#!/usr/bin/env python3
"""Texas Roots — "Start Here" pillar page (v6).

A single, comprehensive beginner's guide that ties the whole site together:
database, almanac, weather, propagation, NOMAD. Written by Jordan. This is the
evergreen anchor page a finished site needs — the one you'd send a brand-new
grower to first. Root-level: /start-here.html
"""
import os, html, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://tx-plants.com"
def esc(s): return html.escape(str(s), quote=True)

FONTS = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;0,9..144,900;1,9..144,400;1,9..144,500&family=Spline+Sans:wght@400;500;600;700&family=Spline+Sans+Mono:wght@400;500&display=swap" rel="stylesheet">'
FAVICON = '''<link rel="icon" href="favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="assets/favicon/favicon-32.png">
<link rel="icon" type="image/png" sizes="16x16" href="assets/favicon/favicon-16.png">
<link rel="apple-touch-icon" href="assets/favicon/apple-touch-icon.png">
<link rel="manifest" href="site.webmanifest">
<meta name="theme-color" content="#1B2B22">'''

def nav():
    return '''<header class="nav"><div class="wrap nav-inner">
  <a href="index.html" class="brand"><svg viewBox="0 0 40 40" fill="none"><path d="M20 36V16" stroke="#5C8A3A" stroke-width="2.4" stroke-linecap="round"/><path d="M20 22C20 14 12 10 6 11c-1 7 5 14 14 11Z" fill="#5C8A3A" fill-opacity="0.85"/><path d="M20 18C20 11 27 7 33 9c1 6-4 12-13 9Z" fill="#1B2B22"/><circle cx="20" cy="36" r="2.4" fill="#C99A3B"/></svg><span class="name">Texas <b>Roots</b></span></a>
  <nav class="nav-links" id="navLinks"><a href="database/index.html">Plant Database</a><a href="almanac/index.html">Almanac</a><a href="blog/index.html">Blog</a><a href="weather.html">Weather</a><a href="shop.html">Shop</a><a href="community/index.html">Community</a><a href="nomad.html">Go Offline</a><a href="order.html" class="nav-cta">Order Now</a></nav>
  <button class="burger" id="burger" aria-label="Menu"><span></span><span></span><span></span></button>
</div></header>'''

def footer():
    return '''<footer><div class="wrap">
  <div class="foot-grid">
    <div class="foot-brand"><a href="index.html" class="brand"><svg viewBox="0 0 40 40" fill="none"><path d="M20 36V16" stroke="#7CB342" stroke-width="2.4" stroke-linecap="round"/><path d="M20 22C20 14 12 10 6 11c-1 7 5 14 14 11Z" fill="#7CB342" fill-opacity="0.85"/><path d="M20 18C20 11 27 7 33 9c1 6-4 12-13 9Z" fill="#EAE2CF"/><circle cx="20" cy="36" r="2.4" fill="#C99A3B"/></svg><span class="name" style="color:#F3EEE2">Texas <b style="color:#7CB342">Roots</b></span></a><p>Heirloom seeds &amp; rooted cuttings, grown and mailed by hand from El Campo, Texas. A free knowledge base for growers everywhere. Founded &amp; built by Jordan Polasek.</p></div>
    <div class="foot-col"><h4>Explore</h4><a href="database/index.html">Plant database</a><a href="almanac/index.html">All articles</a><a href="weather.html">Garden weather</a><a href="database/identify.html">Identify a plant</a></div>
    <div class="foot-col"><h4>Texas Roots</h4><a href="shop.html">Shop</a><a href="community/index.html">Community garden</a><a href="stand.html">The stand</a><a href="about.html">Our story</a></div>
    <div class="foot-col"><h4>More</h4><a href="faq.html">FAQ</a><a href="nomad.html">Go offline</a><a href="vault.html">Knowledge Vault</a><a href="https://jordanpolasek.com">JordanPolasek.com</a><a href="https://bvtech.org">BVTech.org</a><a href="https://autumnpolasek.com">In Remembrance of Autumn 🐾</a></div>
  </div>
  <div class="foot-scripture" style="text-align:center;color:rgba(243,238,226,.55);font-style:italic;padding:0 0 18px;font-size:.9rem">&ldquo;So neither he who plants nor he who waters is anything, but only God, who gives the growth.&rdquo; &mdash; 1 Corinthians 3:7</div><div class="foot-bottom"><span>© <span id="yr"></span> Texas Roots · El Campo, TX · tx-plants.com</span><span>Written &amp; built by <a href="https://jordanpolasek.com">Jordan Polasek</a></span></div>
</div></footer>
<script>document.getElementById('yr').textContent=new Date().getFullYear();const burger=document.getElementById('burger'),navLinks=document.getElementById('navLinks');burger.addEventListener('click',()=>navLinks.classList.toggle('open'));navLinks.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>navLinks.classList.remove('open')));const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target)}}),{threshold:.12});document.querySelectorAll('.reveal').forEach(el=>io.observe(el));</script>
</body></html>'''

CSS = """
.sh-hero{background:linear-gradient(135deg,#10211a,#1B2B22);color:var(--paper);padding:90px 0 76px;position:relative;overflow:hidden}
.sh-hero::after{content:"";position:absolute;inset:0;background:url(assets/img/tunnel-golden.jpg) center/cover;opacity:.12}
.sh-hero .wrap{position:relative;z-index:2;max-width:64ch}
.sh-hero .eyebrow{color:var(--gold)}
.sh-hero h1{font-size:clamp(2.4rem,5.4vw,4rem);line-height:1.04;margin-bottom:18px}
.sh-hero h1 em{font-style:italic;color:var(--sprout-bright);font-weight:500}
.sh-hero p{color:rgba(243,238,226,.86);font-size:1.2rem;line-height:1.62;max-width:60ch}
.sh-toc{background:var(--paper-warm);border-bottom:1px solid var(--line);position:sticky;top:68px;z-index:40}
.sh-toc .wrap{display:flex;gap:8px;flex-wrap:wrap;padding:14px 28px}
.sh-toc a{font-family:'Spline Sans Mono',monospace;font-size:.76rem;letter-spacing:.02em;text-transform:uppercase;color:var(--ink-soft);text-decoration:none;padding:7px 13px;border:1px solid var(--line);border-radius:24px;transition:all .18s}
.sh-toc a:hover{background:var(--ink);color:var(--paper);border-color:var(--ink)}
.sh-body{padding:64px 0 40px;max-width:none}
.sh-step{display:grid;grid-template-columns:80px 1fr;gap:30px;padding:46px 0;border-bottom:1px solid var(--line);align-items:start}
.sh-step:last-child{border-bottom:0}
.sh-step .num{font-family:'Fraunces',serif;font-weight:900;font-size:3.2rem;color:var(--sprout);line-height:.9}
.sh-step h2{font-size:clamp(1.6rem,3vw,2.2rem);margin-bottom:14px;line-height:1.1}
.sh-step p{font-size:1.1rem;color:var(--ink-soft);line-height:1.76;margin-bottom:16px}
.sh-step p strong{color:var(--ink)}
.sh-step a.inline{color:var(--sprout);font-weight:600;text-decoration:none;border-bottom:1px solid var(--line)}
.sh-step a.inline:hover{border-color:var(--sprout)}
.sh-step ul{margin:0 0 16px 22px;color:var(--ink-soft);font-size:1.06rem;line-height:1.7}
.sh-step li{margin-bottom:8px}
.sh-pills{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0 6px}
.sh-pills a{background:var(--paper-card);border:1px solid var(--line);border-radius:6px;padding:10px 16px;text-decoration:none;color:var(--ink);font-weight:600;font-size:.95rem;transition:all .18s}
.sh-pills a:hover{border-color:var(--sprout);transform:translateY(-2px)}
.sh-tip{background:rgba(201,154,59,.13);border:1px solid rgba(201,154,59,.4);border-radius:6px;padding:18px 22px;margin:18px 0;color:var(--ink-soft)}
.sh-tip b{color:var(--gold);display:block;font-family:'Spline Sans Mono',monospace;font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;margin-bottom:6px}
.sh-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin:20px 0}
.sh-card{background:var(--paper-card);border:1px solid var(--line);border-radius:8px;padding:22px;text-decoration:none;color:inherit;transition:transform .2s,box-shadow .2s;display:block}
.sh-card:hover{transform:translateY(-4px);box-shadow:5px 7px 0 var(--shadow)}
.sh-card .k{font-family:'Spline Sans Mono',monospace;font-size:.68rem;letter-spacing:.06em;text-transform:uppercase;color:var(--clay);margin-bottom:8px}
.sh-card h3{font-size:1.2rem;margin-bottom:6px;line-height:1.2}
.sh-card p{font-size:.92rem;color:var(--ink-soft);margin:0;line-height:1.5}
.sh-final{background:var(--ink);color:var(--paper);padding:70px 0;text-align:center;margin-top:30px}
.sh-final h2{font-size:clamp(1.8rem,3.4vw,2.6rem);margin-bottom:14px}
.sh-final p{color:rgba(243,238,226,.84);max-width:54ch;margin:0 auto 26px;font-size:1.1rem;line-height:1.6}
.sh-final .btns{display:flex;gap:14px;justify-content:center;flex-wrap:wrap}
.sh-final .btn-light{background:var(--sprout-bright);color:#10211a}
.sh-final .btn-ghost{color:var(--paper);border-color:rgba(243,238,226,.5)}
@media(max-width:760px){.sh-step{grid-template-columns:1fr;gap:10px}.sh-step .num{font-size:2.4rem}.sh-toc{position:static}}
"""

STEPS = [
    ("Know your Texas climate", "climate", [
        ("p", "Before you plant a single seed, understand the ground you're standing on. Most of Texas sits in <strong>USDA hardiness zones 8a–9b</strong>, which sounds gentle — and our winters mostly are. The real challenge here is the opposite of what northern gardeners fight: <strong>summer heat</strong>. A wall of 95°F-plus days from June through September shuts plants down as hard as any freeze does up north."),
        ("p", "That single fact flips the whole calendar. Our best growing seasons are <strong>spring and fall</strong>, our winters are mild enough to grow cool-season crops straight through, and high summer is when we lean on a short list of heat-lovers and let the rest of the garden coast."),
        ("pills", [("Read: Extending the Texas season", "almanac/extending-the-texas-growing-season.html"),
                   ("Read: What grows best in Texas", "almanac/what-grows-best-in-texas.html"),
                   ("Live garden weather", "weather.html")]),
    ]),
    ("Start with your soil", "soil", [
        ("p", "Every good garden is really a soil project wearing a plant costume. You can do everything else right and fail in bad dirt — or do everything else clumsily and still win in good dirt. So start here. <strong>Get to know your soil before you fight it.</strong>"),
        ("p", "You don't need a lab to begin. Squeeze a damp handful: does it crumble (loam, ideal), stay in a sticky ribbon (clay, common around here), or fall apart (sand)? Most Texas soil leans clay and alkaline, which a lot of plants handle fine once you add organic matter. Compost is the universal fix — it loosens clay, holds sand together, and feeds the soil life that feeds your plants."),
        ("tip", "The cheapest soil upgrade there is: stop throwing away kitchen scraps and leaves. A simple compost pile turns waste into the best amendment money can't buy."),
        ("pills", [("Read: How to test your soil", "almanac/how-to-test-your-soil.html"),
                   ("Read: Best pots for growing", "almanac/best-pots-for-growing.html")]),
    ]),
    ("Pick the right plants to begin", "plants", [
        ("p", "New growers fail most often by planting the wrong thing at the wrong time. The fix is to start with <strong>forgiving, season-appropriate crops</strong> and build confidence. Our free plant database has growing data, identification, edibility, and a full propagation guide for hundreds of plants — but here's a shortlist to start."),
        ("cards", [
            ("Easiest first crops", "Cherry tomatoes, bush beans, okra, radishes, lettuce, basil — fast, forgiving, and productive.", "database/index.html"),
            ("Tough Texas natives", "Plants that already know how to live here — drought-proof and pollinator-friendly.", "database/index.html#native"),
            ("Survival calories", "Storable energy crops — sweet potato, corn, beans, squash, sunchoke — for serious food security.", "database/index.html#survival"),
            ("Browse all 278 plants", "The full free database: how to grow, identify, propagate, and use each one.", "database/index.html"),
        ]),
    ]),
    ("Learn to make more for free", "propagate", [
        ("p", "This is the skill that changes everything. Once you can <strong>propagate</strong> — take a cutting, save a seed, divide a clump — plants stop costing money and start multiplying themselves. One rosemary becomes a hedge. One tomato's seed becomes next year's crop. A sprouting grocery-store garlic becomes a lifetime supply."),
        ("p", "Every plant page in the database tells you exactly how that species wants to be multiplied. And these guides walk through the techniques themselves:"),
        ("pills", [("Take cuttings that root", "almanac/how-to-take-plant-cuttings.html"),
                   ("Save seeds forever", "almanac/how-to-save-seeds.html"),
                   ("Propagation by plant type", "almanac/propagation-by-plant-type.html"),
                   ("Grow from the grocery store", "almanac/growing-from-grocery-store.html")]),
    ]),
    ("Time it with the weather", "timing", [
        ("p", "Timing is half the battle in Texas, and it's the half beginners skip. Plant a tender start the week before a late frost and it dies; set out transplants right before a heat spike and they cook. <strong>Watch the forecast and plant into the windows.</strong>"),
        ("p", "Our free <a class='inline' href='weather.html'>garden weather tool</a> pulls live conditions and a 7-day outlook for any U.S. location, then flags the frost nights, heat spikes, and calm planting windows that actually matter for growing — not just generic weather."),
        ("pills", [("Open the weather tool", "weather.html"),
                   ("Read: Reading the weather for your garden", "almanac/reading-the-weather-for-your-garden.html")]),
    ]),
    ("Grow toward self-sufficiency", "selfsufficiency", [
        ("p", "Once the basics click, the door opens to something bigger: growing real food security. A survival garden, saved seed, captured rainwater, preserved harvests, and the knowledge to do it all without depending on anyone's supply chain. That's the heart of Texas Roots."),
        ("p", "The almanac goes deep on all of it — acre plans, rainwater, food preservation, raising chickens, building soil. And because knowledge itself is part of resilience, I keep a copy of my whole reference library <a class='inline' href='nomad.html'>offline at home</a>, so it works even when the internet doesn't. Save the seed, and save the manual."),
        ("pills", [("Grow a survival garden", "almanac/how-to-grow-a-survival-garden.html"),
                   ("Capture rainwater", "almanac/how-to-capture-rainwater.html"),
                   ("Preserve your harvest", "almanac/food-preservation-basics.html"),
                   ("Keep knowledge offline", "nomad.html")]),
    ]),
]

def render_block(b):
    t = b[0]
    if t == "p": return f"<p>{b[1]}</p>"
    if t == "tip": return f'<div class="sh-tip"><b>Jordan&rsquo;s tip</b>{b[1]}</div>'
    if t == "pills":
        return '<div class="sh-pills">' + "".join(f'<a href="{esc(h)}">{esc(l)} &rarr;</a>' for l,h in b[1]) + '</div>'
    if t == "cards":
        return '<div class="sh-cards">' + "".join(
            f'<a class="sh-card" href="{esc(h)}"><div class="k">Browse</div><h3>{esc(title)}</h3><p>{esc(desc)}</p></a>'
            for title,desc,h in b[1]) + '</div>'
    return ""

def build_start_here():
    url = f"{SITE}/start-here.html"
    howto = {"@context":"https://schema.org","@type":"HowTo",
        "name":"How to Start Growing Food in Texas — A Complete Beginner's Guide",
        "description":"A step-by-step beginner's guide to growing food in Texas: climate, soil, plant choice, propagation, timing, and self-sufficiency. By Jordan Polasek.",
        "author":{"@type":"Person","name":"Jordan Polasek","url":"https://jordanpolasek.com"},
        "step":[{"@type":"HowToStep","name":title,"text":" ".join(
            b[1] if isinstance(b[1],str) else "" for b in blocks if b[0]=="p")[:300] or title}
            for (title,anchor,blocks) in STEPS]}
    crumb = {"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[
        {"@type":"ListItem","position":1,"name":"Texas Roots","item":f"{SITE}/"},
        {"@type":"ListItem","position":2,"name":"Start Here","item":url}]}
    schema_html = "".join(f'<script type="application/ld+json">{json.dumps(s)}</script>\n' for s in (howto,crumb))

    toc = "".join(f'<a href="#{anchor}">{esc(title)}</a>' for title,anchor,_ in STEPS)
    steps_html = ""
    for i,(title,anchor,blocks) in enumerate(STEPS):
        body = "".join(render_block(b) for b in blocks)
        steps_html += f'<div class="sh-step" id="{anchor}"><div class="num">{i+1}</div><div><h2>{esc(title)}</h2>{body}</div></div>'

    page = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Start Here — How to Grow Food in Texas (Complete Beginner's Guide) | Texas Roots</title>
<meta name="description" content="New to gardening in Texas? Start here. A complete, free beginner's guide to growing food on the Gulf Coast: climate, soil, what to plant, how to propagate, timing with the weather, and the path to self-sufficiency. By Jordan Polasek.">
<meta name="author" content="Jordan Polasek">
<link rel="canonical" href="{url}">
<meta property="og:title" content="Start Here — How to Grow Food in Texas">
<meta property="og:description" content="A complete, free beginner's guide to growing food on the Texas Gulf Coast — climate, soil, plants, propagation, timing, and self-sufficiency.">
<meta property="og:type" content="article"><meta property="og:url" content="{url}">
<meta property="og:image" content="{SITE}/assets/img/tunnel-golden.jpg">
{FAVICON}
{FONTS}
<link rel="stylesheet" href="assets/styles.css">
<style>{CSS}</style>
{schema_html}</head>
<body>'''
    page += nav()
    page += f'''<section class="sh-hero"><div class="wrap">
<div class="eyebrow">Start here · written by Jordan Polasek</div>
<h1>How to grow food in Texas, <em>from scratch</em></h1>
<p>If you've never grown a thing, start right here. This is the path I'd walk a brand-new grower down — six steps from bare dirt to a garden that feeds you, with everything free to read and links to dig deeper at every stop.</p>
</div></section>
<div class="sh-toc"><div class="wrap">{toc}</div></div>
<div class="wrap"><div class="sh-body">{steps_html}</div></div>
<section class="sh-final"><div class="wrap">
<h2>That's the whole path. Now plant something.</h2>
<p>Everything here is free and always will be. When you're ready for seeds or rooted cuttings grown in living soil and mailed from the El Campo greenhouse, I'd be glad to grow some for you.</p>
<div class="btns">
<a class="btn btn-light" href="database/index.html">Browse the plant database →</a>
<a class="btn btn-ghost" href="shop.html">Shop seeds &amp; cuttings →</a>
</div>
</div></section>
'''
    page += footer()
    open(os.path.join(ROOT, "start-here.html"), "w").write(page)
    print("Built start-here.html")

if __name__ == "__main__":
    build_start_here()
