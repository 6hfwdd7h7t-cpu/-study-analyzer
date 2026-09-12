const CACHE="study-analyzer-v2-9-learning-only";
const ASSETS=["./","./index.html","./manifest.webmanifest","./icon.svg","./apple-touch-icon.png","./icon-192.png","./icon-512.png"];
self.addEventListener("install",event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS)));self.skipWaiting()});
self.addEventListener("activate",event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))));self.clients.claim()});
self.addEventListener("fetch",event=>{if(event.request.method!=="GET")return;if(event.request.mode==="navigate"){event.respondWith(fetch(event.request).then(response=>{const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(event.request,copy));return response}).catch(()=>caches.match(event.request).then(r=>r||caches.match("./index.html"))));return}event.respondWith(caches.match(event.request).then(cached=>cached||fetch(event.request)))});
