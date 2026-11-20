/**
 * UPS Web Dashboard - Progressive Web App (PWA) Service Worker
 *
 * The backend dynamically replaces `__APP_VERSION__` with the value in `image/VERSION`
 * whenever `/sw.js` is requested, guaranteeing automatic cache invalidation on upgrades.
 */

const CACHE_NAME = 'ups-dashboard-v__APP_VERSION__';

const PRECACHE_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/css/styles.css',
  '/js/app.js',
  '/js/api.js',
  '/js/auth.js',
  '/js/blackout.js',
  '/js/dom.js',
  '/js/i18n.js',
  '/js/pwa.js',
  '/js/settings.js',
  '/js/telemetry.js',
  '/js/tooltip.js',
  '/locales/en.json',
  '/locales/it.json',
  '/icon.svg',
  '/icon-192.png',
  '/icon-512.png',
  '/icon-maskable-512.png',
  '/apple-touch-icon.png',
  '/favicon.ico',
];

/**
 * Install lifecycle: precache core shell assets and activate immediately.
 */
self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_ASSETS).catch((err) => {
        console.warn('[SW] Precache asset warning:', err);
      });
    })
  );
});

/**
 * Activate lifecycle: claim active clients and purge stale cache namespaces.
 */
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
            return undefined;
          })
        );
      }),
    ])
  );
});

/**
 * Fetch lifecycle:
 * 1. `/api/locales`: Network-first with offline cache fallback.
 * 2. Other `/api/*` endpoints: Network-only with graceful offline JSON fallback.
 * 3. HTML navigations & `/locales/*.json`: Network-first with cache fallback.
 * 4. Static assets (CSS, JS, icons): Stale-while-revalidate with query-insensitive fallback.
 */
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // 1. API endpoints
  if (url.pathname.startsWith('/api/')) {
    if (url.pathname === '/api/locales') {
      event.respondWith(
        fetch(event.request)
          .then((res) => {
            if (res.ok) {
              const clone = res.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
            }
            return res;
          })
          .catch(() => caches.match(event.request))
      );
      return;
    }

    // Live telemetry and authentication endpoints must never serve stale cached payloads.
    event.respondWith(
      fetch(event.request).catch(() => {
        if (url.pathname === '/api/stats') {
          return new Response(
            JSON.stringify({
              status: 'offline',
              watts: null,
              load: 0,
              battery: 0,
              error_message: 'Disconnected (Offline)',
            }),
            { headers: { 'Content-Type': 'application/json' } }
          );
        }
        return new Response(
          JSON.stringify({ error: 'Network unavailable' }),
          { status: 503, headers: { 'Content-Type': 'application/json' } }
        );
      })
    );
    return;
  }

  // 2. Document navigations and localization JSON files (Network-first)
  if (event.request.mode === 'navigate' || url.pathname.startsWith('/locales/')) {
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return res;
        })
        .catch(() => {
          if (event.request.mode === 'navigate') {
            return caches.match('/') || caches.match('/index.html');
          }
          return caches.match(event.request, { ignoreSearch: true });
        })
    );
    return;
  }

  // 3. Static shell assets (Stale-while-revalidate with version-query fallback)
  event.respondWith(
    caches.match(event.request, { ignoreSearch: true }).then((cached) => {
      const fetchPromise = fetch(event.request)
        .then((res) => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return res;
        })
        .catch(() => cached);

      return cached || fetchPromise;
    })
  );
});
