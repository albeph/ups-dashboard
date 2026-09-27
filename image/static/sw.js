/* UPS Web Dashboard - Service Worker for PWA (iOS & Android) */
const CACHE_NAME = 'ups-dashboard-v1.1.0';

const PRECACHE_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/locales/it.json',
  '/locales/en.json',
  '/icon.svg',
  '/icon-192.png',
  '/icon-512.png',
  '/icon-maskable-512.png',
  '/apple-touch-icon.png',
  '/favicon.ico'
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_ASSETS).catch((err) => {
        console.warn('[SW] Precache asset error:', err);
      });
    })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    Promise.all([
      self.clients.claim(),
      caches.keys().then((keys) => {
        return Promise.all(
          keys.map((key) => {
            if (key !== CACHE_NAME) {
              return caches.delete(key);
            }
          })
        );
      })
    ])
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // 1. API Calls
  if (url.pathname.startsWith('/api/')) {
    // Locales can be stale-while-revalidate
    if (url.pathname === '/api/locales') {
      event.respondWith(
        caches.match(event.request).then((cached) => {
          const fetchPromise = fetch(event.request)
            .then((res) => {
              if (res.ok) {
                const clone = res.clone();
                caches.open(CACHE_NAME).then((c) => c.put(event.request, clone));
              }
              return res;
            })
            .catch(() => cached);
          return cached || fetchPromise;
        })
      );
      return;
    }

    // Live telemetry and auth: Network only, with fallback on failure
    event.respondWith(
      fetch(event.request).catch(() => {
        if (url.pathname === '/api/stats') {
          return new Response(
            JSON.stringify({
              status: 'offline',
              watts: null,
              load: 0,
              battery: 0,
              error_message: 'Disconnesso (Offline)'
            }),
            { headers: { 'Content-Type': 'application/json' } }
          );
        }
        return new Response(
          JSON.stringify({ error: 'Rete non disponibile' }),
          { status: 503, headers: { 'Content-Type': 'application/json' } }
        );
      })
    );
    return;
  }

  // 2. Navigation requests: Network-first, fallback to cached index.html
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(CACHE_NAME).then((c) => c.put(event.request, clone));
          }
          return res;
        })
        .catch(() => {
          return caches.match('/') || caches.match('/index.html');
        })
    );
    return;
  }

  // 3. Static assets: Stale-While-Revalidate / Cache-first
  event.respondWith(
    caches.match(event.request).then((cached) => {
      const fetchPromise = fetch(event.request)
        .then((res) => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(CACHE_NAME).then((c) => c.put(event.request, clone));
          }
          return res;
        })
        .catch(() => cached);

      return cached || fetchPromise;
    })
  );
});
