/** Shared, renderer-independent circuit data and spline math. Distances are world units. */
export const TRACKS = {
  coast: {
    name: 'Solar Coast', subtitle:'Sunset circuit • sweeping corners', sky: 0x69d9ff, ground:0xffd99b, fog:0x8be8ff,
    surface:0x35465b, accent:0xffa931, environment:'coast', width:23,
    points: [[0,0],[51,-5],[112,1],[159,35],[160,86],[127,114],[61,111],[4,105],[-55,80],[-63,30],[-35,-10]]
  },
  forest: {
    name: 'Emerald Run', subtitle:'Mountain forest • tight technical turns', sky:0x8bebed, ground:0x52b56d, fog:0x8ee6cc,
    surface:0x39465b, accent:0xb8ff61, environment:'forest', width:22,
    points:[[0,0],[55,-12],[114,3],[150,49],[140,99],[89,137],[25,139],[-43,109],[-69,53],[-52,4],[-26,-20]]
  },
  neon: {
    name: 'Neon Metropolis', subtitle:'Midnight city • fast and technical', sky:0x242049, ground:0x27345d, fog:0x332652,
    surface:0x29354f, accent:0xff64d8, environment:'neon', width:24,
    points:[[0,0],[48,-13],[105,-10],[161,16],[179,61],[163,105],[121,130],[50,124],[-14,101],[-50,56],[-36,8]]
  }
};
const smooth = (a,b,c,d,t) => 0.5*((2*b)+(-a+c)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t);
function position(points,t){
  const n=points.length, pos=((t%1)+1)%1*n, i=Math.floor(pos), f=pos-i;
  const p0=points[(i+n-1)%n],p1=points[i],p2=points[(i+1)%n],p3=points[(i+2)%n];
  return {x:smooth(p0[0],p1[0],p2[0],p3[0],f),z:smooth(p0[1],p1[1],p2[1],p3[1],f)};
}
export function createTrack(id='coast'){
  const data=TRACKS[id]||TRACKS.coast, count=480, samples=[]; let length=0;
  for(let i=0;i<=count;i++){
    const p=position(data.points,i/count);
    if(i>0) length+=Math.hypot(p.x-samples[i-1].x,p.z-samples[i-1].z);
    samples.push({...p,s:length});
  }
  const sample=(s)=>{
    const norm=((s%length)+length)%length;
    let lo=0,hi=count;
    while(lo<hi){let mid=(lo+hi)>>1;if(samples[mid].s<norm)lo=mid+1;else hi=mid;}
    const b=Math.max(1,lo),a=b-1,p=samples[a],q=samples[b],t=(norm-p.s)/Math.max(.0001,q.s-p.s);
    const x=p.x+(q.x-p.x)*t,z=p.z+(q.z-p.z)*t,dx=q.x-p.x,dz=q.z-p.z;
    const len=Math.hypot(dx,dz)||1;
    return {x,z,tx:dx/len,tz:dz/len,nx:dz/len,nz:-dx/len,s:norm};
  };
  const nearest=(x,z)=>{
    let best=Infinity,result=null;
    for(let i=0;i<count;i++){
      const a=samples[i],b=samples[i+1],dx=b.x-a.x,dz=b.z-a.z;
      const t=Math.max(0,Math.min(1,((x-a.x)*dx+(z-a.z)*dz)/(dx*dx+dz*dz||1)));
      const px=a.x+dx*t,pz=a.z+dz*t,d2=(x-px)**2+(z-pz)**2;
      if(d2<best){best=d2;const mag=Math.hypot(dx,dz)||1; result={x:px,z:pz,s:a.s+(b.s-a.s)*t,tx:dx/mag,tz:dz/mag, distance:Math.sqrt(d2), lateral:((x-px)*dz-(z-pz)*dx)/mag};}
    }
    return result;
  };
  return {...data,id,samples,length,sample,nearest};
}
