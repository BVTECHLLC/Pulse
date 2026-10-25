import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {DatabaseSync} from 'node:sqlite';
import {world,WIDTH,HEIGHT,TILE,START,houses,npcs,places,chests,signalNodes,mobs,mobDefs,items,lootWeights,lootByRarity,shopStock} from './world.mjs';
import {QUICK_CHAT,TEXT_CHAT_ENABLED,safeUsername,moderateMessage} from './moderation.mjs';
import {RIFTS,GATE,ARENA,HOME_AGENT,ARCADE,FISHING,BEACON,createRift,riftSafe} from './dungeons.mjs';
import {SURVIVAL_LOCATION,SURVIVAL_LENGTH_MS,createSurvival,spawnSurvivalWave} from './survival.mjs';

const __dirname=path.dirname(fileURLToPath(import.meta.url));
const DATA_DIR=process.env.DATA_DIR||path.join(__dirname,'data');
const PORT=Number(process.env.PORT||3000);
const HOST=process.env.HOST||'127.0.0.1';
const IS_PROD=process.env.NODE_ENV==='production';
fs.mkdirSync(DATA_DIR,{recursive:true,mode:0o700});
const db=new DatabaseSync(path.join(DATA_DIR,'game.sqlite'));
db.exec(`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS players(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 username TEXT UNIQUE NOT NULL,
 password_hash TEXT NOT NULL,
 salt TEXT NOT NULL,
 class TEXT NOT NULL,
 palette INTEGER NOT NULL,
 level INTEGER NOT NULL DEFAULT 1,
 xp INTEGER NOT NULL DEFAULT 0,
 hp INTEGER NOT NULL DEFAULT 100,
 focus INTEGER NOT NULL DEFAULT 50,
 gold INTEGER NOT NULL DEFAULT 75,
 x REAL NOT NULL DEFAULT 24.5,
 y REAL NOT NULL DEFAULT 33.5,
 inventory TEXT NOT NULL DEFAULT '{}',
 equipped TEXT NOT NULL DEFAULT '{}',
 quest_kills INTEGER NOT NULL DEFAULT 0,
 quest_done INTEGER NOT NULL DEFAULT 0,
 boss_done INTEGER NOT NULL DEFAULT 0,
 is_demo INTEGER NOT NULL DEFAULT 0,
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,expires_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS sessions_player ON sessions(player_id);`);
db.exec(`CREATE TABLE IF NOT EXISTS homes(owner_id INTEGER PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE, plot INTEGER NOT NULL, theme TEXT NOT NULL DEFAULT 'violet', furniture TEXT NOT NULL DEFAULT 'beanbag', public INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY, reporter_id INTEGER NOT NULL, target_id INTEGER NOT NULL, reason TEXT NOT NULL, created_at INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'open');
CREATE TABLE IF NOT EXISTS blocks(owner_id INTEGER NOT NULL, target_id INTEGER NOT NULL, PRIMARY KEY(owner_id,target_id));
CREATE TABLE IF NOT EXISTS moderation_actions(id INTEGER PRIMARY KEY, target_id INTEGER NOT NULL, action TEXT NOT NULL, reason TEXT NOT NULL, at INTEGER NOT NULL);`);
db.exec(`CREATE TABLE IF NOT EXISTS activity_records(player_id INTEGER PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE, survival_best INTEGER NOT NULL DEFAULT 0, survival_prize_day TEXT NOT NULL DEFAULT '', relay_reward_at INTEGER NOT NULL DEFAULT 0,jam_reward_at INTEGER NOT NULL DEFAULT 0,race_reward_at INTEGER NOT NULL DEFAULT 0);`);
for(const [col,type] of [['jam_reward_at','INTEGER NOT NULL DEFAULT 0'],['race_reward_at','INTEGER NOT NULL DEFAULT 0']])if(!db.prepare('PRAGMA table_info(activity_records)').all().some(r=>r.name===col))db.exec(`ALTER TABLE activity_records ADD COLUMN ${col} ${type}`);
const cols=db.prepare('PRAGMA table_info(players)').all();
if(!cols.some(c=>c.name==='chests'))db.exec("ALTER TABLE players ADD COLUMN chests TEXT NOT NULL DEFAULT '{}'");
for(const [col,sqlType] of [['dungeon_clears','INTEGER NOT NULL DEFAULT 0'],['duel_wins','INTEGER NOT NULL DEFAULT 0'],['last_arcade_day',"TEXT NOT NULL DEFAULT ''"],['arcade_plays','INTEGER NOT NULL DEFAULT 0'],['silenced_until','INTEGER NOT NULL DEFAULT 0'],['banned_until','INTEGER NOT NULL DEFAULT 0']])if(!cols.some(c=>c.name===col))db.exec(`ALTER TABLE players ADD COLUMN ${col} ${sqlType}`);
const sql={
 byName:db.prepare('SELECT * FROM players WHERE username=?'),
 byId:db.prepare('SELECT * FROM players WHERE id=?'),
 insert:db.prepare(`INSERT INTO players(username,password_hash,salt,class,palette,inventory,equipped,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)`),
 update:db.prepare(`UPDATE players SET level=?,xp=?,hp=?,focus=?,gold=?,x=?,y=?,inventory=?,equipped=?,quest_kills=?,quest_done=?,boss_done=?,chests=?,updated_at=? WHERE id=?`),
 sessAdd:db.prepare('INSERT INTO sessions(token_hash,player_id,expires_at) VALUES(?,?,?)'),
 sessFind:db.prepare('SELECT player_id FROM sessions WHERE token_hash=? AND expires_at>?'),
 sessRemove:db.prepare('DELETE FROM sessions WHERE token_hash=?'),
 top:db.prepare('SELECT username,class,level,quest_done,boss_done,dungeon_clears,duel_wins FROM players WHERE is_demo=0 ORDER BY dungeon_clears DESC,level DESC,xp DESC LIMIT 20'),
 homeGet:db.prepare('SELECT plot,theme,furniture,public FROM homes WHERE owner_id=?'),
 homePlot:db.prepare('SELECT owner_id FROM homes WHERE plot=?'),
 homeInsert:db.prepare('INSERT INTO homes(owner_id,plot) VALUES (?,?)'),
 homeUpdate:db.prepare('UPDATE homes SET theme=?,furniture=?,public=? WHERE owner_id=?'),
 banGet:db.prepare('SELECT banned_until,silenced_until FROM players WHERE id=?'),
 report:db.prepare('INSERT INTO reports(reporter_id,target_id,reason,created_at) VALUES(?,?,?,?)'),
 blockAdd:db.prepare('INSERT OR IGNORE INTO blocks(owner_id,target_id) VALUES (?,?)'),
 blockRemove:db.prepare('DELETE FROM blocks WHERE owner_id=? AND target_id=?'),
 blockAll:db.prepare('SELECT target_id FROM blocks WHERE owner_id=?')
};
const now=()=>Date.now();
const tokenHash=s=>crypto.createHash('sha256').update(s).digest('hex');
const passwordHash=(password,salt)=>crypto.scryptSync(password,salt,64).toString('hex');
const compare=(a,b)=>a.length===b.length&&crypto.timingSafeEqual(Buffer.from(a,'hex'),Buffer.from(b,'hex'));
const random=()=>crypto.randomInt(0,1000000)/1000000;
const rnd=(min,max)=>min+Math.floor(random()*(max-min+1));
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const xpNeed=l=>80+l*50;
const countSignals=mask=>Number(mask||0).toString(2).replace(/0/g,'').length;
const maxHp=p=>100+(p.level-1)*18+(p.class==='Guardian'?25:0);
const maxFocus=p=>50+(p.level-1)*6+(p.class==='Dreamer'?25:0);
const attackPower=p=>4+p.level*2+(items[p.equipped.weapon]?.atk||0)+(p.class==='Scout'?3:0);
const defense=p=>Math.floor(p.level/3)+(items[p.equipped.armor]?.def||0)+(p.class==='Guardian'?2:0);
const colorRoles=['Rose','Ocean','Golden','Lavender','Mint','Coral'];
const classNames=['Scout','Dreamer','Guardian'];
const wsClients=new Set();
const parties=new Map(),instances=new Map(),pendingInvites=new Map(),recentDuelWins=new Map(),reportCooldown=new Map();
const beaconState={players:new Map(),cooldown:0};
const jamPlayers=new Map(),jamState={cooldown:0};const circuitRaces=new Map();
const relayEvents=new Map(); // per-party co-op waypoint challenges; validated by server positions
const RELAY_POINTS=[{x:65.5,y:27.5,name:'Moonberry'}, {x:82.5,y:55.5,name:'Soda Shore'}, {x:111.5,y:32.5,name:'Neon Boardwalk'}];
const HOME_PLOTS=[{x:101.5,y:82.5},{x:108.5,y:83.5},{x:115.5,y:84.5},{x:121.5,y:71.5}];
const inArena=p=>p.zone==='overworld'&&p.x>=ARENA.x1&&p.x<=ARENA.x2&&p.y>=ARENA.y1&&p.y<=ARENA.y2;
const inZone=(a,b)=>a.zone===b.zone;
const canSee=(a,b)=>inZone(a,b)&&!a.blocked?.has(b.id);
const partyOf=p=>p.partyId?parties.get(p.partyId):null;
const partyState=p=>{const party=partyOf(p);return party?{leader:party.leader,members:[...party.members].map(id=>({id,name:online.get(id)?.name||'?'}))}:{leader:p.id,members:[{id:p.id,name:p.name}]};};
const online=new Map(); // account id => authoritative player state
const enemies=mobs.map(e=>{const loc=reviveLocation(e.x,e.y);return {...e,x:loc.x,y:loc.y,ox:loc.x,oy:loc.y,hp:mobDefs[e.kind].maxHp,alive:true,respawnAt:0,lastAttack:0,dir:0,roamUntil:0,contributors:new Map()};});
const mobView=e=>({id:e.id,kind:e.kind,x:+e.x.toFixed(2),y:+e.y.toFixed(2),hp:e.hp,maxHp:e.maxHp||mobDefs[e.kind].maxHp,alive:e.alive,boss:!!e.boss,level:e.level});
const distance=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y);
function userSafe(p){return {id:p.id,name:p.name,level:p.level,class:p.class,palette:p.palette,x:+p.x.toFixed(2),y:+p.y.toFixed(2),hp:p.hp,maxHp:maxHp(p),focus:Math.floor(p.focus),maxFocus:maxFocus(p),state:p.state||'idle',zone:p.zone||'overworld',pet:p.equipped.pet||null,pvp:!!p.pvp};}
function details(p){return {...userSafe(p),gold:p.gold,xp:p.xp,xpNeeded:xpNeed(p.level),inventory:p.inventory,equipped:p.equipped,attack:attackPower(p),defense:defense(p),questKills:countSignals(p.questKills),signalMask:p.questKills,questDone:p.questDone,bossDone:p.bossDone,chests:p.chests,demo:p.demo,party:partyState(p),dungeonClears:p.dungeonClears||0,duelWins:p.duelWins||0,activities:db.prepare('SELECT survival_best,relay_reward_at FROM activity_records WHERE player_id=?').get(p.id)||{survival_best:0,relay_reward_at:0},survival:instances.get(p.zone)?.kind==='survival'?{wave:instances.get(p.zone).wave,kills:instances.get(p.zone).kills,remaining:Math.max(0,Math.ceil((SURVIVAL_LENGTH_MS-(now()-instances.get(p.zone).createdAt))/1000))}:null,home:sql.homeGet.get(p.id)||null,textChat:TEXT_CHAT_ENABLED,quickChat:QUICK_CHAT,arena:ARENA,riftNames:RIFTS,arcadePlays:p.arcadePlays||0};}
function reviveLocation(x,y){if(world.safe(x,y))return {x,y}; for(let r=1;r<8;r++)for(let a=0;a<16;a++){let nx=x+Math.round(Math.cos(a*Math.PI/8)*r),ny=y+Math.round(Math.sin(a*Math.PI/8)*r);if(world.safe(nx,ny))return {x:nx,y:ny};}return START;}
function createPlayer(row){let loc=reviveLocation(row.x,row.y);return {id:row.id,name:row.username,class:row.class,palette:row.palette,level:row.level,xp:row.xp,hp:row.hp,focus:row.focus,gold:row.gold,x:loc.x,y:loc.y,inventory:JSON.parse(row.inventory),equipped:JSON.parse(row.equipped),questKills:row.quest_kills,questDone:!!row.quest_done,bossDone:!!row.boss_done,chests:JSON.parse(row.chests||'{}'),demo:!!row.is_demo,dungeonClears:row.dungeon_clears||0,duelWins:row.duel_wins||0,lastArcadeDay:row.last_arcade_day||'',arcadePlays:row.arcade_plays||0,zone:'overworld',pvp:false,blocked:new Set(sql.blockAll.all(row.id).map(r=>r.target_id)),partyId:null,challenge:null,challengeAt:0,lastPulse:0,lastPvp:0,sockets:new Set(),input:{},lastAttack:0,lastBurst:0,respawnImmune:0,healTime:0,dirty:false,state:'idle'};}
function save(p){if(p.demo)return;sql.update.run(p.level,p.xp,p.hp,Math.floor(p.focus),p.gold,p.zone==='overworld'?p.x:GATE.x,p.zone==='overworld'?p.y:GATE.y,JSON.stringify(p.inventory),JSON.stringify(p.equipped),p.questKills,+p.questDone,+p.bossDone,JSON.stringify(p.chests),now(),p.id);db.prepare('UPDATE players SET dungeon_clears=?,duel_wins=?,last_arcade_day=?,arcade_plays=? WHERE id=?').run(p.dungeonClears,p.duelWins,p.lastArcadeDay,p.arcadePlays,p.id);p.dirty=false;}
function send(ws,obj){if(ws.closed||ws.socket.destroyed)return;const message=Buffer.from(JSON.stringify(obj));const head=message.length<126?Buffer.from([0x81,message.length]):message.length<65536?Buffer.from([0x81,126,message.length>>8,message.length&255]):Buffer.from([0x81,127,0,0,0,0,0,0,(message.length>>>24)&255,(message.length>>>16)&255,(message.length>>>8)&255,message.length&255]);if(ws.socket.writableLength<150000)ws.socket.write(Buffer.concat([head,message]));}
function sendSelf(p){for(const ws of p.sockets)send(ws,{type:'self',player:details(p)});}
function notify(p,msg,kind='info'){for(const ws of p.sockets)send(ws,{type:'toast',msg,kind});}
function addItem(p,id,n=1){if(!items[id])return;p.inventory[id]=(p.inventory[id]||0)+n;p.dirty=true;}
function awardXP(p,amount){p.xp+=amount;while(p.xp>=xpNeed(p.level)&&p.level<50){p.xp-=xpNeed(p.level);p.level++;p.hp=maxHp(p);p.focus=maxFocus(p);notify(p,`LEVEL ${p.level}! Your heart shines brighter!`,'level');}p.dirty=true;}
function lootRoll(tier){const total=Object.values(tier).reduce((a,b)=>a+b,0);let roll=random()*total;for(const [k,v] of Object.entries(tier)){roll-=v;if(roll<0){const arr=lootByRarity[k];return arr[rnd(0,arr.length-1)];}}return 'fizzy-pop';}
function killMob(e,killer){
 e.alive=false;e.hp=0;e.respawnAt=now()+(e.boss?120000:25000);
 const def=mobDefs[e.kind];const dungeon=e.id.includes(':')?instances.get(e.id.split(':')[0]):null;let eligible=[];
 for(const [id,dealt] of e.contributors){const p=online.get(id);if(!p||distance(p,e)>13||(dungeon&&p.zone!==dungeon.id))continue;const ratio=dealt/(e.maxHp||def.maxHp);if(ratio>=.10||id===killer.id)eligible.push({p,ratio});}
 if(dungeon?.kind==='survival'){dungeon.kills++;for(const ws of killer.sockets)send(ws,{type:'effect',kind:'defeat',x:e.x,y:e.y,by:killer.name});return;}
 if(!eligible.length)eligible=[{p:killer,ratio:1}];
 for(const {p,ratio} of eligible){
  p.gold+=Math.max(1,Math.round(rnd(...def.coins)*(.65+.35*ratio)*(dungeon?1.2:1)));
  awardXP(p,Math.max(1,Math.round(def.xp*(.65+.35*ratio))));
  // Combat is optional for the main story. Discover signals instead of kill/fetch chores.
  const got=e.boss?lootRoll({rare:82,epic:16,legendary:2}):(random()<(dungeon?.39:.29)?lootRoll(lootWeights):null);
  if(got){addItem(p,got);notify(p,`LOOT! ${items[got].name} · ${items[got].rarity.toUpperCase()}`,(items[got].rarity==='legendary'?'legendary':'loot'));}
  if(e.boss&&!dungeon){p.bossDone=true;notify(p,'THE HUSHLING FALLS! The grove can sing again!','level');}
  p.dirty=true;sendSelf(p);
 }
 e.contributors.clear();
 for(const ws of wsClients)if(ws.player.zone===killer.zone)send(ws,{type:'effect',kind:'defeat',x:e.x,y:e.y,name:def.name,by:killer.name});
 if(dungeon&&e.boss&&!dungeon.completed){dungeon.completed=true;for(const id of dungeon.members){const member=online.get(id);if(!member||member.zone!==dungeon.id)continue;member.dungeonClears++;awardXP(member,110+40*(RIFTS.findIndex(r=>r.id===dungeon.kind)+1));member.gold+=95+35*(RIFTS.findIndex(r=>r.id===dungeon.kind)+1);addItem(member,lootRoll({uncommon:40,rare:48,epic:11.5,legendary:.5}));notify(member,'RIFT CLEARED! Team chest and bonus XP awarded!','level');sendSelf(member);}setTimeout(()=>{for(const id of dungeon.members){const member=online.get(id);if(member?.zone===dungeon.id)leaveRift(member);}instances.delete(dungeon.id);},11000).unref();}
}
function hit(p,burst=false){const time=now(), cooldown=burst?1900:620;if(time-(burst?p.lastBurst:p.lastAttack)<cooldown)return;if(p.hp<=0)return;
 if(burst&&p.focus<18){notify(p,'Not enough Focus for Echo Burst.');return;}
 const pool=p.zone==='overworld'?enemies:(instances.get(p.zone)?.enemies||[]);let inRange=pool.filter(e=>e.alive&&distance(p,e)<(burst?3.2:2));if(!inRange.length&&!inArena(p)){if(!burst)p.lastAttack=time;return;}
 if(burst){p.focus-=18;p.lastBurst=time;}else p.lastAttack=time;
 inRange.sort((a,b)=>distance(p,a)-distance(p,b));if(!burst)inRange=inRange.slice(0,1);
 for(const e of inRange){const crit=random()<.11;let damage=Math.max(1,Math.floor((attackPower(p)+(burst?10+Math.floor(p.level*1.4):0))*(crit?1.75:1)-mobDefs[e.kind].def+rnd(-2,3)));e.contributors.set(p.id,(e.contributors.get(p.id)||0)+Math.min(damage,e.hp));e.hp=Math.max(0,e.hp-damage);
  for(const ws of wsClients)if(ws.player.zone===p.zone)send(ws,{type:'effect',kind:burst?'burst':'hit',x:e.x,y:e.y,damage,crit,by:p.name});
  if(e.hp<=0)killMob(e,p);
 }
 if(inArena(p)&&p.pvp)for(const opponent of online.values()){if(opponent.id===p.id||!opponent.pvp||!inArena(opponent)||distance(p,opponent)>(burst?3.0:1.8))continue;const d=Math.max(1,Math.round(maxHp(opponent)*(burst?.15:.085)+rnd(-2,2)));opponent.hp-=d;for(const w of opponent.sockets)send(w,{type:'effect',kind:'hurt',x:opponent.x,y:opponent.y,damage:d});if(opponent.hp<=0){const pair=[p.id,opponent.id].sort().join(':');if(time-(recentDuelWins.get(pair)||0)>300000){p.duelWins++;recentDuelWins.set(pair,time);notify(p,'FRIENDLY K.O.! +1 arena win','level');}opponent.hp=maxHp(opponent);opponent.x=101.5;opponent.y=39.5;opponent.pvp=false;opponent.respawnImmune=time+3000;notify(opponent,'Good match! No items or currency lost.','info');}opponent.dirty=true;sendSelf(opponent);} 
 p.dirty=true;sendSelf(p);
}
function interact(p){
 if(p.zone!=='overworld'){if(instances.get(p.zone)?.kind==='survival'){notify(p,'Static Storm: your echoes attack automatically. Keep moving!');return;}if(distance(p,{x:5.5,y:14.5})<2.7){leaveRift(p);return;}notify(p,'Clear the Rift together, or use the EXIT button.');return;}
 const signal=signalNodes.find(n=>distance(p,n)<2.4);if(signal){const index=signalNodes.indexOf(signal),bit=2**index,old=p.questKills;if(!(old&bit)){p.questKills|=bit;awardXP(p,32);p.gold+=12;notify(p,`SIGNAL FOUND! ${signal.wave} • +32 XP +12 stardust`,'level');if(countSignals(p.questKills)>=3&&!p.questDone){p.questDone=true;p.gold+=140;awardXP(p,160);addItem(p,'antenna');notify(p,'THE FIRST MIXTAPE COMPLETE! You brought back the music.','level');}sendSelf(p);}else notify(p,`${signal.name}: ${signal.wave}.`);return;}
 const chest=chests.find(c=>distance(c,p)<1.9&&!p.chests[c.id]);
 if(chest){p.chests[chest.id]=true;const coins=rnd(12,25)*chest.tier;p.gold+=coins;
  const potion=chest.tier>=3?'moon-candy':'fizzy-pop';addItem(p,potion);
  if(chest.tier>=4&&random()<.13)addItem(p,lootRoll({uncommon:80,rare:18,epic:2}));
  p.dirty=true;notify(p,`SECRET STASH! +${coins} stardust · ${items[potion].name}`,'loot');sendSelf(p);
  for(const ws of p.sockets)send(ws,{type:'effect',kind:'chest',x:chest.x,y:chest.y});return;
 }
 const npc=npcs.find(n=>distance(p,n)<2.7);if(!npc){notify(p,'Walk closer to someone to talk.');return;}
 if(npc.id==='pip'&&p.questDone)notify(p,'Your mixtape sounds incredible! The airwaves are back.','level');
 for(const ws of p.sockets)send(ws,{type:'dialogue',npc});
}
// Zones isolate dungeon parties; coordinates are never client-authoritative.
function sceneFor(p){return p.zone==='overworld'?null:instances.get(p.zone)?.scene||null;}
function sendScene(p){const scene=sceneFor(p);for(const ws of p.sockets)send(ws,{type:'scene',world:scene,zone:p.zone});sendSelf(p);}
function leaveRift(p){if(p.zone==='overworld')return;const inst=instances.get(p.zone);if(inst)inst.members.delete(p.id);p.zone='overworld';p.x=GATE.x;p.y=GATE.y;p.pvp=false;p.input={};p.hp=Math.max(1,p.hp);sendScene(p);notify(p,'Returned to the Wildways.');if(inst&&!inst.members.size)instances.delete(inst.id);}
function sendParty(p){const party=partyOf(p);for(const id of party?.members||[p.id]){const member=online.get(id);if(member)sendSelf(member);}}
function leaveParty(p){const party=partyOf(p);if(!party)return;party.members.delete(p.id);p.partyId=null;notify(p,'Left the team.');if(party.leader===p.id)party.leader=[...party.members][0];if(party.members.size<2){for(const id of party.members){const friend=online.get(id);if(friend){friend.partyId=null;notify(friend,'The team disbanded.');sendSelf(friend);}}parties.delete(party.id);}else for(const id of party.members)if(online.get(id))sendSelf(online.get(id));sendSelf(p);}
function partyAction(p,msg){if(msg.action==='party-leave'){leaveParty(p);return;}
 if(msg.action==='party-invite'){const name=String(msg.id||'');const target=[...online.values()].find(v=>v.name.toLowerCase()===name.toLowerCase());if(!target||target.id===p.id||target.zone!=='overworld'||distance(p,target)>14||target.blocked.has(p.id)||p.blocked.has(target.id)){notify(p,'That traveler must be nearby and available.');return;}if(p.partyId&&partyOf(p)?.members.size>=4){notify(p,'Teams hold up to four adventurers.');return;}pendingInvites.set(target.id,{from:p.id,until:now()+30000});for(const ws of target.sockets)send(ws,{type:'invite',name:p.name,id:p.id});notify(p,'Team invite sent!');return;}
 if(msg.action==='party-accept'){const inv=pendingInvites.get(p.id);pendingInvites.delete(p.id);if(!inv||inv.until<now()){notify(p,'That invite expired.');return;}const leader=online.get(inv.from);if(!leader||p.partyId||distance(p,leader)>16){notify(p,'You must be near the teammate to join.');return;}let party=partyOf(leader);if(!party){party={id:crypto.randomUUID(),leader:leader.id,members:new Set([leader.id])};parties.set(party.id,party);leader.partyId=party.id;}if(party.members.size>=4)return notify(p,'Team is full.');party.members.add(p.id);p.partyId=party.id;for(const id of party.members){const m=online.get(id);if(m){notify(m,`${p.name} joined the team!`,'level');sendSelf(m);}}return;}}
