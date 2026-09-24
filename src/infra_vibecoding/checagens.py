"""
Checagens do Infra Vibecoding. Rodam sempre que o sistema liga (runserver, migrate, check, deploy).
Qualquer erro aqui impede o sistema de subir.
"""
import sysconfig
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.checks import Error, Tags, register

from .dados import ModeloSeguro, politica_de

_PASTAS_DE_BIBLIOTECAS = {
    Path(p).resolve()
    for p in (sysconfig.get_paths()["purelib"], sysconfig.get_paths()["platlib"])
}


def _eh_do_sistema(app_config):
    """App escrito no próprio sistema: fica dentro de BASE_DIR e fora das bibliotecas instaladas."""
    base = getattr(settings, "BASE_DIR", None)
    if base is None or app_config.name == "infra_vibecoding":
        return False
    caminho = Path(app_config.path).resolve()
    if any(caminho == p or p in caminho.parents for p in _PASTAS_DE_BIBLIOTECAS):
        return False
    base = Path(base).resolve()
    return caminho == base or base in caminho.parents


def verificar_modelo(model):
    """Erros de trava de dados de uma tabela (lista vazia = ok)."""
    nome = f"{model._meta.app_label}.{model.__name__}"
    if not issubclass(model, ModeloSeguro):
        return [Error(
            f"{nome} não herda de ModeloSeguro.",
            hint="Troque models.Model por infra_vibecoding.dados.ModeloSeguro.",
            obj=model,
            id="SEC.E021",
        )]
    if politica_de(model) is None:
        return [Error(
            f"{nome} não tem política de acesso.",
            hint=f"Crie @politica({model.__name__}) no arquivo politicas.py do app {model._meta.app_label}.",
            obj=model,
            id="SEC.E022",
        )]
    return []


@register(Tags.models)
def sec02_toda_tabela_tem_politica(app_configs=None, **kwargs):
    configs = app_configs if app_configs is not None else apps.get_app_configs()
    erros = []
    for cfg in configs:
        if _eh_do_sistema(cfg):
            for model in cfg.get_models():
                erros.extend(verificar_modelo(model))
    return erros


# Telas (US 1.4)

NAMESPACES_IGNORADOS = {"admin"}  # o admin tem proteção própria (endurecida na US 1.7)
_MW_AUTH = "django.contrib.auth.middleware.AuthenticationMiddleware"
_MW_LOGIN = "django.contrib.auth.middleware.LoginRequiredMiddleware"


def _percorrer_rotas(padroes, prefixo="", namespace=None):
    from django.urls import URLPattern, URLResolver

    for p in padroes:
        if isinstance(p, URLResolver):
            ns = p.namespace or namespace
            if ns in NAMESPACES_IGNORADOS:
                continue
            yield from _percorrer_rotas(p.url_patterns, prefixo + str(p.pattern), ns)
        elif isinstance(p, URLPattern):
            yield prefixo + str(p.pattern), p.callback


@register(Tags.urls)
def sec04_toda_tela_declara_acesso(app_configs=None, **kwargs):
    from django.urls import get_resolver

    from .telas import acesso_declarado

    if not getattr(settings, "ROOT_URLCONF", None):
        return []
    erros = []
    for rota, view in _percorrer_rotas(get_resolver().url_patterns):
        if acesso_declarado(view) is None:
            nome = getattr(view, "__name__", repr(view))
            erros.append(Error(
                f"Tela '/{rota}' ({nome}) não declara quem pode abrir.",
                hint="Use @publica, @logado ou @exige(acao, Model) de infra_vibecoding.telas.",
                id="SEC.E041",
            ))
    return erros


@register(Tags.security)
def sec06_login_obrigatorio_por_padrao(app_configs=None, **kwargs):
    mw = list(getattr(settings, "MIDDLEWARE", []))
    if _MW_LOGIN not in mw:
        return [Error(
            "LoginRequiredMiddleware ausente: as telas ficariam abertas por padrão.",
            hint=f"Inclua '{_MW_LOGIN}' em MIDDLEWARE, logo depois do AuthenticationMiddleware.",
            id="SEC.E061",
        )]
    if _MW_AUTH not in mw or mw.index(_MW_LOGIN) < mw.index(_MW_AUTH):
        return [Error(
            "LoginRequiredMiddleware precisa vir depois do AuthenticationMiddleware.",
            id="SEC.E062",
        )]
    return []


# Configurações de segurança (US 1.5)

_MW_OBRIGATORIOS = {
    "django.middleware.security.SecurityMiddleware": "SEC.E063",
    "django.middleware.csrf.CsrfViewMiddleware": "SEC.E064",
    "django.middleware.clickjacking.XFrameOptionsMiddleware": "SEC.E065",
}
_HSTS_MINIMO = 60 * 60 * 24 * 365
_SESSAO_MAXIMA = 60 * 60 * 24 * 30


