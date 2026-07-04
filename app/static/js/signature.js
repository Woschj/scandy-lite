/*
 * Signatur-Pad für die Ausgabe-Bestätigung.
 * Vanilla JS, Maus + Touch, schreibt beim Absenden ein PNG (Data-URL)
 * in das Hidden-Input #signature-data. Blockiert das Absenden, wenn
 * noch nicht unterschrieben wurde.
 */
(function () {
  const canvas = document.getElementById("signature-pad");
  if (!canvas) return;

  const form = canvas.closest("form");
  const hiddenInput = document.getElementById("signature-data");
  const clearBtn = document.getElementById("signature-clear");
  const hint = document.getElementById("signature-hint");
  const ctx = canvas.getContext("2d");

  let drawing = false;
  let hasDrawn = false;

  function resizeCanvas() {
    // Canvas intern in Gerätepixeln führen, damit die Unterschrift scharf bleibt
    const ratio = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * ratio;
    canvas.height = rect.height * ratio;
    ctx.scale(ratio, ratio);
    ctx.lineWidth = 2.2;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "#14201d";
  }
  resizeCanvas();

  function pos(e) {
    const rect = canvas.getBoundingClientRect();
    const source = e.touches ? e.touches[0] : e;
    return { x: source.clientX - rect.left, y: source.clientY - rect.top };
  }

  function start(e) {
    e.preventDefault();
    drawing = true;
    const p = pos(e);
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
  }

  function move(e) {
    if (!drawing) return;
    e.preventDefault();
    const p = pos(e);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    hasDrawn = true;
    if (hint) hint.style.display = "none";
  }

  function end() {
    drawing = false;
  }

  canvas.addEventListener("mousedown", start);
  canvas.addEventListener("mousemove", move);
  window.addEventListener("mouseup", end);
  canvas.addEventListener("touchstart", start, { passive: false });
  canvas.addEventListener("touchmove", move, { passive: false });
  canvas.addEventListener("touchend", end);

  if (clearBtn) {
    clearBtn.addEventListener("click", function () {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      hasDrawn = false;
      if (hint) hint.style.display = "";
    });
  }

  if (form) {
    form.addEventListener("submit", function (e) {
      if (!hasDrawn) {
        e.preventDefault();
        if (hint) {
          hint.style.display = "";
          hint.textContent = "Bitte zuerst unterschreiben.";
          hint.style.color = "var(--danger)";
        }
        return;
      }
      hiddenInput.value = canvas.toDataURL("image/png");
    });
  }
})();
