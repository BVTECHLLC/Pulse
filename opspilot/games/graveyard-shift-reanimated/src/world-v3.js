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
 const world=engine.world,terrain=new Terrain(73),seed=map.id==='cemetery'?7331:map.id==='village'?9137:7711,rnd=rng(seed);engine.terrain=terrain;
 engine.v3Props=[];
 const centerPositions=[{x:12,z:1,axis:'x',sign:1},{x:-15,z:11,axis:'z',sign:1},{x:1,z:-19,axis:'x',sign:-1}];
 for(const pos of centerPositions)platform(world,terrain,pos);
 const rockG=new THREE.DodecahedronGeometry(1,0);rockG.scale(1,.55,.78);
 const rockMat=mat(map.id==='facility'?0x526b7a:0x60665e);
 const rocks=new THREE.InstancedMesh(rockG,rockMat,49),dummy=new THREE.Object3D();
 for(let i=0;i<49;i++){
  let x=0,z=0;for(let retry=0;retry<14;retry++){const r=11+Math.sqrt(rnd())*54,a=rnd()*Math.PI*2;x=Math.cos(a)*r;z=Math.sin(a)*r;if(!terrain.blocked(x,z,0,1.8))break;}
  const size=.75+rnd()*.8;dummy.position.set(x,size*.31,z);dummy.scale.set(size,size,size);dummy.rotation.set(0,rnd()*Math.PI*2,0);dummy.updateMatrix();rocks.setMatrixAt(i,dummy.matrix);
  terrain.addCircle(x,z,size*.68,size*.65);if(size>1.05)terrain.addPerch(x,z,size*.48,size*.64);
 }
 rocks.count=49;rocks.instanceMatrix.needsUpdate=true;rocks.castShadow=true;rocks.receiveShadow=true;world.add(rocks);
 // All decorative trees use the same physical collision footprints as their visuals.
 for(let i=0;i<34;i++){
  let x=0,z=0;for(let t=0;t<20;t++){const a=rnd()*Math.PI*2,r=15+Math.sqrt(rnd())*51;x=Math.cos(a)*r;z=Math.sin(a)*r;if(!terrain.blocked(x,z,0,2))break;}
  vegetation(world,terrain,x,z,.82+rnd()*.57,(name,height)=>engine.cloneModel(name,height));
 }
 // Dungeon set dressing: all physical pillars, coffins, and walls block travel.
 for(let j=0;j<14;j++){
  const a=j*2.39996,r=24+(j%4)*6.7,x=Math.cos(a)*r,z=Math.sin(a)*r;
  if(terrain.blocked(x,z,0,1.4))continue;
  const obj=engine.cloneModel(j%3===0?'Dungeonpillar':j%3===1?'Dungeonbarrel':'Dungeoncrate',j%3===0?2.5:1.2);
  if(obj){obj.position.set(x,0,z);obj.rotation.y=a;world.add(obj);}else block(world,x,z,1.05,1.6,1.05,STONE);
  terrain.addCircle(x,z,.67,2.2);
 }
 // Distinct crafted fantasy props decorate the ruins and provide cover where appropriate.
 const props=['Cauldron','Barrel','Crate_Wooden','WeaponStand','Lantern_Wall','CandleStick_Triple','Banner_1','Potion_1'];
 for(let i=0;i<34;i++){
  const a=i*2.39996,r=15+(i%7)*5.2,x=Math.cos(a)*r,z=Math.sin(a)*r;
  if(terrain.blocked(x,z,0,1.1))continue;
  const name=props[i%props.length],obj=engine.cloneModel('Fantasy'+name,name==='Banner_1'?2.5:name==='Lantern_Wall'?1.3:1.1);
  if(!obj)continue;obj.position.set(x,0,z);obj.rotation.y=a;world.add(obj);
  if(['Cauldron','Barrel','Crate_Wooden','WeaponStand'].includes(name))terrain.addCircle(x,z,.49,1.5);
 }
 // Lit beacons make the map legible at night without expensive light per prop.
 for(let i=0;i<16;i++){
  const a=i/16*Math.PI*2,r=27+(i%3)*6,x=Math.cos(a)*r,z=Math.sin(a)*r;
  const post=new THREE.Mesh(new THREE.CylinderGeometry(.05,.09,1.6,6),WOOD);post.position.set(x,.8,z);world.add(post);
  const flame=new THREE.Mesh(new THREE.ConeGeometry(.19,.44,7),EMBER);flame.position.set(x,1.79,z);world.add(flame);
 }
 const dustGeo=new THREE.BufferGeometry(),pos=[];for(let i=0;i<300;i++)pos.push((rnd()-.5)*140,.12+rnd()*3,(rnd()-.5)*140);
 dustGeo.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));
 const dust=new THREE.Points(dustGeo,new THREE.PointsMaterial({color:0xa1c6b4,size:.045,transparent:true,opacity:.35,depthWrite:false}));world.add(dust);
 engine.v3Dust=dust;
 return terrain;
}
