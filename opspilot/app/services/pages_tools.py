"""New free tool pages for bvtech.org/tools/ (v1.102): What's My IP, Internet
Speed Test, Is It Down, and the EV Savings Calculator. Each is a self-contained
interactive page (scoped CSS, inline JS allowed by the site CSP) published into
the site chrome by services/destination.py. The IP / speed / down tools talk to
the same-origin Worker (/tools-api/net/*); the EV calculator is pure client-side.
"""
from __future__ import annotations

# Each tool: slug, title, desc, card_title, card_excerpt, body()
_HEAD = (".tl{--o:#EB6F24;--o2:#F5BE58;max-width:820px;margin:0 auto;padding:48px 18px 80px}"
         ".tl .eye{font-size:.76rem;letter-spacing:.14em;text-transform:uppercase;color:var(--o2);font-weight:800}"
         ".tl h1{font-family:var(--fh);font-size:clamp(1.8rem,4.5vw,2.6rem);color:var(--white);line-height:1.12;margin:.3em 0 .4em}"
         ".tl .lead{color:var(--text);font-size:1.05rem;line-height:1.7;margin:0 0 26px}"
         ".tl label{display:block;color:var(--text);font-size:.9rem;font-weight:600;margin:0 0 6px}"
         ".tl input,.tl select{width:100%;padding:13px 15px;border-radius:10px;border:1px solid var(--border);"
         "background:rgba(255,255,255,.04);color:var(--white);font-size:1rem;font-family:inherit}"
         ".tl .btn{padding:14px 26px;border-radius:10px;border:0;background:var(--o);color:#0E0D2C;font-weight:800;"
         "font-size:1rem;cursor:pointer;font-family:inherit}.tl .btn[disabled]{opacity:.55;cursor:wait}"
         ".tl .muted{color:var(--muted);font-size:.86rem;line-height:1.6}"
         ".tl .card{border-radius:14px;border:1px solid var(--border);background:var(--card);padding:22px 24px;margin:18px 0}"
         ".tl a{color:var(--o2)}")


def _wrap(eye, h1, lead, inner):
    return ('<section class="tl"><style>' + _HEAD + '</style>'
            '<div class="eye">' + eye + '</div><h1>' + h1 + '</h1>'
            '<p class="lead">' + lead + '</p>' + inner + '</section>')


# ---------------------------------------------------------------- What's My IP
def whats_my_ip():
    body = _wrap(
        "🌐 Free privacy tool", "What's My IP Address?",
        "This is what any website can see about you the moment you visit — pulled live "
        "from your connection, stored nowhere. A good reminder of why a VPN and good "
        "privacy habits matter.",
        r"""
<div class="card" id="ip-card"><div class="muted">Reading your connection…</div></div>
<div class="card"><strong style="color:var(--white)">Want to be harder to track?</strong>
<p class="muted" style="margin:8px 0 0">A VPN hides your IP and city from the sites you visit.
Our team sets up business-grade VPNs and privacy hardening for Texas companies —
<a href="/free-review/">ask us how</a>.</p></div>
<style>
.ip-big{font-family:var(--fh);font-size:clamp(1.6rem,5vw,2.4rem);color:var(--o2);font-weight:800;line-height:1;word-break:break-all}
.ip-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-top:18px}
.ip-grid div span{display:block;color:var(--muted);font-size:.74rem;text-transform:uppercase;letter-spacing:.06em}
.ip-grid div b{color:var(--white);font-size:.98rem;font-weight:600}
</style>
<script>
(function(){
  fetch("/tools-api/net/whoami").then(function(r){return r.json();}).then(function(d){
    var c=document.getElementById("ip-card");
    function row(label,val){return val?('<div><span>'+label+'</span><b>'+String(val).replace(/</g,"&lt;")+'</b></div>'):"";}
    c.innerHTML='<div class="ip-big">'+(d.ip||"unknown")+'</div><div class="ip-grid">'
      +row("Location",[d.city,d.region,d.country].filter(Boolean).join(", "))
      +row("Internet provider",d.isp)+row("Network",d.asn)
      +row("Device",d.device)+row("Operating system",d.os)+row("Browser",d.browser)
      +row("Timezone",d.timezone)+row("Connection",d.http+(d.tls?(" · "+d.tls):""))
      +row("Language",d.lang)+row("Do Not Track",d.dnt?"On":"Off")+'</div>';
  }).catch(function(){document.getElementById("ip-card").innerHTML='<div class="muted">Could not read your connection. Please refresh.</div>';});
})();
</script>""")
    return dict(slug="whats-my-ip", title="What's My IP Address? | Free Privacy Tool | BVTech",
                desc="See your public IP, location, ISP, device and browser — everything a "
                     "website can tell about you. Free, instant, nothing stored. By BVTech.",
                card_title="What's My IP Address?", icon="🌐",
                card_excerpt="See exactly what any website can tell about you — your IP, city, "
                             "ISP and device. Free, instant, nothing stored.",
                body=body)


