import * as THREE from 'three';
import {buildWorld} from './game/world.js';
import {createKartVisual,updateKartVisual,disposeKart} from './game/karts.js';
import {Sound} from './game/audio.js';
import {RaceFX} from './game/fx.js';
import {EffectComposer} from 'three/addons/postprocessing/EffectComposer.js';
import {RenderPass} from 'three/addons/postprocessing/RenderPass.js';
import {UnrealBloomPass} from 'three/addons/postprocessing/UnrealBloomPass.js';
import {TRACKS,createTrack} from './shared/tracks.js';
import {steeringFromControls} from './shared/input.js';
import {RACERS,KART_COLORS,createKart,stepKart,inputForAI,simulatePickups,activateItem,hitKart,resolveKartCollisions,rankings,LAPS,normalizeAngle} from './shared/sim.js';
import './style.css';

const $=s=>document.querySelector(s);
const state={name:'Racer',avatar:0,color:0,trackId:'coast',mode:'menu',phase:'menu',room:null,id:null,host:null,ws:null,players:[],targets:new Map(),visuals:new Map(),obstacles:[],
  track:createTrack('coast'),world:null,seconds:0,phaseStart:0,countdown:0,finishSeconds:0,lastCount:4,lastItem:null,aiOnly:false,quality:'high',cameraMode:0,
  keys:new Set(),mobile:{left:false,right:false,gas:false,brake:false,drift:false},itemQueued:false,localUser:null,soloClock:0,soloCountdown:0,
  onlineClock:0,lastSend:0,lastHud:0,lastMini:0,notice:'',effects:new Map(),fps:60,showBloom:false};
