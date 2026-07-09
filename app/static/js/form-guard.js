/*
 * Verhindert Doppel-Absenden: jedes <form data-guard> deaktiviert seinen
 * Submit-Button sofort nach dem ersten Klick und zeigt einen Hinweistext.
 * Wichtig bei mobilen Netzen mit Verzögerung - ohne das kann ein zweiter Tap
 * (z.B. weil die Antwort nicht sofort sichtbar wird) eine Ausleihe/Entnahme
 * versehentlich doppelt auslösen.
 */
document.addEventListener("submit", function (e) {
  var form = e.target;
  if (!form.matches("[data-guard]")) return;

  var btn = form.querySelector('button[type="submit"]');
  if (!btn || btn.disabled) return;

  btn.disabled = true;
  btn.dataset.originalText = btn.textContent;
  btn.textContent = "Wird verarbeitet…";
}, true);
