/** Presentation-only interpolation of complete server snapshots.
 * Never call stepKart on publicKart: authoritative snapshots intentionally omit internal
 * fields such as steerInput and lastS, causing NaN positions and a frozen chase camera.
 */
import {clamp,normalizeAngle} from './sim.js';
export function interpolateSnapshot(current,target,blend){
  if(!current||!target)return target?{...target}:null;
  const f=clamp(Number(blend)||0,0,1);
  if(!Number.isFinite(target.x)||!Number.isFinite(target.z)||!Number.isFinite(target.heading))return {...current};
  if(!Number.isFinite(current.x)||!Number.isFinite(current.z)||!Number.isFinite(current.heading))return {...target};
  const out={...target};
  for(const field of ['x','z'])out[field]=current[field]+(target[field]-current[field])*f;
  out.heading=current.heading+normalizeAngle(target.heading-current.heading)*f;
  return out;
}
