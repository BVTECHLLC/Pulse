"""The BVTech Explore hub (/explore/) — a friendly "front page of the internet"
for bvtech.org (v1.102): positive tech / Tesla / space / AI / science headlines,
a NASA photo, upcoming rocket launches, local weather, "on this day in tech", a
daily trivia game and a tip — all pulled live by the site Worker (/tools-api/*)
and rendered client-side. Headlines link OUT to the publisher (no copied text,
so Google sees a curated link hub, not scraped content). Styled with the site's
own CSS variables; all script is inline (the site CSP allows 'self'/'unsafe-inline').
"""
from __future__ import annotations

TITLE = "Explore — Tech, Space, EVs, AI & Good News | BVTech"
DESC = ("Your friendly front page for technology: the day's best tech, Tesla, space, "
        "AI and science headlines, a NASA photo, rocket launches, a daily tech-trivia "
        "game and more — curated by Jordan Polasek at BVTech. No politics, no doomscroll.")

CATS = [("tech", "💻 Tech"), ("tesla", "⚡ Tesla & EVs"), ("space", "🚀 Space"),
        ("ai", "🤖 AI"), ("science", "🔬 Science"), ("gadgets", "📱 Gadgets"),
        ("gaming", "🎮 Gaming"), ("security", "🛡️ Security"), ("good", "🌟 Good News")]

_TABS = "".join(
    f'<button class="xp-tab{" on" if i == 0 else ""}" data-cat="{c}">{label}</button>'
    for i, (c, label) in enumerate(CATS))