@register(Tags.security)
def sec01_configuracoes_de_seguranca(app_configs=None, **kwargs):
    s = settings
    erros = []

    def erro(msg, id, hint=None):
        erros.append(Error(msg, hint=hint, id=id))

    if not hasattr(s, "AMBIENTE"):
        erro(
            "As configurações do Infra Vibecoding não foram importadas.",
            "SEC.E010",
            hint="Coloque 'from infra_vibecoding.configuracoes import *' no início do settings.py.",
        )
        return erros

    hashers = list(getattr(s, "PASSWORD_HASHERS", []))
    if not hashers or not hashers[0].endswith("Argon2PasswordHasher"):
        erro("A senha não é guardada com Argon2 (primeiro item de PASSWORD_HASHERS).", "SEC.E011")

    if not s.SESSION_COOKIE_HTTPONLY:
        erro("SESSION_COOKIE_HTTPONLY desligado: o cookie de login ficaria legível por JavaScript.", "SEC.E012")

    if s.SESSION_COOKIE_AGE > _SESSAO_MAXIMA:
        erro("SESSION_COOKIE_AGE acima de 30 dias.", "SEC.E019")

    validadores = {v.get("NAME", "").rsplit(".", 1)[-1]: v for v in getattr(s, "AUTH_PASSWORD_VALIDATORS", [])}
    minimo = validadores.get("MinimumLengthValidator", {}).get("OPTIONS", {}).get("min_length", 8)
    if "MinimumLengthValidator" not in validadores or minimo < 10:
        erro("Política de senha fraca: tamanho mínimo precisa ser 10 ou mais.", "SEC.E017")
    if "CommonPasswordValidator" not in validadores:
        erro("Política de senha fraca: senhas comuns (ex.: 123456) não estão bloqueadas.", "SEC.E017")

    if getattr(s, "X_FRAME_OPTIONS", None) != "DENY":
        erro("X_FRAME_OPTIONS precisa ser 'DENY' (o sistema não pode ser aberto dentro de outro site).", "SEC.E016")

    mw = list(getattr(s, "MIDDLEWARE", []))
    for caminho, id in _MW_OBRIGATORIOS.items():
        if caminho not in mw:
            erro(f"{caminho.rsplit('.', 1)[-1]} ausente de MIDDLEWARE.", id)

    if s.AMBIENTE == "producao":
        if s.DEBUG:
            erro("DEBUG ligado em produção.", "SEC.E014")
        if len(s.SECRET_KEY) < 50 or len(set(s.SECRET_KEY)) < 5 or s.SECRET_KEY.startswith("dev-inseguro"):
            erro("SECRET_KEY de produção ausente, curta, repetitiva ou de desenvolvimento.", "SEC.E015")
        if not s.ALLOWED_HOSTS or "*" in s.ALLOWED_HOSTS:
            erro("ALLOWED_HOSTS de produção vazio ou com '*'.", "SEC.E020")
        for nome in ("SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "SECURE_SSL_REDIRECT"):
            if not getattr(s, nome, False):
                erro(f"{nome} desligado em produção.", "SEC.E013")
        if getattr(s, "SECURE_HSTS_SECONDS", 0) < _HSTS_MINIMO:
            erro("SECURE_HSTS_SECONDS abaixo de 1 ano em produção.", "SEC.E013")

    return erros


# Tela de banco / admin (US 1.6)

def verificar_admin(site=None):
    """Toda tabela do sistema registrada no admin precisa usar AdminSeguro."""
    from django.contrib import admin as dj_admin

    from .admin import AdminSeguro

    site = site or dj_admin.site
    erros = []
    for model, model_admin in site._registry.items():
        if issubclass(model, ModeloSeguro) and not isinstance(model_admin, AdminSeguro):
            erros.append(Error(
                f"{model._meta.label} está no admin sem AdminSeguro.",
                hint="Registre com admin.site.register(Model, AdminSeguro) de infra_vibecoding.admin.",
                obj=model,
                id="SEC.E071",
            ))
    return erros


@register(Tags.admin)
def sec07_admin_protegido(app_configs=None, **kwargs):
    if not apps.is_installed("django.contrib.admin"):
        return []
    return verificar_admin()


@register(Tags.urls)
def sec07_endereco_do_admin(app_configs=None, **kwargs):
    from django.urls import URLResolver, get_resolver

    if not getattr(settings, "ROOT_URLCONF", None):
        return []
    for p in get_resolver().url_patterns:
        if isinstance(p, URLResolver) and p.namespace == "admin" and str(p.pattern) in ("admin/", "admin"):
            return [Error(
                "O admin está no endereço padrão 'admin/', que robôs testam o tempo todo.",
                hint="Troque por um endereço próprio, ex.: path('gestao-interna/', admin.site.urls).",
                id="SEC.E072",
            )]
    return []


# Checagens silenciadas (US 2.1)

def conferir_checagens_silenciadas(silenciadas):
    """Impede silenciar checagens do 00. Roda ao ligar, antes das checagens.

    Não é uma checagem comum de propósito: uma checagem comum também poderia ser silenciada.
    Aqui o sistema simplesmente não liga.
    """
    from django.core.exceptions import ImproperlyConfigured

    proibidas = sorted(c for c in silenciadas if str(c).strip().upper().startswith("SEC"))
    if proibidas:
        raise ImproperlyConfigured(
            "SILENCED_SYSTEM_CHECKS tenta silenciar checagens do Infra Vibecoding: "
            + ", ".join(proibidas)
            + ". Checagens SEC.* não podem ser silenciadas. Corrija a causa do erro."
        )
