/*
 * Reiner Hinweis-Banner bei fehlender Internetverbindung - keine Queue,
 * kein Retry, keine Offline-Datenhaltung. Ausleih-relevante Daten (Bestand,
 * Verfuegbarkeit) duerfen nicht veraltet aus einem Cache kommen, siehe
 * app/static/sw.js - dieser Banner sagt dem Nutzer nur ehrlich, dass gerade
 * keine Verbindung besteht, statt dass Formulare kommentarlos haengen bleiben.
 */
document.addEventListener("DOMContentLoaded", function () {
  var banner = document.createElement("div");
  banner.className = "offline-banner";
  banner.setAttribute("role", "status");
  banner.textContent = "Keine Verbindung - Änderungen werden erst nach Wiederverbindung gespeichert.";
  document.body.appendChild(banner);

  function updateBannerVisibility() {
    banner.classList.toggle("is-visible", !navigator.onLine);
  }

  window.addEventListener("online", updateBannerVisibility);
  window.addEventListener("offline", updateBannerVisibility);
  updateBannerVisibility();
});
