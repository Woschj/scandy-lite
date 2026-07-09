/*
 * Aktiviert +/- Buttons für alle .qty-stepper-Container auf der Seite.
 * Erwartet Struktur: <div class="qty-stepper"><button data-step="-1">–</button>
 * <input type="number" min="..." max="..."><button data-step="1">+</button></div>
 */
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".qty-stepper").forEach(function (stepper) {
    var input = stepper.querySelector("input");
    if (!input) return;

    stepper.querySelectorAll("button[data-step]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var step = parseInt(btn.dataset.step, 10) || 0;
        var current = parseInt(input.value, 10) || 0;
        var next = current + step;
        var min = input.min !== "" ? parseInt(input.min, 10) : null;
        var max = input.max !== "" ? parseInt(input.max, 10) : null;
        if (min !== null && next < min) next = min;
        if (max !== null && next > max) next = max;
        input.value = next;
        input.dispatchEvent(new Event("change", { bubbles: true }));
      });
    });
  });
});