try{const s=JSON.parse(localStorage.getItem('volt-rush-settings')||'{}');state.name=s.name||'Racer';state.avatar=s.avatar||0;state.color=s.color||0;state.trackId=TRACKS[s.trackId]?s.trackId:'coast';}catch{}
const persist=()=>{try{localStorage.setItem('volt-rush-settings',JSON.stringify({name:state.name,avatar:state.avatar,color:state.color,trackId:state.trackId}));}catch{}};
const sound=new Sound();
const obstacleMeshes=new Map();
const previewKarts=[];
let driftParticles;
const driftPool=Array.from({length:90},()=>({x:0,y:-100,z:0,vx:0,vy:0,vz:0,life:0}));
const root=$('#app');root.innerHTML=`
<canvas id="viewport" aria-label="VOLT RUSH 3D racing track"></canvas>
<div id="vignette"></div>
<header id="brand"><div class="logo-mark">V<span>↗</span></div><div><strong>VOLT<span>RUSH</span></strong><small>BY BVTECH ARCADE</small></div></header>
<div id="topActions"><button class="circle-btn" id="audio" aria-label="Toggle sound">♫</button><button class="circle-btn" id="camera" title="Change camera" aria-label="Change camera">◉</button></div>
<section id="menu" class="panel-layout">
 <div class="intro"><div class="eyebrow"><i></i> THE NEXT LAP STARTS HERE</div><h1>OWN THE<br/><em>RACE.</em></h1><p>Precision drifting. Wild power-ups. Full-throttle racing with friends — anywhere, on any screen.</p>
 <div class="feature-pills"><span>◈ 3D WORLDS</span><span>⟁ LIVE ROOMS</span><span>⚡ TOUCH READY</span></div></div>
 <div class="menu-card glass"><div class="card-head"><span>01 / YOUR DRIVER</span><small>BUILD YOUR LEGEND</small></div>
  <input id="playerName" maxlength="16" placeholder="Your racer name" aria-label="Racer name" autocomplete="off"/>
  <div class="labelrow">PICK YOUR PILOT <span>6 ORIGINAL RACERS</span></div><div id="avatars" class="avatar-grid"></div>
  <div class="labelrow">KART FINISH</div><div id="colors" class="color-grid"></div>
  <div class="labelrow">CHOOSE YOUR CIRCUIT</div><div id="tracks" class="track-grid"></div>
  <button class="btn primary" id="solo">⚡ QUICK RACE <span>SOLO + AI</span></button>
  <div class="dual"><button class="btn secondary" id="host">HOST ONLINE ROOM</button><button class="btn secondary" id="joinShow">JOIN FRIEND</button></div>
  <div id="joinForm" class="join-row hidden"><input id="joinCode" maxlength="5" placeholder="ROOM CODE" aria-label="Race room code"/><button class="btn mini primary" id="join">JOIN →</button></div>
 </div>
</section>
<section id="lobby" class="modal-page hidden"><div class="glass dialog"><div class="eyebrow">PRIVATE MULTIPLAYER ROOM</div><h2>THE GRID IS <em>READY.</em></h2>
 <p>Invite friends with your room code. Each room supports up to eight human racers. Empty slots fill with AI when the host starts.</p>
 <div class="code-row"><div><small>YOUR ROOM CODE</small><div id="roomCode" class="room-code">—</div></div><button class="btn secondary" id="copy">COPY INVITE</button></div>
 <div class="labelrow">RACE LOBBY <span id="headcount">0 / 8 ONLINE</span></div><div id="roster" class="roster"></div>
 <div class="labelrow">CIRCUIT <span>HOST SELECTS</span></div><div id="lobbyTracks" class="lobby-tracks"></div>
 <button class="btn primary" id="raceGo">START RACE <span>3 LAPS</span></button><button class="text-button" id="backLobby">← LEAVE ROOM</button></div></section>
<section id="hud" class="hidden"><div class="hud-top"><div class="hud-pill race-meta"><small>POSITION</small><strong id="place">1<span>ST</span></strong></div><div class="hud-pill race-meta"><small>LAP</small><strong id="lap">1<span>/3</span></strong></div><div class="hud-pill timer"><small>RACE TIME</small><strong id="timer">00:00.0</strong></div><div class="hud-pill speed"><small>SPEED</small><strong id="speed">0 <span>KM/H</span></strong></div></div>
 <div id="status" class="race-status"></div><canvas id="minimap" width="230" height="190"></canvas>
 <div id="itemSlot" class="item-slot"><small>POWER-UP</small><strong id="itemText">—</strong><span>SHIFT / TAP</span></div>
 <div id="countdown" class="countdown hidden">3</div>
 <div class="touch-controls" id="touchControls"><div class="steering"><button class="touch" data-control="left" aria-label="Steer left">◀</button><button class="touch" data-control="right" aria-label="Steer right">▶</button></div><div class="actions"><button class="touch smallTouch" data-control="drift" aria-label="Drift">DRIFT</button><button class="touch itemTouch" data-control="item" aria-label="Use item">⚡</button><button class="touch smallTouch" data-control="brake" aria-label="Brake">BRAKE</button><button class="touch goTouch" data-control="gas" aria-label="Accelerate">GO</button></div></div>
 <div class="key-hint">↑ W ACCELERATE · ← → STEER · SPACE DRIFT · SHIFT ITEM · E CAMERA</div>
 <button class="hud-exit" id="leaveGame">EXIT RACE</button>
</section>
<section id="results" class="modal-page hidden"><div class="glass dialog"><div class="eyebrow">CHECKERED FLAG</div><h2 id="finishTitle">RACE <em>COMPLETE.</em></h2><p id="finishText">The finish line is yours.</p><div id="resultsBoard" class="results-board"></div>
 <button id="again" class="btn primary">RACE AGAIN</button><button id="returnMenu" class="text-button">← BACK TO MAIN MENU</button></div></section>
<div id="toast" class="toast hidden" role="status"></div>
<div id="rotateHint" aria-hidden="true">↻ Rotate your phone for the best racing view</div>
<footer id="footer">© BVTECH ARCADE · ORIGINAL CHARACTERS & WORLDS · v2.0</footer>`;

