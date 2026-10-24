/* 最小 PWA service worker：缓存应用外壳；/api 一律走网络（数据实时性优先，
   离线记录由前端 IndexedDB 队列负责，见 src/offline.ts）。 */
const CACHE = 'fc-shell-v10'

self.addEventListener('install', () => self.skipWaiting())

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  )
})

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url)
  if (url.pathname.startsWith('/api') || event.request.method !== 'GET') return
  event.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const cached = await cache.match(event.request)
      const network = fetch(event.request)
        .then((res) => {
          if (res.ok) cache.put(event.request, res.clone())
          return res
        })
        .catch(() => cached)
      return cached || network
    })
  )
})
