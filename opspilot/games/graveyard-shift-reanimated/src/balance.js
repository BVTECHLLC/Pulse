// Deterministic, side-effect-free balancing rules. Independent of Three.js so they can be tested on CI.
// V11: true horde scale — instanced enemies make big counts cheap, and the
// engine's FPS-adaptive cap scales back automatically on weaker devices.
export const BUDGETS = Object.freeze({
  low: Object.freeze({enemies:170, projectiles:90, pickups:110, effects:30, dpr:1.0, trees:8}),
  medium: Object.freeze({enemies:300, projectiles:140, pickups:150, effects:44, dpr:1.4, trees:12}),
  high: Object.freeze({enemies:460, projectiles:190, pickups:190, effects:60, dpr:1.75, trees:17})
});
export function graphicsPreset(value){return value>=.8?'high':value<=.25?'low':'medium';}
export function enemyScale(index,boss=false){return boss?1.0:[.94,.72,1.26,.94,1.08,.95][index]??1;}
export function enemyRadius(index,boss=false){return boss?1.3:[.46,.39,.69,.43,.54,.47][index]??.48;}
export function spawnPlan(seconds,spawnModifier=1,rush=false){
 // V11: faster, denser waves — the screen should fill with a real horde.
 const stage=Math.max(0,Math.floor(seconds/60));
 const interval=Math.max(.2,.88-stage*.07);
 const count=Math.max(2,Math.min(16,Math.round((3+Math.floor(seconds/70)) * Math.max(.7,Math.min(1.8,spawnModifier)) * (rush?1.7:1))));
 return {interval,count};
}
export function comboMultiplier(streak){return Math.min(2.25,1+Math.max(0,streak-1)*.035);}
export function safeDelta(dt){return Math.max(0,Math.min(.043,Number.isFinite(dt)?dt:0));}
export function capAvailable(current,limit){return Math.max(0,limit-current);}
