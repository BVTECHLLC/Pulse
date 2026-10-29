import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {clone as cloneSkinned} from 'three/addons/utils/SkeletonUtils.js';
import {CHARACTERS,MAPS,WEAPONS,PASSIVES,EVOLUTIONS,MUTATORS,levelRequired,findWeapon} from './data.js';
import {profile} from './profile.js';
const TAU=Math.PI*2;
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const rand=(a,b)=>a+Math.random()*(b-a);
const material=(color,emissive=0x000000,roughness=.7)=>new THREE.MeshStandardMaterial({color,emissive,roughness,metalness:.05});
const sphere=new THREE.SphereGeometry(1,10,8);
const cyl=new THREE.CylinderGeometry(1,1,1,7);
const ico=new THREE.IcosahedronGeometry(1,0);
const boxgeo=new THREE.BoxGeometry(1,1,1);
const enemyTypes=[
 {name:'Wanderer',color:0x778c90,hp:35,speed:1.6,radius:.53,damage:10,reward:1,size:1},
 {name:'Skitter',color:0x7dd9c0,hp:24,speed:2.9,radius:.4,damage:7,reward:2,size:.7},
 {name:'Brute',color:0xbb7a8d,hp:145,speed:.94,radius:.8,damage:18,reward:4,size:1.5},
 {name:'Specter',color:0x9d81eb,hp:61,speed:2.15,radius:.48,damage:12,reward:3,size:.9},
 {name:'Infected',color:0xa5d568,hp:80,speed:1.85,radius:.6,damage:14,reward:3,size:1.1},
 {name:'Hollow',color:0xe2a56e,hp:51,speed:2.7,radius:.54,damage:10,reward:2,size:1}
];
const tmp=new THREE.Vector3();
function makeGlow(color,r=.28){return new THREE.Mesh(new THREE.SphereGeometry(r,10,8),new THREE.MeshBasicMaterial({color,transparent:true,opacity:.75,depthWrite:false}));}
function circleRing(radius,color,opacity=.45){const m=new THREE.Mesh(new THREE.RingGeometry(radius-.065,radius,48),new THREE.MeshBasicMaterial({color,transparent:true,opacity,side:THREE.DoubleSide,depthWrite:false}));m.rotation.x=-Math.PI/2;return m;}
function makeGroundTexture(type){
 const c=document.createElement('canvas');c.width=c.height=512;const x=c.getContext('2d');
 x.fillStyle=type==='facility'?'#152733':type==='village'?'#292533':'#1b2929';x.fillRect(0,0,512,512);
 for(let i=0;i<8500;i++){
  const a=Math.random()*512,b=Math.random()*512,r=rand(.2,2.4);x.fillStyle=`rgba(${type==='facility'?'78,161,193':'110,138,130'},${rand(.018,.095)})`;x.fillRect(a,b,r,r);
 }
 x.strokeStyle=type==='facility'?'#304a53':'#263838';x.lineWidth=1.2;
 for(let i=0;i<512;i+=64){x.beginPath();x.moveTo(i,0);x.lineTo(i,512);x.moveTo(0,i);x.lineTo(512,i);x.stroke();}
 if(type==='cemetery')for(let i=0;i<100;i++){x.fillStyle=`rgba(62,99,87,${rand(.025,.1)})`;x.beginPath();x.ellipse(rand(0,512),rand(0,512),rand(3,17),rand(2,10),0,0,TAU);x.fill();}
 const t=new THREE.CanvasTexture(c);t.wrapS=t.wrapT=THREE.RepeatWrapping;t.repeat.set(14,14);t.colorSpace=THREE.SRGBColorSpace;t.anisotropy=4;return t;
}
export class GraveyardEngine {
 constructor(canvas,events={}){
  this.canvas=canvas;this.events=events;this.renderer=new THREE.WebGLRenderer({canvas,antialias:true,alpha:false,powerPreference:'high-performance'});
  this.renderer.setPixelRatio(Math.min(devicePixelRatio||1,1.7));this.renderer.outputColorSpace=THREE.SRGBColorSpace;this.renderer.toneMapping=THREE.ACESFilmicToneMapping;this.renderer.toneMappingExposure=1.4;
  this.scene=new THREE.Scene();this.scene.background=new THREE.Color(0x101925);this.scene.fog=new THREE.FogExp2(0x101925,.015);
  this.camera=new THREE.OrthographicCamera(-17,17,11,-11,.1,200);this.camera.position.set(19,27,25);this.camera.lookAt(0,0,0);
  this.clock=new THREE.Clock();this.world=new THREE.Group();this.scene.add(this.world);
  this.scene.add(new THREE.HemisphereLight(0xaccdff,0x152025,2));
  const moon=new THREE.DirectionalLight(0xaacaff,2.4);moon.position.set(-22,32,-18);this.scene.add(moon);
  const pink=new THREE.DirectionalLight(0xf1719b,1.0);pink.position.set(19,15,18);this.scene.add(pink);
  this.glow=new THREE.PointLight(0x75e7d0,27,14,1.8);this.scene.add(this.glow);
  this.loader=new GLTFLoader();this.models={};this.loading=this.loadAssets();
  this.keys=new Set();this.touch={x:0,z:0};this.status='menu';this.previews=[];this.elapsed=0;this.frameCount=0;
  window.addEventListener('keydown',e=>{if(['KeyW','KeyA','KeyS','KeyD','ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Space'].includes(e.code))e.preventDefault();this.keys.add(e.code);if(!e.repeat&&e.code==='KeyQ')this.activateAbility('dash');if(!e.repeat&&e.code==='KeyE')this.activateAbility('nova');if(e.code==='Escape'&&this.status==='playing')this.pause();else if(e.code==='Escape'&&this.status==='paused')this.resume();});
  window.addEventListener('keyup',e=>this.keys.delete(e.code));
  window.addEventListener('blur',()=>{if(this.status==='playing')this.pause()});
  window.addEventListener('resize',()=>this.resize());this.resize();this.makeMenuWorld();
  this.renderer.setAnimationLoop(()=>this.animate());
 }
 async loadAssets(){
  const ASSET_BASE=import.meta.env.BASE_URL.replace(/\/$/,'');
  const files={Knight:'/assets/models/heroes/Knight.glb',Mage:'/assets/models/heroes/Mage.glb',Ranger:'/assets/models/heroes/Ranger.glb',Rogue:'/assets/models/heroes/Rogue.glb',Rogue_Hooded:'/assets/models/heroes/Rogue_Hooded.glb',Barbarian:'/assets/models/heroes/Barbarian.glb',RigIdle:'/assets/models/heroes/Rig_Medium_General.glb',RigMove:'/assets/models/heroes/Rig_Medium_MovementBasic.glb',DeadTree:'/assets/models/nature/DeadTree_1.gltf',TwistedTree:'/assets/models/nature/TwistedTree_1.gltf',Chest:'/assets/models/fantasy/Chest_Wood.gltf',EyeDrone:'/assets/models/scifi/Enemy_EyeDrone.gltf',Alien:'/assets/models/aliens/Alien_Cyclop.gltf'};
  await Promise.all(Object.entries(files).map(async ([name,url])=>{
   try {const data=await this.loader.loadAsync(ASSET_BASE+url);this.models[name]=data;}catch(e){console.warn('Model unavailable; fallback enabled',name,e);}
  }));this.events.assets?.(Object.keys(this.models).length);return this.models;
 }
 resize(){const w=window.innerWidth,h=window.innerHeight;this.renderer.setSize(w,h,false);const width=17.4;this.camera.left=-width;this.camera.right=width;this.camera.top=width*h/w;this.camera.bottom=-width*h/w;this.camera.updateProjectionMatrix();}
 clearWorld(){this.world.clear();this.enemies=[];this.projectiles=[];this.pickups=[];this.fx=[];this.decor=[];this.orbiters=[];}
 cloneModel(name,height=1.75){const d=this.models[name];if(!d)return null;const g=cloneSkinned(d.scene);const bb=new THREE.Box3().setFromObject(g),sz=bb.getSize(new THREE.Vector3()),center=bb.getCenter(new THREE.Vector3());const scale=height/Math.max(.01,sz.y);g.scale.setScalar(scale);g.position.set(-center.x*scale,-bb.min.y*scale,-center.z*scale);const p=new THREE.Group();p.add(g);return p;}
 makePlayerMesh(char,skinId){
  const p=this.cloneModel(char.model,1.8)||new THREE.Group();
  if(!p.children.length){const body=new THREE.Mesh(new THREE.CapsuleGeometry(.43,.7,4,8),material(0x8fb6db));body.position.y=.9;p.add(body);}
  const skin=[{id:'default',hex:'#9fd4ff'},{id:'crimson',hex:'#ef627b'},{id:'specter',hex:'#91f5e7'},{id:'royal',hex:'#e8bd72'},{id:'void',hex:'#ad88ff'},{id:'toxic',hex:'#a7ed79'},{id:'frost',hex:'#89c9ff'},{id:'ember',hex:'#ff955b'}].find(x=>x.id===skinId)||{hex:'#9fd4ff'};
  const color=new THREE.Color(skin.hex);p.traverse(o=>{if(o.isMesh){const tint=m=>{const t=m.clone();if(t.color)t.color=t.color.clone().lerp(color,.34);if(t.emissive)t.emissive=color.clone().multiplyScalar(.045);return t;};o.material=Array.isArray(o.material)?o.material.map(tint):tint(o.material);}});
  const halo=circleRing(.83,skin.hex,.6);halo.position.y=.055;p.add(halo);
  return p;
 }
 buildFloor(map){
  const ground=new THREE.Mesh(new THREE.PlaneGeometry(280,280),new THREE.MeshStandardMaterial({map:makeGroundTexture(map.id),roughness:1,metalness:0}));ground.rotation.x=-Math.PI/2;ground.position.y=-.05;this.world.add(ground);
  const center=circleRing(7,map.accent,.12);center.position.y=.01;this.world.add(center);
  const stars=new THREE.BufferGeometry();const arr=[];for(let i=0;i<360;i++){arr.push(rand(-130,130),rand(.01,.08),rand(-130,130));}stars.setAttribute('position',new THREE.Float32BufferAttribute(arr,3));
  const points=new THREE.Points(stars,new THREE.PointsMaterial({color:map.id==='facility'?0x72bccc:0x779b8f,size:.075,transparent:true,opacity:.55,depthWrite:false}));this.world.add(points);
 }
 buildDecor(map){
  const tomb=new THREE.Group();const stone=material(map.id==='facility'?0x586e7b:0x656a78);
  for(let i=0;i<68;i++){
   const a=rand(0,TAU),r=rand(12,87),x=Math.cos(a)*r,z=Math.sin(a)*r;if(Math.abs(x)<8&&Math.abs(z)<8)continue;
   const g=new THREE.Group();const base=new THREE.Mesh(boxgeo,stone);base.scale.set(rand(.65,.95),rand(.9,1.8),.27);base.position.y=base.scale.y*.5;g.add(base);
   const top=new THREE.Mesh(new THREE.SphereGeometry(.5,9,6,0,TAU,0,Math.PI/2),stone);top.scale.set(base.scale.x, .45,.33);top.position.y=base.scale.y-.08;g.add(top);
   const cr=new THREE.Mesh(boxgeo,material(0x828596));cr.scale.set(.08,.43,.09);cr.position.set(0,base.scale.y*.64,.17);g.add(cr);
   const cr2=new THREE.Mesh(boxgeo,material(0x828596));cr2.scale.set(.28,.075,.09);cr2.position.set(0,base.scale.y*.69,.18);g.add(cr2);
   g.position.set(x,0,z);g.rotation.y=rand(-.4,.4);g.rotation.z=rand(-.09,.09);tomb.add(g);
  }this.world.add(tomb);
  for(let i=0;i<27;i++){
   const a=rand(0,TAU),r=rand(17,85),x=Math.cos(a)*r,z=Math.sin(a)*r;
   const root=this.cloneModel(i%3===0?'TwistedTree':'DeadTree',rand(3,6));
   if(root){root.position.set(x,0,z);root.rotation.y=rand(0,TAU);this.world.add(root);}else{
    const trunk=new THREE.Mesh(new THREE.CylinderGeometry(.1,.3,3,6),material(0x4d3b40));trunk.position.set(x,1.5,z);this.world.add(trunk);
   }
  }
  if(map.id==='facility'){
   const wallmat=material(0x273f4f);for(let i=0;i<42;i++){const a=rand(0,TAU),r=rand(20,78),p=new THREE.Mesh(boxgeo,wallmat);p.scale.set(rand(.8,2.5),rand(.7,2),rand(.8,2.2));p.position.set(Math.cos(a)*r,p.scale.y/2,Math.sin(a)*r);this.world.add(p);}
  }
  for(let i=0;i<30;i++){const a=rand(0,TAU),r=rand(10,70),p=new THREE.Mesh(ico,material(i%4===0?0x3e575a:0x364746));p.scale.set(rand(.16,.5),rand(.1,.25),rand(.2,.48));p.position.set(Math.cos(a)*r,.05,Math.sin(a)*r);this.world.add(p);}
 }
 makeMenuWorld(){this.clearWorld();const map=MAPS[0];this.buildFloor(map);this.buildDecor(map);this.menuAvatar=new THREE.Group();const b=new THREE.Mesh(new THREE.CapsuleGeometry(.55,.9,4,8),material(0x7fb1cb));b.position.y=1;this.menuAvatar.add(b);this.world.add(this.menuAvatar);}
 async start({character='warden',skin='default',map='cemetery',mutator='standard'}={}){
  const char=CHARACTERS.find(c=>c.id===character)||CHARACTERS[0],setting=MAPS.find(m=>m.id===map)||MAPS[0];
  await this.loading;this.clearWorld();this.scene.background.set(setting.color);this.scene.fog.color.set(setting.fog);this.buildFloor(setting);this.buildDecor(setting);
  this.hero=this.makePlayerMesh(char,skin);this.world.add(this.hero);this.hero.position.set(0,.01,0);this.animMixer=new THREE.AnimationMixer(this.hero);this.animations={};this.animCurrent=null;for(const [kind,src,name] of [['idle','RigIdle','Idle_A'],['run','RigMove','Running_A']]){const clip=this.models[src]?.animations?.find(a=>a.name===name);if(clip)this.animations[kind]=this.animMixer.clipAction(clip);}
  this.mutator=MUTATORS.find(m=>m.id===mutator)||MUTATORS[0];
  this.player={pos:new THREE.Vector3(0,0,0),hp:char.hp+8*(profile.upgrades.health||0)+(char.id==='bruiser'?35:0),maxHp:char.hp+8*(profile.upgrades.health||0)+(char.id==='bruiser'?35:0),speed:char.speed*(char.id==='shade'?1.15:1)*(this.mutator.id==='turbo'?1.15:1)*(1+.015*(profile.upgrades.speed||0)),damage:char.damage*this.mutator.playerDamage*(1+.04*(profile.upgrades.power||0)),armor:char.armor,invuln:0,face:new THREE.Vector3(1,0,0),char,skin,regen:(profile.upgrades.resilience||0)*.08+(char.id==='paladin'?.35:0)};
  this.player.maxHp=Math.round(this.player.maxHp*this.mutator.playerHp);this.player.hp=this.player.maxHp;this.player.dashCooldown=0;this.player.novaCooldown=0;
  this.orbitMeshes=[];this.weapons={[char.weapon]:{level:1,next:0,evolved:false}};this.passives={};this.level=1;this.xp=0;this.earnedXP=0;this.required=levelRequired(1);this.kills=0;this.coins=0;this.souls=0;this.bossKills=0;this.evolutions=0;this.elapsed=0;this.spawnTimer=.5;this.bossWave=0;this.effectsClock=0;this.uiClock=0;this.wave=1;this.status='playing';this.runMap=map;
  this.events.start?.(char);this.events.toast?.(`THE NIGHT BEGINS · ${char.name.toUpperCase()}`);
 }
 pause(){if(this.status!=='playing')return;this.status='paused';this.events.pause?.();}
 resume(){if(this.status!=='paused')return;this.status='playing';this.events.resume?.();}
 moveStick(x,z){this.touch.x=x;this.touch.z=z;}
 nearest(x,z,range=Infinity,exclude=null){let best=null,d=range*range;for(const e of this.enemies){if(e.dead||e===exclude)continue;const dx=e.mesh.position.x-x,dz=e.mesh.position.z-z,v=dx*dx+dz*dz;if(v<d){d=v;best=e;}}return best;}
 spawnEnemy(boss=false){
  if(this.enemies.length>=235)return;const a=rand(0,TAU),r=rand(19,24),idx=boss?2:Math.random()<.32?1:Math.random()<.4?Math.floor(rand(2,6)):0,t=enemyTypes[idx];
  const scale=boss?3.2:t.size,m=new THREE.Group();
  if(boss&&this.models.EyeDrone){const model=this.cloneModel('EyeDrone',3);if(model)m.add(model);}
  if(!m.children.length){
   const b=new THREE.Mesh(idx===1?ico:new THREE.DodecahedronGeometry(.49,0),material(t.color,t.color,1));b.material.emissiveIntensity=boss?.27:.09;b.scale.set(1,1.2,.9);b.position.y=.7;m.add(b);
   const head=new THREE.Mesh(sphere,material(t.color,0x111222));head.scale.set(.38,.38,.38);head.position.y=1.29;m.add(head);
   for(const k of [-1,1]){const eye=makeGlow(boss?0xffc2b1:0xff7d9a,.075);eye.position.set(k*.14,1.32,.33);m.add(eye);}
  }
  m.scale.setScalar(scale);m.position.set(this.player.pos.x+Math.cos(a)*r,0,this.player.pos.z+Math.sin(a)*r);this.world.add(m);
  const mod=1+this.elapsed/250+(this.wave-1)*.12;
  const e={mesh:m,hp:t.hp*(boss?22:1)*mod,maxHp:t.hp*(boss?22:1)*mod,speed:t.speed*(boss?.7:1)*(1+this.elapsed/1800)*this.mutator.enemySpeed,radius:t.radius*scale,size:scale,damage:t.damage*(boss?2.5:1),value:t.reward*(boss?45:1),dead:false,boss,slow:0,flash:0};this.enemies.push(e);
  if(boss){const crown=circleRing(1.6,0xff798d,.85);crown.rotation.x=Math.PI/2;crown.position.y=2.8;m.add(crown);this.events.toast?.('☠ BLOOD MOON · BOSS INCOMING');}
 }
 damageEnemy(e,amount,kind='normal',knock=0){
  if(e.dead)return;const crit=Math.random()<(.04+(.05*(this.passives.crit||0)))?2:1;let d=amount*this.player.damage*(1+.1*(this.passives.might||0))*(1+.1*(this.passives.area||0)*(kind==='area'?1:0));if(this.player.char.id==='alchemist'&&(kind==='poison'||kind==='area'))d*=1.18;if(this.player.char.id==='hex')d*=1.12;
  e.hp-=d*crit;e.flash=.09; if(knock){let v=e.mesh.position.clone().sub(this.player.pos);v.y=0;v.normalize();e.mesh.position.addScaledVector(v,knock);}
  if(this.passives.crit&&crit>1||e.boss)this.events.hit?.({x:e.mesh.position.x,z:e.mesh.position.z,amount:Math.round(d*crit),critical:crit>1});
  if(e.hp<=0)this.killEnemy(e);
 }
 killEnemy(e){if(e.dead)return;e.dead=true;this.world.remove(e.mesh);this.kills++;this.coins+=(e.boss?80:Math.random()<.24?2:0)*this.mutator.reward*(1+.12*(this.passives.fortune||0));this.souls+=(e.boss?25:e.value)*this.mutator.reward;
  if(e.boss){this.bossKills++;this.dropPickup(e.mesh.position.clone(),'chest',1);this.events.toast?.('BOSS ELIMINATED · LOOT DROPPED');}
  else{this.dropPickup(e.mesh.position.clone(),'xp',e.value*2);if(Math.random()<.008)this.dropPickup(e.mesh.position.clone(),'heal',24);}
  if(this.kills===1)this.events.toast?.('FIRST BLOOD');
 }
 dropPickup(pos,type,value){
  if(this.pickups.length>340&&type==='xp'){const existing=this.pickups.find(p=>p.type==='xp');if(existing){existing.value+=value;return;}}
  const color=type==='chest'?0xe9c677:type==='heal'?0xff718e:value>=10?0xb28cff:0x79e9d8;
  const m=new THREE.Mesh(type==='xp'?new THREE.OctahedronGeometry(.17):type==='chest'?boxgeo:sphere,new THREE.MeshStandardMaterial({color,emissive:color,emissiveIntensity:.6,roughness:.25,metalness:.22}));m.scale.setScalar(type==='chest'?.56:type==='heal'?.34:1);m.position.set(pos.x, type==='chest'?.55:.32,pos.z);this.world.add(m);this.pickups.push({mesh:m,pos:m.position,type,value,age:0});
 }
 addXP(value){let xp=value*(1+.1*(this.passives.focus||0)+(this.player.char.id==='hex'?.12:0));this.xp+=xp;this.earnedXP+=Math.round(xp);if(this.xp>=this.required){this.xp-=this.required;this.level++;this.required=levelRequired(this.level);this.status='levelup';this.events.levelUp?.(this.generateChoices());}}
 generateChoices(){
  const pool=[];
  for(const w of WEAPONS){const level=this.weapons[w.id]?.level||0;if(level<8&&(level>0||Object.keys(this.weapons).length<6))pool.push({type:'weapon',id:w.id,title:w.name,icon:w.icon,desc:level?`Level ${level+1} · +damage, extra attacks, faster firing`:w.desc,level,rarity:w.rarity});}
  for(const p of PASSIVES){const level=this.passives[p.id]||0;if(level<5&&(level>0||Object.keys(this.passives).length<6))pool.push({type:'passive',id:p.id,title:p.name,icon:p.icon,desc:p.desc,level,rarity:'passive'});}
  const result=[];
  // Prefer upgrades already in a player's build, but guarantee diversity.
  while(pool.length&&result.length<3){const weights=pool.map(p=>p.level>0?3:1);const sum=weights.reduce((a,b)=>a+b,0);let n=Math.random()*sum,ix=0;for(let i=0;i<weights.length;i++){n-=weights[i];if(n<0){ix=i;break;}}result.push(...pool.splice(ix,1));}
  return result;
 }
 selectUpgrade(choice){if(this.status!=='levelup')return;
  if(choice.type==='weapon'){const w=this.weapons[choice.id];if(w)w.level++;else this.weapons[choice.id]={level:1,next:0,evolved:false};}
  else{this.passives[choice.id]=(this.passives[choice.id]||0)+1;if(choice.id==='vitality'){this.player.maxHp+=20;this.player.hp+=20;}}
  this.status='playing';this.events.toast?.(`${choice.title.toUpperCase()} · UPGRADED`);
  if(this.xp>=this.required){this.xp-=this.required;this.level++;this.required=levelRequired(this.level);this.status='levelup';this.events.levelUp?.(this.generateChoices());}
 }
 openChest(){
  const candidates=EVOLUTIONS.filter(e=>this.weapons[e.weapon]?.level>=8&&this.passives[e.passive]&&!this.weapons[e.weapon].evolved);
  if(candidates.length){const e=candidates[Math.floor(rand(0,candidates.length))];this.weapons[e.weapon].evolved=true;this.evolutions++;this.events.toast?.(`✦ EVOLUTION: ${e.name.toUpperCase()}!`);this.events.evolve?.(e);}
  else{this.coins+=65;this.souls+=25;this.player.hp=Math.min(this.player.maxHp,this.player.hp+25);this.events.toast?.('TREASURE FOUND · +65 COINS · +25 SOULS');}
 }
 spawnProjectile(x,z,dir,damage,config={}){
  const color=config.color||0x9beadd;const mesh=new THREE.Mesh(config.geo||sphere,new THREE.MeshBasicMaterial({color}));mesh.scale.setScalar(config.scale||.2);mesh.position.set(x,.7,z);this.world.add(mesh);
  const v=dir.clone().normalize();this.projectiles.push({mesh,velocity:v,speed:(config.speed||11)*(this.player.char.id==='hacker'?1.15:1),damage,life:config.life||1.3,pierce:config.pierce||0,hit:new Set(),homing:config.homing||false,knock:config.knock||.13});
 }
 pulse(radius,damage,color,opts={}){
  const ring=circleRing(radius,color,.85);ring.position.set(this.player.pos.x,.12,this.player.pos.z);ring.scale.setScalar(.2);this.world.add(ring);this.fx.push({mesh:ring,age:0,duration:.42,maxscale:5,kind:'ring'});
  for(const e of this.enemies){if(e.dead)continue;if(e.mesh.position.distanceTo(this.player.pos)<radius+e.radius){this.damageEnemy(e,damage,'area',opts.knock||.12);if(opts.slow)e.slow=Math.max(e.slow,opts.slow);}}
 }
 fire(id,w){
  const data=findWeapon(id);if(!data)return;const lvl=w.level,ev=w.evolved;const dmg=data.damage*(1+(lvl-1)*.22)*(ev?1.8:1),radius=1+(.12*(this.passives.area||0));const p=this.player.pos;
  const target=this.nearest(p.x,p.z,16);const base=target?target.mesh.position.clone().sub(p).setY(0).normalize():this.player.face.clone();
  const shot=(angle,d=dmg,extra={})=>{const v=base.clone().applyAxisAngle(new THREE.Vector3(0,1,0),angle);this.spawnProjectile(p.x,p.z,v,d,{color:data.color,scale:.14+lvl*.012,...extra});};
  if(id==='orbit')return;
  if(id==='scythe'){this.pulse((2.3+lvl*.18)*radius,dmg,data.color,{knock:.75});return;}
  if(id==='spores'){this.pulse((2.8+lvl*.2)*radius,dmg,data.color,{slow:.4});return;}
  if(id==='nova'){this.pulse((3.7+lvl*.18)*radius,dmg,data.color,{knock:1.1});return;}
  if(id==='frost'){this.pulse((3.2+lvl*.15)*radius,dmg,data.color,{slow:2.7,knock:.23});return;}
  if(id==='coil'){
   let center=target;const seen=new Set();for(let i=0;i<Math.min(12,3+Math.floor(lvl/2)+(ev?5:0)+(this.player.char.id==='storm'?1:0));i++){
    if(!center)break;seen.add(center);this.damageEnemy(center,dmg,'lightning',.12);
    const ring=circleRing(.48,data.color,.84);ring.position.copy(center.mesh.position);ring.position.y=.09;this.world.add(ring);this.fx.push({mesh:ring,age:0,duration:.2,maxscale:2,kind:'ring'});
    center=this.enemies.filter(e=>!seen.has(e)&&!e.dead&&e.mesh.position.distanceTo(center.mesh.position)<(4+lvl*.4)).sort((a,b)=>a.mesh.position.distanceTo(p)-b.mesh.position.distanceTo(p))[0];
   }return;
  }
  if(id==='mines'){const mine=new THREE.Mesh(new THREE.OctahedronGeometry(.35),material(0xb18af0,0x9b65ea));mine.position.set(p.x+rand(-2,2),.33,p.z+rand(-2,2));this.world.add(mine);this.fx.push({mesh:mine,age:-.1,duration:8,maxscale:1,kind:'mine',damage:dmg*1.7,radius:2.0});return;}
  if(id==='drone'){const count=ev?2:1;for(let i=0;i<count;i++)shot(rand(-.2,.2),dmg,{homing:true,scale:.22,speed:15,life:1.6});return;}
  if(id==='ravens'){for(let i=0;i<Math.min(6,2+Math.floor(lvl/2)+(ev?2:0));i++)shot(rand(-.65,.65),dmg,{homing:true,speed:9,life:1.5});return;}
  if(id==='shrapnel'){const n=5+Math.floor(lvl/2)+(ev?6:0);for(let i=0;i<n;i++)shot((i-(n-1)/2)*.13,dmg*.65,{speed:16,life:.57,knock:.26});return;}
  if(id==='voidlance'){for(let i=0;i<(ev?3:1);i++)shot((i-(ev?1:0))*.19,dmg,{scale:.23,life:2,speed:15,pierce:3+Math.floor(lvl/2)});return;}
  if(id==='blood'){for(let i=0;i<1+(ev?2:0);i++)shot((i-(ev?1:0))*.18,dmg,{homing:true,speed:12});this.player.hp=Math.min(this.player.maxHp,this.player.hp+.26*lvl);return;}
  for(let i=0;i<1+Math.floor(lvl/3)+(ev?2:0);i++)shot((i-(Math.floor(lvl/3)+(ev?2:0))/2)*.13,dmg,{homing:id==='boneblades'||id==='ember',pierce:id==='boneblades'?1:0});
 }
 updateCombat(dt){
  const cdr=1-.08*(this.passives.haste||0)-(this.player.char.id==='ranger'?.15:0);
  for(const [id,w] of Object.entries(this.weapons)){
   if(id==='orbit'){
    const count=2+Math.floor(w.level/2)+(w.evolved?4:0);for(let j=0;j<count;j++){
     const a=this.elapsed*2.35+j*TAU/count,r=1.72+(.11*w.level)+(.12*(this.passives.area||0));const x=this.player.pos.x+Math.cos(a)*r,z=this.player.pos.z+Math.sin(a)*r;
     if(!this.orbitMeshes[j]){const mesh=new THREE.Mesh(new THREE.OctahedronGeometry(.25),new THREE.MeshBasicMaterial({color:0xc78aff}));this.world.add(mesh);this.orbitMeshes[j]=mesh;}this.orbitMeshes[j].position.set(x,.8+Math.sin(a*1.4)*.22,z);this.orbitMeshes[j].rotation.y+=dt*5;
     for(const e of this.enemies)if(!e.dead&&Math.hypot(e.mesh.position.x-x,e.mesh.position.z-z)<e.radius+.33&&Math.random()<.08)this.damageEnemy(e,(8+w.level*3)*dt*8,'normal');
    }continue;
   }
   w.next-=dt;
   if(w.next<=0){this.fire(id,w);const d=findWeapon(id);w.next=Math.max(.13,d.cooldown*(1-.055*(w.level-1))*(w.evolved?.75:1)*Math.max(.35,cdr));}
  }
 }
 updateEnemies(dt){
  const p=this.player;
  for(let i=this.enemies.length-1;i>=0;i--){const e=this.enemies[i];if(e.dead){this.enemies.splice(i,1);continue;}
   const v=p.pos.clone().sub(e.mesh.position);v.y=0;const distance=v.length();if(distance>60){this.world.remove(e.mesh);this.enemies.splice(i,1);continue;}
   if(distance>e.radius+.4){v.normalize();e.mesh.position.addScaledVector(v,dt*e.speed*(e.slow>0?.48:1));e.mesh.rotation.y=Math.atan2(v.x,v.z);}
   else if(p.invuln<=0){const damage=Math.max(1,Math.floor(e.damage-p.armor-(this.passives.armor||0)));p.hp-=damage*(p.char.id==='warden'?.88:1);p.invuln=.53;p.pos.addScaledVector(v.normalize(),-.34);this.events.damage?.(damage);if(p.hp<=0){this.finish(false);return;}}
   e.slow=Math.max(0,e.slow-dt);e.flash-=dt;
   e.mesh.scale.y=e.size*(e.flash>0?.9:1);
  }
 }
 updateProjectiles(dt){
  for(let i=this.projectiles.length-1;i>=0;i--){const b=this.projectiles[i];b.life-=dt;
   if(b.homing){const t=this.nearest(b.mesh.position.x,b.mesh.position.z,12);if(t){const dir=t.mesh.position.clone().sub(b.mesh.position).setY(0).normalize();b.velocity.lerp(dir,Math.min(1,dt*6)).normalize();}}
   b.mesh.position.addScaledVector(b.velocity,dt*b.speed);b.mesh.rotation.y+=dt*8;
   for(const e of this.enemies){if(e.dead||b.hit.has(e))continue;if(b.mesh.position.distanceTo(e.mesh.position.clone().setY(.7))<e.radius+.19){this.damageEnemy(e,b.damage,'normal',b.knock);b.hit.add(e);if(b.pierce--<=0){b.life=0;break;}}}
   if(b.life<=0){this.world.remove(b.mesh);b.mesh.geometry!==sphere&&b.mesh.geometry.dispose();b.mesh.material.dispose();this.projectiles.splice(i,1);}
  }
 }
 updatePickups(dt){
  const p=this.player.pos,range=(2.1+.55*(this.passives.magnet||0))*(1+.06*(profile.upgrades.magnet||0));
  for(let i=this.pickups.length-1;i>=0;i--){const o=this.pickups[i];o.age+=dt;const d=Math.hypot(o.pos.x-p.x,o.pos.z-p.z);o.mesh.rotation.y+=dt*2;o.mesh.position.y=(o.type==='chest'?.55:.32)+Math.sin(o.age*3)*.08;
   if(d<range&&o.type!=='chest'){const pull=Math.max(1.3,12/d);o.pos.x+=(p.x-o.pos.x)*Math.min(1,dt*pull);o.pos.z+=(p.z-o.pos.z)*Math.min(1,dt*pull);}
   if(d<(.65+(o.type==='chest'?.25:0))){if(o.type==='xp')this.addXP(o.value);else if(o.type==='chest')this.openChest();else this.player.hp=Math.min(this.player.maxHp,this.player.hp+o.value);this.world.remove(o.mesh);this.pickups.splice(i,1);if(this.status==='levelup')break;}
  }
 }
 updateFX(dt){for(let i=this.fx.length-1;i>=0;i--){const f=this.fx[i];f.age+=dt;if(f.kind==='ring'){f.mesh.scale.setScalar(.2+f.age/f.duration*f.maxscale);f.mesh.material.opacity=Math.max(0,.75*(1-f.age/f.duration));}
   if(f.kind==='mine'&&f.age>0){for(const e of this.enemies)if(!e.dead&&e.mesh.position.distanceTo(f.mesh.position)<.65+e.radius){this.pulseAt(f.mesh.position,f.radius,f.damage);f.age=f.duration;break;}}
   if(f.age>=f.duration){this.world.remove(f.mesh);this.fx.splice(i,1);}}
 }
 pulseAt(pos,radius,dmg){const ring=circleRing(radius,0xbd88f3,.86);ring.position.set(pos.x,.1,pos.z);this.world.add(ring);this.fx.push({mesh:ring,age:0,duration:.4,maxscale:5,kind:'ring'});for(const e of this.enemies)if(!e.dead&&e.mesh.position.distanceTo(pos)<radius+e.radius)this.damageEnemy(e,dmg,'area',.7);}
 activateAbility(which){if(this.status!=='playing')return false;const p=this.player;if(which==='dash'&&p.dashCooldown<=0){const dir=p.face.clone().normalize();p.pos.addScaledVector(dir,3.7);p.invuln=Math.max(.8,p.invuln);p.dashCooldown=9;this.events.toast?.('SHADOW DASH');return true;}if(which==='nova'&&p.novaCooldown<=0){this.pulse(5.3,56+this.level*2,0x91e9db,{knock:1.1});p.novaCooldown=27;this.events.toast?.('NIGHTFALL BURST');return true;}return false;}
 updatePlayer(dt){
  const p=this.player;let mx=0,mz=0;if(this.keys.has('KeyA')||this.keys.has('ArrowLeft'))mx--;if(this.keys.has('KeyD')||this.keys.has('ArrowRight'))mx++;if(this.keys.has('KeyW')||this.keys.has('ArrowUp'))mz--;if(this.keys.has('KeyS')||this.keys.has('ArrowDown'))mz++;
  mx+=this.touch.x;mz+=this.touch.z;const norm=Math.hypot(mx,mz);if(norm>.01){mx/=Math.max(1,norm);mz/=Math.max(1,norm);const b=this.camera.matrixWorld.elements,right=new THREE.Vector3(b[0],0,b[2]).normalize(),up=new THREE.Vector3(b[4],0,b[6]).normalize();const dir=right.multiplyScalar(mx).addScaledVector(up,-mz).normalize();p.pos.x+=dir.x*dt*p.speed*(1+.08*(this.passives.boots||0));p.pos.z+=dir.z*dt*p.speed*(1+.08*(this.passives.boots||0));p.face.copy(dir);this.hero.rotation.y=Math.atan2(dir.x,dir.z);}
  this.hero.position.set(p.pos.x,.045+Math.sin(this.elapsed*(norm>.1?14:3))*(norm>.1?.045:.025),p.pos.z);if(this.animMixer){const type=norm>.1?'run':'idle';if(type!==this.animCurrent){this.animations[this.animCurrent]?.fadeOut(.16);this.animations[type]?.reset().fadeIn(.16).play();this.animCurrent=type;}this.animMixer.update(dt);}
  p.invuln=Math.max(0,p.invuln-dt);p.dashCooldown=Math.max(0,p.dashCooldown-dt);p.novaCooldown=Math.max(0,p.novaCooldown-dt);p.hp=Math.min(p.maxHp,p.hp+dt*(p.regen+.3*(this.passives.regen||0)));
  const lerp=Math.min(1,dt*5);const pos=new THREE.Vector3(p.pos.x+18,27,p.pos.z+23);this.camera.position.lerp(pos,lerp);this.camera.lookAt(p.pos.x,0,p.pos.z);
  this.glow.position.set(p.pos.x,2,p.pos.z);
 }
 finish(victory=false){if(this.status==='ended')return;this.status='ended';const result={victory,kills:this.kills,time:this.elapsed,coins:this.coins+Math.floor(this.elapsed/8),souls:Math.floor(this.souls*(1+.1*(this.passives.greed||0))*(this.player.char.id==='reaper'?1.15:1)),earnedXP:this.earnedXP,level:this.level,bossKills:this.bossKills,evolutions:this.evolutions,map:this.runMap,character:this.player.char.id};this.events.finish?.(result);}
 animate(){const dt=Math.min(.05,this.clock.getDelta());this.frameCount++;if(this.status==='menu'){this.elapsed+=dt;if(this.menuAvatar)this.menuAvatar.rotation.y+=dt*.25;this.camera.position.set(19+Math.sin(this.elapsed*.13)*2,27,25+Math.cos(this.elapsed*.13)*2);this.camera.lookAt(0,0,0);}
  if(this.status==='playing'){
   this.elapsed+=dt;this.wave=Math.min(12,1+Math.floor(this.elapsed/60));this.spawnTimer-=dt;
   if(this.spawnTimer<=0){const count=Math.min(9,Math.ceil((1+Math.floor(this.elapsed/105))*this.mutator.spawn));for(let i=0;i<count;i++)this.spawnEnemy();this.spawnTimer=Math.max(.17,1.2-this.elapsed/900);}
   const nextBoss=Math.floor(this.elapsed/180);if(nextBoss>this.bossWave){this.bossWave=nextBoss;this.spawnEnemy(true);}
   this.updatePlayer(dt);this.updateEnemies(dt);if(this.status==='playing'){this.updateCombat(dt);this.updateProjectiles(dt);this.updatePickups(dt);this.updateFX(dt);}
   if(this.elapsed>=720)this.finish(true);
   this.uiClock+=dt;if(this.uiClock>.11){this.uiClock=0;this.events.tick?.(this.snapshot());}
  }
  this.renderer.render(this.scene,this.camera);
 }
 snapshot(){const p=this.player;return {hp:p.hp,maxHp:p.maxHp,xp:this.xp,required:this.required,level:this.level,kills:this.kills,coins:this.coins,souls:this.souls,time:this.elapsed,wave:this.wave,weapons:this.weapons,passives:this.passives,enemies:this.enemies.length,dashCooldown:p.dashCooldown,novaCooldown:p.novaCooldown};}
 destroy(){this.renderer.setAnimationLoop(null);this.renderer.dispose();}
}
