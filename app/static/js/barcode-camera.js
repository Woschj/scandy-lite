/*
 * Wiederverwendbarer Kamera-Barcode-Scanner (ZXing). Kann mehrfach pro Seite
 * eingebunden werden (z.B. ein Scan-Button für den Gegenstand-Barcode UND
 * einer für den Mitarbeiter-Barcode direkt darunter).
 *
 * Nutzung: ScandyCamera.attach({
 *   startBtn, cancelBtn, wrap, video, unsupportedMsg, input,  // DOM-Elemente
 *   onScan: function(text) { ... }  // optional, Default: Formular absenden
 * });
 */
window.ScandyCamera = (function () {
  function vibrate(pattern) {
    if (navigator.vibrate) {
      try { navigator.vibrate(pattern); } catch (e) { /* manche Browser lehnen ohne User-Geste ab */ }
    }
  }

  function attach(cfg) {
    var codeReader = null;

    function showUnsupported(msg) {
      cfg.startBtn.style.display = "none";
      if (cfg.unsupportedMsg) {
        cfg.unsupportedMsg.textContent = msg;
        cfg.unsupportedMsg.style.display = "block";
      }
    }

    function stopCamera() {
      if (codeReader) {
        try { codeReader.reset(); } catch (e) { /* bereits gestoppt */ }
        codeReader = null;
      }
      cfg.wrap.style.display = "none";
      cfg.startBtn.style.display = "block";
    }

    if (!window.isSecureContext) {
      showUnsupported("Kamera-Scan benötigt eine sichere Verbindung (HTTPS). Bitte per Scanner oder Tastatur eingeben.");
      return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      showUnsupported("Kamera-Zugriff wird von diesem Browser nicht unterstützt.");
      return;
    }
    if (typeof ZXing === "undefined") {
      showUnsupported("Kamera-Scan-Bibliothek konnte nicht geladen werden (kein Internetzugriff?).");
      return;
    }

    cfg.startBtn.addEventListener("click", function () {
      codeReader = new ZXing.BrowserMultiFormatReader();
      cfg.startBtn.style.display = "none";
      cfg.wrap.style.display = "block";

      ZXing.BrowserMultiFormatReader.listVideoInputDevices().then(function (devices) {
        var rear = devices.find(function (d) { return /back|rear|environment/i.test(d.label); });
        var deviceId = rear ? rear.deviceId : (devices.length ? devices[devices.length - 1].deviceId : undefined);

        codeReader.decodeFromVideoDevice(deviceId, cfg.video, function (result) {
          if (result) {
            vibrate(80);
            cfg.input.value = result.getText();
            stopCamera();
            if (cfg.onScan) {
              cfg.onScan(result.getText());
            } else if (cfg.input.form) {
              cfg.input.form.requestSubmit();
            }
          }
          // err bei jedem Frame ohne erkannten Code - kein echter Fehler, wird ignoriert
        });
      }).catch(function () {
        showUnsupported("Kamera konnte nicht gestartet werden: kein Zugriff erteilt oder keine Kamera gefunden.");
        cfg.wrap.style.display = "none";
      });
    });

    if (cfg.cancelBtn) {
      cfg.cancelBtn.addEventListener("click", stopCamera);
    }
  }

  return { attach: attach, vibrate: vibrate };
})();
