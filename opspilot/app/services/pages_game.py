"""BVTech: Graveyard Shift — the game's own home page at bvtech.org/graveyard-shift/.

A Halloween-styled, SEO-rich landing page for our original vampire-survivors
game. It describes the game (written as BVTech / Jordan Polasek), shows how to
play, the blessings and the bestiary, and launches the game (which runs as a
Rust->WebAssembly bundle at portal.bvtech.org/signal/). Built into the site
chrome by destination.publish(); styled with the site's own CSS variables.
"""
from __future__ import annotations

PLAY = "https://portal.bvtech.org/signal/"

TITLE = "Graveyard Shift — a free Halloween vampire-survivors game | BVTech"
DESC = ("Graveyard Shift is BVTech's own free 3D vampire-survivors game: survive the "
        "night against swarms of the undead, collect soul shards, pick powerful "
        "blessings and outlast boss after boss. Built in Rust + WebAssembly by Jordan "
        "Polasek — plays right in your browser, no install.")

BLESSINGS = [
    ("🗡️", "Silver Bolt", "Your trusty auto-attack — upgrade it into a wall of silver."),
    ("🧄", "Garlic Firewall", "A burning aura that melts anything that gets close."),
    ("🏮", "Holy Lantern", "Orbiting lights that grind down the horde around you."),
    ("💥", "Rune Nova", "A periodic holy shockwave that clears the screen."),
    ("🎯", "Stake Volley", "Fire a spread of three stakes at once."),
    ("✨", "Wisp Daemon", "A familiar wisp that hunts the undead on its own."),
    ("➕", "Patch Tuesday", "Slow, steady regeneration — the night is long."),
    ("🛡️", "Blessed Plating", "More max health and a quick top-up when you need it."),
]
BESTIARY = [
    ("🦇", "Bats", "Fast and fragile — they come in clouds."),
    ("💀", "Skeletons", "Steady shamblers that pile up fast."),
    ("🧟", "Ghouls", "Tanky bruisers that soak your bolts."),
    ("👻", "Wraiths", "Weaving spectres that are hard to pin down."),
    ("🧛", "Night Lords", "Towering bosses on a timer — Count Null-Pointer and friends."),
]


def _cards(items):
    return "".join(
        f'<div class="gs-card"><div class="gs-ic">{ic}</div>'
        f'<div><h4>{name}</h4><p>{desc}</p></div></div>'
        for ic, name, desc in items)


