/*
 * Kachel-/Listenansicht-Umschalter für .item-grid-Seiten (Gegenstände,
 * Verbrauchsmaterial, Mitarbeiter) - rein clientseitig (localStorage),
 * analog zum ScandyCart-Muster in cart.js. Eine gemeinsame Einstellung für
 * alle drei Seiten, kein Server-Roundtrip, Default bleibt Kachelansicht.
 */
window.ScandyViewToggle = (function () {
  var STORAGE_KEY = "scandy_list_view";

  function getView() {
    try {
      return localStorage.getItem(STORAGE_KEY) || "grid";
    } catch (e) {
      return "grid";
    }
  }

  function setView(view) {
    try { localStorage.setItem(STORAGE_KEY, view); } catch (e) { /* localStorage nicht verfügbar - Auswahl gilt nur für diese Seite */ }
  }

  function apply(grid) {
    var view = getView();
    grid.classList.toggle("view-list", view === "list");
    document.querySelectorAll(".view-toggle-btn").forEach(function (btn) {
      var active = btn.dataset.view === view;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function init() {
    var grid = document.querySelector(".item-grid");
    if (!grid) return; // Seite ohne Kachel-/Listenansicht (z.B. Reservierungen) - nichts zu tun

    apply(grid);
    document.querySelectorAll(".view-toggle-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        setView(btn.dataset.view);
        apply(grid);
      });
    });
  }

  return { init: init };
})();

document.addEventListener("DOMContentLoaded", ScandyViewToggle.init);
