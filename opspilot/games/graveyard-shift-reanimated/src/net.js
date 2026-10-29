// Serverless P2P co-op for Graveyard Shift.
// No server, no broker, no CSP changes: two players exchange one connection
// code by hand (copy/paste or a share link). WebRTC's data channel then carries
// the co-op traffic directly, browser to browser. STUN helps across networks;
// on the same Wi-Fi it connects with no external help at all.
const ICE = {iceServers:[
  {urls:'stun:stun.l.google.com:19302'},
  {urls:'stun:stun1.l.google.com:19302'},
  {urls:'stun:stun2.l.google.com:19302'},
]};

// Wait until ICE candidate gathering finishes so the single code we hand off
// already contains every candidate (no trickle signaling needed).
function waitIce(pc){
  return new Promise(res=>{
    if(pc.iceGatheringState==='complete')return res();
    const check=()=>{if(pc.iceGatheringState==='complete'){pc.removeEventListener('icegatheringstatechange',check);res();}};
    pc.addEventListener('icegatheringstatechange',check);
    setTimeout(res,3000); // fall back after 3s even if a candidate is slow
  });
}
const enc = o => btoa(unescape(encodeURIComponent(JSON.stringify(o))));
const dec = s => JSON.parse(decodeURIComponent(escape(atob(String(s).trim()))));

function wire(ch,pc,h){
  ch.onopen = ()=>h.onOpen?.();
  ch.onclose = ()=>h.onClose?.();
  ch.onmessage = e=>{try{h.onData?.(JSON.parse(e.data));}catch{}};
  pc.onconnectionstatechange = ()=>{if(['failed','disconnected','closed'].includes(pc.connectionState))h.onClose?.();};
}

// HOST: create an offer code, then accept the guest's answer code.
export function createHost(h){
  const pc = new RTCPeerConnection(ICE);
  const ch = pc.createDataChannel('gs',{ordered:true});
  wire(ch,pc,h);
  const code = (async()=>{const o=await pc.createOffer();await pc.setLocalDescription(o);await waitIce(pc);return enc(pc.localDescription);})();
  return {
    code,
    accept: async answerCode => { await pc.setRemoteDescription(dec(answerCode)); },
    send: o => { if(ch.readyState==='open') ch.send(JSON.stringify(o)); },
    close: ()=>{try{pc.close();}catch{}},
  };
}

// GUEST: take the host's offer code, produce an answer code to send back.
export function createGuest(hostCode,h){
  const pc = new RTCPeerConnection(ICE);
  let ch=null;
  pc.ondatachannel = e=>{ch=e.channel;wire(ch,pc,h);};
  const answer = (async()=>{await pc.setRemoteDescription(dec(hostCode));const a=await pc.createAnswer();await pc.setLocalDescription(a);await waitIce(pc);return enc(pc.localDescription);})();
  return {
    answer,
    send: o => { if(ch&&ch.readyState==='open') ch.send(JSON.stringify(o)); },
    close: ()=>{try{pc.close();}catch{}},
  };
}

export const netSupported = typeof RTCPeerConnection!=='undefined';
