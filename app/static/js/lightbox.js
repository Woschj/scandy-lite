/*
 * Klick-Vorschau (Lightbox) für Gegenstands-/Verbrauchsmaterial-Bilder.
 * Delegiertes Click-Handling auf .item-thumb (kleine Vorschaubilder in
 * Kachel-/Listenansicht + Scan-Ergebnis) und .image-upload-preview (großes
 * Vorschaubild auf den Bearbeiten-Seiten) - kein Template muss dafür
 * einzeln Code einbinden, funktioniert automatisch überall, wo diese
 * Klassen vorkommen. .item-thumb-placeholder (kein echtes Bild, nur ein
 * SVG-Icon) ist bewusst NICHT eingebunden.
 */
(function () {
  var SELECTOR = ".item-thumb, .image-upload-preview";
  var overlay = null;

  function closeLightbox() {
    if (!overlay) return;
    overlay.remove();
    overlay = null;
    document.removeEventListener("keydown", onKeydown);
  }

  function onKeydown(e) {
    if (e.key === "Escape") closeLightbox();
  }

  function openLightbox(src) {
    closeLightbox();
    overlay = document.createElement("div");
    overlay.className = "lightbox-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");

    var img = document.createElement("img");
    img.src = src;
    img.alt = "";
    overlay.appendChild(img);

    var closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "lightbox-close";
    closeBtn.setAttribute("aria-label", "Schließen");
    closeBtn.textContent = "✕";
    closeBtn.addEventListener("click", closeLightbox);
    overlay.appendChild(closeBtn);

    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) closeLightbox();
    });

    document.body.appendChild(overlay);
    document.addEventListener("keydown", onKeydown);
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(SELECTOR).forEach(function (img) {
      img.setAttribute("role", "button");
      img.setAttribute("tabindex", "0");
      img.addEventListener("click", function () {
        openLightbox(img.src);
      });
      img.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openLightbox(img.src);
        }
      });
    });
  });
})();
