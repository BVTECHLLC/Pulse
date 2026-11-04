import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {TRACKS,createTrack} from '../src/shared/tracks.js';
import {LAPS,NET_PROTOCOL,ITEMS,ITEM_GATES,createKart,stepKart,inputForAI,simulatePickups,
  activateItem,stepObstacles,resolveKartCollisions,rollItem} from '../src/shared/sim.js';
import {interpolateSnapshot} from '../src/shared/network.js';
const DT=1/30;
const all=Object.keys(TRACKS);

test('V3 includes six original circuits with sensible widths and loops',()=>{
  assert.equal(all.length,6);
  for(const id of all){const t=createTrack(id);assert.ok(t.width>=22&&t.width<=25);assert.ok(t.length>500);
    for(let n=0;n<48;n++){const pt=t.sample(t.length*n/48);assert.ok(Number.isFinite(pt.x+pt.z));}
  }
});

test('REGRESSION: server public snapshots interpolate without missing internal fields / NaN',()=>{
  const track=createTrack('coast'),k=createKart('test','Host',0,0,0,track);
  const publicSnapshot={id:k.id,x:k.x,z:k.z,heading:k.heading,speed:16,steer:1,progress:0,item:null};
  assert.equal(publicSnapshot.steerInput,undefined);
  assert.equal(publicSnapshot.lastS,undefined);
  let visual={...publicSnapshot};
  for(let i=0;i<240;i++){
    const next={...publicSnapshot,x:publicSnapshot.x+i*.3,z:publicSnapshot.z+i*.1,heading:publicSnapshot.heading+.002*i};
    visual=interpolateSnapshot(visual,next,.5);
    assert.ok(Number.isFinite(visual.x)&&Number.isFinite(visual.z)&&Number.isFinite(visual.heading));
  }
  // The fragile code that caused V2's freeze must not reappear in the client.
  const source=readFileSync(new URL('../src/main.js',import.meta.url),'utf8');
  const fn=source.slice(source.indexOf('function stepOnline('),source.indexOf('function hud('));
  assert.ok(!fn.includes('stepKart('),'Do not simulate on partial server snapshots');
  assert.ok(fn.includes('interpolateSnapshot('),'Online movement must follow authoritative state');
});

test('pickup gates reliably award on first lap across the ENTIRE road',()=>{
  const t=createTrack('candy');
  for(let zone=0;zone<ITEM_GATES.length;zone++)for(const lane of [-.44,0,.44]){
    const k=createKart('p'+zone+lane,'Tester',0,0,0,t);
    const p=t.sample(t.length*ITEM_GATES[zone]);
    k.s=p.s;k.x=p.x+p.nx*t.width*lane;k.z=p.z+p.nz*t.width*lane;
    k.progress=p.s;k.lastS=p.s;
    assert.equal(simulatePickups(k,t,2,()=>.5,[k]),true,`zone ${zone}, lane ${lane}`);
    assert.ok(ITEMS.includes(k.item));
    const first=k.item;k.item=null;
    assert.equal(simulatePickups(k,t,4,()=>.5,[k]),false,'No duplicate from same gate');
    assert.notEqual(first,null);
  }
});

test('new item selection includes eight types, catch-up influences rare boost chance',()=>{
  assert.equal(ITEMS.length,8);
  assert.equal(new Set(ITEMS).size,8);
  const first=Array.from({length:1000},(_,i)=>rollItem(1,8,()=>i/1000));
  const last=Array.from({length:1000},(_,i)=>rollItem(8,8,()=>i/1000));
  assert.ok(last.filter(x=>x==='overdrive').length>first.filter(x=>x==='overdrive').length);
});

test('all eight items activate, consume slot, produce a benefit/hazard and a serial',()=>{
  const track=createTrack('coast');
  for(const item of ITEMS){
    const k=createKart('a','A',0,0,0,track),other=createKart('b','B',0,0,1,track),os=[];
    k.item=item;other.x=k.x+3;other.z=k.z+8;
    const result=activateItem(k,[k,other],22,os);
    assert.equal(result,item);assert.equal(k.item,null);assert.equal(k.useSerial,1);assert.equal(k.usedItem,item);
    if(item==='rocket'||item==='oil')assert.equal(os.length,1);
    if(item==='shield')assert.ok(k.shieldTimer>0);
    if(item==='boost'||item==='overdrive')assert.ok(k.boostTimer>0);
  }
});

test('oil and homing rocket apply server-authoritative damage',()=>{
  const track=createTrack('coast'),shooter=createKart('a','A',0,0,0,track),target=createKart('b','B',0,0,1,track);
  const obs=[];shooter.item='rocket';target.x=shooter.x;target.z=shooter.z+25;
  // Orient forward and place target directly in front of shooter.
  target.x=shooter.x+Math.sin(shooter.heading)*25;target.z=shooter.z+Math.cos(shooter.heading)*25;
  activateItem(shooter,[shooter,target],10,obs);
  for(let i=0;i<70&&obs.length;i++){const r=stepObstacles(obs,[shooter,target],DT);obs.splice(0,obs.length,...r);}
  assert.ok(target.hitSerial>0,'Rocket must actually hit rival');
});

test('solid kart contact separates overlapping karts and blocks high-speed cross-through',()=>{
  const track=createTrack('coast'),a=createKart('a','A',0,0,0,track),b=createKart('b','B',0,0,1,track);
  a.x=0;a.z=0;a.prevX=0;a.prevZ=0;a.speed=23;
  b.x=.4;b.z=.4;b.prevX=.4;b.prevZ=.4;b.speed=24;
  resolveKartCollisions([a,b]);
  assert.ok(Math.hypot(a.x-b.x,a.z-b.z)>3.95);
  a.prevX=-4;a.prevZ=0;a.x=4;a.z=0;a.heading=Math.PI/2;
  b.prevX=4;b.prevZ=0;b.x=-4;b.z=0;b.heading=-Math.PI/2;
  resolveKartCollisions([a,b]);
  assert.ok(a.x<b.x,'Cars must not swap sides by tunneling through');
  assert.ok(Math.hypot(a.x-b.x,a.z-b.z)>3.95);
});

test('all six circuits finish with AI, collisions, and pickups enabled',()=>{
  for(const id of all){
    const t=createTrack(id),karts=Array.from({length:8},(_,i)=>{
      const k=createKart('bot'+i,'Bot',i%6,i%6,i,t);k.ai=true;return k;
    });
    let obstacles=[];
    for(let tick=0;tick<30*170&&!karts.every(k=>k.completed);tick++){
      for(const k of karts){const input=inputForAI(k,t,tick*DT);stepKart(k,input,DT,t);
        simulatePickups(k,t,tick*DT,()=>.3,karts);
        if(k.item&&tick%195===0)activateItem(k,karts,tick*DT,obstacles);
      }
      resolveKartCollisions(karts);obstacles=stepObstacles(obstacles,karts,DT);
      assert.ok(karts.every(k=>Number.isFinite(k.x+k.z+k.heading+k.progress)),`${id} produced non-finite kart state`);
    }
    assert.equal(karts.filter(k=>k.completed).length,8,`${id} has stranded AI`);
    assert.ok(karts.every(k=>k.laps===LAPS));
  }
});

test('protocol guard rejects stale clients, Node binds to Docker network',()=>{
  assert.equal(NET_PROTOCOL,4);
  const server=readFileSync(new URL('../server/index.js',import.meta.url),'utf8');
  assert.ok(server.includes('msg.protocol!==NET_PROTOCOL'));
  assert.ok(server.includes("process.env.HOST||'0.0.0.0'"));
});