let renderer,scene,camera,composer=null,fx=null,clock=new THREE.Clock();
try{
  renderer=new THREE.WebGLRenderer({canvas:$('#viewport'),antialias:true,powerPreference:'high-performance',alpha:false});
  renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.45;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,Math.max(window.innerWidth<900?1.35:1.65,1)));
  renderer.shadowMap.enabled=window.innerWidth>1000;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
  state.quality=window.innerWidth>1100&&!matchMedia('(prefers-reduced-motion: reduce)').matches?'high':'low';scene=new THREE.Scene();
  camera=new THREE.PerspectiveCamera(68,window.innerWidth/window.innerHeight,.2,2000);
  renderer.setSize(window.innerWidth,window.innerHeight);
  // True bloom only on capable desktop layouts; lightweight emissive halos on phones.
  state.showBloom=state.quality==='high';
  if(state.showBloom){
    composer=new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene,camera));
    composer.addPass(new UnrealBloomPass(new THREE.Vector2(innerWidth,innerHeight),.32,.36,.84));
    composer.setSize(innerWidth,innerHeight);
  }
}catch(err){console.error(err);$('#menu').innerHTML='<div class="glass dialog"><h2>3D GRAPHICS UNAVAILABLE</h2><p>Enable WebGL in Safari or Chrome and try again. A recent iPhone, iPad or desktop browser is recommended.</p></div>';throw err;}
const resize=()=>{camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();renderer.setSize(innerWidth,innerHeight);renderer.setPixelRatio(Math.min(devicePixelRatio||1,innerWidth<900?1.35:1.65));composer?.setSize(innerWidth,innerHeight);};
window.addEventListener('resize',resize);
function toast(message){const el=$('#toast');el.textContent=message;el.classList.remove('hidden');clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.classList.add('hidden'),3800);}
function show(which){document.documentElement.dataset.screen=which;for(const id of ['menu','lobby','hud','results'])$('#'+id).classList.toggle('hidden',id!==which);$('#footer').classList.toggle('hidden',which!=='menu');$('#brand').classList.toggle('compact',which==='hud');}
function selectTrack(trackId){if(!TRACKS[trackId])return;state.trackId=trackId;persist();if(state.mode==='menu')loadWorld(trackId);renderSelections();}
function renderSelections(){
  $('#avatars').innerHTML=RACERS.map((a,i)=>`<button class="avatar ${i===state.avatar?'selected':''}" data-avatar="${i}" aria-label="Choose ${a.name}" aria-pressed="${i===state.avatar}"><div class="avatar-symbol" style="--avatar:${KART_COLORS[i]}">${['✦','⟡','☘','ϟ','◎','◇'][i]}</div><strong>${a.name}</strong><small>${a.tag}</small></button>`).join('');
  $('#colors').innerHTML=KART_COLORS.map((c,i)=>`<button class="swatch ${i===state.color?'selected':''}" data-color="${i}" style="--swatch:${c}" aria-label="Kart color ${i+1}" aria-pressed="${i===state.color}"></button>`).join('');
  $('#tracks').innerHTML=Object.entries(TRACKS).map(([id,t])=>`<button class="track-card ${id===state.trackId?'selected':''}" data-track="${id}"><strong>${t.name}</strong><span>${t.subtitle}</span></button>`).join('');
  $('#lobbyTracks').innerHTML=Object.entries(TRACKS).map(([id,t])=>`<button class="lobby-track ${id===state.trackId?'selected':''}" data-lobbytrack="${id}">${t.name}</button>`).join('');
}
$('#playerName').value=state.name;
$('#playerName').addEventListener('change',e=>{state.name=(e.target.value||'Racer').trim().slice(0,16);persist();});
$('#avatars').addEventListener('click',e=>{const b=e.target.closest('[data-avatar]');if(!b)return;state.avatar=+b.dataset.avatar;persist();renderSelections();});
$('#colors').addEventListener('click',e=>{const b=e.target.closest('[data-color]');if(!b)return;state.color=+b.dataset.color;persist();renderSelections();});
$('#tracks').addEventListener('click',e=>{const b=e.target.closest('[data-track]');if(b)selectTrack(b.dataset.track);});
$('#lobbyTracks').addEventListener('click',e=>{const b=e.target.closest('[data-lobbytrack]');if(!b||state.host!==state.id)return;state.ws?.send(JSON.stringify({type:'track',track:b.dataset.lobbytrack}));});
function readName(){state.name=($('#playerName').value||'Racer').replace(/[^\p{L}\p{N} _-]/gu,'').trim().slice(0,16)||'Racer';$('#playerName').value=state.name;persist();}
$('#solo').onclick=()=>{readName();sound.initialize();startSolo();};
$('#host').onclick=()=>{readName();sound.initialize();connectOnline({type:'create',name:state.name,avatar:state.avatar,color:state.color,track:state.trackId});};
$('#joinShow').onclick=()=>{$('#joinForm').classList.toggle('hidden');$('#joinCode').focus();};
$('#join').onclick=()=>{readName();const code=$('#joinCode').value.toUpperCase().trim();if(code.length!==5){toast('Enter the five-character room code.');return;}sound.initialize();connectOnline({type:'join',room:code,name:state.name,avatar:state.avatar,color:state.color});};
$('#joinCode').onkeydown=e=>{if(e.key==='Enter')$('#join').click();};
$('#raceGo').onclick=()=>{if(state.host===state.id)state.ws?.send(JSON.stringify({type:'start'}));};
$('#copy').onclick=async()=>{const url=new URL(location.href);url.searchParams.set('room',state.room);try{await navigator.clipboard.writeText(url.toString());toast('Invite link copied!');}catch{toast('Room code: '+state.room);}};
$('#backLobby').onclick=()=>exitToMenu();$('#leaveGame').onclick=()=>exitToMenu();$('#returnMenu').onclick=()=>exitToMenu();
$('#again').onclick=()=>{if(state.mode==='solo'){startSolo();}else if(state.host===state.id){state.ws?.send(JSON.stringify({type:'rematch'}));show('lobby');}else{show('lobby');toast('Waiting for the host to start the next race.');}};
$('#camera').onclick=()=>{state.cameraMode=(state.cameraMode+1)%3;toast(['Chase camera','Wide camera','Bumper camera'][state.cameraMode]);};
$('#audio').onclick=()=>{$('#audio').textContent=sound.mute()?'♫':'♪̸';if(sound.enabled)sound.initialize();};
const params=new URLSearchParams(location.search);if(params.has('room')){$('#joinCode').value=String(params.get('room')).slice(0,5).toUpperCase();$('#joinForm').classList.remove('hidden');}

