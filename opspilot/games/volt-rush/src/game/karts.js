import * as THREE from 'three';
import {RACERS,KART_COLORS} from '../shared/sim.js';
import {installHeroModel} from './hero-assets.js';
const m=(color,metalness=0,roughness=.6)=>new THREE.MeshStandardMaterial({color,metalness,roughness});
const sphere=(r,mat)=>new THREE.Mesh(new THREE.SphereGeometry(r,12,8),mat);
const cube=(w,h,d,mat)=>new THREE.Mesh(new THREE.BoxGeometry(w,h,d),mat);
function part(g,mesh,x,y,z,rx=0,ry=0,rz=0){mesh.position.set(x,y,z);mesh.rotation.set(rx,ry,rz);g.add(mesh);return mesh;}
function capsule(g,r,height,material,x,y,z){const c=new THREE.Mesh(new THREE.CapsuleGeometry(r,height,5,9),material);c.position.set(x,y,z);g.add(c);return c;}
function makeLabel(name){
  const c=document.createElement('canvas');c.width=256;c.height=60;const x=c.getContext('2d');
  x.fillStyle='#071529dd';x.beginPath();if(x.roundRect){x.roundRect(0,0,256,60,25);x.fill();}else{x.fillRect(0,0,256,60);}x.fillStyle='#ffffff';x.textAlign='center';x.textBaseline='middle';x.font='bold 31px system-ui';x.fillText(name.slice(0,16),128,31,242);
  const texture=new THREE.CanvasTexture(c);texture.colorSpace=THREE.SRGBColorSpace;
  const obj=new THREE.Sprite(new THREE.SpriteMaterial({map:texture,transparent:true,depthWrite:false}));obj.scale.set(6,1.4,1);obj.position.y=5.8;return obj;
}
export function createKartVisual(k,isSelf=false){
  const g=new THREE.Group();const root=new THREE.Group();g.add(root);
  const paint=new THREE.Color(KART_COLORS[k.color]||KART_COLORS[0]),racer=RACERS[k.avatar]||RACERS[0];
  const body=m(paint,.38,.24),dark=m(0x152237,.35,.65),chrome=m(0xa3bbd2,.82,.24),rubber=m(0x171c24,.03,.92),
    glow=m(paint,.4,.22),helmet=m(racer.helmet,.45,.22),suit=m(racer.suit,.2,.57),skin=m(racer.skin,.02,.75);
  glow.emissive=paint;glow.emissiveIntensity=.3;
  part(root,cube(2.5,.62,3.9,body),0,.9,.1);
  part(root,cube(1.9,.26,2.5,dark),0,1.18,-.15);
  part(root,cube(2.35,.24,1.35,body),0,1.05,1.8);
  part(root,cube(2.7,.23,.55,dark),0,.64,2.05);
  part(root,cube(2.75,.19,.55,body),0,2.0,-1.78);
  part(root,cube(.17,.8,.16,chrome,-1,1.6,-1.65));part(root,cube(.17,.8,.16,chrome,1,1.6,-1.65));
  part(root,cube(.48,.22,.11,glow),-.76,1.12,2.03);part(root,cube(.48,.22,.11,glow),.76,1.12,2.03);
  part(root,cube(.45,.25,.14,m(0xfd4656,.05,.5)),-.8,.97,-1.92);part(root,cube(.45,.25,.14,m(0xfd4656,.05,.5)),.8,.97,-1.92);
  part(root,cube(1.2,.18,.5,chrome),0,1.7,.94);
  part(root,cube(1.5,.3,1,dark),0,1.52,-.45);
  const wheels=[];
  for(const x of [-1.5,1.5])for(const z of [-1.3,1.25]){
    const pivot=new THREE.Group();pivot.position.set(x,.63,z);root.add(pivot);
    const tire=new THREE.Mesh(new THREE.CylinderGeometry(.63,.63,.43,15),rubber);tire.rotation.z=Math.PI*.5;pivot.add(tire);
    const rim=new THREE.Mesh(new THREE.CylinderGeometry(.29,.29,.45,12),chrome);rim.rotation.z=Math.PI*.5;pivot.add(rim);
    const center=new THREE.Mesh(new THREE.CylinderGeometry(.11,.11,.48,8),glow);center.rotation.z=Math.PI*.5;pivot.add(center);
    wheels.push({pivot,tire,rim,center,z});
  }
  // Original pilot silhouette, detailed enough to be read at racing camera distance.
  capsule(root,.65,.7,suit,0,2.12,-.45);
  // Friendly original collectible-toy pilots: big head, huge eyes, cheek blush,
  // and six distinctive costume headpieces. All geometry built in Three.js.
  part(root,sphere(.72,skin),0,3.28,-.36);
  const capShell=part(root,sphere(.82,helmet),0,3.56,-.45);capShell.scale.set(1.1,1.02,.98);
  const face=part(root,sphere(.60,skin),0,3.31,.11);face.scale.set(1.09,.92,.42);
  const white=m(0xffffff),pupil=m(0x20223d),blush=m(0xff859f),smile=m(0x753957);
  for(const side of [-1,1]){
    const eye=part(root,sphere(.18,white),side*.27,3.41,.34);eye.scale.set(.9,1.18,.48);
    const dot=part(root,sphere(.108,pupil),side*.29,3.41,.438);dot.scale.z=.65;
    const shine=part(root,sphere(.046,white),side*.32-.022,3.48,.50);
    const cheek=part(root,sphere(.16,blush),side*.47,3.13,.30);cheek.scale.set(1.05,.5,.35);
  }
  const happy=part(root,new THREE.Mesh(new THREE.TorusGeometry(.19,.036,5,13,Math.PI),smile),0,3.15,.425);
  happy.rotation.z=Math.PI;
  // Distinct facial accessories and novelty head silhouettes, not franchise likenesses.
  const trimHat=m(racer.suit,.16,.45);
  if(k.avatar===0){
    const star=new THREE.Mesh(new THREE.OctahedronGeometry(.4,0),m(0xffec73));star.position.set(0,4.55,-.45);root.add(star);
    part(root,cube(.08,.38,.09,chrome),0,4.25,-.45);
  }else if(k.avatar===1){
    for(const side of [-1,1]){const ear=new THREE.Mesh(new THREE.ConeGeometry(.37,.9,4),trimHat);ear.position.set(side*.65,4.18,-.65);ear.rotation.z=-side*.25;root.add(ear);}
  }else if(k.avatar===2){
    for(const side of [-1,1]){const leaf=new THREE.Mesh(new THREE.ConeGeometry(.24,.92,5),trimHat);leaf.position.set(side*.34,4.28,-.42);leaf.rotation.z=side*.55;root.add(leaf);}
  }else if(k.avatar===3){
    for(const side of [-1,1]){const horn=new THREE.Mesh(new THREE.ConeGeometry(.22,.66,5),m(0xffec92));horn.position.set(side*.47,4.25,-.55);root.add(horn);}
  }else if(k.avatar===4){
    const ring=new THREE.Mesh(new THREE.TorusGeometry(.39,.115,5,18),trimHat);ring.position.set(0,4.27,-.44);ring.rotation.y=.4;root.add(ring);
  }else{
    for(const side of [-1,1])part(root,sphere(.31,trimHat),side*.68,4.07,-.46);
  }
  const visor=m(0x10263e,.74,.16);visor.emissive=new THREE.Color(0x113c58);visor.emissiveIntensity=.5;
  const v=part(root,sphere(.48,visor),0,3.77,-.035);v.scale.set(1.12,.32,.20);
  if(racer.style==='mohawk'){
    for(let i=0;i<5;i++)part(root,new THREE.Mesh(new THREE.ConeGeometry(.18,.37,5),suit),0,4.1,-.86+i*.24);
  }else if(racer.style==='pony'){
    const pony=part(root,sphere(.37,helmet),0,3.61,-1.14);pony.scale.set(.7,1.6,.7);
  }else if(racer.style==='cap'){
    part(root,cube(1.05,.12,.47,body),0,3.91,.2);
  }else{
    part(root,cube(.9,.12,.24,chrome),0,4.12,-.37);
  }
  // Silhouette kits are original hard-surface designs, distinct for each pilot.
  // All parts are procedural geometry; no model or texture dependencies.
  const trim=m(racer.suit,.55,.25),pearl=m(0xe7ffff,.3,.23),accent=m(paint,.35,.2);
  accent.emissive=paint;accent.emissiveIntensity=.55;
  const fin=(x,z,y=1.1)=>{const shape=new THREE.Mesh(new THREE.ConeGeometry(.44,2.25,4),trim);shape.rotation.x=Math.PI/2;shape.position.set(x,y,z);root.add(shape);};
  const light=(x,y,z,c)=>{const glowMat=new THREE.MeshBasicMaterial({color:c});const o=part(root,cube(.38,.18,.13,glowMat),x,y,z);return o;};
  if(k.avatar===0){ // Nova: high-downforce aero and swept energy fins
    for(const side of [-1,1]){fin(side*1.27,-1.3,1.43);part(root,cube(.18,.16,3.1,pearl),side*.95,1.26,.12);light(side*.95,1.28,2.02,0x75faff);}
    part(root,cube(1.7,.14,.28,trim),0,1.56,1.13);
  }else if(k.avatar===1){ // Jax: aggressive street buggy with large pipes
    for(const side of [-1,1]){
      part(root,new THREE.Mesh(new THREE.CylinderGeometry(.29,.43,1.05,8),chrome),side*1.13,1.29,-1.9,Math.PI/2);
      part(root,cube(.27,.36,2.7,trim),side*1.08,1.05,.06);light(side*.93,1.1,2.02,0xffa031);
    }
  }else if(k.avatar===2){ // Ivy: nature-inspired wings and leaf-shaped nose
    for(const side of [-1,1]){const leaf=part(root,new THREE.Mesh(new THREE.ConeGeometry(.53,2.2,5),trim),side*1.2,1.1,-.48,Math.PI/2,0,side*.16);leaf.scale.z=.55;}
    const stem=part(root,new THREE.Mesh(new THREE.ConeGeometry(.4,1.9,5),accent),0,1.48,1.35,Math.PI/2);stem.scale.x=.65;
    light(-.7,1.21,2.04,0xa4ff9a);light(.7,1.21,2.04,0xa4ff9a);
  }else if(k.avatar===3){ // Bolt: chunky retro racer with twin upright bolts
    for(const side of [-1,1]){
      part(root,cube(.57,.45,1.2,trim),side*1.07,1.35,1.1);
      const bolt=part(root,new THREE.Mesh(new THREE.ConeGeometry(.35,1.05,4),accent),side*.95,2.38,-1.15);bolt.rotation.z=side*.25;
      light(side*.9,1.45,1.92,0xfff46d);
    }
  }else if(k.avatar===4){ // Echo: sci-fi night racer with swept sidepods
    for(const side of [-1,1]){
      const wing=part(root,new THREE.Mesh(new THREE.ConeGeometry(.58,2.75,3),trim),side*1.35,1.22,-.55,Math.PI/2);wing.rotation.z=side*.19;
      part(root,cube(.15,.12,2.9,accent),side*1.07,1.47,.07);light(side*.9,1.4,2.03,0xfb80ff);
    }
  }else{ // Rook: armored offroad rally chassis with roof lamps
    part(root,cube(3.3,.47,.36,chrome),0,.95,2.15);
    for(let i=-1;i<=1;i++)light(i*.57,4.07,.02,0xffdf9b);
    for(const side of [-1,1])part(root,cube(.39,.43,2.65,trim),side*1.22,.97,0);
  }
  // Tiny trim lights add visual feedback even on lower-fidelity phones.
  for(const side of [-1,1])part(root,cube(.12,.09,1.65,accent),side*1.19,1.22,.28);
  for(const x of [-1,1]){
    const arm=capsule(root,.23,.65,suit,x*.7,2.22,.28);arm.rotation.x=.75;arm.rotation.z=x*.28;
    part(root,sphere(.25,dark),x*.62,1.85,.55);
  }
  const wheel=part(root,new THREE.Mesh(new THREE.TorusGeometry(.59,.08,6,17),dark),0,2.02,.74,Math.PI*.35);
  const shield=new THREE.Mesh(new THREE.SphereGeometry(3.25,20,14),new THREE.MeshBasicMaterial({color:0x7dfefa,transparent:true,opacity:.17,side:THREE.BackSide,depthWrite:false}));shield.position.y=2;shield.visible=false;root.add(shield);
  const shieldBand=new THREE.Mesh(new THREE.TorusGeometry(3.04,.075,6,34),new THREE.MeshBasicMaterial({color:0xb3faff,transparent:true,opacity:.76,blending:THREE.AdditiveBlending}));
  shieldBand.rotation.x=.4;shieldBand.position.y=2.1;shieldBand.visible=false;root.add(shieldBand);
  const flameMat=new THREE.MeshBasicMaterial({color:0x7fe7ff,transparent:true,opacity:.9});
  const flames=[];
  for(let i of [-.7,.7]){
    const flame=new THREE.Mesh(new THREE.ConeGeometry(.26,.94,7),flameMat);
    flame.rotation.x=-Math.PI/2;flame.position.set(i,.87,-2.3);root.add(flame);flames.push(flame);
  }
  const label=makeLabel(k.name);g.add(label);if(isSelf)label.visible=false;
  g.userData={wheels,shield,shieldBand,flames,root,label};
  installHeroModel(g,k);
  return g;
}
export function updateKartVisual(g,k,dt,time){
  const {wheels,shield,shieldBand,flames,root}=g.userData;
  g.position.set(k.x,.17+Math.sin(time*18+k.avatar)*.02,k.z);g.rotation.y=k.heading;
  root.rotation.z=THREE.MathUtils.lerp(root.rotation.z,(k.steer||0)*(k.drifting?.11:.055),.13);
  root.rotation.x=THREE.MathUtils.lerp(root.rotation.x,-Math.abs(k.speed)/300,.1);
  for(const w of wheels){w.tire.rotation.x+=k.speed*dt*.9;w.rim.rotation.x+=k.speed*dt*.9;}
  for(const w of (g.userData.heroWheels||[]))w.rotation.x+=k.speed*dt*.9;
  if(g.userData.hero)g.userData.hero.position.y=Math.sin(time*5+k.avatar)*.035;
  shield.visible=k.shieldTimer>0;shieldBand.visible=shield.visible;if(shield.visible){shield.rotation.y+=dt;shieldBand.rotation.y+=dt*2.8;shield.material.opacity=.10+.09*Math.sin(time*8)**2;}
  for(const f of flames){const enabled=k.boostTimer>0;f.visible=enabled;f.scale.y=enabled?.6+Math.sin(time*41)*.25:1;}
  root.rotation.y=k.spinTimer>0?Math.sin(time*12)*.6:0;
}
export function disposeKart(g){g.traverse(o=>{if(o.geometry&&!o.geometry.userData.voltShared)o.geometry.dispose();if(o.material){for(const m of (Array.isArray(o.material)?o.material:[o.material])){if(!m.userData.voltShared){m.map?.dispose();m.dispose();}}}});}
