// Deterministic, side-effect-free balancing rules. Independent of Three.js so they can be tested on CI.
export const BUDGETS = Object.freeze({
  low: Object.freeze({enemies:95, projectiles:65, pickups:70, effects:24, dpr:1.0, trees:8}),
  medium: Object.freeze({enemies:145, projectiles:90, pickups:90, effects:36, dpr:1.35, trees:12}),
  high: Object.freeze({enemies:185, projectiles:120, pickups:110, effects:48, dpr:1.6, trees:17})
});
export function graphicsPreset(value){return value>=.8?'high':value<=.25?'low':'medium';}
export function enemyScale(index,boss=false){return boss?1.0:[.94,.72,1.26,.94,1.08,.95][index]??1;}
export function enemyRadius(index,boss=false){return boss?1.3:[.46,.39,.69,.43,.54,.47][index]??.48;}
export function spawnPlan(seconds,spawnModifier=1,rush=false){
 const stage=Math.max(0,Math.floor(seconds/75));
 const interval=Math.max(.33,.98-stage*.07);
 const count=Math.max(1,Math.min(7,Math.round((2+Math.floor(seconds/105)) * Math.max(.7,Math.min(1.8,spawnModifier)) * (rush?1.5:1))));
 return {interval,count};
}
export function comboMultiplier(streak){return Math.min(2.25,1+Math.max(0,streak-1)*.035);}
export function safeDelta(dt){return Math.max(0,Math.min(.043,Number.isFinite(dt)?dt:0));}
export function capAvailable(current,limit){return Math.max(0,limit-current);}
