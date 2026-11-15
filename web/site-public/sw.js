/* CinderTrace field mode: app shell + recently visited local data, never remote map tiles. */
const VERSION='__CINDERTRACE_BUILD__';
const SHELL='cindertrace-shell-'+VERSION,DATA='cindertrace-data-'+VERSION;
self.addEventListener('install',event=>event.waitUntil((async()=>{const response=await fetch('/offline-assets.json',{cache:'reload'});if(!response.ok)throw new Error('Offline asset list unavailable');const files=await response.json(),cache=await caches.open(SHELL);await cache.addAll(files);await self.skipWaiting();})()));
self.addEventListener('activate',event=>event.waitUntil((async()=>{for(const key of await caches.keys())if((key.startsWith('cindertrace-shell-')||key.startsWith('cindertrace-data-')||key.startsWith('emberline-shell-')||key.startsWith('emberline-data-'))&&key!==SHELL&&key!==DATA)await caches.delete(key);await self.clients.claim();})()));
self.addEventListener('fetch',event=>{const request=event.request,url=new URL(request.url);if(request.method!=='GET'||url.origin!==self.location.origin)return;
 if(request.mode==='navigate'){event.respondWith(fetch(request).catch(async()=>{const cached=await caches.match('/index.html');return cached||Response.error();}));return;}
 if(url.pathname.startsWith('/assets/')){event.respondWith(caches.match(request).then(c=>c||fetch(request)));return;}
 if(/^\/(ready|context|validation)\//.test(url.pathname))event.respondWith((async()=>{const cache=await caches.open(DATA);try{const response=await fetch(request);if(response.ok){await cache.delete(request);await cache.put(request,response.clone());if(/native-\d+\.json\.gz$/.test(url.pathname)){const nativeKeys=(await cache.keys()).filter(r=>/native-\d+\.json\.gz$/.test(new URL(r.url).pathname));while(nativeKeys.length>4)await cache.delete(nativeKeys.shift());}}return response;}catch(error){const cached=await cache.match(request);if(cached)return cached;throw error;}})());
});