function itemEffect(k,type,audio=true){
  if(!k||!type)return;
  if(audio)sound.play(type);
  fx?.burst(type,k.x,k.z,type==='oil'?.7:1.6,type==='boost'?55:38,type==='pulse'?1.4:1);
  if(type==='shield')fx?.ring('shield',k.x,k.z,2.2);
}
function hitEffect(k,audio=false){if(!k)return;fx?.burst('hit',k.x,k.z,1.3,40,1.1);if(audio)sound.play('hit');}
function recordEffects(players,phase){
  if(phase!=='racing'){state.effects.clear();return;}
  for(const k of players){
    const old=state.effects.get(k.id);
    if(old){
      if(!old.item&&k.item){fx?.burst('boost',k.x,k.z,2.6,15,.35);if(k.id===state.id)sound.play('pickup');}
      if(old.item&&!k.item)itemEffect(k,old.item,k.id===state.id);
      else if(k.shieldTimer>old.shieldTimer+1)itemEffect(k,'shield',k.id===state.id);
      else if(k.boostTimer>old.boostTimer+1)itemEffect(k,'boost',k.id===state.id);
      if(k.spinTimer>old.spinTimer+.75)hitEffect(k,k.id===state.id);
    }
    state.effects.set(k.id,{item:k.item,shieldTimer:k.shieldTimer,boostTimer:k.boostTimer,spinTimer:k.spinTimer});
  }
}
function clearVisuals(){for(const p of previewKarts){scene.remove(p.mesh);disposeKart(p.mesh);}previewKarts.length=0;for(const m of obstacleMeshes.values()){scene.remove(m);m.geometry.dispose();m.material.dispose();}obstacleMeshes.clear();for(const v of state.visuals.values()){scene.remove(v);disposeKart(v);}state.visuals.clear();state.targets.clear();}
function loadWorld(id){
  if(state.world)state.world.dispose();clearVisuals();state.track=createTrack(id);state.world=buildWorld(scene,state.track,state.quality);
  if(state.mode==='menu')for(let i=0;i<4;i++){
    const a=(state.avatar+i)%RACERS.length,k=createKart('demo'+i,RACERS[a].name,a,(state.color+i)%6,0,state.track);
    const mesh=createKartVisual(k,true);scene.add(mesh);previewKarts.push({kart:k,mesh,offset:i*15});
  }
}

