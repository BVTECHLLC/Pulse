import test from 'node:test';
import assert from 'node:assert/strict';
import {Terrain} from '../src/terrain.js';
import {WEAPONS,RELICS,CHARACTERS,EVOLUTIONS} from '../src/data.js';
test('V3 full combat catalog has unique weapon, relic and class identities',()=>{
 for(const pack of [WEAPONS,RELICS,CHARACTERS]) assert.equal(new Set(pack.map(o=>o.id)).size,pack.length);
 assert.ok(WEAPONS.length>=26);assert.ok(RELICS.length>=12);assert.ok(CHARACTERS.length>=16);assert.ok(EVOLUTIONS.length>=20);
});
test('solid trees prevent movement through trunks',()=>{
 const t=new Terrain();t.addCircle(3,0,1,4);
 const p=t.resolve(2.5,0,0,.4);assert.ok(Math.hypot(p.x-3,p.z)>=1.39);
 assert.ok(t.blocked(3,0));assert.ok(!t.blocked(0,0));
});
test('solid ruins prevent movement through walls',()=>{
 const t=new Terrain();t.addBox(10,2,2,3,2);
 const p=t.resolve(10.2,2,0,.42);assert.ok(!t.blocked(p.x,p.z,0,.38));
 assert.ok(t.blocked(10,2,0));assert.equal(t.blocked(10,2,3),false);
});
test('stairs slope, and a high platform cannot be entered from ground level',()=>{
 const t=new Terrain();t.addBox(12,0,3,3,1.6);t.addPlatform(12,0,3,3,1.74);t.addRamp(3,0,2.6,6,1.74,'x',1);
 assert.equal(t.groundHeight(3,0),0);
 assert.ok(t.groundHeight(6,0,0)>.6);
 assert.ok(t.groundHeight(9,0,1.7)>1.6);
 assert.equal(t.blocked(12,0,0),true);
 assert.equal(t.blocked(12,0,1.9),false);
});
test('jumpable rocks are walkable only when feet are high enough',()=>{
 const t=new Terrain();t.addCircle(-5,3,1.1,.8);t.addPerch(-5,3,.8,.8);
 assert.equal(t.groundHeight(-5,3,0),0);
 assert.equal(t.groundHeight(-5,3,.5),.8);
});
test('spawn points are kept out of colliders',()=>{
 const t=new Terrain();for(let i=-10;i<10;i++)t.addCircle(i*1.7,0,.55,2);
 const pt=t.findFree(0,0,0,.4);assert.equal(t.blocked(pt.x,pt.z,0,.4),false);
});
