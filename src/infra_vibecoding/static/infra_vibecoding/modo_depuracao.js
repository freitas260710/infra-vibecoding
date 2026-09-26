// Painel de rastreio do Infra Vibecoding (US 6.4): com ?debug_mode=true no endereço, os links e formulários do
// próprio sistema levam o debug_mode junto, como no Bubble. Tirando do endereço, o painel some.
(function () {
  "use strict";
  var PARAMETRO = "debug_mode";

  function doSistema(url) {
    return url.origin === window.location.origin && url.pathname.indexOf("/__debug__/") !== 0;
  }

  function comDebug(endereco) {
    try {
      var url = new URL(endereco, window.location.href);
      if (!doSistema(url)) return null;
      url.searchParams.set(PARAMETRO, "true");
      return url.toString();
    } catch (e) {
      return null;
    }
  }

  document.addEventListener("click", function (evento) {
    var link = evento.target.closest ? evento.target.closest("a[href]") : null;
    if (!link || link.closest("#djDebug")) return;
    var href = link.getAttribute("href");
    if (!href || href.charAt(0) === "#" || href.indexOf("javascript:") === 0) return;
    var novo = comDebug(href);
    if (novo) link.setAttribute("href", novo);
  }, true);

  document.addEventListener("submit", function (evento) {
    var formulario = evento.target;
    if (!formulario || !formulario.tagName || formulario.tagName.toLowerCase() !== "form") return;
    var metodo = (formulario.getAttribute("method") || "get").toLowerCase();
    if (metodo === "get") {
      if (!formulario.querySelector('input[name="' + PARAMETRO + '"]')) {
        var campo = document.createElement("input");
        campo.type = "hidden";
        campo.name = PARAMETRO;
        campo.value = "true";
        formulario.appendChild(campo);
      }
    } else {
      var novo = comDebug(formulario.getAttribute("action") || window.location.href);
      if (novo) formulario.setAttribute("action", novo);
    }
  }, true);
})();
