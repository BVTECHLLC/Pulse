import {create3DEngine} from './engine3d.js';
'use strict';
// Lantern Vale Online — fully original client rendering, with all gameplay authority on Node.
const $=id=>document.getElementById(id);
const canvas=$('game'),ctx=canvas.getContext('2d',{alpha:false});ctx.imageSmoothingEnabled=false;
let engine3d=null;try{engine3d=create3DEngine(canvas);}catch(error){console.warn('3D unavailable; keeping original 2D mode',error);} 
let settings={volume:.38,music:false,distance:32,night:0,names:true,sfx:true,mode:'3d'};try{settings={...settings,...JSON.parse(localStorage.getItem('signal199x-v3-settings')||'{}')};}catch{}
engine3d?.settings(settings);if(engine3d){engine3d.canvas.style.display=settings.mode==='2d'?'none':'block';canvas.style.visibility=settings.mode==='2d'?'visible':'hidden';}let survivalInfo=null;
const W=960,H=576,T=32;
let world=null,overworld=null,zone='overworld',me=null,details=null,players=[],enemies=[],ws=null,playing=false,mode='register',klass='Scout',palette=0,view='bag',music=false,audio=null,cam={x:0,y:0},visual=null,frame=0,miniChallenge=null,miniInput=[],miniReady=false,dialogue=null,dialogueIndex=0,mouseDown=false,region='',lastUpdate=0,enterChat=false;
const keys={up:false,down:false,left:false,right:false};
const particles=[],emotes=new Map();
const colors={rose:'#ff8daa',lavender:'#c8a0ff',mint:'#89e4b5',gold:'#ffcf79',blue:'#81d3ef'};
const outfits=['#f28ea4','#6bb6e3','#f7c467','#be96ef','#86d8a3','#ef997b'];
const itemRank=['common','uncommon','rare','epic','legendary'];
const tileHash=(x,y,n=0)=>{let z=(x*374761393+y*668265263+n*1274126177)|0;z=Math.imul(z^(z>>>13),1274126177);return ((z^(z>>>16))>>>0)/4294967295};
const rect=(x,y,w,h,c)=>{ctx.fillStyle=c;ctx.fillRect(Math.round(x),Math.round(y),Math.ceil(w),Math.ceil(h));};
const outline=(x,y,w,h,c,stroke)=>{rect(x-2,y-2,w+4,h+4,stroke);rect(x,y,w,h,c)};
function rng(x,y,n=0){return tileHash(Math.floor(x),Math.floor(y),n);}
function text(label,x,y,size=12,color='#fff7df',align='center',weight='900'){ctx.font=`${weight} ${size}px monospace`;ctx.textAlign=align;ctx.textBaseline='middle';ctx.lineWidth=3;ctx.strokeStyle='#2a2041';ctx.strokeText(label,Math.round(x),Math.round(y));ctx.fillStyle=color;ctx.fillText(label,Math.round(x),Math.round(y));}
function tile(x,y,t){const px=x*T,py=y*T,h=rng(x,y);
 if(t===0){rect(px,py,T,T,['#65ac6e','#69b371','#62a969','#70b472'][Math.floor(h*4)]);if(h>.16){rect(px+3+Math.floor(rng(x,y,3)*17),py+3+Math.floor(rng(x,y,4)*14),3,5,'#92c783');rect(px+6+Math.floor(rng(x,y,5)*14),py+23,2,3,'#3b955c');}if(h>.78){const c=['#fff1ba','#f2a1c0','#e8c6ff','#f7d681'][Math.floor(rng(x,y,1)*4)];const bx=px+6+Math.floor(rng(x,y,3)*18),by=py+7+Math.floor(rng(x,y,9)*15);rect(bx,by,3,3,c);rect(bx-2,by+1,7,1,c);rect(bx+1,by-2,1,7,c);rect(bx+1,by+1,1,1,'#ffe084');}if(h<.06){rect(px+12,py+18,7,4,'#4b995f');rect(px+13,py+15,4,4,'#92cf82');}}
 else if(t===1){rect(px,py,T,T,'#c8b389');rect(px,py,32,2,'#d8c395');if(h>.4){rect(px+5,py+18,5,2,'#b19b75');rect(px+20,py+7,3,3,'#b5a17d');}if(h<.25){rect(px+12,py+27,4,2,'#e4d09f');}}
 else if(t===2){rect(px,py,T,T,'#ebd497');rect(px+3,py+6,5,2,'#e2be84');rect(px+23,py+20,3,3,'#fff0b8');if(h>.7)rect(px+15,py+14,2,4,'#cfb77e');}
 else if(t===3){rect(px,py,T,T,'#489bb2');rect(px,py,32,3,'#75c3cf');rect(px+4+(Math.floor(frame/36+x*7)%3)*7,py+8,12,2,'#80d4d7');rect(px+8,py+23,10,2,'#397f9e');if(h>.65){rect(px+22,py+15,6,2,'#c5eff0');}}
 else if(t===4){rect(px,py,T,T,'#3e8d60');rect(px+4,py+6,12,8,'#2d744e');rect(px+17,py+17,12,10,'#529f62');}
 else if(t===6){rect(px,py,T,T,((x+y)%2?'#715371':'#855c83'));rect(px+2,py+2,28,28,'#b77b8c');rect(px+4,py+4,24,24,((x+y)%2?'#9a6393':'#a56586'));rect(px+5,py+5,20,2,'#d59eb7');}
 else if(t===5){rect(px,py,T,T,'#a9a4a0');rect(px,py,32,2,'#8c9394');rect(px,py+16,32,2,'#929190');rect(px+15,py,2,16,'#8a908b');rect(px+7,py+17,2,15,'#8d8c8b');rect(px+25,py+17,2,15,'#8d8c8b');if(h>.7)rect(px+19,py+10,4,2,'#c4bcb0');}
}
function shrub(px,py,big=false){rect(px-12,py-4,big?29:23,7,'#31744c');rect(px-10,py-12,big?27:21,13,'#277449');rect(px-14,py-9,8,10,'#44935b');rect(px+5,py-16,11,12,'#44995e');rect(px-7,py-15,11,10,'#5ab66b');rect(px+4,py-7,7,5,'#73bf75');}
function tree(t){const px=(t.x+.5)*T,py=(t.y+1)*T;rect(px-17,py-9,34,7,'#355e3faa');rect(px-5,py-34,10,35,'#785c46');rect(px-2,py-28,4,26,'#a57c59');const trunkLeft=px-29,trunkTop=py-76;
 const base=t.variant===1?'#3a775f':t.variant===2?'#386f70':'#32765b';const high=t.variant===1?'#5eae77':t.variant===2?'#5ea9a0':'#4da16b';
 rect(trunkLeft+5,trunkTop+13,48,44,base);rect(trunkLeft+13,trunkTop+2,32,63,base);rect(trunkLeft,trunkTop+30,59,29,base);rect(trunkLeft+5,trunkTop+14,47,37,high);rect(trunkLeft+14,trunkTop+4,30,27,high);rect(trunkLeft+9,trunkTop+29,15,9,'#76c48b');rect(trunkLeft+33,trunkTop+17,10,7,'#77c98c');rect(trunkLeft+5,trunkTop+40,8,7,'#4a9e6a');rect(trunkLeft+46,trunkTop+36,9,12,'#236249');rect(trunkLeft+17,trunkTop+49,28,9,base);
 if(t.variant===3){rect(px-11,py-60,4,4,'#ffc5d0');rect(px+17,py-50,5,4,'#fff5cc');rect(px-18,py-39,4,5,'#ffc4d6');}
}
function house(h){const x=h.x*T,y=h.y*T,w=h.w*T,hh=h.h*T;const pal={pink:['#ef9daf','#b96586','#fcddd6','#865072'],blue:['#86bed6','#4c819e','#cceaf0','#467c9d'],yellow:['#f8d691','#bd995c','#fff0be','#a67855'],mint:['#8fceb2','#579a8e','#d8eed2','#577e82'],lilac:['#c2a4d8','#8874ae','#eee1f0','#75618b']}[h.kind]||['#c8b2ae','#8f7085','#eee8d8','#7b5b85'];
 rect(x+13,y+hh-7,w-26,13,'#536c64');rect(x+20,y+55,w-40,hh-60,pal[2]);rect(x+16,y+58,9,hh-58,pal[1]);rect(x+w-26,y+58,10,hh-58,pal[1]);
 rect(x+8,y+40,w-16,23,pal[3]);rect(x,y+30,w,22,pal[1]);rect(x+9,y+18,w-18,28,pal[0]);rect(x+19,y+7,w-38,19,pal[0]);rect(x+29,y+1,w-58,11,pal[0]);rect(x+9,y+35,w-18,5,'#ffe0e0');rect(x+22,y+19,w-44,4,pal[2]);rect(x+18,y+24,w-36,4,pal[1]);for(let i=0;i<4;i++)for(let j=0;j<3;j++){const xx=x+31+i*Math.max(30,(w-60)/4),yy=y+10+j*15;if(xx<x+w-22){rect(xx,yy,7,3,pal[1]);}}
 for(const xx of [x+42,x+w-72]){rect(xx-5,y+77,38,40,pal[1]);rect(xx,y+81,28,30,'#e9fbdb');rect(xx+4,y+85,20,21,'#87c7ca');rect(xx+12,y+83,3,27,pal[2]);rect(xx,y+95,28,3,pal[2]);rect(xx-8,y+114,44,9,pal[0]);rect(xx-7,y+123,42,5,'#5c9775');}
 const doorX=x+w/2-18;rect(doorX-4,y+hh-64,44,65,pal[1]);rect(doorX,y+hh-62,36,60,'#76556f');rect(doorX+8,y+hh-53,18,21,'#bb94a0');rect(doorX+27,y+hh-25,4,4,'#ffde98');rect(doorX-11,y+hh-4,59,8,'#d9c59b');rect(doorX-5,y+hh+5,47,5,'#b2a38b');
 if(h.name.includes('Mercantile')||h.name.includes('Snacks')||h.name.includes('Library')||h.name.includes('Inn')||h.name.includes('Museum')){
  rect(x+w/2-58,y+56,116,24,'#503656');rect(x+w/2-55,y+59,110,18,'#ffe1b1');rect(x+w/2-51,y+62,102,12,'#563b58');const label=h.name.includes('Mercantile')?'MOTH ✦ MART':h.name.includes('Library')?'LIBRARY':h.name.includes('Snacks')?'SUNPOP':h.name.includes('Inn')?'MOON INN':'MUSEUM';text(label,x+w/2,y+68,11,'#fff7d5');}
 rect(x+5,y+hh-16,23,9,'#2c885d');rect(x+w-27,y+hh-14,24,9,'#388d5e');rect(x+9,y+hh-23,4,6,'#f5baaf');rect(x+w-21,y+hh-23,6,5,'#ffcdd0');
}
function extraProps(x,y,t){const h=rng(x,y,30),px=x*T,py=y*T;
 if(t===0&&h>.982){rect(px+15,py+21,4,10,'#7e6d53');rect(px+8,py+11,19,15,'#ecb0bb');rect(px+13,py+6,9,7,'#ffe0d2');rect(px+13,py+18,5,3,'#fff');}
 if(t===1&&h>.992){rect(px+14,py+5,4,22,'#77624d');rect(px+8,py+1,16,8,'#614859');rect(px+12,py+3,10,5,'#f5dfaa');}
 if(t===0&&h<.011)shrub(px+18,py+22);
}
function lamp(x,y){const px=x*T+T/2,py=y*T+T/2;rect(px-2,py-43,5,53,'#52506b');rect(px-8,py-43,18,5,'#71617c');rect(px-7,py-51,17,9,'#fff0b2');rect(px-5,py-50,13,6,'#ffe5a0');rect(px-11,py+5,23,6,'#4b4859');const pulse=.25+Math.sin(frame*.034+x*7)*.06;ctx.fillStyle=`rgba(255,241,161,${pulse*.35})`;ctx.beginPath();ctx.arc(px,py-43,31,0,Math.PI*2);ctx.fill();}
function signpost(x,y,label){const xx=x*T,yy=y*T;rect(xx+14,yy-17,5,46,'#8a674b');rect(xx-20,yy-18,71,21,'#66526a');rect(xx-17,yy-15,65,15,'#ffdcab');rect(xx-15,yy-13,61,12,'#a26b7c');text(label,xx+15,yy-6,10,'#fff9d8');}
function mailbox(x,y){const px=x*T+16,py=y*T+22;rect(px-3,py-15,6,23,'#664d62');rect(px-14,py-27,29,15,'#e6acb6');rect(px-11,py-30,23,6,'#fff1dc');rect(px+7,py-20,5,5,'#fff2bf');}
function pixelSprite(cx,cy,pal=0,moving=false,npc=false){const bob=moving?Math.sin(frame*.45)*2:Math.sin(frame*.045+cx*.03)*.5;const x=Math.round(cx-16),y=Math.round(cy-41+bob);const top=outfits[pal%outfits.length];
 // soft isometric shadow and dark outlines
 rect(x+4,y+37,26,5,'#31584d88');
 rect(x+7,y+27,8,13,'#3b3551');rect(x+19,y+27,8,13,'#3b3551');rect(x+8,y+29,6,9,'#ffe3ae');rect(x+20,y+29,6,9,'#ffe3ae');rect(x+5,y+37,12,5,'#4a405b');rect(x+18,y+37,12,5,'#4a405b');
 rect(x+4,y+17,26,16,'#4b3051');rect(x+6,y+18,22,15,top);rect(x+13,y+18,8,14,'#ffdfaa');rect(x+4,y+21,4,11,'#efc8a5');rect(x+28,y+20,4,12,'#efc8a5');rect(x+7,y+29,21,4,'#4c3c5c');
 rect(x+7,y+4,21,18,'#5b395c');rect(x+9,y+6,17,15,'#f8d9ac');rect(x+8,y+5,20,7,['#54354f','#65566a','#6a4c39','#56386b','#4e6652','#865152'][pal%6]);rect(x+8,y+2,15,7,['#66507a','#536886','#956d4a','#77518f','#4b7c6d','#a76954'][pal%6]);rect(x+13,y+13,3,3,'#564456');rect(x+22,y+13,3,3,'#564456');rect(x+18,y+18,4,2,'#c88888');
 rect(x+12,y+22,8,3,'#fce5bf');if(npc){rect(x+25,y+3,6,3,'#ffe79d');rect(x+28,y-1,3,5,'#ffe79d');}
}
function signalTower(n){const x=n.x*T,y=n.y*T,found=!!(details?.signalMask&(2**((overworld?.signalNodes||[]).findIndex(s=>s.id===n.id))));const pulse=.5+.5*Math.sin(frame*.06+n.x);ctx.fillStyle=found?'#8ad6ab33':'#69f3d32e';ctx.beginPath();ctx.ellipse(x,y-19,26+pulse*5,30+pulse*9,0,0,Math.PI*2);ctx.fill();rect(x-4,y-48,8,46,'#4b5977');rect(x-15,y-53,30,8,'#c5ab8c');rect(x-17,y-58,34,5,'#f7e6b4');rect(x-5,y-67,10,13,found?'#c1ead2':'#79f3d0');rect(x-12,y-4,24,7,'#526980');text(found?'✓':'♪',x,y-77,17,found?'#d5fff2':'#fbffc9');}
function drawChest(c){const px=c.x*T,py=c.y*T,opened=!!details?.chests?.[c.id];rect(px-17,py-3,36,7,'#32504d88');rect(px-14,py-21,29,21,'#68465a');rect(px-12,py-19,25,17,opened?'#877d70':'#b37355');rect(px-12,py-22,25,7,opened?'#927967':'#edb66c');rect(px-12,py-23,25,3,'#ffe1a0');rect(px-4,py-18,9,15,'#f7d18a');rect(px-1,py-12,3,4,'#775668');if(!opened){rect(px-17,py-28,4,4,'#ffeab4');rect(px+14,py-32,4,4,'#fff6c5');}}
function drawMob(e){const cx=e.x*T,cy=e.y*T,b=Math.sin(frame*.105+e.x*4)*2;const x=Math.round(cx-17),y=Math.round(cy-36+b);rect(cx-19,cy-2,38,6,'#27454c77');
 if(e.kind==='sprout'){rect(x+14,y+1,7,23,'#326d63');rect(x+3,y+10,15,10,'#7cce8d');rect(x+17,y+5,15,12,'#71b978');rect(x+5,y+17,27,17,'#396c77');rect(x+7,y+17,23,16,'#99d6a2');rect(x+10,y+23,4,4,'#4c506e');rect(x+23,y+23,4,4,'#4c506e');rect(x+15,y+28,8,2,'#d88ca5');rect(x+15,y+12,4,4,'#f8ff98');}
 else if(e.kind==='mop'){rect(x+4,y+17,30,15,'#947ab1');rect(x+8,y+9,23,18,'#d7b7da');rect(x+13,y+3,10,10,'#e8d0de');rect(x+7,y+6,5,9,'#d7b7da');rect(x+30,y+4,4,12,'#d7b7da');rect(x+10,y+20,5,5,'#544866');rect(x+24,y+20,5,5,'#544866');rect(x+16,y+26,7,3,'#e28c9f');rect(x+7,y+31,5,4,'#7b658f');rect(x+27,y+31,5,4,'#7b658f');}
 else if(e.kind==='gremlin'){rect(x+5,y+12,30,23,'#d87f97');rect(x+10,y+5,21,15,'#ed9a6c');rect(x,y+13,8,10,'#f0b278');rect(x+32,y+13,8,10,'#f0b278');rect(x+12,y+20,5,6,'#623856');rect(x+24,y+20,5,6,'#623856');rect(x+17,y+27,7,4,'#ffeeac');rect(x+9,y+35,7,5,'#59465e');rect(x+26,y+35,7,5,'#59465e');}
 else if(e.kind==='wisp'){ctx.fillStyle='#c4deffa0';ctx.beginPath();ctx.arc(cx,cy-22,29+2*Math.sin(frame*.11),0,Math.PI*2);ctx.fill();rect(x+7,y+4,26,29,'#98b4f0');rect(x+11,y-4,18,18,'#f2d6ff');rect(x+16,y+15,4,6,'#535787');rect(x+25,y+15,4,6,'#535787');rect(x+19,y+23,7,2,'#ffebea');rect(x+5,y+30,6,6,'#d1b2ef');rect(x+29,y+30,6,6,'#d1b2ef');}
 else if(e.kind==='glitch'||e.kind==='bopper'||e.kind==='riftling'){const tint=e.kind==='glitch'?'#73fae4':e.kind==='bopper'?'#ff9bdb':'#bca0ff';ctx.fillStyle=tint+'66';ctx.beginPath();ctx.ellipse(cx,cy-17,22,23,0,0,Math.PI*2);ctx.fill();rect(x+6,y+5,26,26,'#2c2949');rect(x+9,y+8,21,20,tint);rect(x+12,y+14,4,6,'#242039');rect(x+23,y+14,4,6,'#242039');rect(x+15,y+24,10,3,'#f8f7dc');rect(x+11,y+1,5,5,'#ffe3a2');rect(x+28,y-3,4,4,'#ffe3a2');}
 else {const pulse=1+Math.sin(frame*.055)*.05;ctx.fillStyle='#dac0ff44';ctx.beginPath();ctx.arc(cx,cy-30,58*pulse,0,Math.PI*2);ctx.fill();rect(x-20,y-42,72,76,'#503b70');rect(x-15,y-46,62,70,'#9275b8');rect(x-7,y-62,46,22,'#b99ad9');rect(x-11,y-32,16,15,'#ffdfab');rect(x+28,y-32,16,15,'#ffdfab');rect(x+3,y-20,9,10,'#2a244b');rect(x+24,y-20,9,10,'#2a244b');rect(x+12,y,12,5,'#312246');rect(x-17,y+21,14,18,'#503b70');rect(x+40,y+21,14,18,'#503b70');}
 if(e.hp<e.maxHp){rect(cx-23,cy-49,46,7,'#2c2345');rect(cx-21,cy-47,42*Math.max(0,e.hp/e.maxHp),3,e.boss?'#ffc68d':'#ffb3ba');}
 if(e.boss)text(e.kind==='riftboss'?'✦ RIFT OVERLORD ✦':'✦ THE HUSHLING ✦',cx,cy-91,12,'#ffd7ad');
}
function drawWorld(){if(!world)return;if(engine3d&&settings.mode!=='2d'){frame++;engine3d.render({world,visual,players,enemies,me,playing,time:performance.now()});requestAnimationFrame(drawWorld);return;}frame++;ctx.fillStyle='#639f69';ctx.fillRect(0,0,W,H);
 const target=visual||{x:24.5,y:33.5};const tx=target.x*T-W/2,ty=target.y*T-H/2;
 cam.x+=(tx-cam.x)*.14;cam.y+=(ty-cam.y)*.14;cam.x=Math.max(0,Math.min(world.width*T-W,cam.x));cam.y=Math.max(0,Math.min(world.height*T-H,cam.y));
 ctx.save();ctx.translate(-Math.floor(cam.x),-Math.floor(cam.y));
 const minX=Math.max(0,Math.floor(cam.x/T)-2),maxX=Math.min(world.width,Math.ceil((cam.x+W)/T)+2),minY=Math.max(0,Math.floor(cam.y/T)-3),maxY=Math.min(world.height,Math.ceil((cam.y+H)/T)+3);
 for(let y=minY;y<maxY;y++)for(let x=minX;x<maxX;x++)tile(x,y,world.tiles[y][x]);
 for(let y=minY;y<maxY;y++)for(let x=minX;x<maxX;x++)extraProps(x,y,world.tiles[y][x]);
 // scenery elements sorted by feet coordinates, enabling believable depth layering
 const actors=[];
 for(const t of world.trees)if(t.x>=minX-2&&t.x<=maxX+2&&t.y>=minY-2&&t.y<=maxY+2)actors.push({y:(t.y+1)*T,fn:()=>tree(t)});
 for(const h of world.houses)if(h.x+h.w>minX&&h.x<maxX&&h.y+h.h>minY&&h.y<maxY)actors.push({y:(h.y+h.h+.5)*T,fn:()=>house(h)});
 const lamps=zone==='overworld'?[[8,33],[18,28],[32,29],[43,33],[54,33],[63,20],[71,33],[73,56],[82,54],[39,44],[24,46],[102,25],[115,23],[108,44],[114,53],[102,77],[120,78]]:[];
 for(const [x,y] of lamps)if(x>=minX-2&&x<=maxX+2&&y>=minY-2&&y<=maxY+2)actors.push({y:(y+.5)*T,fn:()=>lamp(x,y)});
 for(const s of (zone==='overworld'?[[22,28,'PINEBELL'],[58,24,'MOONBERRY'],[68,57,'SODA SHORE'],[106,29,'ARCADE'],[106,37,'SPARK YARD'],[110,80,'COMMONS']]:[]))if(s[0]>minX-3&&s[0]<maxX+3&&s[1]>minY-3&&s[1]<maxY+3)actors.push({y:s[1]*T+14,fn:()=>signpost(...s)});
 for(const [x,y] of (zone==='overworld'?[[29,32],[9,36],[59,18],[80,53],[15,45],[108,28],[109,73]]:[]))if(x>=minX-1&&x<=maxX+1&&y>=minY-1&&y<=maxY+1)actors.push({y:(y+.5)*T,fn:()=>mailbox(x,y)});
 for(const n of world.signalNodes||[])if(n.x>minX-1&&n.x<maxX+1&&n.y>minY-1&&n.y<maxY+1)actors.push({y:n.y*T,fn:()=>signalTower(n)});
 for(const c of world.chests||[])if(c.x>minX-1&&c.x<maxX+1&&c.y>minY-1&&c.y<maxY+1)actors.push({y:c.y*T,fn:()=>drawChest(c)});
 for(const n of world.npcs)if(n.x>minX-1&&n.x<maxX+1&&n.y>minY-1&&n.y<maxY+1)actors.push({y:n.y*T,fn:()=>{pixelSprite(n.x*T,n.y*T,n.palette,false,true);text(n.name,n.x*T,n.y*T-51,11,'#fff6d4');if(n.quest){text('!',n.x*T,n.y*T-68,23,'#ffdd8a');}if(n.shop)text('◇',n.x*T,n.y*T-67,17,'#ffdda2');}});
 for(const e of enemies)if(e.alive&&e.x>minX-2&&e.x<maxX+2&&e.y>minY-2&&e.y<maxY+2)actors.push({y:e.y*T,fn:()=>drawMob(e)});
 for(const p of players)if(p.id!==me?.id&&p.x>minX-1&&p.x<maxX+1&&p.y>minY-1&&p.y<maxY+1)actors.push({y:p.y*T,fn:()=>{pixelSprite(p.x*T,p.y*T,p.palette,p.state==='walk');text(p.name,p.x*T,p.y*T-53,11,'#e9fbff');const em=emotes.get(p.id);if(em&&em.until>Date.now())text(em.emoji,p.x*T,p.y*T-70,20);}});
 if(playing&&visual){const v=visual;actors.push({y:v.y*T+.01,fn:()=>{pixelSprite(v.x*T,v.y*T,details?.palette||0,Object.values(keys).some(Boolean));text(details?.name||'You',v.x*T,v.y*T-54,12,'#fff9bc');text('▼',v.x*T,v.y*T-72,12,'#ffcd78');const em=emotes.get(me?.id);if(em&&em.until>Date.now())text(em.emoji,v.x*T,v.y*T-87,20);}});}
 else {actors.push({y:33.5*T,fn:()=>{pixelSprite(24.5*T,33.5*T,0,false);}});}
 actors.sort((a,b)=>a.y-b.y);for(const a of actors)a.fn();
 // drifting fireflies and effect particles, on top of geography
 for(let i=particles.length-1;i>=0;i--){let p=particles[i];p.life--;p.x+=p.vx;p.y+=p.vy;if(p.life<=0){particles.splice(i,1);continue;}ctx.globalAlpha=Math.min(1,p.life/20);if(p.text)text(p.text,p.x,p.y,Math.round(p.size),p.color);else rect(p.x,p.y,p.size,p.size,p.color);ctx.globalAlpha=1;}
 ctx.restore();
 // soft vignette around the playable world
 let gradient=ctx.createRadialGradient(W/2,H/2,130,W/2,H/2,640);gradient.addColorStop(0,'#100b1700');gradient.addColorStop(1,'#26113b57');ctx.fillStyle=gradient;ctx.fillRect(0,0,W,H);
 if(zone==='overworld'){const haze=ctx.createLinearGradient(0,0,W,H);haze.addColorStop(0,'#53427b10');haze.addColorStop(.6,'#8c3a720d');haze.addColorStop(1,'#0b174b23');ctx.fillStyle=haze;ctx.fillRect(0,0,W,H);}
 if(!playing){ctx.fillStyle='#1f0b3350';ctx.fillRect(0,0,W,H);}
 requestAnimationFrame(drawWorld);
}
function screenOf(x,y){return {x:x*T-cam.x,y:y*T-cam.y};}
function effect(ev){const base=screenOf(ev.x,ev.y); // particles are world-space
 if(ev.kind==='hit'||ev.kind==='burst'){const msg=(ev.crit?'CRIT ':'')+ev.damage;particles.push({x:ev.x*T,y:ev.y*T-57,vx:(Math.random()-.5)*1.4,vy:-1.4,size:ev.crit?17:13,life:49,text:msg,color:ev.crit?'#ffe99a':'#fff4e6'});if(ev.kind==='burst')for(let i=0;i<23;i++){const angle=i*Math.PI*2/23;particles.push({x:ev.x*T,y:ev.y*T-25,vx:Math.cos(angle)*3.4,vy:Math.sin(angle)*2.6,size:4,life:16,color:i%2?'#bca6ff':'#ffe49f'});}}
 if(ev.kind==='defeat')for(let i=0;i<28;i++){const angle=Math.random()*Math.PI*2;particles.push({x:ev.x*T,y:ev.y*T-26,vx:Math.cos(angle)*(1+Math.random()*3),vy:Math.sin(angle)*(1+Math.random()*3),size:3+Math.random()*4,life:24+Math.random()*26,color:i%3?'#f8e39b':'#f2a7ce'});}
 if(ev.kind==='chest')for(let i=0;i<22;i++){const angle=i*Math.PI*2/22;particles.push({x:ev.x*T,y:ev.y*T-20,vx:Math.cos(angle)*2,vy:Math.sin(angle)*2,size:4,life:30,color:'#ffe799'});}
 if(ev.kind==='hurt')particles.push({x:ev.x*T,y:ev.y*T-53,vx:0,vy:-1,size:15,life:42,text:'-'+ev.damage,color:'#ffc0ba'});
}
function action(name,id){if(ws?.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type:'action',action:name,id}));}
function actionExtra(name,options={}){if(ws?.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type:'action',action:name,...options}));}
function sendInput(){if(ws?.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type:'input',keys}));}
function isWalkable(x,y){if(!world)return false;const ix=Math.floor(x),iy=Math.floor(y);if(ix<2||iy<2||ix>=world.width-2||iy>=world.height-2)return false;const t=world.tiles[iy]?.[ix];if(t===3||t===4)return false;if(world.treeCells.has(ix+','+iy))return false;for(const h of world.houses)if(ix>=h.x&&ix<h.x+h.w&&iy>=h.y&&iy<h.y+h.h)return false;return true;}
function isSafe(x,y){return isWalkable(x-.21,y-.19)&&isWalkable(x+.21,y-.19)&&isWalkable(x-.21,y+.19)&&isWalkable(x+.21,y+.19);}
function predict(){if(playing&&visual){const dt=Math.min(.07,(performance.now()-lastUpdate)/1000||.016);const ix=(keys.right?1:0)-(keys.left?1:0),iy=(keys.down?1:0)-(keys.up?1:0),n=Math.hypot(ix,iy)||1,s=(details?.class==='Scout'?4.35:3.85)*dt;
 if(ix||iy){let nx=visual.x+ix/n*s,ny=visual.y+iy/n*s;if(isSafe(nx,visual.y))visual.x=nx;if(isSafe(visual.x,ny))visual.y=ny;}
 if(me){const d=Math.hypot(me.x-visual.x,me.y-visual.y);if(d>1.4){visual={x:me.x,y:me.y};}else if(d>.1){visual.x+=(me.x-visual.x)*.065;visual.y+=(me.y-visual.y)*.065;}}
 const nearSignal=world?.signalNodes?.find(n=>Math.hypot(n.x-visual.x,n.y-visual.y)<2.4);
 const nearChest=world?.chests?.find(c=>Math.hypot(c.x-visual.x,c.y-visual.y)<1.9&&!details?.chests?.[c.id]);
 const nearNpc=world?.npcs.find(n=>Math.hypot(n.x-visual.x,n.y-visual.y)<2.7);$('nearbyHint').classList.toggle('hidden',(!nearNpc&&!nearChest&&!nearSignal)||!!dialogue);if(nearSignal)$('nearbyHint').textContent='E · TUNE '+nearSignal.name.toUpperCase();else if(nearChest)$('nearbyHint').textContent='E · OPEN SECRET STASH';else if(nearNpc)$('nearbyHint').textContent=nearNpc.shop?'E · TALK / SHOP':`E · TALK TO ${nearNpc.name.toUpperCase()}`;
 let near=zone==='overworld'?'THE WILDWAYS':'THE RIFT',sub='Where strange things roam';for(const place of world.places){const d=Math.hypot(visual.x-place.x,visual.y-place.y);if(d<place.r){near=place.name;sub=place.sub;break;}}
 if(near!==region){region=near;$('regionLabel').textContent=near;$('regionSubtitle').textContent='— '+sub;$('hudRegion').textContent=near;}
 }
 lastUpdate=performance.now();requestAnimationFrame(predict);
}
function resetKeys(){for(const k of Object.keys(keys))keys[k]=false;sendInput();}
function onKey(e,down){if(!playing)return;if($('helpModal').classList.contains('hidden')===false)return;const tag=e.target?.tagName?.toLowerCase();if(tag==='input'||tag==='textarea'||tag==='select'){
 if(e.key==='Escape'){e.target.blur();e.preventDefault();}return;}
 const map={w:'up',arrowup:'up',s:'down',arrowdown:'down',a:'left',arrowleft:'left',d:'right',arrowright:'right'};const key=e.key.toLowerCase();if(map[key]){keys[map[key]]=down;sendInput();e.preventDefault();return;}
 if(!down)return;
 if([' ','spacebar','f','e','h','r','i','m','q','o','enter','escape','1','2','3','4'].includes(key))e.preventDefault();
 if(miniChallenge)return;if(!settingsModal.classList.contains('hidden')){if(key==='escape')closeSettings();return;}
 if(dialogue){if(key==='e'||key==='enter'||key===' '){advanceDialogue();return;}if(key==='escape'){hideDialogue();return;}}
 if(key===' '){action('attack');beep(390,.08,'square',.025);}else if(key==='f'){action('burst');beep(570,.17,'triangle',.05);}else if(key==='e')action('interact');else if(key==='h')action('use','fizzy-pop');else if(key==='r')action('team-heal');else if(key==='i')selectPanel('bag');else if(key==='m')selectPanel('map');else if(key==='q')openHelp();else if(key==='o')openSettings();else if(key==='enter'){$('chatInput').focus();}else if(['1','2','3','4'].includes(key))action('emote',Number(key)-1);
}
window.addEventListener('keydown',e=>onKey(e,true));window.addEventListener('keyup',e=>onKey(e,false));window.addEventListener('blur',resetKeys);
function showDialogue(npc){dialogue=npc;dialogueIndex=0;$('dialogue').classList.remove('hidden');$('dialogueSpeaker').textContent=npc.name.toUpperCase()+' · '+npc.role.toUpperCase();$('dialoguePortrait').textContent=npc.shop?'🛍':npc.quest?'✦':'☻';advanceDialogue(true);}
function advanceDialogue(initial=false){if(!dialogue)return;if(!initial)dialogueIndex++;if(dialogueIndex>=dialogue.dialogue.length){if(dialogue.shop)selectPanel('shop');hideDialogue();return;}const line=dialogue.dialogue[dialogueIndex];$('dialogueText').textContent=line;}
function hideDialogue(){dialogue=null;$('dialogue').classList.add('hidden');}
$('dialogueClose').addEventListener('click',hideDialogue);
function toast(msg,kind='info'){const div=document.createElement('div');div.className='toast '+kind;div.textContent=msg;$('toasts').prepend(div);setTimeout(()=>div.remove(),3700);while($('toasts').children.length>4)$('toasts').lastChild.remove();}
function setViewData(p){if(!p)return;details=p;if(!visual)visual={x:p.x,y:p.y};if(me?.id===p.id){me.x=p.x;me.y=p.y;}else me={...p};$('charName').textContent=p.name;$('charRank').textContent=`LEVEL ${String(p.level).padStart(2,'0')}  ·  ${p.class.toUpperCase()}`;$('portrait').style.background=`linear-gradient(140deg,${outfits[p.palette]}a8,#342747)`;$('portrait').firstElementChild.textContent=p.class==='Guardian'?'♥':p.class==='Dreamer'?'✧':'⚡';$('charStars').textContent='✦ '.repeat(Math.min(5,1+Math.floor(p.level/8)))+'✧ '.repeat(Math.max(0,4-Math.floor(p.level/8)));$('hpLabel').textContent=`${p.hp} / ${p.maxHp}`;$('focusLabel').textContent=`${Math.floor(p.focus)} / ${p.maxFocus}`;$('xpLabel').textContent=`${p.xp} / ${p.xpNeeded} XP`;$('hpBar').style.width=100*p.hp/p.maxHp+'%';$('focusBar').style.width=100*p.focus/p.maxFocus+'%';$('xpBar').style.width=100*p.xp/p.xpNeeded+'%';$('goldCount').textContent=p.gold;$('atkCount').textContent=p.attack;$('defCount').textContent=p.defense;
 let name,txt,prog;
 if(p.bossDone){name='The Airwaves Are Alive';txt='You defeated the Hushling! Now explore, collect rare gear, run Rifts and make lasting friends.';prog=3;}else if(p.questDone){name='The Lost Mixtape';txt='You collected three lost signals and revived the mixtape. The game is yours to explore!';prog=3;}else{name='Collect the Lost Signals';txt='Find and tune ANY three glowing radio towers across the six regions. No mandatory combat, no chores.';prog=Math.min(3,p.questKills||0);}
 $('questName').textContent=name;$('questText').textContent=txt;$('questProgressText').textContent=p.questDone?'THE AIRWAVES':'SIGNALS DISCOVERED';$('questProgress').textContent=p.questDone?'RESTORED!':`${prog} / 3`;$('questBar').style.width=(prog/3*100)+'%';if(['bag','shop','activities','social','home'].includes(view))renderPanel();}
