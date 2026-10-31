import test from 'node:test';
import assert from 'node:assert/strict';
import {createTrack,TRACKS} from '../src/shared/tracks.js';
import {createKart,inputForAI,stepKart,hitKart,activateItem,resolveKartCollisions,rankings} from '../src/shared/sim.js';

test('every circuit is a closed, sampleable and nonzero 3D track',()=>{
  for(const id of Object.keys(TRACKS)){
    const track=createTrack(id);
    assert.ok(track.length>300);
    const a=track.sample(0),b=track.sample(track.length);
    assert.ok(Math.hypot(a.x-b.x,a.z-b.z)<.01);
    assert.ok(track.nearest(a.x,a.z).distance<.01);
    assert.ok(track.sample(track.length*.52).tx!==undefined);
  }
});
test('vehicle speed is capped and controls accelerate it',()=>{
  const t=createTrack('coast'),k=createKart('1','Test',0,0,0,t);
  for(let i=0;i<100;i++)stepKart(k,{gas:true,steer:0},1/30,t);
  assert.ok(k.speed>0&&k.speed<=32);
});
test('boost, shield and collision mechanics work',()=>{
  const t=createTrack('coast'),a=createKart('1','A',0,0,0,t),b=createKart('2','B',0,1,1,t);
  a.item='shield';activateItem(a,[a,b],1,[]);assert.ok(a.shieldTimer>6);
  assert.equal(hitKart(a),false);assert.equal(a.spinTimer,0);
  b.item='boost';activateItem(b,[a,b],1,[]);assert.ok(b.boostTimer>2);
  b.x=a.x;b.z=a.z;resolveKartCollisions([a,b]);assert.ok(Math.hypot(a.x-b.x,a.z-b.z)>0);
  assert.equal(rankings([b,a]).length,2);
});
test('AI navigator continues making forward progress on the circuit',()=>{
  const t=createTrack('coast'),k=createKart('bot','Test AI',0,1,0,t);
  for(let i=0;i<30*65;i++)stepKart(k,inputForAI(k,t,i/30),1/30,t);
  assert.ok(k.progress>t.length*.7,`AI advanced ${k.progress.toFixed(1)} of ${t.length.toFixed(1)} units`);
});
