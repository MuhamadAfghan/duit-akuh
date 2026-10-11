/**
 * Service worker (PRD FR16, section 12).
 *
 * Deliberate scope limits, straight from the PRD:
 *
 * - Caches STATIC SHELL ASSETS ONLY. Finance and chat APIs are never
 *   cached, so the app can never show stale balances or fake a successful
 *   write while offline.
 * - Navigation responses are not cached either. They are per-user rendered
 *   HTML, so caching them risks serving one account's page to another; on
 *   network failure we serve a static offline page instead.
 * - Does not call skipWaiting() on its own. An update must not reload the
 *   app out from under an unsaved draft, so activation is left for the page
 *   to trigger once it knows no draft is pending.
 */

const VERSION = 'v1';
const STATIC_CACHE = `static-${VERSION}`;
const OFFLINE_URL = '/offline.html';

/** Paths that only ever hold immutable or public static files. */
const STATIC_PREFIXES = ['/_next/static/', '/icons/', '/fonts/', '/assets/', '/logo/'];

/**
 * Never touched by the cache, under any circumstances.
 *
 * `/srv/` is the backend proxy (see the rewrite in next.config.mjs);
 * `/auth/` is the sign-in pages. Keep this in step with BASE in
 * src/lib/api.js.
 */
const NEVER_CACHE_PREFIXES = ['/srv/', '/auth/'];

const isStatic = (pathname) => STATIC_PREFIXES.some((prefix) => pathname.startsWith(prefix));

const isNeverCached = (pathname) =>
  NEVER_CACHE_PREFIXES.some((prefix) => pathname.startsWith(prefix));

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll([OFFLINE_URL, '/icons/icon-192.png']))
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.filter((key) => key !== STATIC_CACHE).map((key) => caches.delete(key)));
      await self.clients.claim();
    })()
  );
});

/** Lets the page activate a pending update when it knows it is safe to. */
self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

self.addEventListener('fetch', (event) => {
  const { request } = event;

  if (request.method !== 'GET') {
    return;
  }

  const url = new URL(request.url);

  // Only handle our own origin, and never the API or auth surface.
  if (url.origin !== self.location.origin || isNeverCached(url.pathname)) {
    return;
  }

  // Navigations: always go to the network; fall back to a static offline
  // page. Never cache the response.
  if (request.mode === 'navigate') {
    event.respondWith(
      (async () => {
        try {
          return await fetch(request);
        } catch {
          const cache = await caches.open(STATIC_CACHE);
          const offline = await cache.match(OFFLINE_URL);
          return (
            offline ??
            new Response('Offline', { status: 503, headers: { 'Content-Type': 'text/plain' } })
          );
        }
      })()
    );
    return;
  }

  if (!isStatic(url.pathname)) {
    return;
  }

  // Static assets: cache-first, and only store successful same-origin
  // responses so we never persist an error page as an asset.
  event.respondWith(
    (async () => {
      const cache = await caches.open(STATIC_CACHE);
      const cached = await cache.match(request);

      if (cached) {
        return cached;
      }

      const response = await fetch(request);

      if (response.ok && response.type === 'basic') {
        cache.put(request, response.clone());
      }

      return response;
    })()
  );
});
