"""The BVTech Answers page (v1.103), served by the portal at /answers and
/answers/{id}. A self-contained, same-origin single page: it calls the portal's
own /api/answers/* (session-authenticated) and /api/academy/register +
/api/auth/login so people can join and sign in right here. Yahoo!-Answers in
spirit, tech-only in content, and every post is moderated server-side.
"""
from __future__ import annotations

import html as _html
import json as _json

from . import answers as _A

_CATS = _json.dumps([{"id": k, "label": v} for k, v in _A.CATEGORIES.items()])
_RANKS = _json.dumps([{"min": r[0], "name": r[1], "icon": r[2]} for r in _A.RANKS])


def page(initial_qid: int | None = None) -> str:
    return (r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BVTech Answers — Ask & help with tech, Microsoft 365, security & more</title>
<meta name="description" content="A friendly, moderated tech Q&A community by BVTech: ask about IT, Microsoft 365, cybersecurity, networking, small-business tech and more. Earn reputation and ranks. Free.">
<meta name="robots" content="index,follow">
<link rel="canonical" href="https://portal.bvtech.org/answers">
<style>
:root{--bg:#0E0D2C;--bg2:#13123A;--bg3:#1A1950;--o:#EB6F24;--o2:#F5BE58;--ac:#4440DB;--green:#26C485;
 --white:#fff;--text:rgba(255,255,255,.88);--muted:rgba(255,255,255,.52);--border:rgba(255,255,255,.1);
 --card:rgba(255,255,255,.04);--fh:'Poppins',system-ui,sans-serif;--fb:'Lato',system-ui,sans-serif}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:var(--fb);line-height:1.6}