# ---------------------------------------------------------------- Speed Test
def speed_test():
    body = _wrap(
        "⚡ Free network tool", "Internet Speed Test",
        "Measure your real download and upload speed and ping, straight from your browser "
        "to Cloudflare's global network. Nothing to install.",
        r"""
<div style="text-align:center">
  <div class="sp-dial"><div class="sp-num" id="sp-num">—</div><div class="sp-unit">Mbps</div><div class="sp-lbl" id="sp-lbl">tap start</div></div>
  <button class="btn" id="sp-go" style="margin-top:8px">▶ Start speed test</button>
</div>
<div class="sp-stats" id="sp-stats" hidden>
  <div><span>Download</span><b id="sp-down">—</b> Mbps</div>
  <div><span>Upload</span><b id="sp-up">—</b> Mbps</div>
  <div><span>Ping</span><b id="sp-ping">—</b> ms</div>
</div>
<p class="muted" style="margin-top:18px">Results depend on your Wi-Fi, device and current traffic.
Slow? <a href="/free-review/">We help Texas businesses fix slow, flaky internet</a> for good.</p>
<style>
.sp-dial{width:200px;height:200px;margin:0 auto 10px;border-radius:50%;border:8px solid var(--border);
  display:flex;flex-direction:column;align-items:center;justify-content:center;background:radial-gradient(circle,rgba(235,111,36,.08),transparent)}
.sp-num{font-family:var(--fh);font-size:2.8rem;font-weight:800;color:var(--o2);line-height:1}
.sp-unit{color:var(--muted);font-size:.8rem;letter-spacing:.1em;text-transform:uppercase}
.sp-lbl{color:var(--text);font-size:.85rem;margin-top:6px;min-height:1.2em}
.sp-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:24px;text-align:center}
.sp-stats div{border:1px solid var(--border);border-radius:12px;padding:16px 8px;background:var(--card)}
.sp-stats span{display:block;color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px}
.sp-stats b{font-family:var(--fh);font-size:1.6rem;color:var(--white)}
</style>
<script>
(function(){
  var API="/tools-api/net/speedtest";
  var go=document.getElementById("sp-go"),num=document.getElementById("sp-num"),
      lbl=document.getElementById("sp-lbl"),stats=document.getElementById("sp-stats");
  function set(v,l){num.textContent=v;lbl.textContent=l;}
  async function ping(){
    var best=9999;
    for(var i=0;i<5;i++){var t=performance.now();
      try{await fetch(API+"?bytes=0&r="+Math.random(),{cache:"no-store"});}catch(e){}
      best=Math.min(best,performance.now()-t);}
    return Math.round(best);
  }
  async function download(){
    var sizes=[1,3,8],total=0,time=0;
    for(var i=0;i<sizes.length;i++){
      var bytes=sizes[i]*1024*1024,t=performance.now();
      var r=await fetch(API+"?bytes="+bytes+"&r="+Math.random(),{cache:"no-store"});
      var rd=r.body.getReader(),got=0;
      for(;;){var x=await rd.read();if(x.done)break;got+=x.value.length;
        var mbps=(got*8/1e6)/((performance.now()-t)/1000);set(mbps.toFixed(1),"testing download…");}
      total+=got;time+=(performance.now()-t)/1000;
    }
    return (total*8/1e6)/time;
  }
  async function upload(){
    var payload=new Uint8Array(4*1024*1024),total=0,time=0;
    for(var i=0;i<3;i++){var t=performance.now();
      await fetch(API,{method:"POST",body:payload,cache:"no-store"});
      total+=payload.length;time+=(performance.now()-t)/1000;
      var mbps=(payload.length*8/1e6)/((performance.now()-t)/1000);set(mbps.toFixed(1),"testing upload…");}
    return (total*8/1e6)/time;
  }
  go.addEventListener("click",async function(){
    go.disabled=true;stats.hidden=true;set("…","measuring ping…");
    try{
      var p=await ping();document.getElementById("sp-ping").textContent=p;
      var d=await download();document.getElementById("sp-down").textContent=d.toFixed(1);
      set(d.toFixed(1),"now testing upload…");
      var u=await upload();document.getElementById("sp-up").textContent=u.toFixed(1);
      set(d.toFixed(1),"download speed");stats.hidden=false;
    }catch(e){set("—","test failed — try again");}
    go.disabled=false;go.textContent="▶ Run it again";
  });
})();
</script>""")
    return dict(slug="speed-test", title="Internet Speed Test | Free | BVTech",
                desc="Test your internet download, upload and ping speed from your browser — "
                     "free, nothing to install, powered by Cloudflare's network. By BVTech.",
                card_title="Internet Speed Test", icon="⚡",
                card_excerpt="Measure your real download, upload and ping speed right in your "
                             "browser. Free, instant, nothing to install.",
                body=body)


# ---------------------------------------------------------------- Is It Down
def is_it_down():
    body = _wrap(
        "🔌 Free network tool", "Is It Down? Website Checker",
        "Can't reach a website? Check whether it's down for everyone or just you. We load it "
        "once from Cloudflare's global network and report back.",
        r"""
<form id="dn-form" autocomplete="off" style="display:flex;gap:10px;flex-wrap:wrap">
  <input id="dn-host" type="text" inputmode="url" placeholder="example.com" aria-label="Website" required style="flex:1 1 240px">
  <button class="btn" id="dn-go" type="submit">Check it</button>
</form>
<div id="dn-out"></div>
<p class="muted" style="margin-top:16px">Checked from Cloudflare's network, not your location —
so if a site works here but not for you, it's likely your Wi-Fi, DNS or ISP. <a href="/tools/whats-my-ip/">Check your connection →</a></p>
<style>
.dn-card{border-radius:14px;border:1px solid var(--border);background:var(--card);padding:22px 24px;margin:18px 0}
.dn-badge{display:inline-block;padding:5px 14px;border-radius:999px;font-weight:800;font-size:.85rem}
.dn-up{background:rgba(38,196,133,.16);color:#6fe0b4}.dn-down{background:rgba(229,72,77,.16);color:#ff8d8f}
.dn-card h3{color:var(--white);margin:12px 0 6px;font-family:var(--fh)}
.dn-card p{color:var(--text);margin:0;line-height:1.6;font-size:.92rem}
.dn-card .n{color:var(--muted);font-size:.84rem;margin-top:10px}
</style>
<script>
(function(){
  var f=document.getElementById("dn-form"),out=document.getElementById("dn-out"),
      inp=document.getElementById("dn-host"),go=document.getElementById("dn-go");
  f.addEventListener("submit",function(ev){
    ev.preventDefault();var host=inp.value.trim().replace(/^https?:\/\//i,"").split("/")[0];
    if(!host)return;go.disabled=true;out.innerHTML='<div class="dn-card"><p>Checking '+host.replace(/</g,"")+'…</p></div>';
    fetch("/tools-api/net/isdown?host="+encodeURIComponent(host)).then(function(r){return r.json();}).then(function(d){
      if(d.error){out.innerHTML='<div class="dn-card"><p>'+d.error+'</p></div>';return;}
      var up=d.up;
      out.innerHTML='<div class="dn-card"><span class="dn-badge '+(up?"dn-up":"dn-down")+'">'
        +(up?"✅ IT'S UP":"⚠️ LOOKS DOWN")+'</span><h3>'+d.host+'</h3><p>'+d.verdict
        +(d.ms?(" · responded in "+d.ms+" ms"):"")+(d.server?(" · "+d.server):"")+'</p>'
        +(d.redirect?'<p class="n">Redirects to: '+String(d.redirect).replace(/</g,"&lt;").slice(0,120)+'</p>':"")
        +'<p class="n">'+d.note+'</p></div>';
    }).catch(function(){out.innerHTML='<div class="dn-card"><p>Could not run the check. Try again in a minute.</p></div>';})
    .finally(function(){go.disabled=false;});
  });
})();
</script>""")
    return dict(slug="is-it-down", title="Is It Down? Free Website Status Checker | BVTech",
                desc="Is a website down for everyone or just you? Check any site's status live "
                     "from Cloudflare's global network. Free and instant, by BVTech.",
                card_title="Is It Down? Website Checker", icon="🔌",
                card_excerpt="Down for everyone, or just you? Check any website's status live "
                             "from Cloudflare's global network. Free.",
                body=body)


