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

  // Auf Werkzeug-/Material-Etiketten und Mitarbeiterausweisen kommen in der
  // Praxis nur 1D-Barcodes (per Label-Drucker/Ausweisdrucker) oder ein
  // gelegentlicher QR-Code vor - nie Aztec/Data-Matrix/PDF417/RSS. Den
  // Decoder auf diese Teilmenge zu beschränken spart pro Frame spürbar
  // Rechenzeit (der JS-Fallback-Decoder probiert sonst ALLE ~15 Formate
  // durch), was bei schwachen Geräten/schlechtem Licht direkt mehr
  // tatsächlich ausgewertete Frames pro Sekunde bedeutet.
  var SCAN_FORMATS = typeof Html5QrcodeSupportedFormats !== "undefined" ? [
    Html5QrcodeSupportedFormats.QR_CODE,
    Html5QrcodeSupportedFormats.CODE_128,
    Html5QrcodeSupportedFormats.CODE_39,
    Html5QrcodeSupportedFormats.CODE_93,
    Html5QrcodeSupportedFormats.EAN_13,
    Html5QrcodeSupportedFormats.EAN_8,
    Html5QrcodeSupportedFormats.UPC_A,
    Html5QrcodeSupportedFormats.UPC_E,
    Html5QrcodeSupportedFormats.CODABAR,
    Html5QrcodeSupportedFormats.ITF,
  ] : undefined;

  function attach(cfg) {
    var scanner = null;
    var controlsEl = null;
    var centerContent = cfg.centerContent !== false; // Default true

    function showUnsupported(msg) {
      cfg.startBtn.style.display = "none";
      if (cfg.unsupportedMsg) {
        cfg.unsupportedMsg.textContent = msg;
        cfg.unsupportedMsg.style.display = "block";
      }
    }

    // Taschenlampe/Zoom sind pro Gerät/Browser unterschiedlich unterstützt
    // (v.a. iOS Safari bietet praktisch keins von beiden über die Web-API) -
    // deshalb erst NACH erfolgreichem Kamerastart per Track-Capabilities
    // geprüft und nur bei tatsächlicher Unterstützung eingeblendet, statt
    // feste Buttons in jedem Template zu duplizieren.
    function buildControls() {
      var container = document.createElement("div");
      container.className = "camera-extras";

      // Rein optische Zielhilfe, OHNE Einfluss auf den tatsächlichen
      // Scan-Bereich (der ist jetzt das ganze Kamerabild, s. start()-Config
      // oben) - gibt trotzdem eine Orientierung, wo man den Barcode grob
      // hinhalten sollte, ohne dass er exakt hineinpassen muss.
      var videoEl = document.getElementById(cfg.videoContainerId);
      if (videoEl) {
        var guide = document.createElement("div");
        guide.className = "camera-viewfinder-hint";
        videoEl.appendChild(guide);
      }

      // Verbleibender Rest-Grund für "wird nicht erkannt", wenn der Code
      // trotzdem im Bild ist: er ist schlicht zu klein abgebildet (zu wenig
      // Pixel pro Balken) oder wird schräg statt frontal fotografiert
      // (verzerrt die Balkenbreiten, auf denen 1D-Codes beruhen). Als fester
      // Hinweis statt erst nach einem Fehlversuch, da es pro Frame keinen
      // expliziten "nicht erkannt"-Fehler gibt, der das erklären könnte.
      var hint = document.createElement("p");
      hint.className = "camera-hint";
      hint.textContent = "Barcode muss nicht exakt in den Rahmen passen - aber je größer/näher und gerader er im Bild ist, desto zuverlässiger klappt's.";
      container.appendChild(hint);

      var caps;
      try {
        caps = scanner.getRunningTrackCameraCapabilities();
      } catch (e) {
        caps = null; // Track-Capabilities auf diesem Gerät/Browser nicht abrufbar - Hinweistext trotzdem zeigen
      }

      var row = document.createElement("div");
      row.className = "camera-controls";

      var torch = caps ? caps.torchFeature() : null;
      if (torch && torch.isSupported()) {
        var torchOn = false;
        var torchBtn = document.createElement("button");
        torchBtn.type = "button";
        torchBtn.className = "btn btn-ghost camera-torch-btn";
        torchBtn.textContent = "🔦 Licht";
        torchBtn.addEventListener("click", function () {
          torchOn = !torchOn;
          torch.apply(torchOn).catch(function () { torchOn = !torchOn; });
          torchBtn.classList.toggle("is-active", torchOn);
        });
        row.appendChild(torchBtn);
      }

      var zoom = caps ? caps.zoomFeature() : null;
      if (zoom && zoom.isSupported() && zoom.max() > zoom.min()) {
        var zoomWrap = document.createElement("label");
        zoomWrap.className = "camera-zoom-control";
        zoomWrap.textContent = "🔍";
        var zoomSlider = document.createElement("input");
        zoomSlider.type = "range";
        zoomSlider.min = zoom.min();
        zoomSlider.max = zoom.max();
        zoomSlider.step = zoom.step() || 0.1;
        zoomSlider.value = zoom.value() || zoom.min();
        zoomSlider.setAttribute("aria-label", "Zoom für kleine Barcodes");
        zoomSlider.addEventListener("input", function () {
          zoom.apply(Number(zoomSlider.value)).catch(function () { /* Gerät lehnt Wert ab - ignorieren */ });
        });
        zoomWrap.appendChild(zoomSlider);
        row.appendChild(zoomWrap);
      }

      if (row.children.length > 0) {
        container.appendChild(row);
      }
      cfg.wrap.insertBefore(container, cfg.cancelBtn || null);
      controlsEl = container;
    }

    function stopCamera() {
      cfg.wrap.style.display = "none";
      cfg.startBtn.style.display = "block";
      if (cfg.hideWhileActive) { cfg.hideWhileActive.style.display = ""; }
      document.body.classList.remove("camera-active");
      if (centerContent) { document.body.classList.remove("camera-active-centered"); }
      // Barcode-Feld direkt wieder fokussieren: nach "Kamera schließen" ist
      // die naheliegendste nächste Aktion, den Code per Scanner-Pistole oder
      // Tastatur einzugeben - ohne das müsste erst manuell reingeklickt
      // werden, und auf Mobilgeräten kann der Reflow (Kamera-Bereich
      // verschwindet, Seite springt zurück) sonst zu einem Fehltipp auf die
      // jetzt verschobenen darunterliegenden Elemente führen.
      if (cfg.input) { cfg.input.focus(); }
      if (controlsEl) {
        controlsEl.remove();
        controlsEl = null;
      }
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
      // formatsToSupport/experimentalFeatures/verbose werden vom Konstruktor
      // gelesen, NICHT von start()'s Konfiguration (Quelle: Html5Qrcode-
      // Konstruktor vs. .start() im Bundle geprüft) - useBarCodeDetectorIfSupported
      // stand vorher irrtümlich in start()'s Config und wurde dadurch
      // stillschweigend ignoriert, die native (robustere) BarcodeDetector-API
      // kam also nie tatsächlich zum Einsatz.
      scanner = new Html5Qrcode(cfg.videoContainerId, {
        formatsToSupport: SCAN_FORMATS,
        verbose: false,
        // Nutzt die native Browser-BarcodeDetector-API, wo verfügbar (Chrome/Edge
        // auf Android u.a.) - deutlich toleranter gegenüber Rotation/Winkel/
        // schlechtem Kontrast als der mitgelieferte JS-Decoder. Fällt automatisch
        // auf diesen zurück, wo nicht unterstützt (u.a. Safari/iOS).
        experimentalFeatures: { useBarCodeDetectorIfSupported: true },
      });
      scanner.start(
        { facingMode: "environment" }, // Rückkamera bevorzugen (Barcodes werden selten mit der Frontkamera gescannt)
        {
          fps: 10,
          // Bewusst KEIN qrbox: ohne dieses Feld deckt der Scan-Bereich das
          // GESAMTE Kamerabild ab statt nur einen eng eingegrenzten
          // Ausschnitt (Quelle: Html5Qrcode-internes setupUi() im Bundle
          // geprüft - "qrbox: undefined" -> Scan-Dimensionen = volle
          // Video-Breite/-Höhe). Nutzer mussten den Barcode vorher exakt in
          // einen kleinen weißen Kasten einpassen, was bei allem außer
          // perfekt zentrierter/großer Positionierung zu Fehlerkennungen
          // führte - der Decoder sucht jetzt selbst im ganzen Bild danach,
          // an beliebiger Position/Größe. Der Rahmen in .camera-viewfinder-
          // hint (siehe buildControls) ist nur noch eine optische
          // Zielhilfe ohne Einfluss auf den tatsächlichen Scan-Bereich.
          // Explizite Auflösungsanfrage statt der Browser-Default-Auflösung
          // (oft nur 640x480) - kleine/dicht gedruckte Barcodes brauchen
          // mehr Rohpixel, um überhaupt lesbar aufgelöst zu werden. "ideal"
          // statt "min"/"exact": fällt auf schwächeren Geräten/Kameras ohne
          // Fehler auf das Machbare zurück, statt den Kamerastart abzulehnen.
          videoConstraints: {
            facingMode: "environment",
            width: { ideal: 1920 },
            height: { ideal: 1080 },
          },
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
      ).then(function () {
        buildControls();
      }).catch(function () {
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
