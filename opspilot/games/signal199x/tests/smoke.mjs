import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import net from 'node:net';
import os from 'node:os';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';

const DIR=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function portFree(){return new Promise((resolve,reject)=>{const srv=net.createServer();srv.listen(0,'127.0.0.1',()=>{const p=srv.address().port;srv.close(()=>resolve(p));});srv.on('error',reject);});}
async function liveServer(port,folder){let child=spawn(process.execPath,['server.mjs'],{cwd:DIR,env:{...process.env,PORT:String(port),HOST:'127.0.0.1',DATA_DIR:folder},stdio:'ignore'});for(let i=0;i<55;i++){if(child.exitCode!==null)throw Error('Server exited prematurely');try{const r=await fetch(`http://127.0.0.1:${port}/health`);if(r.ok)return child;}catch{}await delay(100);}throw Error('Timed out starting server');}
function wsConnect(port,cookie){return new Promise((resolve,reject)=>{
 const sock=net.connect({port,host:'127.0.0.1'}),key=crypto.randomBytes(16).toString('base64');
 let handshake=false,buf=Buffer.alloc(0),queue=[],waiters=[];
 const api={
  async recv(){if(queue.length)return queue.shift();return new Promise((r,j)=>{const timer=setTimeout(()=>j(Error('Timeout waiting for WebSocket frame')),6000);waiters.push(m=>{clearTimeout(timer);r(m);});});},
  send(msg){const data=Buffer.from(JSON.stringify(msg)),mask=crypto.randomBytes(4);let header;
   if(data.length<126)header=Buffer.from([0x81,0x80|data.length]);else header=Buffer.from([0x81,0xfe,data.length>>8,data.length&255]);
   const masked=Buffer.from(data);for(let i=0;i<masked.length;i++)masked[i]^=mask[i%4];sock.write(Buffer.concat([header,mask,masked]));},
  close(){sock.end();}
 };
 sock.on('error',reject);
 sock.on('connect',()=>sock.write(['GET /ws HTTP/1.1','Host: 127.0.0.1:'+port,'Upgrade: websocket','Connection: Upgrade','Sec-WebSocket-Key: '+key,'Sec-WebSocket-Version: 13','Origin: http://127.0.0.1:'+port,'Cookie: lv_session='+cookie,'\r\n'].join('\r\n')));
 sock.on('data',chunk=>{
  buf=Buffer.concat([buf,chunk]);
  if(!handshake){const index=buf.indexOf('\r\n\r\n');if(index<0)return;const response=buf.subarray(0,index).toString();if(!response.includes('101 Switching Protocols')){reject(Error('WS handshake refused '+response));return;}handshake=true;buf=buf.subarray(index+4);resolve(api);}
  while(buf.length>=2){const code=buf[0]&15;let len=buf[1]&127,offset=2;
   if(len===126){if(buf.length<4)break;len=buf.readUInt16BE(2);offset=4;}
   else if(len===127){if(buf.length<10)break;len=buf.readUInt32BE(6);offset=10;}
   if(buf.length<offset+len)break;const payload=buf.subarray(offset,offset+len);buf=buf.subarray(offset+len);
   if(code===1){const message=JSON.parse(payload.toString());if(waiters.length)waiters.shift()(message);else queue.push(message);}
  }
 });
 });}

test('account, authoritative movement, inventory and persistence smoke test', {timeout:25000}, async t=>{
 const port=await portFree(),folder=fs.mkdtempSync(path.join(os.tmpdir(),'signal199x-smoke-'));
 let child=await liveServer(port,folder);
 t.after(async()=>{child.kill('SIGTERM');await delay(250);fs.rmSync(folder,{recursive:true,force:true});});
 const base=`http://127.0.0.1:${port}`;
 const get=async(endpoint,cookie)=>{const r=await fetch(base+endpoint,{headers:cookie?{Cookie:'lv_session='+cookie}:{}});return {r,data:await r.json()};};
 const post=async(endpoint,payload,cookie)=>{const r=await fetch(base+endpoint,{method:'POST',headers:{'Content-Type':'application/json',...(cookie?{Cookie:'lv_session='+cookie}:{})},body:JSON.stringify(payload)});return {r,data:await r.json()};};
 const w=await get('/api/world');assert.equal(w.data.width,132);assert.equal(w.data.places.length,6);assert.equal(w.data.chests.length,10);
 assert.equal((await get('/api/me')).data.player,null);
 assert.equal((await post('/api/register',{username:'Friend123',password:'short'})).r.status,400);
 const signup=await post('/api/register',{username:'Friend123',password:'AveryStrongPassphrase1234',class:'Scout',palette:1,age13:true});assert.equal(signup.r.status,200);
 const cookie=signup.r.headers.get('set-cookie')?.match(/lv_session=([0-9a-f]{64})/)?.[1];assert.ok(cookie);
 assert.equal((await get('/api/me',cookie)).data.player.name,'Friend123');
 assert.equal((await post('/api/login',{username:'Friend123',password:'incorrectpassword'})).r.status,401);
 const ws=await wsConnect(port,cookie);
 assert.equal((await ws.recv()).type,'welcome');
 const x0=(await get('/api/me',cookie)).data.player.x;
 ws.send({type:'input',keys:{right:true}});await delay(720);ws.send({type:'input',keys:{}});
 await delay(300);
 ws.send({type:'action',action:'addGold',gold:99999});
 ws.send({type:'input',keys:{x:1000,y:1000,gold:99999}});
 await delay(150);
 let mine=(await get('/api/me',cookie)).data.player;
 assert.ok(mine.x>x0+.9,`Movement did not advance: ${mine.x} <= ${x0}`);
 assert.ok(mine.x<40,`Client attempted to set position: ${mine.x}`);
 assert.equal(mine.gold,75);
 assert.equal(mine.level,1);
 assert.deepEqual(mine.inventory,{stick:1,'fizzy-pop':3});
 ws.close();await delay(300);
 // WS disconnect flushes character state to SQLite.
 mine=(await get('/api/me',cookie)).data.player;assert.ok(mine.x>x0+.9);
 assert.equal((await post('/api/logout',{},cookie)).r.status,200);
 assert.equal((await get('/api/me',cookie)).data.player,null);
 const login=await post('/api/login',{username:'Friend123',password:'AveryStrongPassphrase1234'});
 assert.equal(login.r.status,200);
 const cookie2=login.r.headers.get('set-cookie').match(/lv_session=([0-9a-f]{64})/)[1];
 assert.ok((await get('/api/me',cookie2)).data.player.x>x0+.9);
});

