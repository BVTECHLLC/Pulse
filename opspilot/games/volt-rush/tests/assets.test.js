import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,statSync,existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const art=(...a)=>path.join(root,'public','art',...a);
const drivers=['nova','jax','ivy','bolt','echo','rook'];
const regions=['coast','forest','neon','candy','moon','volcano'];
function glbJSON(filepath){
  const b=readFileSync(filepath);
  assert.equal(b.toString('ascii',0,4),'glTF');
  assert.equal(b.readUInt32LE(4),2);
  assert.equal(b.readUInt32LE(8),b.length,'Declared length agrees with file');
  const jsonSize=b.readUInt32LE(12);
  assert.equal(b.toString('ascii',16,20),'JSON');
  return JSON.parse(b.subarray(20,20+jsonSize).toString('utf8'));
}
test('all six 3D hero mascots are genuine nonempty GLBs at desktop and mobile detail',()=>{
  for(const name of drivers){
    const desktop=art('models',`${name}-desktop.glb`),mobile=art('models',`${name}-mobile.glb`);
    assert.ok(existsSync(desktop)&&existsSync(mobile),name);
    assert.ok(statSync(desktop).size>45000,`${name} high model not empty`);
    assert.ok(statSync(mobile).size<statSync(desktop).size,`${name} mobile LOD must be smaller`);
    for(const filepath of [desktop,mobile]){
      const parsed=glbJSON(filepath);
      const names=new Set(parsed.materials.map(x=>x.name));
      assert.ok(names.has('Paint'),'Player-selectable kart finish material');
      assert.ok(names.has('Skin')&&names.has('EyeWhite'),'Original 3D character face');
      assert.ok(parsed.nodes.some(x=>x.name==='Wheel_LF'),'Independently animated wheels');
      assert.ok(parsed.meshes.length>=23,'Detailed kart + mascot mesh groups');
    }
  }
});
test('all six racing surfaces have smaller phone WebPs and matching track cover art',()=>{
  for(const name of regions){
    const high=art('textures',`${name}-road-desktop.webp`),low=art('textures',`${name}-road-mobile.webp`);
    for(const f of [high,low,art('tracks',`${name}.webp`)]){
      assert.ok(existsSync(f),f);const b=readFileSync(f);
      assert.equal(b.toString('ascii',0,4),'RIFF');assert.equal(b.toString('ascii',8,12),'WEBP');
    }
    assert.ok(statSync(low).size<statSync(high).size,`${name} mobile texture budget`);
  }
});
test('six original portrait images and route-specific art remain part of the shipping public bundle',()=>{
  for(const name of drivers)assert.ok(statSync(art('portraits',`${name}.webp`)).size>2000);
  const source=readFileSync(path.join(root,'src','main.js'),'utf8');
  assert.match(source,/preloadHeroAssets\(\)/);
  assert.match(source,/installHeroModel\(/);
  assert.match(source,/art\/portraits/);
  assert.match(source,/art\/tracks/);
  const world=readFileSync(path.join(root,'src','game','world.js'),'utf8');
  assert.match(world,/art\/textures/);
  assert.match(world,/InstancedMesh/);
});
test('mobile graphics preserve cross-platform shared physics and dedicated /kart/ socket',()=>{
  const source=readFileSync(path.join(root,'src','main.js'),'utf8');
  const hero=readFileSync(path.join(root,'src','game','hero-assets.js'),'utf8');
  assert.match(source,/\/kart\/ws/);
  assert.match(source,/interpolateSnapshot\(/);
  assert.match(source,/defaultPixelRatio=mobileProfile\?1\.25/);
  assert.match(hero,/three\/addons\/loaders\/GLTFLoader/);
  assert.match(hero,/import\.meta\.env\.BASE_URL/);
});
