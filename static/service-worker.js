/**
 * Service Worker для PWA виджета Beer ABC Dashboard
 * Стратегия кэширования:
 * - Статика (CSS, JS, fonts): Cache-first
 * - API запросы: Network-first с fallback на кэш
 * - HTML страницы: Network-first
 */

const CACHE_NAME = 'beer-abc-v1';
const STATIC_CACHE = 'beer-abc-static-v1';
const API_CACHE = 'beer-abc-api-v1';

// Ресурсы для предварительного кэширования
const STATIC_ASSETS = [
    '/',
    '/dashboard/widget',
    '/static/manifest.json',
    '/static/js/widget/revenue_widget.js',
    '/static/dashboard/styles/widget.css',
    '/static/dashboard/styles/variables.css',
    '/static/dashboard/styles/base.css',
    '/static/fonts/IBMPlexMono/IBMPlexMono-Regular.woff2',
    '/static/fonts/IBMPlexMono/IBMPlexMono-Bold.woff2',
    '/logo.jpg'
];

// Установка Service Worker
self.addEventListener('install', (event) => {
    console.log('[SW] Install');
    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then((cache) => {
                console.log('[SW] Pre-caching static assets');
                return cache.addAll(STATIC_ASSETS);
            })
            .catch((error) => {
                console.error('[SW] Pre-cache failed:', error);
            })
    );
    self.skipWaiting();
});

// Активация Service Worker
self.addEventListener('activate', (event) => {
    console.log('[SW] Activate');
    event.waitUntil(
        caches.keys()
            .then((cacheNames) => {
                return Promise.all(
                    cacheNames.map((cacheName) => {
                        if (cacheName !== STATIC_CACHE && cacheName !== API_CACHE) {
                            console.log('[SW] Deleting old cache:', cacheName);
                            return caches.delete(cacheName);
                        }
                    })
                );
            })
            .then(() => {
                console.log('[SW] Claiming clients');
                return self.clients.claim();
            })
    );
});

// Перехват запросов
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);

    // Игнорируем не-GET запросы
    if (request.method !== 'GET') {
        return;
    }

    // API запросы - Network-first с fallback на кэш
    if (url.pathname.startsWith('/api/')) {
        console.log('[SW] API request:', url.pathname);
        event.respondWith(networkFirstStrategy(request, API_CACHE));
        return;
    }

    // Статические ресурсы - Cache-first
    if (isStaticAsset(url.pathname)) {
        console.log('[SW] Static asset:', url.pathname);
        event.respondWith(cacheFirstStrategy(request, STATIC_CACHE));
        return;
    }

    // HTML страницы - Network-first
    console.log('[SW] Page request:', url.pathname);
    event.respondWith(networkFirstStrategy(request, STATIC_CACHE));
});

/**
 * Проверка, является ли ресурс статическим
 */
function isStaticAsset(pathname) {
    const staticExtensions = [
        '.js', '.css', '.woff2', '.woff', '.ttf', '.eot',
        '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico',
        '.json'
    ];
    return staticExtensions.some(ext => pathname.endsWith(ext));
}

/**
 * Network-first стратегия: сначала сеть, потом кэш
 */
async function networkFirstStrategy(request, cacheName) {
    try {
        console.log('[SW] Network-first: fetching from network');
        const networkResponse = await fetch(request);

        // Кэшируем успешные ответы
        if (networkResponse.ok) {
            const cache = await caches.open(cacheName);
            cache.put(request, networkResponse.clone());
        }

        return networkResponse;
    } catch (error) {
        console.log('[SW] Network failed, trying cache:', error.message);

        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            console.log('[SW] Serving from cache');
            return cachedResponse;
        }

        // Fallback для офлайн режима
        if (request.headers.get('accept')?.includes('text/html')) {
            console.log('[SW] Returning offline fallback');
            return caches.match('/');
        }

        return new Response('Offline', { status: 503 });
    }
}

/**
 * Cache-first стратегия: сначала кэш, потом сеть
 */
async function cacheFirstStrategy(request, cacheName) {
    const cachedResponse = await caches.match(request);

    if (cachedResponse) {
        console.log('[SW] Serving from cache');

        // Обновляем кэш в фоне (stale-while-revalidate)
        fetch(request)
            .then((networkResponse) => {
                if (networkResponse.ok) {
                    caches.open(cacheName)
                        .then((cache) => cache.put(request, networkResponse));
                }
            })
            .catch(() => {
                // Игнорируем ошибки сети
            });

        return cachedResponse;
    }

    try {
        console.log('[SW] Cache miss, fetching from network');
        const networkResponse = await fetch(request);

        if (networkResponse.ok) {
            const cache = await caches.open(cacheName);
            cache.put(request, networkResponse.clone());
        }

        return networkResponse;
    } catch (error) {
        console.error('[SW] Fetch failed:', error.message);
        return new Response('Offline', { status: 503 });
    }
}
