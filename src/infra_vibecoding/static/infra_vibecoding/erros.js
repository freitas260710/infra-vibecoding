// Infra Vibecoding: aviso de erro nos pedidos feitos por pedaços da tela (HTMX).
// Carregar no base.html do sistema, depois do htmx:
//   <script src="{% static 'infra_vibecoding/erros.js' %}" defer></script>
// Quando um pedido dá erro, o 00 responde uma frase curta (ex.: "Você não tem permissão para fazer isso."),
// e este script mostra a frase num aviso no topo da tela. Para trocar o visual, use a classe iv-aviso-erro.
(function () {
  function avisar(texto) {
    var antigo = document.querySelector(".iv-aviso-erro");
    if (antigo) antigo.remove();
    var aviso = document.createElement("div");
    aviso.className = "iv-aviso-erro";
    aviso.setAttribute("role", "alert");
    aviso.textContent = texto;
    aviso.title = "Clique para fechar";
    aviso.style.cssText = "position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:9999;" +
      "background:#b42318;color:#fff;padding:10px 16px;border-radius:6px;max-width:90%;cursor:pointer;" +
      "font:14px/1.4 system-ui,sans-serif;box-shadow:0 2px 8px rgba(0,0,0,.2)";
    aviso.addEventListener("click", function () { aviso.remove(); });
    document.body.appendChild(aviso);
    setTimeout(function () { aviso.remove(); }, 10000);
  }
  document.addEventListener("htmx:responseError", function (e) {
    var xhr = e.detail.xhr;
    var tipo = xhr.getResponseHeader("Content-Type") || "";
    var texto = tipo.indexOf("text/plain") === 0 && xhr.responseText.length < 300
      ? xhr.responseText : "Algo deu errado. Tente de novo.";
    avisar(texto);
  });
  document.addEventListener("htmx:sendError", function () {
    avisar("Sem conexão com o sistema. Confira a internet e tente de novo.");
  });
})();
