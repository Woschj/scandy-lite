/*
 * Klick-Vorschau (Lightbox) für Gegenstands-/Verbrauchsmaterial-Bilder auf
 * .item-thumb (kleine Vorschaubilder in Kachel-/Listenansicht + Scan-
 * Ergebnis) und .image-upload-preview (großes Vorschaubild auf den
 * Bearbeiten-Seiten) - kein Template muss dafür einzeln Code einbinden,
 * funktioniert automatisch überall, wo diese Klassen zum Zeitpunkt von
 * DOMContentLoaded im DOM stehen. .item-thumb-placeholder (kein echtes
 * Bild, nur ein SVG-Icon) ist bewusst NICHT eingebunden.
 *
 * WICHTIG: das ist KEIN delegiertes Event-Handling (kein Listener auf
 * document, der bei jedem Klick prüft ob das Ziel passt) - stattdessen wird
 * einmalig bei DOMContentLoaded ein Listener PRO zu diesem Zeitpunkt
 * gefundenem Element angehängt. Bilder, die ERST NACH DOMContentLoaded
 * dynamisch ins DOM eingefügt werden (z.B. per fetch/innerHTML nachgeladen),
 * bekommen dadurch KEINEN Lightbox-Klick automatisch - für einen solchen
 * Fall müsste die passende Stelle explizit window.ScandyLightbox.attach(el)
 * (siehe unten) für die neuen Elemente aufrufen.
 */
window.ScandyLightbox = (function () {
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

  // Hängt Klick-/Tastatur-Handler an EIN Element - wird beim initialen Scan
  // (DOMContentLoaded) für jeden SELECTOR-Treffer aufgerufen, kann aber auch
  // gezielt für nachträglich ins DOM eingefügte Bilder aufgerufen werden
  // (z.B. nach einem fetch()/innerHTML-Update), da dieses Modul KEIN
  // delegiertes Handling nutzt - siehe Datei-Kopfkommentar. data-lightbox-
  // bound verhindert doppeltes Binden, falls attach() versehentlich zweimal
  // für dasselbe Element aufgerufen wird.
  function attach(img) {
    if (!img || img.dataset.lightboxBound) return;
    img.dataset.lightboxBound = "true";
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
  }

  function attachAll(root) {
    (root || document).querySelectorAll(SELECTOR).forEach(attach);
  }

  document.addEventListener("DOMContentLoaded", function () {
    attachAll(document);
  });

  return { attach: attach, attachAll: attachAll };
})();
