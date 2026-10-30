import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {clone as cloneSkinned} from 'three/addons/utils/SkeletonUtils.js';
import {CHARACTERS,MAPS,WEAPONS,PASSIVES,EVOLUTIONS,MUTATORS,RELICS,SKINS,DIFFICULTIES,levelRequired,findWeapon} from './data.js';
import {profile} from './profile.js';
import {EnemyBatch} from './enemy-batch.js';
import {BUDGETS,graphicsPreset,enemyScale,enemyRadius,spawnPlan,comboMultiplier,safeDelta} from './balance.js';
import {buildWorldV3} from './world-v3.js';
import {CHEST_REWARDS} from './v3-content.js';
import {EffectComposer} from 'three/addons/postprocessing/EffectComposer.js';
import {RenderPass} from 'three/addons/postprocessing/RenderPass.js';
import {UnrealBloomPass} from 'three/addons/postprocessing/UnrealBloomPass.js';
import {OutputPass} from 'three/addons/postprocessing/OutputPass.js';
const TAU=Math.PI*2;
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const rand=(a,b)=>a+Math.random()*(b-a);
const material=(color,emissive=0x000000,roughness=.7)=>new THREE.MeshStandardMaterial({color,emissive,roughness,metalness:.05});
const sphere=new THREE.SphereGeometry(1,10,8);
const cyl=new THREE.CylinderGeometry(1,1,1,7);
const ico=new THREE.IcosahedronGeometry(1,0);
const boxgeo=new THREE.BoxGeometry(1,1,1);
const octa=new THREE.OctahedronGeometry(1,0);
const enemyTypes=[
 {name:'Wanderer',color:0x778c90,hp:35,speed:1.6,radius:.53,damage:10,reward:1,size:1},
 {name:'Skitter',color:0x7dd9c0,hp:24,speed:2.9,radius:.4,damage:7,reward:2,size:.7},
 {name:'Brute',color:0xbb7a8d,hp:120,speed:.94,radius:.65,damage:18,reward:4,size:1.2},
 {name:'Specter',color:0x9d81eb,hp:61,speed:2.15,radius:.48,damage:12,reward:3,size:.9},
 {name:'Infected',color:0xa5d568,hp:80,speed:1.85,radius:.6,damage:14,reward:3,size:1.1},
 {name:'Hollow',color:0xe2a56e,hp:51,speed:2.7,radius:.54,damage:10,reward:2,size:1}
];
const tmp=new THREE.Vector3();
function makeGlow(color,r=.28){return new THREE.Mesh(new THREE.SphereGeometry(r,10,8),new THREE.MeshBasicMaterial({color,transparent:true,opacity:.75,depthWrite:false}));}
function circleRing(radius,color,opacity=.45){const m=new THREE.Mesh(new THREE.RingGeometry(radius-.065,radius,48),new THREE.MeshBasicMaterial({color,transparent:true,opacity,side:THREE.DoubleSide,depthWrite:false}));m.rotation.x=-Math.PI/2;return m;}
// Original procedural "dark graveyard grass" — no grid, mossy and moody. CC0 by construction.
function makeGroundTexture(type){
 const S=512,c=document.createElement('canvas');c.width=c.height=S;const x=c.getContext('2d');
 // Per-map dark earth palette: cemetery = wet moss, village = rotted turf, facility = toxic moss, crypt = drowned, inferno = scorched.
 const P={
  cemetery:{base:'#14231a',g1:[52,86,48],g2:[86,120,66],g3:[20,40,26],dirt:[34,34,24]},
  village: {base:'#1d2016',g1:[74,76,42],g2:[110,104,60],g3:[30,32,18],dirt:[44,38,22]},
  facility:{base:'#12241f',g1:[44,92,78],g2:[72,132,110],g3:[18,44,38],dirt:[26,40,36]},
  crypt:   {base:'#0e1a20',g1:[40,78,86],g2:[70,120,128],g3:[14,34,40],dirt:[22,36,40]},
  inferno: {base:'#201108',g1:[96,56,28],g2:[150,88,38],g3:[40,20,10],dirt:[52,30,16]},
 }[type]||{base:'#14231a',g1:[52,86,48],g2:[86,120,66],g3:[20,40,26],dirt:[34,34,24]};
 x.fillStyle=P.base;x.fillRect(0,0,S,S);
 // soft tonal patches for large-scale variation
 for(let i=0;i<80;i++){const g=Math.random()<.5?P.g3:P.dirt;x.fillStyle=`rgba(${g[0]},${g[1]},${g[2]},${rand(.05,.16)})`;x.beginPath();x.ellipse(rand(0,S),rand(0,S),rand(18,70),rand(14,54),rand(0,TAU),0,TAU);x.fill();}
 // dirt / mud bald patches
 for(let i=0;i<34;i++){x.fillStyle=`rgba(${P.dirt[0]},${P.dirt[1]},${P.dirt[2]},${rand(.18,.4)})`;x.beginPath();x.ellipse(rand(0,S),rand(0,S),rand(8,34),rand(6,22),rand(0,TAU),0,TAU);x.fill();}
 // thousands of tiny grass blades (short strokes, varied greens + angle)
 x.lineWidth=1;x.lineCap='round';
 for(let i=0;i<9000;i++){
  const bx=rand(0,S),by=rand(0,S),len=rand(2.5,7),ang=-Math.PI/2+rand(-.5,.5),t=Math.random();
  const g=t<.62?P.g1:t<.9?P.g2:P.g3;x.strokeStyle=`rgba(${g[0]},${g[1]},${g[2]},${rand(.3,.8)})`;
  x.beginPath();x.moveTo(bx,by);x.lineTo(bx+Math.cos(ang)*len,by+Math.sin(ang)*len);x.stroke();
 }
 // scattered pale moss flecks + a few dark roots/cracks for an eerie feel
 for(let i=0;i<260;i++){const g=P.g2;x.fillStyle=`rgba(${g[0]+20},${g[1]+20},${g[2]+10},${rand(.05,.22)})`;x.fillRect(rand(0,S),rand(0,S),rand(.6,2),rand(.6,2));}
 x.strokeStyle='rgba(6,10,8,.5)';
 for(let i=0;i<26;i++){x.lineWidth=rand(.6,1.8);x.beginPath();let px=rand(0,S),py=rand(0,S);x.moveTo(px,py);for(let s=0;s<4;s++){px+=rand(-22,22);py+=rand(-22,22);x.lineTo(px,py);}x.stroke();}
 const t=new THREE.CanvasTexture(c);t.wrapS=t.wrapT=THREE.RepeatWrapping;t.repeat.set(20,20);t.colorSpace=THREE.SRGBColorSpace;t.anisotropy=8;return t;
}
export class GraveyardEngine {
 constructor(canvas,events={}){
  this.canvas=canvas;this.events=events;this.renderer=new THREE.WebGLRenderer({canvas,antialias:true,alpha:false,powerPreference:'high-performance'});
  this.preset=graphicsPreset(profile.settings.graphics??.5);this.budget=BUDGETS[this.preset];this.renderer.setPixelRatio(Math.min(devicePixelRatio||1,this.budget.dpr));this.renderer.outputColorSpace=THREE.SRGBColorSpace;this.renderer.toneMapping=THREE.ACESFilmicToneMapping;this.renderer.toneMappingExposure=1.55;
  this.renderer.shadowMap.enabled=false;this.renderer.shadowMap.type=THREE.PCFSoftShadowMap;this.scene=new THREE.Scene();this.scene.background=new THREE.Color(0x101925);this.scene.fog=new THREE.FogExp2(0x101925,.017);
  this.camera=new THREE.PerspectiveCamera(52,window.innerWidth/Math.max(1,window.innerHeight),.1,200);this.camera.position.set(14,24,19);this.camera.lookAt(0,0,0);
  this.clock=new THREE.Clock();this.world=new THREE.Group();this.scene.add(this.world);
  this.scene.add(new THREE.HemisphereLight(0xc8dcda,0x0d1620,1.85));
  const moon=new THREE.DirectionalLight(0xc5cde0,2.3);moon.position.set(-22,32,-18);this.scene.add(moon);moon.castShadow=true;moon.shadow.mapSize.set(1024,1024);moon.shadow.camera.left=-30;moon.shadow.camera.right=30;moon.shadow.camera.top=30;moon.shadow.camera.bottom=-30;moon.shadow.normalBias=.04;this.sun=moon;
  const pink=new THREE.DirectionalLight(0xc77bd6,1.2);pink.position.set(19,15,18);this.scene.add(pink);
  const amber=new THREE.DirectionalLight(0xffb06a,.5);amber.position.set(-16,10,22);this.scene.add(amber);
  this.glow=new THREE.PointLight(0x9fe9c6,24,14,2);this.scene.add(this.glow);
  this.loader=new GLTFLoader();this.models={};this.loading=this.loadAssets();
  this.keys=new Set();this.touch={x:0,z:0};this.projectileMaterials=new Map();this.projectilePool=[];this.focusedShrine=null;this.combo=0;this.comboClock=0;this.fps=60;this.fpsFrames=0;this.fpsWindow=0;this.currentEnemyCap=this.budget.enemies;this.status='menu';this.previews=[];this.elapsed=0;this.frameCount=0;this.composer=null;this.useBloom=false;this.bloomPass=null;
  window.addEventListener('keydown',e=>{if(['KeyW','KeyA','KeyS','KeyD','ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Space'].includes(e.code))e.preventDefault();this.keys.add(e.code);if(!e.repeat&&e.code==='KeyQ')this.activateAbility('dash');if(!e.repeat&&e.code==='KeyE')this.activateAbility('nova');if(!e.repeat&&e.code==='KeyF')this.interact();if(!e.repeat&&e.code==='Space')this.jump();if(e.code==='Escape'&&this.status==='playing')this.pause();else if(e.code==='Escape'&&this.status==='paused')this.resume();});
  window.addEventListener('keyup',e=>this.keys.delete(e.code));
  window.addEventListener('blur',()=>{if(this.status==='playing')this.pause()});
  window.addEventListener('resize',()=>this.resize());this.resize();this.makeMenuWorld();
  this.renderer.setAnimationLoop(()=>this.animate());
 }
 async loadAssets(){
  const ASSET_BASE=import.meta.env.BASE_URL.replace(/\/$/,'');
  const files={Knight:'/assets/models/heroes/Knight.glb',Mage:'/assets/models/heroes/Mage.glb',Ranger:'/assets/models/heroes/Ranger.glb',Rogue:'/assets/models/heroes/Rogue.glb',Rogue_Hooded:'/assets/models/heroes/Rogue_Hooded.glb',Barbarian:'/assets/models/heroes/Barbarian.glb',RigIdle:'/assets/models/heroes/Rig_Medium_General.glb',RigMove:'/assets/models/heroes/Rig_Medium_MovementBasic.glb',DeadTree:'/assets/models/nature/DeadTree_1.gltf',TwistedTree:'/assets/models/nature/TwistedTree_1.gltf',Chest:'/assets/models/fantasy/Chest_Wood.gltf',EyeDrone:'/assets/models/scifi/Enemy_EyeDrone.gltf',Alien:'/assets/models/aliens/Alien_Cyclop.gltf'};
  const kit=['pillar','barrel','crate','chest_common','chest_uncommon','chest_rare','chest_rare_mimic','artifact','sword_rare','dagger_common','dagger_rare','staff_rare','staff_uncommon','staff_common','crossbow_common','crossbow_rare','axe_rare','hammer_common','spellBook','barrelDark'];
  for(const name of kit)files['Dungeon'+name]='/assets/models/kaykit/'+name+'.gltf.glb';
  for(const name of ['Cauldron','Potion_1','Lantern_Wall','Sword_Bronze','WeaponStand','Barrel','Crate_Wooden','CandleStick_Triple','Banner_1','Chandelier','Torch_Metal','Coin_Pile','Key_Gold'])files['Fantasy'+name]='/assets/models/fantasy/'+name+'.gltf';
  await Promise.all(Object.entries(files).map(async ([name,url])=>{
   try {const data=await this.loader.loadAsync(ASSET_BASE+url);this.models[name]=data;}catch(e){console.warn('Model unavailable; fallback enabled',name,e);}
  }));this.events.assets?.(Object.keys(this.models).length);return this.models;
 }
 _setupBloom(){try{const w=window.innerWidth,h=window.innerHeight;const mob=/Mobi|Android|iPhone|iPad|iPod|Silk/i.test(navigator.userAgent||'');this.composer=new EffectComposer(this.renderer);this.composer.addPass(new RenderPass(this.scene,this.camera));this.bloomPass=new UnrealBloomPass(new THREE.Vector2(w,h),mob?.42:.55,.55,.82);this.composer.addPass(this.bloomPass);this.composer.addPass(new OutputPass());this.composer.setSize(w,h);}catch(err){this.composer=null;this.useBloom=false;}}
 resize(){const w=window.innerWidth,h=window.innerHeight;this.renderer.setSize(w,h,false);if(this.composer){this.composer.setSize(w,h);this.bloomPass?.setSize(w,h);}const width=13.2;if(this.camera.isPerspectiveCamera){this.camera.aspect=w/Math.max(1,h);}else{this.camera.left=-width;this.camera.right=width;this.camera.top=width*h/w;this.camera.bottom=-width*h/w;}this.camera.updateProjectionMatrix();}
 disposeGenerated(root){if(!root)return;root.traverse?.(obj=>{if(!obj.isMesh)return;if(obj.geometry&&!([sphere,boxgeo,ico,cyl].includes(obj.geometry)))obj.geometry.dispose();if(Array.isArray(obj.material))obj.material.forEach(m=>m.dispose());else obj.material?.dispose();});}