def body() -> str:
    return r"""
<section class="gs">
<style>
.gs{--o:#EB6F24;--o2:#F5BE58;--pp:#9f7bff;max-width:1060px;margin:0 auto;padding:110px 18px 90px}
@media(max-width:700px){.gs{padding-top:88px}}
.gs *{box-sizing:border-box}
.gs a{text-decoration:none}
.gs-badge{display:inline-flex;align-items:center;gap:8px;background:linear-gradient(135deg,rgba(159,123,255,.2),rgba(235,111,36,.16));border:1px solid rgba(159,123,255,.4);color:#c89bff;font-weight:800;font-size:.76rem;letter-spacing:.08em;padding:7px 14px;border-radius:999px;text-transform:uppercase}
.gs-hero{text-align:center;margin:10px 0 0}
.gs-hero h1{font-family:var(--fh);font-size:clamp(2.2rem,6vw,3.6rem);font-weight:800;margin:18px 0 10px;line-height:1.02;letter-spacing:-.02em;
  background:linear-gradient(90deg,#9f7bff,#8be08f);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.gs-hero .tag{color:var(--text);font-size:clamp(1.05rem,2.4vw,1.35rem);margin:0 auto 6px;max-width:640px;line-height:1.5}
.gs-hero .sub{color:var(--muted);font-size:.95rem;margin:10px 0 0}
/* launch panel */
.gs-stage{position:relative;margin:28px 0 10px;border-radius:22px;overflow:hidden;border:1px solid rgba(159,123,255,.35);
  background:radial-gradient(130% 120% at 50% 0%,#1b1340 0%,#0c0a22 60%,#070612 100%);min-height:300px;
  display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:48px 20px}
.gs-moon{position:absolute;top:26px;right:40px;width:74px;height:74px;border-radius:50%;
  background:radial-gradient(circle at 38% 38%,#fdfbe6,#d9d7b0);box-shadow:0 0 50px 12px rgba(245,240,200,.25)}
.gs-bat{position:absolute;font-size:1.4rem;opacity:.8;animation:gs-fly 7s ease-in-out infinite}
.gs-bat.b1{top:30%;left:12%;animation-delay:0s}.gs-bat.b2{top:55%;left:26%;animation-delay:1.4s;font-size:1.1rem}
.gs-bat.b3{top:22%;left:72%;animation-delay:.7s}.gs-bat.b4{top:64%;left:82%;animation-delay:2.1s;font-size:1rem}
@keyframes gs-fly{0%{transform:translate(0,0)}25%{transform:translate(16px,-12px)}50%{transform:translate(-10px,8px)}75%{transform:translate(12px,10px)}100%{transform:translate(0,0)}}
.gs-stage h2{position:relative;font-family:var(--fh);color:#fff;font-size:1.5rem;margin:0 0 6px}
.gs-stage p{position:relative;color:var(--muted);margin:0 0 22px;max-width:440px}
.gs-play{position:relative;display:inline-flex;align-items:center;gap:10px;background:linear-gradient(135deg,#9f7bff,#EB6F24);color:#0E0D2C;
  font-family:var(--fh);font-weight:800;font-size:1.25rem;padding:16px 40px;border-radius:14px;box-shadow:0 10px 30px rgba(159,123,255,.3);transition:.16s}
.gs-play:hover{transform:translateY(-2px);box-shadow:0 14px 38px rgba(159,123,255,.45)}
.gs-mini{position:relative;color:var(--muted);font-size:.82rem;margin-top:16px}
/* sections */
.gs-h{font-family:var(--fh);color:#fff;font-size:1.3rem;margin:40px 0 16px;display:flex;align-items:center;gap:10px}
.gs-h::before{content:"";width:4px;height:22px;border-radius:3px;background:linear-gradient(var(--pp),var(--o))}
.gs-steps{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
@media(max-width:760px){.gs-steps{grid-template-columns:1fr 1fr}}
.gs-step{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:18px 16px}
.gs-step .n{font-family:var(--fh);font-weight:800;color:var(--o2);font-size:1.2rem}
.gs-step h4{color:#fff;margin:8px 0 6px;font-size:1rem}
.gs-step p{color:var(--muted);font-size:.86rem;line-height:1.5;margin:0}
.gs-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:760px){.gs-grid{grid-template-columns:1fr}}
.gs-card{display:flex;gap:14px;align-items:flex-start;background:var(--card);border:1px solid var(--border);border-radius:14px;padding:16px 18px;transition:.14s}
.gs-card:hover{border-color:rgba(159,123,255,.4);transform:translateY(-2px)}
.gs-ic{font-size:1.8rem;line-height:1}
.gs-card h4{color:#fff;margin:0 0 4px;font-size:1rem}
.gs-card p{color:var(--muted);margin:0;font-size:.86rem;line-height:1.5}
.gs-foot{margin-top:44px;text-align:center;border-radius:18px;padding:34px 24px;border:1px solid rgba(245,190,88,.3);
  background:linear-gradient(135deg,rgba(159,123,255,.18),rgba(235,111,36,.14))}
.gs-foot h3{font-family:var(--fh);color:#fff;margin:0 0 14px;font-size:clamp(1.3rem,3vw,1.7rem)}
.gs-foot a{display:inline-block;margin:5px;padding:12px 22px;border-radius:10px;font-weight:800}
.gs-foot .p{background:var(--o);color:#0E0D2C}.gs-foot .s{background:transparent;color:#fff;border:1px solid rgba(255,255,255,.3)}
.gs-note{color:var(--muted);font-size:.8rem;text-align:center;margin-top:22px;line-height:1.6}
</style>

<div class="gs-hero">
  <span class="gs-badge">🎃 Halloween at BVTech · Free to play</span>
  <h1>Graveyard Shift</h1>
  <p class="tag">Survive the night. The dead don't clock out. Our own 3D vampire-survivors game — swarms of undead, soul-shard level-ups, and boss after boss until dawn.</p>
  <p class="sub">An original BVTech game by <strong style="color:var(--text)">Jordan Polasek</strong> · Rust + WebAssembly · plays right in your browser</p>
</div>

<div class="gs-stage">
  <div class="gs-moon"></div>
  <span class="gs-bat b1">🦇</span><span class="gs-bat b2">🦇</span><span class="gs-bat b3">🦇</span><span class="gs-bat b4">🦇</span>
  <h2>🧛 Enter the graveyard</h2>
  <p>Move with WASD, arrows, or drag on your phone — you attack automatically. How long can you last?</p>
  <a class="gs-play" href="__PLAY__">▶ Play Now</a>
  <div class="gs-mini">Free · no install · works on desktop &amp; mobile</div>
</div>

<h3 class="gs-h">🕯️ How to play</h3>
<div class="gs-steps">
  <div class="gs-step"><div class="n">1</div><h4>Move &amp; dodge</h4><p>WASD / arrows / drag. You fire on your own — focus on not getting cornered.</p></div>
  <div class="gs-step"><div class="n">2</div><h4>Gather souls</h4><p>Fallen undead drop soul shards. Scoop them up to fill your level bar.</p></div>
  <div class="gs-step"><div class="n">3</div><h4>Pick a blessing</h4><p>Each level, choose one of three upgrades. Stack them into a build.</p></div>
  <div class="gs-step"><div class="n">4</div><h4>Outlast the night</h4><p>Bosses arrive on a timer and it only gets harder. Survive until dawn.</p></div>
</div>

<h3 class="gs-h">⚔️ Blessings &amp; weapons</h3>
<div class="gs-grid">""" + _cards(BLESSINGS) + r"""</div>

<h3 class="gs-h">🪦 The bestiary</h3>
<div class="gs-grid">""" + _cards(BESTIARY) + r"""</div>

<div class="gs-foot">
  <h3>Ready for your shift? 🎃</h3>
  <a class="p" href="__PLAY__">▶ Play Graveyard Shift</a>
  <a class="s" href="https://portal.bvtech.org/arena/">⚔️ Try Breach Protocol</a>
  <a class="s" href="/explore/">🧭 More on Explore</a>
</div>
<p class="gs-note">Graveyard Shift is an original BVTech game — all art, characters and code are our own. Built in Texas by Jordan Polasek. Happy Halloween! 🦇</p>
</section>
""".replace("__PLAY__", PLAY)