a{color:var(--o2);text-decoration:none}a:hover{text-decoration:underline}
.top{position:sticky;top:0;z-index:20;background:rgba(14,13,44,.92);backdrop-filter:blur(10px);border-bottom:1px solid var(--border)}
.top .in{max-width:1100px;margin:0 auto;display:flex;align-items:center;gap:16px;padding:14px 18px}
.brand{font-family:var(--fh);font-weight:800;color:var(--white);font-size:1.15rem;white-space:nowrap}
.brand span{background:linear-gradient(90deg,var(--o),var(--o2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.top .sp{flex:1}
.top .lnk{color:var(--muted);font-size:.9rem;white-space:nowrap}
.chip{display:inline-flex;align-items:center;gap:8px;background:var(--card);border:1px solid var(--border);border-radius:999px;padding:5px 12px;font-size:.84rem;color:var(--text)}
.chip b{color:var(--o2)}
.btn{padding:10px 18px;border-radius:9px;border:0;background:var(--o);color:#0E0D2C;font-weight:800;cursor:pointer;font-family:inherit;font-size:.92rem}
.btn:hover{filter:brightness(1.05)}.btn.ghost{background:transparent;color:var(--white);border:1px solid var(--border)}
.btn[disabled]{opacity:.5;cursor:default}
.wrap{max-width:1100px;margin:0 auto;padding:24px 18px 80px;display:grid;grid-template-columns:230px 1fr;gap:26px}
@media(max-width:820px){.wrap{grid-template-columns:1fr}.side{order:2}}
.side h4{color:var(--muted);font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;margin:18px 0 8px}
.side a.cat{display:flex;justify-content:space-between;padding:8px 10px;border-radius:8px;color:var(--text);font-size:.9rem;cursor:pointer}
.side a.cat:hover,.side a.cat.on{background:var(--card);text-decoration:none;color:var(--o2)}
.tabs{display:flex;gap:6px;margin-bottom:16px;flex-wrap:wrap}
.tab{padding:7px 14px;border-radius:999px;border:1px solid var(--border);background:var(--card);color:var(--text);font-size:.85rem;cursor:pointer;font-weight:700}
.tab.on{background:linear-gradient(90deg,var(--o),var(--o2));color:#0E0D2C;border-color:transparent}
.q-card{display:flex;gap:16px;padding:18px;border:1px solid var(--border);border-radius:13px;background:var(--card);margin-bottom:12px;cursor:pointer}
.q-card:hover{border-color:var(--o)}
.q-stats{flex:0 0 64px;text-align:center;color:var(--muted);font-size:.74rem}
.q-stats b{display:block;color:var(--white);font-family:var(--fh);font-size:1.15rem;line-height:1.1}
.q-stats .solved{color:var(--green)}
.q-main h3{margin:0 0 6px;color:var(--white);font-size:1.08rem;line-height:1.35;font-family:var(--fh)}
.q-main .meta{color:var(--muted);font-size:.8rem}
.q-main .cat{color:var(--o2)}
.pill{display:inline-block;font-size:.68rem;font-weight:800;padding:2px 8px;border-radius:999px;background:rgba(38,196,133,.16);color:#6fe0b4;margin-left:6px}
.panel{border:1px solid var(--border);border-radius:14px;background:var(--card);padding:22px;margin-bottom:16px}
.panel h2{margin:0 0 10px;color:var(--white);font-family:var(--fh);font-size:1.4rem;line-height:1.3}
.vote{display:flex;flex-direction:column;align-items:center;gap:2px;flex:0 0 44px;color:var(--muted)}
.vote button{background:none;border:0;color:var(--muted);font-size:1.3rem;cursor:pointer;line-height:1;padding:2px}
.vote button:hover{color:var(--o)}.vote button.on{color:var(--o)}
.vote .n{color:var(--white);font-weight:800;font-family:var(--fh)}
.ans{display:flex;gap:14px;padding:18px 0;border-top:1px solid var(--border)}
.ans .body{flex:1;min-width:0}
.ans.best{background:rgba(38,196,133,.06);border-radius:10px;padding:18px;border:1px solid rgba(38,196,133,.3)}
.ans .who{color:var(--muted);font-size:.82rem;margin-top:10px}
.ans .who .rank{color:var(--o2);font-weight:700}
.best-btn{background:none;border:1px solid var(--border);color:var(--muted);border-radius:8px;padding:5px 10px;font-size:.78rem;cursor:pointer}
.best-btn:hover{border-color:var(--green);color:var(--green)}
.best-tag{color:var(--green);font-weight:800;font-size:.8rem}
textarea,input,select{width:100%;padding:12px 14px;border-radius:9px;border:1px solid var(--border);background:rgba(255,255,255,.04);color:var(--white);font-family:inherit;font-size:.96rem}
textarea{min-height:120px;resize:vertical}
label{display:block;color:var(--text);font-weight:700;font-size:.88rem;margin:12px 0 5px}
.err{color:#ff9b9d;background:rgba(229,72,77,.12);border:1px solid rgba(229,72,77,.35);border-radius:9px;padding:10px 13px;font-size:.88rem;margin:10px 0}
.ok{color:#6fe0b4;font-size:.88rem;margin:10px 0}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;align-items:flex-start;justify-content:center;z-index:50;padding:40px 16px;overflow:auto}
.modal.on{display:flex}
.modal .box{background:var(--bg2);border:1px solid var(--border);border-radius:16px;max-width:640px;width:100%;padding:26px}
.modal h3{margin:0 0 4px;color:var(--white);font-family:var(--fh)}
.muted{color:var(--muted);font-size:.85rem}
.rank-note{font-size:.78rem;color:var(--muted);margin-top:4px}
.sk{color:var(--muted);text-align:center;padding:40px 0}
.back{color:var(--muted);cursor:pointer;font-size:.9rem;display:inline-block;margin-bottom:14px}
.foot{max-width:1100px;margin:0 auto;padding:0 18px 50px;color:var(--muted);font-size:.8rem;text-align:center}
.prose{white-space:pre-wrap;word-wrap:break-word}
</style></head>
<body>
<div class="top"><div class="in">
  <a class="brand" href="/answers"><span>BVTech</span> Answers</a>
  <span class="lnk" style="margin-left:6px">by <a href="https://bvtech.org" target="_blank">BVTech</a></span>
  <div class="sp"></div>
  <div id="whoami"></div>
  <button class="btn" id="ask-btn">✦ Ask</button>
</div></div>

<div class="wrap">
  <aside class="side">
    <button class="btn" style="width:100%;margin-bottom:8px" id="ask-btn2">✦ Ask a question</button>
    <h4>Sort</h4>
    <div class="tabs" id="sorts">
      <button class="tab on" data-sort="new">Newest</button>
      <button class="tab" data-sort="active">Active</button>
      <button class="tab" data-sort="top">Top</button>
      <button class="tab" data-sort="unanswered">Unanswered</button>
    </div>
    <h4>Topics</h4>
    <div id="cats"></div>
    <h4>Ranks</h4>
    <div id="ranks" class="muted" style="font-size:.82rem;line-height:1.9"></div>
  </aside>

  <main id="main"><div class="sk">Loading…</div></main>
</div>
<div class="foot">Be kind, stay on-topic (tech!), and help each other out. Every post is automatically
moderated — no profanity, politics, spam or abuse. © BVTech LLC.</div>

<!-- Ask modal -->
<div class="modal" id="ask-modal"><div class="box">
  <h3>Ask the community</h3>
  <p class="muted">Clear, specific tech questions get the best answers. Keep it friendly.</p>
  <div id="ask-err"></div>
  <label>Title</label>
  <input id="ask-title" maxlength="160" placeholder="e.g. How do I enforce MFA for all Microsoft 365 users?">
  <label>Topic</label>
  <select id="ask-cat"></select>
  <label>Details <span class="muted">(optional)</span></label>
  <textarea id="ask-body" maxlength="6000" placeholder="Add any context: what you've tried, your setup, error messages…"></textarea>
  <div style="margin-top:16px;display:flex;gap:10px;justify-content:flex-end">
    <button class="btn ghost" id="ask-cancel">Cancel</button>
    <button class="btn" id="ask-submit">Post question</button>
  </div>
</div></div>

<!-- Auth modal -->
<div class="modal" id="auth-modal"><div class="box">
  <h3 id="auth-title">Join BVTech Answers</h3>
  <p class="muted">Free account — also unlocks the BVTech Academy, labs and leaderboards.</p>
  <div id="auth-err"></div>
  <div id="auth-name-wrap"><label>Display name</label><input id="auth-name" maxlength="40" placeholder="How you'll appear"></div>
  <label>Email</label><input id="auth-email" type="email" placeholder="you@email.com">
  <label>Password</label><input id="auth-pass" type="password" placeholder="At least 8 characters">
  <div style="margin-top:16px;display:flex;gap:10px;justify-content:space-between;align-items:center">
    <a id="auth-toggle" style="cursor:pointer;font-size:.86rem">Already have an account? Sign in</a>
    <button class="btn" id="auth-submit">Create account</button>
  </div>
</div></div>

<script>
const CATS=""" + _CATS + r""", RANKS=""" + _RANKS + r""";
const INITIAL_QID=""" + (str(initial_qid) if initial_qid else "null") + r""";
let ME={authed:false}, AUTH_MODE="register";
const $=(s)=>document.querySelector(s), main=$("#main");
function esc(s){const d=document.createElement("div");d.textContent=s==null?"":s;return d.innerHTML;}
function ago(iso){if(!iso)return"";const s=(Date.now()-new Date(iso))/1000;if(s<60)return"just now";if(s<3600)return Math.round(s/60)+"m ago";if(s<86400)return Math.round(s/3600)+"h ago";return Math.round(s/86400)+"d ago";}
async function api(path,opts){const r=await fetch("/api/answers"+path,Object.assign({headers:{"Content-Type":"application/json"}},opts||{}));let j={};try{j=await r.json();}catch(e){}if(!r.ok)throw (j&&j.detail)||("Error "+r.status);return j;}

// ---------- auth ----------
async function loadMe(){try{ME=await (await fetch("/api/answers/me")).json();}catch(e){ME={authed:false};}renderWho();}
function renderWho(){
  const w=$("#whoami");
  if(ME.authed){w.innerHTML='<span class="chip">'+ME.rank.icon+' <b>'+esc(ME.handle)+'</b> · '+ME.rep+' rep · '+esc(ME.rank.name)+'</span>';}
  else{w.innerHTML='<a class="lnk" id="signin" style="cursor:pointer">Sign in</a>';$("#signin").onclick=()=>openAuth("login");}
}
function openAuth(mode){AUTH_MODE=mode;$("#auth-err").innerHTML="";
  $("#auth-title").textContent=mode==="register"?"Join BVTech Answers":"Welcome back";
  $("#auth-name-wrap").style.display=mode==="register"?"block":"none";
  $("#auth-submit").textContent=mode==="register"?"Create account":"Sign in";
  $("#auth-toggle").textContent=mode==="register"?"Already have an account? Sign in":"New here? Create an account";
  $("#auth-modal").classList.add("on");}
$("#auth-toggle").onclick=()=>openAuth(AUTH_MODE==="register"?"login":"register");
$("#auth-submit").onclick=async()=>{
  const email=$("#auth-email").value.trim(),pass=$("#auth-pass").value,name=$("#auth-name").value.trim();
  $("#auth-err").innerHTML="";
  try{
    if(AUTH_MODE==="register"){await fetch("/api/academy/register",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password:pass,full_name:name})}).then(okJson);}
    else{await fetch("/api/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password:pass})}).then(okJson);}
    $("#auth-modal").classList.remove("on");await loadMe();
  }catch(e){$("#auth-err").innerHTML='<div class="err">'+esc(typeof e==="string"?e:"Could not sign in. Check your details.")+'</div>';}
};
async function okJson(r){let j={};try{j=await r.json();}catch(e){}if(!r.ok)throw (j&&j.detail)||"Failed";return j;}
function needAuth(){if(!ME.authed){openAuth("register");return false;}return true;}

// ---------- sidebar ----------
function buildSidebar(){
  const c=$("#cats");c.innerHTML='<a class="cat on" data-cat="">All topics</a>'+CATS.map(x=>'<a class="cat" data-cat="'+x.id+'">'+esc(x.label)+'</a>').join("");
  c.querySelectorAll(".cat").forEach(a=>a.onclick=()=>{c.querySelectorAll(".cat").forEach(z=>z.classList.remove("on"));a.classList.add("on");STATE.cat=a.dataset.cat;loadList();});
  $("#ranks").innerHTML=RANKS.map(r=>r.icon+" "+r.name+" <span style='color:var(--muted)'>· "+r.min+"+</span>").join("<br>");
  const sel=$("#ask-cat");sel.innerHTML=CATS.map(x=>'<option value="'+x.id+'">'+esc(x.label)+'</option>').join("");
}
let STATE={sort:"new",cat:""};
$("#sorts").querySelectorAll(".tab").forEach(t=>t.onclick=()=>{$("#sorts").querySelector(".on").classList.remove("on");t.classList.add("on");STATE.sort=t.dataset.sort;loadList();});

// ---------- list ----------
async function loadList(){
  history.replaceState(null,"","/answers");
  main.innerHTML='<div class="sk">Loading questions…</div>';
  let d;try{d=await api("/questions?sort="+STATE.sort+(STATE.cat?"&category="+STATE.cat:""));}catch(e){main.innerHTML='<div class="err">Could not load questions.</div>';return;}
  if(!d.questions.length){main.innerHTML='<div class="panel"><h2>No questions yet here</h2><p class="muted">Be the first to ask — help the community get started.</p></div>';return;}
  main.innerHTML='<div class="tabs" style="margin-bottom:6px"><div class="muted">'+d.total+' question'+(d.total===1?"":"s")+'</div></div>'+
    d.questions.map(q=>'<div class="q-card" data-id="'+q.id+'">'+
      '<div class="q-stats"><b>'+q.score+'</b>votes<div style="margin-top:8px"><b class="'+(q.solved?"solved":"")+'">'+q.answers+'</b>'+(q.solved?"✓ answers":"answers")+'</div></div>'+
      '<div class="q-main"><h3>'+esc(q.title)+(q.solved?'<span class="pill">SOLVED</span>':"")+'</h3>'+
      '<div class="meta"><span class="cat">'+esc(q.cat_label)+'</span> · asked by '+esc(q.by)+' · '+ago(q.at)+'</div></div></div>').join("");
  main.querySelectorAll(".q-card").forEach(c=>c.onclick=()=>openQ(c.dataset.id));
}

// ---------- detail ----------
async function openQ(id){
  history.replaceState(null,"","/answers/"+id);window.scrollTo(0,0);
  main.innerHTML='<div class="sk">Loading…</div>';
  let q;try{q=await api("/questions/"+id);}catch(e){main.innerHTML='<div class="err">Question not found.</div>';return;}
  const voteBox=(kind,tid,score,yv)=>'<div class="vote"><button class="up '+(yv===1?"on":"")+'" data-k="'+kind+'" data-t="'+tid+'" data-v="1">▲</button><span class="n">'+score+'</span><button class="down '+(yv===-1?"on":"")+'" data-k="'+kind+'" data-t="'+tid+'" data-v="-1">▼</button></div>';
  let html='<span class="back" id="back">← All questions</span>'+
    '<div class="panel"><div style="display:flex;gap:16px">'+voteBox("q",q.id,q.score,q.your_vote)+
    '<div style="flex:1;min-width:0"><div class="meta muted" style="margin-bottom:6px"><span style="color:var(--o2)">'+esc(q.cat_label)+'</span> · '+ago(q.at)+' · '+q.views+' views</div>'+
    '<h2>'+esc(q.title)+'</h2>'+(q.body?'<div class="prose">'+esc(q.body)+'</div>':"")+
    '<div class="muted" style="margin-top:10px">asked by <span style="color:var(--o2)">'+q.author.rank.icon+' '+esc(q.author.handle)+'</span> ('+esc(q.author.rank.name)+')</div></div></div></div>';
  html+='<h3 style="font-family:var(--fh);color:var(--white);margin:22px 0 8px">'+q.answers.length+' Answer'+(q.answers.length===1?"":"s")+'</h3>';
  html+='<div class="panel" style="padding:4px 18px">'+(q.answers.length?q.answers.map(a=>
    '<div class="ans '+(a.is_best?"best":"")+'">'+voteBox("a",a.id,a.score,a.your_vote)+
    '<div class="body"><div class="prose">'+esc(a.body)+'</div>'+
    '<div class="who">'+(a.is_best?'<span class="best-tag">✓ Best answer</span> · ':"")+'answered by <span class="rank">'+a.author.rank.icon+' '+esc(a.author.handle)+'</span> ('+esc(a.author.rank.name)+') · '+ago(a.at)+
    ((q.is_author&&!a.is_best)?' · <button class="best-btn" data-best="'+a.id+'">Mark best</button>':"")+'</div></div></div>').join(""):'<div class="sk">No answers yet — be the first!</div>')+'</div>';
  // answer composer
  html+='<div class="panel"><h3 style="margin:0 0 8px;color:var(--white);font-family:var(--fh)">Your answer</h3>'+
    '<div id="a-err"></div><textarea id="a-body" maxlength="6000" placeholder="Share what you know. Be specific and kind."></textarea>'+
    '<div style="margin-top:12px;text-align:right"><button class="btn" id="a-submit">Post your answer</button></div></div>';
  main.innerHTML=html;
  $("#back").onclick=loadList;
  main.querySelectorAll(".vote button").forEach(b=>b.onclick=()=>doVote(b,id));
  main.querySelectorAll(".best-btn").forEach(b=>b.onclick=()=>doBest(id,b.dataset.best));
  $("#a-submit").onclick=()=>doAnswer(id);
}
async function doVote(btn,qid){
  if(!needAuth())return;
  const k=btn.dataset.k,t=btn.dataset.t;let v=parseInt(btn.dataset.v);
  if(btn.classList.contains("on"))v=0;  // toggle off
  try{await api("/vote",{method:"POST",body:JSON.stringify({kind:k,target_id:+t,value:v})});openQ(qid);}
  catch(e){alert(typeof e==="string"?e:"Could not vote.");}
}
async function doBest(qid,rid){try{await api("/questions/"+qid+"/best",{method:"POST",body:JSON.stringify({reply_id:+rid})});openQ(qid);}catch(e){alert(e);}}
async function doAnswer(qid){
  if(!needAuth())return;
  const body=$("#a-body").value.trim();$("#a-err").innerHTML="";
  try{await api("/questions/"+qid+"/answers",{method:"POST",body:JSON.stringify({body})});await loadMe();openQ(qid);}
  catch(e){$("#a-err").innerHTML='<div class="err">'+esc(typeof e==="string"?e:"Could not post.")+'</div>';}
}

// ---------- ask ----------
function openAsk(){if(!needAuth())return;$("#ask-err").innerHTML="";$("#ask-title").value="";$("#ask-body").value="";$("#ask-modal").classList.add("on");}
$("#ask-btn").onclick=openAsk;$("#ask-btn2").onclick=openAsk;
$("#ask-cancel").onclick=()=>$("#ask-modal").classList.remove("on");
$("#ask-submit").onclick=async()=>{
  const title=$("#ask-title").value.trim(),body=$("#ask-body").value.trim(),category=$("#ask-cat").value;
  $("#ask-err").innerHTML="";
  try{const r=await api("/questions",{method:"POST",body:JSON.stringify({title,body,category})});$("#ask-modal").classList.remove("on");await loadMe();openQ(r.id);}
  catch(e){$("#ask-err").innerHTML='<div class="err">'+esc(typeof e==="string"?e:"Could not post.")+'</div>';}
};
document.querySelectorAll(".modal").forEach(m=>m.onclick=(e)=>{if(e.target===m)m.classList.remove("on");});

// ---------- boot ----------
buildSidebar();loadMe();
if(INITIAL_QID)openQ(INITIAL_QID);else loadList();
</script>
</body></html>""")
