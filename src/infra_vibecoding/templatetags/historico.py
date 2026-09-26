"""{% load historico %} e {{ registro|historico_url }}: endereço da tela de histórico do registro (US 6.1)."""
from django import template

from ..historico import historico_url as _historico_url

register = template.Library()


@register.filter
def historico_url(registro):
    if registro is None or registro.pk is None:
        return ""
    return _historico_url(registro)