 clearWorld(){
  if(this.enemyBatch){this.enemyBatch.dispose();this.enemyBatch=null;}
  this.chests=[];this.closestChest=null;this.terrain=null;this.v3Props=[];this.heldWeapon=null;
  for(const f of this.fx||[]){if(f.mesh?.geometry&&!([sphere,boxgeo,ico,cyl].includes(f.mesh.geometry)))f.mesh.geometry.dispose();f.mesh?.material?.dispose?.();}
  for(const pickup of this.pickups||[])pickup.mesh?.material?.dispose?.();
  for(const boss of this.enemies||[])if(boss.boss)this.disposeGenerated(boss.mesh);
  for(const orbit of this.orbitMeshes||[]){orbit.geometry?.dispose();orbit.material?.dispose();}
  if(this.floorMesh){this.floorMesh.geometry.dispose();this.floorMesh.material.dispose();this.floorTexture?.dispose();this.floorMesh=null;}
  for(const o of this.decorOwned||[]){o.material?.dispose?.();}this.decorOwned=[];
  for(const h of this.hazards||[]){h.mesh?.material?.dispose?.();h.mesh?.geometry?.dispose?.();h.ring?.material?.dispose?.();h.ring?.geometry?.dispose?.();}
  this.world.clear();this.enemies=[];this.projectiles=[];this.projectilePool=[];this.pickups=[];this.fx=[];this.decor=[];this.orbiters=[];this.shrines=[];this.focusedShrine=null;this.partnerMesh=null;this.partnerTarget=null;this.v3Crystal=null;this.hazards=[];
 }
 cloneModel(name,height=1.75){const d=this.models[name];if(!d)return null;const g=cloneSkinned(d.scene);const bb=new THREE.Box3().setFromObject(g),sz=bb.getSize(new THREE.Vector3()),center=bb.getCenter(new THREE.Vector3());const scale=height/Math.max(.01,sz.y);g.scale.setScalar(scale);g.position.set(-center.x*scale,-bb.min.y*scale,-center.z*scale);const p=new THREE.Group();p.add(g);return p;}
 attachWeapon(id){
  if(!this.hero)return;this.heldWeapon?.parent?.remove(this.heldWeapon);this.heldWeapon=null;
  const lookup={boneblades:'sword_rare',ember:'staff_common',shrapnel:'crossbow_common',voidlance:'staff_rare',scythe:'axe_rare',spores:'staff_uncommon',drone:'artifact',nova:'staff_rare',orbit:'dagger_rare',coil:'staff_uncommon',frost:'staff_common',mines:'barrelDark',ravens:'artifact',blood:'dagger_rare'};
  const name=findWeapon(id)?.model||lookup[id]||'sword_rare',model=this.cloneModel('Dungeon'+name,.72);
  if(model){model.position.set(.53,.91,.22);model.rotation.set(-.4,0,-.45);this.hero.add(model);this.heldWeapon=model;}
 }
 jump(){if(this.status!=='playing'||!this.player?.grounded||this.player.jumpCooldown>0)return false;this.player.vy=8.5;this.player.grounded=false;this.player.jumpCooldown=.22;this.events.jump?.();return true;}
 makePlayerMesh(char,skinId){
  const p=this.cloneModel(char.model,1.8)||new THREE.Group();
  if(!p.children.length){const body=new THREE.Mesh(new THREE.CapsuleGeometry(.43,.7,4,8),material(0x8fb6db));body.position.y=.9;p.add(body);}
  const skin=SKINS.find(x=>x.id===skinId)||SKINS[0];const color=new THREE.Color(skin.hex);const style=skin.style||'flat';
  // V12: REPLACE the model's washed-out texture with a solid, vivid, style-driven
  // material so skins read as truly different looks and never render white.
  const dark=color.clone().multiplyScalar(.55);
  p.traverse(o=>{if(o.isMesh){
   const b={color:color.clone(),flatShading:true};
   // V13.1: emissive toned down across the board so the hero reads as colored,
   // not a glowing blob — bloom was amplifying these into eye-searing white.
   if(style==='metal'){b.metalness=.95;b.roughness=.28;b.emissive=dark.clone().multiplyScalar(.12);}
   else if(style==='ghost'){b.transparent=true;b.opacity=.62;b.emissive=color.clone().multiplyScalar(.35);b.metalness=.1;b.roughness=.45;b.depthWrite=false;}
   else if(style==='ember'){b.emissive=color.clone().multiplyScalar(.45);b.metalness=.2;b.roughness=.55;}
   else if(style==='frost'){b.metalness=.5;b.roughness=.18;b.transparent=true;b.opacity=.88;b.emissive=color.clone().multiplyScalar(.14);}
   else {b.metalness=.18;b.roughness=.55;b.emissive=color.clone().multiplyScalar(.09);}
   o.material=new THREE.MeshStandardMaterial(b);o.castShadow=true;}});
  // A subtle aura reads the skin color at distance without blooming out (V13.1: toned way down).
  const halo=circleRing(.9,skin.hex,.5);halo.position.y=.05;p.add(halo);
  const aura=new THREE.Mesh(new THREE.SphereGeometry(.82,14,10),new THREE.MeshBasicMaterial({color:skin.hex,transparent:true,opacity:style==='ghost'?.2:.1,depthWrite:false,side:THREE.BackSide}));aura.position.y=1.0;p.add(aura);
  const rim=new THREE.PointLight(color.getHex(),1.1,4.6,2.2);rim.position.set(0,1.35,0);p.add(rim);
  return p;
 }
 // --- Co-op: a live avatar of the other player, driven by network state ---
 setPartner(s){
  if(!s)return;this.partner=Object.assign(this.partner||{},s);
  if(!this.partnerMesh){const pc=CHARACTERS.find(c=>c.id===s.ch)||CHARACTERS[0];this.partnerMesh=this.makePlayerMesh(pc,s.sk||'crimson');const ring=circleRing(1.42,0xffe08a,.6);ring.position.y=.07;this.partnerMesh.add(ring);const beacon=makeGlow(0xffd36a,.2);beacon.position.y=2.5;this.partnerMesh.add(beacon);this.partnerMesh.position.set(s.x||0,s.y||0,s.z||0);this.partnerTarget=new THREE.Vector3(s.x||0,s.y||0,s.z||0);this.world.add(this.partnerMesh);}
  if(this.partnerTarget)this.partnerTarget.set(s.x||0,s.y||0,s.z||0);
 }
 clearPartner(){if(this.partnerMesh){this.world.remove(this.partnerMesh);this.disposeGenerated?.(this.partnerMesh);}this.partnerMesh=null;this.partnerTarget=null;this.partner=null;}
 netState(){const p=this.player;if(!p||!p.pos)return null;return {t:'s',x:+p.pos.x.toFixed(2),z:+p.pos.z.toFixed(2),y:+((p.y||0)).toFixed(2),hp:Math.ceil(p.hp),mh:p.maxHp,lv:this.level,al:this.status!=='ended',k:this.kills,ch:p.char.id,sk:p.skin};}
 buildFloor(map){
  const tex=makeGroundTexture(map.id);const ground=new THREE.Mesh(new THREE.PlaneGeometry(170,170),new THREE.MeshStandardMaterial({map:tex,roughness:1,metalness:0}));ground.rotation.x=-Math.PI/2;ground.position.y=-.05;this.world.add(ground);this.floorMesh=ground;this.floorTexture=tex;
  // V9: clean ground — no carved rings. A single soft central dais marks the start.
  const dais=new THREE.Mesh(new THREE.CircleGeometry(5.5,48),new THREE.MeshStandardMaterial({color:0x1c2a22,roughness:.95,transparent:true,opacity:.5}));dais.rotation.x=-Math.PI/2;dais.position.y=.004;this.world.add(dais);
 }
 buildDecor(map){
  const count=72,stone=new THREE.MeshStandardMaterial({color:map.id==='facility'?0x53646b:0x515c5d,roughness:1});
  const parts=[
   new THREE.InstancedMesh(boxgeo,stone,count),
   new THREE.InstancedMesh(boxgeo,stone,count),
   new THREE.InstancedMesh(boxgeo,new THREE.MeshStandardMaterial({color:0x79807b,roughness:1}),count),
  ];
  const dummy=new THREE.Object3D();for(let i=0;i<count;i++){
   const a=rand(0,TAU),r=rand(10,69),x=Math.cos(a)*r,z=Math.sin(a)*r,h=rand(.7,1.35),w=rand(.45,.8),rot=rand(-.6,.6);
   dummy.rotation.set(0,rot,0);dummy.position.set(x,h*.5,z);dummy.scale.set(w,h,.25);dummy.updateMatrix();parts[0].setMatrixAt(i,dummy.matrix);
   dummy.position.y=h;dummy.scale.set(w+.12,.14,.35);dummy.updateMatrix();parts[1].setMatrixAt(i,dummy.matrix);
   dummy.position.set(x,h*.56,z+.15);dummy.scale.set(.06,.32,.07);dummy.updateMatrix();parts[2].setMatrixAt(i,dummy.matrix);
   this.terrain?.addBox(x,z,w*.53,.25,h+.18);
  }
  for(const mesh of parts){mesh.instanceMatrix.needsUpdate=true;mesh.frustumCulled=false;this.world.add(mesh);}this.decorOwned=[...parts];
  // World V3 owns all solid trees, rocks and elevated geometry (collisions match visuals).
  if(this.status==='menu')return;
  // Side objectives: touching an altar and pressing F grants a short power spike.
  for(let i=0;i<4;i++){
   const a=.42+i*TAU/4,r=15+i*6.4,x=Math.cos(a)*r,z=Math.sin(a)*r;
   const g=new THREE.Group(),pillar=new THREE.Mesh(new THREE.CylinderGeometry(.65,.85,.6,7),material(0x69736f));pillar.position.y=.3;g.add(pillar);
   const rune=circleRing(1.33,0xe3bd7d,.65);rune.position.y=.045;g.add(rune);
   const crystal=new THREE.Mesh(new THREE.OctahedronGeometry(.35),new THREE.MeshStandardMaterial({color:0xc5b57d,emissive:0x6a5420,emissiveIntensity:.62,metalness:.4}));crystal.position.y=.94;g.add(crystal);
   g.position.set(x,0,z);this.world.add(g);this.shrines.push({mesh:g,x,z,rune,crystal,used:false});
  }
 }
 makeWaterTexture(){
  // V12: richer realistic water — depth gradient + two octaves of soft caustics + bright specular glints.
  const S=512,c=document.createElement('canvas');c.width=c.height=S;const x=c.getContext('2d');
  const g=x.createLinearGradient(0,0,0,S);g.addColorStop(0,'#05222e');g.addColorStop(.5,'#0b3e4d');g.addColorStop(1,'#063039');x.fillStyle=g;x.fillRect(0,0,S,S);
  try{x.filter='blur(3px)';}catch{}
  for(let i=0;i<26;i++){x.strokeStyle=`rgba(140,220,235,${rand(.03,.08)})`;x.lineWidth=rand(8,20);x.beginPath();const y=rand(0,S);x.moveTo(-30,y);for(let xx=-30;xx<=S+30;xx+=16)x.lineTo(xx,y+Math.sin(xx*.03+i*1.7)*rand(10,26));x.stroke();}
  try{x.filter='blur(1px)';}catch{}
  for(let i=0;i<64;i++){x.strokeStyle=`rgba(175,235,245,${rand(.03,.08)})`;x.lineWidth=rand(1,2.5);x.beginPath();const y=rand(0,S);x.moveTo(-10,y);for(let xx=-10;xx<=S+10;xx+=8)x.lineTo(xx,y+Math.sin(xx*.12+i)*rand(2,6));x.stroke();}
  for(let i=0;i<72;i++){const cx=rand(0,S),cy=rand(0,S),r=rand(3,13);const rg=x.createRadialGradient(cx,cy,0,cx,cy,r);rg.addColorStop(0,`rgba(205,245,255,${rand(.07,.2)})`);rg.addColorStop(1,'rgba(205,245,255,0)');x.fillStyle=rg;x.beginPath();x.arc(cx,cy,r,0,TAU);x.fill();}
  x.filter='none';
  const t=new THREE.CanvasTexture(c);t.wrapS=t.wrapT=THREE.RepeatWrapping;t.repeat.set(2,2);t.colorSpace=THREE.SRGBColorSpace;t.anisotropy=4;return t;
 }
 makeMoonTexture(){
  const S=256,c=document.createElement('canvas');c.width=c.height=S;const x=c.getContext('2d');
  const grd=x.createRadialGradient(S*.4,S*.38,10,S*.5,S*.5,S*.6);grd.addColorStop(0,'#ffe0a8');grd.addColorStop(.55,'#ffb257');grd.addColorStop(1,'#e07a1f');
  x.fillStyle=grd;x.fillRect(0,0,S,S);
  for(let i=0;i<60;i++){const cx=rand(0,S),cy=rand(0,S),r=rand(3,20);x.fillStyle=`rgba(150,78,20,${rand(.1,.3)})`;x.beginPath();x.arc(cx,cy,r,0,TAU);x.fill();x.fillStyle=`rgba(255,224,170,${rand(.08,.2)})`;x.beginPath();x.arc(cx-r*.25,cy-r*.25,r*.7,0,TAU);x.fill();}
  const t=new THREE.CanvasTexture(c);t.colorSpace=THREE.SRGBColorSpace;return t;
 }
 buildHalloween(map){
  // V6: water + Halloween theming layered onto any map.
  this.waters=[];this.waterSheen=[];this.bats=[];this.pumpkins=[];this.wisps=[];
  this.scene.fog.color.copy(new THREE.Color(map.fog||0x101923)).lerp(new THREE.Color(0x2a1536),.55);
  this.scene.background.copy(new THREE.Color(map.color||0x101925)).lerp(new THREE.Color(0x120a1c),.55);
  // enormous cratered harvest moon + layered halo + warm cast
  const moon=new THREE.Mesh(new THREE.SphereGeometry(12,32,20),new THREE.MeshBasicMaterial({map:this.makeMoonTexture(),fog:false}));moon.position.set(-46,38,-60);this.world.add(moon);
  for(const [hr,op] of [[15,.2],[19,.12],[25,.06]]){const halo=new THREE.Mesh(new THREE.SphereGeometry(hr,22,16),new THREE.MeshBasicMaterial({color:0xff7a1a,transparent:true,opacity:op,fog:false,side:THREE.BackSide}));halo.position.copy(moon.position);this.world.add(halo);}
  const moonLight=new THREE.PointLight(0xffb060,2.1,220,1.2);moonLight.position.copy(moon.position);this.world.add(moonLight);
  // V9: fewer, larger, cleaner water pools — smooth reflective surface, soft shore (no hard rings)
  const wtex=this.makeWaterTexture();
  for(const [wx,wz,wr] of [[-30,22,11],[33,-16,10],[12,38,8],[-42,-26,9],[40,30,8]]){
   const shore=new THREE.Mesh(new THREE.CircleGeometry(wr+1.2,44),new THREE.MeshStandardMaterial({color:0x12201c,roughness:.95,transparent:true,opacity:.6}));shore.rotation.x=-Math.PI/2;shore.position.set(wx,-.03,wz);this.world.add(shore);
   const w=new THREE.Mesh(new THREE.CircleGeometry(wr,56),new THREE.MeshStandardMaterial({color:0x0a3243,emissive:0x0c4254,emissiveIntensity:.55,transparent:true,opacity:.93,roughness:.07,metalness:.9,map:wtex}));
   w.rotation.x=-Math.PI/2;w.position.set(wx,-.015,wz);this.world.add(w);this.waters.push(w);
   // a faint rippling surface sheen that drifts the opposite way for layered depth
   const sheen=new THREE.Mesh(new THREE.CircleGeometry(wr-.3,40),new THREE.MeshBasicMaterial({color:0x9fe3ff,transparent:true,opacity:.07,map:wtex,depthWrite:false,blending:THREE.AdditiveBlending}));
   sheen.rotation.x=-Math.PI/2;sheen.position.set(wx,.005,wz);this.world.add(sheen);this.waterSheen=this.waterSheen||[];this.waterSheen.push(sheen);
  }
  // drifting spectral wisps — eerie green soul-lights floating over the field
  for(let i=0;i<14;i++){const wsp=makeGlow(0x7dffb0,.16);const cx=rand(-55,55),cz=rand(-55,55);wsp.position.set(cx,rand(1.2,3.4),cz);this.world.add(wsp);this.wisps.push({mesh:wsp,cx,cz,y:wsp.position.y,phase:rand(0,TAU),sp:rand(.15,.4)});}
  if(this.status==='menu')return;
  // jack-o'-lanterns with inner glow
  for(let i=0;i<15;i++){
   const a=rand(0,TAU),r=rand(11,58),x=Math.cos(a)*r,z=Math.sin(a)*r,free=this.terrain?.findFree?.(x,z,0,.5)||{x,z};
   const g=new THREE.Group();
   const body=new THREE.Mesh(new THREE.SphereGeometry(.42,12,9),new THREE.MeshStandardMaterial({color:0xff7a1a,emissive:0xff5300,emissiveIntensity:.6,roughness:.55}));body.scale.set(1.05,.82,1.05);body.position.y=.36;g.add(body);
   const stem=new THREE.Mesh(new THREE.CylinderGeometry(.045,.08,.2,5),material(0x4f7a3a));stem.position.y=.72;g.add(stem);
   const light=new THREE.PointLight(0xff8a2e,1.15,4.6,2);light.position.set(free.x,.52,free.z);this.world.add(light);
   g.position.set(free.x,0,free.z);this.world.add(g);this.pumpkins.push({light,phase:rand(0,TAU)});
  }
  // bats circling overhead
  for(let i=0;i<12;i++){
   const bat=new THREE.Group(),bm=new THREE.MeshStandardMaterial({color:0x1a1420,emissive:0x140e1c,emissiveIntensity:.3});
   bat.add(new THREE.Mesh(new THREE.SphereGeometry(.1,6,5),bm));
   const wL=new THREE.Mesh(new THREE.ConeGeometry(.17,.5,3),bm);wL.rotation.z=Math.PI/2;wL.position.x=-.22;bat.add(wL);
   const wR=new THREE.Mesh(new THREE.ConeGeometry(.17,.5,3),bm);wR.rotation.z=-Math.PI/2;wR.position.x=.22;bat.add(wR);
   bat.scale.setScalar(rand(.8,1.4));this.world.add(bat);
   this.bats.push({mesh:bat,wL,wR,a:rand(0,TAU),r:rand(9,32),y:rand(6,12),cx:rand(-16,16),cz:rand(-16,16),sp:rand(.3,.7)});
  }
 }
 _animAmbience(dt){
  for(const w of this.waters||[]){const m=w.material.map;if(m){m.offset.x+=dt*.02;m.offset.y+=dt*.013;}w.material.emissiveIntensity=.52+Math.sin(this.elapsed*1.3+w.position.x)*.12;}
  for(const s of this.waterSheen||[]){s.rotation.z+=dt*.09;if(s.material)s.material.opacity=.05+Math.abs(Math.sin(this.elapsed*.7+s.position.x))*.06;}
  for(const h of this.hazards||[]){if(h.mesh?.material){h.mesh.material.emissiveIntensity=(h.type==='lava'?1.25:.85)+Math.sin(this.elapsed*3+h.phase)*.35;h.mesh.material.opacity=.7+Math.sin(this.elapsed*2+h.phase)*.12;}if(h.ring)h.ring.rotation.z+=dt*.4;}
  for(const b of this.bats||[]){b.a+=dt*b.sp;b.mesh.position.set(b.cx+Math.cos(b.a)*b.r,b.y+Math.sin(b.a*2)*.7,b.cz+Math.sin(b.a)*b.r);b.mesh.rotation.y=-b.a+Math.PI/2;const flap=Math.sin(this.elapsed*13+b.a*4)*.7;b.wL.rotation.z=Math.PI/2+flap;b.wR.rotation.z=-Math.PI/2-flap;}
  for(const p of this.pumpkins||[])p.light.intensity=1.05+Math.sin(this.elapsed*7+p.phase)*.4;
  for(const w of this.wisps||[]){w.mesh.position.set(w.cx+Math.sin(this.elapsed*w.sp+w.phase)*4.5,w.y+Math.sin(this.elapsed*1.3+w.phase)*.55,w.cz+Math.cos(this.elapsed*w.sp*.8+w.phase)*4.5);if(w.mesh.material)w.mesh.material.opacity=.45+Math.sin(this.elapsed*2+w.phase)*.33;}
  if(this.v3Crystal){this.v3Crystal.rotation.y+=dt*.8;this.v3Crystal.rotation.x+=dt*.3;this.v3Crystal.position.y=5.2+Math.sin(this.elapsed*1.4)*.3;}
  for(const fl of this.arenaPillars||[]){fl.flame.scale.y=.8+Math.sin(this.elapsed*9+fl.phase)*.22;fl.light.intensity=2.3+Math.sin(this.elapsed*11+fl.phase)*.8;}
  if(this.portal){const pr=this.portal;pr.ring.rotation.z+=dt*1.6;pr.inner.rotation.z-=dt*2.3;pr.inner.material.opacity=.72+Math.sin(this.elapsed*4)*.2;pr.light.intensity=3.4+Math.sin(this.elapsed*5)*1.1;pr.group.position.y=1.5+Math.sin(this.elapsed*1.8)*.14;}
 }
 makeMenuWorld(){this.status='menu';this.clearWorld();this.portal=null;this.arenaPillars=[];this.finalBoss=null;this.finalBossSpawned=false;this.buildFloor(MAPS[0]);buildWorldV3(this,MAPS[0]);this.buildDecor(MAPS[0]);this.buildHalloween(MAPS[0]);this.menuAvatar=new THREE.Group();const body=new THREE.Mesh(new THREE.CapsuleGeometry(.5,.8,4,8),material(0x839f91));body.position.y=.95;this.menuAvatar.add(body);this.world.add(this.menuAvatar);
  this.loading?.then(()=>{if(this.status!=='menu')return;const hero=this.makePlayerMesh(CHARACTERS[0],'default');this.world.remove(this.menuAvatar);this.menuAvatar=hero;this.world.add(hero);});}
 async start({character='warden',skin='default',map='cemetery',mutator='standard',relic='nightfall',boon=null,weapon=null,difficulty='normal',mode='survival'}={}){
  const char=CHARACTERS.find(c=>c.id===character)||CHARACTERS[0],setting=MAPS.find(m=>m.id===map)||MAPS[0];
  await this.loading;this.status='initializing';this.clearWorld();this.preset=graphicsPreset(profile.settings.graphics??.5);this.budget=BUDGETS[this.preset];this.currentEnemyCap=this.budget.enemies;this.renderer.setPixelRatio(Math.min(devicePixelRatio||1,this.budget.dpr));this.renderer.shadowMap.enabled=profile.settings.shadows===true&&this.preset==='high';this.useBloom=this.preset!=='low'&&profile.settings.particles!==false;if(this.useBloom&&!this.composer)this._setupBloom();this.resize();
  this.scene.background.set(setting.color);this.scene.fog.color.set(setting.fog);this.buildFloor(setting);buildWorldV3(this,setting);this.buildDecor(setting);this.buildHalloween(setting);this.enemyBatch=new EnemyBatch(this.world,this.budget.enemies);
  this.hero=this.makePlayerMesh(char,skin);this.world.add(this.hero);this.attachWeapon(char.weapon);this.hero.position.set(0,.01,0);
  this.animMixer=new THREE.AnimationMixer(this.hero);this.animations={};this.animCurrent=null;
  for(const [kind,src,name] of [['idle','RigIdle','Idle_A'],['run','RigMove','Running_A']]){const clip=this.models[src]?.animations?.find(a=>a.name===name);if(clip)this.animations[kind]=this.animMixer.clipAction(clip);}
  this.mutator=MUTATORS.find(m=>m.id===mutator)||MUTATORS[0];
  this.difficulty=DIFFICULTIES.find(d=>d.id===difficulty)||DIFFICULTIES[0];
  this.startWeapon=(weapon&&WEAPONS.some(w=>w.id===weapon))?weapon:char.weapon;
  this.player={pos:new THREE.Vector3(0,0,0),hp:char.hp+8*(profile.upgrades.health||0)+(char.id==='bruiser'?35:0),maxHp:char.hp+8*(profile.upgrades.health||0)+(char.id==='bruiser'?35:0),speed:char.speed*(char.id==='shade'?1.15:1)*(this.mutator.id==='turbo'?1.15:1)*(1+.015*(profile.upgrades.speed||0)),damage:char.damage*this.mutator.playerDamage*(1+.04*(profile.upgrades.power||0)),armor:char.armor,invuln:0,frenzy:0,face:new THREE.Vector3(1,0,0),char,skin,regen:(profile.upgrades.resilience||0)*.08+(char.id==='paladin'?.35:0)};
  this.player.y=0;this.player.vy=0;this.player.grounded=true;this.player.jumpCooldown=0;this.player.maxHp=Math.round(this.player.maxHp*this.mutator.playerHp);this.player.hp=this.player.maxHp;this.player.dashCooldown=0;this.player.novaCooldown=0;this.player.relic=RELICS.find(r=>r.id===relic)||RELICS[0];this.player.blessing=0;
  this.orbitMeshes=[];this.weapons={[this.startWeapon||char.weapon]:{level:1,next:0,evolved:false}};this.passives={};this.level=1;this.xp=0;this.earnedXP=0;this.required=levelRequired(1);this.kills=0;this.coins=0;this.souls=0;this.bossKills=0;this.evolutions=0;this.elapsed=0;this.spawnTimer=.32;this.bossWave=0;this.chestTimer=21;this.chests=[];this.closestChest=null;this.uiClock=0;this.wave=1;this.combo=0;this.comboClock=0;this.contractIndex=0;this.contracts=[{name:'CLEAR THE GATES',target:35,coins:40,souls:12},{name:'HOLD THE LINE',target:105,coins:75,souls:30},{name:'BREAK THE HORDE',target:220,coins:130,souls:55}];this.rush=false;this.fps=60;this.fpsWindow=0;this.fpsFrames=0;this.banished=new Set();this.rerolls=3;this.banishes=2;this.finalBossSpawned=false;this.finalBoss=null;this.portal=null;this.arenaPillars=[];this.overtime=false;this.mode=mode;this.depth=1;this.chamberActive=false;this.dungeonMult=1;this.hazards=[];
  // Pre-run blessing
  this.boon=boon;this.boonReward=1;this.player.lifesteal=0;
  if(boon==='fury')this.player.damage*=1.25;
  else if(boon==='fleet')this.player.speed*=1.15;
  else if(boon==='bulwark'){this.player.maxHp=Math.round(this.player.maxHp*1.25);this.player.hp=this.player.maxHp;}
  else if(boon==='leech')this.player.lifesteal=.025;
  else if(boon==='seer'){this.rerolls+=2;this.banishes+=1;}
  else if(boon==='fortune')this.boonReward=1.35;
  else if(boon==='arsenal'){const opts=WEAPONS.filter(w=>w.id!==char.weapon);const pick=opts[Math.floor(Math.random()*opts.length)];if(pick)this.weapons[pick.id]={level:1,next:0,evolved:false};}
  // V11: pre-compile every shader now so the first frames — and the first boss,
  // which reuses these same materials — pop in without a hitch.
  try{this.renderer.compile(this.scene,this.camera);}catch{}
  this.status='playing';this.runMap=map;
  this.events.start?.(char);this.events.toast?.(this.mode==='dungeon'?`THE DESCENT BEGINS · ${char.name.toUpperCase()}`:`THE NIGHT BEGINS · ${char.name.toUpperCase()}`);
  if(this.mode==='dungeon')this._startChamber(1);else this._populateHazards(setting,4);
 }

