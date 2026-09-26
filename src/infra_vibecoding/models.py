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
    publico = models.BooleanField("público", default=False)  # decidido no envio: vale para aquele arquivo

    class Meta:
        verbose_name = "arquivo guardado"
        verbose_name_plural = "arquivos guardados"
        indexes = [models.Index(fields=["modelo", "registro"])]

    def __str__(self):
        return self.nome


class LinkDeCompartilhamento(ModeloSeguro):
    """Link de um arquivo privado para quem não é usuário (US 4.2, D58): prazo, cancelável e registrado.
    Guarda só o resumo do código do link: nem quem lê o banco consegue montar o link de novo."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    arquivo = models.ForeignKey(ArquivoGuardado, on_delete=models.CASCADE, related_name="links",
                                verbose_name="arquivo")
    resumo = models.CharField("resumo do código", max_length=64, unique=True, editable=False)
    criado_por = models.CharField("criado por", max_length=254)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    vence_em = models.DateTimeField("vence em")
    cancelado_em = models.DateTimeField("cancelado em", null=True, blank=True)
    cancelado_por = models.CharField("cancelado por", max_length=254, blank=True)
    downloads = models.PositiveIntegerField("downloads", default=0)
    ultimo_download_em = models.DateTimeField("último download em", null=True, blank=True)

    class Meta:
        verbose_name = "link de compartilhamento"
        verbose_name_plural = "links de compartilhamento"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.arquivo.nome} (até {self.vence_em:%d/%m/%Y %H:%M})"

    @property
    def ativo(self):
        from django.utils import timezone

        return self.cancelado_em is None and self.vence_em > timezone.now()