function startRift(p,id){if(p.zone!=='overworld'||distance(p,GATE)>4)return notify(p,'Find the Rift Gate along the Wildway.');const type=RIFTS.find(r=>r.id===id);if(!type)return;
 const party=partyOf(p);if(party&&party.leader!==p.id)return notify(p,'Only the team leader can start a Rift.');const members=(party?[...party.members]:[p.id]).map(id=>online.get(id)).filter(Boolean);
 if(members.some(m=>m.zone!=='overworld'||distance(m,GATE)>6))return notify(p,'All team members need to stand at the gate.');
 const instance=createRift(id,crypto.randomUUID(),members.map(m=>m.id));instances.set(instance.id,instance);
 for(const m of members){m.zone=instance.id;m.x=instance.scene.start.x;m.y=instance.scene.start.y;m.input={};m.pvp=false;m.hp=maxHp(m);m.focus=maxFocus(m);m.dirty=true;sendScene(m);notify(m,`${type.name} • TEAM OF ${members.length} • FIND THE BOSS!`,'level');}}
function finishSurvival(p,reason='time'){
 const inst=instances.get(p.zone);if(!inst||inst.kind!=='survival'||inst.completed)return;
 inst.completed=true;const existing=db.prepare('SELECT * FROM activity_records WHERE player_id=?').get(p.id);
 const score=inst.kills+inst.wave*3, best=Math.max(existing?.survival_best||0,score),day=new Date().toISOString().slice(0,10);
 db.prepare('INSERT INTO activity_records(player_id,survival_best,survival_prize_day) VALUES (?,?,?) ON CONFLICT(player_id) DO UPDATE SET survival_best=excluded.survival_best,survival_prize_day=excluded.survival_prize_day').run(p.id,best,day);
 const reward=(existing?.survival_prize_day===day)?0:Math.min(120,25+inst.wave*12);
 if(reward){p.gold+=reward;awardXP(p,Math.min(180,35+score));if(inst.wave>=5&&random()<.22)addItem(p,lootRoll({uncommon:72,rare:25,epic:3}));}
 notify(p,`STATIC STORM ${reason==='time'?'COMPLETE':'OVER'}! Wave ${inst.wave} · ${inst.kills} echoes · score ${score}${reward?' · +'+reward+' stardust':' · daily reward claimed'}`,'level');
 for(const ws of p.sockets)send(ws,{type:'survival-result',score,wave:inst.wave,kills:inst.kills,best,reward});
 leaveRift(p);instances.delete(inst.id);sendSelf(p);
}
function startSurvival(p){if(p.zone!=='overworld'||distance(p,SURVIVAL_LOCATION)>5)return notify(p,'Visit the Neon Boardwalk arcade to play Static Storm.');const id=crypto.randomUUID(),inst=createSurvival(id,p.id);instances.set(id,inst);p.zone=id;p.x=inst.scene.start.x;p.y=inst.scene.start.y;p.hp=maxHp(p);p.focus=maxFocus(p);p.pvp=false;p.input={};spawnSurvivalWave(inst);sendScene(p);notify(p,'STATIC STORM! 90 seconds. Your radio fires at nearby echoes automatically. Dodge and survive!','level');}
function startRelay(p){if(p.zone!=='overworld'||distance(p,GATE)>5)return notify(p,'Find the Wildway Gate to start the co-op relay.');const party=partyOf(p);if(!party||party.members.size<2)return notify(p,'Signal Relay requires at least two friends on a team.');if(party.leader!==p.id)return notify(p,'Only the party leader can start a relay.');if(relayEvents.has(party.id))return notify(p,'Your team already has an active relay!');if([...party.members].some(id=>!online.has(id)||distance(online.get(id),GATE)>7))return notify(p,'Gather your teammates at the Wildway Gate.');relayEvents.set(party.id,{ends:now()+420000,done:new Set(),members:new Set(party.members)});for(const id of party.members){const member=online.get(id);notify(member,'SIGNAL RELAY! Tune the Moonberry, Soda Shore & Neon towers within 7 minutes. Split up!','level');}}
function jam(p){if(p.zone!=='overworld'||distance(p,ARCADE)>5)return notify(p,'Find the Neon Boardwalk jukebox to join the jam.');const t=now();if(t<jamState.cooldown)return notify(p,'The jukebox is cooling down. Dance while it recharges!');jamPlayers.set(p.id,t);for(const [id,tick] of jamPlayers)if(t-tick>9000||!online.has(id))jamPlayers.delete(id);
 const people=[...jamPlayers.keys()];if(people.length<2)return notify(p,'Beat sent! A second player must join within 9 seconds.');jamState.cooldown=t+75000;jamPlayers.clear();for(const id of people){const member=online.get(id);if(!member)continue;const row=db.prepare('SELECT jam_reward_at FROM activity_records WHERE player_id=?').get(id);if(!row||t-row.jam_reward_at>900000){member.gold+=23;awardXP(member,28);db.prepare('INSERT INTO activity_records(player_id,jam_reward_at) VALUES(?,?) ON CONFLICT(player_id) DO UPDATE SET jam_reward_at=excluded.jam_reward_at').run(id,t);}notify(member,'DUO JAM! You matched the beat together! 🎵','level');sendSelf(member);}for(const ws of wsClients)if(ws.player.zone==='overworld'&&distance(ws.player,ARCADE)<17)send(ws,{type:'effect',kind:'burst',x:ARCADE.x,y:ARCADE.y});}