import {DatabaseSync} from 'node:sqlite';
import {moderateMessage,safeUsername,QUICK_CHAT} from '../moderation.mjs';
async function recvKind(ws,kind,limit=5000){const start=Date.now();while(Date.now()-start<limit){const m=await ws.recv();if(m?.type===kind)return m;}throw Error('Did not receive '+kind);}

test('co-op invitations, isolated rift, quick-chat policy, reporting and houses', {timeout:28000}, async t=>{
 const port=await portFree(),folder=fs.mkdtempSync(path.join(os.tmpdir(),'signal199x-feature-'));
 const child=await liveServer(port,folder);
 const users=[];t.after(async()=>{for(const w of users)w.close();child.kill('SIGTERM');await delay(400);fs.rmSync(folder,{recursive:true,force:true});});
 const base=`http://127.0.0.1:${port}`;
 const post=async(endpoint,payload)=>{const res=await fetch(base+endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});return {status:res.status,data:await res.json(),cookie:res.headers.get('set-cookie')?.match(/lv_session=([0-9a-f]{64})/)?.[1]};};
 assert.equal((await post('/api/demo',{class:'Scout'})).status,400,'Guest sessions must also require age acknowledgement');
 assert.equal((await post('/api/register',{username:'FvckHate',password:'long-enough-passphrase',age13:true})).status,400,'Restricted username should not be allowed');
 const first=await post('/api/register',{username:'BuddyOne',password:'ThisIsALongPassphrase2026!',age13:true});
 const second=await post('/api/register',{username:'BuddyTwo',password:'ThisIsALongPassphrase2026!',age13:true});
 const third=await post('/api/register',{username:'HouseMate',password:'ThisIsALongPassphrase2026!',age13:true});
 assert.equal(first.status,200);assert.equal(second.status,200);assert.equal(third.status,200);
 const db=new DatabaseSync(path.join(folder,'game.sqlite'));
 db.prepare('UPDATE players SET x=?, y=? WHERE username IN (?,?)').run(54.5,33.5,'BuddyOne','BuddyTwo');
 db.prepare('UPDATE players SET x=?,y=?,gold=? WHERE username=?').run(107.5,73.5,650,'HouseMate');
 db.close();
 const a=await wsConnect(port,first.cookie),b=await wsConnect(port,second.cookie),h=await wsConnect(port,third.cookie);users.push(a,b,h);
 assert.equal((await recvKind(a,'welcome')).player.name,'BuddyOne');await recvKind(b,'welcome');await recvKind(h,'welcome');await recvKind(a,'toast');
 a.send({type:'chat',text:'Here is a bad link www.spam.example'});const t1=await recvKind(a,'toast');assert.match(t1.msg,/quick|safety|pre-written/i);
 a.send({type:'action',action:'party-invite',id:'BuddyTwo'});const invite=await recvKind(b,'invite');assert.equal(invite.name,'BuddyOne');
 b.send({type:'action',action:'party-accept'});await delay(300);
 const meResponse=await fetch(base+'/api/me',{headers:{Cookie:'lv_session='+first.cookie}});const self=await meResponse.json();assert.equal(self.player.party.members.length,2);
 a.send({type:'action',action:'report',id:'BuddyTwo',reason:'spam'});await delay(170);
 const rdb=new DatabaseSync(path.join(folder,'game.sqlite'));assert.equal(rdb.prepare('SELECT COUNT(*) AS c FROM reports').get().c,1);rdb.close();
 a.send({type:'action',action:'dungeon-start',id:'rain'});const sceneA=await recvKind(a,'scene'),sceneB=await recvKind(b,'scene');assert.equal(sceneA.world.sceneType,'dungeon');assert.equal(sceneA.zone,sceneB.zone);await delay(150);
 a.send({type:'action',action:'dungeon-exit'});const exit=await recvKind(a,'scene');assert.equal(exit.zone,'overworld');
 h.send({type:'action',action:'home-buy',id:'2'});await delay(250);
 let r=await fetch(base+'/api/me',{headers:{Cookie:'lv_session='+third.cookie}});let home=(await r.json()).player;assert.equal(home.home.plot,2);assert.equal(home.gold,200);
 h.send({type:'action',action:'home-theme',id:'neon'});await delay(280);
 r=await fetch(base+'/api/me',{headers:{Cookie:'lv_session='+third.cookie}});home=(await r.json()).player;assert.equal(home.home.theme,'neon');assert.equal(home.gold,165);
 const ddb=new DatabaseSync(path.join(folder,'game.sqlite'));assert.equal(ddb.prepare('SELECT COUNT(*) AS c FROM homes').get().c,1);ddb.close();
});

