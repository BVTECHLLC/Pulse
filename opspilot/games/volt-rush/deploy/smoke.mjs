/** Real two-human-client full-race smoke test.
 * Start: npm run build && node server/index.js (separate terminal)
 * Test: npm run smoke (runs for up to ~150 s at real racing speed)
 * Both human sockets send ordinary control inputs; server simulates all positions.
 */
import {WebSocket} from 'ws';
import assert from 'node:assert/strict';
import {createTrack} from '../src/shared/tracks.js';
import {inputForAI} from '../src/shared/sim.js';

const PORT=process.env.PORT||3108,origin=`http://127.0.0.1:${PORT}`,endpoint=`ws://127.0.0.1:${PORT}/kart/ws`;
const health=await fetch(origin+'/kart/health');assert.equal(health.status,200);
assert.equal((await health.json()).ok,true);
const page=await fetch(origin+'/kart/');assert.equal(page.status,200);
assert.ok((await page.text()).includes('VOLT RUSH'));
function client(){return new Promise((resolve,reject)=>{
  const ws=new WebSocket(endpoint,{headers:{Origin:origin}}),c={ws,messages:[],latest:null,id:null,send(msg){if(ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify(msg));}};
  ws.on('open',()=>resolve(c));ws.on('error',reject);
  ws.on('message',buf=>{try{const m=JSON.parse(buf.toString());c.messages.push(m);if(c.messages.length>80)c.messages.shift();if(m.type==='state')c.latest=m;if(m.type==='welcome')c.id=m.id;}catch{}});
});}
async function until(c,fn,timeout=8500){const start=Date.now();while(Date.now()-start<timeout){const msg=c.messages.find(fn);if(msg)return msg;await new Promise(r=>setTimeout(r,30));}throw Error('Timed out waiting for '+fn.toString());}
const host=await client(),friend=await client();let run;
try{
  await until(host,m=>m.type==='welcome');await until(friend,m=>m.type==='welcome');
  host.send({type:'create',name:'Host Smoke',avatar:0,color:1,track:'coast'});
  const j=await until(host,m=>m.type==='joined');assert.equal(j.room.length,5);
  friend.send({type:'join',name:'Friend Smoke',room:j.room,avatar:2,color:3});
  await until(friend,m=>m.type==='joined');await until(host,m=>m.type==='state'&&m.players.length===2);
  host.send({type:'start'});
  await until(host,m=>m.type==='state'&&m.phase==='countdown');
  await until(friend,m=>m.type==='state'&&m.phase==='racing'&&m.players.length===8,9000);
  const circuit=createTrack('coast');let positions=0,movedA=false,movedB=false;
  // Inputs from two HUMAN WebSockets, using the same shared steering helper the bots use.
  run=setInterval(()=>{
    for(const c of [host,friend]){
      const s=c.latest;
      if(s?.phase!=='racing')continue;
      const k=s.players.find(p=>p.id===c.id);if(!k||k.completed)continue;
      const input=inputForAI(k,circuit,s.seconds);
      c.send({type:'input',gas:true,brake:input.brake,steer:input.steer,drift:input.drift,item:!!k.item,
        // The server MUST ignore forged client coordinates even if supplied.
        x:999999,z:999999,progress:999999});
      assert.ok(Math.abs(k.x)<1000&&Math.abs(k.z)<1000,'Server must be authoritative');
      if(k.progress>30){if(c===host)movedA=true;else movedB=true;}
      positions++;
    }
  },60);
  const limit=Date.now()+165000;
  while(Date.now()<limit){
    if(host.latest?.phase==='finished'&&friend.latest?.phase==='finished')break;
    await new Promise(r=>setTimeout(r,250));
  }
  assert.equal(host.latest?.phase,'finished','Server must finish a full race');
  assert.equal(friend.latest?.phase,'finished','Both human clients must receive final results');
  assert.ok(movedA&&movedB,'Both human sockets must drive forward');
  assert.ok(host.latest.players.some(k=>k.completed),'At least one racer must finish 3 laps');
  for(const c of [host,friend])assert.ok(host.latest.players.find(k=>k.id===c.id)?.completed,`Human ${c.id} must finish all 3 laps`);
  assert.equal(host.latest.players.length,8,'2 humans + 6 AI racers');
  console.log(`PASS: 2 human room sockets, inputs, ${positions} control ticks, 3-lap racing, authoritative state, final standings, HTTP health.`);
}finally{clearInterval(run);host.ws.close();friend.ws.close();}
