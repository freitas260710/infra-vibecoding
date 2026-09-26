"""
Páginas de erro do Infra Vibecoding (US 3.5).

O 00 liga sozinho as páginas de erro em português, sem mostrar nada técnico:
- 404 "não encontrado" (também quando a pessoa tenta abrir um registro que a regra não deixa ver: a página não
  confirma que ele existe);
- 403 "sem permissão" (fica registrado quem tentou e onde);
- 403 "formulário vencido" (proteção CSRF: a página ficou aberta muito tempo);
- 400 "pedido inválido";
- 500 "algo deu errado", com um código curto (ex.: E-7F3K2). O mesmo código vai para o registro, junto com o
  erro completo: quando alguém reclamar, procure o código no registro;
- 429 "muitas tentativas" (limite de pedidos, US 3.3).

Pedido feito por um pedaço da tela (HTMX): a resposta é só uma frase curta, sem a página inteira. O script
infra_vibecoding/erros.js mostra essa frase num aviso no topo da tela (o sistema carrega no base.html).

No computador do desenvolvedor (DEBUG ligado), o Django continua mostrando a página detalhada do erro. Para ver
as páginas de erro como o usuário vê: /erros/ver/404/ (também 400, 403, 403_csrf, 429 e 500). Só no Mac.

Visual: o sistema cria na pasta templates dele o arquivo com o mesmo nome (404.html, 403.html, 403_csrf.html,
400.html, 500.html, infra_vibecoding/limite.html). A página 500 não pode depender do banco nem do usuário logado
e precisa mostrar {{ codigo }} (SEC.E113). O sistema não troca QUANDO cada página aparece: nada de handler404,
handler500 etc. no urls.py (SEC.E111) nem CSRF_FAILURE_VIEW próprio (SEC.E112).
"""
import logging

from django.conf import settings
from django.http import Http404, HttpResponse
from django.template import loader

log = logging.getLogger("infra_vibecoding.erros")
auditoria = logging.getLogger("infra_vibecoding.auditoria")


FRASES = {
    400: "Pedido inválido. Recarregue a página e tente de novo.",
    403: "Você não tem permissão para fazer isso.",
    404: "Não encontrado. Esta página não existe ou você não tem acesso a ela.",
    "csrf": "A página ficou aberta muito tempo. Recarregue e tente de novo.",
    500: "Algo deu errado.",
}


def novo_codigo():
    """Código do erro: o mesmo código do pedido (US 6.1), com "E-" na frente. Fora de um pedido, um código novo."""
    from .pedido import codigo_atual
    from .pedido import novo_codigo as codigo_novo

    return "E-" + (codigo_atual() or codigo_novo())


def _eh_htmx(request):
    return request is not None and bool(request.headers.get("HX-Request"))


def _frase(request, chave, status, codigo=None):
    """Resposta curta para pedido feito por um pedaço da tela (HTMX)."""
    texto = FRASES[chave] + (f" Código do erro: {codigo}." if codigo else "")
    resposta = HttpResponse(texto, status=status, content_type="text/plain; charset=utf-8")
    if codigo:
        resposta["X-Codigo-Erro"] = codigo
    return resposta


def _pagina(request, template, status, contexto=None):
    corpo = loader.render_to_string(template, contexto or {}, request=request)
    return HttpResponse(corpo, status=status)


def pedido_invalido(request, exception=None):
    if _eh_htmx(request):
        return _frase(request, 400, 400)
    return _pagina(request, "400.html", 400)


def sem_permissao(request, exception=None):
    usuario = getattr(request, "user", None)
    quem = getattr(usuario, "email", None) or "visitante"
    auditoria.warning("acesso negado: %s em %s %s", quem, request.method, request.path)
    if _eh_htmx(request):
        return _frase(request, 403, 403)
    return _pagina(request, "403.html", 403)


def nao_encontrado(request, exception=None):
    if _eh_htmx(request):
        return _frase(request, 404, 404)
    return _pagina(request, "404.html", 404)


def erro_interno(request):
    """Erro inesperado. Mostra só o código; o erro completo vai para o registro com o mesmo código.

    A página é montada sem consultar o banco nem o usuário (o erro pode ter sido justamente aí)."""
    codigo = novo_codigo()
    log.error("erro interno %s em %s %s", codigo, getattr(request, "method", ""), getattr(request, "path", ""),
              exc_info=True)
    if _eh_htmx(request):
        return _frase(request, 500, 500, codigo)
    resposta = HttpResponse(loader.get_template("500.html").render({"codigo": codigo}), status=500)
    resposta["X-Codigo-Erro"] = codigo
    return resposta


def formulario_vencido(request, reason=""):
    """Falha da proteção CSRF (CSRF_FAILURE_VIEW): quase sempre, página aberta há muito tempo."""
    auditoria.warning("formulário recusado pela proteção CSRF em %s %s (%s)", request.method, request.path, reason)
    if _eh_htmx(request):
        return _frase(request, "csrf", 403)
    return _pagina(request, "403_csrf.html", 403, {"motivo": reason if settings.DEBUG else ""})


def ligar_paginas_de_erro():
    """Chamado pelo 00 ao ligar: as páginas de erro padrão do Django passam a ser as do 00."""
    from django.conf import urls

    urls.handler400 = "infra_vibecoding.erros.pedido_invalido"
    urls.handler403 = "infra_vibecoding.erros.sem_permissao"
    urls.handler404 = "infra_vibecoding.erros.nao_encontrado"
    urls.handler500 = "infra_vibecoding.erros.erro_interno"


# Ver as páginas no Mac (para ajustar o visual)

_EXEMPLOS = {
    "400": ("400.html", 400, {}),
    "403": ("403.html", 403, {}),
    "403_csrf": ("403_csrf.html", 403, {}),
    "404": ("404.html", 404, {}),
    "429": ("infra_vibecoding/limite.html", 429, {"minutos": 1}),
    "500": ("500.html", 500, {"codigo": "E-EXEMP"}),
}


def ver_pagina_de_erro(request, tipo):
    if not settings.DEBUG or tipo not in _EXEMPLOS:
        raise Http404
    template, status, contexto = _EXEMPLOS[tipo]
    if tipo == "500":
        return HttpResponse(loader.get_template(template).render(contexto), status=status)
    return _pagina(request, template, status, contexto)


def _declarar():
    from .telas import publica

    return publica(ver_pagina_de_erro)


ver_pagina_de_erro = _declarar()
