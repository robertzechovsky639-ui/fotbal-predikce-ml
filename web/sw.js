const C='fotbal-__GIT_SHA__',A=['./','style.css','live.js','static.js','app.js','poll-worker.js','manifest.json','icon.svg','names_rules.json'];
self.addEventListener('install',e=>{self.skipWaiting();e.waitUntil(caches.open(C).then(c=>c.addAll(A)))});
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(k=>Promise.all(k.filter(x=>x!==C).map(x=>caches.delete(x)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{
  const u=new URL(e.request.url);
  if(u.origin!==location.origin||u.pathname.includes('/data/'))return;
  e.respondWith((async()=>{
    const cache=await caches.open(C);
    const ctrl=new AbortController();
    const timer=setTimeout(()=>ctrl.abort(),3000);
    try{
      const r=await fetch(e.request,{signal:ctrl.signal});
      clearTimeout(timer);
      if(r&&r.ok)cache.put(e.request,r.clone());
      return r;
    }catch(err){
      clearTimeout(timer);
      const hit=await caches.match(e.request);
      if(hit)return hit;
      throw err;
    }
  })());
});
