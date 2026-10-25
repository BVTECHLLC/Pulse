// Conservative layered moderation. No filter can guarantee safety; free text off by default.
export const QUICK_CHAT=Object.freeze([
 'Hi there! 👋','Want to team up?','Nice work! ⭐','Need a hand?','Thanks, friend!','On my way!','Boss ahead!','Let’s explore!','Good game!','Taking a break.','Welcome!','Great teamwork!'
]);
export const TEXT_CHAT_ENABLED=process.env.ENABLE_TEXT_CHAT==='true';
const harmful=[
 /f+[\W_]*u+[\W_]*c+[\W_]*k+/i, /s+[\W_]*h+[\W_]*i+[\W_]*t+/i,
 /b+[\W_]*i+[\W_]*t+[\W_]*c+[\W_]*h+/i, /c+[\W_]*u+[\W_]*n+[\W_]*t+/i,
 /n+[\W_]*[i1!]+[\W_]*g+[\W_]*g?[\W_]*[ae3]+[\W_]*r?/i,
 /f+[\W_]*a+[\W_]*g+[\W_]*g?[\W_]*o?[\W_]*t+/i,
 /r+[\W_]*e+[\W_]*t+[\W_]*a+[\W_]*r+[\W_]*d+/i,
 /k+[\W_]*[i1!]+[\W_]*l+[\W_]*l+[\W_]*\s*(?:y+[\W_]*o+[\W_]*u+|u+|y+[\W_]*r+)/i,
 /(?:https?:\/\/|www\.|\.com\b|\.gg\b|discord|telegram|snapchat|instagram|\b@\w+)/i,
 /\b(?:address|phone number|where do you live|what school|send pics|send photos|meet me irl)\b/i,
 /\b(?:sex|porn|nudes|suicide|self harm)\b/i,
 /\b(?:idiot|moron|stupid|hate you|loser|dumbass)\b/i
];
const map=Object.freeze({'0':'o','1':'i','3':'e','4':'a','5':'s','7':'t','@':'a','$':'s','!':'i'});
export function normalizeMessage(input){return String(input||'').normalize('NFKC').replace(/[\u200B-\u200F\uFEFF]/g,'').replace(/[013457@$!]/g,c=>map[c]||c).replace(/(.)\1{3,}/gu,'$1$1').slice(0,240);}
export function safeUsername(name){const n=normalizeMessage(name).toLowerCase().replace(/[^a-z]/g,'');if(n.startsWith('admin')||n.startsWith('moderator')||n.startsWith('support')||n.startsWith('bvtech')||n.startsWith('signal'))return false;return n.length>0&&!/f[v]+ck|sh[i1]t|n[i1]gg?[a4e3]r?|b[i1]tch/i.test(n)&&!harmful.some(rx=>rx.test(n));}
export function moderateMessage(input){const raw=String(input||'').normalize('NFKC').trim();if(!raw||raw.length>160)return {ok:false,reason:'Message length not allowed.'};
 const n=normalizeMessage(raw);const collapsed=n.replace(/[\W_]/g,'');
 if(harmful.some(rx=>rx.test(n)||rx.test(collapsed)))return {ok:false,reason:'Message blocked by the safety filter.'};
 if(/\d{3}[\s().-]*\d{3}[\s().-]*\d{4}/.test(raw)||/\b[\w.%+-]+@[\w.-]+\.[a-z]{2,}\b/i.test(raw))return {ok:false,reason:'Do not share personal contact information.'};
 if(/(.)\1{7,}/u.test(n)||/[A-Z]{17,}/.test(raw)||n.split(/\s+/).length>35)return {ok:false,reason:'Please avoid spam.'};
 return {ok:true,text:raw.replace(/[\u0000-\u001f\u007f]/g,'')};
}
