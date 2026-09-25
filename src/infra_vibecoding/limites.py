"""
Proteção contra força bruta do Infra Vibecoding (US 3.3, D50).

1. Limite geral em TODO pedido (qualquer tela, ação ou pedaço do HTMX), ligado pelo 00 no MIDDLEWARE (SEC.E066):
   - visitante (sem login): até 120 pedidos por minuto por endereço de internet;
   - usuário logado: até 240 pedidos por minuto por usuário (vários colegas no mesmo escritório não se atrapalham).
   Passou do limite: página "muitas tentativas" (código 429), com registro.
2. Login: 5 senhas erradas para o mesmo e-mail em 15 minutos bloqueiam aquele e-mail por 15 minutos, e no máximo
   20 tentativas erradas por endereço de internet em 15 minutos. O bloqueio é temporário de propósito: se fosse
   permanente, qualquer um trancaria a conta dos outros só errando a senha. "Esqueci a senha" continua funcionando.
3. @limite(por_minuto=N): o sistema aperta ações pesadas do negócio (ex.: exportar planilha). Só aperta: o limite
   geral continua valendo.

    from infra_vibecoding.limites import limite

    @exige("exportar", Pedido)
    @limite(por_minuto=5)
    def exportar_pedidos(request): ...

O sistema pode apertar o limite geral (LIMITE_PEDIDOS_POR_ENDERECO e LIMITE_PEDIDOS_POR_USUARIO menores no
settings.py). Afrouxar não: acima do máximo do 00, o sistema não liga (SEC.E067).

A contagem usa o cache do Django: no Mac, na memória; em produção, no banco (vale para todas as cópias do sistema).
Nos testes automáticos (pytest), os limites gerais e o bloqueio de login ficam desligados, para os testes do
sistema não esbarrarem neles; os testes do próprio 00 ligam com LIMITES_NOS_TESTES = True.
"""
import hashlib
import logging
import time
from functools import wraps

from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.template.loader import render_to_string
from django.http import HttpResponse

log = logging.getLogger("infra_vibecoding.auditoria")

MAXIMO_POR_ENDERECO = 120   # pedidos por minuto, visitante
MAXIMO_POR_USUARIO = 240    # pedidos por minuto, usuário logado
LOGIN_POR_EMAIL = 5         # senhas erradas por e-mail...
LOGIN_POR_ENDERECO = 20     # ...e por endereço de internet...
LOGIN_JANELA = 15 * 60      # ...em 15 minutos
LOGIN_BLOQUEIO = 15 * 60    # bloqueio de 15 minutos


def endereco_de(request):
    return request.META.get("REMOTE_ADDR", "") if request is not None else ""


def _em_teste():
    """Rodando nos testes automáticos (o Django cria mail.outbox só neles) e sem pedir os limites ligados."""
    return hasattr(mail, "outbox") and not getattr(settings, "LIMITES_NOS_TESTES", False)


def _chave(tipo, valor):
    return f"infra_vibecoding:{tipo}:" + hashlib.sha256(str(valor).encode()).hexdigest()


def contar(tipo, valor, janela_segundos):
    """Soma mais um na janela atual (janelas fixas) e devolve o total da janela."""
    janela = int(time.time() // janela_segundos)
    chave = f"{_chave(tipo, valor)}:{janela}"
    cache.add(chave, 0, janela_segundos + 5)
    try:
        return cache.incr(chave)
    except ValueError:
        cache.set(chave, 1, janela_segundos + 5)
        return 1


def muitas_tentativas(request, segundos=60):
    corpo = render_to_string("infra_vibecoding/limite.html", {"minutos": max(1, segundos // 60)}, request=request)
    resposta = HttpResponse(corpo, status=429)
    resposta["Retry-After"] = str(segundos)
    return resposta


def limite_por_endereco():
    return min(getattr(settings, "LIMITE_PEDIDOS_POR_ENDERECO", MAXIMO_POR_ENDERECO), MAXIMO_POR_ENDERECO)


def limite_por_usuario():
    return min(getattr(settings, "LIMITE_PEDIDOS_POR_USUARIO", MAXIMO_POR_USUARIO), MAXIMO_POR_USUARIO)


class LimiteDePedidos:
    """Middleware do limite geral. Vem ligado nas configurações do 00, logo depois do AuthenticationMiddleware."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not _em_teste():
            usuario = getattr(request, "user", None)
            if usuario is not None and usuario.is_authenticated:
                if contar("pedidos-usuario", usuario.pk, 60) > limite_por_usuario():
                    log.warning("limite: usuário %s passou de %s pedidos por minuto (%s)",
                                getattr(usuario, "email", usuario.pk), limite_por_usuario(), request.path)
                    return muitas_tentativas(request)
            elif contar("pedidos-endereco", endereco_de(request), 60) > limite_por_endereco():
                log.warning("limite: endereço %s passou de %s pedidos por minuto (%s)",
                            endereco_de(request), limite_por_endereco(), request.path)
                return muitas_tentativas(request)
        return self.get_response(request)


def limite(por_minuto):
    """Aperta o limite de uma tela ou ação do sistema: até `por_minuto` pedidos por minuto por usuário
    (ou por endereço de internet, para visitante)."""

    def conferir(request, nome):
        if _em_teste():
            return None
        usuario = getattr(request, "user", None)
        quem = f"u{usuario.pk}" if usuario is not None and usuario.is_authenticated else endereco_de(request)
        if contar(f"acao:{nome}", quem, 60) > por_minuto:
            log.warning("limite: %s passou de %s por minuto em %s", quem, por_minuto, nome)
            return muitas_tentativas(request)
        return None

    def decorar(view):
        nome = f"{view.__module__}.{view.__qualname__}"
        if isinstance(view, type):
            original = view.dispatch

            def dispatch(self, request, *args, **kwargs):
                return conferir(request, nome) or original(self, request, *args, **kwargs)

            dispatch.__dict__.update(original.__dict__)
            view.dispatch = dispatch
            return view

        @wraps(view)
        def interna(request, *args, **kwargs):
            return conferir(request, nome) or view(request, *args, **kwargs)

        return interna

    return decorar


# Login

def login_bloqueado(email, request):
    """Este e-mail (ou este endereço de internet) está bloqueado por senhas erradas demais?"""
    if _em_teste():
        return False
    return bool(cache.get(_chave("login-bloqueio-email", email))
                or cache.get(_chave("login-bloqueio-endereco", endereco_de(request))))


def registrar_senha_errada(email, request):
    if _em_teste():
        return
    endereco = endereco_de(request)
    if contar("login-erro-email", email, LOGIN_JANELA) >= LOGIN_POR_EMAIL:
        cache.set(_chave("login-bloqueio-email", email), True, LOGIN_BLOQUEIO)
        log.warning("limite: login bloqueado por 15 minutos para %s (senhas erradas demais)", email)
    if contar("login-erro-endereco", endereco, LOGIN_JANELA) >= LOGIN_POR_ENDERECO:
        cache.set(_chave("login-bloqueio-endereco", endereco), True, LOGIN_BLOQUEIO)
        log.warning("limite: login bloqueado por 15 minutos para o endereço %s (tentativas demais)", endereco)
