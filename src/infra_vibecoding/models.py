"""Tabelas do próprio 00. Os sistemas não leem nem gravam nelas direto: só pelas funções do 00."""
import uuid

from django.db import models

from .dados import ModeloSeguro


class ArquivoGuardado(ModeloSeguro):
    """Cada arquivo enviado (US 4.1). Pertence a um registro e a um campo; quem baixa é decidido pela regra desse
    registro. O conteúdo fica no armazenamento de arquivos (pasta local ou nuvem), com nome aleatório."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    modelo = models.CharField("tabela", max_length=100)
    registro = models.CharField("registro", max_length=64, blank=True)
    campo = models.CharField("campo", max_length=100)
    nome = models.CharField("nome original", max_length=255)
    tipo = models.CharField("tipo", max_length=100)
    tamanho = models.BigIntegerField("tamanho (bytes)")
    caminho = models.CharField("onde está guardado", max_length=255)
    espaco = models.CharField("espaço (cota)", max_length=100, blank=True, db_index=True)
    enviado_por = models.CharField("enviado por", max_length=254)
    enviado_em = models.DateTimeField("enviado em", auto_now_add=True)

    class Meta:
        verbose_name = "arquivo guardado"
        verbose_name_plural = "arquivos guardados"
        indexes = [models.Index(fields=["modelo", "registro"])]

    def __str__(self):
        return self.nome
