/* GRAVEYARD SHIFT NIGHTFALL V3 — event-driven, volume-aware original soundtrack/SFX.
 * One soundtrack at a time, at most four effect voices, coalesced auto-fire effects.
 * Starts only after the first user's gesture to respect autoplay policies.
 */
export const SOUNDS = Object.freeze({
 ui_select: [0.045,100],levelup:[0.24,100],evolve:[0.31,100],chest_spawn:[0.19,1400],
 chest_open:[0.32,250],boss_warning:[0.30,2500],boss_defeat:[0.3,900],blood_moon:[0.28,4000],
 hit:[0.24,420],dash:[0.14,400],spell:[0.24,500],swing:[0.068,580],
 bow:[0.11,450],magic:[0.09,620],flame:[0.09,750],quake:[0.11,740],
 pickup:[0.05,1000],altar:[0.23,600],victory:[0.34,2500],defeat:[0.28,2500],
 jump:[0.07,420],rush_end:[0.16,2500]
});
export function weaponSound(id){
 if(['sunbow','widow','crossbow','shrapnel'].includes(id))return 'bow';
 if(['wyrmfire','ember'].includes(id))return 'flame';
 if(['scythe','chakram','boneblades','thorn','blood'].includes(id))return 'swing';
 if(['meteor','quakes','fuse','mines'].includes(id))return 'quake';
 return 'magic';
}
export class GraveAudio {
 constructor(settings,base='/assets/audio/'){
  this.settings=settings;this.base=base;this.unlocked=false;this.mode='menu';this.paused=false;
  this.current=null;this.tracks={};this.samples={};this.last=new Map();this.voices=[];
  this.attackAt=-1e10;this.eventTimes=[];
 }
 unlock(){
  if(this.unlocked)return;this.unlocked=true;
  this.setMode(this.mode,true);
 }
 getTrack(mode){
  if(!this.tracks[mode]){
   const el=new Audio(`${this.base}${mode==='battle'?'nightfall_battle':'nightfall_menu'}.ogg`);
   el.loop=true;el.preload='auto';el.volume=0;this.tracks[mode]=el;
  }
  return this.tracks[mode];
 }
 syncVolumes(){
  for(const [name,track] of Object.entries(this.tracks))track.volume=this.paused||name!==this.mode?0:Math.min(1,(Number(this.settings.music)||0)*.48);
  if((Number(this.settings.music)||0)<=0)this.current?.pause();
  else if(this.unlocked&&!this.paused)this.current?.play().catch(()=>{});
  // Existing SFX are deliberately not amplified if the user moves the slider upward.
 }
 setMode(mode,force=false){
  if(!['menu','battle'].includes(mode))return;
  if(this.mode===mode&&!force){this.syncVolumes();return;}
  if(this.current){this.current.pause();this.current.currentTime=0;}
  this.mode=mode;this.current=this.getTrack(mode);this.syncVolumes();
 }
 setPaused(state){this.paused=!!state;if(this.paused)this.current?.pause();this.syncVolumes();}
 play(name,{important=false,vol=1}={}){
  if(!this.unlocked||(Number(this.settings.sfx)||0)<=0||!SOUNDS[name])return false;
  const now=performance.now(),[defaultGain,delay]=SOUNDS[name];
  if(now-(this.last.get(name)||-1e10)<delay)return false;
  // Treat every shot as one group even when multiple weapons fire every frame.
  if(['swing','bow','magic','flame','quake'].includes(name)){
   if(now-this.attackAt<520)return false;this.attackAt=now;
  }
  this.eventTimes=this.eventTimes.filter(ts=>now-ts<1000);
  if(!important&&this.eventTimes.length>=5)return false;
  this.voices=this.voices.filter(voice=>!voice.paused&&!voice.ended);
  if(this.voices.length>=4){if(!important)return false;const old=this.voices.shift();old.pause();}
  this.last.set(name,now);this.eventTimes.push(now);
  let sample=this.samples[name];if(!sample){sample=new Audio(`${this.base}${name}.ogg`);sample.preload='auto';this.samples[name]=sample;}
  // Clone cached metadata so rare overlapping important cues can still play.
  const voice=sample.cloneNode();voice.volume=Math.min(.5,defaultGain*Math.max(0,Math.min(1,Number(this.settings.sfx)||0))*vol);
  this.voices.push(voice);voice.play().catch(()=>{});
  return true;
 }
 weapon(id){this.play(weaponSound(id));}
 dispose(){this.current?.pause();for(const t of Object.values(this.tracks))t.pause();for(const v of this.voices)v.pause();this.voices=[];}
}
