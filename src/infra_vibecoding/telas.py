"""
Travas de telas do Infra Vibecoding (equivalente ao redirect de página do Bubble, porém fechado por padrão).

- Toda tela exige login por padrão (LoginRequiredMiddleware do Django): quem não está logado vai para o login.
- Toda tela declara de que tipo é, com um destes decorators:
      @publica                 qualquer um abre (login, cadastro, página inicial, webhooks assinados)
      @logado                  qualquer usuário logado abre
      @exige("acao", Model)    só abre para quem a política do Model permite a ação
- Tela sem declaração: o sistema não liga (checagem SEC.E041).
- Sem permissão: SemPermissao, que o Django transforma em "403 sem permissão".

Funciona em telas escritas como função e como classe (class-based views).
A tela protegida é a porta. Os dados continuam protegidos pelas travas de dados e de ações.
"""
from functools import wraps

from django.contrib.auth.decorators import login_not_required

from .dados import exigir


def _eh_classe(view):
    return isinstance(view, type)


def _marcar_classe(cls, tipo, antes=None, publica_=False):
    original = cls.dispatch

    def dispatch(self, request, *args, **kwargs):
        if antes is not None:
            antes(request)
        return original(self, request, *args, **kwargs)

    dispatch._acesso = tipo
    if publica_:
        dispatch.login_required = False
    cls.dispatch = dispatch
    cls._acesso = tipo
    return cls


def publica(view):
    """Tela que qualquer um abre, logado ou não."""
    if _eh_classe(view):
        return _marcar_classe(view, "publica", publica_=True)
    view = login_not_required(view)
    view._acesso = "publica"
    return view


def logado(view):
    """Tela que qualquer usuário logado abre."""
    if _eh_classe(view):
        return _marcar_classe(view, "logado")
    view._acesso = "logado"
    return view


def exige(acao, model):
    """Tela que só abre para quem a política de `model` permite `acao`.

    A pergunta é genérica (sem registro): pode(usuario, acao, Model). As conferências de um registro
    específico continuam dentro da tela, com obj.salvar(usuario) e obj.excluir(usuario).
    """
    tipo = f"exige:{acao}:{model.__name__}"

    def conferir(request):
        exigir(request.user, acao, model)

    def decorar(view):
        if _eh_classe(view):
            return _marcar_classe(view, tipo, antes=conferir)

        @wraps(view)
        def interna(request, *args, **kwargs):
            conferir(request)
            return view(request, *args, **kwargs)

        interna._acesso = tipo
        return interna

    return decorar


def acesso_declarado(view):
    """Tipo de acesso declarado por uma tela (ou None)."""
    alvo = getattr(view, "view_class", view)
    tipo = getattr(view, "_acesso", None) or getattr(alvo, "_acesso", None)
    if tipo:
        return tipo
    # Telas do próprio Django marcadas com login_not_required (ex.: LoginView) contam como públicas.
    if getattr(view, "login_required", True) is False:
        return "publica"
    return None
