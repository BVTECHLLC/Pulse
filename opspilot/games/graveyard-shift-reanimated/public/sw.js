// Graveyard Shift service worker — makes the game installable + resilient offline.
// Network-first for the app shell/bundles so updates always win; cache is a fallback.
const CACHE='graveyard-shift-v8';
self.addEventListener('install',e=>{self.skipWaiting();});
self.addEventListener('activate',e=>{e.waitUntil((async()=>{const keys=await caches.keys();await Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)));await self.clients.claim();})());});
self.addEventListener('fetch',e=>{
  const req=e.request;if(req.method!=='GET')return;
  e.respondWith((async()=>{
    try{const fresh=await fetch(req);if(fresh&&fresh.status===200&&new URL(req.url).origin===location.origin){const c=await caches.open(CACHE);c.put(req,fresh.clone());}return fresh;}
    catch(err){const cached=await caches.match(req);if(cached)return cached;throw err;}
  })());
});
