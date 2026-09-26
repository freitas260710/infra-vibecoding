"""
Código do pedido (US 6.1, D60): cada clique no sistema ganha um código curto. Tudo o que acontece dentro daquele
clique leva o mesmo código: o histórico das alterações, o registro de acessos e, se der erro, o código do erro
(E-<código>) e o erro no Sentry. Partindo de qualquer ponta, acha-se o resto na tela de Registros.

Vem ligado pelo 00 como o PRIMEIRO item do MIDDLEWARE (SEC.E131). A resposta leva o cabeçalho X-Codigo-Pedido.
Fora de um clique (comando de terminal, rotina), o código fica vazio.
"""
import secrets
from contextvars import ContextVar

_LETRAS = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_PEDIDO = ContextVar("infra_vibecoding_pedido", default=None)  # (código, request)


def novo_codigo():
    return "".join(secrets.choice(_LETRAS) for _ in range(8))


def codigo_atual():
    atual = _PEDIDO.get()
    return atual[0] if atual else ""


def pessoa_atual():
    """E-mail de quem está logado no clique atual (ou "" fora de um clique ou sem login)."""
    atual = _PEDIDO.get()
    if not atual:
        return ""
    usuario = getattr(atual[1], "user", None)
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return ""
    return getattr(usuario, "email", "") or str(usuario.pk)


def endereco_atual():
    atual = _PEDIDO.get()
    if not atual:
        return ""
    from .limites import endereco_de

    return endereco_de(atual[1])


class CodigoDoPedido:
    """Middleware: dá um código a cada pedido e o devolve no cabeçalho X-Codigo-Pedido."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        codigo = novo_codigo()
        request.codigo_do_pedido = codigo
        token = _PEDIDO.set((codigo, request))
        try:
            resposta = self.get_response(request)
        finally:
            _PEDIDO.reset(token)
        resposta["X-Codigo-Pedido"] = codigo
        return resposta
