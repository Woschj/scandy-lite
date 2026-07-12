/*
 * Service Worker: cached NUR die statische App-Shell (CSS/JS/Icons/Manifest)
 * fuer schnelleres Laden bei wackligem WLAN - bewusst KEIN Cache fuer
 * Seiten-Navigationen, API-Antworten oder irgendwelche POSTs. Ein Ausleih-
 * Tool darf niemals veraltete Bestands-/Verfuegbarkeits-Daten offline
 * anzeigen (Risiko: Doppel-Ausleihe). Der Offline-Hinweis selbst kommt aus
 * app/static/js/offline-banner.js, nicht aus diesem Service Worker.
 *
 * Muss unter /sw.js (Root-Scope) ausgeliefert werden, nicht unter
 * /static/sw.js - sonst kontrolliert der Service Worker nur /static/*
 * statt der eigentlichen App-Seiten. Siehe die /sw.js-Route in app/main.py.
 */
const CACHE_NAME = "scandy-lite-shell-v3";

const SHELL_ASSETS = [
  "/static/css/app.css",
  "/static/js/vendor/htmx.min.js",
  "/static/js/vendor/alpine.min.js",
  "/static/js/vendor/html5-qrcode.min.js",
  "/static/js/form-guard.js",
  "/static/js/qty-stepper.js",
  "/static/js/cart.js",
  "/static/js/view-toggle.js",
  "/static/js/lightbox.js",
  "/static/js/barcode-camera.js",
  "/static/js/signature.js",
  "/static/js/offline-banner.js",
  "/static/icons/icon.svg",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/icon-maskable-512.png",
  "/static/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Nur eigene, statische GET-Requests behandeln - alles andere (Seiten-
  // Navigationen, /uploads/, jeder POST/PUT/DELETE) laeuft unangetastet
  // durch den Browser, kein respondWith().
  if (event.request.method !== "GET" || url.origin !== self.location.origin || !url.pathname.startsWith("/static/")) {
    return;
  }

  // Network-first (nicht cache-first!): bei jedem Request wird zuerst
  // versucht, die aktuelle Datei vom Server zu holen - nur wenn das
  // fehlschlaegt (offline), wird auf den Cache zurueckgefallen. Cache-first
  // hat bereits einen echten Bug verursacht: nach einem CSS-Fix zeigte ein
  // Geraet mit bereits installiertem Service Worker weiterhin die ALTE,
  // kaputte app.css, weil "einmal gecacht" nie wieder mit dem Server
  // abgeglichen wurde. Network-first heilt sich bei jedem Deploy von selbst,
  // ohne dass CACHE_NAME manuell erhoeht werden muss.
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Nur echte Erfolgsantworten cachen - ein voruebergehender 404/500
        // (z.B. Deploy-Race) darf nicht als "guter" Offline-Fallback
        // gespeichert werden, sonst wird die Fehlerantwort spaeter beim
        // naechsten echten Offline-Zustand ausgeliefert.
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