const RACE_NODES=[{x:105.5,y:37.5,name:'Starting Stretch'}, {x:110.5,y:50.5,name:'Spark Crossing'}, {x:110.5,y:78.5,name:'Commons Finish'}];
function raceStart(p){if(p.zone!=='overworld'||distance(p,ARCADE)>6)return notify(p,'Meet at the Neon Boardwalk to start a Circuit Sprint.');const party=partyOf(p);if(!party||party.leader!==p.id||party.members.size<2)return notify(p,'Race leader needs a team of 2–4.');if(circuitRaces.has(party.id))return notify(p,'Your team already has a race in progress.');if([...party.members].some(id=>!online.has(id)||distance(online.get(id),ARCADE)>8))return notify(p,'Gather your racers at the Boardwalk.');const entrants=new Map([...party.members].map(id=>[id,{step:0,done:0}]));circuitRaces.set(party.id,{expires:now()+240000,entrants});for(const id of party.members)notify(online.get(id),'CIRCUIT SPRINT! Follow the route: south to the Yard, across Spark Crossing, finish in Cassette Commons!','level');}
function raceTick(time){for(const [id,race] of circuitRaces){if(time>race.expires){for(const uid of race.entrants.keys())if(online.get(uid))notify(online.get(uid),'Circuit Sprint ended. Race again any time!');circuitRaces.delete(id);continue;}
 for(const [uid,progress] of race.entrants){if(progress.done)continue;const p=online.get(uid),target=RACE_NODES[progress.step];if(!p||p.zone!=='overworld'||!target)continue;if(distance(p,target)>2.4)continue;progress.step++;notify(p,`${target.name} checkpoint ${progress.step}/3!`,'heal');if(progress.step>=RACE_NODES.length){progress.done=time;const row=db.prepare('SELECT race_reward_at FROM activity_records WHERE player_id=?').get(uid);if(!row||time-row.race_reward_at>3600000){p.gold+=45;awardXP(p,65);db.prepare('INSERT INTO activity_records(player_id,race_reward_at) VALUES(?,?) ON CONFLICT(player_id) DO UPDATE SET race_reward_at=excluded.race_reward_at').run(uid,time);sendSelf(p);}notify(p,'CIRCUIT SPRINT FINISH! You crossed the finish line!','level');}}
 if([...race.entrants.values()].every(v=>v.done))circuitRaces.delete(id);
 }}
