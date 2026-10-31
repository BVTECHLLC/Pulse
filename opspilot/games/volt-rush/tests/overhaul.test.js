import test from 'node:test';
import assert from 'node:assert/strict';
import {TRACKS,createTrack} from '../src/shared/tracks.js';
import {steeringFromControls} from '../src/shared/input.js';
import {createKart,stepKart,inputForAI,normalizeAngle,LAPS} from '../src/shared/sim.js';
const T=1/30;
const mobileEmpty={left:false,right:false};

test('keyboard and mobile agree: right = +1, left = -1, both = neutral',()=>{
  for(const key of ['ArrowRight','KeyD'])assert.equal(steeringFromControls(new Set([key]),mobileEmpty),1);
  for(const key of ['ArrowLeft','KeyA'])assert.equal(steeringFromControls(new Set([key]),mobileEmpty),-1);
  assert.equal(steeringFromControls(new Set(),{left:false,right:true}),1);
  assert.equal(steeringFromControls(new Set(),{left:true,right:false}),-1);
  assert.equal(steeringFromControls(new Set(['ArrowLeft']),{left:false,right:true}),0);
});

test('steering moves to the correct side of the chase camera',()=>{
  const track=createTrack('coast');
  const probe=(steer)=>{
    const k=createKart(`steer${steer}`,'Steer',0,0,0,track);
    for(let i=0;i<30;i++)stepKart(k,{gas:true,steer:0},T,track);
    const old={x:k.x,z:k.z,heading:k.heading};
    for(let i=0;i<9;i++)stepKart(k,{gas:true,steer},T,track);
    const right={x:-Math.cos(old.heading),z:Math.sin(old.heading)};
    return {lateral:(k.x-old.x)*right.x+(k.z-old.z)*right.z,delta:normalizeAngle(k.heading-old.heading)};
  };
  const right=probe(1),left=probe(-1);
  assert.ok(right.lateral>0.4,`Right must move screen-right; actual ${right.lateral}`);
  assert.ok(left.lateral<-.4,`Left must move screen-left; actual ${left.lateral}`);
  assert.ok(right.delta<0,`Right command must turn clockwise in chase view`);
  assert.ok(left.delta>0,`Left command must turn counter-clockwise in chase view`);
});

test('circuits are 20–24 units wide, have safe line edges',()=>{
  for(const [id,t] of Object.entries(TRACKS)){
    assert.ok(t.width>=20&&t.width<=24,`${id} width ${t.width}`);
    const track=createTrack(id);
    for(let i=0;i<track.samples.length;i+=12){
      const p=track.samples[i];assert.ok(Number.isFinite(p.x)&&Number.isFinite(p.z));
    }
  }
});

test('all 3 AI circuits complete 3 full laps with updated steering',()=>{
  for(const id of Object.keys(TRACKS)){
    const track=createTrack(id),k=createKart(`bot-${id}`,'Robot',1,2,0,track);
    for(let tick=0;tick<30*170&&!k.completed;tick++){
      const input=inputForAI(k,track,tick*T);stepKart(k,input,T,track);
    }
    assert.equal(k.completed,true,`${id}: AI stuck at ${k.progress.toFixed(1)} / ${(LAPS*track.length).toFixed(1)}`);
    assert.equal(k.laps,LAPS);
  }
});
