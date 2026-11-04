"""The BVTech Explore hub (/explore/) — our own "front page of tech" for
bvtech.org (v1.106): an impressive, Yahoo-style portal built in BVTech's brand.

What's on it:
  * A hero with greeting, live clock and the reader's local weather + forecast.
  * A live tech-markets ticker (big-tech stocks + crypto), free & keyless.
  * "The BVTech Take" — our OWN original commentary on the day's news (the daily
    Tech Dispatch), written as Jordan Polasek, with every source cited inside.
    Explore links readers to our authored takes, never to scraped article text.
  * Latest headlines by category (link OUT to the publisher), trending on HN,
    the NASA photo, upcoming rocket launches, "on this day in tech", a daily
    trivia game, BVTech Answers, our two browser games and the free tools.

Everything dynamic is pulled live by the site Worker (/tools-api/*) and rendered
client-side; the page is styled with the site's own CSS variables and all script
is inline (the site CSP allows 'self'/'unsafe-inline'). The top padding is set
from the real header height on load, so the fixed site banner can never clip the
hero again.
"""
from __future__ import annotations

TITLE = "Explore — Tech, Space, EVs, AI, Markets & Good News | BVTech"
DESC = ("Your front page for technology: live tech-market prices, the day's best "
        "tech, Tesla, space, AI and science news, our own original take on the "
        "headlines, a NASA photo, rocket launches, a daily tech game and more — "
        "curated by Jordan Polasek at BVTech. No politics, no doomscroll.")

CATS = [("tech", "💻 Tech"), ("tesla", "⚡ Tesla & EVs"), ("space", "🚀 Space"),
        ("ai", "🤖 AI"), ("science", "🔬 Science"), ("gadgets", "📱 Gadgets"),
        ("gaming", "🎮 Gaming"), ("security", "🛡️ Security"), ("good", "🌟 Good News")]

_TABS = "".join(
    f'<button class="xp-tab{" on" if i == 0 else ""}" data-cat="{c}">{label}</button>'
    for i, (c, label) in enumerate(CATS))

# warm Thanksgiving bunting — amber / rust / gold / cranberry pennants
_PAPEL_COLORS = ["#d97706", "#b45309", "#c2410c", "#a3561f", "#d4a017", "#7c2d12"]
_PAPEL = ('<div class="xp-papel" aria-hidden="true">'
          + "".join(f'<i style="background:{_PAPEL_COLORS[i % 6]}"></i>' for i in range(20))
          + "</div>")


