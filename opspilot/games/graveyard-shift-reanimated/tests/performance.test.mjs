import test from 'node:test';import assert from 'node:assert/strict';
import {BUDGETS,enemyScale,enemyRadius,spawnPlan,safeDelta,comboMultiplier,graphicsPreset} from '../src/balance.js';
test('enemy and boss scale never explode',()=>{for(let i=0;i<6;i++){assert.ok(enemyScale(i)<1.4);assert.ok(enemyRadius(i)<1)}assert.equal(enemyScale(2,true),1);assert.ok(enemyRadius(2,true)<1.5);});
test('spawn plan stays finite and controlled even after 3 hours',()=>{for(const t of [0,90,360,720,9999])for(const modifier of [1,1.6,100]){const p=spawnPlan(t,modifier,true);assert.ok(p.interval>=.2);assert.ok(p.count<=16&&p.count>=1)}});
test('GPU budgets remain bounded',()=>{for(const b of Object.values(BUDGETS)){assert.ok(b.enemies<=480);assert.ok(b.projectiles<=200);assert.ok(b.effects<=64);assert.ok(b.dpr<=1.8);}});
test('frame clamp and combo are bounded',()=>{assert.equal(safeDelta(3),.043);assert.equal(safeDelta(Infinity),0);assert.ok(comboMultiplier(500)<=2.25);assert.equal(graphicsPreset(0),'low');});

test('all selectable relics have unique ids and bounded cooldowns',async()=>{const {RELICS}=await import('../src/data.js');assert.ok(RELICS.length>=12);assert.equal(new Set(RELICS.map(r=>r.id)).size,RELICS.length);assert.ok(RELICS.every(r=>r.cooldown>=15&&r.cooldown<=40));});
