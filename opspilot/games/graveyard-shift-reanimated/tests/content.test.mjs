import test from 'node:test';import assert from 'node:assert/strict';
import {CHARACTERS,SKINS,MAPS,MUTATORS,WEAPONS,PASSIVES,EVOLUTIONS,META,accountLevel,levelRequired,metaPrice} from '../src/data.js';
test('content minimums and no duplicate IDs',()=>{
 for(const [name,list,min] of [['characters',CHARACTERS,10],['skins',SKINS,8],['maps',MAPS,3],['weapons',WEAPONS,14],['passives',PASSIVES,12],['evolutions',EVOLUTIONS,8],['mutators',MUTATORS,4]]){
  assert.ok(list.length>=min,`${name}: expected at least ${min}`);assert.equal(new Set(list.map(x=>x.id||x.weapon)).size,list.length,`${name}: duplicate IDs`);
 }
});
test('every class starts with a defined weapon',()=>{for(const c of CHARACTERS)assert.ok(WEAPONS.some(w=>w.id===c.weapon),c.name);});
test('every evolution uses a real weapon and passive',()=>{for(const e of EVOLUTIONS){assert.ok(WEAPONS.some(w=>w.id===e.weapon));assert.ok(PASSIVES.some(p=>p.id===e.passive));}});
test('level thresholds and coin costs grow monotonically',()=>{for(let i=2;i<50;i++)assert.ok(levelRequired(i)>levelRequired(i-1));for(const m of META)for(let n=1;n<m.max;n++)assert.ok(metaPrice(m,n)>metaPrice(m,n-1));});
test('account levels are monotonic',()=>{let last=0;for(let xp=0;xp<25000;xp+=49){const level=accountLevel(xp);assert.ok(level>=last);last=level;}});
test('every map has a unique ID and positive unlock',()=>{assert.equal(new Set(MAPS.map(x=>x.id)).size,MAPS.length);assert.ok(MAPS.every(x=>x.unlock>=0));});

import {sanitizeImportedSave} from '../src/profile.js';
test('imported guest saves cannot introduce executable strings or invalid upgrades',()=>{
 const raw={version:1,totalXP:2000,coins:200,selected:'<img src=x onerror=alert(1)>',skin:'void',stats:{runs:'evil',bestKills:4},settings:{sfx:9999,shadows:'notbool'},upgrades:{power:99999,exploit:999},achievements:['first','impossible']};
 const clean=sanitizeImportedSave(raw);assert.equal(clean.selected,'warden');assert.equal(clean.upgrades.power,META.find(m=>m.id==='power').max);assert.ok(!('exploit' in clean.upgrades));assert.equal(clean.stats.runs,0);assert.equal(clean.settings.sfx,1);assert.equal(clean.settings.shadows,true);assert.deepEqual(clean.achievements,['first']);
});
test('reject malformed save files',()=>{assert.throws(()=>sanitizeImportedSave({version:1,coins:'99999',totalXP:0}));});
