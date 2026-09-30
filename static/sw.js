self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
// simple pass-through so the app always shows fresh data
self.addEventListener("fetch", (e) => {
  e.respondWith(fetch(e.request));
});
