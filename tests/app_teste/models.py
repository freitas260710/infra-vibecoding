from django.conf import settings
from django.db import models

from infra_vibecoding.dados import ModeloSeguro


class Pedido(ModeloSeguro):
    dono = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    titulo = models.CharField(max_length=100)
    valor = models.DecimalField(max_digits=10, decimal_places=2, default=0)


class Rascunho(ModeloSeguro):
    """Tabela com política vazia: ninguém vê nada."""

    texto = models.CharField(max_length=100)
