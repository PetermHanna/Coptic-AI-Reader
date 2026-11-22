// Offline support: keep the app and every book you have opened on the phone,
// so it works in a church basement without signal. Updates load in the
// background and are used next time.
const CACHE = 'reader-v1';
const SHELL = [
  './', 'index.html', 'manifest.webmanifest', 'src/app.js', 'src/matcher.js', 'src/style.css',
  'fonts/NotoSansCoptic.woff2', 'fonts/NotoNaskhArabic-Regular.woff2', 'fonts/NotoNaskhArabic-Bold.woff2',
  'books/sample.json', 'icons/icon-192.png', 'icons/icon-512.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// stale-while-revalidate for our own files
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  e.respondWith(caches.open(CACHE).then(async (cache) => {
    const cached = await cache.match(e.request, { ignoreSearch: true });
    const fresh = fetch(e.request).then((res) => {
      if (res.ok) cache.put(e.request, res.clone());
      return res;
    }).catch(() => cached);
    return cached || fresh;
  }));
});