# ---------------------------------------------------------------- EV Savings
def ev_savings():
    body = _wrap(
        "⚡ Free fun calculator", "EV Savings Calculator",
        "Thinking about an electric car — a Tesla, a Rivian, anything? See roughly what you'd "
        "save on fuel each year versus a gas car. Slide the numbers to match your life.",
        r"""
<div class="ev-grid">
  <div><label>Miles you drive per year</label><input id="ev-miles" type="number" value="12000" min="0"></div>
  <div><label>Gas price ($/gallon)</label><input id="ev-gas" type="number" value="3.00" step="0.01" min="0"></div>
  <div><label>Your gas car's MPG</label><input id="ev-mpg" type="number" value="25" min="1"></div>
  <div><label>Electricity price ($/kWh)</label><input id="ev-rate" type="number" value="0.14" step="0.01" min="0"></div>
  <div><label>EV efficiency (miles/kWh)</label><input id="ev-eff" type="number" value="3.5" step="0.1" min="0.1"></div>
</div>
<div class="ev-out" id="ev-out"></div>
<p class="muted" style="margin-top:14px">A rough estimate for fuel only (not insurance, maintenance or
purchase price) — but EVs usually win on those too. BVTech runs on American-made values and honest numbers.</p>
<style>
.ev-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:16px}
.ev-out{margin-top:26px;border-radius:16px;border:1px solid rgba(245,190,88,.3);
  background:linear-gradient(135deg,rgba(38,196,133,.12),rgba(68,64,219,.1));padding:26px;text-align:center}
.ev-save{font-family:var(--fh);font-size:clamp(2rem,7vw,3.2rem);font-weight:800;color:var(--green,#26C485);line-height:1}
.ev-sub{color:var(--text);margin:8px 0 0}
.ev-row{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:20px}
.ev-row div{background:rgba(255,255,255,.04);border-radius:10px;padding:12px 8px}
.ev-row span{display:block;color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.05em}
.ev-row b{color:var(--white);font-size:1.15rem;font-family:var(--fh)}
</style>
<script>
(function(){
  var ids=["ev-miles","ev-gas","ev-mpg","ev-rate","ev-eff"],out=document.getElementById("ev-out");
  function n(id){return Math.max(0,parseFloat(document.getElementById(id).value)||0);}
  function money(v){return "$"+v.toLocaleString(undefined,{maximumFractionDigits:0});}
  function calc(){
    var miles=n("ev-miles"),gas=n("ev-gas"),mpg=n("ev-mpg")||1,rate=n("ev-rate"),eff=n("ev-eff")||1;
    var gasCost=(miles/mpg)*gas, evCost=(miles/eff)*rate, save=gasCost-evCost;
    var gallons=miles/mpg, co2=gallons*19.6/2204.6; // metric tons CO2 (19.6 lb/gal)
    out.innerHTML='<div class="ev-save">'+money(save)+'</div>'
      +'<div class="ev-sub">estimated fuel savings per year with an EV</div>'
      +'<div class="ev-row"><div><span>Gas car fuel</span><b>'+money(gasCost)+'/yr</b></div>'
      +'<div><span>EV charging</span><b>'+money(evCost)+'/yr</b></div>'
      +'<div><span>5-year savings</span><b>'+money(save*5)+'</b></div></div>'
      +'<div class="ev-sub" style="margin-top:16px">That\'s about <b style="color:var(--o2)">'
      +co2.toFixed(1)+' metric tons</b> of CO₂ you\'d skip every year — '
      +Math.round(co2*16.5)+' tree-seedlings grown for a decade.</div>';
  }
  ids.forEach(function(id){document.getElementById(id).addEventListener("input",calc);});
  calc();
})();
</script>""")
    return dict(slug="ev-savings-calculator", title="EV Savings Calculator | Gas vs Electric | BVTech",
                desc="How much would an electric car (Tesla, Rivian and more) save you on fuel "
                     "each year versus gas? Free, instant calculator by BVTech.",
                card_title="EV Savings Calculator", icon="🔋",
                card_excerpt="Thinking Tesla? See what you'd save on fuel each year going electric "
                             "vs gas. Slide the numbers to match your life.",
                body=body)


