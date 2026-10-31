import * as THREE from 'three';
const mat=(color,roughness=.8,metalness=.04)=>new THREE.MeshStandardMaterial({color,roughness,metalness});
const box=(w,h,d,m,x=0,y=0,z=0)=>{const o=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),m);o.position.set(x,y,z);return o;};
const rand=(n)=>{let x=Math.sin(n*174.39+13.7)*43758.5453;return x-Math.floor(x);};
function strip(points,offsetA,offsetB,y,material,group){
  const verts=[],norms=[],uv=[],index=[];let s=0;
  for(let i=0;i<points.length;i++){
    const p=points[i],b=points[(i+1)%points.length],a=points[(i+points.length-1)%points.length];
    const dx=b.x-a.x,dz=b.z-a.z,len=Math.hypot(dx,dz)||1,nx=dz/len,nz=-dx/len;
    for(const off of [offsetA,offsetB]){verts.push(p.x+nx*off,y,p.z+nz*off);norms.push(0,1,0);uv.push(off*.14,p.s*.14);}
    if(i<points.length-1){const j=i*2;index.push(j,j+2,j+1,j+1,j+2,j+3);}
    s=p.s;
  }
  const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(verts,3));geo.setAttribute('normal',new THREE.Float32BufferAttribute(norms,3));geo.setAttribute('uv',new THREE.Float32BufferAttribute(uv,2));geo.setIndex(index);
  const mesh=new THREE.Mesh(geo,material);mesh.receiveShadow=true;group.add(mesh);return mesh;
}
function cylinder(radiusTop,radiusBottom,height,material,x,y,z,sides=8){const mesh=new THREE.Mesh(new THREE.CylinderGeometry(radiusTop,radiusBottom,height,sides),material);mesh.position.set(x,y,z);return mesh;}
function addPine(group,x,z,size){
  const trunk=mat(0x4c4037),leaf=mat(0x1f6d51);
  const g=new THREE.Group();g.position.set(x,0,z);
  g.add(cylinder(.26,.38,size*.48,trunk,0,size*.24,0,6));
  for(let i=0;i<3;i++)g.add(cylinder(0,1.65*size*(1-i*.18)/3,size*.72,leaf,0,size*(.52+i*.21),0,7));
  group.add(g);
}
function addPalm(group,x,z,size){
  const wood=mat(0x746044),leaf=mat(0x367a54),g=new THREE.Group();g.position.set(x,0,z);
  const trunk=cylinder(.24,.4,size,wood,0,size*.5,0,7);trunk.rotation.z=.13;g.add(trunk);
  for(let j=0;j<7;j++){
    const a=j*Math.PI*2/7,frond=new THREE.Mesh(new THREE.ConeGeometry(.9,size*.82,4),leaf);
    frond.position.set(Math.sin(a)*size*.34,size*1.12,Math.cos(a)*size*.34);
    frond.rotation.z=-Math.sin(a)*1.09;frond.rotation.x=Math.cos(a)*1.09;g.add(frond);
  }group.add(g);
}
function addMountain(group,x,z,rad,height,color){
  const m=new THREE.Mesh(new THREE.ConeGeometry(rad,height,5),mat(color));m.position.set(x,height*.5-2,z);m.rotation.y=rand(x+z)*6;group.add(m);
}
function addBuildings(group,track,quality){
  const colors=[0x263957,0x283453,0x303d62,0x1b3150,0x38406b];
  const neon=[0x30e5f5,0xfb59d3,0xffd069];
  for(let i=0;i<(quality==='high'?130:65);i++){
    const angle=rand(i+2)*Math.PI*2,r=rand(i+500)*130+33;
    const x=42+Math.cos(angle)*r,z=37+Math.sin(angle)*r;
    if(track.nearest(x,z).distance<track.width*1.1)continue;
    const w=5+rand(i+23)*12,h=8+rand(i+63)*50,d=5+rand(i+89)*11;
    const base=box(w,h,d,mat(colors[i%colors.length],.72,.2),x,h*.5-1.5,z);group.add(base);
    const stripColor=neon[i%3];const glow=new THREE.MeshBasicMaterial({color:stripColor});
    for(let level=0;level<Math.min(10,Math.floor(h/4));level++){
      const y=level*4+3;
      group.add(box(w+.06,.08,d+.06,glow,x,y,z));
    }
    if(i%5===0){group.add(box(w+1,.25,d+1,glow,x,h-.8,z));}
  }
}
function makeSign(text,bg='#12213d',fg='#ffffff'){
  const canvas=document.createElement('canvas');canvas.width=768;canvas.height=160;
  const ctx=canvas.getContext('2d');ctx.fillStyle=bg;ctx.fillRect(0,0,768,160);
  ctx.strokeStyle='#ffffff44';ctx.lineWidth=8;ctx.strokeRect(7,7,754,146);
  ctx.fillStyle=fg;ctx.font='900 75px system-ui,sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(text,384,82);
  const tx=new THREE.CanvasTexture(canvas);tx.colorSpace=THREE.SRGBColorSpace;
  return new THREE.MeshBasicMaterial({map:tx,side:THREE.DoubleSide});
}
function billboard(group,track,s,text){
  const p=track.sample(s),g=new THREE.Group();g.position.set(p.x+p.nx*(track.width*.85),0,p.z+p.nz*(track.width*.85));
  g.rotation.y=Math.atan2(p.tx,p.tz);
  const metal=mat(0x283245,.4,.7);g.add(box(.2,8,.2,metal,-5,4,0));g.add(box(.2,8,.2,metal,5,4,0));
  const sign=box(11,2.6,.16,makeSign(text),0,7.4,0);g.add(sign);group.add(g);
}
function rail(group,track,offset,color){
  const pts=track.samples;
  const m=mat(color,.55,.2);
  for(let i=0;i<pts.length-1;i+=4){
    const p=track.sample(pts[i].s),q=track.sample(pts[Math.min(i+4,pts.length-1)].s);
    const x=p.x+p.nx*offset,z=p.z+p.nz*offset,xx=q.x+q.nx*offset,zz=q.z+q.nz*offset;
    const len=Math.hypot(xx-x,zz-z),bar=box(.3,.7,len+.4,m,(x+xx)/2,.7,(z+zz)/2);
    bar.rotation.y=Math.atan2(xx-x,zz-z);group.add(bar);
  }
}
export function buildWorld(scene,track,quality='high'){
  scene.background=new THREE.Color(track.sky);
  scene.fog=new THREE.FogExp2(track.fog,track.environment==='neon'?.0035:.0026);
  const group=new THREE.Group();scene.add(group);
  const ground= new THREE.Mesh(new THREE.PlaneGeometry(2400,2400),mat(track.ground));
  ground.rotation.x=-Math.PI/2;ground.position.y=-.65;ground.receiveShadow=true;group.add(ground);
  const outer=mat(track.environment==='neon'?0x43365b:0xdbd4c0),road=mat(track.surface,.98),edges=mat(track.accent,.45,.08);
  const pts=track.samples.slice(0,-1);
  strip([...pts,track.samples[track.samples.length-1]],-track.width*.6,track.width*.6,-.045,outer,group);
  strip([...pts,track.samples[track.samples.length-1]],-track.width*.5,track.width*.5,.015,road,group);
  strip([...pts,track.samples[track.samples.length-1]],-track.width*.51,-track.width*.46,.038,edges,group);
  strip([...pts,track.samples[track.samples.length-1]],track.width*.46,track.width*.51,.038,edges,group);
  const dash=mat(0xd7d9d8,.8);
  for(let s=5;s<track.length;s+=10){const p=track.sample(s),o=box(.15,.025,3.2,dash,p.x,.052,p.z);o.rotation.y=Math.atan2(p.tx,p.tz);group.add(o);}
  // Start line is a real alternating checkerboard across the drivable surface.
  for(let i=0;i<16;i++)for(let j=0;j<2;j++){
    const p=track.sample(track.length-1+j*1.4),span=track.width*.95,xoff=(i+.5)/16*span-span/2;
    const tile=box(span/16,.028,1.4,mat((i+j)%2?0xf6f7f4:0x182236),p.x+p.nx*xoff,.071,p.z+p.nz*xoff);
    tile.rotation.y=Math.atan2(p.tx,p.tz);group.add(tile);
  }
  rail(group,track,-track.width*.72,track.environment==='neon'?0x7b64d3:0xc8c9c5);
  rail(group,track,track.width*.72,track.environment==='neon'?0x7b64d3:0xc8c9c5);
  const p=track.sample(track.length-3),start=new THREE.Group();start.position.set(p.x,0,p.z);start.rotation.y=Math.atan2(p.tx,p.tz);
  const mast=mat(track.environment==='neon'?0x93fbef:0x283e55,.4,.35);
  start.add(box(.7,9,.8,mast,-track.width*.62,4.5,0));start.add(box(.7,9,.8,mast,track.width*.62,4.5,0));
  start.add(box(track.width*1.25,.75,.95,mast,0,8.8,0));
  const banner=box(track.width*1.15,2.8,.12,makeSign('VOLT  RUSH','#102139','#f3f5fa'),0,7.15,0);start.add(banner);group.add(start);
  for(let i=0;i<7;i++){const s=track.length*(i+.3)/7;billboard(group,track,s,['RACE HARD','BOOST ZONE','DRIFT / WIN','BVTECH ARCADE','FULL THROTTLE','NO LIMITS','VOLT RUSH'][i]);}
  // Five original rotating energy cubes. Item type is still awarded by the server
  // and randomized on collection — the hologram does NOT promise a particular item.
  const pickups=[],pickupColors=[0x36ecff,0xffd74d,0xf579ff,0x8bff97,0xff7664];
  for(let i=0;i<5;i++){
    const p=track.sample(track.length*[.13,.31,.49,.67,.86][i]);
    const g=new THREE.Group();g.position.set(p.x,2.9,p.z);
    const emissive=new THREE.MeshStandardMaterial({color:pickupColors[i],emissive:pickupColors[i],emissiveIntensity:2.2,metalness:.18,roughness:.2});
    const glass=new THREE.MeshBasicMaterial({color:pickupColors[i],transparent:true,opacity:.13,depthWrite:false,blending:THREE.AdditiveBlending});
    const core=new THREE.Mesh(new THREE.IcosahedronGeometry(1.25,1),emissive);g.add(core);
    const halo=new THREE.Mesh(new THREE.IcosahedronGeometry(1.72,1),glass);g.add(halo);
    const hoop=new THREE.Mesh(new THREE.TorusGeometry(2,.13,8,32),new THREE.MeshBasicMaterial({color:pickupColors[i],transparent:true,opacity:.78,blending:THREE.AdditiveBlending}));hoop.rotation.x=.45;g.add(hoop);
    const hoop2=new THREE.Mesh(new THREE.TorusGeometry(1.8,.065,7,32),new THREE.MeshBasicMaterial({color:0xffffff,transparent:true,opacity:.8,blending:THREE.AdditiveBlending}));hoop2.rotation.y=Math.PI/2;g.add(hoop2);
    const badge=new THREE.Mesh(new THREE.OctahedronGeometry(.48,0),new THREE.MeshBasicMaterial({color:0xffffff}));badge.position.set(0,0,1.7);g.add(badge);
    group.add(g);pickups.push({group:g,hoop,hoop2,halo,core,index:i});
    const groundRing=new THREE.Mesh(new THREE.TorusGeometry(2.35,.10,6,32),new THREE.MeshBasicMaterial({color:pickupColors[i],transparent:true,opacity:.64}));
    groundRing.rotation.x=Math.PI*.5;groundRing.position.set(p.x,.15,p.z);group.add(groundRing);
  }
  // Low-poly festival arches, grandstands and colorful crowds, all procedural.
  const flags=[0xff6795,0xffdb56,0x58e5fe,0x8bff97,0xab8cff];
  for(let j=0;j<4;j++){
    const q=track.sample(track.length*(.08+j*.24));const angle=Math.atan2(q.tx,q.tz),stand=new THREE.Group();
    stand.position.set(q.x+q.nx*track.width*.99,0,q.z+q.nz*track.width*.99);stand.rotation.y=angle;
    const standMat=mat(track.environment==='neon'?0x506099:0xfef3dd),seat=mat(track.environment==='neon'?0x283856:0x36465b);
    for(let row=0;row<3;row++)stand.add(box(15,.55,2.9,seat,0,1+row*.9,row*1.4));
    for(let fan=0;fan<(quality==='high'?60:25);fan++){
      const row=fan%3,col=Math.floor(fan/3);const x=(col/(quality==='high'?20:9)-.5)*14;
      const body=new THREE.Mesh(new THREE.ConeGeometry(.34,.83,5),mat(flags[(fan+j)%flags.length]));
      body.position.set(x,1.9+row*.9,row*1.4);stand.add(body);
    }
    for(let flag=0;flag<5;flag++){
      const x=-7+flag*3.5;stand.add(box(.12,3,.12,standMat,x,3.2,3.1));
      const cloth=box(1.2,.65,.09,new THREE.MeshBasicMaterial({color:flags[(flag+j)%flags.length],side:THREE.DoubleSide}),x+.56,4.4,3.1);
      stand.add(cloth);
    }
    group.add(stand);
  }
  // Site-specific scenery is completely original procedural geometry.
  if(track.environment==='coast'){
    for(let i=0;i<(quality==='high'?95:44);i++){
      const a=rand(i+1)*Math.PI*2,r=rand(i+27)*170+18,x=42+Math.cos(a)*r,z=29+Math.sin(a)*r;
      if(track.nearest(x,z).distance<track.width*.95)continue;
      if(i%3===0)addPalm(group,x,z,6+rand(i+51)*5);
      else {
        const rock=new THREE.Mesh(new THREE.IcosahedronGeometry(2+rand(i+89)*3,0),mat(i%2?0xa49a7a:0xb58a62));
        rock.position.set(x,.4,z);rock.scale.y=.55;rock.rotation.y=rand(i+6)*6;group.add(rock);
      }
    }
    for(let i=0;i<22;i++)addMountain(group,Math.cos(i*4.7)*480,Math.sin(i*4.7)*480,60+rand(i+123)*90,80+rand(i+333)*100,0x9ca7a2);
  }else if(track.environment==='forest'){
    for(let i=0;i<(quality==='high'?180:75);i++){
      const a=rand(i+15)*Math.PI*2,r=rand(i+19)*165+22,x=22+Math.cos(a)*r,z=40+Math.sin(a)*r;
      if(track.nearest(x,z).distance<track.width*.95)continue;
      addPine(group,x,z,4+rand(i+50)*5);
    }
    for(let i=0;i<22;i++)addMountain(group,Math.cos(i*4.7)*450,Math.sin(i*4.7)*450,65+rand(i+123)*80,85+rand(i+333)*115,0x617e76);
  }else addBuildings(group,track,quality);
  const sun=new THREE.DirectionalLight(track.environment==='neon'?0xb0bbff:0xfff3d2,track.environment==='neon'?1.7:2.3);
  sun.position.set(-90,150,80);sun.castShadow=quality==='high';sun.shadow.mapSize.set(1024,1024);
  sun.shadow.camera.left=-180;sun.shadow.camera.right=180;sun.shadow.camera.top=180;sun.shadow.camera.bottom=-180;
  sun.shadow.bias=-.00025;scene.add(sun);const ambience=new THREE.HemisphereLight(0xecffff,0x566349,track.environment==='neon'?2.1:1.65);scene.add(ambience);
  let glow=null;
  if(track.environment==='neon'){
    glow=new THREE.PointLight(0xff5dbb,36,90);glow.position.set(75,19,30);scene.add(glow);
  }
  return {group,pickups,update(seconds){for(const p of pickups){p.group.rotation.y=seconds*.8+p.index*.7;p.group.rotation.z=.19+Math.sin(seconds*.9+p.index)*.15;p.group.position.y=3+Math.sin(seconds*2.5+p.index)*.5;p.hoop.rotation.z=seconds*1.8;p.hoop2.rotation.x=seconds*-1.3;p.halo.scale.setScalar(1+Math.sin(seconds*4+p.index)*.075);}},dispose(){scene.remove(group);scene.remove(sun);scene.remove(ambience);if(glow)scene.remove(glow);group.traverse(o=>{if(o.geometry)o.geometry.dispose();if(o.material){const ms=Array.isArray(o.material)?o.material:[o.material];for(const m of ms){m.map?.dispose();m.dispose();}}});}};
}
