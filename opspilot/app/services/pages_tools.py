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
<a href="/contact/">ask us how</a>.</p></div>
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
Slow? <a href="/contact/">We help Texas businesses fix slow, flaky internet</a> for good.</p>
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


def all_tools():
    return [whats_my_ip(), speed_test(), is_it_down(), ev_savings()]