# --------------------------------------------------------- Password Strength
def password_strength():
    body = _wrap(
        "🔒 Free privacy tool", "Password Strength Checker",
        "See how strong a password really is — its estimated entropy and how long it would take "
        "an attacker to crack it. It's checked <b>entirely in your browser</b> and never sent "
        "anywhere, so it's safe to test your real passwords.",
        r"""
<div class="card">
  <label for="pw">Password to test</label>
  <div style="position:relative">
    <input id="pw" type="password" autocomplete="off" spellcheck="false" placeholder="Type or paste a password">
    <button id="pw-eye" type="button" style="position:absolute;right:8px;top:8px;background:transparent;border:0;color:var(--o2);font-size:1.1rem;cursor:pointer">👁</button>
  </div>
  <div class="pw-meter"><div id="pw-bar"></div></div>
  <div id="pw-verdict" class="pw-verdict">Enter a password to begin.</div>
  <div class="pw-grid" id="pw-stats"></div>
  <ul id="pw-tips" class="pw-tips"></ul>
</div>
<div class="card"><strong style="color:var(--white)">Running a business?</strong>
<p class="muted" style="margin:8px 0 0">Weak and reused passwords are the #1 way companies get breached. We roll out password managers, MFA and dark-web monitoring for Texas teams — <a href="/free-review/">let's lock it down</a>.</p></div>
<style>
.pw-meter{height:12px;border-radius:7px;background:rgba(255,255,255,.08);overflow:hidden;margin:16px 0 10px}
#pw-bar{height:100%;width:0;border-radius:7px;transition:.25s}
.pw-verdict{font-weight:800;font-size:1.05rem;margin-bottom:2px}
.pw-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:14px 0 0}
.pw-grid div{background:rgba(255,255,255,.03);border:1px solid var(--border);border-radius:10px;padding:10px 12px}
.pw-grid span{display:block;color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.06em}
.pw-grid b{color:var(--white);font-size:1rem}
.pw-tips{margin:14px 0 0;padding-left:18px;color:var(--text);font-size:.9rem;line-height:1.6}
</style>
<script>
(function(){
  var pw=document.getElementById("pw"),bar=document.getElementById("pw-bar"),ver=document.getElementById("pw-verdict"),
      stats=document.getElementById("pw-stats"),tips=document.getElementById("pw-tips");
  document.getElementById("pw-eye").onclick=function(){pw.type=pw.type==="password"?"text":"password";};
  var COMMON=["password","123456","12345678","qwerty","111111","letmein","admin","welcome","iloveyou","monkey","dragon","abc123","000000","password1","football","baseball","superman","trustno1","sunshine","princess"];
  function human(sec){
    if(sec<1)return "instantly";
    var u=[["second",60],["minute",60],["hour",24],["day",365],["year",1e12]];var v=sec;
    for(var i=0;i<u.length;i++){if(v<u[i][1]||i===u.length-1){var n=Math.round(v);return (n>=1e9?"billions of years":(n.toLocaleString()+" "+u[i][0]+(n===1?"":"s")));}v/=u[i][1];}
  }
  function score(p){
    if(!p)return null;
    var pool=0;
    if(/[a-z]/.test(p))pool+=26; if(/[A-Z]/.test(p))pool+=26; if(/[0-9]/.test(p))pool+=10;
    if(/[^a-zA-Z0-9]/.test(p))pool+=33;
    var bits=p.length*(Math.log(pool||2)/Math.log(2));
    var low=p.toLowerCase();var common=COMMON.some(function(c){return low.indexOf(c)>=0;});
    if(common)bits=Math.min(bits,16);
    if(/^(.)\1+$/.test(p))bits=Math.min(bits,10);
    if(/^[0-9]+$/.test(p))bits=Math.min(bits,p.length*3.3);
    var sec=Math.pow(2,bits)/1e10;
    return {bits:bits,sec:sec,common:common};
  }
  function tier(b){
    if(b<28)return ["Very weak","#ff6b6b",16];
    if(b<40)return ["Weak","#f59e42",38];
    if(b<60)return ["Fair","#f5be58",64];
    if(b<80)return ["Strong","#4ad6a0",85];
    return ["Very strong","#26C485",100];
  }
  function upd(){
    var p=pw.value,s=score(p);
    if(!s){bar.style.width="0";ver.textContent="Enter a password to begin.";ver.style.color="var(--muted)";stats.innerHTML="";tips.innerHTML="";return;}
    var t=tier(s.bits);
    bar.style.width=t[2]+"%";bar.style.background=t[1];
    ver.textContent=t[0];ver.style.color=t[1];
    stats.innerHTML='<div><span>Length</span><b>'+p.length+'</b></div>'
      +'<div><span>Entropy</span><b>'+Math.round(s.bits)+' bits</b></div>'
      +'<div><span>Est. time to crack</span><b>'+human(s.sec)+'</b></div>';
    var tp=[];
    if(p.length<12)tp.push("Use at least 12–16 characters — length matters most.");
    if(!/[A-Z]/.test(p)||!/[a-z]/.test(p))tp.push("Mix upper and lower case.");
    if(!/[0-9]/.test(p))tp.push("Add some numbers.");
    if(!/[^a-zA-Z0-9]/.test(p))tp.push("Add a symbol like ! or #.");
    if(s.common)tp.push("Avoid common words and patterns — attackers try these first.");
    if(!tp.length)tp.push("Great password! Use a unique one per site and keep them in a password manager.");
    tips.innerHTML=tp.map(function(x){return "<li>"+x+"</li>";}).join("");
  }
  pw.addEventListener("input",upd);
})();
</script>""")
    return dict(slug="password-strength", title="Password Strength Checker | Free & Private | BVTech",
                desc="Test how strong your password is — entropy and estimated crack time, checked "
                     "entirely in your browser and never sent anywhere. Free tool by BVTech.",
                card_title="Password Strength Checker", icon="🔒",
                card_excerpt="How strong is your password really? See its entropy and crack time — "
                             "checked in your browser, never sent anywhere.",
                faqs=[("Is my password sent to BVTech or stored anywhere?",
                       "No. The entire check runs in your browser — your password never leaves your device and nothing is stored or logged."),
                      ("How is the crack time estimated?",
                       "We estimate entropy from the password's length and character variety, then assume a fast offline attack of about 10 billion guesses per second. Real times vary, but it's a solid guide to relative strength."),
                      ("What makes a strong password?",
                       "Length first — aim for 12–16+ characters, mix character types, avoid common words and reuse, and store unique passwords in a password manager with MFA turned on.")],
                body=body)


