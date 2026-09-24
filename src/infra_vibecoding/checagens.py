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
