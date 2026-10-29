import test from 'node:test';
import assert from 'node:assert/strict';
import {SOUNDS,GraveAudio,weaponSound} from '../src/audio.js';
class FakeAudio {
  constructor(path=''){this.src=path;this.paused=true;this.ended=false;this.volume=0;this.currentTime=0;this.loop=false;}
  cloneNode(){return new FakeAudio(this.src);}
  play(){this.paused=false;return Promise.resolve();}
  pause(){this.paused=true;}
}
const originalAudio=globalThis.Audio;
globalThis.Audio=FakeAudio;
test.after(()=>{globalThis.Audio=originalAudio});
test('all named cues have matching OGG files',async()=>{
 const {existsSync}=await import('node:fs');
 for(const s of Object.keys(SOUNDS))assert.ok(existsSync(new URL(`../public/assets/audio/${s}.ogg`,import.meta.url)),s);
 for(const m of ['nightfall_menu','nightfall_battle'])assert.ok(existsSync(new URL(`../public/assets/audio/${m}.ogg`,import.meta.url)),m);
});
test('ambient volume honors music and music mute',()=>{
 const settings={music:.25,sfx:.6};const a=new GraveAudio(settings);
 a.setMode('menu',true);a.unlock();assert.ok(a.current.volume>0);settings.music=0;a.syncVolumes();assert.equal(a.current.volume,0);assert.equal(a.current.paused,true);
 settings.music=.5;a.setMode('battle');assert.equal(a.mode,'battle');assert.ok(a.current.volume>0);
 a.setPaused(true);assert.equal(a.current.paused,true);a.dispose();
});
test('weapons map to distinct sonic categories',()=>{
 assert.equal(weaponSound('crossbow'),'bow');assert.equal(weaponSound('wyrmfire'),'flame');assert.equal(weaponSound('scythe'),'swing');assert.equal(weaponSound('quakes'),'quake');assert.equal(weaponSound('hexbolt'),'magic');
});
test('attack sound cooldown and simultaneous voice cap prevent audio spam',()=>{
 const a=new GraveAudio({music:.3,sfx:.9});a.unlock();
 assert.equal(a.play('bow'),true);assert.equal(a.play('bow'),false);assert.equal(a.play('swing'),false);
 for(let i=0;i<40;i++)a.weapon(['scythe','crossbow','wyrmfire'][i%3]);
 assert.ok(a.voices.length<=4);
 a.dispose();
});
test('mute disables effects and no audio plays until gesture',()=>{
 const a=new GraveAudio({music:.1,sfx:0});assert.equal(a.play('levelup'),false);a.unlock();assert.equal(a.play('levelup'),false);a.dispose();
});
