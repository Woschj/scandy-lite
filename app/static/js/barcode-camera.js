/*
 * Wiederverwendbarer Kamera-Barcode-Scanner (html5-qrcode). Kann mehrfach pro
 * Seite eingebunden werden (z.B. ein Scan-Button für den Gegenstand-Barcode
 * UND einer für den Mitarbeiter-Barcode direkt darunter).
 *
 * Nutzung: ScandyCamera.attach({
 *   startBtn, cancelBtn, wrap, videoContainerId, unsupportedMsg, input,
 *   onScan: function(text) { ... },  // optional, Default: Formular absenden
 *   centerContent: true  // optional, Default true - siehe unten
 * });
 *
 * centerContent steuert, ob die Kamera-Karte im verbleibenden Platz vertikal
 * zentriert wird (Klasse "camera-active-centered" auf <body>, siehe app.css).
 * Macht nur Sinn, wenn hideWhileActive auch WIRKLICH fast die ganze Seite
 * ausblendet (Hauptscan-Seite) - blendet hideWhileActive nur ein einzelnes
 * Formularfeld aus und der Rest der Seite (Gegenstand-Karte, Checkliste)
 * bleibt sichtbar, würde die Zentrierung bei Inhalt, der höher als der
 * verfügbare Platz ist, den oberen Teil hinter die Nav schieben und
 * unerreichbar machen - dafür centerContent: false setzen.
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
    var centerContent = cfg.centerContent !== false; // Default true

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
      if (centerContent) { document.body.classList.remove("camera-active-centered"); }
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

    function startScanner() {
      scanner = new Html5Qrcode(cfg.videoContainerId);
      scanner.start(
        { facingMode: "environment" }, // Rückkamera bevorzugen (Barcodes werden selten mit der Frontkamera gescannt)
        {
          fps: 10,
          qrbox: { width: 250, height: 200 }, // etwas quadratischer als vorher (250x150) - mehr Fläche für schräg/gedreht liegende Barcodes
          // Nutzt die native Browser-BarcodeDetector-API, wo verfügbar (Chrome/Edge auf
          // Android u.a.) - deutlich toleranter gegenüber Rotation/Winkel als der
          // mitgelieferte JS-Decoder. Fällt automatisch auf diesen zurück, wo nicht
          // unterstützt (u.a. Safari/iOS) - kein Nachteil, nur potenzieller Zusatznutzen.
          experimentalFeatures: { useBarCodeDetectorIfSupported: true },
        },
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
        if (centerContent) { document.body.classList.remove("camera-active-centered"); }
        scanner = null;
      });
    }

    cfg.startBtn.addEventListener("click", function () {
      cfg.startBtn.style.display = "none";
      cfg.wrap.style.display = "block";
      if (cfg.hideWhileActive) { cfg.hideWhileActive.style.display = "none"; }
      document.body.classList.add("camera-active");
      if (centerContent) { document.body.classList.add("camera-active-centered"); }
      cfg.wrap.scrollIntoView({ behavior: "smooth", block: "start" });

      // html5-qrcode liest beim Start die tatsächliche Breite/Höhe des
      // Video-Containers aus, um Video-/Viewfinder-Größe zu berechnen - der
      // Container war bis eben "display:none" (Breite/Höhe 0). Ohne diese
      // Verzögerung hat der Browser oft noch keinen Layout-Durchlauf für
      // "display:block" abgeschlossen, wenn html5-qrcode misst, wodurch das
      // Kamerabild auf einen viel zu kleinen Bereich zusammenschrumpft statt
      // den Container zu füllen (auf iOS Safari beobachtet). Zwei
      // verschachtelte requestAnimationFrame-Aufrufe warten zuverlässig auf
      // den nächsten fertigen Layout-/Paint-Zyklus.
      requestAnimationFrame(function () {
        requestAnimationFrame(startScanner);
      });
    });

    if (cfg.cancelBtn) {
      cfg.cancelBtn.addEventListener("click", stopCamera);
    }
  }

  return { attach: attach, vibrate: vibrate };
})();
