import {createTrack} from './tracks.js';
export const LAPS=3;
export const RACERS = [
  {id:'nova',name:'Nova',tag:'The comet',suit:0x39d8fa,helmet:0xe6faff,skin:0xdfad8b,style:'visor'},
  {id:'jax',name:'Jax',tag:'Street legend',suit:0xfd9d3c,helmet:0x222d43,skin:0x8e593e,style:'mohawk'},
  {id:'ivy',name:'Ivy',tag:'Precision pilot',suit:0x80e0a3,helmet:0x432f55,skin:0xf2cbab,style:'pony'},
  {id:'bolt',name:'Bolt',tag:'Retro rocket',suit:0xfcc94f,helmet:0xed504f,skin:0xc89471,style:'visor'},
  {id:'echo',name:'Echo',tag:'Midnight ace',suit:0xe47bea,helmet:0x293f83,skin:0xc79176,style:'visor'},
  {id:'rook',name:'Rook',tag:'The challenger',suit:0xeb7271,helmet:0xe8e8e9,skin:0x946d55,style:'cap'}
];
export const KART_COLORS=['#19d8fb','#fe9653','#85db9a','#f3cb5f','#ba90fc','#fb6e95'];
export const ITEMS = ['boost','pulse','shield','oil'];
export const normalizeAngle=(v)=>Math.atan2(Math.sin(v),Math.cos(v));
export const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
export function createKart(id,name,avatar=0,color=0,index=0,track=createTrack()){
  const p=track.sample(track.length-9-index*5.5), row=index%2===0?-2.8:2.8;
  return {id,name:String(name||'Racer').slice(0,16),avatar:avatar%RACERS.length,color:color%KART_COLORS.length,
    x:p.x+p.nx*row,z:p.z+p.nz*row,heading:Math.atan2(p.tx,p.tz),speed:0,steer:0,
    s:p.s,progress:0,laps:0,completed:false,finishTime:0,boostTimer:0,shieldTimer:0,spinTimer:0,
    invulnTimer:0,driftCharge:0,drifting:false,item:null,lastItemAt:0,lastS:p.s,
    ai:false,points:0,emote:'',emoteTimer:0};
}
export function inputForAI(k,track,seconds){
  const ahead=clamp(12+k.speed*.35,14,26), p=track.sample(k.s+ahead);
  const lane=Math.sin(seconds*.27+k.avatar*2.1)*1.5;
  const dx=p.x+p.nx*lane-k.x,dz=p.z+p.nz*lane-k.z;
  const error=normalizeAngle(Math.atan2(dx,dz)-k.heading);
  return {gas:true,brake:Math.abs(error)>.9,steer:clamp(error*2.7,-1,1),drift:Math.abs(error)>.22 && k.speed>16};
}
export function stepKart(k,input,dt,track){
  if(k.completed)return;
  dt=clamp(dt,0,.05);
  k.boostTimer=Math.max(0,k.boostTimer-dt);k.shieldTimer=Math.max(0,k.shieldTimer-dt);
  k.spinTimer=Math.max(0,k.spinTimer-dt);k.invulnTimer=Math.max(0,k.invulnTimer-dt);
  k.emoteTimer=Math.max(0,k.emoteTimer-dt);
  const nearestBefore=track.nearest(k.x,k.z), off=nearestBefore.distance>track.width*.48;
  const wasDrifting=k.drifting;
  k.drifting=!!input.drift && k.speed>9 && Math.abs(input.steer)>.13 && k.spinTimer===0;
  if(k.drifting)k.driftCharge=clamp(k.driftCharge+dt*(.7+Math.abs(input.steer)*.7),0,2.9);
  if(wasDrifting&&!k.drifting){if(k.driftCharge>.45)k.boostTimer=Math.max(k.boostTimer,Math.min(1.4,k.driftCharge*.46));k.driftCharge=0;}
  if(k.spinTimer>0){k.speed*=Math.max(0,1-2.2*dt);k.heading+=dt*7.6;}
  else {
    const boosted=k.boostTimer>0;
    const maxSpeed=boosted?45:32;
    const gas=!!input.gas,brake=!!input.brake;
    const acceleration=boosted?25:gas?18:brake?-30:-8;
    k.speed=clamp(k.speed+dt*(acceleration-(off?16:0)), -9,maxSpeed);
    if(!gas&&!brake&&Math.abs(k.speed)<.4)k.speed=0;
    if(off)k.speed*=Math.max(0,1-dt*.7);
    const steer=clamp(+input.steer||0,-1,1);
    k.steer=steer;
    const speedRatio=clamp(Math.abs(k.speed)/12,0,1);
    k.heading+=steer*(k.drifting?2.35:1.68)*speedRatio*dt*(k.speed<0?-1:1);
  }
  k.x+=Math.sin(k.heading)*k.speed*dt;
  k.z+=Math.cos(k.heading)*k.speed*dt;
  const closest=track.nearest(k.x,k.z), dist=closest.distance;
  if(dist>track.width*.59){
    const pull=clamp((dist-track.width*.5)*dt*.19,0,.11);
    k.x+=(closest.x-k.x)*pull;k.z+=(closest.z-k.z)*pull;
  }
  if(dist>track.width*1.35){
    k.x=closest.x+(k.x-closest.x)*(track.width*.7/dist);
    k.z=closest.z+(k.z-closest.z)*(track.width*.7/dist);
    k.speed=Math.min(k.speed,9);
  }
  // Continuity check prevents skipping sections of the circuit by cutting across nearby turns.
  let ds=closest.s-k.lastS;
  if(ds>track.length/2)ds-=track.length;
  if(ds<-track.length/2)ds+=track.length;
  const plausible=Math.abs(k.speed)*dt+1.5;
  // Cap implausible segment jumps without freezing tracking after one tight-corner projection.
  k.progress=Math.max(0,k.progress+clamp(ds,-plausible,plausible));
  k.lastS=closest.s;
  k.s=closest.s;
  k.laps=Math.min(LAPS,Math.floor((k.progress+0.001)/track.length));
  if(k.laps>=LAPS){k.completed=true;k.speed=0;}
}
export function hitKart(k){
  if(k.completed||k.invulnTimer>0)return false;
  if(k.shieldTimer>0){k.shieldTimer=0;k.invulnTimer=.8;return false;}
  k.spinTimer=1.45;k.invulnTimer=2.8;k.speed*=.42;k.drifting=false;k.driftCharge=0;return true;
}
export function simulatePickups(k,track,seconds){
  const cells=[.13,.31,.49,.67,.86];
  if(k.item||seconds-k.lastItemAt<4)return false;
  for(let i=0;i<cells.length;i++){
    let d=Math.abs(k.s-track.length*cells[i]);d=Math.min(d,track.length-d);
    if(d<3.2 && Math.abs(track.nearest(k.x,k.z).lateral)<track.width*.49){
      k.item=ITEMS[Math.floor(Math.random()*ITEMS.length)];k.lastItemAt=seconds;return true;
    }
  }
  return false;
}
export function activateItem(k,all,seconds,obstacles){
  if(!k.item||k.completed)return null;
  const used=k.item;k.item=null;
  if(used==='boost')k.boostTimer=3;
  else if(used==='shield')k.shieldTimer=7;
  else if(used==='pulse'){
    // Electric pulse strikes the nearest unshielded rival ahead or alongside.
    const targets=all.filter(o=>o.id!==k.id&&!o.completed&&Math.hypot(o.x-k.x,o.z-k.z)<40)
      .sort((a,b)=>Math.hypot(a.x-k.x,a.z-k.z)-Math.hypot(b.x-k.x,b.z-k.z));
    if(targets[0])hitKart(targets[0]);
  }else if(used==='oil'){
    obstacles.push({id:`o${Math.floor(seconds*1000)}-${k.id}`,x:k.x-Math.sin(k.heading)*4,z:k.z-Math.cos(k.heading)*4,owner:k.id,ttl:16});
  }
  return used;
}
export function rankings(karts){return [...karts].sort((a,b)=>a.completed&&b.completed?(a.finishTime||Infinity)-(b.finishTime||Infinity):a.completed?-1:b.completed?1:b.progress-a.progress);}
/** Resolve gentle kart bumping; authoritative host applies once per fixed simulation step. */
export function resolveKartCollisions(karts){
  for(let i=0;i<karts.length;i++)for(let j=i+1;j<karts.length;j++){
    const a=karts[i],b=karts[j];if(a.completed||b.completed)continue;
    let dx=b.x-a.x,dz=b.z-a.z,d=Math.hypot(dx,dz);
    if(d>=3.3)continue;
    if(d<.001){dx=1;dz=0;d=1;}
    const nx=dx/d,nz=dz/d,push=(3.3-d)*.42;
    a.x-=nx*push;a.z-=nz*push;b.x+=nx*push;b.z+=nz*push;
    a.speed*=.994;b.speed*=.994;
  }
}