function relayTick(time){for(const [partyId,e] of relayEvents){if(time>e.ends){for(const id of e.members)if(online.get(id))notify(online.get(id),'The relay timed out. Try coordinating a new route!');relayEvents.delete(partyId);continue;}
 for(let i=0;i<RELAY_POINTS.length;i++){if(e.done.has(i))continue;const point=RELAY_POINTS[i];const hasRunner=[...e.members].some(id=>{const m=online.get(id);return m?.zone==='overworld'&&distance(m,point)<2.4;});if(!hasRunner)continue;e.done.add(i);for(const id of e.members)if(online.get(id))notify(online.get(id),`RELAY ${e.done.size}/3: ${point.name} tuned!`,'heal');}
 if(e.done.size===RELAY_POINTS.length){for(const id of e.members){const m=online.get(id);if(!m)continue;const row=db.prepare('SELECT relay_reward_at FROM activity_records WHERE player_id=?').get(m.id);if(!row||time-row.relay_reward_at>3600000){m.gold+=60;awardXP(m,95);db.prepare('INSERT INTO activity_records(player_id,relay_reward_at) VALUES (?,?) ON CONFLICT(player_id) DO UPDATE SET relay_reward_at=excluded.relay_reward_at').run(m.id,time);notify(m,'TEAM RELAY CLEARED! +60 stardust +95 XP','level');sendSelf(m);}else notify(m,'TEAM RELAY COMPLETE! Hourly reward already claimed.','level');}relayEvents.delete(partyId);}
 }}
