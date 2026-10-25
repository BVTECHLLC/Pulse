// Three co-op rift arenas. Every mob and reward stays authoritative on Node.
export const RIFTS=[
 {id:'rain',name:'RAINY RADIO TOWER',subtitle:'A singing storm of tangled antennas',level:2,color:'#79d7ff',boss:'The Feedback King'},
 {id:'arcade',name:'PHANTOM ARCADE',subtitle:'Defeat glitches inside an abandoned cabinet',level:5,color:'#ffa2f0',boss:'The Arcade Overlord'},
 {id:'moon',name:'MIDNIGHT MOONSTATION',subtitle:'A strange broadcast from far beyond home',level:9,color:'#c2aaff',boss:'The Lost Transmission'}
];
export const GATE={x:54.5,y:33.5};
export const ARENA={x1:104,x2:117,y1:41,y2:55};
export const HOME_AGENT={x:107.5,y:73.5};
export const ARCADE={x:104.5,y:26.5};
export const FISHING={x:81.5,y:57.5};
export const BEACON={x:53.5,y:33.5};
export function makeRiftMap(id){const width=44,height=28;
 const tiles=Array.from({length:height},(_,y)=>Array.from({length:width},(_,x)=>x<2||y<2||x>=width-2||y>=height-2?4:(id==='moon'?5:id==='arcade'?6:1)));
 const holes=id==='moon'?[[10,10],[31,12]]:id==='arcade'?[[13,8],[28,17]]:[[12,11],[31,9]];
 for(const [cx,cy] of holes)for(let y=cy-1;y<=cy+1;y++)for(let x=cx-1;x<=cx+1;x++)tiles[y][x]=3;
 for(let y=4;y<24;y++)for(let x=4;x<40;x++)if((x+y*7)%41===0)tiles[y][x]=5;
 return {width,height,tile:32,tiles,trees:[],houses:[],npcs:[],chests:[],places:[{name:RIFTS.find(r=>r.id===id)?.name||'RIFT',sub:'An expedition beyond the airwaves',x:22,y:14,r:100}],start:{x:5.5,y:14.5},sceneType:'dungeon'};
}
export function riftSafe(map,x,y){return x>=2&&y>=2&&x<map.width-2&&y<map.height-2&&!([3,4].includes(map.tiles[Math.floor(y)]?.[Math.floor(x)]));}
export function createRift(id,instanceId,partyIds){const scene=makeRiftMap(id);const type=RIFTS.find(r=>r.id===id)||RIFTS[0];const count=Math.max(1,partyIds.length),scale=1+Math.max(0,count-1)*.45;
 const spawns=[[11,6],[14,21],[22,10],[22,18],[31,6],[33,21],[35,13]];
 const enemies=spawns.map(([x,y],i)=>({id:`${instanceId}:m${i}`,kind:'riftling',x:x+.5,y:y+.5,ox:x+.5,oy:y+.5,level:type.level+1,maxHp:Math.round((100+type.level*15)*scale),hp:Math.round((100+type.level*15)*scale),attack:8+type.level*2,alive:true,respawnAt:0,lastAttack:0,dir:0,roamUntil:0,contributors:new Map(),boss:false}));
 const bHp=Math.round((380+type.level*60)*scale);enemies.push({id:`${instanceId}:boss`,kind:'riftboss',x:38.5,y:14.5,ox:38.5,oy:14.5,level:type.level+3,maxHp:bHp,hp:bHp,attack:16+type.level*2,alive:true,respawnAt:0,lastAttack:0,dir:0,roamUntil:0,contributors:new Map(),boss:true});
 return {id:instanceId,kind:id,scene,enemies,members:new Set(partyIds),createdAt:Date.now(),completed:false};}