function makeButton(label,handler){const b=document.createElement('button');b.className='item-action';b.type='button';b.textContent=label;b.addEventListener('click',handler);return b;}
function appendItem(container,id,qty=0,buttonType='equip'){
 const it=world.items[id];if(!it)return;const row=document.createElement('div');row.className='inventory-item';const em=document.createElement('div');em.className='item-emoji';em.textContent=it.icon;row.appendChild(em);
 const meta=document.createElement('div');meta.className='item-detail';const n=document.createElement('div');n.className='item-name';n.textContent=it.name+(qty?' ×'+qty:'');meta.appendChild(n);const rarity=document.createElement('div');rarity.className='rarity '+it.rarity;rarity.textContent=it.rarity+' · '+(it.atk?'+'+it.atk+' ATK':it.def?'+'+it.def+' DEF':it.heal?'+'+it.heal+' HP':'');meta.appendChild(rarity);const desc=document.createElement('div');desc.className='item-desc';desc.textContent=it.description;meta.appendChild(desc);row.appendChild(meta);
 if(buttonType==='buy')row.appendChild(makeButton(it.price+' ✦',()=>action('buy',id)));
 else if(it.slot==='consumable')row.appendChild(makeButton('USE',()=>action('use',id)));
 else if(it.slot==='weapon'||it.slot==='armor'||it.slot==='pet')row.appendChild(makeButton(details?.equipped?.[it.slot]===id?'ON':'EQUIP',()=>action('equip',id)));
 container.appendChild(row);
}
function activityCard(parent,title,desc,fn){const row=document.createElement('div');row.className='activity-card';const meta=document.createElement('div');const t=document.createElement('strong');t.textContent=title;const sub=document.createElement('p');sub.textContent=desc;meta.append(t,sub);const b=makeButton('GO',fn);row.append(meta,b);parent.appendChild(row);}
function selectPanel(which){if(which==='shop'){$('panelContent').replaceChildren();view='shop';renderPanel();return;}view=which;document.querySelectorAll('[data-panel]').forEach(b=>b.classList.toggle('active',b.dataset.panel===which));renderPanel();}
async function renderPanel(){if(!world)return;const host=$('panelContent');host.replaceChildren();if(view==='bag'||view==='shop'){
 if(view==='shop'){const title=document.createElement('div');title.className='tiny-news-head';title.textContent='✦ MIRA’S MOTHLIGHT MARKET';host.appendChild(title);const p=document.createElement('p');p.className='map-caption';p.textContent='Everything you need, except a money-back guarantee!';host.appendChild(p);for(const id of world.shopStock)appendItem(host,id,0,'buy');return;}
 const bag=details?.inventory||{};if(!Object.keys(bag).length){const empty=document.createElement('div');empty.className='empty-panel';empty.textContent='Your bag is empty, but your heart is full. ✨';host.appendChild(empty);}else for(const [id,qty] of Object.entries(bag).sort((a,b)=>itemRank.indexOf(world.items[b[0]]?.rarity)-itemRank.indexOf(world.items[a[0]]?.rarity)))appendItem(host,id,qty);
 }else if(view==='map'){
 const c=document.createElement('canvas');c.width=264;c.height=188;c.className='map-canvas';host.appendChild(c);const m=c.getContext('2d');for(let y=0;y<world.height;y++)for(let x=0;x<world.width;x++){const t=world.tiles[y][x];m.fillStyle=['#6ead78','#cdb087','#edcf92','#5b9dbc','#2c6a52','#afa6a0','#b66f99'][t];const sx=264/world.width,sy=188/world.height;m.fillRect(x*sx,y*sy,Math.ceil(sx),Math.ceil(sy));}for(const h of world.houses){m.fillStyle='#f7acc4';m.fillRect(h.x*264/world.width,h.y*188/world.height,h.w*264/world.width,h.h*188/world.height);}for(const place of world.places){m.fillStyle='#fff9db';m.fillRect(place.x*264/world.width-2,place.y*188/world.height-2,5,5);}if(me){m.fillStyle='#fc3c86';m.fillRect(Math.floor(me.x*264/world.width)-2,Math.floor(me.y*188/world.height)-2,6,6);}const label=document.createElement('div');label.className='map-caption';label.textContent='◆ You   ◇ 6 districts · Arcade · Arena · Co-op Gate · Housing';host.appendChild(label);
 }else if(view==='activities'){
 const heading=document.createElement('div');heading.className='tiny-news-head';heading.textContent='✳ THINGS TO DO (NO DAILY CHORES)';host.appendChild(heading);
 const p=document.createElement('p');p.className='activity-intro';p.textContent='Explore freely. Try an activity at its world location. Prize rewards are capped fairly; the fun is not.';host.appendChild(p);
 activityCard(host,'🎮 MEMORY JAM','Neon Boardwalk · replay a tune, win cassette collectibles.',()=>action('minigame-start','arcade'));
 activityCard(host,'🎣 PIXEL FISHING','Soda Shore · catch a melody, win snacks and stardust.',()=>action('minigame-start','fish'));
 activityCard(host,'☄ STATIC STORM SURVIVAL','SOLO · Neon Boardwalk · 90-second auto-attack survival. Dodge swarms, survive waves, earn fair daily prizes.',()=>action('survival-start'));
 activityCard(host,'📡 DUO BROADCAST','Wildway Gate · two travelers tune in together within 20 seconds.',()=>action('beacon'));
 const title=document.createElement('div');title.className='tiny-news-head';title.textContent='◈ CO-OP RIFT EXPEDITIONS';host.appendChild(title);
 for(const r of overworld?.rifts||[])activityCard(host,'✦ '+r.name,r.subtitle+' · Recommended Lv '+r.level,()=>action('dungeon-start',r.id));
 activityCard(host,'♫ DUO RHYTHM JAM','Neon Boardwalk · two players hit the jukebox within 9 seconds. Shared tunes and rewards.',()=>action('jam'));
 activityCard(host,'🏎 CIRCUIT SPRINT · MULTIPLAYER','2–4 racers · start at Boardwalk. Hit Spark Yard, Spark Crossing and Cassette Commons checkpoints.',()=>action('race-start'));
 activityCard(host,'🏁 SIGNAL RELAY · CO-OP','2–4 players · Wildway Gate · split up, reach three distant towers within 7 minutes. All teammates earn rewards.',()=>action('relay-start'));
 if(zone!=='overworld')activityCard(host,'↩ LEAVE THE RIFT','Return to the Wildway portal.',()=>action('dungeon-exit'));
 }else if(view==='social'){
 const title=document.createElement('div');title.className='tiny-news-head';title.textContent='♥ TEAM UP & PLAY SAFELY';host.appendChild(title);
 const party=details?.party?.members||[];const label=document.createElement('p');label.className='activity-intro';label.textContent='Your team: '+party.map(p=>p.name).join(' · ')+' (max 4)';host.appendChild(label);
 const target=document.createElement('input');target.placeholder='Nearby traveler name';target.maxLength=16;target.className='panel-input';host.appendChild(target);
 activityCard(host,'💖 HEARTWAVE (R)','Spend 25 Focus to heal yourself and nearby teammates.',()=>action('team-heal'));
 activityCard(host,'✉ INVITE TO TEAM','Invite a nearby player (they must accept).',()=>action('party-invite',target.value.trim()));
 activityCard(host,'↩ LEAVE TEAM','You can leave at any time.',()=>action('party-leave'));
 const a=document.createElement('div');a.className='tiny-news-head';a.textContent='⚔ FRIENDLY SPARK YARD';host.appendChild(a);
 activityCard(host,'⚔ '+(details?.pvp?'DISABLE':'ENABLE')+' PVP','Inside the Spark Yard only. Both players opt in. Gear advantage removed. No lost items.',()=>action('pvp-toggle'));
 const r=document.createElement('div');r.className='tiny-news-head';r.textContent='🛡 COMMUNITY TOOLS';host.appendChild(r);
 const reason=document.createElement('select');reason.className='panel-input';for(const [val,label] of [['harassment','Harassment'],['spam','Spam'],['unsafe','Unsafe behavior'],['cheating','Cheating'],['other','Other']]){const o=document.createElement('option');o.value=val;o.textContent=label;reason.appendChild(o);}host.appendChild(reason);
 activityCard(host,'⛨ REPORT PLAYER','Reports are saved for moderator review.',()=>actionExtra('report',{id:target.value.trim(),reason:reason.value}));
 activityCard(host,'🚫 BLOCK PLAYER','Hide their messages and avatar from your view.',()=>action('block',target.value.trim()));
 }else if(view==='home'){
 const title=document.createElement('div');title.className='tiny-news-head';title.textContent='⌂ MY LITTLE CORNER OF THE UNIVERSE';host.appendChild(title);
 const home=details?.home;
 if(!home){const text=document.createElement('p');text.className='activity-intro';text.textContent='Visit Tilly in Cassette Commons and claim an available plot for 450 stardust. No real money, no rent.';host.appendChild(text);for(let i=0;i<4;i++)activityCard(host,'⌂ CLAIM HOUSE '+(i+1),'Private room · one per account.',()=>action('home-buy',String(i)));}
 else{
 const room=document.createElement('div');room.className='home-preview '+home.theme;room.innerHTML='<span class="room-ceiling">✦ YOUR SPACE ✦</span><div class="room-furniture"></div><div class="room-floor"></div>';room.querySelector('.room-furniture').textContent=({beanbag:'🛋️',arcade:'🕹️',plants:'🪴',bookshelf:'📚',jukebox:'🎶'})[home.furniture]||'🛋️';host.appendChild(room);
 const txt=document.createElement('p');txt.className='activity-intro';txt.textContent='Room '+(home.plot+1)+' · '+home.theme+' · '+home.furniture+'. Every new style costs 35 stardust.';host.appendChild(txt);
 for(const x of ['violet','sunset','ocean','forest','neon'])activityCard(host,'🎨 '+x.toUpperCase(),'Apply this room color.',()=>action('home-theme',x));
 for(const x of ['beanbag','arcade','plants','bookshelf','jukebox'])activityCard(host,'✦ '+x.toUpperCase(),'Swap the centerpiece.',()=>action('home-furniture',x));
 activityCard(host,'PRIVATE ROOM (DEFAULT)','Keep your home off public listings.',()=>action('home-public','no'));
 }
 }else if(view==='rank'){
 const title=document.createElement('div');title.className='tiny-news-head';title.textContent='★ STARFALL HALL OF FAME';host.appendChild(title);
 try{const res=await fetch('api/leaderboard');const j=await res.json();if(view!=='rank')return;for(const [i,p] of (j.players||[]).entries()){const r=document.createElement('div');r.className='rank-row';const n=document.createElement('span');n.className='rank-number';n.textContent=String(i+1).padStart(2,'0');const name=document.createElement('b');name.textContent=p.username;const level=document.createElement('span');level.className='rank-level';level.textContent='LV '+p.level;r.append(n,name,level);host.appendChild(r);}if(!j.players?.length){const empty=document.createElement('div');empty.className='empty-panel';empty.textContent='Be the first legend on the board!';host.appendChild(empty);}}catch{host.textContent='Leaderboard unavailable.';}
 }}
