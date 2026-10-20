/* Minimal offline cache for app shell and local OCR runtime assets.
   Model/language files are cached on first successful online request. */
const CACHE_NAME = "tuuza-ocr-v1";
const APP_SHELL = ["/quotation-ocr", "/manifest.json", "/icon.svg"];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", event => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  const isOcrAsset = url.pathname.startsWith("/tesseract/");
  const isAppShell = url.pathname === "/quotation-ocr" || url.pathname === "/manifest.json" || url.pathname === "/icon.svg";
  if (!isOcrAsset && !isAppShell) return;
  event.respondWith(caches.open(CACHE_NAME).then(async cache => {
    const cached = await cache.match(req);
    if (cached) return cached;
    try {
      const response = await fetch(req);
      if (response.ok && (isOcrAsset || isAppShell)) {
        // Cache large runtime/model files only after a successful online download.
        await cache.put(req, response.clone());
      }
      return response;
    } catch (err) {
      if (isAppShell) {
        const fallback = await cache.match("/quotation-ocr");
        if (fallback) return fallback;
      }
      throw err;
    }
  }));
});