def body() -> str:
    return r"""
<section class="xp">
<style>
.xp{--o:#EB6F24;--o2:#F5BE58;max-width:1160px;margin:0 auto;padding:30px 18px 90px}
.xp-hero{display:flex;justify-content:space-between;align-items:flex-end;gap:18px;flex-wrap:wrap;margin:6px 0 10px}
.xp-hello{font-family:var(--fh);font-size:clamp(1.7rem,4vw,2.5rem);font-weight:800;color:var(--white);margin:0;line-height:1.1}
.xp-hello span{background:linear-gradient(90deg,var(--o),var(--o2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.xp-sub{color:var(--muted);margin:8px 0 0;font-size:.98rem}
.xp-wx{display:flex;align-items:center;gap:12px;background:var(--card);border:1px solid var(--border);border-radius:14px;padding:12px 16px;min-width:200px}
.xp-wx .t{font-size:1.9rem;font-weight:800;color:var(--white);font-family:var(--fh);line-height:1}
.xp-wx .e{font-size:2rem;line-height:1}
.xp-wx .m{color:var(--muted);font-size:.8rem;line-height:1.35}
.xp-clock{color:var(--o2);font-variant-numeric:tabular-nums}
.xp-grid{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:22px;margin-top:22px;align-items:start}
.xp-main,.xp-side{min-width:0}
@media(max-width:900px){.xp-grid{grid-template-columns:1fr}}
.xp-tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}
.xp-tab{font-family:var(--fb);font-size:.86rem;font-weight:700;padding:7px 14px;border-radius:999px;border:1px solid var(--border);background:var(--card);color:var(--text);cursor:pointer;transition:.15s}
.xp-tab:hover{border-color:var(--o)}
.xp-tab.on{background:linear-gradient(90deg,var(--o),var(--o2));color:#0E0D2C;border-color:transparent}
.xp-feat{display:block;border-radius:16px;border:1px solid var(--border);background:linear-gradient(150deg,rgba(235,111,36,.10),rgba(68,64,219,.08));padding:24px 26px;margin-bottom:14px;text-decoration:none}
.xp-feat .src{font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;color:var(--o2);font-weight:800}
.xp-feat h3{color:var(--white);font-size:1.3rem;line-height:1.3;margin:8px 0 6px;font-family:var(--fh)}
.xp-feat p{color:var(--muted);margin:0;font-size:.92rem;line-height:1.6}
.xp-list{display:flex;flex-direction:column;gap:2px}
.xp-item{display:flex;gap:14px;align-items:baseline;padding:13px 14px;border-radius:11px;text-decoration:none;border:1px solid transparent;transition:.12s}
.xp-item:hover{background:var(--card);border-color:var(--border)}
.xp-item .n{color:var(--o2);font-weight:800;font-family:var(--fh);font-size:.95rem;flex:0 0 1.4em;text-align:right}
.xp-item .b{min-width:0}
.xp-item h4{color:var(--white);font-size:1rem;line-height:1.4;margin:0;font-weight:600}
.xp-item .meta{color:var(--muted);font-size:.78rem;margin-top:3px}
.xp-item:hover h4{color:var(--o2)}
.xp-card{border-radius:16px;border:1px solid var(--border);background:var(--card);padding:20px;margin-bottom:18px}
.xp-card h3{margin:0 0 12px;color:var(--white);font-family:var(--fh);font-size:1.05rem;display:flex;align-items:center;gap:8px}
.xp-card h3 .tag{margin-left:auto;font-size:.66rem;font-weight:800;letter-spacing:.08em;color:var(--o2);border:1px solid var(--border);border-radius:999px;padding:2px 9px}
.xp-photo img{width:100%;border-radius:12px;display:block;max-height:240px;object-fit:cover;background:var(--bg3)}
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
.xp-otd a{color:inherit;text-decoration:none}.xp-otd a:hover{color:var(--o2)}
.xp-game .q{color:var(--white);font-size:1.02rem;font-weight:600;line-height:1.4;margin:0 0 14px}
.xp-opt{display:block;width:100%;text-align:left;padding:11px 14px;margin:0 0 8px;border-radius:10px;border:1px solid var(--border);background:rgba(255,255,255,.02);color:var(--text);font-size:.92rem;cursor:pointer;transition:.12s;font-family:inherit}
.xp-opt:hover:not(:disabled){border-color:var(--o)}
.xp-opt.right{border-color:var(--green);background:rgba(38,196,133,.14);color:#fff}
.xp-opt.wrong{border-color:#e5484d;background:rgba(229,72,77,.14)}
.xp-opt:disabled{cursor:default}
.xp-why{color:var(--muted);font-size:.86rem;line-height:1.55;margin:12px 0 0;padding:12px 14px;border-radius:10px;background:rgba(68,64,219,.1);border:1px solid var(--border)}
.xp-tip{color:var(--text);font-size:.94rem;line-height:1.6}
.xp-tip b{color:var(--o2)}
.xp-cta{margin-top:30px;border-radius:18px;padding:30px 28px;background:linear-gradient(135deg,rgba(68,64,219,.2),rgba(235,111,36,.14));border:1px solid rgba(245,190,88,.3);text-align:center}
.xp-cta h2{color:var(--white);font-family:var(--fh);margin:0 0 8px;font-size:clamp(1.3rem,3vw,1.8rem)}
.xp-cta p{color:var(--text);margin:0 auto 18px;max-width:560px;line-height:1.6}
.xp-cta a{display:inline-block;margin:5px;padding:12px 22px;border-radius:10px;font-weight:800;text-decoration:none}
.xp-cta .p{background:var(--o);color:#0E0D2C}.xp-cta .s{background:transparent;color:#fff;border:1px solid rgba(255,255,255,.3)}
.xp-sk{color:var(--muted);padding:26px 4px;text-align:center;font-size:.9rem}
.xp-foot{color:var(--muted);font-size:.8rem;text-align:center;margin-top:30px;line-height:1.6}
</style>

<div class="xp-hero">
  <div>
    <h1 class="xp-hello"><span id="xp-greet">Welcome</span> to Explore</h1>
    <p class="xp-sub">The fun side of tech, curated by <strong style="color:var(--text)">Jordan Polasek</strong> at BVTech — no politics, no doomscroll. <span class="xp-clock" id="xp-clock"></span></p>
  </div>
  <div class="xp-wx" id="xp-wx" hidden>
    <div class="e" id="xp-wx-e">🌡️</div>
    <div><div class="t" id="xp-wx-t">—</div><div class="m" id="xp-wx-m"></div></div>
  </div>
</div>

<div class="xp-grid">
  <div class="xp-main">
    <div class="xp-tabs">""" + _TABS + r"""</div>
    <div id="xp-feed"><div class="xp-sk">Loading the good stuff…</div></div>
  </div>

  <aside class="xp-side">
    <div class="xp-card xp-game">
      <h3>🧠 Daily Byte <span class="tag" id="xp-game-tag">TODAY</span></h3>
      <div id="xp-game"><div class="xp-sk">Loading today's question…</div></div>
    </div>
    <div class="xp-card xp-photo" id="xp-photo-card" hidden>
      <h3>🔭 NASA Photo of the Day</h3>
      <a id="xp-photo-link" target="_blank" rel="noopener"><img id="xp-photo-img" alt="" loading="lazy"></a>
      <div class="cap" id="xp-photo-cap"></div>
    </div>
    <div class="xp-card" id="xp-launch-card" hidden>
      <h3>🚀 Next Rocket Launches</h3>
      <div id="xp-launches"></div>
    </div>
    <div class="xp-card" id="xp-otd-card" hidden>
      <h3>📅 On This Day in Tech</h3>
      <ul class="xp-otd" id="xp-otd" style="margin:0;padding:0"></ul>
    </div>
    <div class="xp-card">
      <h3>💡 Tip of the Day</h3>
      <div class="xp-tip" id="xp-tip">Stay tuned…</div>
    </div>
  </aside>
</div>

<div class="xp-cta">
  <h2>Liked poking around? Learn the real thing — free.</h2>
  <p>The BVTech Academy turns this curiosity into skills: hands-on labs, our new live-style Lightning Labs on cloud and AI security, and certificates. Built in Texas by Jordan Polasek.</p>
  <a class="p" href="/academy/lightning-labs/">⚡ Try a Lightning Lab</a>
  <a class="s" href="/academy/">🎓 Academy Home</a>
  <a class="s" href="/tools/">🧰 Free Tools</a>
</div>
<p class="xp-foot">Headlines link to their original publishers — BVTech just curates the good ones. Photos courtesy of NASA. Refreshed through the day.</p>
</section>

<script>
(function(){
  var API="/tools-api/";
  function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e;}
  function ago(ts){if(!ts)return"";var s=(Date.now()-ts)/1000;if(s<3600)return Math.max(1,Math.round(s/60))+"m ago";if(s<86400)return Math.round(s/3600)+"h ago";return Math.round(s/86400)+"d ago";}
  function get(u){return fetch(API+u).then(function(r){return r.json();});}

  // greeting + clock
  var h=new Date().getHours();
  document.getElementById("xp-greet").textContent=h<12?"Good morning":h<18?"Good afternoon":"Good evening";
  var ck=document.getElementById("xp-clock");
  function tick(){try{ck.textContent="· "+new Date().toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"});}catch(e){}}
  tick();setInterval(tick,30000);

  // headlines
  var feed=document.getElementById("xp-feed"),cur="tech",loaded={};
  function renderFeed(cat,data){
    if(cur!==cat)return;
    feed.textContent="";
    var items=(data&&data.items)||[];
    if(!items.length){feed.appendChild(el("div","xp-sk","No headlines right now — check back soon."));return;}
    var f=items[0];
    var fa=el("a","xp-feat");fa.href=f.link;fa.target="_blank";fa.rel="noopener";
    fa.appendChild(el("div","src",f.source+(f.t?" · "+ago(f.t):"")));
    fa.appendChild(el("h3",null,f.title));
    feed.appendChild(fa);
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
  function load(cat){
    cur=cat;
    if(loaded[cat]){renderFeed(cat,loaded[cat]);return;}
    feed.innerHTML='<div class="xp-sk">Loading '+cat+'…</div>';
    get("feeds?cat="+cat).then(function(d){loaded[cat]=d;renderFeed(cat,d);})
      .catch(function(){if(cur===cat)feed.innerHTML='<div class="xp-sk">Could not load headlines. Try another tab.</div>';});
  }
  Array.prototype.forEach.call(document.querySelectorAll(".xp-tab"),function(t){
    t.addEventListener("click",function(){
      document.querySelector(".xp-tab.on").classList.remove("on");
      t.classList.add("on");load(t.dataset.cat);
    });
  });
  load("tech");

  // weather (visitor location if allowed, else El Campo TX)
  function wx(lat,lon){
    get("explore/weather"+(lat?"?lat="+lat+"&lon="+lon:"")).then(function(d){
      if(!d||!d.now||d.now.temp==null)return;
      document.getElementById("xp-wx-e").textContent=d.now.sky[1];
      document.getElementById("xp-wx-t").textContent=d.now.temp+"°";
      document.getElementById("xp-wx-m").innerHTML=d.now.sky[0]+"<br>feels "+d.now.feels+"° · "+(d.days[0]?("H "+d.days[0].hi+"° L "+d.days[0].lo+"°"):"");
      document.getElementById("xp-wx").hidden=false;
    }).catch(function(){});
  }
  if(navigator.geolocation){
    navigator.geolocation.getCurrentPosition(
      function(p){wx(p.coords.latitude.toFixed(2),p.coords.longitude.toFixed(2));},
      function(){wx();},{timeout:6000,maximumAge:3600000});
  }else wx();

  // daily game + tip
  get("daily").then(function(d){
    var box=document.getElementById("xp-game");box.textContent="";
    document.getElementById("xp-tip").innerHTML="<b>Did you know?</b> "+(d.tip||"");
    if(!d||!d.question){box.appendChild(el("div","xp-sk","Game unavailable."));return;}
    box.appendChild(el("p","q",d.question.q));
    var answered=false,btns=[];
    (d.question.options||[]).forEach(function(opt,i){
      var b=el("button","xp-opt",opt);btns.push(b);
      b.addEventListener("click",function(){
        if(answered)return;answered=true;
        fetch(API+"daily/grade",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({choice:i})})
          .then(function(r){return r.json();}).then(function(res){
            btns.forEach(function(x){x.disabled=true;});
            if(res.correct){b.classList.add("right");}
            else{b.classList.add("wrong");if(btns[res.answer])btns[res.answer].classList.add("right");}
            box.appendChild(el("div","xp-why",(res.correct?"✅ Nailed it. ":"💡 ")+(res.why||"")));
          }).catch(function(){answered=false;});
      });
      box.appendChild(b);
    });
  }).catch(function(){document.getElementById("xp-game").innerHTML='<div class="xp-sk">Game unavailable.</div>';});

  // NASA photo
  get("explore/photos").then(function(d){
    var it=(d&&d.items||[])[0];if(!it)return;
    document.getElementById("xp-photo-img").src=it.img;
    document.getElementById("xp-photo-img").alt=it.title;
    document.getElementById("xp-photo-link").href=it.link||it.img;
    document.getElementById("xp-photo-cap").innerHTML="<b>"+it.title+"</b> — "+(it.desc||"");
    document.getElementById("xp-photo-card").hidden=false;
  }).catch(function(){});

  // launches
  get("explore/launches").then(function(d){
    var items=(d&&d.items)||[];if(!items.length)return;
    var box=document.getElementById("xp-launches");
    items.forEach(function(l){
      var dt=new Date(l.net);
      var row=el("div","xp-launch");
      var dd=el("div","d");dd.appendChild(el("b",null,String(dt.getDate())));
      dd.appendChild(el("span",null,dt.toLocaleString([], {month:"short"})));
      row.appendChild(dd);
      var i=el("div","i");i.appendChild(el("h4",null,l.name));
      i.appendChild(el("p",null,(l.provider||"")+" · "+dt.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"})));
      row.appendChild(i);box.appendChild(row);
    });
    document.getElementById("xp-launch-card").hidden=false;
  }).catch(function(){});

  // on this day
  get("explore/onthisday").then(function(d){
    var items=(d&&d.items)||[];if(!items.length)return;
    var ul=document.getElementById("xp-otd");
    items.forEach(function(e){
      var li=el("li");li.appendChild(el("b",null,String(e.year)));
      if(e.link){var a=el("a",null,e.text);a.href=e.link;a.target="_blank";a.rel="noopener";li.appendChild(a);}
      else li.appendChild(document.createTextNode(e.text));
      ul.appendChild(li);
    });
    document.getElementById("xp-otd-card").hidden=false;
  }).catch(function(){});
})();
</script>
"""
