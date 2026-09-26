from django.conf import settings
from django.db import models

from infra_vibecoding.arquivos import CampoArquivo
from infra_vibecoding.dados import ModeloSeguro
from infra_vibecoding.usuarios import UsuarioSeguro


class UsuarioTeste(UsuarioSeguro):
    """Tabela de usuário dos testes do 00 (US 2.4)."""


class Pedido(ModeloSeguro):
    dono = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    titulo = models.CharField(max_length=100)
    valor = models.DecimalField(max_digits=10, decimal_places=2, default=0)


class Rascunho(ModeloSeguro):
    """Tabela com política vazia: ninguém vê nada."""

    texto = models.CharField(max_length=100)


class ItemPedido(ModeloSeguro):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="itens")
    descricao = models.CharField(max_length=100)


# US 2.3: regras que consultam outras tabelas.

class Setor(ModeloSeguro):
    nome = models.CharField(max_length=50)


class AcessoSetor(ModeloSeguro):
    """Quem tem acesso a qual setor. A política dela é fechada: ninguém lê direto."""

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    setor = models.ForeignKey(Setor, on_delete=models.CASCADE)
    pode_editar = models.BooleanField(default=False)


class Documento(ModeloSeguro):
    setor = models.ForeignKey(Setor, on_delete=models.CASCADE)
    titulo = models.CharField(max_length=100)


# US 4.1: arquivo privado ligado a um registro.

class Anexo(ModeloSeguro):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="anexos")
    arquivo = CampoArquivo(tipos=["imagem", "pdf"], tamanho_max_mb=1, blank=False)
    comprovante = CampoArquivo(tipos=["pdf"], tamanho_max_mb=1)
    foto_publica = CampoArquivo(tipos=["imagem"], publico="foto do pedido na vitrine pública dos testes")