function minigame(p,kind){const station=kind==='fish'?FISHING:ARCADE;if(p.zone!=='overworld'||distance(p,station)>4)return notify(p,'Find the game station before playing.');if(p.challenge)return notify(p,'Finish your current challenge first.');const day=new Date().toISOString().slice(0,10);if(p.lastArcadeDay!==day){p.lastArcadeDay=day;p.arcadePlays=0;}if(p.arcadePlays>=12)return notify(p,'Daily prize limit reached. Come back tomorrow!');if(now()-p.challengeAt<12000)return notify(p,'Let the machine reset for a few seconds.');const length=kind==='fish'?4:5;const sequence=Array.from({length},()=>rnd(0,3));p.challenge={id:crypto.randomUUID(),kind,sequence,expires:now()+27000};p.challengeAt=now();for(const ws of p.sockets)send(ws,{type:'minigame',game:kind,challengeId:p.challenge.id,sequence});}
function finishMinigame(p,msg){const c=p.challenge;p.challenge=null;if(!c||c.id!==msg.id||c.expires<now())return notify(p,'Challenge expired. Try again.');if(!Array.isArray(msg.sequence)||msg.sequence.length!==c.sequence.length||!msg.sequence.every((a,i)=>Number.isInteger(a)&&a===c.sequence[i]))return notify(p,'Not quite! Practice makes perfect.');if(p.zone!=='overworld'||distance(p,c.kind==='fish'?FISHING:ARCADE)>5)return;const reward=rnd(10,23);p.gold+=reward;p.arcadePlays++;p.dirty=true;if(c.kind==='fish'){if(random()<.35)addItem(p,'pixel-soda');notify(p,`Pixel Fishing success! +${reward} stardust 🎣`,'loot');}else{if(random()<.16)addItem(p,'disc');notify(p,`MEMORY JAM perfect! +${reward} stardust 🎵`,'loot');}sendSelf(p);}
function pulseBeacon(p){if(p.zone!=='overworld'||distance(p,BEACON)>4)return notify(p,'Find the Co-op Broadcast Beacon.');const t=now();if(t<beaconState.cooldown)return notify(p,'The beacon is recharging.');if(t-p.lastPulse<25000)return notify(p,'Your radio needs a moment to recharge.');p.lastPulse=t;beaconState.players.set(p.id,t);for(const [id,time] of beaconState.players)if(t-time>20000||!online.has(id))beaconState.players.delete(id);if(beaconState.players.size<2){notify(p,'Signal 1/2! Another player must tune the beacon within 20 seconds.','loot');return;}const ids=[...beaconState.players.keys()];beaconState.players.clear();beaconState.cooldown=t+90000;for(const id of ids){const m=online.get(id);if(!m||m.zone!=='overworld'||distance(m,BEACON)>7)continue;m.gold+=35;awardXP(m,45);if(random()<.24)addItem(m,'disc');notify(m,'DUO BROADCAST COMPLETE! +35 stardust +45 XP 🎶','level');sendSelf(m);}for(const ws of wsClients)if(ws.player.zone==='overworld')send(ws,{type:'effect',kind:'beacon',x:BEACON.x,y:BEACON.y});}
function homeAction(p,msg){const id=String(msg.id||'');const home=sql.homeGet.get(p.id);if(msg.action==='home-buy'){if(p.zone!=='overworld'||distance(p,HOME_AGENT)>8)return notify(p,'Visit Tilly in Cassette Commons first.');const plot=Number(id);if(!Number.isInteger(plot)||plot<0||plot>=HOME_PLOTS.length||home)return notify(p,'This home template is unavailable.');if(p.gold<450)return notify(p,'A cozy room costs 450 stardust.');try{sql.homeInsert.run(p.id,plot);p.gold-=450;p.dirty=true;notify(p,'HOME SWEET HOME! Your own cozy room is ready.','level');sendSelf(p);}catch{notify(p,'Could not create this home.');}return;}
 if(!home){notify(p,'You need to own a home first.');return;}const theme=msg.action==='home-theme'?id:home.theme;const furniture=msg.action==='home-furniture'?id:home.furniture;const vis=msg.action==='home-public'?(id==='yes'?1:0):home.public;
 if(!['violet','sunset','ocean','forest','neon'].includes(theme)||!['beanbag','arcade','plants','bookshelf','jukebox'].includes(furniture))return;const isChange=theme!==home.theme||furniture!==home.furniture;if(isChange&&p.gold<35)return notify(p,'New décor costs 35 stardust.');if(isChange)p.gold-=35;sql.homeUpdate.run(theme,furniture,vis,p.id);p.dirty=true;sendSelf(p);notify(p,'Your room has been updated! ✨','loot');}
