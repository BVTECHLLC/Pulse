import * as THREE from 'three';
import {Terrain} from './terrain.js';
const mat=(color,metalness=0)=>new THREE.MeshStandardMaterial({color,metalness,roughness:.84,flatShading:true});
const STONE=mat(0x55666c),TRIM=mat(0x98a49b),EARTH=mat(0x3e4844),WOOD=mat(0x5a423c),EMBER=new THREE.MeshStandardMaterial({color:0xd8a16a,emissive:0xe58b3e,emissiveIntensity:1.25});
const rng=(seed)=>()=>((seed=(seed*1664525+1013904223)>>>0)/4294967296);
function block(world,x,z,sx,sy,sz,m=STONE,y=sy/2){const o=new THREE.Mesh(new THREE.BoxGeometry(sx,sy,sz),m);o.position.set(x,y,z);o.castShadow=true;o.receiveShadow=true;world.add(o);return o;}
function stairway(world,terrain,startX,startZ,axis,sign,h=1.55){const len=5.4,width=2.6;terrain.addRamp(startX,startZ,width,len,h,axis,sign);
 for(let i=0;i<9;i++){const t=(i+.5)/9,x=startX+(axis==='x'?sign*t*len:0),z=startZ+(axis==='z'?sign*t*len:0);const step=new THREE.Mesh(new THREE.BoxGeometry(axis==='x'?len/9:width,.18,axis==='z'?len/9:width),TRIM);step.position.set(x,t*h-.11,z);step.receiveShadow=true;world.add(step);}
}
function platform(world,terrain,{x,z,h=1.55,r=3.2,axis='x',sign=1}){
 block(world,x,z,r*2,h,r*2,STONE,h/2);block(world,x,z,r*2+.28,.17,r*2+.28,TRIM,h+.05);
 terrain.addBox(x,z,r,r,h);terrain.addPlatform(x,z,r+.14,r+.14,h+.14);
 const sx=axis==='x'?x-sign*(r+5.4):x,sz=axis==='z'?z-sign*(r+5.4):z;
 stairway(world,terrain,sx,sz,axis,sign,h+.14);
 // Ruined posts are physically solid instead of cardboard scenery.
 for(const dx of [-r+.45,r-.45])for(const dz of [-r+.45,r-.45]){
  const yy=h+(Math.abs(dx+dz)<1?1.4:1.0);block(world,x+dx,z+dz,.66,yy-h,.66,STONE,h+(yy-h)/2);
  terrain.addBox(x+dx,z+dz,.33,.33,yy);
 }
}
function vegetation(world,terrain,x,z,scale,asset){
 const shadow=new THREE.Mesh(new THREE.CircleGeometry(scale*.7,12),new THREE.MeshBasicMaterial({color:0x091712,transparent:true,opacity:.26,depthWrite:false}));shadow.rotation.x=-Math.PI/2;shadow.position.set(x,.018,z);world.add(shadow);
 const o=asset?.('DeadTree',2.2*scale);
 if(o){o.position.set(x,0,z);o.rotation.y=(x*12.5+z*17.7)%6.28;world.add(o);}
 else{
  const trunk=new THREE.Mesh(new THREE.CylinderGeometry(.24*scale,.40*scale,2.9*scale,7),WOOD);trunk.position.set(x,1.45*scale,z);trunk.castShadow=true;world.add(trunk);
  const crown=new THREE.Mesh(new THREE.ConeGeometry(1.0*scale,2.4*scale,7),mat(0x344f4b));crown.position.set(x,3.1*scale,z);crown.castShadow=true;world.add(crown);
 }
 terrain.addCircle(x,z,.35*scale,2.9*scale);
}
export function buildWorldV3(engine,map){
 // V9: a hand-structured, walled arena. A perimeter rampart rings the fight; a
 // central ruined shrine anchors the middle; symmetric ruins give verticality;
 // decoration is kept sparse and purposeful so the space reads clean.
 const world=engine.world,terrain=new Terrain(73),seed=map.id==='cemetery'?7331:map.id==='village'?9137:7711,rnd=rng(seed);engine.terrain=terrain;
 engine.v3Props=[];
 const wallCol=map.id==='facility'?0x3a4a52:map.id==='inferno'?0x4a2a1c:map.id==='crypt'?0x27404a:0x3a4048;

 // --- Perimeter rampart (one cylindrical shell + a stone cap + watch-pillars) ---
 const R=56;
 const wall=new THREE.Mesh(new THREE.CylinderGeometry(R,R,5.5,64,1,true),new THREE.MeshStandardMaterial({color:wallCol,roughness:.92,metalness:.04,side:THREE.DoubleSide,flatShading:true}));
 wall.position.y=2.6;world.add(wall);
 const cap=new THREE.Mesh(new THREE.TorusGeometry(R,.7,8,64),TRIM);cap.rotation.x=Math.PI/2;cap.position.y=5.3;world.add(cap);
 for(let i=0;i<44;i++){const a=i/44*Math.PI*2;terrain.addCircle(Math.cos(a)*R,Math.sin(a)*R,5.5,6);}
 for(let i=0;i<16;i++){const a=i/16*Math.PI*2,x=Math.cos(a)*R,z=Math.sin(a)*R;
  const pil=new THREE.Mesh(new THREE.CylinderGeometry(1.5,1.9,9,8),STONE);pil.position.set(x,4.3,z);pil.castShadow=true;world.add(pil);
  const flame=new THREE.Mesh(new THREE.ConeGeometry(.55,1.4,8),EMBER);flame.position.set(x,9.7,z);world.add(flame);
  if(i%4===0){const l=new THREE.PointLight(0xffa64d,1.5,34,2);l.position.set(x*.9,8.5,z*.9);world.add(l);}
 }

 // --- Central ruined shrine: 4 standing monoliths framing the start, a floating rune crystal above ---
 for(const [mx,mz] of [[9,9],[-9,9],[9,-9],[-9,-9]]){
  const mono=new THREE.Mesh(new THREE.BoxGeometry(1.1,4.4,1.1),STONE);mono.position.set(mx,2.2,mz);mono.rotation.y=(mx+mz)*0.1;mono.castShadow=true;world.add(mono);
  const tip=new THREE.Mesh(new THREE.ConeGeometry(.8,1.0,4),TRIM);tip.position.set(mx,4.7,mz);tip.rotation.y=.78;world.add(tip);
  terrain.addCircle(mx,mz,.75,4.4);
 }
 const crystal=new THREE.Mesh(new THREE.OctahedronGeometry(1.0),new THREE.MeshStandardMaterial({color:0x8be8ff,emissive:0x59c6ff,emissiveIntensity:1.8,metalness:.3,roughness:.2}));crystal.position.set(0,5.2,0);world.add(crystal);
 const crLight=new THREE.PointLight(0x7fd8ff,1.7,30,2);crLight.position.set(0,5.2,0);world.add(crLight);
 engine.v3Crystal=crystal;

 // --- Three symmetric ruined platforms (climbable verticality) ---
 for(const pos of [{x:0,z:-30,axis:'x',sign:-1},{x:-26,z:18,axis:'z',sign:1},{x:26,z:18,axis:'x',sign:1}])platform(world,terrain,pos);

 // --- Sparse rocks (instanced), kept to the mid-ring so the arena stays open ---
 const rockG=new THREE.DodecahedronGeometry(1,0);rockG.scale(1,.55,.78);
 const rockMat=mat(map.id==='facility'?0x526b7a:0x60665e);
 const rocks=new THREE.InstancedMesh(rockG,rockMat,16),dummy=new THREE.Object3D();let rc=0;
 for(let i=0;i<16;i++){
  let x=0,z=0,ok=false;for(let retry=0;retry<16;retry++){const r=16+Math.sqrt(rnd())*32,a=rnd()*Math.PI*2;x=Math.cos(a)*r;z=Math.sin(a)*r;if(!terrain.blocked(x,z,0,1.8)){ok=true;break;}}
  if(!ok)continue;const size=.8+rnd()*.7;dummy.position.set(x,size*.31,z);dummy.scale.set(size,size,size);dummy.rotation.set(0,rnd()*Math.PI*2,0);dummy.updateMatrix();rocks.setMatrixAt(rc++,dummy.matrix);
  terrain.addCircle(x,z,size*.68,size*.65);if(size>1.1)terrain.addPerch(x,z,size*.48,size*.64);
 }
 rocks.count=rc;rocks.instanceMatrix.needsUpdate=true;rocks.castShadow=true;rocks.receiveShadow=true;world.add(rocks);

 // --- A ring of dead trees hugging the rampart for silhouette, plus a few crafted props ---
 for(let i=0;i<12;i++){const a=i/12*Math.PI*2+rnd()*.3,r=44+rnd()*8;const x=Math.cos(a)*r,z=Math.sin(a)*r;if(terrain.blocked(x,z,0,2))continue;vegetation(world,terrain,x,z,.9+rnd()*.5,(name,height)=>engine.cloneModel(name,height));}
 const props=['Cauldron','WeaponStand','CandleStick_Triple','Banner_1','Barrel','Crate_Wooden'];
 for(let i=0;i<10;i++){const a=i/10*Math.PI*2+1.1,r=20+(i%3)*8;const x=Math.cos(a)*r,z=Math.sin(a)*r;if(terrain.blocked(x,z,0,1.1))continue;
  const name=props[i%props.length],obj=engine.cloneModel('Fantasy'+name,name==='Banner_1'?2.5:1.1);
  if(!obj)continue;obj.position.set(x,0,z);obj.rotation.y=a;world.add(obj);
  if(['Cauldron','Barrel','Crate_Wooden','WeaponStand'].includes(name))terrain.addCircle(x,z,.49,1.5);
 }

 // --- Light drifting dust for atmosphere (reduced) ---
 const dustGeo=new THREE.BufferGeometry(),pos=[];for(let i=0;i<110;i++)pos.push((rnd()-.5)*110,.2+rnd()*3.4,(rnd()-.5)*110);
 dustGeo.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));
 const dust=new THREE.Points(dustGeo,new THREE.PointsMaterial({color:0xa1c6b4,size:.05,transparent:true,opacity:.3,depthWrite:false}));world.add(dust);
 engine.v3Dust=dust;
 return terrain;
}
