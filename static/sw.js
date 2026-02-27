// Photo Match PWA — Service Worker
// Provides offline shell, caching, and background sync

const CACHE_VERSION = "photo-match-v1";
const STATIC_CACHE  = `${CACHE_VERSION}-static`;
const THUMB_CACHE   = `${CACHE_VERSION}-thumbnails`;

const PRECACHE_URLS = [
  "/",
  "/static/manifest.json",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
];

// ── Offline shell ─────────────────────────────────────────────────────────────
const OFFLINE_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#18181b">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>Photo Match — Offline</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#09090b;color:#fafafa;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:32px 24px;text-align:center}
.logo{font-size:2rem;margin-bottom:8px}
h1{font-size:1.4rem;font-weight:700;margin-bottom:8px;color:#f4f4f5}
p{font-size:.875rem;color:#71717a;line-height:1.6;max-width:320px;margin:0 auto 24px}
.badge{display:inline-flex;align-items:center;gap:6px;background:#27272a;border:1px solid #3f3f46;border-radius:20px;padding:6px 14px;font-size:.8rem;color:#f97316;font-weight:600;margin-bottom:24px}
.badge::before{content:'';width:8px;height:8px;border-radius:50%;background:#f97316;flex-shrink:0;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
button{background:#f97316;color:white;border:none;border-radius:24px;padding:12px 28px;font-size:.9rem;font-weight:600;cursor:pointer;transition:opacity .2s}
button:hover{opacity:.85}
.note{font-size:.72rem;color:#52525b;margin-top:12px}
</style>
</head>
<body>
<div class="logo">📷</div>
<h1>Photo Match</h1>
<div class="badge">⚡ Server unreachable</div>
<p>The server is offline or unreachable. Check that your VPN / Tailscale is running and the server is up.</p>
<button onclick="location.reload()">↻ Retry connection</button>
<p class="note">Thumbnails you've already viewed are cached in your browser.</p>
</body>
</html>`;

// ── Lifecycle: install ─────────────────────────────────────────────────────────
self.addEventListener("message", e => {
  if (e.data?.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(STATIC_CACHE)
      .then(c => c.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

// ── Lifecycle: activate ────────────────────────────────────────────────────────
self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys
          .filter(k => !k.startsWith(CACHE_VERSION))
          .map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

// ── Fetch strategy ─────────────────────────────────────────────────────────────
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);

  // API calls — network only, never cache (except version which is cheap)
  if (url.pathname.startsWith("/api/")) {
    if (url.pathname === "/api/version") {
      e.respondWith(
        fetch(e.request)
          .catch(() => new Response(JSON.stringify({ version: "offline" }), {
            headers: { "Content-Type": "application/json" }
          }))
      );
    }
    // All other API calls: network only
    return;
  }

  // Thumbnails — cache first (long-lived), serve stale while updating
  if (url.pathname.startsWith("/api/thumbnail/") ||
      url.pathname.startsWith("/api/wa-thumbnail/") ||
      url.pathname.startsWith("/static/thumbnails_cache/")) {
    e.respondWith(
      caches.open(THUMB_CACHE).then(c =>
        c.match(e.request).then(cached => {
          const net = fetch(e.request).then(res => {
            if (res?.status === 200) c.put(e.request, res.clone());
            return res;
          }).catch(() => null);
          return cached || net;
        })
      )
    );
    return;
  }

  // HTML navigation — network first, fall back to offline shell
  if (e.request.mode === "navigate") {
    e.respondWith(
      fetch(e.request)
        .catch(() => new Response(OFFLINE_HTML, {
          headers: { "Content-Type": "text/html; charset=utf-8" }
        }))
    );
    return;
  }

  // Static assets — cache first, update in background
  e.respondWith(
    caches.open(STATIC_CACHE).then(c =>
      c.match(e.request).then(cached => {
        const net = fetch(e.request).then(res => {
          if (res?.status === 200) c.put(e.request, res.clone());
          return res;
        }).catch(() => null);
        return cached || net;
      })
    )
  );
});