# ------------------------------------------------------- Password Generator
def password_generator():
    body = _wrap(
        "🔑 Free privacy tool", "Secure Password Generator",
        "Create strong, random passwords and passphrases generated <b>in your browser</b> with "
        "cryptographically-secure randomness — never sent anywhere. Copy and go.",
        r"""
<div class="card">
  <div id="pg-out" class="pg-out" tabindex="0">press Generate…</div>
  <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:12px">
    <button class="btn" id="pg-gen">🎲 Generate</button>
    <button class="btn" id="pg-copy" style="background:var(--o2)">📋 Copy</button>
    <span id="pg-copied" class="muted" style="align-self:center;opacity:0;transition:.2s">Copied!</span>
  </div>
  <div class="pg-opts">
    <label class="pg-range">Length: <b id="pg-lenv">18</b><input id="pg-len" type="range" min="6" max="48" value="18"></label>
    <label class="pg-chk"><input type="checkbox" id="pg-upper" checked> Uppercase</label>
    <label class="pg-chk"><input type="checkbox" id="pg-lower" checked> Lowercase</label>
    <label class="pg-chk"><input type="checkbox" id="pg-num" checked> Numbers</label>
    <label class="pg-chk"><input type="checkbox" id="pg-sym" checked> Symbols</label>
    <label class="pg-chk"><input type="checkbox" id="pg-amb" checked> Avoid look-alikes</label>
    <label class="pg-chk"><input type="checkbox" id="pg-phrase"> Passphrase mode</label>
  </div>
</div>
<style>
.pg-out{font-family:ui-monospace,Menlo,monospace;font-size:clamp(1.1rem,3.5vw,1.6rem);color:var(--o2);word-break:break-all;background:rgba(0,0,0,.25);border:1px solid var(--border);border-radius:10px;padding:16px;min-height:1.6em}
.pg-opts{margin-top:18px;display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.pg-range{grid-column:1/-1;color:var(--text);font-weight:600;display:flex;align-items:center;gap:10px}
.pg-range input{flex:1}
.pg-chk{display:flex;align-items:center;gap:8px;color:var(--text);font-weight:600}
.pg-chk input{width:auto}
</style>
<script>
(function(){
  var WORDS=["anchor","bridge","canyon","copper","dragon","ember","falcon","garden","harbor","island","jungle","kettle","lantern","meadow","nebula","orbit","pebble","quartz","rocket","saddle","timber","umbra","velvet","willow","yonder","zephyr","basil","cobalt","dapper","fable","granite","hazel","indigo","jasper","kelvin","lunar","maple","nickel","onyx","pepper","quiver","ripple","summit","tundra","valor","walnut","amber","breeze","cactus","dune"];
  var U="ABCDEFGHIJKLMNOPQRSTUVWXYZ",L="abcdefghijklmnopqrstuvwxyz",N="0123456789",S="!@#$%^&*-_=+?";
  var AMB=/[l1IO0o]/g;
  function rnd(max){var a=new Uint32Array(1);crypto.getRandomValues(a);return a[0]%max;}
  function pick(set){return set.charAt(rnd(set.length));}
  var out=document.getElementById("pg-out");
  function gen(){
    var phrase=document.getElementById("pg-phrase").checked;
    if(phrase){
      var n=4,parts=[];for(var i=0;i<n;i++){var w=WORDS[rnd(WORDS.length)];parts.push(w.charAt(0).toUpperCase()+w.slice(1));}
      out.textContent=parts.join("-")+rnd(100);return;
    }
    var pool="";
    if(document.getElementById("pg-upper").checked)pool+=U;
    if(document.getElementById("pg-lower").checked)pool+=L;
    if(document.getElementById("pg-num").checked)pool+=N;
    if(document.getElementById("pg-sym").checked)pool+=S;
    if(document.getElementById("pg-amb").checked)pool=pool.replace(AMB,"");
    if(!pool){out.textContent="pick at least one character set";return;}
    var len=+document.getElementById("pg-len").value,s="";
    for(var i=0;i<len;i++)s+=pick(pool);
    out.textContent=s;
  }
  document.getElementById("pg-len").addEventListener("input",function(){document.getElementById("pg-lenv").textContent=this.value;});
  document.getElementById("pg-gen").onclick=gen;
  document.getElementById("pg-copy").onclick=function(){
    var t=out.textContent||"";if(!t||t.indexOf("press")===0)return;
    (navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(function(){
      var c=document.getElementById("pg-copied");c.style.opacity=1;setTimeout(function(){c.style.opacity=0;},1200);
    }).catch(function(){});
  };
  gen();
})();
</script>""")
    return dict(slug="password-generator", title="Secure Password Generator | Free & Private | BVTech",
                desc="Generate strong random passwords and easy-to-type passphrases in your browser "
                     "with secure randomness — nothing is sent or stored. Free tool by BVTech.",
                card_title="Secure Password Generator", icon="🔑",
                card_excerpt="Create strong random passwords or passphrases with one tap — generated "
                             "in your browser, never sent anywhere.",
                faqs=[("Are the generated passwords safe to use?",
                       "Yes. They're created with your browser's cryptographically-secure random generator (crypto.getRandomValues) and never transmitted or logged."),
                      ("What is passphrase mode?",
                       "It strings together several random words plus a number — easier to type and remember than a symbol soup, while still being very hard to guess. Great for device logins and master passwords."),
                      ("How long should my password be?",
                       "12–16 characters is a good minimum; longer is stronger. Use a unique password for every account and store them in a password manager.")],
                body=body)


