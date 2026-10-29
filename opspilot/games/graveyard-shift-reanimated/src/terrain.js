// NIGHTFALL V3 — pure terrain collision and elevation. No renderer dependency.
// World Y is feet height; all obstacles carry real blocking footprints.
export const PLAYER_RADIUS = 0.42;
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
export class Terrain {
 constructor(bound=75){this.bound=bound;this.solids=[];this.platforms=[];this.ramps=[];this.perches=[];}
 addCircle(x,z,r,top=2){this.solids.push({shape:'circle',x,z,r,top});}
 addBox(x,z,halfX,halfZ,top=2){this.solids.push({shape:'box',x,z,halfX,halfZ,top});}
 addPerch(x,z,r,y){this.perches.push({x,z,r,y});}
 addPlatform(x,z,halfX,halfZ,y){this.platforms.push({x,z,halfX,halfZ,y});}
 // Ramp progresses from the ground at (x,z) along the chosen axis.
 addRamp(x,z,width,length,height,axis='x',sign=1){this.ramps.push({x,z,width,length,height,axis,sign});}
 groundHeight(x,z,feet=0){
  let h=0;
  for(const r of this.ramps){const along=((r.axis==='x'?x-r.x:z-r.z)*r.sign),side=Math.abs(r.axis==='x'?z-r.z:x-r.x);
   if(along>=-.12&&along<=r.length+.12&&side<=r.width*.5)h=Math.max(h,clamp(along/r.length,0,1)*r.height);
  }
  for(const p of this.perches){if(Math.hypot(x-p.x,z-p.z)<=p.r&&feet>=p.y-.43)h=Math.max(h,p.y);}
  for(const p of this.platforms){if(Math.abs(x-p.x)<=p.halfX&&Math.abs(z-p.z)<=p.halfZ&&feet>=p.y-.43)h=Math.max(h,p.y);}
  return h;
 }
 resolve(x,z,feet=0,r=PLAYER_RADIUS){
  let px=clamp(x,-this.bound+r,this.bound-r),pz=clamp(z,-this.bound+r,this.bound-r);
  // Four passes converge reliably at intersections; inexpensive at our modest prop counts.
  for(let iter=0;iter<3;iter++)for(const s of this.solids){if(feet>=s.top-.16)continue;
   if(s.shape==='circle'){
    const dx=px-s.x,dz=pz-s.z,d=Math.hypot(dx,dz),min=s.r+r;
    if(d<min){const nx=d>.0001?dx/d:1,nz=d>.0001?dz/d:0;px=s.x+nx*min;pz=s.z+nz*min;}
   }else{
    const cx=clamp(px,s.x-s.halfX,s.x+s.halfX),cz=clamp(pz,s.z-s.halfZ,s.z+s.halfZ),dx=px-cx,dz=pz-cz,d=Math.hypot(dx,dz);
    if(d<r){if(d>.00001){px+=dx/d*(r-d);pz+=dz/d*(r-d);}else{
     const vx=s.halfX+r-Math.abs(px-s.x),vz=s.halfZ+r-Math.abs(pz-s.z);
     if(vx<vz)px=s.x+Math.sign(px-s.x||1)*(s.halfX+r);else pz=s.z+Math.sign(pz-s.z||1)*(s.halfZ+r);
    }}
   }
  }
  return {x:clamp(px,-this.bound+r,this.bound-r),z:clamp(pz,-this.bound+r,this.bound-r)};
 }
 blocked(x,z,feet=0,r=PLAYER_RADIUS){const p=this.resolve(x,z,feet,r);return Math.hypot(p.x-x,p.z-z)>.02;}
 findFree(x,z,feet=0,r=.65){if(!this.blocked(x,z,feet,r))return {x,z};for(let i=1;i<=32;i++){const a=i*2.399963,dist=.4+Math.sqrt(i)*.68,xx=x+Math.cos(a)*dist,zz=z+Math.sin(a)*dist;if(!this.blocked(xx,zz,feet,r))return {x:xx,z:zz};}return {x:0,z:0};}
}
