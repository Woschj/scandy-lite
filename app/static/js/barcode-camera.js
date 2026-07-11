/*
 * Wiederverwendbarer Kamera-Barcode-Scanner (html5-qrcode). Kann mehrfach pro
 * Seite eingebunden werden (z.B. ein Scan-Button für den Gegenstand-Barcode
 * UND einer für den Mitarbeiter-Barcode direkt darunter).
 *
 * Nutzung: ScandyCamera.attach({
 *   startBtn, cancelBtn, wrap, videoContainerId, unsupportedMsg, input,
 *   onScan: function(text) { ... }  // optional, Default: Formular absenden
 * });
 *
 * videoContainerId ist die ID eines LEEREN <div> - html5-qrcode erzeugt
 * darin selbst sein Video-/Canvas-Element (anders als z.B. ZXing, das ein
 * fertiges <video>-Element erwartet).
 */
window.ScandyCamera = (function () {
  function vibrate(pattern) {
    if (navigator.vibrate) {
      try { navigator.vibrate(pattern); } catch (e) { /* manche Browser lehnen ohne User-Geste ab */ }
    }
  }

  function attach(cfg) {
    var scanner = null;

    function showUnsupported(msg) {
      cfg.startBtn.style.display = "none";
      if (cfg.unsupportedMsg) {
        cfg.unsupportedMsg.textContent = msg;
        cfg.unsupportedMsg.style.display = "block";
      }
    }

    function stopCamera() {
      cfg.wrap.style.display = "none";
      cfg.startBtn.style.display = "block";
      if (cfg.hideWhileActive) { cfg.hideWhileActive.style.display = ""; }
      document.body.classList.remove("camera-active");
      if (scanner) {
        var s = scanner;
        scanner = null;
        s.stop().then(function () {
          try { s.clear(); } catch (e) { /* bereits geleert */ }
        }).catch(function () { /* war schon gestoppt */ });
      }
    }

    if (!window.isSecureContext) {
      showUnsupported("Kamera-Scan benötigt eine sichere Verbindung (HTTPS). Bitte per Scanner oder Tastatur eingeben.");
      return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      showUnsupported("Kamera-Zugriff wird von diesem Browser nicht unterstützt.");
      return;
    }
    if (typeof Html5Qrcode === "undefined") {
      showUnsupported("Kamera-Scan-Bibliothek konnte nicht geladen werden (kein Internetzugriff?).");
      return;
    }

    cfg.startBtn.addEventListener("click", function () {
      cfg.startBtn.style.display = "none";
      cfg.wrap.style.display = "block";
      if (cfg.hideWhileActive) { cfg.hideWhileActive.style.display = "none"; }
      document.body.classList.add("camera-active");
      cfg.wrap.scrollIntoView({ behavior: "smooth", block: "start" });

      scanner = new Html5Qrcode(cfg.videoContainerId);
      scanner.start(
        { facingMode: "environment" }, // Rückkamera bevorzugen (Barcodes werden selten mit der Frontkamera gescannt)
        { fps: 10, qrbox: { width: 250, height: 150 } },
        function (decodedText) {
          vibrate(80);
          cfg.input.value = decodedText;
          stopCamera();
          if (cfg.onScan) {
            cfg.onScan(decodedText);
          } else if (cfg.input.form) {
            cfg.input.form.requestSubmit();
          }
        },
        function () { /* kein Code in diesem Frame erkannt - kein echter Fehler, wird pro Frame aufgerufen */ }
      ).catch(function () {
        showUnsupported("Kamera konnte nicht gestartet werden: kein Zugriff erteilt oder keine Kamera gefunden.");
        cfg.wrap.style.display = "none";
        cfg.startBtn.style.display = "block";
        if (cfg.hideWhileActive) { cfg.hideWhileActive.style.display = ""; }
        document.body.classList.remove("camera-active");
        scanner = null;
      });
    });

    if (cfg.cancelBtn) {
      cfg.cancelBtn.addEventListener("click", stopCamera);
    }
  }

  return { attach: attach, vibrate: vibrate };
})();
