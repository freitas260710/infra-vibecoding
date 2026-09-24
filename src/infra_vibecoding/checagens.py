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
