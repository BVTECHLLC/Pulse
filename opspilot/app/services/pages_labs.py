"""BVTech Lightning Labs page (/academy/lightning-labs/) — v1.102.

A free, on-demand take on the live "lightning class" format: short, interactive,
instructor-authored mini-courses on cloud and AI security. The three labs mirror
the three topics businesses keep asking about (Azure/M365 identity attacks,
Active Directory, AI red-teaming), but self-paced and hands-on instead of a
scheduled stream. Questions are graded by the site Worker (/tools-api/lab) so
answers never sit in the page. Authored by Jordan Polasek, BVTech LLC.
"""
from __future__ import annotations

TITLE = "Lightning Labs — Free Interactive Cloud & AI Security Classes | BVTech"
DESC = ("Free, self-paced lightning labs by Jordan Polasek: trace identity attacks in "
        "Azure & Microsoft 365, demystify Active Directory, and red-team an AI chatbot. "
        "Hands-on and interactive — no scheduled stream, learn the moment you land.")


def body() -> str:
    return r"""
<section class="ll">
<style>
.ll{--o:#EB6F24;--o2:#F5BE58;max-width:1000px;margin:0 auto;padding:40px 18px 90px}
.ll-eyebrow{font-size:.78rem;letter-spacing:.14em;text-transform:uppercase;color:var(--o2);font-weight:800}
.ll h1{font-family:var(--fh);font-size:clamp(2rem,5vw,2.9rem);color:var(--white);line-height:1.1;margin:.3em 0 .35em}
.ll .lead{color:var(--text);font-size:1.08rem;line-height:1.7;max-width:720px;margin:0 0 10px}
.ll .by{color:var(--muted);font-size:.92rem;margin:0 0 30px}
.ll .by b{color:var(--o2)}
.ll-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px}
.ll-card{text-align:left;border-radius:16px;border:1px solid var(--border);background:var(--card);padding:24px;cursor:pointer;transition:.15s;color:inherit;font-family:inherit;display:flex;flex-direction:column}
.ll-card:hover{border-color:var(--o);transform:translateY(-3px)}
.ll-card .ic{font-size:2rem}
.ll-card .trk{font-size:.7rem;letter-spacing:.08em;text-transform:uppercase;font-weight:800;color:var(--o2);margin:10px 0 6px}
.ll-card h3{color:var(--white);font-family:var(--fh);font-size:1.15rem;line-height:1.3;margin:0 0 8px}
.ll-card p{color:var(--muted);font-size:.9rem;line-height:1.6;margin:0 0 16px;flex:1}
.ll-card .m{display:flex;gap:14px;font-size:.8rem;color:var(--text)}
.ll-card .m b{color:var(--o2)}
.ll-card .go{margin-top:14px;display:inline-block;font-weight:800;color:var(--o)}
.ll-run{display:none}
.ll-run.on{display:block}
.ll-cards.off{display:none}
.ll-back{background:none;border:0;color:var(--muted);font-size:.9rem;cursor:pointer;padding:0;margin:0 0 18px;font-family:inherit}
.ll-back:hover{color:var(--o2)}
.ll-prog{height:6px;border-radius:999px;background:rgba(255,255,255,.08);overflow:hidden;margin:0 0 22px}
.ll-prog i{display:block;height:100%;background:linear-gradient(90deg,var(--o),var(--o2));width:0;transition:width .3s}
.ll-intro{color:var(--text);line-height:1.7;background:rgba(68,64,219,.1);border:1px solid var(--border);border-radius:12px;padding:16px 18px;margin:0 0 22px}
.ll-q{color:var(--white);font-size:1.15rem;font-weight:600;line-height:1.45;margin:0 0 6px;font-family:var(--fh)}
.ll-hint{color:var(--muted);font-size:.84rem;margin:0 0 16px}
.ll-opt{display:block;width:100%;text-align:left;padding:14px 16px;margin:0 0 10px;border-radius:11px;border:1px solid var(--border);background:rgba(255,255,255,.02);color:var(--text);font-size:.96rem;cursor:pointer;transition:.12s;font-family:inherit;line-height:1.5}
.ll-opt:hover:not(.locked){border-color:var(--o)}
.ll-opt.sel{border-color:var(--o);background:rgba(235,111,36,.12)}
.ll-opt.right{border-color:var(--green);background:rgba(38,196,133,.16);color:#fff}
.ll-opt.wrong{border-color:#e5484d;background:rgba(229,72,77,.14)}
.ll-opt.locked{cursor:default}
.ll-chk{display:inline-flex;width:20px;height:20px;border-radius:6px;border:2px solid var(--muted);margin-right:10px;vertical-align:-4px}
.ll-opt.sel .ll-chk{border-color:var(--o);background:var(--o)}
.ll-btn{padding:13px 26px;border-radius:10px;border:0;background:var(--o);color:#0E0D2C;font-weight:800;font-size:1rem;cursor:pointer;font-family:inherit;margin-top:6px}
.ll-btn[disabled]{opacity:.5;cursor:default}
.ll-why{color:var(--text);font-size:.92rem;line-height:1.65;margin:14px 0 0;padding:14px 16px;border-radius:11px;border:1px solid var(--border)}
.ll-why.ok{background:rgba(38,196,133,.1)}.ll-why.no{background:rgba(229,72,77,.1)}
.ll-why b{color:var(--white)}
.ll-done{text-align:center;padding:20px 10px}
.ll-done .score{font-family:var(--fh);font-size:3rem;font-weight:800;color:var(--o2);line-height:1}
.ll-done h2{color:var(--white);font-family:var(--fh);margin:14px 0 10px}
.ll-done p{color:var(--text);line-height:1.7;max-width:620px;margin:0 auto 20px}
.ll-done a{display:inline-block;margin:5px;padding:12px 22px;border-radius:10px;font-weight:800;text-decoration:none}
.ll-done .p{background:var(--o);color:#0E0D2C}.ll-done .s{background:transparent;color:#fff;border:1px solid rgba(255,255,255,.3)}
.ll-note{margin-top:30px;color:var(--muted);font-size:.86rem;line-height:1.6;border-top:1px solid var(--border);padding-top:18px}
</style>

<div class="ll-eyebrow">⚡ Free · Interactive · Self-paced</div>
<h1>Lightning Labs</h1>
<p class="lead">Short, hands-on security classes you can take the moment you land — no
scheduled stream, no sign-up wall. Read the scenario, make the calls a real defender
makes, and get instant feedback on every choice.</p>
<p class="by">Authored by <b>Jordan Polasek</b>, Founder of BVTech LLC · El Campo, Texas</p>

<div class="ll-cards" id="ll-cards"><div style="color:var(--muted);padding:30px 0">Loading labs…</div></div>

<div class="ll-run" id="ll-run">
  <button class="ll-back" id="ll-back">← All Lightning Labs</button>
  <div class="ll-eyebrow" id="ll-run-trk"></div>
  <h1 id="ll-run-title" style="font-size:clamp(1.6rem,4vw,2.2rem)"></h1>
  <div class="ll-prog"><i id="ll-prog"></i></div>
  <div id="ll-stage"></div>
</div>

<p class="ll-note">These labs are a free taste of the BVTech Academy. Want the real thing
for your team? BVTech runs private, hands-on security training for Texas businesses —
<a href="/contact/" style="color:var(--o2)">get in touch</a>.</p>
</section>

<script>
(function(){
  var API="/tools-api/lab";
  function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e;}
  var cards=document.getElementById("ll-cards"),run=document.getElementById("ll-run"),
      stage=document.getElementById("ll-stage");

  function showList(){
    run.classList.remove("on");cards.classList.remove("off");
    history.replaceState(null,"","/academy/lightning-labs/");window.scrollTo(0,0);
  }
  document.getElementById("ll-back").addEventListener("click",showList);

  fetch(API).then(function(r){return r.json();}).then(function(d){
    cards.textContent="";
    (d.labs||[]).forEach(function(l){
      var c=el("button","ll-card");
      c.appendChild(el("div","ic",l.icon));
      c.appendChild(el("div","trk",l.track));
      c.appendChild(el("h3",null,l.title));
      c.appendChild(el("p",null,l.blurb));
      var m=el("div","m");
      m.innerHTML="<span>⏱ <b>"+l.minutes+" min</b></span><span>⭐ <b>+"+l.xp+" XP</b></span>";
      c.appendChild(m);
      c.appendChild(el("span","go","Start the lab →"));
      c.addEventListener("click",function(){openLab(l.id);});
      cards.appendChild(c);
    });
    if(location.hash.indexOf("lab=")>=0)openLab(location.hash.split("lab=")[1]);
  }).catch(function(){cards.innerHTML='<div style="color:var(--muted)">Could not load labs right now. Please refresh.</div>';});

  function openLab(id){
    fetch(API+"?id="+encodeURIComponent(id)).then(function(r){return r.json();}).then(function(lab){
      if(!lab||lab.error)return;
      cards.classList.add("off");run.classList.add("on");
      history.replaceState(null,"","#lab="+id);window.scrollTo(0,0);
      document.getElementById("ll-run-trk").textContent=lab.icon+" "+lab.track;
      document.getElementById("ll-run-title").textContent=lab.title;
      var i=0,score=0;
      function prog(){document.getElementById("ll-prog").style.width=(i/lab.steps.length*100)+"%";}
      function intro(){
        stage.textContent="";prog();
        stage.appendChild(Object.assign(el("div","ll-intro"),{textContent:lab.intro}));
        var b=el("button","ll-btn","Start →");b.addEventListener("click",step);stage.appendChild(b);
      }
      function step(){
        if(i>=lab.steps.length)return done();
        prog();var s=lab.steps[i];stage.textContent="";
        stage.appendChild(el("div","ll-q",s.q));
        var multi=s.kind==="multi",chosen=[];
        if(multi)stage.appendChild(el("div","ll-hint","Pick all that apply, then check."));
        var opts=[];
        s.options.forEach(function(o){
          var b=el("button","ll-opt");
          if(multi){var cb=el("span","ll-chk");b.appendChild(cb);}
          b.appendChild(document.createTextNode(o.t));opts.push(b);
          b.addEventListener("click",function(){
            if(b.classList.contains("locked"))return;
            if(multi){
              var k=chosen.indexOf(o.j);
              if(k>=0){chosen.splice(k,1);b.classList.remove("sel");}
              else{chosen.push(o.j);b.classList.add("sel");}
            }else{grade([o.j],opts,s);}
          });
          stage.appendChild(b);
        });
        if(multi){
          var cb2=el("button","ll-btn","Check answer");
          cb2.addEventListener("click",function(){if(chosen.length)grade(chosen,opts,s);});
          stage.appendChild(cb2);
        }
      }
      function grade(answer,opts,s){
        opts.forEach(function(o){o.classList.add("locked");});
        fetch(API+"/grade",{method:"POST",headers:{"Content-Type":"application/json"},
          body:JSON.stringify({id:id,step:i,answer:s.kind==="multi"?answer:answer[0]})})
          .then(function(r){return r.json();}).then(function(res){
            if(res.correct)score++;
            var btns=stage.querySelectorAll(".ll-btn");btns.forEach(function(x){x.remove();});
            // mark options
            s.options.forEach(function(o,idx){
              var picked=answer.indexOf(o.j)>=0;
              var correctOpt=(s.kind!=="multi"&&res.correct&&picked);
              if(picked)opts[idx].classList.add(res.correct?"right":"wrong");
            });
            var w=el("div","ll-why "+(res.correct?"ok":"no"));
            w.innerHTML="<b>"+(res.correct?"✅ Correct. ":"Not quite. ")+"</b>"+(res.why||"");
            stage.appendChild(w);
            var nb=el("button","ll-btn",res.last?"See results →":"Next →");
            nb.style.marginTop="16px";
            nb.addEventListener("click",function(){i++;res.last?done():step();});
            stage.appendChild(nb);
          }).catch(function(){opts.forEach(function(o){o.classList.remove("locked");});});
      }
      function done(){
        prog();stage.textContent="";
        var d=el("div","ll-done");
        d.appendChild(el("div","score",score+"/"+lab.steps.length));
        d.appendChild(el("h2",null,score===lab.steps.length?"Perfect run! 🏆":"Lab complete! 🎉"));
        d.appendChild(el("p",null,lab.done));
        var a1=el("a","p","🎓 Create a free account to save XP");a1.href="/academy/";
        var a2=el("a","s","⚡ Try another Lightning Lab");a2.href="#";
        a2.addEventListener("click",function(ev){ev.preventDefault();showList();});
        d.appendChild(a1);d.appendChild(a2);
        stage.appendChild(d);
      }
      intro();
    }).catch(function(){});
  }
})();
</script>
"""
