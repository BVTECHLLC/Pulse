import * as THREE from 'three';

// 6 archetypes x 3 GPU instanced parts, independent of enemy count.
// Enemy objects contain simulation data only: absolutely no per-ghoul scene graph.
// Different, readable silhouettes are important for threat recognition.
const BODY=[new THREE.CapsuleGeometry(.37,.52,2,7),new THREE.IcosahedronGeometry(.52,0),new THREE.BoxGeometry(.84,1.05,.64),new THREE.ConeGeometry(.58,1.35,7),new THREE.DodecahedronGeometry(.55,0),new THREE.CylinderGeometry(.27,.62,1.12,7)];
const HEAD=[new THREE.IcosahedronGeometry(.29,1),new THREE.OctahedronGeometry(.28),new THREE.DodecahedronGeometry(.32,0),new THREE.IcosahedronGeometry(.3),new THREE.IcosahedronGeometry(.33),new THREE.OctahedronGeometry(.3)];
const EYE=new THREE.SphereGeometry(.065,5,4);
const CLAW=new THREE.ConeGeometry(.12,.63,5);
const SPIKE=new THREE.ConeGeometry(.22,.72,5);
const SHADES=[0x899b91,0x4d8580,0x735861,0x67728e,0x71876d,0xb2a17e];
const GLOWS=[0xffaa71,0xb7f2d2,0xff6c76,0xa6a7ff,0xd3ed82,0xffb87c];
const tmp=new THREE.Object3D();
export class EnemyBatch{
 constructor(group,capacity){
  this.types=SHADES.map((color,id)=>{
   const body=new THREE.InstancedMesh(BODY[id],new THREE.MeshStandardMaterial({color,roughness:.93,metalness:0}),capacity);
   const head=new THREE.InstancedMesh(HEAD[id],new THREE.MeshStandardMaterial({color:new THREE.Color(color).multiplyScalar(1.25),roughness:.95}),capacity);
   const eyes=new THREE.InstancedMesh(EYE,new THREE.MeshBasicMaterial({color:GLOWS[id]}),capacity*2);
   const claws=new THREE.InstancedMesh(CLAW,new THREE.MeshStandardMaterial({color:id===1?0xa4ead8:SHADES[id],metalness:.1,roughness:.86}),capacity*2);
   const crests=new THREE.InstancedMesh(SPIKE,new THREE.MeshStandardMaterial({color:id===3?0x9c88d5:SHADES[id],roughness:.8}),capacity*2);
   for(const mesh of [body,head,eyes,claws,crests]){mesh.count=0;mesh.frustumCulled=false;mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);group.add(mesh);}
   return {body,head,eyes,claws,crests};
  });
 }
 update(enemies,seconds){
  const counts=new Int32Array(6);
  for(const e of enemies){
   if(e.dead||e.boss)continue;
   const idx=e.type|0;const batch=this.types[idx];if(!batch)continue;
   const n=counts[idx]++;const s=e.size;
   const x=e.mesh.position.x,z=e.mesh.position.z,angle=e.mesh.rotation.y,gy=e.mesh.position.y||0;
   const bounce=Math.sin(seconds*(idx===1?12:7)+e.phase)*(idx===1?.055:.028);
   tmp.rotation.set(0,angle,0);
   tmp.position.set(x,gy+(idx===1?.55:.70)*s+bounce,z);tmp.scale.set(s*(idx===2?1.29:idx===1?1.2:.9),s*(idx===1?.65:1.04),s*(idx===1?1.45:.85));
   tmp.updateMatrix();batch.body.setMatrixAt(n,tmp.matrix);
   tmp.position.set(x,gy+(idx===1?1.12:1.29)*s+bounce,z);tmp.scale.setScalar(s*(idx===2?1.05:idx===1?.75:1));tmp.updateMatrix();batch.head.setMatrixAt(n,tmp.matrix);
   for(let j=0;j<2;j++){
    const side=j===0?-.11:.11;
    tmp.position.set(x+Math.cos(angle)*side*s+Math.sin(angle)*.245*s,gy+(idx===1?1.14:1.31)*s+bounce,z-Math.sin(angle)*side*s+Math.cos(angle)*.245*s);
    tmp.scale.setScalar(e.flash>0?1.33*s:.88*s);tmp.rotation.set(0,0,0);tmp.updateMatrix();batch.eyes.setMatrixAt(n*2+j,tmp.matrix);
    // Articulated limbs/horns make swarms readable at distance without 3D allocations per enemy.
    const xx=j?1:-1;
    tmp.position.set(x+Math.cos(angle)*xx*.53*s,gy+.79*s+bounce,z-Math.sin(angle)*xx*.53*s);
    tmp.rotation.set((j?-.3:.3),angle,(j?-.52:.52));tmp.scale.set(.88*s,(idx===1?1.5:1)*s,.9*s);tmp.updateMatrix();batch.claws.setMatrixAt(n*2+j,tmp.matrix);
    tmp.position.set(x+Math.cos(angle)*xx*.29*s,gy+(idx===2?1.72:1.53)*s+bounce,z-Math.sin(angle)*xx*.29*s);
    tmp.rotation.set(0,angle,(j?-.5:.5));tmp.scale.set(.8*s,(idx===2?1.35:.65)*s,.8*s);tmp.updateMatrix();batch.crests.setMatrixAt(n*2+j,tmp.matrix);
   }
  }
  this.types.forEach((b,id)=>{const n=counts[id];b.body.count=n;b.head.count=n;b.eyes.count=n*2;b.claws.count=n*2;b.crests.count=n*2;for(const mesh of [b.body,b.head,b.eyes,b.claws,b.crests])if(mesh.count)mesh.instanceMatrix.needsUpdate=true;});
 }
 dispose(){for(const b of this.types)for(const mesh of [b.body,b.head,b.eyes,b.claws,b.crests]){mesh.parent?.remove(mesh);mesh.material.dispose();}}
}
