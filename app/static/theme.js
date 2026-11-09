/* Modo oscuro: sigue al sistema hasta que la persona elige; la elección se recuerda en este navegador. */
(function () {
  var KEY = "bl-theme", root = document.documentElement, saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) { /* sin almacenamiento: queda el del sistema */ }
  var mq = window.matchMedia ? matchMedia("(prefers-color-scheme: dark)") : null;
  var dark = saved ? saved === "dark" : !!(mq && mq.matches);

  function paint() {
    root.setAttribute("data-theme", dark ? "dark" : "light");
    var m = document.querySelector('meta[name="theme-color"]');
    if (m) m.setAttribute("content", dark ? "#0e151c" : "#15212b");
    var btns = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < btns.length; i++) {
      btns[i].setAttribute("aria-pressed", dark ? "true" : "false");
      btns[i].setAttribute("title", dark ? "Pasar a modo claro" : "Pasar a modo oscuro");
      btns[i].setAttribute("aria-label", dark ? "Pasar a modo claro" : "Pasar a modo oscuro");
      var ico = btns[i].querySelector(".ico, .theme-ico");
      if (ico) ico.textContent = dark ? "\u2600" : "\u263E";
    }
  }
  paint();

  if (mq && mq.addEventListener) {
    mq.addEventListener("change", function (e) { if (!saved) { dark = e.matches; paint(); } });
  }
  document.addEventListener("DOMContentLoaded", function () {
    paint();
    document.addEventListener("click", function (ev) {
      var b = ev.target.closest && ev.target.closest("[data-theme-toggle]");
      if (!b) return;
      dark = !dark;
      saved = dark ? "dark" : "light";
      try { localStorage.setItem(KEY, saved); } catch (e) { /* no se pudo recordar */ }
      paint();
    });
  });
})();
