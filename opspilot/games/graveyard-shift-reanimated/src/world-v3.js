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
 // V11: an organic canyon, not a ring. A jagged natural cliff wall encloses the
 // fight at irregular distances, a raised mesa gives commanding high ground, a
 // roofed cavern nook adds real depth, and rock spires break the skyline.
 const world=engine.world,terrain=new Terrain(74),seed=map.id==='cemetery'?7331:map.id==='village'?9137:map.id==='crypt'?6203:map.id==='inferno'?5519:7711,rnd=rng(seed);engine.terrain=terrain;
 engine.v3Props=[];
 const cliffCol=map.id==='facility'?0x3b4c54:map.id==='inferno'?0x4c2a1a:map.id==='crypt'?0x25404a:map.id==='sanctum'?0x332b40:0x3c4248;

 // --- Jagged cliff wall: many irregular stone chunks at varied radius (no circle) ---
 const cliffG=new THREE.DodecahedronGeometry(1,0);cliffG.scale(1.1,1,.95);
 const cliffMat=mat(cliffCol);const N=60;const cliffs=new THREE.InstancedMesh(cliffG,cliffMat,N),cd=new THREE.Object3D();
 for(let i=0;i<N;i++){const a=i/N*Math.PI*2+ (rnd()-.5)*.09, r=49+rnd()*11, x=Math.cos(a)*r, z=Math.sin(a)*r;
  const sx=4+rnd()*4.5, sy=5+rnd()*7, sz=4+rnd()*4.5;
  cd.position.set(x,sy*.32,z);cd.scale.set(sx,sy,sz);cd.rotation.set((rnd()-.5)*.3,rnd()*6.28,(rnd()-.5)*.3);cd.updateMatrix();cliffs.setMatrixAt(i,cd.matrix);
  terrain.addCircle(x,z,Math.max(sx,sz)*.42,8);}
 cliffs.instanceMatrix.needsUpdate=true;cliffs.castShadow=true;cliffs.receiveShadow=true;world.add(cliffs);
 // a few brazier beacons perched along the rim for legibility (emissive only, cheap)
 for(let i=0;i<8;i++){const a=i/8*Math.PI*2+.4,r=47,x=Math.cos(a)*r,z=Math.sin(a)*r;
  const flame=new THREE.Mesh(new THREE.ConeGeometry(.5,1.3,8),EMBER);flame.position.set(x,3.2,z);world.add(flame);
  if(i%2===0){const l=new THREE.PointLight(0xffa64d,1.3,30,2);l.position.set(x*.92,4,z*.92);world.add(l);}}

 // --- Central shrine: 4 monoliths frame the spawn, a rune crystal floats above ---
 for(const [mx,mz] of [[8,8],[-8,8],[8,-8],[-8,-8]]){
  const mono=new THREE.Mesh(new THREE.BoxGeometry(1.1,4.4,1.1),STONE);mono.position.set(mx,2.2,mz);mono.rotation.y=(mx+mz)*0.1;mono.castShadow=true;world.add(mono);
  const tip=new THREE.Mesh(new THREE.ConeGeometry(.8,1.0,4),TRIM);tip.position.set(mx,4.7,mz);tip.rotation.y=.78;world.add(tip);
  terrain.addCircle(mx,mz,.75,4.4);}
 const crystal=new THREE.Mesh(new THREE.OctahedronGeometry(1.0),new THREE.MeshStandardMaterial({color:0x8be8ff,emissive:0x59c6ff,emissiveIntensity:1.8,metalness:.3,roughness:.2}));crystal.position.set(0,5.2,0);world.add(crystal);
 const crLight=new THREE.PointLight(0x7fd8ff,1.7,30,2);crLight.position.set(0,5.2,0);world.add(crLight);engine.v3Crystal=crystal;

 // --- A big raised MESA (commanding high ground) with two stairways + a couple ruins ---
 const MX=0,MZ=-31,MR=8.5,MH=3.0;
 block(world,MX,MZ,MR*2,MH,MR*2,STONE,MH/2);block(world,MX,MZ,MR*2+.4,.2,MR*2+.4,TRIM,MH+.08);
 terrain.addBox(MX,MZ,MR,MR,MH);terrain.addPlatform(MX,MZ,MR+.2,MR+.2,MH+.14);
 stairway(world,terrain,MX,MZ+MR+5.4,'z',-1,MH+.14);
 stairway(world,terrain,MX+MR+5.4,MZ,'x',-1,MH+.14);
 for(const dx of [-MR+.7,MR-.7]){block(world,MX+dx,MZ-MR+.7,.7,2.2,.7,STONE,MH+1.1);terrain.addBox(MX+dx,MZ-MR+.7,.35,.35,MH+2.2);}

 // --- CAVERN nook: a roofed stone chamber with stalagmites, stalactites + a dim glow ---
 const CX=30,CZ=29;
 const roof=new THREE.Mesh(new THREE.BoxGeometry(22,1.4,22),mat(0x2a2f34));roof.position.set(CX,6.2,CZ);roof.castShadow=true;world.add(roof);
 for(const [dx,dz] of [[-9,-9],[9,-9],[-9,9],[9,9]]){const col=new THREE.Mesh(new THREE.CylinderGeometry(1.1,1.4,6.2,7),STONE);col.position.set(CX+dx,3.1,CZ+dz);col.castShadow=true;world.add(col);terrain.addCircle(CX+dx,CZ+dz,1.0,6);}
 for(let i=0;i<10;i++){const sx=CX+(rnd()-.5)*17,sz=CZ+(rnd()-.5)*17;if(terrain.blocked(sx,sz,0,1))continue;
  const h=1+rnd()*2.4;const sg=new THREE.Mesh(new THREE.ConeGeometry(.5+rnd()*.4,h,6),mat(0x4a5560));sg.position.set(sx,h/2,sz);sg.castShadow=true;world.add(sg);terrain.addCircle(sx,sz,.5,h*.8);
  const dh=.8+rnd()*1.8;const st=new THREE.Mesh(new THREE.ConeGeometry(.35+rnd()*.3,dh,6),mat(0x3f4953));st.position.set(CX+(rnd()-.5)*18,5.5-dh/2,CZ+(rnd()-.5)*18);st.rotation.x=Math.PI;world.add(st);}
 const cavGlow=new THREE.PointLight(0x6cff9a,1.4,20,2);cavGlow.position.set(CX,2.4,CZ);world.add(cavGlow);

 // --- A few rock spires kept to the OUTER ring so the play space stays open ---
 for(let i=0;i<6;i++){const a=i/6*Math.PI*2+rnd()*.5,r=30+rnd()*12;const x=Math.cos(a)*r,z=Math.sin(a)*r;if(terrain.blocked(x,z,0,2))continue;
  const h=3.5+rnd()*5,rr=.7+rnd()*1.1;const sp=new THREE.Mesh(new THREE.CylinderGeometry(rr*.5,rr,h,6),mat(0x555f5a,.05));sp.position.set(x,h/2,z);sp.rotation.y=rnd()*6.28;sp.castShadow=true;world.add(sp);
  const capR=new THREE.Mesh(new THREE.DodecahedronGeometry(rr*1.15,0),mat(0x5d665f));capR.position.set(x,h,z);capR.scale.y=.6;world.add(capR);
  terrain.addCircle(x,z,rr*.85,h);if(h<4.4)terrain.addPerch(x,z,rr*.7,h);}

 // --- Two lower ruined platforms + edge vegetation (silhouette only) ---
 for(const pos of [{x:-28,z:16,axis:'z',sign:1},{x:-24,z:-22,axis:'x',sign:1}])platform(world,terrain,pos);
 for(let i=0;i<9;i++){const a=i/9*Math.PI*2+rnd()*.4,r=40+rnd()*7;const x=Math.cos(a)*r,z=Math.sin(a)*r;if(terrain.blocked(x,z,0,2))continue;vegetation(world,terrain,x,z,.9+rnd()*.5,(name,height)=>engine.cloneModel(name,height));}
 // Decorative props are now flush dressing with NO collision — they never block you.
 const props=['Cauldron','WeaponStand','CandleStick_Triple','Barrel','Potion_1','Coin_Pile'];
 for(let i=0;i<8;i++){const a=i/8*Math.PI*2+1.3,r=34+rnd()*9;const x=Math.cos(a)*r,z=Math.sin(a)*r;if(terrain.blocked(x,z,0,1.1))continue;
  const name=props[i%props.length],obj=engine.cloneModel('Fantasy'+name,1.0);if(!obj)continue;obj.position.set(x,0,z);obj.rotation.y=a;world.add(obj);}

 // --- Drifting dust motes for atmosphere ---
 const dustGeo=new THREE.BufferGeometry(),pos=[];for(let i=0;i<120;i++)pos.push((rnd()-.5)*110,.2+rnd()*4,(rnd()-.5)*110);
 dustGeo.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));
 const dust=new THREE.Points(dustGeo,new THREE.PointsMaterial({color:0xa1c6b4,size:.05,transparent:true,opacity:.3,depthWrite:false}));world.add(dust);engine.v3Dust=dust;
 return terrain;
}