# ----------------------------------------------------------- Subnet Calculator
def subnet_calculator():
    body = _wrap(
        "🧮 Free IT tool", "Subnet / CIDR Calculator",
        "Enter an IPv4 address in CIDR notation (like <code>192.168.1.0/24</code>) and instantly "
        "get the network address, broadcast, usable host range, subnet mask and host count. "
        "Runs entirely in your browser.",
        r"""
<div class="card">
  <label for="sn-in">IP address / CIDR</label>
  <div style="display:flex;gap:10px;flex-wrap:wrap">
    <input id="sn-in" value="192.168.1.0/24" spellcheck="false" style="flex:1;min-width:200px">
    <button class="btn" id="sn-go">Calculate</button>
  </div>
  <div id="sn-err" class="muted" style="color:#ff8f8f;margin-top:10px;display:none"></div>
  <div class="sn-grid" id="sn-out"></div>
</div>
<style>
.sn-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:18px}
.sn-grid div{background:rgba(255,255,255,.03);border:1px solid var(--border);border-radius:10px;padding:11px 13px}
.sn-grid span{display:block;color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.06em}
.sn-grid b{color:var(--white);font-size:1rem;font-family:ui-monospace,Menlo,monospace;word-break:break-all}
#sn-in{font-family:ui-monospace,Menlo,monospace}
</style>
<script>
(function(){
  function toInt(ip){var p=ip.split(".");if(p.length!==4)return null;var n=0;for(var i=0;i<4;i++){var o=+p[i];if(!(o>=0&&o<=255)||p[i]==="")return null;n=(n*256)+o;}return n>>>0;}
  function toIp(n){return [(n>>>24)&255,(n>>>16)&255,(n>>>8)&255,n&255].join(".");}
  function calc(){
    var err=document.getElementById("sn-err"),out=document.getElementById("sn-out");
    err.style.display="none";out.innerHTML="";
    var raw=(document.getElementById("sn-in").value||"").trim();
    var m=raw.split("/");var ip=toInt(m[0]);var bits=m.length>1?+m[1]:32;
    if(ip===null||!(bits>=0&&bits<=32)||m[1]===""){err.textContent="Enter a valid IPv4 address and prefix, e.g. 10.0.0.0/24";err.style.display="block";return;}
    var mask=bits===0?0:(0xFFFFFFFF<<(32-bits))>>>0;
    var net=(ip&mask)>>>0,bc=(net|(~mask>>>0))>>>0;
    var total=Math.pow(2,32-bits);
    var usable=bits>=31?0:total-2;
    var first=bits>=31?net:(net+1)>>>0,last=bits>=31?bc:(bc-1)>>>0;
    function row(k,v){return '<div><span>'+k+'</span><b>'+v+'</b></div>';}
    out.innerHTML=row("Network address",toIp(net)+"/"+bits)
      +row("Usable host range",usable?(toIp(first)+" – "+toIp(last)):"—")
      +row("Broadcast",toIp(bc))
      +row("Subnet mask",toIp(mask))
      +row("Wildcard",toIp(~mask>>>0))
      +row("Total addresses",total.toLocaleString())
      +row("Usable hosts",usable.toLocaleString())
      +row("Prefix",("/"+bits));
  }
  document.getElementById("sn-go").onclick=calc;
  document.getElementById("sn-in").addEventListener("keydown",function(e){if(e.key==="Enter")calc();});
  calc();
})();
</script>""")
    return dict(slug="subnet-calculator", title="Subnet / CIDR Calculator | Free IPv4 Tool | BVTech",
                desc="Free IPv4 subnet calculator: enter CIDR like 192.168.1.0/24 to get the network, "
                     "broadcast, usable host range, subnet mask and host count. Runs in your browser.",
                card_title="Subnet / CIDR Calculator", icon="🧮",
                card_excerpt="Enter a CIDR like 192.168.1.0/24 and get the network, broadcast, host "
                             "range, mask and host count — instantly.",
                faqs=[("What does this subnet calculator do?",
                       "Given an IPv4 address and prefix length (CIDR), it computes the network address, broadcast address, usable host range, subnet mask, wildcard mask and the number of hosts — all in your browser."),
                      ("What is CIDR notation?",
                       "CIDR (Classless Inter-Domain Routing) writes a network as an address plus a prefix length, like 10.0.0.0/24. The /24 means the first 24 bits are the network portion, leaving 254 usable host addresses."),
                      ("Does it support IPv6?",
                       "This calculator is IPv4-only today. Need help planning IPv4 or IPv6 addressing for your business network? BVTech designs and documents networks for Texas companies — reach out.")],
                body=body)


# ----------------------------------------------------------- Hash Generator
def hash_generator():
    body = _wrap(
        "🔐 Free dev tool", "Hash Generator — SHA-256, SHA-1 &amp; SHA-512",
        "Generate cryptographic hashes of any text, computed <b>in your browser</b> "
        "with the Web Crypto API — nothing is uploaded. Great for checksums, file "
        "integrity, and quick fingerprints.",
        r"""
<div class="card">
  <label for="hg-in">Text to hash</label>
  <textarea id="hg-in" rows="4" placeholder="Type or paste text…" style="width:100%;background:rgba(255,255,255,.04);border:1px solid var(--border);border-radius:10px;padding:12px;color:var(--white);font-family:inherit;font-size:1rem;resize:vertical">hello world</textarea>
  <div class="hg-rows" id="hg-out" style="margin-top:16px"></div>
</div>
<style>
.hg-row{display:flex;gap:12px;align-items:baseline;padding:10px 0;border-top:1px solid var(--border)}
.hg-row:first-child{border-top:0}
.hg-row span{flex:0 0 80px;color:var(--o2);font-weight:800;font-size:.82rem}
.hg-row code{font-family:ui-monospace,Menlo,monospace;font-size:.82rem;color:var(--text);word-break:break-all;line-height:1.5}
</style>
<script>
(function(){
  var inp=document.getElementById('hg-in'),out=document.getElementById('hg-out');
  var ALGOS=['SHA-256','SHA-1','SHA-512'];
  function hex(buf){var a=new Uint8Array(buf),s='';for(var i=0;i<a.length;i++)s+=a[i].toString(16).padStart(2,'0');return s;}
  async function run(){
    if(!(window.crypto&&crypto.subtle)){out.innerHTML='<div class="muted">Web Crypto is unavailable in this browser.</div>';return;}
    var data=new TextEncoder().encode(inp.value||'');var rows='';
    for(var i=0;i<ALGOS.length;i++){try{var d=await crypto.subtle.digest(ALGOS[i],data);rows+='<div class="hg-row"><span>'+ALGOS[i]+'</span><code>'+hex(d)+'</code></div>';}catch(e){}}
    out.innerHTML=rows;
  }
  inp.addEventListener('input',run);run();
})();
</script>""")
    return dict(slug="hash-generator", title="Hash Generator — SHA-256 / SHA-1 / SHA-512 | Free | BVTech",
                desc="Free online hash generator: get the SHA-256, SHA-1 and SHA-512 hash of any "
                     "text, computed in your browser with Web Crypto. Nothing uploaded. By BVTech.",
                card_title="Hash Generator", icon="🔐",
                card_excerpt="SHA-256, SHA-1 & SHA-512 hashes of any text — computed in your browser, "
                             "nothing uploaded.",
                faqs=[("Is my text uploaded anywhere?",
                       "No. Hashing runs entirely in your browser via the Web Crypto API — your text never leaves your device."),
                      ("Which hash algorithms are supported?",
                       "SHA-256, SHA-1 and SHA-512. SHA-256 is the modern default; SHA-1 is shown for legacy checksums (it is no longer considered collision-resistant for security use)."),
                      ("What can I use a hash for?",
                       "Verifying a download matches its published checksum, fingerprinting data, and integrity checks. For storing passwords, use a slow password hash (bcrypt/argon2) server-side — not a raw SHA.")],
                body=body)


