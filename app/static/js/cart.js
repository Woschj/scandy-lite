/*
 * Warenkorb für Reservierungen - rein clientseitig (localStorage), damit das
 * Reservieren-Vormerken ohne Seitenwechsel/Serverkontakt geht und über
 * mehrere Seiten/Abteilungswechsel hinweg erhalten bleibt. Erst beim
 * gesammelten Absenden (Warenkorb-Seite -> /reservations/cart/submit)
 * passiert serverseitig überhaupt etwas.
 *
 * Enthält zwei Arten von Einträgen:
 *   {type: "item", id: "..."}                    - ein Gegenstand (Menge immer 1)
 *   {type: "consumable", id: "...", quantity: N}  - eine Menge Verbrauchsmaterial
 */
window.ScandyCart = (function () {
  var STORAGE_KEY = "scandy_reservation_cart";

  function getEntries() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (e) {
      return [];
    }
  }

  function saveEntries(entries) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
    } catch (e) { /* localStorage nicht verfügbar (z.B. privater Modus) - Warenkorb bleibt dann nur für die Sitzung im Speicher */ }
    updateBadges();
  }

  function findEntry(type, id) {
    return getEntries().find(function (e) { return e.type === type && e.id === id; });
  }

  function has(type, id) {
    return !!findEntry(type, id);
  }

  function addItem(id) {
    var entries = getEntries();
    if (!has("item", id)) {
      entries.push({ type: "item", id: id });
      saveEntries(entries);
    }
  }

  function addConsumable(id, quantity) {
    quantity = Math.max(1, parseInt(quantity, 10) || 1);
    var entries = getEntries();
    var existing = entries.find(function (e) { return e.type === "consumable" && e.id === id; });
    if (existing) {
      existing.quantity = quantity;
    } else {
      entries.push({ type: "consumable", id: id, quantity: quantity });
    }
    saveEntries(entries);
  }

  function remove(type, id) {
    saveEntries(getEntries().filter(function (e) { return !(e.type === type && e.id === id); }));
  }

  function clear() {
    saveEntries([]);
  }

  function count() {
    return getEntries().length;
  }

  function updateBadges() {
    var n = count();
    document.querySelectorAll("[data-cart-badge]").forEach(function (el) {
      el.textContent = n;
      el.style.display = n > 0 ? "" : "none";
    });
  }

  function initToggleButtons() {
    // Gegenstände: einfacher Ein/Aus-Toggle
    document.querySelectorAll("[data-cart-toggle]").forEach(function (btn) {
      var id = btn.dataset.itemId;
      function render() {
        if (has("item", id)) {
          btn.textContent = "Im Warenkorb ✓";
          btn.classList.add("in-cart");
        } else {
          btn.textContent = "In den Warenkorb";
          btn.classList.remove("in-cart");
        }
      }
      render();
      btn.addEventListener("click", function () {
        if (has("item", id)) {
          remove("item", id);
        } else {
          addItem(id);
          if (navigator.vibrate) { try { navigator.vibrate(40); } catch (e) {} }
        }
        render();
      });
    });

    // Verbrauchsmaterial: Button + zugehöriges Mengenfeld (data-cart-quantity-for="<id>")
    document.querySelectorAll("[data-cart-toggle-consumable]").forEach(function (btn) {
      var id = btn.dataset.consumableId;
      var qtyInput = document.querySelector('[data-cart-quantity-for="' + id + '"]');
      function render() {
        var entry = findEntry("consumable", id);
        if (entry) {
          btn.textContent = "Im Warenkorb ✓ (" + entry.quantity + ")";
          btn.classList.add("in-cart");
        } else {
          btn.textContent = "In den Warenkorb";
          btn.classList.remove("in-cart");
        }
      }
      render();
      btn.addEventListener("click", function () {
        if (has("consumable", id)) {
          remove("consumable", id);
        } else {
          var qty = qtyInput ? qtyInput.value : 1;
          addConsumable(id, qty);
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

  return {
    getEntries: getEntries, addItem: addItem, addConsumable: addConsumable,
    remove: remove, clear: clear, count: count, has: has, updateBadges: updateBadges,
  };
})();