function reportAction(p,msg){if(p.demo)return notify(p,'Sign up to report other players.');const target=[...online.values()].find(v=>v.name.toLowerCase()===String(msg.id||'').toLowerCase());const reason=String(msg.reason||'').slice(0,80);if(!target||target.id===p.id||!['harassment','spam','unsafe','cheating','other'].includes(reason))return notify(p,'Select a nearby player and report reason.');if(!inZone(p,target)||distance(p,target)>24)return notify(p,'You can only report players in your area.');const k=p.id+':'+target.id;if(now()-(reportCooldown.get(k)||0)<3600000)return notify(p,'You have already submitted a recent report.');reportCooldown.set(k,now());sql.report.run(p.id,target.id,reason,now());notify(p,'Report received. Moderators can review it. Thank you.');}
function blockAction(p,msg){const target=[...online.values()].find(v=>v.name.toLowerCase()===String(msg.id||'').toLowerCase());if(!target||target.id===p.id)return;sql.blockAdd.run(p.id,target.id);p.blocked.add(target.id);notify(p,`${target.name} blocked. Their chat and avatar will be hidden.`,'info');}
function playerAction(p,msg){switch(msg.action){
 case 'attack':hit(p);break;
 case 'pvp-toggle':{if(!inArena(p))return notify(p,'PvP is only available inside the Spark Yard.');p.pvp=!p.pvp;notify(p,p.pvp?'Friendly PvP enabled. No gear advantage, no losses.':'PvP disabled.');sendSelf(p);break;}
 case 'party-invite':case 'party-accept':case 'party-leave':partyAction(p,msg);break;
 case 'dungeon-start':startRift(p,String(msg.id||''));break;
 case 'dungeon-exit':{const inst=instances.get(p.zone);if(inst?.kind==='survival')finishSurvival(p,'early');else leaveRift(p);break;}
 case 'survival-start':startSurvival(p);break;
 case 'survival-exit':{if(instances.get(p.zone)?.kind==='survival')finishSurvival(p,'early');break;}
 case 'relay-start':startRelay(p);break;
 case 'jam':jam(p);break;
 case 'race-start':raceStart(p);break;
 case 'minigame-start':minigame(p,String(msg.id||''));break;
 case 'minigame-finish':finishMinigame(p,msg);break;
 case 'beacon':pulseBeacon(p);break;
 case 'home-buy':case 'home-theme':case 'home-furniture':case 'home-public':homeAction(p,msg);break;
 case 'report':reportAction(p,msg);break;
 case 'block':blockAction(p,msg);break;
 case 'burst':hit(p,true);break;
 case 'team-heal':{if(p.focus<25||now()-(p.lastHealSkill||0)<10000)return notify(p,'Team heal needs 25 Focus and a 10-second recharge.');p.focus-=25;p.lastHealSkill=now();let healed=0;for(const member of online.values())if(inZone(p,member)&&distance(p,member)<4&&(member.id===p.id||partyOf(p)?.members.has(member.id))){member.hp=Math.min(maxHp(member),member.hp+Math.round(maxHp(member)*.28));sendSelf(member);healed++;}notify(p,`HEARTWAVE! Restored health to ${healed} teammates!`,'heal');break;}
 case 'interact':interact(p);break;
 case 'emote':{const emotes=['👋','💖','✨','💬'];const i=Number(msg.index);if(i>=0&&i<4)for(const ws of wsClients)if(canSee(ws.player,p))send(ws,{type:'emote',id:p.id,emoji:emotes[i]});break;}
 case 'buy':{const id=String(msg.id||'');if(!shopStock.includes(id)||p.zone!=='overworld')return;const npc=npcs.find(n=>n.shop&&distance(p,n)<3.4);if(!npc){notify(p,'Visit Mira’s shop to buy items.');return;}const item=items[id];if(p.gold<item.price){notify(p,'Not enough stardust!');return;}p.gold-=item.price;addItem(p,id);notify(p,`Purchased ${item.name}!`,'loot');sendSelf(p);break;}
 case 'equip':{const id=String(msg.id||''),it=items[id];if(!it||!['weapon','armor','pet'].includes(it.slot)||!p.inventory[id])return;p.equipped[it.slot]=id;p.dirty=true;sendSelf(p);notify(p,`Equipped ${it.name}!`,'loot');break;}
 case 'use':{const id=String(msg.id||''),it=items[id];if(!it||it.slot!=='consumable'||!p.inventory[id]||p.hp>=maxHp(p))return;p.inventory[id]--;if(p.inventory[id]<=0)delete p.inventory[id];p.hp=Math.min(maxHp(p),p.hp+it.heal);p.dirty=true;sendSelf(p);notify(p,`+${it.heal} HP restored!`,'heal');break;}
 }}