document.querySelectorAll('[data-panel]').forEach(btn=>btn.addEventListener('click',()=>selectPanel(btn.dataset.panel)));
$('questBtn').addEventListener('click',openHelp);
function chatEntry(name,msg,system=false){const feed=$('chatFeed');const row=document.createElement('div');if(system)row.className='system';if(!system){const n=document.createElement('b');n.textContent=name+': ';row.appendChild(n);}row.appendChild(document.createTextNode(msg));feed.appendChild(row);while(feed.children.length>7)feed.firstChild.remove();}
$('chatForm').addEventListener('submit',e=>{e.preventDefault();const input=$('chatInput'),quick=$('quickChat');if(overworld?.textChat){const text=input.value.trim();if(!text)return;if(ws?.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type:'chat',text}));input.value='';input.blur();}else{const index=Number(quick.value);if(quick.value===''||!Number.isInteger(index))return;if(ws?.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type:'chat',quick:true,index}));quick.value='';}});
function connect(){const scheme=location.protocol==='https:'?'wss':'ws';ws=new WebSocket(`${scheme}://${location.host}${location.pathname.replace(/[^/]*$/,"")}ws`);ws.onopen=()=>{playing=true;$('loginOverlay').classList.add('hidden');$('gameHud').classList.remove('hidden');$('chatPanel').classList.remove('hidden');$('logoutBtn').classList.remove('hidden');$('mobileControls').classList.toggle('hidden',!('ontouchstart' in window||navigator.maxTouchPoints>0));chatEntry('','The airwaves are safe. Quick-chat is on. Have fun!',true);sendInput();};
 ws.onmessage=e=>{let j;try{j=JSON.parse(e.data)}catch{return;}if(j.type==='welcome'){setViewData(j.player);toast('✧ Your adventure begins!');$('onlineCount').textContent=(j.online||1)+' TRAVELER'+(j.online===1?'':'S')+' ONLINE';renderPanel();}
 else if(j.type==='self')setViewData(j.player);
 else if(j.type==='snapshot'){players=j.players;enemies=j.enemies;const mine=players.find(p=>p.id===me?.id);if(mine){me={...mine};if(!visual)visual={x:me.x,y:me.y};if(details&&(details.hp!==mine.hp||details.focus!==mine.focus)){details.hp=mine.hp;details.focus=mine.focus;$('hpLabel').textContent=`${mine.hp} / ${mine.maxHp}`;$('focusLabel').textContent=`${mine.focus} / ${mine.maxFocus}`;$('hpBar').style.width=(100*mine.hp/mine.maxHp)+'%';$('focusBar').style.width=(100*mine.focus/mine.maxFocus)+'%';}}if(j.survival){survivalInfo=j.survival;$('survivalHud').classList.remove('hidden');$('survivalHud').textContent=`☄ STATIC STORM · WAVE ${j.survival.wave} · ${j.survival.remaining}s · ${j.survival.kills} ECHOES`;}else{$('survivalHud').classList.add('hidden');survivalInfo=null;}if(frame%28===0)$('onlineCount').textContent=players.length+' TRAVELER'+(players.length===1?'':'S')+' ONLINE';}
 else if(j.type==='effect'){effect(j);if(j.kind==='burst'||j.kind==='chest')beep(520,.15,'triangle',.013);}
 else if(j.type==='toast'){toast(j.msg,j.kind);if(j.kind==='level')beep(760,.18,'triangle',.016);else if(j.kind==='loot')beep(630,.1,'sine',.013);}
 else if(j.type==='dialogue')showDialogue(j.npc);
 else if(j.type==='chat')chatEntry(j.name,j.text);
 else if(j.type==='scene'){zone=j.zone;world=j.world||overworld;world.treeCells=new Set((world.trees||[]).map(t=>t.x+','+t.y));enemies=[];players=[];visual=null;cam.x=0;cam.y=0;region='';selectPanel('activities');}
 else if(j.type==='invite'){if(confirm(`${j.name} invited you to a team! Accept?`))action('party-accept');}
 else if(j.type==='minigame'){startMini(j);}
 else if(j.type==='survival-result'){toast(`STATIC STORM · SCORE ${j.score} · PERSONAL BEST ${j.best}`,'level');}
 else if(j.type==='emote')emotes.set(j.id,{emoji:j.emoji,until:Date.now()+2200});
 };
 ws.onclose=()=>{if(playing){playing=false;resetKeys();$('gameHud').classList.add('hidden');$('chatPanel').classList.add('hidden');$('loginOverlay').classList.remove('hidden');$('logoutBtn').classList.add('hidden');toast('Disconnected. Sign in to continue.','warning');}};
 ws.onerror=()=>{if(!playing)toast('Could not connect. Is the server running?','warning');};
}
function openHelp(){$('helpModal').classList.remove('hidden');resetKeys();}
function closeHelp(){$('helpModal').classList.add('hidden');}
$('helpBtn').addEventListener('click',openHelp);$('helpClose').addEventListener('click',closeHelp);$('helpModal').addEventListener('click',e=>{if(e.target===$('helpModal'))closeHelp();});
async function post(url,body={}){const res=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),credentials:'same-origin'});const j=await res.json();if(!res.ok)throw Error(j.error||'Something went wrong.');return j;}
function setMode(m){mode=m;document.querySelector('.age-ack').classList.toggle('hidden',m==='login');$('ageCheck').required=m==='register';$('tabRegister').classList.toggle('active',m==='register');$('tabLogin').classList.toggle('active',m==='login');$('newCharacter').classList.toggle('hidden',m==='login');$('playBtn').firstChild.textContent=m==='register'?'BEGIN YOUR STORY ':'RETURN TO THE VALE ';$('password').autocomplete=m==='login'?'current-password':'new-password';$('password').placeholder=m==='login'?'Your passphrase':'10+ characters';$('authError').textContent='';}
$('tabRegister').addEventListener('click',()=>setMode('register'));$('tabLogin').addEventListener('click',()=>setMode('login'));
document.querySelectorAll('[data-class]').forEach(btn=>btn.addEventListener('click',()=>{klass=btn.dataset.class;document.querySelectorAll('[data-class]').forEach(b=>b.classList.toggle('selected',b===btn));}));
document.querySelectorAll('[data-palette]').forEach(btn=>btn.addEventListener('click',()=>{palette=Number(btn.dataset.palette);document.querySelectorAll('[data-palette]').forEach(b=>b.classList.toggle('selected',b===btn));}));
$('authForm').addEventListener('submit',async e=>{e.preventDefault();$('authError').textContent='';const b=$('playBtn');b.disabled=true;b.firstChild.textContent='OPENING THE GATES ';try{await post('api/'+(mode==='register'?'register':'login'),{username:$('username').value,password:$('password').value,class:klass,palette,age13:$('ageCheck').checked});connect();}catch(e){$('authError').textContent=e.message;}finally{b.disabled=false;b.firstChild.textContent=mode==='register'?'BEGIN YOUR STORY ':'RETURN TO THE VALE ';}});
$('demoBtn').addEventListener('click',async()=>{if(!$('ageCheck').checked){$('authError').textContent='Confirm you are at least 13 before entering.';return;}const b=$('demoBtn');b.disabled=true;b.textContent='Opening the secret gate...';try{await post('api/demo',{class:klass,palette,age13:$('ageCheck').checked});connect();}catch(e){$('authError').textContent=e.message;}finally{b.disabled=false;b.textContent='or peek inside as a guest ↗ (unsaved)';}});
$('logoutBtn').addEventListener('click',async()=>{try{await post('api/logout');}catch{}if(ws)ws.close();playing=false;visual=null;me=null;details=null;$('loginOverlay').classList.remove('hidden');$('gameHud').classList.add('hidden');$('chatPanel').classList.add('hidden');$('logoutBtn').classList.add('hidden');});
for(const btn of document.querySelectorAll('.action-buttons [data-action],.mobile-actions [data-action]'))btn.addEventListener('click',()=>action(btn.dataset.action));
for(const b of document.querySelectorAll('.dpad [data-dir]')){const press=e=>{e.preventDefault();keys[b.dataset.dir]=true;sendInput();};const release=e=>{e.preventDefault();keys[b.dataset.dir]=false;sendInput();};b.addEventListener('pointerdown',press);b.addEventListener('pointerup',release);b.addEventListener('pointercancel',release);b.addEventListener('pointerleave',release);}
function beep(freq,seconds=0.08,type='triangle',gain=.016,channel='sfx'){if(channel==='music'&&!music)return;if(channel==='sfx'&&!settings.sfx)return;if(!audio){try{audio=new (window.AudioContext||window.webkitAudioContext)();}catch{return;}}if(audio.state==='suspended')audio.resume().catch(()=>{});gain*=Math.max(0,Math.min(1,settings.volume));const t=audio.currentTime,o=audio.createOscillator(),v=audio.createGain();o.type=type;o.frequency.value=freq;v.gain.setValueAtTime(gain,t);v.gain.exponentialRampToValueAtTime(.001,t+seconds);o.connect(v).connect(audio.destination);o.start(t);o.stop(t+seconds);}
let tuneTimer=null,tuneIndex=0;const melody=[392,493.88,587.33,659.26,587.33,493.88,392,293.66,349.23,440,523.25,587.33,523.25,440,349.23,261.63,392,0,523.25,659.26,783.99,659.26,523.25,440,392,0,293.66,349.23,392,440,392,349.23];
function toggleMusic(){music=!music;$('audioState').textContent=music?'ON':'OFF';if(music){audio??=new (window.AudioContext||window.webkitAudioContext)();audio.resume();tuneTimer=setInterval(()=>{const n=melody[tuneIndex++%melody.length];if(n)beep(n,.23,'triangle',.016,'music');if(tuneIndex%4===0)beep(n/2||196,.3,'sine',.01,'music');},280);}else{clearInterval(tuneTimer);}}
$('audioBtn').addEventListener('click',toggleMusic);
const settingsModal=$('settingsModal');function openSettings(){settingsModal.classList.remove('hidden');resetKeys();}function closeSettings(){settingsModal.classList.add('hidden');}
$('settingsBtn').addEventListener('click',openSettings);$('settingsClose').addEventListener('click',closeSettings);settingsModal.addEventListener('click',e=>{if(e.target===settingsModal)closeSettings();});
for(const field of settingsModal.querySelectorAll('[data-setting]')){const key=field.dataset.setting;if(field.type==='checkbox')field.checked=!!settings[key];else field.value=settings[key];field.addEventListener('input',()=>{settings[key]=field.type==='checkbox'?field.checked:key==='mode'?field.value:Number(field.value);engine3d?.settings(settings);if(engine3d){engine3d.canvas.style.display=settings.mode==='2d'?'none':'block';canvas.style.visibility=settings.mode==='2d'?'visible':'hidden';}try{localStorage.setItem('signal199x-v3-settings',JSON.stringify(settings));}catch{}$('volumeReadout').textContent=Math.round(settings.volume*100)+'%';$('distanceReadout').textContent=settings.distance+' tiles';});}
$('volumeReadout').textContent=Math.round(settings.volume*100)+'%';$('distanceReadout').textContent=settings.distance+' tiles';
$('fullscreenBtn').addEventListener('click',()=>{$('stage').requestFullscreen?.();});
$('settingsMusicBtn').addEventListener('click',()=>toggleMusic());
async function init(){if(window.matchMedia('(max-width:620px)').matches)document.querySelector('.stage-col').appendChild($('chatPanel'));try{const res=await fetch('api/world');if(!res.ok)throw Error('world not found');world=await res.json();overworld=world;for(const [index,phrase] of world.quickChat.entries()){const o=document.createElement('option');o.value=String(index);o.textContent=phrase;$('quickChat').appendChild(o);}if(world.textChat){$('quickChat').classList.add('hidden');$('chatInput').classList.remove('hidden');}world.treeCells=new Set(world.trees.map(t=>t.x+','+t.y));cam.x=world.start.x*T-W/2;cam.y=world.start.y*T-H/2;visual={x:world.start.x,y:world.start.y};const resp=await fetch('api/me');const session=await resp.json();if(session.player)connect();else visual={x:world.start.x,y:world.start.y};renderPanel();}catch(e){console.error(e);$('authError').textContent='Could not load the world. Start the Node server to play.';}
 requestAnimationFrame(drawWorld);requestAnimationFrame(predict);setInterval(sendInput,80);$('year').textContent=new Date().getFullYear();}
