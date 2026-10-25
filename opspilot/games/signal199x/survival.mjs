// Signal 199X: ORIGINAL private auto-attack survival challenge.
// Challenge starts and ends on the trusted server. The browser supplies inputs only.
import {riftSafe} from './dungeons.mjs';
export const SURVIVAL_LOCATION={x:105.5,y:26.5};
export const SURVIVAL_LENGTH_MS=90000;
export function createSurvival(id,playerId){const width=34,height=34;const tiles=Array.from({length:height},(_,z)=>Array.from({length:width},(_,x)=>x<2||z<2||x>width-3||z>height-3?4:((x+z)%8===0?6:5)));
 const scene={width,height,tile:32,tiles,trees:[],houses:[],npcs:[],chests:[],signalNodes:[],places:[{name:'THE STATIC STORM',sub:'Survive the transmission',x:17,y:17,r:60}],start:{x:17.5,y:17.5},sceneType:'survival'};
 return {id,kind:'survival',scene,enemies:[],members:new Set([playerId]),createdAt:Date.now(),wave:0,kills:0,autoAt:0,nextWaveAt:0,completed:false};}
export function spawnSurvivalWave(instance){const wave=++instance.wave,amount=Math.min(18,3+wave*2),time=Date.now();for(let i=0;i<amount;i++){const a=i/amount*Math.PI*2,r=8+(i%3)*1.5,x=17.5+Math.cos(a)*r,y=17.5+Math.sin(a)*r;instance.enemies.push({id:`${instance.id}:s${wave}-${i}`,kind:'riftling',x,y,ox:x,oy:y,level:1+wave,maxHp:Math.min(130,20+wave*12),hp:Math.min(130,20+wave*12),attack:Math.min(13,3+wave),alive:true,respawnAt:Infinity,lastAttack:time,dir:0,roamUntil:0,contributors:new Map(),boss:false});}instance.nextWaveAt=time+1000;}