 pause(){if(this.status!=='playing')return;this.status='paused';this.events.pause?.();}
 resume(){if(this.status!=='paused')return;this.status='playing';this.events.resume?.();}
 moveStick(x,z){this.touch.x=x;this.touch.z=z;}
 nearest(x,z,range=Infinity,exclude=null){let best=null,d=range*range;for(const e of this.enemies){if(e.dead||e===exclude)continue;const dx=e.mesh.position.x-x,dz=e.mesh.position.z-z,v=dx*dx+dz*dz;if(v<d){d=v;best=e;}}return best;}
 spawnFinalBoss(){
  // THE GRAVEKEEPER — the one you have to beat. Kill it and a dawn portal opens.
  this.finalBossSpawned=true;
  const a=rand(0,TAU),r=13,rawX=this.player.pos.x+Math.cos(a)*r,rawZ=this.player.pos.z+Math.sin(a)*r,free=this.terrain?.findFree(rawX,rawZ,0,1.8)||{x:rawX,z:rawZ};
  const m=new THREE.Group();
  const armor=material(0x2b3a2f,0x0a1d10);armor.metalness=.2;
  const torso=new THREE.Mesh(new THREE.CapsuleGeometry(.72,.9,4,10),armor);torso.position.y=1.55;torso.scale.set(1.3,1.1,.92);m.add(torso);
  const head=new THREE.Mesh(new THREE.IcosahedronGeometry(.56,1),material(0xcfe8cf));head.position.y=2.78;m.add(head);
  const crownMat=material(0xe8c45a,0x5a4410);for(let i=0;i<7;i++){const spike=new THREE.Mesh(new THREE.ConeGeometry(.1,.42,5),crownMat);const ca=i/7*TAU;spike.position.set(Math.cos(ca)*.42,3.18,Math.sin(ca)*.42);m.add(spike);}
  const hornMat=material(0x7fe08a);for(const sign of [-1,1]){
   const horn=new THREE.Mesh(new THREE.ConeGeometry(.3,1.0,6),hornMat);horn.position.set(sign*.56,3.35,0);horn.rotation.z=sign*.42;m.add(horn);
   const eye=makeGlow(0x8dff7a,.14);eye.position.set(sign*.22,2.86,.46);m.add(eye);
  }
  const scythe=new THREE.Mesh(new THREE.TorusGeometry(.72,.09,6,10,Math.PI*1.15),material(0xd7fbe0,0x5aa877));scythe.position.set(1.15,2.0,0);scythe.rotation.set(Math.PI/2,0,.4);m.add(scythe);
  const aura=makeGlow(0x6cff9a,1.9);aura.position.y=1.6;m.add(aura);
  const mark=circleRing(2.5,0x8dff7a,.7);mark.position.y=.05;m.add(mark);
  m.scale.setScalar(1.35);m.position.set(free.x,0,free.z);this.world.add(m);
  const mod=1+this.elapsed/370+(this.wave-1)*.055,dm=this.difficulty||{};const hp=3400*mod*(dm.hpMul||1);
  const entry={mesh:m,type:2,hp,maxHp:hp,speed:.82*this.mutator.enemySpeed,radius:1.75,size:2.4,damage:30*(dm.dmgMul||1),value:900,dead:false,boss:true,final:true,slow:0,flash:0,phase:rand(0,TAU),orbitCooldown:0};
  this.enemies.push(entry);this.finalBoss=entry;
  this.buildArena();this.scene.fog.color.set(0x2a0a14);this.scene.background.set(0x180611);
  this.events.boss?.('warning');this.events.toast?.('☠☠ THE GRAVEKEEPER RISES · SLAY IT TO OPEN THE DAWN PORTAL');
 }
 buildArena(){
  // A ring of green flame-pillars rises for the finale. Decorative only (no collision) so you can never be trapped.
  const stone=material(0x3a3340,0x120a16);
  for(let i=0;i<12;i++){const ang=i/12*TAU,rr=21,x=Math.cos(ang)*rr,z=Math.sin(ang)*rr;
   const col=new THREE.Mesh(new THREE.CylinderGeometry(.55,.72,4.4,8),stone);col.position.set(x,2.2,z);this.world.add(col);
   const flame=new THREE.Mesh(new THREE.ConeGeometry(.52,1.5,7),new THREE.MeshStandardMaterial({color:0x8dff7a,emissive:0x4cff86,emissiveIntensity:2.2,transparent:true,opacity:.9}));flame.position.set(x,5.0,z);this.world.add(flame);
   const light=new THREE.PointLight(0x6cff9a,2.6,13,2);light.position.set(x,5.2,z);this.world.add(light);
   this.arenaPillars.push({col,flame,light,phase:i*.6});
  }
 }
 spawnVictoryPortal(pos){
  if(this.portal)return;
  const free=this.terrain?.findFree(pos.x,pos.z,0,1.2)||{x:pos.x,z:pos.z};
  const group=new THREE.Group();group.position.set(free.x,1.5,free.z);
  const ring=new THREE.Mesh(new THREE.TorusGeometry(1.6,.22,10,28),new THREE.MeshStandardMaterial({color:0x8be8ff,emissive:0x59c6ff,emissiveIntensity:2.6,metalness:.3,roughness:.2}));group.add(ring);
  const inner=new THREE.Mesh(new THREE.CircleGeometry(1.45,30),new THREE.MeshBasicMaterial({color:0xd6b8ff,transparent:true,opacity:.8,side:THREE.DoubleSide}));group.add(inner);
  const light=new THREE.PointLight(0x9fd8ff,3.4,20,2);group.add(light);
  const beam=new THREE.Mesh(new THREE.CylinderGeometry(1.3,1.3,22,16,1,true),new THREE.MeshBasicMaterial({color:0x8be8ff,transparent:true,opacity:.12,side:THREE.DoubleSide}));beam.position.y=10;group.add(beam);
  this.world.add(group);
  this.portal={group,ring,inner,light,x:free.x,z:free.z};
  this.events.boss?.('defeat');this.events.toast?.('✦ THE GRAVEKEEPER FALLS · STEP INTO THE DAWN PORTAL TO ESCAPE');
 }
 // --- Ground hazards: lava burns fast, toxic creep burns slower and slows you ---
 spawnHazard(x,z,r,type){
  const lava=type==='lava',col=lava?0xff5a1e:0x8be03a;
  const disc=new THREE.Mesh(new THREE.CircleGeometry(r,28),new THREE.MeshStandardMaterial({color:col,emissive:col,emissiveIntensity:lava?1.4:.95,roughness:.55,transparent:true,opacity:.8,depthWrite:false}));
  disc.rotation.x=-Math.PI/2;disc.position.set(x,.03,z);this.world.add(disc);
  const ring=circleRing(r,col,.6);ring.position.set(x,.05,z);this.world.add(ring);
  this.hazards.push({x,z,r,type,dps:lava?20:10,slow:lava?1:.6,mesh:disc,ring,phase:rand(0,TAU)});
 }
 _populateHazards(setting,count){
  const lavaMap=setting?.id==='inferno';
  for(let i=0;i<count;i++){
   const a=rand(0,TAU),d=rand(10,30),x=Math.cos(a)*d,z=Math.sin(a)*d;
   if(Math.hypot(x,z)<7)continue; // keep the spawn point clear
   const type=(lavaMap?Math.random()<.7:Math.random()<.4)?'lava':'creep';
   this.spawnHazard(x,z,rand(2.2,3.6),type);
  }
 }
 _clearHazards(){for(const h of this.hazards||[]){this.world.remove(h.mesh,h.ring);h.mesh?.material?.dispose?.();h.mesh?.geometry?.dispose?.();h.ring?.material?.dispose?.();h.ring?.geometry?.dispose?.();}this.hazards=[];}
 // --- Dungeon Dive: clear a chamber of foes, then descend into a deeper one ---
 aliveEnemies(){let n=0;for(const e of this.enemies)if(!e.dead)n++;return n;}
 _startChamber(depth){
  this.depth=depth;this.chamberActive=true;this.dungeonMult=1+(depth-1)*.2;this.wave=depth;
  const guardian=depth%5===0;
  const count=Math.min(Math.max(28,this.currentEnemyCap-12),6+depth*3);
  for(let i=0;i<count;i++)this.spawnEnemy();
  if(guardian)this.spawnEnemy(true);
  this._populateHazards(MAPS.find(m=>m.id===this.runMap)||MAPS[0],Math.min(6,1+Math.floor(depth/2)));
  this.scene.fog.color.lerp(new THREE.Color(guardian?0x2a0820:0x0a1622),.22);
  this.events.toast?.(guardian?`⚔ DEPTH ${depth} · CHAMBER GUARDIAN — SLAY IT TO DESCEND`:`▼ DEPTH ${depth} · CLEAR THE CHAMBER`);
 }
 _clearChamber(){
  this.chamberActive=false;
  this.spawnChest(this.depth>=3);
  const tier=this.depth>=10?3:this.depth>=6?2:this.depth>=3?1:0;
  this.dropPickup(this.player.pos.clone().add(new THREE.Vector3(1.6,0,0)),'relic',tier);
  this.coins+=40+this.depth*12;this.player.hp=Math.min(this.player.maxHp,this.player.hp+this.player.maxHp*.2);
  const a=rand(0,TAU),px=this.player.pos.x+Math.cos(a)*8,pz=this.player.pos.z+Math.sin(a)*8;
  this._spawnDescendPortal(new THREE.Vector3(px,0,pz));
  this.events.toast?.('✦ CHAMBER CLEARED · ENTER THE DESCENT FOR GREATER SPOILS');
 }
 _spawnDescendPortal(pos){
  if(this.portal)return;
  const free=this.terrain?.findFree(pos.x,pos.z,0,1.2)||{x:pos.x,z:pos.z};
  const group=new THREE.Group();group.position.set(free.x,1.5,free.z);
  const ring=new THREE.Mesh(new THREE.TorusGeometry(1.6,.22,10,28),new THREE.MeshStandardMaterial({color:0xc46bff,emissive:0x8a3cff,emissiveIntensity:2.2,metalness:.3,roughness:.2}));group.add(ring);
  const inner=new THREE.Mesh(new THREE.CircleGeometry(1.45,30),new THREE.MeshBasicMaterial({color:0x2a0a3a,transparent:true,opacity:.86,side:THREE.DoubleSide}));group.add(inner);
  const light=new THREE.PointLight(0xb06bff,3,18,2);group.add(light);
  this.world.add(group);
  this.portal={group,ring,inner,light,x:free.x,z:free.z,descend:true};
 }
 _descend(){
  if(this.portal){this.world.remove(this.portal.group);this.disposeGenerated?.(this.portal.group);this.portal=null;}
  this._clearHazards();
  this.player.hp=Math.min(this.player.maxHp,this.player.hp+this.player.maxHp*.12);
  this._startChamber((this.depth||1)+1);
 }
 spawnEnemy(boss=false){
  if(this.enemies.length>=this.currentEnemyCap)return;
  const a=rand(0,TAU),r=rand(14.5,19),roll=Math.random();
  const idx=boss?2:roll<.36?0:roll<.55?1:roll<.67?2:roll<.81?3:roll<.93?4:5;
  const t=enemyTypes[idx],scale=enemyScale(idx,boss),rawX=this.player.pos.x+Math.cos(a)*r,rawZ=this.player.pos.z+Math.sin(a)*r,free=this.terrain?.findFree(rawX,rawZ,0,enemyRadius(idx,boss))||{x:rawX,z:rawZ},position=new THREE.Vector3(free.x,0,free.z);
  let m;
  if(boss){
   m=new THREE.Group();const armor=material(0x524755,0x17070d);armor.metalness=.15;
   const torso=new THREE.Mesh(new THREE.CapsuleGeometry(.66,.77,4,9),armor);torso.position.y=1.34;torso.scale.set(1.15,1.02,.84);m.add(torso);
   const head=new THREE.Mesh(new THREE.IcosahedronGeometry(.47,1),material(0xb4a49b));head.position.y=2.41;m.add(head);
   const hornMat=material(0x9b7b6c);for(const sign of [-1,1]){
    const horn=new THREE.Mesh(new THREE.ConeGeometry(.23,.73,6),hornMat);horn.position.set(sign*.46,2.92,0);horn.rotation.z=sign*.36;m.add(horn);
    const eye=makeGlow(0xff776e,.09);eye.position.set(sign*.18,2.48,.4);m.add(eye);
   }
   const mark=circleRing(1.65,0xff706d,.65);mark.position.y=.045;m.add(mark);
   m.position.copy(position);this.world.add(m);
  }else{m=new THREE.Object3D();m.position.copy(position);}
  // V13: late game is where the fun lives — enemies get tankier AND their hits
  // scale with the clock, so a good build (not just a big HP pool) is what keeps you alive.
  const et=this.elapsed,dm=this.difficulty||{};
  let mod,dmgRamp;
  if(this.mode==='dungeon'){mod=this.dungeonMult||1;dmgRamp=this.dungeonMult||1;}
  else{mod=1+et/330+(et>240?Math.pow((et-240)/300,2)*.9:0)+(this.wave-1)*.05;dmgRamp=1+et/340*.9;}
  const hp=(boss?630:t.hp)*mod*(this.overtime?1.55:1)*(dm.hpMul||1);
  this.enemies.push({mesh:m,type:idx,hp,maxHp:hp,speed:(boss?1.0:t.speed)*(1+this.elapsed/2000)*this.mutator.enemySpeed,radius:enemyRadius(idx,boss),size:scale,damage:(boss?23:t.damage)*(dm.dmgMul||1)*(this.overtime?1.4:1)*dmgRamp,value:t.reward*(boss?36:1),dead:false,boss,slow:0,flash:0,phase:rand(0,TAU),orbitCooldown:0});
  if(boss){this.events.boss?.('warning');this.events.toast?.('☠ GRAVE TITAN · BOSS APPROACHING');}
 }
 damageEnemy(e,amount,kind='normal',knock=0){
  if(e.dead)return;const crit=Math.random()<(.04+(.05*(this.passives.crit||0)))?2:1;let d=amount*this.player.damage*((this.player.frenzy||0)>0?1.8:1)*(this.player.blessing>0?1.35:1)*(1+.1*(this.passives.might||0))*(1+.1*(this.passives.area||0)*(kind==='area'?1:0));if(this.player.char.id==='alchemist'&&(kind==='poison'||kind==='area'))d*=1.18;if(this.player.char.id==='hex')d*=1.12;
  e.hp-=d*crit;e.flash=.09;if(this.player.lifesteal>0)this.player.hp=Math.min(this.player.maxHp,this.player.hp+d*crit*this.player.lifesteal); if(knock){let v=e.mesh.position.clone().sub(this.player.pos);v.y=0;v.normalize();const px=e.mesh.position.x+v.x*knock,pz=e.mesh.position.z+v.z*knock,allowed=this.terrain?.resolve(px,pz,e.mesh.position.y,e.radius*.7)||{x:px,z:pz};e.mesh.position.x=allowed.x;e.mesh.position.z=allowed.z;}
  if(this.passives.crit&&crit>1||e.boss)this.events.hit?.({x:e.mesh.position.x,z:e.mesh.position.z,amount:Math.round(d*crit),critical:crit>1});
  if(e.hp<=0)this.killEnemy(e);
 }
 killEnemy(e){
  if(e.dead)return;e.dead=true;if(e.boss){this.world.remove(e.mesh);this.disposeGenerated(e.mesh);}this.kills++;
  if(this.comboClock>0)this.combo=Math.min(35,this.combo+1);else this.combo=1;this.comboClock=3.7;
  const bonus=comboMultiplier(this.combo);
  const rew=this.difficulty?.rewardMul||1;
  this.coins+=(e.boss?80:Math.random()<.24?2:0)*this.mutator.reward*(1+.12*(this.passives.fortune||0))*(this.boonReward||1)*rew;
  this.souls+=(e.boss?25:e.value)*this.mutator.reward*rew;
  if(e.boss){this.bossKills++;this.spawnChest(true);this.dropPickup(e.mesh.position.clone(),'relic',e.final?3:(Math.random()<.4?2:1));
   if(e.final){this.finalBoss=null;this.coins+=250;this.spawnVictoryPortal(e.mesh.position.clone());}
   else{this.events.boss?.('defeat');this.events.toast?.('TITAN SLAIN · OPEN ITS RELIC');}}
  else{this.dropPickup(e.mesh.position.clone(),'xp',e.value*1.6*bonus);const lowHp=this.player.hp/this.player.maxHp<.5;if(Math.random()<(lowHp?.15:.05))this.dropPickup(e.mesh.position.clone(),'heal',26);if(Math.random()<.045)this.dropPickup(e.mesh.position.clone(),'coin',6);
   // V13 lucky loot — rare chance for a tiered power gem; elites roll far more often, Fortune & hard modes stack the odds.
   const elite=e.type===2||e.type===3,luck=(elite?.022:.009)*(1+.5*(this.passives.fortune||0))*Math.min(2.4,this.difficulty?.rewardMul||1);if(Math.random()<luck)this.dropPickup(e.mesh.position.clone(),'relic',this.rollRelicTier());}
  const contract=this.contracts?.[this.contractIndex];if(contract&&this.kills>=contract.target){this.coins+=contract.coins;this.souls+=contract.souls;this.contractIndex++;this.events.toast?.(`✦ CONTRACT CLEARED · ${contract.name} · +${contract.coins} COINS`);}
  if(this.kills===1)this.events.toast?.('FIRST BLOOD');
 }
 dropPickup(pos,type,value){
  if(type==='xp'){
   // Merge nearby soul fragments before ever creating new draw calls.
   for(let i=this.pickups.length-1,iMin=Math.max(0,this.pickups.length-25);i>=iMin;i--){const q=this.pickups[i];if(q.type==='xp'&&Math.hypot(q.pos.x-pos.x,q.pos.z-pos.z)<2.7){q.value+=value;return;}}
  }
  if(this.pickups.length>=this.budget.pickups){
   // Soft cap: never lose a drop. Heal/coin apply instantly; XP merges into an existing orb (or falls through to make one).
   if(type==='heal'){this.player.hp=Math.min(this.player.maxHp,this.player.hp+value);return;}
   if(type==='coin'){this.coins+=value;return;}
   const q=this.pickups.find(p=>p.type==='xp');if(q){q.value+=value;return;}
  }
  if(type==='relic'){
   const RC=[0x5db7ff,0xb569ff,0xffb54d,0x8ffff0][value]||0x5db7ff;
   const gem=new THREE.Mesh(octa,new THREE.MeshStandardMaterial({color:RC,emissive:RC,emissiveIntensity:1.2,roughness:.18,metalness:.35}));
   gem.scale.setScalar(.34+value*.08);gem.position.set(pos.x,.6,pos.z);this.world.add(gem);
   let light=null;if(value>=2){light=new THREE.PointLight(RC,value>=3?3.6:2.2,8);light.position.set(pos.x,1.2,pos.z);this.world.add(light);}
   this.pickups.push({mesh:gem,pos:gem.position,type:'relic',value,tier:value,age:0,light});
   return;
  }
  const color=type==='chest'?0xe9c677:type==='coin'?0xffcf5a:type==='heal'?0xff718e:value>=10?0xc4abff:0x89e5c0;
  const mesh=new THREE.Mesh(type==='xp'?ico:type==='chest'?boxgeo:sphere,new THREE.MeshStandardMaterial({color,emissive:color,emissiveIntensity:type==='coin'?.6:.43,roughness:.35}));mesh.scale.setScalar(type==='chest'?.47:type==='coin'?.25:type==='heal'?.3:.19);
  mesh.position.set(pos.x,type==='chest'?.55:.33,pos.z);this.world.add(mesh);this.pickups.push({mesh,pos:mesh.position,type,value,age:0});
 }
 addXP(value){let xp=value*(1+.1*(this.passives.focus||0)+(this.player.char.id==='hex'?.12:0))*(this.boonReward||1)*(this.overtime?2:1)*(this.difficulty?.rewardMul||1);this.xp+=xp;this.earnedXP+=Math.round(xp);this.events.pickup?.();if(this.xp>=this.required){this.xp-=this.required;this.level++;this.required=levelRequired(this.level);this.status='levelup';this.events.levelUp?.(this.generateChoices());}}
 generateChoices(){
  const pool=[];
  for(const w of WEAPONS){const level=this.weapons[w.id]?.level||0;if(level<20&&!this.banished?.has(w.id)&&(level>0||Object.keys(this.weapons).length<6))pool.push({type:'weapon',id:w.id,title:w.name,icon:w.icon,desc:level?`Level ${level+1} · +damage, extra attacks, faster firing`:w.desc,level,rarity:w.rarity});}
  for(const p of PASSIVES){const level=this.passives[p.id]||0;if(level<(p.max||12)&&!this.banished?.has(p.id)&&(level>0||Object.keys(this.passives).length<6))pool.push({type:'passive',id:p.id,title:p.name,icon:p.icon,desc:p.desc,level,rarity:'passive'});}
  const result=[];
  // V5: less random — always offer at least one weapon so your arsenal keeps
  // growing; favor upgrades you already run, then fill the rest with variety.
  const weightedPick=arr=>{const weights=arr.map(p=>p.level>0?3:1);const sum=weights.reduce((a,b)=>a+b,0)||1;let n=Math.random()*sum;for(let i=0;i<arr.length;i++){n-=weights[i];if(n<0)return i;}return arr.length-1;};
  const weaponIdx=pool.map((p,i)=>p.type==='weapon'?i:-1).filter(i=>i>=0);
  if(weaponIdx.length){const local=weaponIdx.map(i=>pool[i]);const li=weightedPick(local);result.push(pool.splice(weaponIdx[li],1)[0]);}
  while(pool.length&&result.length<3){result.push(pool.splice(weightedPick(pool),1)[0]);}
  // V13: small chance a weapon choice is "empowered" — a +2 level jackpot pick.
  if(result.length&&Math.random()<.13){const ei=result.findIndex(c=>c.type==='weapon');if(ei>=0)result[ei].empowered=true;}
  return result;
 }
 selectUpgrade(choice){if(this.status!=='levelup')return;
  if(choice.type==='weapon'){const inc=choice.empowered?2:1;const w=this.weapons[choice.id];if(w)w.level+=inc;else this.weapons[choice.id]={level:inc,next:0,evolved:false};}
  else{this.passives[choice.id]=(this.passives[choice.id]||0)+1;if(choice.id==='vitality'){this.player.maxHp+=20;this.player.hp+=20;}}
  this.status='playing';this.events.toast?.(`${choice.title.toUpperCase()} · UPGRADED`);
  if(this.xp>=this.required){this.xp-=this.required;this.level++;this.required=levelRequired(this.level);this.status='levelup';this.events.levelUp?.(this.generateChoices());}
 }
 reroll(){if(this.status!=='levelup'||this.rerolls<=0)return null;this.rerolls--;this.events.toast?.(`REROLLED · ${this.rerolls} LEFT`);return this.generateChoices();}
 banish(id){if(this.status!=='levelup'||this.banishes<=0||!id)return null;this.banishes--;this.banished.add(id);this.events.toast?.(`BANISHED · ${this.banishes} LEFT`);return this.generateChoices();}
 skipUpgrade(){if(this.status!=='levelup')return;this.coins+=18;this.player.hp=Math.min(this.player.maxHp,this.player.hp+this.player.maxHp*.08);this.status='playing';this.events.toast?.('SKIPPED · +18 COINS · PATCHED UP');if(this.xp>=this.required){this.xp-=this.required;this.level++;this.required=levelRequired(this.level);this.status='levelup';this.events.levelUp?.(this.generateChoices());}}
 openChest(){
  const candidates=EVOLUTIONS.filter(e=>this.weapons[e.weapon]?.level>=8&&this.passives[e.passive]&&!this.weapons[e.weapon].evolved);
  if(candidates.length){const e=candidates[Math.floor(rand(0,candidates.length))];this.weapons[e.weapon].evolved=true;this.evolutions++;this.events.toast?.(`✦ EVOLUTION: ${e.name.toUpperCase()}!`);this.events.evolve?.(e);}
  else{this.coins+=65;this.souls+=25;this.player.hp=Math.min(this.player.maxHp,this.player.hp+25);this.addXP(35);this.events.toast?.('RELIC UNSEALED · +65 COINS · +35 XP');}
 }
 spawnProjectile(x,z,dir,damage,config={}){
  if(this.projectiles.length>=this.budget.projectiles)return;
  const color=config.color||0x9beadd;let material=this.projectileMaterials.get(color);
  if(!material){material=new THREE.MeshBasicMaterial({color});this.projectileMaterials.set(color,material);}
  const poolKey=config.visual||'orb';let mesh=this.projectilePool.find(m=>m.userData.visual===poolKey);
  if(mesh)this.projectilePool.splice(this.projectilePool.indexOf(mesh),1);
  else{
   const visual=poolKey==='bolt'?new THREE.ConeGeometry(.27,1.6,5):poolKey==='disc'?new THREE.TorusGeometry(.7,.18,5,10):poolKey==='shard'?new THREE.OctahedronGeometry(.77,0):poolKey==='flame'?new THREE.ConeGeometry(.47,1.25,7):poolKey==='meteor'?new THREE.DodecahedronGeometry(.8,0):sphere;
   const glowing=new THREE.MeshStandardMaterial({color,emissive:color,emissiveIntensity:poolKey==='meteor'?3.2:2.7,metalness:.1,roughness:.2});
   mesh=new THREE.Mesh(visual,glowing);mesh.userData.visual=poolKey;
   if(poolKey==='bolt'||poolKey==='flame')mesh.rotation.x=Math.PI/2;
  }
  mesh.visible=true;mesh.material.color.set(color);mesh.material.emissive.set(color);mesh.scale.setScalar(config.scale||.2);mesh.position.set(x,(this.player.y||0)+.83,z);
  if(poolKey==='bolt'||poolKey==='flame')mesh.rotation.x=Math.PI/2;
  if(!mesh.parent)this.world.add(mesh);
  const v=dir.clone().normalize();if(poolKey==='bolt'||poolKey==='flame')mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),v);this.projectiles.push({mesh,velocity:v,speed:(config.speed||11)*(this.player.char.id==='hacker'?1.15:1),damage,life:config.life||1.3,pierce:config.pierce||0,hit:new Set(),homing:config.homing||false,knock:config.knock||.13,impact:config.impact||0,visual:poolKey});
 }
 pulse(radius,damage,color,opts={}){
  if(profile.settings.particles!==false&&this.fx.length<this.budget.effects){const ring=circleRing(radius,color,.71);ring.position.set(this.player.pos.x,(this.player.y||0)+.12,this.player.pos.z);ring.scale.setScalar(.3);this.world.add(ring);this.fx.push({mesh:ring,age:0,duration:.36,maxscale:.82,kind:'ring'});}
  for(const e of this.enemies){if(e.dead)continue;const dx=e.mesh.position.x-this.player.pos.x,dz=e.mesh.position.z-this.player.pos.z;if(dx*dx+dz*dz<(radius+e.radius)**2&&Math.abs((e.mesh.position.y||0)-(this.player.y||0))<2){this.damageEnemy(e,damage,'area',opts.knock||.12);if(opts.slow)e.slow=Math.max(e.slow,opts.slow);}}
 }
 fire(id,w){
  const data=findWeapon(id);if(!data)return;const lvl=w.level,ev=w.evolved;const dmg=data.damage*(1+(lvl-1)*.22)*(ev?1.8:1),radius=1+(.12*(this.passives.area||0));const p=this.player.pos;
  const target=this.nearest(p.x,p.z,16);const base=target?target.mesh.position.clone().sub(p).setY(0).normalize():this.player.face.clone();
  const shot=(angle,d=dmg,extra={})=>{const v=base.clone().applyAxisAngle(new THREE.Vector3(0,1,0),angle);this.spawnProjectile(p.x,p.z,v,d,{color:data.color,scale:.19+lvl*.012,visual:'bolt',...extra});};
  if(id==='orbit'||id==='thorn')return;this.events.weapon?.(id);
  if(id==='quakes'){this.pulse((3.3+lvl*.3)*radius,dmg,data.color,{knock:1.1});return;}
  if(id==='fuse'){const enemy=this.nearest(p.x,p.z,14);this.pulseAt(enemy?.mesh.position||p,(2.4+lvl*.14)*radius,dmg*1.5,data.color);return;}
  if(id==='meteor'){const enemy=this.nearest(p.x,p.z,15);this.spawnMeteor(enemy?.mesh.position||p,dmg*1.4,(2.1+lvl*.2)*radius,data.color);return;}
  if(id==='wyrmfire'){const n=Math.min(18,6+Math.floor(lvl/2)+(ev?5:0));for(let i=0;i<n;i++)shot((i-(n-1)/2)*.135,dmg*.8,{visual:'flame',speed:10,life:.8,scale:.24});return;}
  if(id==='crystal'){for(let i=-2-Math.floor(lvl/3);i<=2+Math.floor(lvl/3);i++)shot(i*.11,dmg*.8,{visual:'shard',speed:13,life:1.45,pierce:1});return;}
  if(id==='sunbow'){for(let i=-1;i<=1;i+=2)shot(i*.1,dmg,{visual:'bolt',speed:20,life:2,pierce:2+Math.floor(lvl/3)});return;}
  if(id==='chakram'){for(let i=-1;i<=1;i+=2)shot(i*.32,dmg,{visual:'disc',speed:10,life:1.6,pierce:3+Math.floor(lvl/3),scale:.25});return;}
  if(id==='widow'){shot(rand(-.05,.05),dmg,{visual:'shard',speed:19,life:1.1,pierce:1});return;}
  if(id==='crossbow'){shot(0,dmg,{visual:'bolt',speed:19,life:2,pierce:2+Math.floor(lvl/3),scale:.26});return;}
  if(id==='spirits'){for(let i=0;i<2+(ev?3:0);i++)shot(rand(-.55,.55),dmg,{visual:'orb',homing:true,life:2.6,speed:9,scale:.23});return;}
  if(id==='hexbolt'){for(let i=-1;i<=1;i++)shot(i*.075,dmg*.64,{visual:'bolt',speed:17,life:1.2});return;}
  if(id==='scythe'){this.pulse((2.3+lvl*.18)*radius,dmg,data.color,{knock:.75});return;}
  if(id==='spores'){this.pulse((2.8+lvl*.2)*radius,dmg,data.color,{slow:.4});return;}
  if(id==='nova'){this.pulse((3.7+lvl*.18)*radius,dmg,data.color,{knock:1.1});return;}
  if(id==='frost'){this.pulse((3.2+lvl*.15)*radius,dmg,data.color,{slow:2.7,knock:.23});return;}
  if(id==='coil'){
   let center=target;const seen=new Set();for(let i=0;i<Math.min(12,3+Math.floor(lvl/2)+(ev?5:0)+(this.player.char.id==='storm'?1:0));i++){
    if(!center)break;seen.add(center);this.damageEnemy(center,dmg,'lightning',.12);
    if(profile.settings.particles!==false&&this.fx.length<this.budget.effects){const ring=circleRing(.48,data.color,.84);ring.position.copy(center.mesh.position);ring.position.y=.09;this.world.add(ring);this.fx.push({mesh:ring,age:0,duration:.2,maxscale:.8,kind:'ring'});}
    center=this.enemies.filter(e=>!seen.has(e)&&!e.dead&&e.mesh.position.distanceTo(center.mesh.position)<(4+lvl*.4)).sort((a,b)=>a.mesh.position.distanceTo(p)-b.mesh.position.distanceTo(p))[0];
   }return;
  }
  if(id==='mines'){if(this.fx.length>=this.budget.effects)return;const mine=new THREE.Mesh(new THREE.OctahedronGeometry(.35),material(0xb18af0,0x9b65ea));mine.position.set(p.x+rand(-2,2),.33,p.z+rand(-2,2));this.world.add(mine);this.fx.push({mesh:mine,age:-.1,duration:8,maxscale:1,kind:'mine',damage:dmg*1.7,radius:2.0});return;}
  if(id==='drone'){const count=ev?2:1;for(let i=0;i<count;i++)shot(rand(-.2,.2),dmg,{homing:true,scale:.22,speed:15,life:1.6});return;}
  if(id==='ravens'){for(let i=0;i<Math.min(6,2+Math.floor(lvl/2)+(ev?2:0));i++)shot(rand(-.65,.65),dmg,{homing:true,speed:9,life:1.5});return;}
  if(id==='shrapnel'){const n=5+Math.floor(lvl/2)+(ev?6:0);for(let i=0;i<n;i++)shot((i-(n-1)/2)*.13,dmg*.65,{speed:16,life:.57,knock:.26});return;}
  if(id==='voidlance'){for(let i=0;i<(ev?3:1);i++)shot((i-(ev?1:0))*.19,dmg,{scale:.23,life:2,speed:15,pierce:3+Math.floor(lvl/2)});return;}
  if(id==='blood'){for(let i=0;i<1+(ev?2:0);i++)shot((i-(ev?1:0))*.18,dmg,{homing:true,speed:12});this.player.hp=Math.min(this.player.maxHp,this.player.hp+.26*lvl);return;}
  if(id==='tempest'){const n=10+lvl+(ev?8:0);for(let i=0;i<n;i++)shot(i*TAU/n,dmg*.8,{visual:'bolt',speed:15,life:1.25,pierce:1+Math.floor(lvl/4)});return;}
  if(id==='starfall'){const n=2+Math.floor(lvl/3)+(ev?3:0);for(let i=0;i<n;i++){const ang=rand(0,TAU),rr=rand(2.2,9);this.spawnMeteor(new THREE.Vector3(p.x+Math.cos(ang)*rr,0,p.z+Math.sin(ang)*rr),dmg*1.2,(1.9+lvl*.14)*radius,data.color);}return;}
  for(let i=0;i<1+Math.floor(lvl/3)+(ev?2:0);i++)shot((i-(Math.floor(lvl/3)+(ev?2:0))/2)*.13,dmg,{homing:id==='boneblades'||id==='ember',pierce:id==='boneblades'?1:0});
 }
 updateCombat(dt){
  const cdr=1-.08*(this.passives.haste||0)-(this.player.char.id==='ranger'?.15:0);
  for(const [id,w] of Object.entries(this.weapons)){
   if(id==='orbit'||id==='thorn'){
    const count=Math.min(9,2+Math.floor(w.level/2)+(w.evolved?4:0));for(let j=0;j<count;j++){
     const a=this.elapsed*2.35+j*TAU/count,r=1.72+(.11*w.level)+(.12*(this.passives.area||0));const x=this.player.pos.x+Math.cos(a)*r,z=this.player.pos.z+Math.sin(a)*r;
     if(!this.orbitMeshes[j]){const mesh=new THREE.Mesh(id==='thorn'?new THREE.ConeGeometry(.28,.65,5):new THREE.OctahedronGeometry(.25),new THREE.MeshStandardMaterial({color:id==='thorn'?0x8ce384:0xc78aff,emissive:id==='thorn'?0x447b43:0x74488e,emissiveIntensity:.8}));this.world.add(mesh);this.orbitMeshes[j]=mesh;}
     this.orbitMeshes[j].position.set(x,.8+Math.sin(a*1.4)*.22,z);this.orbitMeshes[j].rotation.y+=dt*5;
     for(const e of this.enemies)if(!e.dead&&e.orbitCooldown<=0&&Math.hypot(e.mesh.position.x-x,e.mesh.position.z-z)<e.radius+.33){this.damageEnemy(e,(8+w.level*3)*.29,'normal');e.orbitCooldown=.25;}
    }continue;
   }
   w.next-=dt;if(w.next<=0){this.fire(id,w);const d=findWeapon(id);w.next=Math.max(.16,d.cooldown*(1-.055*(w.level-1))*(w.evolved?.75:1)*Math.max(.35,cdr)*((this.player.frenzy||0)>0?.6:1));}
  }
 }
 updateEnemies(dt){
  const p=this.player;
  for(let i=this.enemies.length-1;i>=0;i--){const e=this.enemies[i];if(e.dead){this.enemies.splice(i,1);continue;}
   const dx=p.pos.x-e.mesh.position.x,dz=p.pos.z-e.mesh.position.z,dist2=dx*dx+dz*dz;
   if(dist2>52*52){if(e.boss){this.world.remove(e.mesh);this.disposeGenerated(e.mesh);}this.enemies.splice(i,1);continue;}
   const dist=Math.sqrt(dist2);
   if(dist>e.radius+.45){const inv=1/Math.max(.001,dist);const vx=dx*inv,vz=dz*inv;const crowdSlow=e.boss?1:1/(1+Math.max(0,this.enemies.length-85)/350);
    const step=dt*e.speed*crowdSlow*(e.slow>0?.48:1);
    const candidate=this.terrain?.resolve(e.mesh.position.x+vx*step,e.mesh.position.z+vz*step,e.mesh.position.y,e.radius*.76)||{x:e.mesh.position.x+vx*step,z:e.mesh.position.z+vz*step};
    e.mesh.position.x=candidate.x;e.mesh.position.z=candidate.z;
    e.mesh.rotation.y=Math.atan2(vx,vz);
   }else if(p.invuln<=0){const damage=Math.max(1,Math.floor(e.damage-p.armor-(this.passives.armor||0)));p.hp-=damage*(p.char.id==='warden'?.88:1);p.invuln=.60;p.pos.x-=dx/Math.max(.1,dist)*.28;p.pos.z-=dz/Math.max(.1,dist)*.28;this.events.damage?.(damage);if(p.hp<=0){this.finish(false);return;}}
   if(!e.boss){e.mesh.position.y=this.terrain?.groundHeight(e.mesh.position.x,e.mesh.position.z,e.mesh.position.y)||0;}
   e.slow=Math.max(0,e.slow-dt);e.flash-=dt;e.orbitCooldown=Math.max(0,e.orbitCooldown-dt);
   if(e.boss)e.mesh.position.y=Math.sin(this.elapsed*2+e.phase)*.065;
  }
  this.enemyBatch?.update(this.enemies,this.elapsed);
 }
 updateProjectiles(dt){
  for(let i=this.projectiles.length-1;i>=0;i--){const b=this.projectiles[i];b.life-=dt;
   if(b.homing){const t=this.nearest(b.mesh.position.x,b.mesh.position.z,11);if(t){tmp.set(t.mesh.position.x-b.mesh.position.x,0,t.mesh.position.z-b.mesh.position.z).normalize();b.velocity.lerp(tmp,Math.min(1,dt*6)).normalize();if(b.visual==='bolt'||b.visual==='flame')b.mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),b.velocity);}}
   b.mesh.position.addScaledVector(b.velocity,dt*b.speed);if(b.visual==='disc'||b.visual==='shard')b.mesh.rotation.y+=dt*12;
   if(this.terrain?.blocked(b.mesh.position.x,b.mesh.position.z,b.mesh.position.y,.11)){b.life=0;}
   if(b.life>0)for(const e of this.enemies){if(e.dead||b.hit.has(e))continue;
    const dx=b.mesh.position.x-e.mesh.position.x,dz=b.mesh.position.z-e.mesh.position.z;
    /* V5: elevation-agnostic — your shots connect at any height, on ramps or perches */
    if(dx*dx+dz*dz<(e.radius+.24)*(e.radius+.24)){
     this.damageEnemy(e,b.damage,'normal',b.knock);this.spark(e.mesh.position,b.mesh.material.color);b.hit.add(e);if(b.pierce--<=0){b.life=0;break;}
    }
   }
   if(b.life<=0){if(b.impact>0)this.pulseAt(b.mesh.position,b.impact,b.damage);b.mesh.visible=false;this.projectilePool.push(b.mesh);this.projectiles.splice(i,1);}
  }
 }
 rollRelicTier(){const r=Math.random();return r<.55?0:r<.84?1:r<.965?2:3;}
 grantRelic(tier){
  // V13: the "jackpot" moment — escalating lucky rewards, capped by a once-in-a-run Mythic Frenzy spike.
  const p=this.player,heal=f=>{p.hp=Math.min(p.maxHp,p.hp+p.maxHp*f);};
  const bump=n=>{const owned=Object.entries(this.weapons).filter(([id,w])=>w.level<20);for(let i=0;i<n&&owned.length;i++){const k=Math.floor(Math.random()*owned.length);owned.splice(k,1)[0][1].level++;}};
  if(tier===0){this.coins+=70;heal(.22);bump(1);this.souls+=18;this.events.relic?.(0);this.events.toast?.('✦ RARE CACHE · +1 WEAPON · +70 COINS');this.pulse(2,10,0x5db7ff,{knock:.1});}
  else if(tier===1){this.coins+=150;heal(.4);bump(2);const pa=PASSIVES[Math.floor(Math.random()*PASSIVES.length)];this.passives[pa.id]=(this.passives[pa.id]||0)+1;this.souls+=40;this.events.relic?.(1);this.events.toast?.('◆ EPIC HOARD · +2 WEAPONS · +1 PASSIVE · +150 COINS');this.pulse(2.6,16,0xb569ff,{knock:.16});}
  else if(tier===2){this.coins+=260;heal(1);p.invuln=Math.max(p.invuln,2.6);bump(3);this.addXP(90+this.level*14);this.souls+=75;this.events.relic?.(2);this.events.toast?.('★ LEGENDARY TROVE · FULL HEAL · +3 WEAPONS');this.pulse(3.4,22,0xffb54d,{knock:.22});}
  else{this.coins+=500;heal(1);p.invuln=Math.max(p.invuln,3.2);p.frenzy=Math.max(p.frenzy||0,13);bump(4);this.addXP(160+this.level*20);this.souls+=140;this.events.relic?.(3);this.events.toast?.('☀ MYTHIC WINDFALL · THE NIGHT BLESSES YOU · FRENZY UNLEASHED');this.pulse(4.6,30,0x8ffff0,{knock:.3});}
 }
 updatePickups(dt){
  const p=this.player.pos,range=(4.6+.7*(this.passives.magnet||0))*(1+.06*(profile.upgrades.magnet||0));
  for(let i=this.pickups.length-1;i>=0;i--){const o=this.pickups[i];o.age+=dt;const dx=o.pos.x-p.x,dz=o.pos.z-p.z,d=Math.hypot(dx,dz);o.mesh.rotation.y+=dt*1.9;o.mesh.position.y=(o.type==='chest'?.55:.32)+Math.sin(o.age*3)*.06;
   // Generous magnet so loot always comes to you; plus anti-stranding — anything left >6s gets reeled in no matter how far.
   if(o.type!=='chest'&&(d<range||o.age>6)){const pull=Math.max(2.5,14/Math.max(.15,d));o.pos.x-=dx*Math.min(1,dt*pull);o.pos.z-=dz*Math.min(1,dt*pull);}
   if(o.light)o.light.position.set(o.pos.x,1.2,o.pos.z);
   if(d<(.78+(o.type==='chest'?.25:0))){if(o.type==='xp')this.addXP(o.value);else if(o.type==='chest')this.openChest();else if(o.type==='relic')this.grantRelic(o.tier);else if(o.type==='coin'){this.coins+=o.value;this.events.pickup?.();}else{this.player.hp=Math.min(this.player.maxHp,this.player.hp+o.value);this.events.pickup?.();}
    this.world.remove(o.mesh);if(o.light)this.world.remove(o.light);o.mesh.material.dispose();this.pickups.splice(i,1);if(this.status==='levelup')break;}
  }
 }
 updateFX(dt){for(let i=this.fx.length-1;i>=0;i--){const f=this.fx[i];f.age+=dt;
  if(f.kind==='meteor'){const t=Math.max(0,Math.min(1,f.age/f.duration));f.mesh.position.set(f.dest.x+2*(1-t),f.dest.y+9*(1-t)+.15,f.dest.z+1.5*(1-t));f.mesh.rotation.set(t*8,t*6,t*5);if(f.age>=f.duration)this.pulseAt(new THREE.Vector3(f.dest.x,f.dest.y,f.dest.z),f.radius,f.damage,f.color);}
  if(f.kind==='spark'){f.mesh.scale.setScalar(Math.max(.05,1-f.age/f.duration)*1.8);f.mesh.material.opacity=Math.max(0,1-f.age/f.duration);}
  if(f.kind==='ring'){f.mesh.scale.setScalar(.2+Math.max(0,f.age)/f.duration*f.maxscale);f.mesh.material.opacity=Math.max(0,.7*(1-f.age/f.duration));}
  if(f.kind==='mine'&&f.age>0){for(const e of this.enemies)if(!e.dead&&Math.hypot(e.mesh.position.x-f.mesh.position.x,e.mesh.position.z-f.mesh.position.z)<.65+e.radius){this.pulseAt(f.mesh.position,f.radius,f.damage);f.age=f.duration;break;}}
  if(f.age>=f.duration){this.world.remove(f.mesh);if(f.mesh.geometry&&!([sphere,ico,boxgeo,cyl].includes(f.mesh.geometry)))f.mesh.geometry.dispose();f.mesh.material.dispose();this.fx.splice(i,1);}
 }}
 pulseAt(pos,radius,dmg,color=0xbd88f3){if(profile.settings.particles!==false&&this.fx.length<this.budget.effects){const ring=circleRing(radius,color,.8);ring.position.set(pos.x,Math.max(.1,pos.y+.12),pos.z);this.world.add(ring);this.fx.push({mesh:ring,age:0,duration:.4,maxscale:.4,kind:'ring'});}for(const e of this.enemies)if(!e.dead&&Math.hypot(e.mesh.position.x-pos.x,e.mesh.position.z-pos.z)<radius+e.radius&&Math.abs(e.mesh.position.y-pos.y)<2.4)this.damageEnemy(e,dmg,'area',.7);}
 activateAbility(which){if(this.status!=='playing')return false;const p=this.player;
  if(which==='dash'&&p.dashCooldown<=0){{const dest=this.terrain?.resolve(p.pos.x+p.face.x*3.8,p.pos.z+p.face.z*3.8,p.y,.42);if(dest){p.pos.x=dest.x;p.pos.z=dest.z;}else p.pos.addScaledVector(p.face,3.8);}p.invuln=Math.max(.85,p.invuln);p.dashCooldown=7;this.pulse(1.6,15,0xa7d5bd,{knock:.5});this.events.ability?.('dash');this.events.toast?.('SHADOW DASH');return true;}
  if(which==='nova'&&p.novaCooldown<=0){
   const id=p.relic.id;p.novaCooldown=p.relic.cooldown;
   if(id==='nightfall')this.pulse(5.5,62+this.level*2,0xe7c88e,{knock:1.1});
   if(id==='meteorstorm'){for(const t of this.enemies.filter(e=>!e.dead).sort((a,b)=>a.mesh.position.distanceToSquared(p.pos)-b.mesh.position.distanceToSquared(p.pos)).slice(0,12))this.spawnMeteor(t.mesh.position,60+this.level*2,2.4,0xff9c57);}
   if(id==='timewarp')this.pulse(9,35+this.level,0x90b8f9,{slow:8});
   if(id==='earthshatter')this.pulse(7.3,89+this.level*2,0xd8a27c,{knock:1.4});
   if(id==='phoenix'){this.pulse(7,42+this.level,0xff9354,{knock:.3});p.hp=Math.min(p.maxHp,p.hp+p.maxHp*.34);}
   if(id==='reaper'){for(const e of this.enemies.filter(e=>!e.dead).sort((a,b)=>b.hp-a.hp).slice(0,8))this.damageEnemy(e,120+this.level*4,'reap',.2);}
   if(id==='mushroom')this.pulse(10,20+this.level,0x88d77c,{slow:10});
   if(id==='frostbite')this.pulse(6.8,24+this.level,0x92cde4,{knock:.1,slow:6});
   if(id==='bloodwell'){this.pulse(4.4,18+this.level,0xc46e80,{knock:.17});p.hp=Math.min(p.maxHp,p.hp+p.maxHp*.27);p.invuln=Math.max(p.invuln,.5);}
   if(id==='thunder'){const targets=this.enemies.filter(e=>!e.dead&&Math.hypot(e.mesh.position.x-p.pos.x,e.mesh.position.z-p.pos.z)<11).sort((a,b)=>a.hp-b.hp).slice(0,16);for(const e of targets)this.damageEnemy(e,61+this.level*2,'lightning',.3);this.pulse(2.6,22,0xa1d3f6,{knock:.2});}
   if(id==='sanctuary'){p.invuln=Math.max(p.invuln,5);p.hp=Math.min(p.maxHp,p.hp+22);this.pulse(2.2,20,0xe9d39d,{knock:.6});}
   if(id==='gravity'){for(const e of this.enemies){if(e.dead||e.boss)continue;const d=Math.hypot(e.mesh.position.x-p.pos.x,e.mesh.position.z-p.pos.z);if(d<7&&d>1){e.mesh.position.x+=(p.pos.x-e.mesh.position.x)*.3;e.mesh.position.z+=(p.pos.z-e.mesh.position.z)*.3;}}this.pulse(6,45+this.level,0xa68df1,{knock:.35});}
   this.events.ability?.('spell');this.events.toast?.(`✦ ${p.relic.name.toUpperCase()}`);return true;
  }return false;
 }
 spawnMeteor(pos,damage,radius,color=0xffa16a){
  if(this.fx.length>=this.budget.effects){this.pulseAt(pos,radius,damage,color);return;}
  const mesh=new THREE.Mesh(new THREE.DodecahedronGeometry(.55,0),new THREE.MeshStandardMaterial({color,emissive:color,emissiveIntensity:2.2,roughness:.26,flatShading:true}));
  const dest={x:pos.x,z:pos.z,y:pos.y||0};mesh.position.set(dest.x+2,dest.y+9,dest.z+1.5);this.world.add(mesh);
  this.fx.push({mesh,age:0,duration:.64,kind:'meteor',dest,damage,radius,color});
 }
 spark(pos,color){if(!profile.settings.particles||this.fx.length>=this.budget.effects)return;
  const mesh=new THREE.Mesh(new THREE.OctahedronGeometry(.12),new THREE.MeshBasicMaterial({color,transparent:true,opacity:1,depthWrite:false}));
  mesh.position.set(pos.x,pos.y+.8,pos.z);this.world.add(mesh);this.fx.push({mesh,age:0,duration:.24,maxscale:1,kind:'spark'});
 }
 spawnChest(boss=false){if(this.chests.length>=5||this.status!=='playing')return;
  const angle=rand(0,TAU),dist=rand(8,14),target=this.terrain?.findFree(this.player.pos.x+Math.cos(angle)*dist,this.player.pos.z+Math.sin(angle)*dist,0,.92)||{x:0,z:0},rarity=boss?'rare':Math.random()<.18?'rare':Math.random()<.5?'uncommon':'common';
  const mesh=this.cloneModel('Dungeonchest_'+rarity,1.1)||this.cloneModel('Chest',1.1)||new THREE.Mesh(boxgeo,material(0xe0b574));
  mesh.position.set(target.x,.08,target.z);this.world.add(mesh);
  const ring=circleRing(1.15,rarity==='rare'?0xffc779:0x8be3c6,.7);ring.position.set(target.x,.07,target.z);this.world.add(ring);
  const chest={mesh,ring,x:target.x,z:target.z,age:0,rarity};this.chests.push(chest);this.events.chest?.('spawn',rarity);
  this.events.toast?.(rarity==='rare'?'✦ LEGENDARY RELIC CHEST SPAWNED':'◆ SUPPLY CHEST DISCOVERED · PRESS F TO OPEN');
 }
 interact(){if(this.status!=='playing')return false;if(this.closestChest){this.openWorldChest(this.closestChest);return true;}return this.useShrine();}
 openWorldChest(chest){const index=this.chests.indexOf(chest);if(index<0)return;this.events.chest?.('open',chest.rarity);
  this.world.remove(chest.mesh,chest.ring);this.chests.splice(index,1);this.closestChest=null;
  const roll=Math.random(),reward=chest.rarity==='rare'&&roll<.48?'legendary':roll<.18?'heal':roll<.42?'xp':roll<.69?'weapon':'coins';
  const r=CHEST_REWARDS.find(x=>x.id===reward);
  if(reward==='heal'){this.player.hp=Math.min(this.player.maxHp,this.player.hp+75);this.player.novaCooldown=0;}
  if(reward==='coins') {this.coins+=100;this.souls+=32;}
  if(reward==='xp')this.addXP(80+this.level*13);
  if(reward==='weapon'||reward==='legendary'){
   const owned=Object.entries(this.weapons).filter(([id,w])=>w.level<8);
   const upgrades=reward==='legendary'?2:1;
   for(let i=0;i<upgrades&&owned.length;i++){const index=Math.floor(Math.random()*owned.length),[id,w]=owned.splice(index,1)[0];w.level=Math.min(8,w.level+1);}
   this.coins+=reward==='legendary'?100:20;
  }
  this.events.toast?.('✦ '+r.name.toUpperCase()+' · '+r.detail.toUpperCase());
  this.pulse(2.1,12,r.color,{knock:.22});
 }
 useShrine(){if(this.status!=='playing'||!this.focusedShrine||this.focusedShrine.used)return false;
  const altar=this.focusedShrine;altar.used=true;altar.crystal.material.color.set(0x3a4646);altar.crystal.material.emissive.set(0x000000);altar.rune.material.opacity=.16;
  this.player.hp=Math.min(this.player.maxHp,this.player.hp+Math.max(30,this.player.maxHp*.33));this.player.blessing=22;this.player.dashCooldown=0;this.coins+=45;this.souls+=24;
  this.events.altar?.();this.events.toast?.('✦ ALTAR AWAKENED · 22s DAMAGE BLESSING · +45 COINS');return true;
 }

 updatePlayer(dt){
  const p=this.player;let mx=0,mz=0,hazSlow=1;
  if(this.hazards?.length){for(const h of this.hazards){if(Math.hypot(p.pos.x-h.x,p.pos.z-h.z)<h.r){p.hp-=h.dps*dt;if(h.slow<hazSlow)hazSlow=h.slow;if(Math.random()<.05)this.events.damage?.(Math.ceil(h.dps));}}
   if(p.hp<=0){this.finish(false,'hazard');return;}}
  if(this.keys.has('KeyA')||this.keys.has('ArrowLeft'))mx--;
  if(this.keys.has('KeyD')||this.keys.has('ArrowRight'))mx++;
  if(this.keys.has('KeyW')||this.keys.has('ArrowUp'))mz--;
  if(this.keys.has('KeyS')||this.keys.has('ArrowDown'))mz++;
  mx+=this.touch.x;mz+=this.touch.z;const norm=Math.hypot(mx,mz);
  if(norm>.01){
   mx/=Math.max(1,norm);mz/=Math.max(1,norm);
   const b=this.camera.matrixWorld.elements,right=new THREE.Vector3(b[0],0,b[2]).normalize(),up=new THREE.Vector3(b[4],0,b[6]).normalize();
   const dir=right.multiplyScalar(mx).addScaledVector(up,-mz).normalize(),speed=dt*p.speed*(1+.08*(this.passives.boots||0))*hazSlow;
   const next=this.terrain?.resolve(p.pos.x+dir.x*speed,p.pos.z+dir.z*speed,p.y,.42)||{x:p.pos.x+dir.x*speed,z:p.pos.z+dir.z*speed};
   p.pos.x=next.x;p.pos.z=next.z;p.face.copy(dir);this.hero.rotation.y=Math.atan2(dir.x,dir.z);
  }
  const surface=this.terrain?.groundHeight(p.pos.x,p.pos.z,p.y)||0;
  if(p.grounded){if(p.y<surface+.35&&p.y>=surface-.5)p.y=surface;else if(p.y>surface+.5)p.grounded=false;}
  if(!p.grounded){p.vy-=16.8*dt;p.y+=p.vy*dt;if(p.y<=surface&&p.vy<=0){p.y=surface;p.vy=0;p.grounded=true;}}
  p.y=Math.max(0,p.y);p.jumpCooldown=Math.max(0,p.jumpCooldown-dt);
  this.hero.position.set(p.pos.x,p.y+.035+Math.sin(this.elapsed*(norm>.1?13:3))*(p.grounded?(norm>.1?.027:.014):0),p.pos.z);
  if(this.animMixer){const type=norm>.1?'run':'idle';if(type!==this.animCurrent){this.animations[this.animCurrent]?.fadeOut(.14);this.animations[type]?.reset().fadeIn(.14).play();this.animCurrent=type;}this.animMixer.update(dt);}
  p.blessing=Math.max(0,p.blessing-dt);p.invuln=Math.max(0,p.invuln-dt);p.dashCooldown=Math.max(0,p.dashCooldown-dt);p.novaCooldown=Math.max(0,p.novaCooldown-dt);p.frenzy=Math.max(0,(p.frenzy||0)-dt);
  p.hp=Math.min(p.maxHp,p.hp+dt*(p.regen+.3*(this.passives.regen||0)));
  const pos=new THREE.Vector3(p.pos.x+12.5,p.y+21,p.pos.z+17);this.camera.position.lerp(pos,Math.min(1,dt*4));this.camera.lookAt(p.pos.x,p.y+.38,p.pos.z);
  this.glow.position.set(p.pos.x,p.y+2,p.pos.z);
  this.focusedShrine=null;for(const shrine of this.shrines){if(!shrine.used&&Math.hypot(shrine.x-p.pos.x,shrine.z-p.pos.z)<2.1){this.focusedShrine=shrine;break;}}
  this.closestChest=this.chests?.find(ch=>Math.hypot(ch.x-p.pos.x,ch.z-p.pos.z)<2.1)||null;
 }
 finish(victory=false,ending=null){if(this.status==='ended')return;this.status='ended';const result={victory,ending,kills:this.kills,time:this.elapsed,coins:this.coins+Math.floor(this.elapsed/8),souls:Math.floor(this.souls*(1+.1*(this.passives.greed||0))*(this.player.char.id==='reaper'?1.15:1)),earnedXP:this.earnedXP,level:this.level,bossKills:this.bossKills,evolutions:this.evolutions,map:this.runMap,character:this.player.char.id};this.events.finish?.(result);}
 animate(){
  const dt=safeDelta(this.clock.getDelta());this.frameCount++;
  this.fpsWindow+=dt;this.fpsFrames++;
  if(this.fpsWindow>=2){this.fps=Math.round(this.fpsFrames/this.fpsWindow);this.fpsWindow=0;this.fpsFrames=0;
   if(this.status==='playing'&&this.fps<30&&this.useBloom){this.useBloom=false;this.events.toast?.('PERFORMANCE MODE · BLOOM OFF');}
   if(this.status==='playing'&&this.fps<38)this.currentEnemyCap=Math.max(70,Math.floor(this.currentEnemyCap*.88));
   else if(this.status==='playing'&&this.fps>55)this.currentEnemyCap=Math.min(this.budget.enemies,this.currentEnemyCap+5);
  }
  if(this.status==='menu'){this.elapsed+=dt;if(this.menuAvatar)this.menuAvatar.rotation.y+=dt*.2;this.camera.position.set(14+Math.sin(this.elapsed*.13)*1.8,24,19+Math.cos(this.elapsed*.13)*1.8);this.camera.lookAt(0,0,0);}
  if(this.status==='playing'){
   this.elapsed+=dt;this.comboClock=Math.max(0,this.comboClock-dt);if(this.comboClock===0)this.combo=0;
   if(this.mode==='dungeon'){
    // Dungeon Dive: no timed horde — clear the chamber, then a descent portal opens.
    if(this.chamberActive&&this.aliveEnemies()===0&&!this.portal)this._clearChamber();
   }else{
    this.wave=Math.min(12,1+Math.floor(this.elapsed/60));
    const rushWindow=this.elapsed%90;const nextRush=this.elapsed>80&&rushWindow>0&&rushWindow<18;
    if(nextRush&&!this.rush){this.events.bloodMoon?.('start');this.events.toast?.('☾ BLOOD MOON · THE DEAD GROW RESTLESS');}
    if(!nextRush&&this.rush){this.events.bloodMoon?.('end');this.events.toast?.('✦ BLOOD MOON ENDED · SURVIVED THE RUSH');}
    this.rush=nextRush;
    this.spawnTimer-=dt;
    if(this.spawnTimer<=0){const plan=spawnPlan(this.elapsed,this.mutator.spawn,this.rush);const n=Math.ceil((this.overtime?plan.count*1.6:plan.count)*(this.difficulty?.spawnMul||1));for(let i=0;i<n;i++)this.spawnEnemy();this.spawnTimer=plan.interval*(this.overtime?.68:1);}
    this.chestTimer-=dt;if(this.chestTimer<=0){this.spawnChest();this.chestTimer=rand(35,52);}
    const nextBoss=Math.floor(this.elapsed/120);if(nextBoss>this.bossWave){this.bossWave=nextBoss;this.spawnEnemy(true);}
    if(this.elapsed>=540&&!this.finalBossSpawned)this.spawnFinalBoss();
   }
   this.updatePlayer(dt);this.updateEnemies(dt);
   if(this.status==='playing'){this.updateCombat(dt);this.updateProjectiles(dt);this.updatePickups(dt);this.updateFX(dt);}
   if(this.portal&&Math.hypot(this.player.pos.x-this.portal.x,this.player.pos.z-this.portal.z)<2.3){
    if(this.portal.descend)this._descend();else{this.finish(true,'portal');return;}
   }
   // V9 ENDLESS NIGHT: past 12:00 (or if you skip the Dawn Portal) the survival night never ends —
   // it ramps hard but pours out double XP. Leave via the portal or fall. (Dungeon mode is exempt.)
   if(this.mode!=='dungeon'&&this.elapsed>=720&&!this.overtime){this.overtime=true;this.events.bloodMoon?.('start');this.events.toast?.('☠ THE NIGHT REFUSES TO END · ENDLESS · DOUBLE XP');this.scene.fog.color.lerp(new THREE.Color(0x3a0a12),.5);}
   this.uiClock+=dt;if(this.uiClock>.13){this.uiClock=0;this.events.tick?.(this.snapshot());}
  }
  if(this.status==='playing'){for(const ch of this.chests){ch.age+=dt;ch.mesh.rotation.y+=dt*.24;ch.mesh.position.y=.08+Math.sin(ch.age*2)*.055;ch.ring.rotation.z+=dt*.22;}}
  this._animAmbience(dt);
  if(this.partnerMesh&&this.partnerTarget){this.partnerMesh.position.lerp(this.partnerTarget,Math.min(1,dt*11));this.partnerMesh.rotation.y+=dt*.3;}
  if(this.useBloom&&this.composer)this.composer.render();else this.renderer.render(this.scene,this.camera);
 }
 _buildRadar(){const p=this.player;if(!p)return null;const px=p.pos.x,pz=p.pos.z,R=42;const en=[];for(const e of this.enemies){if(e.dead||e.boss)continue;const dx=e.mesh.position.x-px,dz=e.mesh.position.z-pz;if(dx*dx+dz*dz<R*R){en.push([Math.round(dx),Math.round(dz)]);if(en.length>=40)break;}}
  return {r:R,en,pa:this.partner?[Math.round((this.partner.x||0)-px),Math.round((this.partner.z||0)-pz)]:null,bo:this.finalBoss&&!this.finalBoss.dead?[Math.round(this.finalBoss.mesh.position.x-px),Math.round(this.finalBoss.mesh.position.z-pz)]:null,po:this.portal?[Math.round(this.portal.x-px),Math.round(this.portal.z-pz)]:null};}
 snapshot(){const p=this.player;return {hp:p.hp,maxHp:p.maxHp,frenzy:p.frenzy||0,xp:this.xp,required:this.required,level:this.level,kills:this.kills,coins:this.coins,souls:this.souls,time:this.elapsed,wave:this.wave,weapons:this.weapons,passives:this.passives,enemies:this.enemies.length,dashCooldown:p.dashCooldown,novaCooldown:p.novaCooldown,combo:this.combo,blessing:p.blessing,shrine:!!this.focusedShrine,chest:!!this.closestChest,height:Math.round(p.y*10)/10,jumpReady:p.grounded&&p.jumpCooldown<=0,chests:this.chests.length,rush:this.rush,contract:this.contracts?.[this.contractIndex]||null,fps:this.fps,quality:this.preset,finalBoss:this.finalBoss&&!this.finalBoss.dead?{hp:Math.max(0,this.finalBoss.hp),maxHp:this.finalBoss.maxHp,name:'THE GRAVEKEEPER'}:null,portal:!!this.portal,partner:this.partner?{hp:this.partner.hp,mh:this.partner.mh,lv:this.partner.lv,al:this.partner.al,k:this.partner.k||0}:null,coopKills:this.partner?(this.kills+(this.partner.k||0)):null,overtime:!!this.overtime,mode:this.mode,depth:this.depth||1,chamberLeft:this.mode==='dungeon'?this.aliveEnemies():0,descend:!!this.portal?.descend,radar:this._buildRadar()};}
 destroy(){this.renderer.setAnimationLoop(null);this.renderer.dispose();}
}
