import * as THREE from 'three';
import {RACERS,KART_COLORS} from '../shared/sim.js';
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
  part(root,sphere(.69,skin),0,3.2,-.35);
  part(root,sphere(.78,helmet),0,3.48,-.43);
  const visor=m(0x10263e,.74,.16);visor.emissive=new THREE.Color(0x113c58);visor.emissiveIntensity=.5;
  const v=part(root,sphere(.52,visor),0,3.42,.09);v.scale.set(1.13,.54,.25);
  if(racer.style==='mohawk'){
    for(let i=0;i<5;i++)part(root,new THREE.Mesh(new THREE.ConeGeometry(.18,.37,5),suit),0,4.1,-.86+i*.24);
  }else if(racer.style==='pony'){
    const pony=part(root,sphere(.37,helmet),0,3.61,-1.14);pony.scale.set(.7,1.6,.7);
  }else if(racer.style==='cap'){
    part(root,cube(1.05,.12,.47,body),0,3.91,.2);
  }else{
    part(root,cube(.9,.12,.24,chrome),0,4.12,-.37);
  }
  for(const x of [-1,1]){
    const arm=capsule(root,.23,.65,suit,x*.7,2.22,.28);arm.rotation.x=.75;arm.rotation.z=x*.28;
    part(root,sphere(.25,dark),x*.62,1.85,.55);
  }
  const wheel=part(root,new THREE.Mesh(new THREE.TorusGeometry(.59,.08,6,17),dark),0,2.02,.74,Math.PI*.35);
  const shield=new THREE.Mesh(new THREE.SphereGeometry(3.25,18,12),new THREE.MeshBasicMaterial({color:0x6ce8ff,transparent:true,opacity:.13,side:THREE.BackSide,depthWrite:false}));shield.position.y=2;shield.visible=false;root.add(shield);
  const flameMat=new THREE.MeshBasicMaterial({color:0x7fe7ff,transparent:true,opacity:.9});
  const flames=[];
  for(let i of [-.7,.7]){
    const flame=new THREE.Mesh(new THREE.ConeGeometry(.26,.94,7),flameMat);
    flame.rotation.x=-Math.PI/2;flame.position.set(i,.87,-2.3);root.add(flame);flames.push(flame);
  }
  const label=makeLabel(k.name);g.add(label);if(isSelf)label.visible=false;
  g.userData={wheels,shield,flames,root,label};
  return g;
}
export function updateKartVisual(g,k,dt,time){
  const {wheels,shield,flames,root}=g.userData;
  g.position.set(k.x,.17+Math.sin(time*18+k.avatar)*.02,k.z);g.rotation.y=k.heading;
  root.rotation.z=THREE.MathUtils.lerp(root.rotation.z,(k.steer||0)*(k.drifting?.11:.055),.13);
  root.rotation.x=THREE.MathUtils.lerp(root.rotation.x,-Math.abs(k.speed)/300,.1);
  for(const w of wheels){w.tire.rotation.x+=k.speed*dt*.9;w.rim.rotation.x+=k.speed*dt*.9;}
  shield.visible=k.shieldTimer>0;if(shield.visible)shield.rotation.y+=dt;
  for(const f of flames){const enabled=k.boostTimer>0;f.visible=enabled;f.scale.y=enabled?.6+Math.sin(time*41)*.25:1;}
  root.rotation.y=k.spinTimer>0?Math.sin(time*12)*.6:0;
}
export function disposeKart(g){g.traverse(o=>{if(o.geometry)o.geometry.dispose();if(o.material){o.material.map?.dispose();o.material.dispose();}});}
