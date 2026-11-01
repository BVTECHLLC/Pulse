/** Original GLB kart/mascot assets. Shared geometries, per-player paint, mobile LOD. */
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {RACERS,KART_COLORS} from '../shared/sim.js';

const cache=new Map();
let inFlight=null;
const modelTier=()=>{
  const touch=typeof matchMedia==='function'&&matchMedia('(pointer:coarse)').matches;
  return (touch||(typeof navigator!=='undefined'&&navigator.deviceMemory&&navigator.deviceMemory<=4))?'mobile':'desktop';
};
const base=()=>import.meta.env.BASE_URL || '/kart/';
const loader=new GLTFLoader();

export function preloadHeroAssets(){
  if(inFlight)return inFlight;
  const tier=modelTier();
  inFlight=Promise.allSettled(RACERS.map(async r=>{
    const gltf=await loader.loadAsync(`${base()}art/models/${r.id}-${tier}.glb`);
    const scene=gltf.scene;
    scene.traverse(o=>{if(o.isMesh){
      if(o.geometry)o.geometry.userData.voltShared=true;
      const materials=Array.isArray(o.material)?o.material:[o.material];
      for(const mat of materials)if(mat)mat.userData.voltShared=true;
      o.frustumCulled=true;
    }});
    cache.set(r.id,scene);
    return r.id;
  })).then(results=>({ready:results.filter(x=>x.status==='fulfilled').length,failed:results.filter(x=>x.status==='rejected').length}));
  return inFlight;
}

export function installHeroModel(kartVisual,kart){
  const id=RACERS[kart.avatar]?.id;
  if(!id||!cache.has(id)||kartVisual.userData.hero)return false;
  const root=kartVisual.userData.root,source=cache.get(id);
  const hero=source.clone(true);
  const heroWheels=[];
  const paint=new THREE.Color(KART_COLORS[kart.color]||KART_COLORS[0]);
  hero.traverse(o=>{
    if(!o.isMesh)return;
    if(o.material?.name==='Paint'){
      o.material=o.material.clone();o.material.userData.voltShared=false;
      o.material.color.copy(paint);o.material.roughness=.27;
    }
    if(/^(Wheel|Rim|Hub)_/.test(o.name))heroWheels.push(o);
    o.castShadow=false; // Eight moving karts cast no dynamic shadow on battery-constrained Safari.
  });
  const {shield,shieldBand,flames}=kartVisual.userData;
  const keep=new Set([shield,shieldBand,...flames]);
  for(const child of root.children)if(!keep.has(child))child.visible=false;
  hero.name='Original3DHero';root.add(hero);
  kartVisual.userData.hero=hero;kartVisual.userData.heroWheels=heroWheels;
  return true;
}
export function hasHeroAsset(avatar){return cache.has(RACERS[avatar]?.id);}