init();

// Signal Memory Jam and Pixel Fishing: visual skill/memory game, reward decided only by server.
const PAD_COLORS=['#ff8fb1','#81f0e2','#ffdd83','#ad9cfc'];
let miniTimers=[];
function startMini(j){miniChallenge=j;miniInput=[];miniReady=false;resetKeys();$('minigameModal').classList.remove('hidden');$('minigameTitle').textContent=j.game==='fish'?'PIXEL FISHING':'MEMORY JAM';$('minigameInstructions').textContent=j.game==='fish'?'Watch the bobber colors. Repeat the sequence to reel in your catch.':'Watch the glowing notes. Play them back in the same order.';$('miniDisplay').textContent='WATCH CLOSELY';$('miniProgress').textContent='LISTENING...';for(const b of document.querySelectorAll('[data-pad]'))b.disabled=true;
 j.sequence.forEach((note,i)=>{miniTimers.push(setTimeout(()=>{for(const b of document.querySelectorAll('[data-pad]'))b.classList.remove('lit');const pad=document.querySelector(`[data-pad="${note}"]`);pad.classList.add('lit');$('miniDisplay').textContent=['ROSE','MINT','GOLD','VIOLET'][note];beep([440,523,659,784][note],.2,'triangle',.03);},1000+i*760));miniTimers.push(setTimeout(()=>{document.querySelector(`[data-pad="${note}"]`)?.classList.remove('lit');},1480+i*760));});
 miniTimers.push(setTimeout(()=>{miniReady=true;$('miniDisplay').textContent='YOUR TURN!';$('miniProgress').textContent=`0 / ${j.sequence.length} notes`;for(const b of document.querySelectorAll('[data-pad]'))b.disabled=false;},1150+j.sequence.length*760));
}
function closeMini(){for(const timer of miniTimers)clearTimeout(timer);miniTimers=[];miniChallenge=null;miniReady=false;$('minigameModal').classList.add('hidden');}
$('minigameClose').addEventListener('click',closeMini);
for(const b of document.querySelectorAll('[data-pad]'))b.addEventListener('click',()=>{if(!miniReady||!miniChallenge)return;const val=Number(b.dataset.pad);miniInput.push(val);b.classList.add('lit');setTimeout(()=>b.classList.remove('lit'),180);beep([440,523,659,784][val],.13,'sine',.03);$('miniProgress').textContent=`${miniInput.length} / ${miniChallenge.sequence.length} notes`;
 if(miniInput.length===miniChallenge.sequence.length){actionExtra('minigame-finish',{id:miniChallenge.challengeId,sequence:miniInput});const won=miniInput.every((v,i)=>v===miniChallenge.sequence[i]);$('miniDisplay').textContent=won?'NICE RHYTHM!':'OOPS! TRY AGAIN';miniReady=false;for(const pad of document.querySelectorAll('[data-pad]'))pad.disabled=true;setTimeout(closeMini,1000);}});
