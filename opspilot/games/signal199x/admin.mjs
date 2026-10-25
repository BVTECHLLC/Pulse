#!/usr/bin/env node
// Offline operator tool. NEVER expose it through an HTTP endpoint.
import {DatabaseSync} from 'node:sqlite';
import path from 'node:path';
const db=new DatabaseSync(path.join(process.env.DATA_DIR||path.join(import.meta.dirname,'data'),'game.sqlite'));
const [command,...argv]=process.argv.slice(2);const help='Usage: node admin.mjs reports | players | mute USER MINUTES REASON | ban USER HOURS REASON | unmute USER | unban USER | close REPORT_ID | delete USER';
const byName=db.prepare('SELECT id,username,banned_until,silenced_until FROM players WHERE username=? COLLATE NOCASE');
function audit(id,action,reason){db.prepare('INSERT INTO moderation_actions(target_id,action,reason,at) VALUES(?,?,?,?)').run(id,action,reason,Date.now());}
try{
 if(command==='reports')console.table(db.prepare("SELECT r.id,p1.username AS reporter,p2.username AS accused,r.reason,datetime(r.created_at/1000,'unixepoch') AS when_utc,r.status FROM reports r JOIN players p1 ON p1.id=r.reporter_id JOIN players p2 ON p2.id=r.target_id ORDER BY r.created_at DESC LIMIT 100").all());
 else if(command==='players')console.table(db.prepare('SELECT username,level,duel_wins,dungeon_clears,datetime(created_at/1000,\'unixepoch\') AS joined_utc FROM players WHERE is_demo=0 ORDER BY created_at DESC LIMIT 100').all());
 else if(['mute','ban'].includes(command)){
  const [name,lengthStr,...reasons]=argv;const target=byName.get(name),length=Number(lengthStr),reason=reasons.join(' ').trim();if(!target||!Number.isInteger(length)||length<1||length>43200||reason.length<5)throw Error('Valid player, duration and reason (5+ characters) required.');
  const key=command==='mute'?'silenced_until':'banned_until',factor=command==='mute'?60000:3600000;db.prepare(`UPDATE players SET ${key}=? WHERE id=?`).run(Date.now()+length*factor,target.id);audit(target.id,command,reason);console.log(command.toUpperCase(),'applied to',target.username);
 }else if(['unmute','unban'].includes(command)){
  const target=byName.get(argv[0]);if(!target)throw Error('Player not found.');const key=command==='unmute'?'silenced_until':'banned_until';db.prepare(`UPDATE players SET ${key}=0 WHERE id=?`).run(target.id);audit(target.id,command,'Operator action');console.log(command,target.username);
 }else if(command==='close'){
  const id=Number(argv[0]);if(!Number.isInteger(id)||id<1)throw Error('Report ID must be a positive number.');db.prepare("UPDATE reports SET status='closed' WHERE id=?").run(id);console.log('Closed report',id);
 }else if(command==='delete'){
  const target=byName.get(argv[0]);if(!target)throw Error('Player not found.');db.exec('BEGIN');try{db.prepare('DELETE FROM reports WHERE reporter_id=? OR target_id=?').run(target.id,target.id);db.prepare('DELETE FROM blocks WHERE owner_id=? OR target_id=?').run(target.id,target.id);db.prepare('DELETE FROM moderation_actions WHERE target_id=?').run(target.id);db.prepare('DELETE FROM players WHERE id=?').run(target.id);db.exec('COMMIT');console.log('Deleted account data for',target.username);}catch(e){db.exec('ROLLBACK');throw e;}
 }else console.log(help);
}catch(e){console.error(e.message,'\n',help);process.exitCode=1;}finally{db.close();}
