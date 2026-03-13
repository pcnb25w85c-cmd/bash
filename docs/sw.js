const V = 'action-v3';
const SHELL = ['./','./manifest.json','./icon.png'];

self.addEventListener('install', e =>
  e.waitUntil(caches.open(V).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()))
);
self.addEventListener('activate', e =>
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k))))
    .then(() => self.clients.claim()))
);
self.addEventListener('fetch', e => {
  // Altijd netwerk voor externe API-calls
  if (!e.request.url.startsWith(self.location.origin)) return;
  e.respondWith(caches.match(e.request).then(c => c || fetch(e.request)));
});
