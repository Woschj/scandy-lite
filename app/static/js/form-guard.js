/*
 * Verhindert Doppel-Absenden: jedes <form data-guard> deaktiviert seinen
 * Submit-Button sofort nach dem ersten Klick und zeigt einen Hinweistext.
 * Wichtig bei mobilen Netzen mit Verzögerung - ohne das kann ein zweiter Tap
 * (z.B. weil die Antwort nicht sofort sichtbar wird) eine Ausleihe/Entnahme
 * versehentlich doppelt auslösen.
 *
 * WICHTIG: bewusst Bubble-Phase (kein "true" als drittes Argument), nicht
 * Capture-Phase. Manche Formulare (z.B. die Unterschrift beim Ausleihen)
 * haben einen EIGENEN submit-Handler direkt am Formular, der die Übermittlung
 * per preventDefault() abbrechen kann (z.B. wenn noch nicht unterschrieben
 * wurde). Läuft dieser HIER-Handler in der Capture-Phase, feuert er VOR
 * diesem anderen Handler - der Button wäre dann schon deaktiviert, obwohl
 * die Übermittlung gleich abgebrochen wird, und bliebe für immer auf
 * "Wird verarbeitet" hängen. In der Bubble-Phase läuft er NACH den direkt
 * am Formular hängenden Handlern, weshalb sich per e.defaultPrevented
 * prüfen lässt, ob die Übermittlung überhaupt noch stattfindet.
 */
document.addEventListener("submit", function (e) {
  if (e.defaultPrevented) return; // ein anderer Handler hat die Übermittlung bereits abgebrochen

  var form = e.target;
  if (!form.matches("[data-guard]")) return;

  var btn = form.querySelector('button[type="submit"]');
  if (!btn || btn.disabled) return;

  btn.disabled = true;
  btn.dataset.originalText = btn.textContent;
  btn.textContent = "Wird verarbeitet…";

  // Sicherheitsnetz: falls aus irgendeinem Grund keine neue Seite lädt
  // (Netzwerk-Hänger, Server-Fehler ohne Redirect), Button nach 15s wieder
  // freigeben statt den Nutzer dauerhaft auszusperren.
  setTimeout(function () {
    if (btn.disabled) {
      btn.disabled = false;
      btn.textContent = btn.dataset.originalText;
    }
  }, 15000);
});
