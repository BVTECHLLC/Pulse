/** Canonical controls shared by keyboard and pointer/touch UI.
 * Steer +1 = screen RIGHT, steer -1 = screen LEFT.
 */
export function steeringFromControls(keys,mobile){
  const right=!!mobile.right||keys.has('ArrowRight')||keys.has('KeyD');
  const left=!!mobile.left||keys.has('ArrowLeft')||keys.has('KeyA');
  return Number(right)-Number(left);
}