const recent=new Map();
function rateLimit(req,key,max=8,windowMs=60000){const ip=(process.env.TRUST_PROXY==='true'?req.headers['x-forwarded-for']?.split(',')[0]:null)||req.socket.remoteAddress||'unknown';const name=ip+'|'+key;let r=recent.get(name);if(!r||now()>r.until){r={count:0,until:now()+windowMs};recent.set(name,r);}return ++r.count<=max;}
function cookie(req){const raw=req.headers.cookie||'';return Object.fromEntries(raw.split(';').map(c=>c.trim().split('=').slice(0,2)).filter(x=>x.length===2));}
function sessionPlayer(req){const tok=cookie(req).lv_session;if(!tok||!/^[0-9a-f]{64}$/.test(tok))return null;const s=sql.sessFind.get(tokenHash(tok),now());return s?sql.byId.get(s.player_id):null;}
function setCookie(res,tok){res.setHeader('Set-Cookie',`lv_session=${tok}; HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000${IS_PROD?'; Secure':''}`);}
function newSession(res,id){const token=crypto.randomBytes(32).toString('hex');sql.sessAdd.run(tokenHash(token),id,now()+30*24*3600000);setCookie(res,token);return token;}
function json(res,status,obj){res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify(obj));}
const originOk=req=>!req.headers.origin||req.headers.origin===`http://${req.headers.host}`||req.headers.origin===`https://${req.headers.host}`||((process.env.ALLOWED_ORIGINS||'').split(',').includes(req.headers.origin));
function readBody(req){return new Promise((resolve,reject)=>{let raw='';req.on('data',c=>{raw+=c;if(raw.length>4096){reject(new Error('Request too large'));req.destroy();}});req.on('end',()=>{try{resolve(JSON.parse(raw||'{}'));}catch{reject(new Error('Invalid JSON'));}});req.on('error',reject);});}
const mime={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.ico':'image/x-icon','.webp':'image/webp'};
async function handler(req,res){
 res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('Referrer-Policy','strict-origin-when-cross-origin');res.setHeader('X-Frame-Options','DENY');res.setHeader('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' ws: wss:; base-uri 'none'; object-src 'none'; frame-ancestors 'none'");
 const url=new URL(req.url,'http://localhost');const pathname=url.pathname;
 if(pathname==='/health')return json(res,200,{ok:true});
 if(pathname==='/api/world'&&req.method==='GET')return json(res,200,{width:WIDTH,height:HEIGHT,tile:TILE,tiles:world.tiles,trees:world.trees,houses,places,npcs,chests,signalNodes,items,shopStock,mobDefs,start:START,quickChat:QUICK_CHAT,textChat:TEXT_CHAT_ENABLED,rifts:RIFTS,arena:ARENA,homePlots:HOME_PLOTS,stations:{arcade:ARCADE,fishing:FISHING,beacon:BEACON,gate:GATE,agent:HOME_AGENT},sceneType:'overworld'});
 if(pathname==='/api/leaderboard'&&req.method==='GET')return json(res,200,{players:sql.top.all()});
 if(pathname==='/api/me'&&req.method==='GET'){
  const row=sessionPlayer(req);return json(res,200,{player:row?details(online.get(row.id)||createPlayer(row)):null});
 }
 if(pathname.startsWith('/api/')&&req.method==='POST'){
  if(!originOk(req))return json(res,403,{error:'Invalid request origin.'});
  if(!rateLimit(req,'post',90))return json(res,429,{error:'Slow down for a moment.'});
  let body;try{body=await readBody(req);}catch(e){return json(res,400,{error:e.message});}
  if(pathname==='/api/logout'){const tok=cookie(req).lv_session;if(tok)sql.sessRemove.run(tokenHash(tok));res.setHeader('Set-Cookie',`lv_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0${IS_PROD?'; Secure':''}`);return json(res,200,{ok:true});}
  if(pathname==='/api/register'||pathname==='/api/demo'){
   const demo=pathname==='/api/demo';if(!rateLimit(req,demo?'demo':'register',demo?4:6,3600000))return json(res,429,{error:'Too many attempts. Try again later.'});
   const username=demo?'Traveler'+crypto.randomBytes(4).toString('hex'):String(body.username||'').trim();
   const password=demo?crypto.randomBytes(24).toString('hex'):String(body.password||'');
   const klass=classNames.includes(body.class)?body.class:'Scout';
   const palette=Number.isInteger(body.palette)?clamp(body.palette,0,5):0;
   if(body.age13!==true)return json(res,400,{error:'Accounts are currently for players age 13+. Under-13 accounts are not supported.'});
   if(!safeUsername(username))return json(res,400,{error:'Please choose another traveler name.'});
   if(!/^[a-zA-Z0-9_]{3,16}$/.test(username))return json(res,400,{error:'Username must be 3–16 letters, numbers, or underscores.'});
   if(password.length<10||password.length>128)return json(res,400,{error:'Password must be 10–128 characters.'});
   if(sql.byName.get(username))return json(res,409,{error:'That traveler name is already taken.'});
   const salt=crypto.randomBytes(24).toString('hex');const inventory={stick:1,'fizzy-pop':3};const equipped={weapon:'stick'};
   const t=now();let id;
   try{id=Number(sql.insert.run(username,passwordHash(password,salt),salt,klass,palette,JSON.stringify(inventory),JSON.stringify(equipped),t,t).lastInsertRowid);}catch{return json(res,409,{error:'Name unavailable.'});}
   db.prepare('UPDATE players SET is_demo=?,hp=?,focus=? WHERE id=?').run(+demo,100+(klass==='Guardian'?25:0),50+(klass==='Dreamer'?25:0),id);
   newSession(res,id);return json(res,200,{ok:true,username,demo});
  }
  if(pathname==='/api/login'){
   if(!rateLimit(req,'login',15,60000))return json(res,429,{error:'Too many login attempts. Try again soon.'});
   const username=String(body.username||'').trim();const pass=String(body.password||'');const row=sql.byName.get(username);
   const fallback='0'.repeat(128);const probe=passwordHash(pass.slice(0,128),row?.salt||'00'.repeat(24));
   if(!row||!compare(probe,row.password_hash||fallback))return json(res,401,{error:'Wrong username or password.'});
   if(row.banned_until>now())return json(res,403,{error:'This account is suspended. Contact the site administrator.'});
   newSession(res,row.id);return json(res,200,{ok:true,username:row.username});
  }
  return json(res,404,{error:'Unknown API route.'});
 }
 if(req.method!=='GET')return json(res,405,{error:'Method not allowed'});
 const PUBLIC=path.join(__dirname,'public');let local;
 try{const decoded=decodeURIComponent(pathname);local=path.resolve(PUBLIC,'.'+(decoded==='/'?'/index.html':decoded));}catch{return json(res,400,{error:'Bad path'});}
 if(!local.startsWith(PUBLIC+path.sep))return json(res,403,{error:'Forbidden'});
 fs.readFile(local,(err,data)=>{if(err)return json(res,404,{error:'Not found'});res.writeHead(200,{'Content-Type':mime[path.extname(local)]||'application/octet-stream','Cache-Control':path.extname(local)==='.html'?'no-store':'public, max-age=3600'});res.end(data);});
}
const server=http.createServer((req,res)=>{handler(req,res).catch(e=>{console.error('HTTP',e);if(!res.headersSent)json(res,500,{error:'Server error'});});});
// Minimal, dependency-free RFC 6455 WebSocket implementation. Rejects fragmentation,
// unmasked frames and large payloads; enough for browser text frames/pings.
function wsAccept(req,socket,head){
 if(!originOk(req)||req.url!=='/ws'||req.headers.upgrade?.toLowerCase()!=='websocket'||req.headers['sec-websocket-version']!=='13'||!/^[A-Za-z0-9+/]{22}==$/.test(req.headers['sec-websocket-key']||'')){socket.destroy();return;}
 const row=sessionPlayer(req);if(!row||row.banned_until>now()||wsClients.size>=80){socket.write('HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n');socket.destroy();return;}
 const accept=crypto.createHash('sha1').update(req.headers['sec-websocket-key']+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
 socket.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: '+accept+'\r\n\r\n');
 let p=online.get(row.id);if(!p){p=createPlayer(row);online.set(p.id,p);}if(p.sockets.size>=2){socket.destroy();return;}
 const ws={socket,closed:false,buf:Buffer.alloc(0),player:p,lastChat:0,lastAction:0,chatStrikes:0,lastMessage:'',repeatCount:0,lastTraffic:now(),perSecond:0,windowAt:now()};wsClients.add(ws);p.sockets.add(ws);
 send(ws,{type:'welcome',player:details(p),online:online.size});notify(p,`Welcome ${p.name}! Explore, chat, and find Uncle Pip.`);
 function close(){if(ws.closed)return;ws.closed=true;wsClients.delete(ws);p.sockets.delete(ws);if(!p.sockets.size){if(p.zone!=='overworld')leaveRift(p);leaveParty(p);save(p);online.delete(p.id);if(p.demo)db.prepare('DELETE FROM players WHERE id=?').run(p.id);}}
 socket.on('close',close);socket.on('error',close);
 function parse(b){let i=0;while(b.length-i>=2){const start=i,byte=b[i],opcode=byte&15,masked=(b[i+1]&128)!==0,fin=(byte&128)!==0;let len=b[i+1]&127;i+=2;
  if(len===126){if(b.length-i<2){i=start;break;}len=b.readUInt16BE(i);i+=2;}
  if(len===127){if(b.length-i<8){i=start;break;}const high=b.readUInt32BE(i);const low=b.readUInt32BE(i+4);len=high*4294967296+low;i+=8;}
  if(!masked||len>8192||!fin){socket.destroy();return Buffer.alloc(0);}
  if(b.length-i<4+len){i=start;break;}const mask=b.subarray(i,i+4);i+=4;const data=Buffer.from(b.subarray(i,i+len));i+=len;
  for(let z=0;z<data.length;z++)data[z]^=mask[z%4];
  if(opcode===8){socket.end();return Buffer.alloc(0);}
  if(opcode===9){const hdr=Buffer.from([0x8a,data.length]);socket.write(Buffer.concat([hdr,data]));continue;}
  if(opcode!==1){if(opcode!==10)socket.destroy();continue;}
  let msg;try{msg=JSON.parse(data.toString('utf8'));}catch{continue;}if(!msg||typeof msg!=='object')continue;
  handleMessage(ws,msg);
 }return b.subarray(i);}
 socket.on('data',chunk=>{ws.buf=Buffer.concat([ws.buf,chunk]);if(ws.buf.length>32768)return socket.destroy();ws.buf=parse(ws.buf);});if(head?.length)ws.buf=parse(head);
}
function handleMessage(ws,msg){const p=ws.player;const t=now();if(t-ws.windowAt>1000){ws.windowAt=t;ws.perSecond=0;}if(++ws.perSecond>40){ws.socket.destroy();return;}if(!msg||Array.isArray(msg))return;
 if(msg.type==='input'){
  const d=msg.keys&&typeof msg.keys==='object'?msg.keys:{};p.input={up:d.up===true,down:d.down===true,left:d.left===true,right:d.right===true};return;
 }
 if(msg.type==='action'&&now()-ws.lastAction>75){ws.lastAction=now();playerAction(p,msg);return;}
 if(msg.type==='chat'){if(p.demo)return notify(p,'Quick chat is for permanent accounts.');if(now()-ws.lastChat<1800)return notify(p,'Please slow down.');ws.lastChat=now();if(sql.banGet.get(p.id).silenced_until>now())return notify(p,'Your chat has been temporarily muted.');let text;if(msg.quick===true){text=QUICK_CHAT[Number(msg.index)];if(!text)return;}else{if(!TEXT_CHAT_ENABLED)return notify(p,'For safety, only pre-written quick chat is available.');const check=moderateMessage(msg.text);if(!check.ok){if(++ws.chatStrikes>=4){db.prepare('UPDATE players SET silenced_until=? WHERE id=?').run(now()+600000,p.id);notify(p,'Chat muted for 10 minutes after repeated blocked messages.');}else notify(p,check.reason);return;}text=check.text;}
 const stripped=text.toLowerCase().replace(/[^a-z0-9]/g,'');if(stripped===ws.lastMessage){ws.repeatCount++;if(ws.repeatCount>=3)return notify(p,'Please avoid repeating the same message.');}else ws.repeatCount=0;ws.lastMessage=stripped;
 for(const client of wsClients)if(canSee(client.player,p)&&distance(client.player,p)<23)send(client,{type:'chat',name:p.name,id:p.id,text});return;}
}
server.on('upgrade',wsAccept);
const FRAME=50;
function tick(){const delta=FRAME/1000,time=now();
 for(const p of online.values()){
  if(p.hp<=0)continue;
  const ix=(p.input.right?1:0)-(p.input.left?1:0),iy=(p.input.down?1:0)-(p.input.up?1:0);const norm=Math.hypot(ix,iy)||1;
  const speed=(p.class==='Scout'?4.35:3.85)*delta;
  const nx=p.x+ix/norm*speed,ny=p.y+iy/norm*speed;
  const scene=sceneFor(p);const walkable=scene?(x,y)=>riftSafe(scene,x,y):world.safe;const isSafe=(x,y)=>walkable(x-.21,y-.19)&&walkable(x+.21,y-.19)&&walkable(x-.21,y+.19)&&walkable(x+.21,y+.19);
  if(ix||iy){if(isSafe(nx,p.y))p.x=nx;if(isSafe(p.x,ny))p.y=ny;p.dirty=true;p.state='walk';}else p.state='idle';if(p.pvp&&!inArena(p)){p.pvp=false;notify(p,'Left the arena. PvP automatically disabled.');sendSelf(p);}
  if(p.focus<maxFocus(p))p.focus=Math.min(maxFocus(p),p.focus+.16);
  if(p.zone==='overworld'&&Math.hypot(p.x-START.x,p.y-START.y)<8&&p.hp<maxHp(p)&&time-p.healTime>1100){p.hp++;p.healTime=time;p.dirty=true;}
 }
 relayTick(time);raceTick(time);
 for(const inst of instances.values())if(inst.kind==='survival'&&!inst.completed){const p=online.get([...inst.members][0]);if(!p||p.zone!==inst.id){instances.delete(inst.id);continue;}if(time-inst.createdAt>=SURVIVAL_LENGTH_MS){finishSurvival(p);continue;}if(!inst.enemies.some(e=>e.alive)&&time>inst.nextWaveAt)spawnSurvivalWave(inst);if(time-inst.autoAt>460){inst.autoAt=time;const nearest=inst.enemies.filter(e=>e.alive).sort((a,b)=>distance(a,p)-distance(b,p))[0];if(nearest&&distance(nearest,p)<9){const damage=16+inst.wave*3;nearest.contributors.set(p.id,(nearest.contributors.get(p.id)||0)+damage);nearest.hp-=damage;if(nearest.hp<=0)killMob(nearest,p);for(const ws of p.sockets)send(ws,{type:'effect',kind:'burst',x:nearest.x,y:nearest.y,damage});}}}
 for(const e of [...enemies,...[...instances.values()].flatMap(i=>i.enemies)]){
  const dungeon=e.id.includes(':')?instances.get(e.id.split(':')[0]):null;if(dungeon?.completed)continue;
  if(!e.alive){if(time>=e.respawnAt){e.alive=true;e.hp=mobDefs[e.kind].maxHp;e.contributors.clear();e.x=e.ox;e.y=e.oy;}continue;}
  const def=mobDefs[e.kind];let target=null,near=Infinity;
  for(const p of online.values()){if(p.zone!==(dungeon?.id||'overworld'))continue;let d=distance(e,p);if(p.hp>0&&d<def.range&&d<near){target=p;near=d;}}
  let dx=0,dy=0;
  if(target){if(near>.75){dx=(target.x-e.x)/Math.max(.001,near);dy=(target.y-e.y)/Math.max(.001,near);}
   if(near<1.12&&time-e.lastAttack>1500&&time>target.respawnImmune){e.lastAttack=time;const dealt=Math.max(1,(e.attack||def.atk)-defense(target)+rnd(-1,2));target.hp=Math.max(0,target.hp-dealt);target.dirty=true;for(const ws of target.sockets)send(ws,{type:'effect',kind:'hurt',x:target.x,y:target.y,damage:dealt});if(target.hp<=0){if(dungeon?.kind==='survival'){finishSurvival(target,'knockout');continue;}target.hp=maxHp(target);target.focus=maxFocus(target);if(dungeon){target.x=dungeon.scene.start.x;target.y=dungeon.scene.start.y;}else{target.x=START.x;target.y=START.y;}target.respawnImmune=time+4000;notify(target,'Your radio rewound! No items or stardust lost.','info');}sendSelf(target);}
  }else{
   if(time>e.roamUntil){e.dir=random()*Math.PI*2;e.roamUntil=time+rnd(1400,3600);}dx=Math.cos(e.dir)*.4;dy=Math.sin(e.dir)*.4;
  }
  const speed=(dungeon?.kind==='survival'?Math.min(.92,def.speed*.75):def.speed)*delta;
  const eSafe=dungeon?(x,y)=>riftSafe(dungeon.scene,x,y):world.safe;
  if(eSafe(e.x+dx*speed,e.y))e.x+=dx*speed;
  if(eSafe(e.x,e.y+dy*speed))e.y+=dy*speed;
  if(dungeon?.kind!=='survival'&&distance(e,{x:e.ox,y:e.oy})>8){e.x=e.ox;e.y=e.oy;}
 }
}
setInterval(tick,FRAME);
setInterval(()=>{
 if(!wsClients.size)return;
 for(const ws of wsClients){const p=ws.player;const ps=Array.from(online.values()).filter(v=>canSee(p,v)).map(userSafe);const es=(p.zone==='overworld'?enemies:instances.get(p.zone)?.enemies||[]).map(mobView);send(ws,{type:'snapshot',players:ps,enemies:es,serverTime:now(),survival:instances.get(p.zone)?.kind==='survival'?{wave:instances.get(p.zone).wave,kills:instances.get(p.zone).kills,remaining:Math.max(0,Math.ceil((SURVIVAL_LENGTH_MS-(now()-instances.get(p.zone).createdAt))/1000))}:null});}
},160);
setInterval(()=>{for(const p of online.values()){if(sql.banGet.get(p.id).banned_until>now())for(const ws of p.sockets)ws.socket.destroy();}},5000);
setInterval(()=>{for(const p of online.values())if(p.dirty)save(p);db.prepare('DELETE FROM sessions WHERE expires_at<?').run(now());db.prepare('DELETE FROM players WHERE is_demo=1 AND created_at<?').run(now()-172800000);for(const [k,v] of recent)if(now()>v.until)recent.delete(k);},15000);
for(const sig of ['SIGTERM','SIGINT'])process.on(sig,()=>{console.log('Saving world...');for(const p of online.values())save(p);db.close();server.close(()=>process.exit(0));setTimeout(()=>process.exit(0),1000).unref();});
server.listen(PORT,HOST,()=>console.log(`Signal 199X listening on http://${HOST}:${PORT} (${IS_PROD?'production':'development'})`));