function spawnVisuals(){
  for(const p of previewKarts){scene.remove(p.mesh);disposeKart(p.mesh);}previewKarts.length=0;
  for(const k of state.players){if(!state.visuals.has(k.id)){const v=createKartVisual(k,k.id===state.id);state.visuals.set(k.id,v);scene.add(v);}}
  for(const [id,v]of state.visuals)if(!state.players.some(k=>k.id===id)){scene.remove(v);disposeKart(v);state.visuals.delete(id);}
}
function connectOnline(msg){
  if(state.ws){state.ws.close();state.ws=null;}
  state.mode='online';toast('Connecting to the race server…');
  const proto=location.protocol==='https:'?'wss:':'ws:';
  const ws=new WebSocket(proto+'//'+location.host+'/kart/ws');state.ws=ws;
  ws.onopen=()=>{ws.send(JSON.stringify(msg));};
  ws.onmessage=event=>{
    let data;try{data=JSON.parse(event.data);}catch{return;}
    if(data.type==='welcome')state.id=data.id;
    else if(data.type==='joined'){state.room=data.room;state.id=data.id;toast('Room connected!');}
    else if(data.type==='error'){toast(data.message);if(state.phase==='menu'){ws.close();state.mode='menu';}}
    else if(data.type==='state')receiveState(data);
    else if(data.type==='left')exitToMenu();
  };
  ws.onerror=()=>toast('Connection failed. Check the multiplayer server and HTTPS.');
  ws.onclose=()=>{if(state.ws!==ws)return;state.ws=null;if(state.mode==='online'){toast('Disconnected from the race server.');exitToMenu(false);}};
}
function receiveState(data){
  if(state.mode!=='online')return;
  if(data.track!==state.track.id)loadWorld(data.track);
  const oldPhase=state.phase;
  state.phase=data.phase;state.host=data.host;state.room=data.room;state.seconds=data.seconds;state.countdown=data.countdown;state.obstacles=data.obstacles||[];state.finishSeconds=data.finishSeconds;
  state.players=data.players;
  recordEffects(data.players,data.phase);
  if(data.phase==='lobby'){
    show('lobby');$('#roomCode').textContent=state.room;$('#headcount').textContent=`${data.players.length} / 8 ONLINE`;
    $('#roster').innerHTML=data.players.map(k=>`<div class="roster-person"><span class="roster-dot" style="background:${KART_COLORS[k.color]}"></span><strong>${escapeText(k.name)}</strong><small>${k.id===state.host?'HOST':'READY'}</small></div>`).join('');
    state.trackId=data.track;renderSelections();
    $('#raceGo').classList.toggle('hidden',state.host!==state.id);
    [...$('#lobbyTracks').children].forEach(b=>{b.disabled=state.host!==state.id;});
  }else if(data.phase==='countdown'||data.phase==='racing'){
    if(oldPhase==='lobby'||oldPhase==='menu'||oldPhase==='finished'){
      state.targets.clear();state.lastCount=4;show('hud');toast(TRACKS[data.track].name+' · 3 LAPS');
    }
    for(const k of data.players){
      const prev=state.targets.get(k.id);
      if(prev){const current=prev.current;if(k.id===state.id&&data.phase==='racing'){
        const oldX=current.x,oldZ=current.z,oldHeading=current.heading;
        Object.assign(current,k);
        current.x=oldX*.46+k.x*.54;current.z=oldZ*.46+k.z*.54;
        current.heading=oldHeading+normalizeAngle(k.heading-oldHeading)*.54;
      }else if(k.id===state.id){Object.assign(current,k);}
      prev.target={...k};
      }else state.targets.set(k.id,{current:{...k},target:{...k}});
    }
    spawnVisuals();
    if(data.phase==='countdown'){const next=Math.max(0,Math.ceil(data.countdown-.5));$('#countdown').classList.remove('hidden');$('#countdown').textContent=next>0?next:'GO!';if(next!==state.lastCount){state.lastCount=next;sound.play(next>0?'tick':'go');}}
    else {$('#countdown').classList.add('hidden');if(oldPhase==='countdown'&&state.lastCount>0)sound.play('go');}
  }else if(data.phase==='finished'&&oldPhase!=='finished'){showResults(data.players);}
}
const escapeText=(s)=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function startSolo(){
  state.mode='solo';state.id='local';state.host='local';state.phase='countdown';state.seconds=0;state.finishSeconds=0;state.soloClock=0;state.soloCountdown=3.5;state.lastCount=4;state.obstacles=[];
  loadWorld(state.trackId);
  state.players=[];
  const own=createKart('local',state.name,state.avatar,state.color,0,state.track);state.players.push(own);
  for(let i=0;i<7;i++){const avatar=(i+state.avatar+1)%RACERS.length;
    const ai=createKart('cpu'+i,RACERS[avatar].name+' AI',avatar,(i+1)%6,i+1,state.track);ai.ai=true;state.players.push(ai);
  }
  state.targets.clear();state.effects.clear();for(const k of state.players)state.targets.set(k.id,{current:k,target:k});
  spawnVisuals();show('hud');toast('3 LAPS · '+TRACKS[state.track.id].name);
}
function exitToMenu(close=true){
  if(close&&state.ws){state.ws.close();state.ws=null;}
  state.mode='menu';state.phase='menu';state.room=null;state.id=null;state.obstacles=[];state.players=[];state.effects.clear();
  state.keys.clear();Object.keys(state.mobile).forEach(k=>state.mobile[k]=false);state.itemQueued=false;
  loadWorld(state.trackId);show('menu');
}
function showResults(players){
  if(state.phase!=='finished')state.phase='finished';
  const standings=rankings(players),me=standings.findIndex(k=>k.id===state.id),winner=standings[0];
  $('#finishTitle').innerHTML=me===0?'YOU <em>DOMINATED.</em>':'RACE <em>COMPLETE.</em>';
  $('#finishText').textContent=me===0?'The podium belongs to you.':`${winner?.name||'A racer'} takes the win. Refuel and try again.`;
  $('#resultsBoard').innerHTML=standings.map((k,i)=>`<div class="result-person ${k.id===state.id?'me':''}"><b>${String(i+1).padStart(2,'0')}</b><span class="roster-dot" style="background:${KART_COLORS[k.color]}"></span><strong>${escapeText(k.name)}</strong><small>${k.completed?formatTime(k.finishTime):'DNF'}</small></div>`).join('');
  $('#again').textContent=state.mode==='solo'?'RESTART QUICK RACE':state.host===state.id?'SET UP REMATCH':'WAIT FOR HOST';
  $('#again').disabled=state.mode==='online'&&state.host!==state.id;
  sound.play('finish');for(const racer of players.slice(0,8))fx?.burst('finish',racer.x,racer.z,3.2,54,1.65);show('results');
}
function formatTime(t){const m=Math.floor(t/60),s=Math.floor(t%60),ds=Math.floor((t%1)*10);return String(m).padStart(2,'0')+':'+String(s).padStart(2,'0')+'.'+ds;}
function getInput(){return {
  gas:state.mobile.gas||state.keys.has('ArrowUp')||state.keys.has('KeyW'),
  brake:state.mobile.brake||state.keys.has('ArrowDown')||state.keys.has('KeyS'),
  steer:steeringFromControls(state.keys,state.mobile),
  drift:state.mobile.drift||state.keys.has('Space'),item:state.itemQueued
};}
const controlCodes=new Set(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','KeyW','KeyA','KeyS','KeyD','Space','ShiftLeft','ShiftRight']);
window.addEventListener('keydown',e=>{
  if(document.activeElement?.tagName==='INPUT')return;
  if(controlCodes.has(e.code))e.preventDefault();
  state.keys.add(e.code);
  if(['ShiftLeft','ShiftRight'].includes(e.code)&&!e.repeat)state.itemQueued=true;
  if(e.code==='KeyE'&&!e.repeat)$('#camera').click();
  if(e.code==='KeyM'&&!e.repeat)$('#audio').click();
  if(e.code==='Escape'&&state.phase==='racing')exitToMenu();
});
window.addEventListener('keyup',e=>state.keys.delete(e.code));
window.addEventListener('blur',()=>{state.keys.clear();Object.keys(state.mobile).forEach(k=>state.mobile[k]=false);});
for(const b of document.querySelectorAll('.touch')){
  const key=b.dataset.control;
  const press=e=>{e.preventDefault();if(key==='item')state.itemQueued=true;else state.mobile[key]=true;b.classList.add('pressed');try{b.setPointerCapture(e.pointerId);}catch{}};
  const release=e=>{e.preventDefault();if(key!=='item')state.mobile[key]=false;b.classList.remove('pressed');};
  b.addEventListener('pointerdown',press);b.addEventListener('pointerup',release);b.addEventListener('pointercancel',release);b.addEventListener('lostpointercapture',release);
}
function stepSolo(dt){
  if(state.phase==='countdown'){
    state.soloCountdown-=dt;
    const count=Math.max(0,Math.ceil(state.soloCountdown-.5));
    $('#countdown').classList.remove('hidden');$('#countdown').textContent=count||'GO!';
    if(count!==state.lastCount){state.lastCount=count;sound.play(count>0?'tick':'go');}
    if(state.soloCountdown<=0){state.phase='racing';$('#countdown').classList.add('hidden');}
    return;
  }
  if(state.phase!=='racing')return;
  state.seconds+=dt;
  const input=getInput();
  for(const k of state.players){
    const control=k.ai?inputForAI(k,state.track,state.seconds):input;
    stepKart(k,control,dt,state.track);
    const oldItem=k.item;
    simulatePickups(k,state.track,state.seconds);
    if(!oldItem&&k.item&&k.id===state.id){sound.play('pickup');fx?.burst('boost',k.x,k.z,2.7,12,.35);}
    if(control.item&&k.item){const used=activateItem(k,state.players,state.seconds,state.obstacles);itemEffect(k,used,k.id===state.id);}
    if(k.ai&&k.item&&Math.random()<dt*.2){const used=activateItem(k,state.players,state.seconds,state.obstacles);itemEffect(k,used,false);}
    if(k.completed&&!k.finishTime)k.finishTime=state.seconds;
  }
  resolveKartCollisions(state.players);
  if(input.item)state.itemQueued=false;
  for(const o of state.obstacles){o.ttl-=dt;for(const k of state.players){if(k.id!==o.owner&&Math.hypot(k.x-o.x,k.z-o.z)<2.6){if(hitKart(k))hitEffect(k,k.id===state.id);o.ttl=0;break;}}}
  state.obstacles=state.obstacles.filter(o=>o.ttl>0);
  if(!state.finishSeconds&&state.players.some(k=>k.completed))state.finishSeconds=state.seconds;
  if((state.finishSeconds&&state.seconds-state.finishSeconds>24)||state.players.every(k=>k.completed)||state.seconds>450)showResults(state.players);
}
function stepOnline(dt,t){
  if(state.phase==='countdown'){
    state.countdown=Math.max(0,state.countdown-dt);
    const count=Math.max(0,Math.ceil(state.countdown-.5));
    $('#countdown').textContent=count||'GO!';
    if(count!==state.lastCount){state.lastCount=count;sound.play(count>0?'tick':'go');}
    return;
  }
  if(state.phase!=='racing')return;
  const input=getInput(),me=state.targets.get(state.id);
  if(me)stepKart(me.current,input,dt,state.track);
  for(const [id,p]of state.targets){
    if(id===state.id)continue;
    const k=p.current,targ=p.target;
    const f=Math.min(1,dt*11);
    k.x+=(targ.x-k.x)*f;k.z+=(targ.z-k.z)*f;k.heading+=normalizeAngle(targ.heading-k.heading)*f;
    Object.assign(k,{speed:targ.speed,drifting:targ.drifting,boostTimer:targ.boostTimer,shieldTimer:targ.shieldTimer,spinTimer:targ.spinTimer,steer:targ.steer,item:targ.item});
  }
  if(t-state.lastSend>.05){
    if(state.ws?.readyState===WebSocket.OPEN){state.ws.send(JSON.stringify({type:'input',...input}));}
    state.lastSend=t;state.itemQueued=false;
  }
}
function hud(time){
  if(time-state.lastHud<.09)return;state.lastHud=time;
  const me=(state.mode==='online'?state.targets.get(state.id)?.current:state.players.find(k=>k.id===state.id));
  if(!me)return;
  const place=rankings(state.players).findIndex(k=>k.id===state.id)+1;
  $('#place').innerHTML=place+`<span>${place===1?'ST':place===2?'ND':place===3?'RD':'TH'}</span>`;
  $('#lap').innerHTML=Math.min(LAPS,me.laps+1)+`<span>/${LAPS}</span>`;
  $('#timer').textContent=formatTime(state.seconds);$('#speed').innerHTML=Math.round(Math.abs(me.speed)*7)+` <span>KM/H</span>`;
  const item=me.item;$('#itemText').textContent= item?({boost:'⚡ TURBO',pulse:'✦ PULSE',shield:'⬡ SHIELD',oil:'◈ OIL'}[item]):'EMPTY';
  $('#itemSlot').classList.toggle('charged',!!item);
  $('#status').textContent=me.drifting?'DRIFT CHARGING · '+Math.round(me.driftCharge*100)+'%':me.boostTimer>0?'⚡ TURBO BOOST':me.spinTimer>0?'HIT! RECOVERING':'';
  sound.update(me.speed);
}
function minimap(t){
  if(t-state.lastMini<.12)return;state.lastMini=t;
  const c=$('#minimap'),ctx=c.getContext('2d');if(!ctx)return;ctx.clearRect(0,0,230,190);
  const xs=state.track.samples.map(p=>p.x),zs=state.track.samples.map(p=>p.z);
  const minX=Math.min(...xs)-16,maxX=Math.max(...xs)+16,minZ=Math.min(...zs)-16,maxZ=Math.max(...zs)+16;
  const scale=Math.min(210/(maxX-minX),163/(maxZ-minZ));
  const project=(x,z)=>[115+(x-(minX+maxX)/2)*scale,96+(z-(minZ+maxZ)/2)*scale];
  ctx.lineCap='round';ctx.lineJoin='round';ctx.beginPath();state.track.samples.forEach((p,i)=>{const [x,y]=project(p.x,p.z);i?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.strokeStyle='#1f3453';ctx.lineWidth=11;ctx.stroke();ctx.strokeStyle='#b4c6d6';ctx.lineWidth=5;ctx.stroke();
  for(const k of state.players){const p=state.mode==='online'?state.targets.get(k.id)?.current:k;if(!p)continue;
    const [x,y]=project(p.x,p.z);ctx.beginPath();ctx.arc(x,y,k.id===state.id?5:3.4,0,Math.PI*2);ctx.fillStyle=k.id===state.id?'#ffffff':KART_COLORS[k.color];ctx.fill();if(k.id===state.id){ctx.strokeStyle='#42f5e8';ctx.lineWidth=2;ctx.stroke();}}
}
const driftGeo=new THREE.BufferGeometry();
const driftData=new Float32Array(driftPool.length*3);driftGeo.setAttribute('position',new THREE.BufferAttribute(driftData,3));
driftParticles=new THREE.Points(driftGeo,new THREE.PointsMaterial({color:0xffd36b,size:.48,transparent:true,opacity:.95,depthWrite:false}));
driftParticles.frustumCulled=false;scene.add(driftParticles);fx=new RaceFX(scene,state.quality);
let renderedTime=0,frames=0,fpsTime=0;
function animate(){
  requestAnimationFrame(animate);const dt=Math.min(clock.getDelta(),.05);renderedTime+=dt;
  if(state.mode==='solo')stepSolo(dt);
  if(state.mode==='online')stepOnline(dt,renderedTime);
  state.world?.update(renderedTime);
  fpsTime+=dt;frames++;
  if(fpsTime>3){state.fps=frames/fpsTime;frames=0;fpsTime=0;
    if(state.fps<49){const pr=renderer.getPixelRatio(),min=innerWidth<900?.9:1.05;
      if(pr>min+.08){renderer.setPixelRatio(Math.max(min,pr-.2));composer?.setPixelRatio(renderer.getPixelRatio());}
      if(state.showBloom&&state.fps<43){state.showBloom=false;}
    }
  }
  fx?.update(dt);
  if(previewKarts.length){
    for(const p of previewKarts){const spot=state.track.sample((renderedTime*21+p.offset)%state.track.length);
      p.kart.x=spot.x;p.kart.z=spot.z;p.kart.heading=Math.atan2(spot.tx,spot.tz);p.kart.speed=21;
      updateKartVisual(p.mesh,p.kart,dt,renderedTime);
    }
  }
  if(state.obstacles.length){
    for(const o of state.obstacles){if(!obstacleMeshes.has(o.id)){
      const geo=new THREE.CylinderGeometry(2,2,.08,18);
      const mat=new THREE.MeshStandardMaterial({color:0x141725,metalness:.65,roughness:.25,emissive:0x2c1a4b,emissiveIntensity:.38});
      const mesh=new THREE.Mesh(geo,mat);mesh.position.set(o.x,.1,o.z);scene.add(mesh);obstacleMeshes.set(o.id,mesh);
    }}
  }
  for(const [id,m] of obstacleMeshes){if(!state.obstacles.some(o=>o.id===id)){scene.remove(m);m.geometry.dispose();m.material.dispose();obstacleMeshes.delete(id);}}
  if(state.phase==='racing'||state.phase==='countdown'){
    for(const k of state.players){const v=state.visuals.get(k.id);const r=state.mode==='online'?state.targets.get(k.id)?.current:k;
      if(v&&r){updateKartVisual(v,r,dt,renderedTime);if(r.boostTimer>0||r.drifting)fx?.trail(r);}
    }
    const me=state.mode==='online'?state.targets.get(state.id)?.current:state.players.find(k=>k.id===state.id);
    if(me){
      const hd=me.heading;const wide=state.cameraMode===1,bumper=state.cameraMode===2;
      const back=bumper?-1.1:wide?20:13,height=bumper?2.7:wide?12:8.7,look=bumper?17:8;
      const goal=new THREE.Vector3(me.x-Math.sin(hd)*back,height,me.z-Math.cos(hd)*back);
      camera.position.lerp(goal,Math.min(1,dt*6));
      const focus=new THREE.Vector3(me.x+Math.sin(hd)*look,bumper?2.8:3.15,me.z+Math.cos(hd)*look);
      const target=focus;camera.lookAt(target);
      camera.fov+=( (68+Math.max(0,me.speed-22)*.45)-camera.fov)*Math.min(1,dt*2.5);camera.updateProjectionMatrix();
      if(state.phase==='racing')hud(renderedTime);
      minimap(renderedTime);
      for(let i=0;i<driftPool.length;i++){
        const p=driftPool[i];p.life-=dt;
        if(p.life<=0&&me.drifting&&Math.random()<.19){p.life=.3+Math.random()*.65;p.x=me.x-Math.sin(me.heading)*1.8+(Math.random()-.5)*2.5;p.z=me.z-Math.cos(me.heading)*1.8+(Math.random()-.5)*2.5;p.y=.55;p.vx=(Math.random()-.5)*4;p.vz=(Math.random()-.5)*4;p.vy=2+Math.random()*3;}
        if(p.life>0){p.x+=p.vx*dt;p.z+=p.vz*dt;p.y+=p.vy*dt;p.vy-=dt*11;}
        driftData[i*3]=p.life>0?p.x:0;driftData[i*3+1]=p.life>0?p.y:-999;driftData[i*3+2]=p.life>0?p.z:0;
      }
      driftGeo.attributes.position.needsUpdate=true;
    }
  }else{
    const p=state.track.sample(state.track.length*.035),radius=38;
    const a=renderedTime*.085;const goal=new THREE.Vector3(p.x+Math.sin(a)*radius,17,p.z+Math.cos(a)*radius);
    camera.position.lerp(goal,Math.min(1,dt*1.4));camera.lookAt(p.x,1,p.z);camera.fov+=(63-camera.fov)*Math.min(1,dt*2);camera.updateProjectionMatrix();
  }
  if(state.showBloom&&composer)composer.render();else renderer.render(scene,camera);
}
loadWorld(state.trackId);renderSelections();show('menu');animate();