# -------------------------------------------------------- Base64 Encode/Decode
def base64_tool():
    body = _wrap(
        "🔁 Free dev tool", "Base64 Encoder &amp; Decoder",
        "Encode text to Base64 or decode Base64 back to text — UTF-8 safe, all "
        "<b>in your browser</b>. No uploads, no limits.",
        r"""
<div class="card">
  <div style="display:flex;gap:8px;margin-bottom:12px">
    <button class="btn b64-mode on" data-mode="enc">Encode →</button>
    <button class="btn b64-mode" data-mode="dec" style="background:#1d2742;color:var(--white)">← Decode</button>
  </div>
  <label for="b64-in">Input</label>
  <textarea id="b64-in" rows="4" placeholder="Type or paste…" style="width:100%;background:rgba(255,255,255,.04);border:1px solid var(--border);border-radius:10px;padding:12px;color:var(--white);font-family:ui-monospace,Menlo,monospace;font-size:.95rem;resize:vertical">BVTech</textarea>
  <label for="b64-out" style="margin-top:12px">Output</label>
  <textarea id="b64-out" rows="4" readonly style="width:100%;background:rgba(0,0,0,.25);border:1px solid var(--border);border-radius:10px;padding:12px;color:var(--o2);font-family:ui-monospace,Menlo,monospace;font-size:.95rem;resize:vertical"></textarea>
  <div class="muted" id="b64-err" style="color:#ff8f8f;margin-top:8px"></div>
</div>
<style>.b64-mode.on{background:var(--o);color:#0E0D2C}</style>
<script>
(function(){
  var mode='enc',inp=document.getElementById('b64-in'),out=document.getElementById('b64-out'),err=document.getElementById('b64-err');
  function run(){
    err.textContent='';var v=inp.value||'';
    try{
      if(mode==='enc'){out.value=btoa(unescape(encodeURIComponent(v)));}
      else{out.value=decodeURIComponent(escape(atob(v.replace(/\s+/g,''))));}
    }catch(e){out.value='';err.textContent=(mode==='dec'?'That is not valid Base64.':'Could not encode.');}
  }
  Array.prototype.forEach.call(document.querySelectorAll('.b64-mode'),function(b){
    b.onclick=function(){mode=b.getAttribute('data-mode');
      Array.prototype.forEach.call(document.querySelectorAll('.b64-mode'),function(x){x.classList.toggle('on',x===b);x.style.background=x===b?'var(--o)':'#1d2742';x.style.color=x===b?'#0E0D2C':'var(--white)';});run();};
  });
  inp.addEventListener('input',run);run();
})();
</script>""")
    return dict(slug="base64-encode-decode", title="Base64 Encoder & Decoder — Free Online Tool | BVTech",
                desc="Free Base64 encoder and decoder: convert text to Base64 and back, UTF-8 safe, "
                     "entirely in your browser. Nothing uploaded. By BVTech.",
                card_title="Base64 Encode / Decode", icon="🔁",
                card_excerpt="Convert text to Base64 and back — UTF-8 safe, in your browser, nothing "
                             "uploaded.",
                faqs=[("Is my data sent to a server?",
                       "No — encoding and decoding happen in your browser. Nothing is uploaded or stored."),
                      ("Does it handle non-English characters?",
                       "Yes. The tool is UTF-8 safe, so emoji and accented characters encode and decode correctly."),
                      ("Is Base64 encryption?",
                       "No. Base64 is an encoding, not encryption — anyone can decode it. Use it for transport/formatting, never to protect secrets.")],
                body=body)


# ----------------------------------------------------------- JSON Formatter
def json_formatter():
    body = _wrap(
        "🧩 Free dev tool", "JSON Formatter &amp; Validator",
        "Pretty-print, minify and validate JSON — <b>in your browser</b>, nothing "
        "uploaded. Catches the exact line of a syntax error so you can fix it fast.",
        r"""
<div class="card">
  <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">
    <button class="btn" id="jf-pretty">✨ Format</button>
    <button class="btn" id="jf-min" style="background:#1d2742;color:var(--white)">⚊ Minify</button>
    <span id="jf-status" class="muted" style="align-self:center"></span>
  </div>
  <textarea id="jf-in" rows="12" spellcheck="false" placeholder='{"paste":"your JSON here"}' style="width:100%;background:rgba(0,0,0,.25);border:1px solid var(--border);border-radius:10px;padding:14px;color:var(--white);font-family:ui-monospace,Menlo,monospace;font-size:.9rem;line-height:1.55;resize:vertical">{"bvtech":"IT & cybersecurity","services":["managed IT","security","cloud"],"texas":true}</textarea>
</div>
<script>
(function(){
  var ta=document.getElementById('jf-in'),st=document.getElementById('jf-status');
  function go(min){
    st.textContent='';st.style.color='';
    var raw=ta.value;
    try{var obj=JSON.parse(raw);ta.value=min?JSON.stringify(obj):JSON.stringify(obj,null,2);st.textContent='✓ Valid JSON';st.style.color='#4ad6a0';}
    catch(e){var m=String(e.message||e);st.textContent='✗ '+m;st.style.color='#ff8f8f';}
  }
  document.getElementById('jf-pretty').onclick=function(){go(false);};
  document.getElementById('jf-min').onclick=function(){go(true);};
  go(false);
})();
</script>""")
    return dict(slug="json-formatter", title="JSON Formatter & Validator — Free Online | BVTech",
                desc="Free JSON formatter, minifier and validator that runs entirely in your browser. "
                     "Pretty-print or minify JSON and catch syntax errors instantly. By BVTech.",
                card_title="JSON Formatter / Validator", icon="🧩",
                card_excerpt="Pretty-print, minify and validate JSON in your browser — it points to "
                             "the exact syntax error.",
                faqs=[("Is my JSON uploaded anywhere?",
                       "No. Formatting and validation run in your browser — your data never leaves your device."),
                      ("What does the validator catch?",
                       "Any JSON syntax error — trailing commas, unquoted keys, mismatched brackets — and it shows the error message so you can locate it."),
                      ("What's the difference between format and minify?",
                       "Format pretty-prints with 2-space indentation for readability; minify strips all whitespace to the smallest valid JSON for transport.")],
                body=body)


