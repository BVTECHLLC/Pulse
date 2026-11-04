import {createTrack} from './tracks.js';
export const LAPS=3;
export const NET_PROTOCOL=4;
export const RACERS = [
  {id:'nova',name:'Nova',tag:'The comet',suit:0x39d8fa,helmet:0xe6faff,skin:0xdfad8b,style:'visor'},
  {id:'jax',name:'Jax',tag:'Street legend',suit:0xfd9d3c,helmet:0x222d43,skin:0x8e593e,style:'mohawk'},
  {id:'ivy',name:'Ivy',tag:'Precision pilot',suit:0x80e0a3,helmet:0x432f55,skin:0xf2cbab,style:'pony'},
  {id:'bolt',name:'Bolt',tag:'Retro rocket',suit:0xfcc94f,helmet:0xed504f,skin:0xc89471,style:'visor'},
  {id:'echo',name:'Echo',tag:'Midnight ace',suit:0xe47bea,helmet:0x293f83,skin:0xc79176,style:'visor'},
  {id:'rook',name:'Rook',tag:'The challenger',suit:0xeb7271,helmet:0xe8e8e9,skin:0x946d55,style:'cap'}
];
export const KART_COLORS=['#19d8fb','#fe9653','#85db9a','#f3cb5f','#ba90fc','#fb6e95'];
export const ITEMS = ['boost','pulse','shield','oil','rocket','shockwave','repair','overdrive'];
export const ITEM_GATES = [.13,.31,.49,.67,.86];
// Catch-up balance without hiding races behind powerful guaranteed hits.
const ITEM_WEIGHTS = {boost:16,pulse:12,shield:15,oil:12,rocket:11,shockwave:8,repair:13,overdrive:6};
export function rollItem(placing=1,total=8,rng=Math.random){
  const behind=total>1?clamp((placing-1)/(total-1),0,1):0;
  const weights=ITEMS.map(id=>{let w=ITEM_WEIGHTS[id];if(['boost','overdrive','rocket'].includes(id))w*=.8+behind*1.7;if(id==='oil')w*=1.5-behind*.9;if(id==='repair'||id==='shield')w*=.85+behind*.5;return w;});
  let t=clamp(Number(rng())||0,0,.999999)*weights.reduce((a,b)=>a+b,0);
  for(let i=0;i<weights.length;i++){t-=weights[i];if(t<0)return ITEMS[i];}
  return ITEMS[0];
}
export const normalizeAngle=(v)=>Math.atan2(Math.sin(v),Math.cos(v));
export const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
export function createKart(id,name,avatar=0,color=0,index=0,track=createTrack()){
  const p=track.sample(track.length-9-index*5.5), row=index%2===0?-2.8:2.8;
  return {id,name:String(name||'Racer').slice(0,16),avatar:avatar%RACERS.length,color:color%KART_COLORS.length,
    x:p.x+p.nx*row,z:p.z+p.nz*row,heading:Math.atan2(p.tx,p.tz),speed:0,steer:0,
    s:p.s,progress:0,laps:0,completed:false,finishTime:0,boostTimer:0,shieldTimer:0,spinTimer:0,
    invulnTimer:0,driftCharge:0,drifting:false,item:null,lastItemAt:-100,lastPickupKey:null,lastS:p.s,steerInput:0,
    overdriveTimer:0,itemSerial:0,useSerial:0,usedItem:null,hitSerial:0,prevX:p.x+p.nx*row,prevZ:p.z+p.nz*row,
    ai:false,points:0,emote:'',emoteTimer:0};
}
export function inputForAI(k,track,seconds,all=[]){
  const ahead=clamp(12+k.speed*.35,14,26), p=track.sample(k.s+ahead);
  // Each bot holds its own racing lane so they fan out instead of stacking on one line.
  const lane=Math.sin(seconds*.45+k.avatar*2.1)*2.3 + (((k.avatar%3)-1)*1.6);
  const dx=p.x+p.nx*lane-k.x,dz=p.z+p.nz*lane-k.z;
  // Local avoidance: steer away from any rival that's close, so bots don't grind on each other.
  let avoid=0, crowdedAhead=false;
  for(let i=0;i<all.length;i++){
    const o=all[i]; if(!o||o.id===k.id||o.completed)continue;
    const rx=o.x-k.x,rz=o.z-k.z,dd=Math.hypot(rx,rz);
    if(dd<8){
      const side=rx*Math.cos(k.heading)-rz*Math.sin(k.heading);   // >0 => rival on my right
      const fwd =rx*Math.sin(k.heading)+rz*Math.cos(k.heading);   // >0 => rival ahead of me
      avoid += (side>0?-1:1)*(1-dd/8)*(fwd>0?1.25:.5);
      if(fwd>0 && dd<5.2) crowdedAhead=true;
    }
  }
  const error=normalizeAngle(Math.atan2(dx,dz)-k.heading);
  // Steering convention: +1 is RIGHT as seen from the rear chase camera.
  let steer=clamp(-error*2.35 + avoid*1.35, -1, 1);
  // Unstick: if a bot is pinned near-stationary while trying to drive, reverse and
  // turn out of the jam for a moment (brake with ~0 speed reverses in stepKart).
  k.aiStuck = (Math.abs(k.speed)<2.4) ? ((k.aiStuck||0)+1) : 0;
  if(k.aiStuck>16){
    if(k.aiStuck>52) k.aiStuck=0;   // give the forward plan another shot after ~1.2s
    const out = avoid!==0 ? Math.sign(avoid) : (k.avatar%2?1:-1);
    return {gas:false,brake:true,steer:clamp(out,-1,1),drift:false};
  }
  return {gas:true,brake:Math.abs(error)>1.2,steer,drift:!crowdedAhead && Math.abs(error)>.34 && k.speed>22};
}
export function stepKart(k,input,dt,track){
  if(k.completed)return;
  dt=clamp(dt,0,.05);
  k.prevX=k.x;k.prevZ=k.z;
  k.boostTimer=Math.max(0,k.boostTimer-dt);k.shieldTimer=Math.max(0,k.shieldTimer-dt);
  k.spinTimer=Math.max(0,k.spinTimer-dt);k.overdriveTimer=Math.max(0,k.overdriveTimer-dt);k.invulnTimer=Math.max(0,k.invulnTimer-dt);
  k.emoteTimer=Math.max(0,k.emoteTimer-dt);
  const nearestBefore=track.nearest(k.x,k.z);
  const off=nearestBefore.distance>track.width*.48;
  const wasDrifting=k.drifting;
  const request=clamp(Number(input.steer)||0,-1,1);
  // Progressive steering response eliminates twitchiness from keyboard/touch taps.
  k.steerInput+= (request-k.steerInput)*Math.min(1,dt*(k.drifting?13:10));
  k.drifting=!!input.drift && k.speed>10 && Math.abs(request)>.14 && k.spinTimer===0;
  if(k.drifting)k.driftCharge=clamp(k.driftCharge+dt*(.72+Math.abs(request)*.75),0,2.9);
  if(wasDrifting&&!k.drifting){if(k.driftCharge>.45)k.boostTimer=Math.max(k.boostTimer,Math.min(1.5,k.driftCharge*.50));k.driftCharge=0;}
  if(k.spinTimer>0){k.speed*=Math.max(0,1-2.2*dt);k.heading+=dt*7.6;}
  else {
    const boosted=k.boostTimer>0,maxSpeed=k.overdriveTimer>0?51:boosted?45:33;
    const gas=!!input.gas,brake=!!input.brake;
    const acceleration=boosted?26:gas?20:brake?-29:-7;
    // Gentle off-track slowdown; driveable shoulders rather than instant punishment.
    k.speed=clamp(k.speed+dt*(acceleration-(off?5:0)),-9,maxSpeed);
    if(!gas&&!brake&&Math.abs(k.speed)<.35)k.speed=0;
    if(off)k.speed*=Math.max(0,1-dt*.18);
    k.steer=k.steerInput;
    const speedRatio=clamp(Math.abs(k.speed)/10,0,1);
    const highSpeedGrip=1-.22*clamp((Math.abs(k.speed)-18)/27,0,1);
    // CRITICAL: right input is a NEGATIVE yaw in chase-camera space.
    k.heading-=k.steerInput*(k.drifting?2.24:1.85)*speedRatio*highSpeedGrip*dt*(k.speed<0?-1:1);
    // Mild driver assist: align a little with the road only if not actively drifting.
    // The correction is stronger as the kart approaches a track boundary.
    const headingOfRoad=Math.atan2(nearestBefore.tx,nearestBefore.tz);
    const headingError=normalizeAngle(headingOfRoad-k.heading);
    if(!k.drifting&&k.speed>7&&Math.abs(headingError)<.94){
      const edge=clamp((nearestBefore.distance/track.width-.18)*1.9,0,.52);
      k.heading+=headingError*dt*(.13+edge*.38)*(1-Math.abs(request)*.66);
    }
  }
  k.x+=Math.sin(k.heading)*k.speed*dt;
  k.z+=Math.cos(k.heading)*k.speed*dt;
  const closest=track.nearest(k.x,k.z),dist=closest.distance;
  if(dist>track.width*.46){
    const excess=dist-track.width*.46;
    const pull=clamp(excess*dt*.075,0,.13);
    k.x+=(closest.x-k.x)*pull;k.z+=(closest.z-k.z)*pull;
  }
  if(dist>track.width*.64){
    const maxDist=track.width*.64;
    const ratio=maxDist/Math.max(dist,.001);
    k.x=closest.x+(k.x-closest.x)*ratio;
    k.z=closest.z+(k.z-closest.z)*ratio;
    k.speed*=Math.max(0,1-dt*1.5);
    // Rubberized safety rails gently guide the nose back down the circuit.
    const desired=Math.atan2(closest.tx,closest.tz);
    k.heading+=normalizeAngle(desired-k.heading)*Math.min(.11,dt*.9);
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
  if(k.shieldTimer>0){k.shieldTimer=0;k.invulnTimer=.8;k.hitSerial=(k.hitSerial||0)+1;return false;}
  k.hitSerial=(k.hitSerial||0)+1;k.spinTimer=1.45;k.invulnTimer=2.8;k.speed*=.42;k.drifting=false;k.driftCharge=0;return true;
}
/** Five full-road pickup gates. Crossing any gate with an empty slot awards exactly one item.
 * Full road width is intentional: no invisible precision-hit requirement on touchscreens.
 * A per-gate-per-lap key prevents stationary farming, while a short cooldown blocks spam.
 */
export const GATE_RESPAWN=3.0;   // seconds a used item box stays gone (Mario-Kart style)
export function stepGates(gateTimers,dt){if(gateTimers)for(let i=0;i<gateTimers.length;i++)if(gateTimers[i]>0)gateTimers[i]=Math.max(0,gateTimers[i]-dt);}
export function simulatePickups(k,track,seconds,rng=Math.random,players=[],gateTimers=null){
  if(k.completed||k.item||seconds-k.lastItemAt<.8)return false;
  const lap=Math.floor(Math.max(0,k.progress)/track.length);
  for(let i=0;i<ITEM_GATES.length;i++){
    if(gateTimers&&gateTimers[i]>0)continue;       // Mario-Kart: box was just taken — hidden for everyone until it respawns
    const at=track.length*ITEM_GATES[i];
    let d=Math.abs(k.s-at);d=Math.min(d,track.length-d);
    const key=`${lap}:${i}`;                        // this kart gets one box per gate per lap (no double-dip on one crossing)
    if(d<Math.max(4.8,Math.abs(k.speed)*.14)&&k.lastPickupKey!==key){
      const order=players.length?rankings(players).findIndex(p=>p.id===k.id)+1:1;
      k.item=rollItem(order||1,players.length||8,rng);
      k.lastItemAt=seconds;k.lastPickupKey=key;k.itemSerial=(k.itemSerial||0)+1;
      if(gateTimers)gateTimers[i]=GATE_RESPAWN;
      return true;
    }
  }
  return false;
}
const nearestRival=(k,all,range,frontOnly=false)=>all.filter(o=>o.id!==k.id&&!o.completed&&
  Math.hypot(o.x-k.x,o.z-k.z)<range&&(!frontOnly||((o.x-k.x)*Math.sin(k.heading)+(o.z-k.z)*Math.cos(k.heading))>0))
  .sort((a,b)=>Math.hypot(a.x-k.x,a.z-k.z)-Math.hypot(b.x-k.x,b.z-k.z))[0];
export function activateItem(k,all,seconds,obstacles){
  if(!k.item||k.completed)return null;
  const used=k.item;k.item=null;k.usedItem=used;k.useSerial=(k.useSerial||0)+1;
  if(used==='boost')k.boostTimer=Math.max(k.boostTimer,2.9);
  else if(used==='overdrive'){k.boostTimer=Math.max(k.boostTimer,4.1);k.overdriveTimer=4.1;}
  else if(used==='shield')k.shieldTimer=Math.max(k.shieldTimer,7.5);
  else if(used==='repair'){k.spinTimer=0;k.invulnTimer=Math.max(k.invulnTimer,2.1);k.boostTimer=Math.max(k.boostTimer,1.05);}
  else if(used==='pulse'){
    const target=nearestRival(k,all,37);if(target)hitKart(target);
    else k.boostTimer=Math.max(k.boostTimer,1.15);
  }else if(used==='shockwave'){
    for(const target of all)if(target.id!==k.id&&Math.hypot(target.x-k.x,target.z-k.z)<19)hitKart(target);
    k.shieldTimer=Math.max(k.shieldTimer,.6);
  }else if(used==='rocket'){
    const target=nearestRival(k,all,70,true);
    obstacles.push({id:`rocket-${k.id}-${k.useSerial}`,type:'rocket',x:k.x+Math.sin(k.heading)*4,
      z:k.z+Math.cos(k.heading)*4,heading:k.heading,targetId:target?.id||null,owner:k.id,ttl:3.4});
  }else if(used==='oil'){
    obstacles.push({id:`oil-${k.id}-${k.useSerial}`,type:'oil',x:k.x-Math.sin(k.heading)*4,
      z:k.z-Math.cos(k.heading)*4,owner:k.id,ttl:16});
  }
  return used;
}
export function stepObstacles(obstacles,all,dt){
  for(const o of obstacles){
    o.ttl-=dt;
    if(o.type==='rocket'){
      const target=all.find(k=>k.id===o.targetId&&!k.completed);
      if(target){const desired=Math.atan2(target.x-o.x,target.z-o.z);o.heading+=clamp(normalizeAngle(desired-o.heading),-dt*2.7,dt*2.7);}
      o.x+=Math.sin(o.heading)*dt*64;o.z+=Math.cos(o.heading)*dt*64;
    }
    for(const k of all){
      if(k.id===o.owner||k.completed)continue;
      if(Math.hypot(k.x-o.x,k.z-o.z)<(o.type==='rocket'?3.8:3.1)){
        hitKart(k);o.ttl=0;break;
      }
    }
  }
  return obstacles.filter(o=>o.ttl>0);
}
export function rankings(karts){return [...karts].sort((a,b)=>a.completed&&b.completed?(a.finishTime||Infinity)-(b.finishTime||Infinity):a.completed?-1:b.completed?1:b.progress-a.progress);}
/** Server-authoritative, swept-circle kart contact. Prevent high-speed pass-throughs.
 * Collision resolution is also called by solo races so online and offline feel alike.
 */
export function resolveKartCollisions(karts){
  const diameter=4.05;
  for(let i=0;i<karts.length;i++)for(let j=i+1;j<karts.length;j++){
    const a=karts[i],b=karts[j];if(a.completed||b.completed)continue;
    let dx=b.x-a.x,dz=b.z-a.z,d=Math.hypot(dx,dz);
    const ax=Number.isFinite(a.prevX)?a.prevX:a.x,az=Number.isFinite(a.prevZ)?a.prevZ:a.z;
    const bx=Number.isFinite(b.prevX)?b.prevX:b.x,bz=Number.isFinite(b.prevZ)?b.prevZ:b.z;
    const rx=bx-ax,rz=bz-az,vx=dx-rx,vz=dz-rz,denom=vx*vx+vz*vz;
    const t=denom>.00001?clamp(-(rx*vx+rz*vz)/denom,0,1):0;
    const closest=Math.hypot(rx+vx*t,rz+vz*t);
    if(d>=diameter && (closest>=diameter||t<=0||t>=1))continue;
    if(d>=diameter){ // Swept impact: rewind to first contact rather than letting karts tunnel.
      a.x=ax+(a.x-ax)*t;a.z=az+(a.z-az)*t;
      b.x=bx+(b.x-bx)*t;b.z=bz+(b.z-bz)*t;
      dx=b.x-a.x;dz=b.z-a.z;d=Math.hypot(dx,dz);
    }
    if(d<.0001){const prevDistance=Math.hypot(rx,rz);if(prevDistance>.0001){dx=rx/prevDistance;dz=rz/prevDistance;}else{const ang=a.heading||0;dx=Math.cos(ang);dz=-Math.sin(ang);}d=0;}
    const nx=dx/(d||1),nz=dz/(d||1),correction=(diameter-d)*.505;
    a.x-=nx*correction;a.z-=nz*correction;b.x+=nx*correction;b.z+=nz*correction;
    // Forgiving contact: bump and slide past instead of bogging down and sticking.
    const close=Math.abs(a.speed-b.speed);
    const penalty=clamp(.975-close*.0028,.9,.99);
    a.speed*=penalty;b.speed*=penalty;
    a.driftCharge*=.97;b.driftCharge*=.97;
  }
}
