/*
 * Warenkorb für Reservierungen - rein clientseitig (localStorage), damit das
 * Reservieren-Vormerken ohne Seitenwechsel/Serverkontakt geht und über
 * mehrere Seiten/Abteilungswechsel hinweg erhalten bleibt. Erst beim
 * gesammelten Absenden (Warenkorb-Seite -> /reservations/cart/submit)
 * passiert serverseitig überhaupt etwas.
 */
window.ScandyCart = (function () {
  var STORAGE_KEY = "scandy_reservation_cart";

  function getIds() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (e) {
      return [];
    }
  }

  function saveIds(ids) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
    } catch (e) { /* localStorage nicht verfügbar (z.B. privater Modus) - Warenkorb bleibt dann nur für die Sitzung im Speicher */ }
    updateBadges();
  }

  function has(id) {
    return getIds().indexOf(id) !== -1;
  }

  function add(id) {
    var ids = getIds();
    if (ids.indexOf(id) === -1) {
      ids.push(id);
      saveIds(ids);
    }
  }

  function remove(id) {
    saveIds(getIds().filter(function (existing) { return existing !== id; }));
  }

  function clear() {
    saveIds([]);
  }

  function count() {
    return getIds().length;
  }

  function updateBadges() {
    var n = count();
    document.querySelectorAll("[data-cart-badge]").forEach(function (el) {
      el.textContent = n;
      el.style.display = n > 0 ? "" : "none";
    });
  }

  function initToggleButtons() {
    document.querySelectorAll("[data-cart-toggle]").forEach(function (btn) {
      var id = btn.dataset.itemId;
      function render() {
        if (has(id)) {
          btn.textContent = "Im Warenkorb ✓";
          btn.classList.add("in-cart");
        } else {
          btn.textContent = "In den Warenkorb";
          btn.classList.remove("in-cart");
        }
      }
      render();
      btn.addEventListener("click", function () {
        if (has(id)) {
          remove(id);
        } else {
          add(id);
          if (navigator.vibrate) { try { navigator.vibrate(40); } catch (e) {} }
        }
        render();
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    updateBadges();
    initToggleButtons();
  });

  return { getIds: getIds, add: add, remove: remove, clear: clear, count: count, has: has, updateBadges: updateBadges };
})();