# ------------------------------------------------------------- UUID Generator
def uuid_generator():
    body = _wrap(
        "🆔 Free dev tool", "UUID / GUID Generator",
        "Generate RFC-4122 version-4 UUIDs with cryptographically-secure randomness, "
        "<b>in your browser</b>. Click to copy. Great for IDs, keys and test data.",
        r"""
<div class="card">
  <div id="ug-out" class="ug-out">—</div>
  <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:14px">
    <button class="btn" id="ug-gen">🎲 New UUID</button>
    <button class="btn" id="ug-copy" style="background:var(--o2)">📋 Copy</button>
    <label class="muted" style="align-self:center;display:flex;align-items:center;gap:6px">How many: <input id="ug-n" type="number" min="1" max="50" value="1" style="width:70px;padding:7px 9px"></label>
  </div>
  <div id="ug-list" style="margin-top:14px"></div>
</div>
<style>
.ug-out{font-family:ui-monospace,Menlo,monospace;font-size:clamp(1rem,3vw,1.4rem);color:var(--o2);word-break:break-all;background:rgba(0,0,0,.25);border:1px solid var(--border);border-radius:10px;padding:16px}
#ug-list div{font-family:ui-monospace,Menlo,monospace;font-size:.86rem;color:var(--text);padding:6px 0;border-top:1px solid var(--border);word-break:break-all}
</style>
<script>
(function(){
  function uuid(){
    if(crypto.randomUUID)return crypto.randomUUID();
    var b=new Uint8Array(16);crypto.getRandomValues(b);b[6]=(b[6]&15)|64;b[8]=(b[8]&63)|128;
    var h=[];for(var i=0;i<16;i++)h.push(b[i].toString(16).padStart(2,'0'));
    return h.slice(0,4).join('')+'-'+h.slice(4,6).join('')+'-'+h.slice(6,8).join('')+'-'+h.slice(8,10).join('')+'-'+h.slice(10).join('');
  }
  var out=document.getElementById('ug-out'),list=document.getElementById('ug-list');
  function gen(){
    var n=Math.max(1,Math.min(50,+document.getElementById('ug-n').value||1));
    var first=uuid();out.textContent=first;
    if(n>1){var rows='';for(var i=1;i<n;i++)rows+='<div>'+uuid()+'</div>';list.innerHTML=rows;}else list.innerHTML='';
  }
  document.getElementById('ug-gen').onclick=gen;
  document.getElementById('ug-copy').onclick=function(){
    var t=out.textContent;var all=[t].concat(Array.prototype.map.call(list.querySelectorAll('div'),function(d){return d.textContent;})).join('\n');
    (navigator.clipboard?navigator.clipboard.writeText(all):Promise.reject()).catch(function(){});
  };
  gen();
})();
</script>""")
    return dict(slug="uuid-generator", title="UUID / GUID Generator — Free v4 UUIDs | BVTech",
                desc="Free online UUID/GUID generator: create RFC-4122 version-4 UUIDs with secure "
                     "randomness in your browser. Generate one or many, click to copy. By BVTech.",
                card_title="UUID / GUID Generator", icon="🆔",
                card_excerpt="Generate secure RFC-4122 v4 UUIDs — one or many — right in your browser.",
                faqs=[("Are these UUIDs cryptographically random?",
                       "Yes. They use your browser's secure random generator (crypto.randomUUID / getRandomValues), so collisions are astronomically unlikely."),
                      ("What version of UUID is this?",
                       "Version 4 (random), the most common form for database keys, correlation IDs and test data."),
                      ("Can I generate many at once?",
                       "Yes — set the count (up to 50) and copy them all with one click.")],
                body=body)


def _faq_block(faqs):
    """Render a visible FAQ section so the on-page content matches the FAQPage
    JSON-LD (answer engines and Google want the schema to reflect visible text)."""
    import html as _h
    items = "".join(
        f'<details class="tl-faq"><summary>{_h.escape(q)}</summary>'
        f'<div class="tl-faq-a">{_h.escape(a)}</div></details>'
        for q, a in faqs)
    return (
        '<div class="tl-faqs"><h2>Frequently asked questions</h2>'
        '<style>'
        '.tl-faqs{margin:34px 0 0}'
        '.tl-faqs h2{font-family:var(--fh);color:var(--white);font-size:1.3rem;margin:0 0 14px}'
        '.tl-faq{border:1px solid var(--border);border-radius:12px;background:var(--card);margin:0 0 10px;padding:0 16px}'
        '.tl-faq summary{cursor:pointer;padding:14px 0;color:var(--white);font-weight:700;font-size:1rem;list-style:none}'
        '.tl-faq summary::-webkit-details-marker{display:none}'
        '.tl-faq summary::before{content:"+";color:var(--o2);font-weight:800;margin-right:10px}'
        '.tl-faq[open] summary::before{content:"–"}'
        '.tl-faq-a{color:var(--text);font-size:.94rem;line-height:1.65;padding:0 0 14px}'
        '</style>' + items + '</div>')


def all_tools():
    from . import pages_convert
    tools = [speed_test(), whats_my_ip(), is_it_down(), ev_savings(),
             password_strength(), password_generator(), subnet_calculator(),
             hash_generator(), base64_tool(), json_formatter(), uuid_generator(),
             *pages_convert.all_converters()]
    # Append a VISIBLE FAQ to any tool that declares faqs, so the page text
    # matches its FAQPage schema (schema must reflect visible content).
    for t in tools:
        if t.get("faqs"):
            t["body"] = t["body"] + _faq_block(t["faqs"])
    return tools