test('message safety filter rejects obfuscated vulgarity, links and private info',()=>{
 assert.equal(safeUsername('FvckHate'),false);
 assert.equal(safeUsername('Moderator_Official'),false);
 assert.equal(safeUsername('StarBreeze'),true);
 assert.equal(moderateMessage('f_u_c_k').ok,false);
 assert.equal(moderateMessage('https://somewhere.com').ok,false);
 assert.equal(moderateMessage('Call me at 555-123-4567').ok,false);
 assert.equal(moderateMessage('Hi team, great work!').ok,true);
 assert.ok(QUICK_CHAT.length>=10);
});

test('v3 Static Storm stays server-authoritative and Duo Jam requires two real players', {timeout:26000}, async t=>{
 const port=await portFree(),folder=fs.mkdtempSync(path.join(os.tmpdir(),'signal199x-v3-'));const child=await liveServer(port,folder),users=[];
 t.after(async()=>{users.forEach(x=>x.close());child.kill('SIGTERM');await delay(350);fs.rmSync(folder,{recursive:true,force:true});});
 const base=`http://127.0.0.1:${port}`;
 async function register(name){const r=await fetch(base+'/api/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:name,password:'StrongPasswordVerySecure2026!',age13:true})});assert.equal(r.status,200);return r.headers.get('set-cookie').match(/lv_session=([a-f0-9]+)/)[1];}
 const c1=await register('StarStorm3'),c2=await register('StarStorm4');
 const db=new DatabaseSync(path.join(folder,'game.sqlite'));db.prepare('UPDATE players SET x=104.5,y=26.5 WHERE username IN (?,?)').run('StarStorm3','StarStorm4');db.close();
 const a=await wsConnect(port,c1),b=await wsConnect(port,c2);users.push(a,b);await recvKind(a,'welcome');await recvKind(b,'welcome');
 a.send({type:'action',action:'jam'});await recvKind(a,'toast');await delay(100);b.send({type:'action',action:'jam'});await recvKind(b,'toast');
 await delay(170);
 const check=new DatabaseSync(path.join(folder,'game.sqlite'));
 assert.equal(check.prepare('SELECT count(*) AS count FROM activity_records WHERE jam_reward_at>0').get().count,2);
 const goldBefore=check.prepare('SELECT gold FROM players WHERE username=?').get('StarStorm3').gold;
 check.close();
 // Start a private survival room; no browser may award its own score or pick a wave.
 a.send({type:'action',action:'survival-start'});const scene=await recvKind(a,'scene');assert.equal(scene.world.sceneType,'survival');assert.notEqual(scene.zone,'overworld');
 await delay(2600);
 const state=await fetch(base+'/api/me',{headers:{Cookie:'lv_session='+c1}}).then(r=>r.json());assert.ok(state.player.survival?.wave>=1);
 a.send({type:'action',action:'survival-exit'});const result=await recvKind(a,'survival-result');assert.ok(result.wave>=1);assert.ok(result.reward>=0);
 await recvKind(a,'scene');await delay(180);
 const after=await fetch(base+'/api/me',{headers:{Cookie:'lv_session='+c1}}).then(r=>r.json());assert.equal(after.player.zone,'overworld');assert.ok(after.player.gold>=goldBefore);
 a.send({type:'action',action:'survival-start'});await recvKind(a,'toast'); // arcade location check prevents remote teleport into another game
 const verify=new DatabaseSync(path.join(folder,'game.sqlite'));
 assert.equal(verify.prepare("SELECT count(*) AS c FROM activity_records WHERE survival_prize_day!=''").get().c,1);
 verify.close();
});
