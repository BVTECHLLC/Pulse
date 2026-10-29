import {accountLevel,metaPrice,ACHIEVEMENTS,CHARACTERS,SKINS,MAPS,MUTATORS,META,RELICS} from './data.js';
const KEY='bvtech.graveyard-shift.reanimated.profile.v1';
export const initialProfile=()=>({version:1,coins:0,souls:0,totalXP:0,selected:'warden',skin:'default',map:'cemetery',mutator:'standard',selectedRelic:'nightfall',upgrades:{},achievements:[],stats:{runs:0,bestKills:0,bestTime:0,defeated:0,wins:0},settings:{music:.25,sfx:.6,graphics:.5,shadows:true,particles:true,shake:true,damageNumbers:true},lastPlayed:null});
export function loadProfile(){
 try {const p=JSON.parse(localStorage.getItem(KEY));if(p?.version===1)return sanitizeImportedSave(p);}catch{}return initialProfile();
}
export let profile=loadProfile();
export function saveProfile(){try{localStorage.setItem(KEY,JSON.stringify(profile));}catch(e){console.warn('Browser save unavailable for this session',e);}}
export function updateProfile(fn){fn(profile);saveProfile();window.dispatchEvent(new CustomEvent('gs:profile'));}
export function buyUpgrade(up){const rank=profile.upgrades[up.id]||0,cost=metaPrice(up,rank);if(rank>=up.max||profile.coins<cost)return false;updateProfile(p=>{p.coins-=cost;p.upgrades[up.id]=rank+1;});return true;}
export function applyResult(run){
 const unlocked=[];
 updateProfile(p=>{
  const power=(p.upgrades.luck||0)*.03;
  p.coins+=Math.floor(run.coins*(1+power));p.souls+=Math.floor(run.souls*(1+power));p.totalXP+=run.earnedXP;
  p.stats.runs++;p.stats.defeated+=run.kills;p.stats.bestKills=Math.max(p.stats.bestKills,run.kills);p.stats.bestTime=Math.max(p.stats.bestTime,run.time);if(run.victory)p.stats.wins++;
  p.lastPlayed=new Date().toISOString();
  const events={first:run.kills>0,hundred:run.kills>=100,fivehundred:run.kills>=500,minutes:run.time>=300,boss:run.bossKills>0,victory:run.victory,evolved:run.evolutions>0,collector:accountLevel(p.totalXP)>=10};
  for(const a of ACHIEVEMENTS){if(events[a.id]&&!p.achievements.includes(a.id)){p.achievements.push(a.id);p.coins+=a.reward;unlocked.push(a);}}
 });return unlocked;
}
// Optional authenticated bridge. The server must verify run results before crediting rewards.
// This prototype never uploads passwords, and never deletes the player's local progress.
export async function fetchServerProfile(){
 try {const r=await fetch('/api/graveyard-shift/v1/me',{credentials:'include',signal:AbortSignal.timeout(2500)});if(!r.ok)return null;const data=await r.json();return data?.profile||null;}catch{return null;}
}

// Sanitize imported guest-save data; never trust it as a Linode reward or ranked score.
export function sanitizeImportedSave(raw){
 if(!raw||raw.version!==1||!Number.isFinite(raw.totalXP)||!Number.isFinite(raw.coins))throw Error('Invalid save file');
 const base=initialProfile();
 const num=(n,max=100000000)=>Number.isFinite(n)?Math.max(0,Math.min(max,Math.floor(n))):0;
 base.coins=num(raw.coins);base.souls=num(raw.souls);base.totalXP=num(raw.totalXP);
 if(CHARACTERS.some(c=>c.id===raw.selected))base.selected=raw.selected;
 if(SKINS.some(c=>c.id===raw.skin))base.skin=raw.skin;
 if(MAPS.some(c=>c.id===raw.map))base.map=raw.map;
 if(MUTATORS.some(c=>c.id===raw.mutator))base.mutator=raw.mutator;
 if(RELICS.some(c=>c.id===raw.selectedRelic))base.selectedRelic=raw.selectedRelic;
 if(raw.upgrades&&typeof raw.upgrades==='object'&&!Array.isArray(raw.upgrades)){for(const m of META)base.upgrades[m.id]=num(raw.upgrades[m.id],m.max);}
 if(Array.isArray(raw.achievements))base.achievements=ACHIEVEMENTS.filter(a=>raw.achievements.includes(a.id)).map(a=>a.id);
 if(raw.stats&&typeof raw.stats==='object'){for(const k of Object.keys(base.stats))base.stats[k]=num(raw.stats[k]);}
 if(raw.settings&&typeof raw.settings==='object')for(const k of Object.keys(base.settings)){const prior=base.settings[k];if(typeof prior==='boolean'){if(typeof raw.settings[k]==='boolean')base.settings[k]=raw.settings[k];}else if(Number.isFinite(raw.settings[k]))base.settings[k]=Math.max(0,Math.min(1,raw.settings[k]));}
 return base;
}
