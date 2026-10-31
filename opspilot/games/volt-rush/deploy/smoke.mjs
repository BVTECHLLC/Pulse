// Run AFTER npm install, npm run build, and starting the game server.
import {WebSocket} from 'ws';
import assert from 'node:assert/strict';
const port=process.env.PORT||3108,endpoint=`ws://127.0.0.1:${port}/kart/ws`;
const health=await fetch(`http://127.0.0.1:${port}/kart/health`);
assert.equal(health.status,200,'health endpoint failed');
assert.equal((await health.json()).ok,true);
const page=await fetch(`http://127.0.0.1:${port}/kart/`);
assert.equal(page.status,200);assert.ok((await page.text()).includes('VOLT RUSH'));
function client(){return new Promise((resolve,reject)=>{
  const ws=new WebSocket(endpoint,{headers:{Origin:`http://127.0.0.1:${port}`}}),messages=[];
  ws.on('open',()=>resolve({ws,messages,send:m=>ws.send(JSON.stringify(m))}));ws.on('error',reject);
  ws.on('message',buf=>{try{messages.push(JSON.parse(buf.toString()));}catch{}});
});}
async function until(c,fn,timeout=5500){const start=Date.now();while(Date.now()-start<timeout){const msg=c.messages.find(fn);if(msg)return msg;await new Promise(r=>setTimeout(r,30));}throw new Error('Timed out waiting for server state');}
const host=await client();host.send({type:'create',name:'Host Smoke',avatar:0,color:1,track:'neon'});
const j=await until(host,m=>m.type==='joined');const code=j.room;assert.equal(code.length,5);
const friend=await client();friend.send({type:'join',name:'Friend Smoke',room:code,avatar:2,color:3});
await until(friend,m=>m.type==='joined');await until(host,m=>m.type==='state'&&m.players?.length===2);
host.send({type:'start'});
await until(friend,m=>m.type==='state'&&m.phase==='countdown');
await until(host,m=>m.type==='state'&&m.phase==='racing'&&m.players?.length===8,6000);
friend.send({type:'input',gas:true,steer:.3,drift:false});
console.log(`PASS: HTTP, 2-client WebSocket room ${code}, roster, countdown, AI filling, racing inputs`);
host.ws.close();friend.ws.close();