def body() -> str:
    return r"""
<section class="xp" id="xp">
<style>
.xp{--o:#EB6F24;--o2:#F5BE58;--up:#26C485;--dn:#ff6b6b;max-width:1160px;margin:0 auto;padding:104px 18px 100px}
@media(max-width:700px){.xp{padding-top:84px}}
.xp *{box-sizing:border-box}
.xp a{text-decoration:none}
/* ---- hero ---- */
.xp-hero{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;flex-wrap:wrap;margin:0 0 20px}
.xp-hello{font-family:var(--fh);font-size:clamp(1.9rem,4.4vw,2.9rem);font-weight:800;color:var(--white);margin:0;line-height:1.05;letter-spacing:-.01em}
.xp-hello span{background:linear-gradient(90deg,var(--o),var(--o2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.xp-sub{color:var(--muted);margin:10px 0 0;font-size:1rem;line-height:1.5}
.xp-sub b{color:var(--text)}
.xp-clock{color:var(--o2);font-variant-numeric:tabular-nums;font-weight:700}
.xp-wx{display:flex;align-items:center;gap:14px;background:linear-gradient(135deg,rgba(68,64,219,.16),rgba(235,111,36,.10));border:1px solid var(--border);border-radius:16px;padding:14px 18px;min-width:230px}
.xp-wx .e{font-size:2.4rem;line-height:1}
.xp-wx .t{font-size:2.1rem;font-weight:800;color:var(--white);font-family:var(--fh);line-height:1}
.xp-wx .m{color:var(--muted);font-size:.8rem;line-height:1.4;margin-top:2px}
.xp-wx .p{color:var(--o2);font-size:.72rem;font-weight:700;margin-top:3px}
/* ---- search + section nav ---- */
.xp-bar{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin:0 0 20px}
.xp-search{display:flex;flex:1;min-width:240px;background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden}
.xp-search input{flex:1;background:transparent;border:0;outline:0;color:var(--white);font-size:.95rem;padding:12px 16px;font-family:var(--fb)}
.xp-search input::placeholder{color:var(--muted)}
.xp-search button{background:linear-gradient(135deg,var(--o),var(--o2));color:#0E0D2C;border:0;font-weight:800;padding:0 20px;cursor:pointer;font-size:.9rem}
.xp-nav{display:flex;gap:8px;flex-wrap:wrap}
.xp-nav a{color:var(--muted);font-size:.84rem;font-weight:700;padding:9px 14px;border-radius:999px;border:1px solid var(--border);transition:.15s}
.xp-nav a:hover{color:var(--white);border-color:var(--o)}
/* ---- markets ticker ---- */
.xp-mkt{display:flex;align-items:stretch;border:1px solid var(--border);border-radius:12px;overflow:hidden;background:var(--card);margin:0 0 26px}
.xp-mkt .lab{flex-shrink:0;display:flex;align-items:center;gap:7px;padding:0 16px;background:linear-gradient(135deg,var(--o),var(--o2));color:#0E0D2C;font-weight:800;font-size:.72rem;letter-spacing:.1em;white-space:nowrap}
.xp-mkt .lab .dot{width:7px;height:7px;border-radius:50%;background:#0E0D2C;animation:xp-pulse 1.6s infinite}
@keyframes xp-pulse{0%{opacity:1}50%{opacity:.25}100%{opacity:1}}
.xp-mkt .track{flex:1;overflow:hidden;position:relative;-webkit-mask-image:linear-gradient(to right,transparent,#000 3%,#000 97%,transparent);mask-image:linear-gradient(to right,transparent,#000 3%,#000 97%,transparent)}
.xp-mkt .scroll{display:inline-flex;align-items:center;gap:26px;padding:12px 20px;white-space:nowrap;animation:xp-marquee 48s linear infinite}
.xp-mkt:hover .scroll{animation-play-state:paused}
@keyframes xp-marquee{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}
.xp-q{font-size:.86rem;color:var(--text);font-variant-numeric:tabular-nums}
.xp-q b{color:var(--white);font-weight:800;margin-right:7px;font-family:var(--fh)}
.xp-q .up{color:var(--up);font-weight:700}.xp-q .dn{color:var(--dn);font-weight:700}
/* ---- featured game (VOLT RUSH — 3D multiplayer racer) ---- */
.xp-feature{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:0;border-radius:20px;overflow:hidden;
  border:1px solid rgba(80,190,255,.4);margin:0 0 14px;background:#07132a;transition:.18s}
.xp-feature:hover{transform:translateY(-2px);border-color:rgba(80,190,255,.75)}
@media(max-width:760px){.xp-feature{grid-template-columns:1fr}}
.xp-feature .art{position:relative;min-height:210px;overflow:hidden;
  background:radial-gradient(130% 120% at 50% 118%,#1b3b6b 0%,#0e2347 55%,#07132a 100%)}
.xp-feature .sky{position:absolute;inset:0;background:
  radial-gradient(2px 2px at 20% 28%,rgba(255,255,255,.75),transparent),
  radial-gradient(2px 2px at 68% 18%,rgba(255,255,255,.5),transparent),
  radial-gradient(1.5px 1.5px at 44% 12%,rgba(255,255,255,.6),transparent),
  radial-gradient(1.5px 1.5px at 85% 34%,rgba(255,255,255,.45),transparent)}
.xp-feature .road{position:absolute;left:50%;bottom:0;width:155%;height:150px;transform:translateX(-50%);
  background:linear-gradient(#24487f,#0b1c3a);clip-path:polygon(38% 0,62% 0,100% 100%,0 100%)}
.xp-feature .road::before{content:"";position:absolute;left:50%;top:0;bottom:0;width:7px;transform:translateX(-50%);
  background:repeating-linear-gradient(#ffd34d 0 16px,transparent 16px 36px)}
.xp-feature .flag{position:absolute;top:2px;left:50%;transform:translateX(-50%);width:22%;height:15px;opacity:.9;
  background:repeating-conic-gradient(#fff 0 25%,#0b1c3a 0 50%) 0 0/12px 12px}
.xp-feature .kart{position:absolute;bottom:24px;left:50%;transform:translateX(-50%);font-size:2.7rem;
  filter:drop-shadow(0 7px 10px rgba(0,0,0,.55));animation:xp-rev 2.4s ease-in-out infinite}
@keyframes xp-rev{0%,100%{transform:translateX(-50%) translateY(0)}50%{transform:translateX(-50%) translateY(-5px)}}
.xp-feature .streak{position:absolute;height:3px;border-radius:3px;opacity:.7;
  background:linear-gradient(90deg,transparent,#52beff);animation:xp-zoom 1.1s linear infinite}
.xp-feature .streak.a{top:40%;left:-40%;width:42%;animation-delay:0s}
.xp-feature .streak.b{top:55%;left:-40%;width:28%;animation-delay:.45s}
.xp-feature .streak.c{top:70%;left:-40%;width:34%;animation-delay:.85s}
@keyframes xp-zoom{0%{transform:translateX(0)}100%{transform:translateX(380%)}}
.xp-feature .txt{padding:26px 28px;display:flex;flex-direction:column;justify-content:center;background:linear-gradient(135deg,rgba(80,190,255,.12),rgba(245,190,88,.08))}
.xp-feature .kick{font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;color:#7fd0ff;font-weight:800}
.xp-feature h2{font-family:var(--fh);color:#fff;font-size:clamp(1.5rem,3vw,2rem);margin:10px 0 8px;line-height:1.1;letter-spacing:.02em}
.xp-feature p{color:var(--text);font-size:.95rem;line-height:1.6;margin:0 0 16px}
.xp-feature .play{display:inline-flex;align-items:center;gap:8px;align-self:flex-start;background:linear-gradient(135deg,#52beff,#EB6F24);
  color:#06122a;font-weight:800;font-size:1rem;padding:12px 26px;border-radius:12px}
@media(prefers-reduced-motion:reduce){.xp-feature .kart,.xp-feature .streak{animation:none}}
.xp-season{display:inline-flex;align-items:center;gap:7px;background:rgba(80,190,255,.15);border:1px solid rgba(80,190,255,.38);
  color:#7fd0ff;font-weight:800;font-size:.72rem;letter-spacing:.06em;padding:5px 12px;border-radius:999px;margin-bottom:10px}
/* previously-featured strip (old news) */
.xp-encore{display:flex;align-items:center;gap:10px 14px;flex-wrap:wrap;margin:0 0 30px;padding:11px 18px;border-radius:12px;
  border:1px dashed var(--border);background:rgba(255,255,255,.02)}
.xp-encore .lab{font-size:.66rem;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:800}
.xp-encore a{color:var(--o2);font-weight:800;font-size:.92rem}
.xp-encore .m{color:var(--muted);font-size:.84rem}
/* NASA photo of the day — top feature */
.xp-apod{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:0;border-radius:18px;overflow:hidden;
  border:1px solid rgba(68,64,219,.4);margin:0 0 26px;background:#0a0920;transition:.18s}
.xp-apod:hover{transform:translateY(-2px);border-color:rgba(120,120,255,.6)}
@media(max-width:760px){.xp-apod{grid-template-columns:1fr}}
.xp-apod .xp-apod-img{position:relative;min-height:210px;background:#05040f}
.xp-apod .xp-apod-img img{width:100%;height:100%;object-fit:cover;display:block;min-height:210px;max-height:300px}
.xp-apod .xp-apod-txt{padding:24px 26px;display:flex;flex-direction:column;justify-content:center;background:linear-gradient(135deg,rgba(68,64,219,.16),rgba(80,140,255,.08))}
.xp-apod .kick{font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;color:#8fb3ff;font-weight:800}
.xp-apod h2{font-family:var(--fh);color:#fff;font-size:clamp(1.25rem,2.6vw,1.65rem);margin:9px 0 8px;line-height:1.15}
.xp-apod p{color:var(--text);font-size:.9rem;line-height:1.55;margin:0 0 12px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.xp-apod .xp-apod-go{color:#8fb3ff;font-weight:800;font-size:.92rem}
/* papel-picado festive bunting */
.xp-papel{display:flex;gap:2px;height:26px;margin:0 0 16px;overflow:hidden;opacity:.92}
.xp-papel i{flex:1;height:24px;clip-path:polygon(0 0,100% 0,100% 64%,50% 100%,0 64%);position:relative}
.xp-papel i::after{content:"";position:absolute;inset:4px 30% 40%;background:rgba(0,0,0,.18);border-radius:50%}
.xp-greet-season{display:inline-block;margin-left:8px;font-size:1.1rem;vertical-align:middle}
/* ---- section heads ---- */
.xp-h{display:flex;align-items:center;gap:10px;margin:0 0 16px}
.xp-h h2{font-family:var(--fh);font-size:1.15rem;color:var(--white);margin:0;font-weight:800}
.xp-h .pre{width:4px;height:20px;border-radius:3px;background:linear-gradient(var(--o),var(--o2))}
.xp-h .live{margin-left:auto;display:flex;align-items:center;gap:6px;font-size:.68rem;font-weight:800;letter-spacing:.1em;color:var(--o2)}
.xp-h .live .dot{width:7px;height:7px;border-radius:50%;background:var(--up);animation:xp-pulse 1.6s infinite}
/* ---- the BVTech take ---- */
.xp-take-band{margin:0 0 30px}
.xp-take-grid{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(0,1fr);gap:20px}
@media(max-width:860px){.xp-take-grid{grid-template-columns:1fr}}
.xp-take-feat{display:block;border-radius:18px;border:1px solid rgba(245,190,88,.28);background:linear-gradient(145deg,rgba(235,111,36,.14),rgba(68,64,219,.12));padding:28px 30px;transition:.18s}
.xp-take-feat:hover{transform:translateY(-2px);border-color:rgba(245,190,88,.55)}
.xp-kick{font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;color:var(--o2);font-weight:800;display:flex;align-items:center;gap:8px}
.xp-take-feat h3{font-family:var(--fh);color:var(--white);font-size:clamp(1.3rem,2.6vw,1.75rem);line-height:1.22;margin:12px 0 10px;letter-spacing:-.01em}
.xp-take-feat p{color:var(--text);font-size:1rem;line-height:1.65;margin:0 0 16px}
.xp-take-feat .by{color:var(--muted);font-size:.82rem}.xp-take-feat .by b{color:var(--o2)}
.xp-take-feat .go{display:inline-block;margin-top:14px;color:var(--o2);font-weight:800;font-size:.95rem}
.xp-take-more{display:flex;flex-direction:column;gap:12px}
.xp-take-mini{display:block;border:1px solid var(--border);border-radius:14px;background:var(--card);padding:16px 18px;transition:.15s}
.xp-take-mini:hover{border-color:var(--o);transform:translateY(-2px)}
.xp-take-mini .d{font-size:.68rem;letter-spacing:.08em;color:var(--o2);font-weight:800;text-transform:uppercase}
.xp-take-mini h4{color:var(--white);font-family:var(--fh);font-size:1rem;line-height:1.3;margin:6px 0 5px}
.xp-take-mini p{color:var(--muted);font-size:.84rem;line-height:1.5;margin:0}
/* ---- main grid ---- */
.xp-grid{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:24px;align-items:start}
.xp-main,.xp-side{min-width:0}
@media(max-width:900px){.xp-grid{grid-template-columns:1fr}}
.xp-tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}
.xp-tab{font-family:var(--fb);font-size:.84rem;font-weight:700;padding:8px 14px;border-radius:999px;border:1px solid var(--border);background:var(--card);color:var(--text);cursor:pointer;transition:.15s}
.xp-tab:hover{border-color:var(--o)}
.xp-tab.on{background:linear-gradient(90deg,var(--o),var(--o2));color:#0E0D2C;border-color:transparent}
.xp-feat{display:block;border-radius:16px;border:1px solid var(--border);background:linear-gradient(150deg,rgba(235,111,36,.10),rgba(68,64,219,.08));padding:22px 24px;margin-bottom:12px;transition:.15s}
.xp-feat:hover{transform:translateY(-2px);border-color:rgba(245,190,88,.4)}
.xp-feat .src{font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;color:var(--o2);font-weight:800}
.xp-feat h3{color:var(--white);font-size:1.3rem;line-height:1.3;margin:8px 0 0;font-family:var(--fh)}
.xp-list{display:flex;flex-direction:column;gap:2px}
.xp-item{display:flex;gap:14px;align-items:baseline;padding:13px 14px;border-radius:11px;border:1px solid transparent;transition:.12s}
.xp-item:hover{background:var(--card);border-color:var(--border)}
.xp-item .n{color:var(--o2);font-weight:800;font-family:var(--fh);font-size:.95rem;flex:0 0 1.4em;text-align:right}
.xp-item .b{min-width:0}
.xp-item h4{color:var(--white);font-size:1rem;line-height:1.4;margin:0;font-weight:600}
.xp-item .meta{color:var(--muted);font-size:.78rem;margin-top:3px}
.xp-item:hover h4{color:var(--o2)}
/* ---- cards ---- */
.xp-card{border-radius:16px;border:1px solid var(--border);background:var(--card);padding:20px;margin-bottom:18px;transition:.15s}
.xp-card.lift:hover{transform:translateY(-2px);border-color:rgba(245,190,88,.35)}
.xp-card h3{margin:0 0 14px;color:var(--white);font-family:var(--fh);font-size:1.05rem;display:flex;align-items:center;gap:8px}
.xp-card h3 .tag{margin-left:auto;font-size:.66rem;font-weight:800;letter-spacing:.08em;color:var(--o2);border:1px solid var(--border);border-radius:999px;padding:2px 9px}
/* markets mini */
.xp-mrow{display:flex;align-items:center;gap:10px;padding:9px 0;border-top:1px solid var(--border)}
.xp-mrow:first-of-type{border-top:0}
.xp-mrow .sym{font-family:var(--fh);font-weight:800;color:var(--white);font-size:.92rem;flex:0 0 52px}
.xp-mrow .nm{color:var(--muted);font-size:.78rem;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.xp-mrow .px{color:var(--text);font-size:.88rem;font-variant-numeric:tabular-nums;text-align:right}
.xp-mrow .ch{font-size:.8rem;font-weight:700;font-variant-numeric:tabular-nums;flex:0 0 66px;text-align:right}
.xp-mrow .ch.up{color:var(--up)}.xp-mrow .ch.dn{color:var(--dn)}
/* weather forecast */
.xp-fc{display:flex;gap:8px}
.xp-fc .d{flex:1;text-align:center;background:rgba(255,255,255,.03);border:1px solid var(--border);border-radius:10px;padding:9px 4px}
.xp-fc .d .dn{font-size:.68rem;color:var(--muted);text-transform:uppercase;font-weight:700}
.xp-fc .d .ic{font-size:1.3rem;margin:3px 0}
.xp-fc .d .hl{font-size:.74rem;color:var(--text)}
.xp-fc .d .hl b{color:var(--white)}
/* photo / launches / otd */
.xp-photo img{width:100%;border-radius:12px;display:block;max-height:220px;object-fit:cover;background:var(--bg3)}
.xp-photo .cap{color:var(--muted);font-size:.8rem;margin-top:9px;line-height:1.5}
.xp-photo .cap b{color:var(--text)}
.xp-launch{display:flex;gap:12px;align-items:center;padding:10px 0;border-top:1px solid var(--border)}
.xp-launch:first-of-type{border-top:0}
.xp-launch .d{flex:0 0 52px;text-align:center}
.xp-launch .d b{display:block;font-family:var(--fh);font-size:1.3rem;color:var(--white);line-height:1}
.xp-launch .d span{font-size:.68rem;color:var(--muted);text-transform:uppercase}
.xp-launch .i h4{margin:0;color:var(--white);font-size:.9rem;line-height:1.3}
.xp-launch .i p{margin:2px 0 0;color:var(--muted);font-size:.76rem}
.xp-otd li{color:var(--text);font-size:.9rem;line-height:1.5;margin:0 0 10px;list-style:none;padding-left:52px;position:relative;min-height:1.2em}
.xp-otd li b{position:absolute;left:0;top:0;color:var(--o2);font-family:var(--fh);font-weight:800}
.xp-otd a{color:inherit}.xp-otd a:hover{color:var(--o2)}
/* trending */
.xp-tr a{display:flex;gap:10px;align-items:baseline;padding:9px 0;border-top:1px solid var(--border);color:var(--text);font-size:.86rem;line-height:1.4}
.xp-tr a:first-child{border-top:0}.xp-tr a:hover{color:var(--o2)}
.xp-tr .n{color:var(--o2);font-weight:800;font-family:var(--fh);flex:0 0 1.2em}
/* game */
.xp-game .q{color:var(--white);font-size:1.02rem;font-weight:600;line-height:1.4;margin:0 0 14px}
.xp-opt{display:block;width:100%;text-align:left;padding:11px 14px;margin:0 0 8px;border-radius:10px;border:1px solid var(--border);background:rgba(255,255,255,.02);color:var(--text);font-size:.92rem;cursor:pointer;transition:.12s;font-family:inherit}
.xp-opt:hover:not(:disabled){border-color:var(--o)}
.xp-opt.right{border-color:var(--green);background:rgba(38,196,133,.14);color:#fff}
.xp-opt.wrong{border-color:#e5484d;background:rgba(229,72,77,.14)}
.xp-opt:disabled{cursor:default}
.xp-game .meta{display:flex;gap:8px;align-items:center;margin:0 0 12px;flex-wrap:wrap}
.xp-game .cat{font-size:.72rem;color:var(--muted)}
.xp-game .diff{font-size:.66rem;font-weight:800;letter-spacing:.05em;padding:2px 8px;border-radius:999px}
.xp-game .d-Easy{background:rgba(38,196,133,.16);color:#6fe0b4}.xp-game .d-Med{background:rgba(245,190,88,.16);color:#F5BE58}.xp-game .d-Hard{background:rgba(229,72,77,.16);color:#ff8d8f}
.xp-game .streak{margin-left:auto;font-size:.76rem;color:var(--o2);font-weight:700}
.xp-why{color:var(--muted);font-size:.86rem;line-height:1.55;margin:12px 0 0;padding:12px 14px;border-radius:10px;background:rgba(68,64,219,.1);border:1px solid var(--border)}
.xp-tip{color:var(--text);font-size:.94rem;line-height:1.6}.xp-tip b{color:var(--o2)}
/* answers */
.xp-ans a.row{display:block;padding:9px 0;border-top:1px solid var(--border);color:var(--text);font-size:.88rem;line-height:1.4}
.xp-ans a.row:first-child{border-top:0}.xp-ans a.row:hover{color:var(--o2)}
.xp-ans .m{color:var(--muted);font-size:.74rem;margin-top:2px}.xp-ans .s{color:var(--green)}
/* discover + games + tools bands */
.xp-three{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin:4px 0 8px}
@media(max-width:860px){.xp-three{grid-template-columns:1fr}}
.xp-three .xp-card{margin:0;height:100%}
.xp-games{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin:30px 0 8px}
@media(max-width:860px){.xp-games{grid-template-columns:1fr}}
.xp-gcard{display:block;border-radius:18px;border:1px solid var(--border);padding:26px 28px;transition:.18s;position:relative;overflow:hidden}
.xp-gcard:hover{transform:translateY(-3px)}
.xp-gcard .k{font-size:.7rem;letter-spacing:.12em;font-weight:800;text-transform:uppercase}
.xp-gcard h3{font-family:var(--fh);color:var(--white);font-size:1.4rem;margin:8px 0 8px}
.xp-gcard p{color:var(--text);font-size:.92rem;line-height:1.55;margin:0 0 14px}
.xp-gcard .go{font-weight:800;font-size:.95rem}
.xp-tools{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:12px 0 0}
@media(max-width:860px){.xp-tools{grid-template-columns:repeat(2,1fr)}}
.xp-tool{display:flex;flex-direction:column;align-items:center;gap:7px;text-align:center;border:1px solid var(--border);border-radius:14px;background:var(--card);padding:18px 10px;transition:.15s}
.xp-tool:hover{transform:translateY(-2px);border-color:var(--o)}
.xp-tool .ic{font-size:1.7rem}
.xp-tool .nm{color:var(--white);font-size:.84rem;font-weight:700}
.xp-tool .ds{color:var(--muted);font-size:.72rem;line-height:1.3}
/* cta + misc */
.xp-cta{margin-top:36px;border-radius:20px;padding:34px 30px;background:linear-gradient(135deg,rgba(68,64,219,.22),rgba(235,111,36,.14));border:1px solid rgba(245,190,88,.3);text-align:center}
.xp-cta h2{color:var(--white);font-family:var(--fh);margin:0 0 8px;font-size:clamp(1.4rem,3vw,1.9rem)}
.xp-cta p{color:var(--text);margin:0 auto 18px;max-width:580px;line-height:1.6}
.xp-cta a{display:inline-block;margin:5px;padding:12px 22px;border-radius:10px;font-weight:800}
.xp-cta .p{background:var(--o);color:#0E0D2C}.xp-cta .s{background:transparent;color:#fff;border:1px solid rgba(255,255,255,.3)}
.xp-sk{color:var(--muted);padding:26px 4px;text-align:center;font-size:.9rem}
.xp-sk.sh{background:linear-gradient(90deg,var(--card),rgba(255,255,255,.07),var(--card));background-size:200% 100%;animation:xp-sh 1.3s infinite;border-radius:10px;height:14px;padding:0;margin:10px 0}
@keyframes xp-sh{0%{background-position:200% 0}100%{background-position:-200% 0}}
.xp-band{margin:34px 0 0}
.xp-foot{color:var(--muted);font-size:.8rem;text-align:center;margin-top:32px;line-height:1.7}
.xp-foot a{color:var(--o2)}
@media(prefers-reduced-motion:reduce){.xp-mkt .scroll{animation:none}.xp-sk.sh{animation:none}}
</style>

""" + _PAPEL + r"""
<!-- HERO -->
<div class="xp-hero">
  <div>
    <h1 class="xp-hello"><span id="xp-greet">Welcome</span> to Explore <span class="xp-greet-season">🦃🍂🥧</span></h1>
    <p class="xp-sub">The fun, useful side of tech — curated by <b>Jordan Polasek</b> at BVTech. No politics, no doomscroll. <span style="color:#d97706">Happy Thanksgiving! 🦃</span> <span class="xp-clock" id="xp-clock"></span></p>
  </div>
  <div class="xp-wx" id="xp-wx" hidden>
    <div class="e" id="xp-wx-e">🌡️</div>
    <div><div class="t" id="xp-wx-t">—</div><div class="m" id="xp-wx-m"></div><div class="p" id="xp-wx-p"></div></div>
  </div>
</div>

<!-- SEARCH + SECTION NAV -->
<div class="xp-bar">
  <form class="xp-search" id="xp-search" autocomplete="off">
    <input id="xp-search-q" type="search" placeholder="Search the web…" aria-label="Search the web">
    <button type="submit">Search</button>
  </form>
  <nav class="xp-nav">
    <a href="#xp-take">Our Take</a>
    <a href="#xp-news">News</a>
    <a href="#xp-discover">Discover</a>
    <a href="#xp-games">Games</a>
    <a href="#xp-tools">Tools</a>
  </nav>
</div>

<!-- MARKETS TICKER -->
<div class="xp-mkt" id="xp-mkt" hidden>
  <div class="lab"><span class="dot"></span>TECH MARKETS</div>
  <div class="track"><div class="scroll" id="xp-mkt-scroll"></div></div>
</div>

<!-- NASA PHOTO OF THE DAY (top feature) -->
<a class="xp-apod" id="xp-apod" target="_blank" rel="noopener" hidden>
  <div class="xp-apod-img"><img id="xp-apod-img" alt="" loading="lazy"></div>
  <div class="xp-apod-txt">
    <span class="kick">🔭 NASA · Astronomy Photo of the Day</span>
    <h2 id="xp-apod-title">Today's view of the universe</h2>
    <p id="xp-apod-desc"></p>
    <span class="xp-apod-go">See it full-size →</span>
  </div>
</a>

<!-- FEATURED GAME (VOLT RUSH — 3D multiplayer racer) -->
<a class="xp-feature" href="https://portal.bvtech.org/kart/">
  <div class="art">
    <div class="sky"></div>
    <div class="road"></div>
    <div class="flag"></div>
    <span class="streak a"></span><span class="streak b"></span><span class="streak c"></span>
    <span class="kart">🏎️</span>
  </div>
  <div class="txt">
    <span class="season">🆕 Just launched · V3</span>
    <span class="kick">🏁 Featured Game</span>
    <h2>VOLT RUSH</h2>
    <p>Our brand-new 3D multiplayer kart racer — six neon circuits, eight wild power-ups and hand-made racers, with real-time online races against your friends. Free, right in your browser, on phone or desktop.</p>
    <span class="play">▶ Race now →</span>
  </div>
</a>

<!-- PREVIOUSLY FEATURED (old news) -->
<div class="xp-encore">
  <span class="lab">🍂 Previously featured</span>
  <span class="m">Last season's hit —</span>
  <a href="/graveyard-shift/">🧛 Graveyard Shift →</a>
  <span class="m">our 3D vampire-survivors game is still in the arcade below.</span>
</div>

<!-- THE BVTECH TAKE -->
<div class="xp-take-band" id="xp-take">
  <div class="xp-h"><span class="pre"></span><h2>The BVTech Take</h2><span class="live">OUR ORIGINAL COMMENTARY</span></div>
  <div class="xp-take-grid">
    <a class="xp-take-feat" id="xp-take-feat" href="/blog/">
      <div class="xp-kick">✍️ Written by us · sources cited</div>
      <h3 id="xp-take-title">Our daily read on the tech that matters</h3>
      <p id="xp-take-ex">Every day we read across the web and write our own honest take — what caught our eye and why it matters for a small business — then link every source so you can dig in yourself. No scraping, no reposting: our words, their credit.</p>
      <div class="by">By <b>Jordan Polasek</b> · BVTech <span id="xp-take-date"></span></div>
      <span class="go">Read our full take →</span>
    </a>
    <div class="xp-take-more" id="xp-take-more"></div>
  </div>
</div>

<!-- MAIN GRID: NEWS + RAIL -->
<div class="xp-grid" id="xp-news">
  <div class="xp-main">
    <div class="xp-h"><span class="pre"></span><h2>Latest in Tech</h2><span class="live"><span class="dot"></span>LIVE</span></div>
    <div class="xp-tabs">""" + _TABS + r"""</div>
    <div id="xp-feed"><div class="xp-sk sh"></div><div class="xp-sk sh"></div><div class="xp-sk sh"></div></div>
  </div>

  <aside class="xp-side">
    <div class="xp-card lift" id="xp-mkt-card" hidden>
      <h3>📈 Markets <span class="tag" id="xp-mkt-tag">LIVE</span></h3>
      <div id="xp-mkt-list"></div>
    </div>
    <div class="xp-card lift" id="xp-fc-card" hidden>
      <h3>⛅ Your Forecast</h3>
      <div class="xp-fc" id="xp-fc"></div>
    </div>
    <div class="xp-card lift xp-game">
      <h3>🧠 Daily Byte <span class="tag" id="xp-game-tag">TODAY</span></h3>
      <div id="xp-game"><div class="xp-sk">Loading today's question…</div></div>
    </div>
    <div class="xp-card lift" id="xp-tr-card" hidden>
      <h3>🔥 Trending in Tech</h3>
      <div class="xp-tr" id="xp-tr"></div>
    </div>
    <div class="xp-card lift" id="xp-ans-card" hidden>
      <h3>💬 BVTech Answers <span class="tag">COMMUNITY</span></h3>
      <div class="xp-ans" id="xp-ans"></div>
      <a href="https://portal.bvtech.org/answers" style="display:inline-block;margin-top:12px;color:var(--o2);font-weight:700;font-size:.9rem">Ask the community →</a>
    </div>
    <div class="xp-card lift">
      <h3>💡 Tip of the Day</h3>
      <div class="xp-tip" id="xp-tip">Stay tuned…</div>
    </div>
  </aside>
</div>

<!-- DISCOVER: photo / launches / on this day -->
<div class="xp-band" id="xp-discover">
  <div class="xp-h"><span class="pre"></span><h2>Discover</h2></div>
  <div class="xp-three">
    <div class="xp-card lift" id="xp-launch-card" hidden>
      <h3>🚀 Next Rocket Launches</h3>
      <div id="xp-launches"></div>
    </div>
    <div class="xp-card lift" id="xp-otd-card" hidden>
      <h3>📅 On This Day in Tech</h3>
      <ul class="xp-otd" id="xp-otd" style="margin:0;padding:0"></ul>
    </div>
  </div>
</div>

<!-- GAMES -->
<div class="xp-band" id="xp-games">
  <div class="xp-h"><span class="pre"></span><h2>Play — Free, in your browser</h2></div>
  <div class="xp-games">
    <a class="xp-gcard" href="https://portal.bvtech.org/kart/" style="background:linear-gradient(135deg,rgba(80,190,255,.16),rgba(245,190,88,.10));border-color:rgba(80,190,255,.45)">
      <div class="k" style="color:#7fd0ff">🏁 NEW · 3D MULTIPLAYER RACER</div>
      <h3>VOLT RUSH</h3>
      <p>Race friends in real time across six neon tracks with eight wild power-ups and hand-made 3D racers. Phone or desktop, free in your browser.</p>
      <span class="go" style="color:#7fd0ff">▶ Race now →</span>
    </a>
    <a class="xp-gcard" href="https://portal.bvtech.org/arena/" style="background:linear-gradient(135deg,rgba(57,192,255,.16),rgba(245,190,88,.10));border-color:rgba(57,192,255,.4)">
      <div class="k" style="color:#39c0ff">⚔️ ORIGINAL · RUST + WEBASSEMBLY</div>
      <h3>Breach Protocol</h3>
      <p>Our own 3D survivors game — hold the grid against waves of breaches, level up and pick powerful upgrades. Runs right in your browser.</p>
      <span class="go" style="color:#39c0ff">▶ Play Breach Protocol →</span>
    </a>
    <a class="xp-gcard" href="/graveyard-shift/" style="background:linear-gradient(135deg,rgba(130,40,160,.18),rgba(40,30,70,.2));border-color:rgba(160,110,200,.45)">
      <div class="k" style="color:#c89bff">🍂 SEASONAL ENCORE · VAMPIRE SURVIVORS</div>
      <h3>Graveyard Shift</h3>
      <p>Last season's featured game lives on — survive the night in our 3D bullet-heaven: swarms of undead, soul-shard level-ups and tech-flavored blessings, boss after boss till dawn.</p>
      <span class="go" style="color:#c89bff">▶ Start the night shift →</span>
    </a>
  </div>
</div>

<!-- FREE TOOLS -->
<div class="xp-band" id="xp-tools">
  <div class="xp-h"><span class="pre"></span><h2>Free BVTech Tools</h2></div>
  <div class="xp-tools">
    <a class="xp-tool" href="/tools/whats-my-ip/"><span class="ic">🌐</span><span class="nm">What's My IP</span><span class="ds">IP &amp; network info</span></a>
    <a class="xp-tool" href="/tools/speed-test/"><span class="ic">⚡</span><span class="nm">Speed Test</span><span class="ds">Check your line</span></a>
    <a class="xp-tool" href="/tools/is-it-down/"><span class="ic">📡</span><span class="nm">Is It Down?</span><span class="ds">Site status</span></a>
    <a class="xp-tool" href="/tools/ev-savings/"><span class="ic">🔋</span><span class="nm">EV Savings</span><span class="ds">Gas vs. electric</span></a>
    <a class="xp-tool" href="/tools/"><span class="ic">🧰</span><span class="nm">All Tools</span><span class="ds">The full kit</span></a>
  </div>
</div>

<!-- CTA -->
<div class="xp-cta">
  <h2>Liked poking around? Learn the real thing — free.</h2>
  <p>The BVTech Academy turns this curiosity into skills: hands-on labs, our live-style Lightning Labs on cloud and AI security, and certificates. Built in Texas by Jordan Polasek.</p>
  <a class="p" href="/academy/lightning-labs/">⚡ Try a Lightning Lab</a>
  <a class="s" href="/academy/">🎓 Academy Home</a>
  <a class="s" href="https://portal.bvtech.org/answers">💬 BVTech Answers</a>
  <a class="s" href="/tools/">🧰 Free Tools</a>
</div>
<p class="xp-foot"><b>Our take, not a reprint.</b> "The BVTech Take" is original commentary written by Jordan Polasek at BVTech — we read the day's news, write our own analysis, and link every source so you can read the original yourself. We never republish other outlets' articles; the headlines here link straight out to the publisher that reported them.<br><br><b>Sources &amp; data:</b> tech headlines and "Trending" come from publishers' own feeds and Hacker News (each links to its source) · market quotes are delayed and for information only, not advice · space imagery is NASA's Astronomy Picture of the Day (APOD) · rocket launches from The Space Devs Launch Library · "On this day in tech" from public historical records · weather from Open-Meteo. Refreshed through the day. <a href="/blog/">Read all our takes →</a></p>
</section>

<script>
(function(){
  var API="/tools-api/";
  function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e;}
  function ago(ts){if(!ts)return"";var s=(Date.now()-ts)/1000;if(s<3600)return Math.max(1,Math.round(s/60))+"m ago";if(s<86400)return Math.round(s/3600)+"h ago";return Math.round(s/86400)+"d ago";}
  function get(u){return fetch(API+u).then(function(r){return r.json();});}
  function money(n){n=+n;if(!isFinite(n))return"";return n>=1000?n.toLocaleString(undefined,{maximumFractionDigits:0}):n.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});}

  // bulletproof header clearance: set top padding from the REAL fixed-header height
  (function(){
    try{
      var hdr=document.querySelector("header,.header");var xp=document.getElementById("xp");
      if(hdr&&xp){var set=function(){var h=hdr.offsetHeight||72;xp.style.paddingTop=(h+30)+"px";};
        set();window.addEventListener("resize",set);setTimeout(set,400);}
    }catch(e){}
  })();

  // greeting + clock
  var h=new Date().getHours();
  document.getElementById("xp-greet").textContent=h<12?"Good morning":h<18?"Good afternoon":"Good evening";
  var ck=document.getElementById("xp-clock");
  function tick(){try{ck.textContent="· "+new Date().toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});}catch(e){}}
  tick();setInterval(tick,30000);

  // web search
  var sf=document.getElementById("xp-search");
  if(sf)sf.addEventListener("submit",function(e){e.preventDefault();
    var q=document.getElementById("xp-search-q").value.trim();if(!q)return;
    window.open("https://duckduckgo.com/?q="+encodeURIComponent(q),"_blank","noopener");});

  // ---- markets (ticker + rail card) ----
  function chSpan(ch){var s=el("span",(ch>=0?"up":"dn"));s.textContent=(ch>=0?"▲ ":"▼ ")+Math.abs(ch).toFixed(2)+"%";return s;}
  get("explore/markets").then(function(d){
    var items=(d&&d.items)||[];if(!items.length)return;
    var sc=document.getElementById("xp-mkt-scroll");
    function fill(){items.forEach(function(q){
      var w=el("span","xp-q");var b=el("b",null,q.sym);w.appendChild(b);
      w.appendChild(document.createTextNode("$"+money(q.price)+" "));
      w.appendChild(chSpan(q.chg));sc.appendChild(w);
    });}
    fill();fill();
    document.getElementById("xp-mkt").hidden=false;
    // rail card: top 7
    var box=document.getElementById("xp-mkt-list");
    items.slice(0,7).forEach(function(q){
      var r=el("div","xp-mrow");
      r.appendChild(el("div","sym",q.sym));
      r.appendChild(el("div","nm",q.name));
      r.appendChild(el("div","px","$"+money(q.price)));
      var c=el("div","ch "+(q.chg>=0?"up":"dn"),(q.chg>=0?"+":"")+q.chg.toFixed(2)+"%");
      r.appendChild(c);box.appendChild(r);
    });
    document.getElementById("xp-mkt-card").hidden=false;
  }).catch(function(){});

  // ---- the BVTech take ----
  get("explore/takes").then(function(d){
    var items=(d&&d.items)||[];if(!items.length)return;
    var f=items[0];
    var fa=document.getElementById("xp-take-feat");fa.href=f.href;
    document.getElementById("xp-take-title").textContent=f.title;
    if(f.excerpt)document.getElementById("xp-take-ex").textContent=f.excerpt;
    if(f.date)document.getElementById("xp-take-date").textContent="· "+f.date;
    var more=document.getElementById("xp-take-more");
    items.slice(1,4).forEach(function(t){
      var a=el("a","xp-take-mini");a.href=t.href;
      if(t.date)a.appendChild(el("div","d",t.date));
      a.appendChild(el("h4",null,t.title));
      if(t.excerpt)a.appendChild(el("p",null,t.excerpt));
      more.appendChild(a);
    });
  }).catch(function(){});

  // ---- headlines ----
  var feed=document.getElementById("xp-feed"),cur="tech",loaded={};
  function renderFeed(cat,data){
    if(cur!==cat)return;feed.textContent="";
    var items=(data&&data.items)||[];
    if(!items.length){feed.appendChild(el("div","xp-sk","No headlines right now — check back soon."));return;}
    var f=items[0];
    var fa=el("a","xp-feat");fa.href=f.link;fa.target="_blank";fa.rel="noopener";
    fa.appendChild(el("div","src",f.source+(f.t?" · "+ago(f.t):"")));
    fa.appendChild(el("h3",null,f.title));feed.appendChild(fa);
    var list=el("div","xp-list");
    items.slice(1).forEach(function(it,i){
      var a=el("a","xp-item");a.href=it.link;a.target="_blank";a.rel="noopener";
      a.appendChild(el("div","n",String(i+2)));
      var b=el("div","b");b.appendChild(el("h4",null,it.title));
      b.appendChild(el("div","meta",it.source+(it.t?" · "+ago(it.t):"")));
      a.appendChild(b);list.appendChild(a);
    });
    feed.appendChild(list);
  }
  function load(cat){cur=cat;
    if(loaded[cat]){renderFeed(cat,loaded[cat]);return;}
    feed.innerHTML='<div class="xp-sk sh"></div><div class="xp-sk sh"></div><div class="xp-sk sh"></div>';
    get("feeds?cat="+cat).then(function(d){loaded[cat]=d;renderFeed(cat,d);})
      .catch(function(){if(cur===cat)feed.innerHTML='<div class="xp-sk">Could not load headlines. Try another tab.</div>';});
  }
  Array.prototype.forEach.call(document.querySelectorAll(".xp-tab"),function(t){
    t.addEventListener("click",function(){
      document.querySelector(".xp-tab.on").classList.remove("on");
      t.classList.add("on");load(t.dataset.cat);});
  });
  load("tech");

  // ---- trending (Hacker News) ----
  get("feeds?cat=hn").then(function(d){
    var items=(d&&d.items)||[];if(!items.length)return;
    var box=document.getElementById("xp-tr");
    items.slice(0,6).forEach(function(it,i){
      var a=el("a");a.href=it.link;a.target="_blank";a.rel="noopener";
      a.appendChild(el("span","n",String(i+1)));
      a.appendChild(el("span",null,it.title));box.appendChild(a);
    });
    document.getElementById("xp-tr-card").hidden=false;
  }).catch(function(){});

  // ---- weather (hero + forecast card) ----
  function wx(lat,lon){
    get("explore/weather"+(lat?"?lat="+lat+"&lon="+lon:"")).then(function(d){
      if(!d||!d.now||d.now.temp==null)return;
      document.getElementById("xp-wx-e").textContent=d.now.sky[1];
      document.getElementById("xp-wx-t").textContent=d.now.temp+"°";
      document.getElementById("xp-wx-m").innerHTML=d.now.sky[0]+"<br>feels "+d.now.feels+"° · "+(d.days[0]?("H "+d.days[0].hi+"° L "+d.days[0].lo+"°"):"");
      if(d.place)document.getElementById("xp-wx-p").textContent="📍 "+d.place;
      document.getElementById("xp-wx").hidden=false;
      var fc=document.getElementById("xp-fc");
      if(fc&&d.days&&d.days.length){fc.textContent="";
        d.days.slice(0,4).forEach(function(day,i){
          var dd=el("div","d");
          var nm=i===0?"Today":new Date(day.day+"T12:00").toLocaleDateString([],{weekday:"short"});
          dd.appendChild(el("div","dn",nm));
          dd.appendChild(el("div","ic",day.sky[1]));
          var hl=el("div","hl");hl.innerHTML="<b>"+day.hi+"°</b> "+day.lo+"°";
          dd.appendChild(hl);fc.appendChild(dd);
        });
        document.getElementById("xp-fc-card").hidden=false;
      }
    }).catch(function(){});
  }
  wx();
  if(navigator.geolocation){try{navigator.geolocation.getCurrentPosition(
    function(p){wx(p.coords.latitude.toFixed(2),p.coords.longitude.toFixed(2));},
    function(){},{timeout:6000,maximumAge:3600000});}catch(e){}}

  // ---- daily game + tip ----
  function streakGet(){try{return JSON.parse(localStorage.getItem("bvByte")||"{}");}catch(e){return {};}}
  function streakSet(v){try{localStorage.setItem("bvByte",JSON.stringify(v));}catch(e){}}
  get("daily").then(function(d){
    var box=document.getElementById("xp-game");box.textContent="";
    document.getElementById("xp-tip").innerHTML="<b>Did you know?</b> "+(d.tip||"");
    var tag=document.getElementById("xp-game-tag");if(tag&&d.index)tag.textContent="#"+d.index;
    if(!d||!d.question){box.appendChild(el("div","xp-sk","Game unavailable."));return;}
    var st=streakGet();
    var meta=el("div","meta");meta.appendChild(el("span","cat",d.category||""));
    if(d.difficulty)meta.appendChild(el("span","diff d-"+d.difficulty,d.difficulty));
    var streakEl=el("span","streak",(st.streak>0?("🔥 "+st.streak+" day streak"):""));
    meta.appendChild(streakEl);box.appendChild(meta);
    box.appendChild(el("p","q",d.question.q));
    var answered=d.done===d.date,btns=[];
    (d.question.options||[]).forEach(function(opt,i){
      var b=el("button","xp-opt",opt);btns.push(b);
      b.addEventListener("click",function(){
        if(answered)return;answered=true;
        fetch(API+"daily/grade",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({choice:i})})
          .then(function(r){return r.json();}).then(function(res){
            btns.forEach(function(x){x.disabled=true;});
            if(res.correct){b.classList.add("right");}
            else{b.classList.add("wrong");if(btns[res.answer])btns[res.answer].classList.add("right");}
            var s2=streakGet();
            if(s2.done!==d.date){
              if(res.correct){s2.streak=(s2.last===d.date-1?(s2.streak||0)+1:1);}else{s2.streak=0;}
              s2.done=d.date;s2.last=d.date;streakSet(s2);
              streakEl.textContent=s2.streak>0?("🔥 "+s2.streak+" day streak"):"";
            }
            box.appendChild(el("div","xp-why",(res.correct?"✅ Nailed it. ":"💡 ")+(res.why||"")));
            var more=el("p","xp-tip");more.style.marginTop="10px";more.style.fontSize=".82rem";
            more.innerHTML='New question every day · <a href="/academy/" style="color:var(--o2)">Play the full Academy →</a>';
            box.appendChild(more);
          }).catch(function(){answered=false;});
      });
      box.appendChild(b);
    });
  }).catch(function(){document.getElementById("xp-game").innerHTML='<div class="xp-sk">Game unavailable.</div>';});

  // ---- NASA photo of the day (top feature) ----
  get("explore/photos").then(function(d){
    var it=(d&&d.items||[])[0];if(!it)return;
    var img=document.getElementById("xp-apod-img");if(img){img.src=it.img;img.alt=it.title||"";}
    var t=document.getElementById("xp-apod-title");if(t&&it.title)t.textContent=it.title;
    var ds=document.getElementById("xp-apod-desc");if(ds)ds.textContent=it.desc||"";
    var a=document.getElementById("xp-apod");if(a){a.href=it.link||it.img;a.hidden=false;}
  }).catch(function(){});

  // ---- launches ----
  get("explore/launches").then(function(d){
    var items=(d&&d.items)||[];if(!items.length)return;
    var box=document.getElementById("xp-launches");
    items.forEach(function(l){
      var dt=new Date(l.net);var row=el("div","xp-launch");
      var dd=el("div","d");dd.appendChild(el("b",null,String(dt.getDate())));
      dd.appendChild(el("span",null,dt.toLocaleString([],{month:"short"})));row.appendChild(dd);
      var i=el("div","i");i.appendChild(el("h4",null,l.name));
      i.appendChild(el("p",null,(l.provider||"")+" · "+dt.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"})));
      row.appendChild(i);box.appendChild(row);
    });
    document.getElementById("xp-launch-card").hidden=false;
  }).catch(function(){});

  // ---- on this day ----
  get("explore/onthisday").then(function(d){
    var items=(d&&d.items)||[];if(!items.length)return;
    var ul=document.getElementById("xp-otd");
    items.forEach(function(e){
      var li=el("li");li.appendChild(el("b",null,String(e.year)));
      if(e.link){var a=el("a",null,e.text);a.href=e.link;a.target="_blank";a.rel="noopener";li.appendChild(a);}
      else li.appendChild(document.createTextNode(e.text));ul.appendChild(li);
    });
    document.getElementById("xp-otd-card").hidden=false;
  }).catch(function(){});

  // ---- answers ----
  get("answers").then(function(d){
    var items=(d&&d.items)||[];if(!items.length)return;
    var box=document.getElementById("xp-ans");
    items.slice(0,5).forEach(function(q){
      var a=el("a","row");a.href=q.url;a.target="_blank";a.rel="noopener";
      a.appendChild(el("div",null,(q.solved?"✓ ":"")+q.cat+" "+q.title));
      a.appendChild(el("div","m"+(q.solved?" s":""),q.answers+" answer"+(q.answers===1?"":"s")+" · "+q.score+" votes"));
      box.appendChild(a);
    });
    document.getElementById("xp-ans-card").hidden=false;
  }).catch(function(){});
})();
</script>
"""
