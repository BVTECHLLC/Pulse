import * as THREE from 'three';
// Original procedural race particles — no downloaded sprites, sounds or models.
const MAX=360;
function starTexture(){
  const c=document.createElement('canvas');c.width=c.height=64;
  const ctx=c.getContext('2d');const grad=ctx.createRadialGradient(32,32,1,32,32,31);
  grad.addColorStop(0,'rgba(255,255,255,1)');grad.addColorStop(.2,'rgba(255,255,255,.95)');grad.addColorStop(.45,'rgba(255,255,255,.40)');grad.addColorStop(1,'rgba(255,255,255,0)');
  ctx.fillStyle=grad;ctx.fillRect(0,0,64,64);return new THREE.CanvasTexture(c);
}
const palette={boost:0x5bf6ff,shield:0x9cffe2,pulse:0xe48aff,oil:0xffce48,hit:0xff647e,finish:0xffe783,drift:0xffd868};
export class RaceFX {
  constructor(scene,quality='high'){
    this.scene=scene;this.max=quality==='high'?MAX:170;this.clock=0;this.cursor=0;
    this.particles=Array.from({length:this.max},()=>({life:0,x:0,y:-999,z:0,vx:0,vy:0,vz:0,gravity:0}));
    this.positions=new Float32Array(this.max*3);this.colors=new Float32Array(this.max*3);
    const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(this.positions,3));
    geometry.setAttribute('color',new THREE.BufferAttribute(this.colors,3));
    this.texture=starTexture();this.mesh=new THREE.Points(geometry,new THREE.PointsMaterial({size:1.25,map:this.texture,vertexColors:true,transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,sizeAttenuation:true}));
    this.mesh.frustumCulled=false;scene.add(this.mesh);this.rings=[];
  }
  burst(type,x,z,y=1.8,amount=35,scale=1){
    const color=new THREE.Color(palette[type]||palette.boost);const count=Math.min(amount,this.max);
    for(let i=0;i<count;i++){
      const p=this.particles[this.cursor++%this.max],a=Math.random()*Math.PI*2,v=(2+Math.random()*10)*scale;
      p.x=x;p.y=y;p.z=z;p.vx=Math.cos(a)*v;p.vz=Math.sin(a)*v;p.vy=(Math.random()-.2)*8*scale;
      p.life=.35+Math.random()*.9;p.gravity=type==='finish'?3.5:9;
      const c=color.clone().lerp(new THREE.Color(type==='finish'?0xff74da:0xffffff),Math.random()*.65);
      p.r=c.r;p.g=c.g;p.b=c.b;
    }
    if(['pulse','shield','hit','boost'].includes(type))this.ring(type,x,z,y);
  }
  ring(type,x,z,y=1.1){
    if(this.rings.length>12)return;
    const mat=new THREE.MeshBasicMaterial({color:palette[type]||0xffffff,transparent:true,opacity:.9,side:THREE.DoubleSide,depthWrite:false,blending:THREE.AdditiveBlending});
    const mesh=new THREE.Mesh(new THREE.TorusGeometry(1.1,.18,6,36),mat);
    mesh.rotation.x=Math.PI/2;mesh.position.set(x,y,z);this.scene.add(mesh);this.rings.push({mesh,life:.48,max:.48});
  }
  trail(k){
    if(Math.random()>.47)return;
    const p=this.particles[this.cursor++%this.max],c=new THREE.Color(k.drifting?0xffaa40:0x55e9ff),spread=k.drifting?2:1.1;
    p.x=k.x-Math.sin(k.heading)*2+(Math.random()-.5)*spread;
    p.z=k.z-Math.cos(k.heading)*2+(Math.random()-.5)*spread;
    p.y=.55+Math.random()*.7;p.vx=(Math.random()-.5)*3;p.vy=1+Math.random()*2;p.vz=(Math.random()-.5)*3;
    p.life=.17+Math.random()*.37;p.gravity=2;p.r=c.r;p.g=c.g;p.b=c.b;
  }
  update(dt){
    this.clock+=dt;
    for(let i=0;i<this.max;i++){
      const p=this.particles[i];p.life-=dt;
      if(p.life>0){p.x+=p.vx*dt;p.y+=p.vy*dt;p.z+=p.vz*dt;p.vy-=p.gravity*dt;}
      const at=i*3;this.positions[at]=p.life>0?p.x:0;this.positions[at+1]=p.life>0?p.y:-999;this.positions[at+2]=p.life>0?p.z:0;
      this.colors[at]=p.r||0;this.colors[at+1]=p.g||0;this.colors[at+2]=p.b||0;
    }
    this.mesh.geometry.attributes.position.needsUpdate=true;this.mesh.geometry.attributes.color.needsUpdate=true;
    for(let i=this.rings.length-1;i>=0;i--){const r=this.rings[i];r.life-=dt;
      r.mesh.scale.setScalar(1+(1-r.life/r.max)*8);r.mesh.material.opacity=Math.max(0,r.life/r.max)*.68;
      if(r.life<=0){this.scene.remove(r.mesh);r.mesh.geometry.dispose();r.mesh.material.dispose();this.rings.splice(i,1);}
    }
  }
  dispose(){for(const r of this.rings){this.scene.remove(r.mesh);r.mesh.geometry.dispose();r.mesh.material.dispose();}this.rings.length=0;this.scene.remove(this.mesh);this.mesh.geometry.dispose();this.mesh.material.dispose();this.texture.dispose();}
}
