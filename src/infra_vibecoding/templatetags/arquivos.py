"""{% load arquivos %} e {{ registro|arquivo:"campo" }}: nome, tamanho, tipo, eh_imagem e url do arquivo (US 4.1)."""
from django import template

from ..arquivos import arquivo_de

register = template.Library()


@register.filter
def arquivo(registro, campo):
    if registro is None:
        return None
    return arquivo_de(registro, campo)
