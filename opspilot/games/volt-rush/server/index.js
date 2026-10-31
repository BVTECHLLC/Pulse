import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {WebSocketServer,WebSocket} from 'ws';
import {createTrack,TRACKS} from '../src/shared/tracks.js';
import {createKart,inputForAI,stepKart,simulatePickups,activateItem,hitKart,resolveKartCollisions,rankings,LAPS,RACERS} from '../src/shared/sim.js';

const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const DIST=path.join(ROOT,'dist');
const PORT=Number(process.env.PORT)||3108;
const MAX_ROOMS=80,MAX_CLIENTS=150;
const rooms=new Map(), peers=new Map(), ipCounts=new Map();
const cleanName=v=>String(v||'Guest').replace(/[^\p{L}\p{N} _-]/gu,'').trim().slice(0,16)||'Guest';
const randCode=()=>Array.from({length:5},()=> 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'[Math.floor(Math.random()*32)]).join('');
const json=(ws,data)=>{if(ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify(data));};
const publicKart=(k)=>({id:k.id,name:k.name,avatar:k.avatar,color:k.color,x:+k.x.toFixed(3),z:+k.z.toFixed(3),heading:+k.heading.toFixed(3),speed:+k.speed.toFixed(2),steer:+k.steer.toFixed(2),s:+k.s.toFixed(2),progress:+k.progress.toFixed(2),laps:k.laps,completed:k.completed,finishTime:k.finishTime,boostTimer:k.boostTimer,shieldTimer:k.shieldTimer,spinTimer:k.spinTimer,driftCharge:k.driftCharge,drifting:k.drifting,item:k.item,ai:k.ai,emote:k.emoteTimer>0?k.emote:''});
const state=r=>({type:'state',room:r.code,track:r.trackId,host:r.host,phase:r.phase,countdown:r.phase==='countdown'?Math.max(0,(r.countdownEnd-Date.now())/1000):0,seconds:r.seconds,laps:LAPS,players:r.players.map(publicKart),obstacles:r.obstacles,finishSeconds:r.finishSeconds});
function broadcast(r,payload){for(const id of r.connections){const ws=peers.get(id)?.ws;if(ws)json(ws,payload);}}
function roster(r){broadcast(r,state(r));}
function createRoom(ws,id,msg){
  if(rooms.size>=MAX_ROOMS)return json(ws,{type:'error',message:'The arcade is busy. Please try again.'});
  let code;do{code=randCode()}while(rooms.has(code));
  const trackId=TRACKS[msg.track]?msg.track:'coast',track=createTrack(trackId);
  const r={code,trackId,track,host:id,phase:'lobby',connections:new Set([id]),players:[createKart(id,cleanName(msg.name),Number(msg.avatar)||0,Number(msg.color)||0,0,track)],inputs:new Map(),seconds:0,countdownEnd:0,finishSeconds:0,obstacles:[],lastActive:Date.now(),tick:0};
  rooms.set(code,r);const peer=peers.get(id);peer.room=code;
  json(ws,{type:'joined',id,room:code});roster(r);
}
function joinRoom(ws,id,msg){
  const code=String(msg.room||'').toUpperCase().replace(/[^A-Z2-9]/g,'').slice(0,5),r=rooms.get(code);
  if(!r)return json(ws,{type:'error',message:'Room not found. Check the five-character code.'});
  if(r.phase!=='lobby')return json(ws,{type:'error',message:'This race has started. Ask the host for the next round.'});
  if(r.connections.size>=8)return json(ws,{type:'error',message:'That race room is full.'});
  r.connections.add(id);const k=createKart(id,cleanName(msg.name),Number(msg.avatar)||0,Number(msg.color)||0,r.players.length,r.track);
  r.players.push(k);peers.get(id).room=code;
  json(ws,{type:'joined',id,room:code});roster(r);
}
function resetGrid(r){
  r.track=createTrack(r.trackId);r.obstacles=[];r.seconds=0;r.finishSeconds=0;
  r.players=r.players.filter(k=>!k.ai).map((k,i)=>createKart(k.id,k.name,k.avatar,k.color,i,r.track));
  const wanted=8-r.players.length;
  for(let i=0;i<wanted;i++){
    let a=(i+2)%RACERS.length;const k=createKart('bot'+i,RACERS[a].name+' AI',a,(i+3)%6,r.players.length,r.track);
    k.ai=true;r.players.push(k);
  }
  r.inputs.clear();
}
function startRace(r){if(r.phase!=='lobby')return;resetGrid(r);r.phase='countdown';r.countdownEnd=Date.now()+3500;broadcast(r,state(r));}
function leaveRoom(id){
  const peer=peers.get(id);if(!peer?.room)return;
  const r=rooms.get(peer.room);peer.room=null;if(!r)return;
  r.connections.delete(id);r.players=r.players.filter(k=>k.id!==id);r.inputs.delete(id);
  if(!r.connections.size){rooms.delete(r.code);return;}
  if(r.host===id)r.host=[...r.connections][0];r.lastActive=Date.now();roster(r);
}
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.json':'application/json','.webmanifest':'application/manifest+json','.png':'image/png','.ico':'image/x-icon','.woff2':'font/woff2'};
const app=http.createServer((req,res)=>{
  const url=new URL(req.url||'/',`http://${req.headers.host||'localhost'}`);
  if(url.pathname==='/kart/health'){res.writeHead(200,{'content-type':'application/json','cache-control':'no-store'});return res.end(JSON.stringify({ok:true,rooms:rooms.size,connections:peers.size,uptime:Math.round(process.uptime())}));}
  if(!url.pathname.startsWith('/kart')){res.writeHead(404);return res.end('Not found');}
  let sub=url.pathname.slice('/kart'.length);
  if(!sub||sub==='/')sub='/index.html';
  let file=path.resolve(DIST,'.'+decodeURIComponent(sub));
  if(!file.startsWith(DIST+path.sep)){res.writeHead(403);return res.end('Forbidden');}
  if(!fs.existsSync(file)||!fs.statSync(file).isFile()){
    if(!sub.includes('.'))file=path.join(DIST,'index.html');
    else {res.writeHead(404);return res.end('Not found');}
  }
  if(!fs.existsSync(file)){res.writeHead(503);return res.end('Run npm run build first.');}
  res.writeHead(200,{'content-type':types[path.extname(file)]||'application/octet-stream',
    'cache-control':file.includes('/assets/')?'public,max-age=31536000,immutable':'no-cache',
    'x-content-type-options':'nosniff','referrer-policy':'strict-origin-when-cross-origin'});
  fs.createReadStream(file).pipe(res);
});
const wss=new WebSocketServer({noServer:true,maxPayload:800,perMessageDeflate:false});
app.on('upgrade',(req,socket,head)=>{
  let pathname;try{pathname=new URL(req.url||'/',`http://${req.headers.host}`).pathname;}catch{socket.destroy();return;}
  if(pathname!=='/kart/ws'||peers.size>=MAX_CLIENTS){socket.destroy();return;}
  // Same-site browser Origin enforcement. Explicit override for controlled reverse-proxy setups.
  const origin=req.headers.origin,host=String(req.headers['x-forwarded-host']||req.headers.host||'').split(',')[0].trim();
  if(origin){try{if(new URL(origin).host!==host && process.env.ALLOW_CROSS_ORIGIN!=='true' && !(process.env.NODE_ENV!=='production' && ['localhost','127.0.0.1'].includes(new URL(origin).hostname))){socket.destroy();return;}}catch{socket.destroy();return;}}
  const ip=String(req.headers['x-real-ip']||req.socket.remoteAddress||'unknown').slice(0,100);
  if((ipCounts.get(ip)||0)>=6){socket.destroy();return;}
  wss.handleUpgrade(req,socket,head,ws=>{ws.ip=ip;wss.emit('connection',ws,req);});
});
let nextId=1;
wss.on('connection',ws=>{
  const id='p'+(nextId++).toString(36);peers.set(id,{ws,room:null,input:{},lastMsg:0});ipCounts.set(ws.ip,(ipCounts.get(ws.ip)||0)+1);
  ws.isAlive=true;ws.on('pong',()=>{ws.isAlive=true;});json(ws,{type:'welcome',id});
  ws.on('message',buf=>{
    let msg;try{msg=JSON.parse(String(buf));}catch{return;}
    if(typeof msg!=='object'||!msg||typeof msg.type!=='string')return;
    const peer=peers.get(id);if(!peer)return;
    const now=Date.now();if(msg.type==='input'){
      if(now-peer.lastMsg<25)return;peer.lastMsg=now;
      const r=rooms.get(peer.room);if(!r||r.phase!=='racing')return;
      r.inputs.set(id,{gas:!!msg.gas,brake:!!msg.brake,drift:!!msg.drift,
        steer:Math.max(-1,Math.min(1,Number.isFinite(msg.steer)?msg.steer:0)),item:!!msg.item});
      return;
    }
    if(['create','join'].includes(msg.type)){
      if(peer.room)leaveRoom(id);
      if(msg.type==='create')createRoom(ws,id,msg);else joinRoom(ws,id,msg);
      return;
    }
    const r=rooms.get(peer.room);if(!r)return;
    if(msg.type==='leave'){leaveRoom(id);json(ws,{type:'left'});}
    else if(msg.type==='track'&&id===r.host&&r.phase==='lobby'&&TRACKS[msg.track]){r.trackId=msg.track;r.track=createTrack(msg.track);roster(r);}
    else if(msg.type==='start'&&id===r.host)startRace(r);
    else if(msg.type==='rematch'&&id===r.host&&r.phase==='finished'){
      r.phase='lobby';r.players=r.players.filter(k=>!k.ai);roster(r);
    }
    else if(msg.type==='emote'){
      const k=r.players.find(k=>k.id===id);
      if(k&&['gg','wow','nice'].includes(msg.emote)){k.emote=msg.emote;k.emoteTimer=2;}
    }
  });
  ws.on('close',()=>{leaveRoom(id);peers.delete(id);ipCounts.set(ws.ip,Math.max(0,(ipCounts.get(ws.ip)||1)-1));});
  ws.on('error',()=>{});
});
// Fixed timestep to avoid fast machines producing faster karts; no player-supplied position data.
let last=Date.now(),acc=0;
setInterval(()=>{
  const now=Date.now(),frame=Math.min(.15,(now-last)/1000);last=now;acc+=frame;
  while(acc>=1/30){
    for(const r of rooms.values()){
      if(r.phase==='countdown'&&now>=r.countdownEnd){r.phase='racing';r.seconds=0;broadcast(r,state(r));}
      if(r.phase!=='racing')continue;
      const dt=1/30;r.seconds+=dt;
      for(const k of r.players){
        const input=k.ai?inputForAI(k,r.track,r.seconds):r.inputs.get(k.id)||{};
        stepKart(k,input,dt,r.track);
        simulatePickups(k,r.track,r.seconds);
        if(input.item) {activateItem(k,r.players,r.seconds,r.obstacles);if(!k.ai)r.inputs.set(k.id,{...input,item:false});}
        if(k.ai&&k.item&&Math.random()<.007)activateItem(k,r.players,r.seconds,r.obstacles);
        if(k.completed&&!k.finishTime)k.finishTime=r.seconds;
      }
      resolveKartCollisions(r.players);
      for(const o of r.obstacles){o.ttl-=dt;for(const k of r.players){if(o.owner!==k.id&&Math.hypot(k.x-o.x,k.z-o.z)<2.6){hitKart(k);o.ttl=0;break;}}}
      r.obstacles=r.obstacles.filter(o=>o.ttl>0);
      if(!r.finishSeconds&&r.players.some(k=>k.completed))r.finishSeconds=r.seconds;
      if((r.finishSeconds&&r.seconds-r.finishSeconds>24)||r.players.every(k=>k.completed)||r.seconds>450){
        r.phase='finished';broadcast(r,state(r));
      }
    }
    acc-=1/30;
  }
  for(const r of rooms.values())if(r.phase==='racing'&&++r.tick%3===0)broadcast(r,state(r));
},1000/30);
setInterval(()=>{
  for(const client of wss.clients){if(!client.isAlive){client.terminate();continue;}client.isAlive=false;client.ping();}
  for(const [code,r] of rooms)if(!r.connections.size||Date.now()-r.lastActive>12*60*60*1000)rooms.delete(code);
},30000).unref();
app.listen(PORT,process.env.HOST||'0.0.0.0',()=>console.log(`VOLT RUSH ready: port ${PORT}`));
