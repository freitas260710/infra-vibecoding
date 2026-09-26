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


class Historico(ModeloSeguro):
    """Histórico automático (US 6.1, D36): toda criação, alteração e exclusão de qualquer tabela do sistema, por
    qualquer caminho, com o antes e o depois de cada campo. Ninguém edita nem apaga. Guardado para sempre (D60)."""

    ACOES = [("criou", "criou"), ("alterou", "alterou"), ("excluiu", "excluiu"), ("acao", "ação")]

    quando = models.DateTimeField("quando", auto_now_add=True, db_index=True)
    pedido = models.CharField("código do pedido", max_length=16, blank=True, db_index=True)
    pessoa = models.CharField("pessoa logada", max_length=254, blank=True, db_index=True)
    autor = models.CharField("quem gravou", max_length=254)
    como_sistema = models.BooleanField("como sistema", default=False)
    motivo = models.TextField("motivo", blank=True)
    tabela = models.CharField("tabela", max_length=100)
    registro = models.CharField("registro", max_length=64)
    rotulo = models.CharField("rótulo", max_length=200, blank=True)
    acao = models.CharField("ação", max_length=10, choices=ACOES)
    nome_da_acao = models.CharField("nome da ação", max_length=120, blank=True)
    mudancas = models.JSONField("mudanças", default=dict, blank=True)

    _somente_inclusao = True  # alteração e exclusão em massa também são recusadas (QuerySetSeguro)

    class Meta:
        verbose_name = "histórico"
        verbose_name_plural = "histórico"
        ordering = ["-quando", "-id"]
        indexes = [models.Index(fields=["tabela", "registro"])]

    def __str__(self):
        return f"{self.quando:%d/%m/%Y %H:%M} {self.autor} {self.get_acao_display()} {self.tabela} {self.registro}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("O histórico não pode ser alterado.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("O histórico não pode ser apagado.")


class Acesso(ModeloSeguro):
    """Registro de acessos (US 6.2, D60): entradas, senhas erradas, bloqueios, saídas, acessos negados, verificação em
    duas etapas, senha, links de acesso, downloads, planilhas, tela de banco e erros. Ninguém edita. Guardado por um
    ano: o mais antigo é apagado pela limpeza (infra_vibecoding.acessos.limpar_acessos_antigos)."""

    TIPOS = [
        ("entrou", "entrou"), ("senha_errada", "senha errada"), ("bloqueado", "bloqueado"), ("saiu", "saiu"),
        ("negado", "acesso negado"), ("dois_fatores", "verificação em duas etapas"), ("senha", "senha"),
        ("link", "link de acesso"), ("download", "download"), ("planilha", "planilha"),
        ("tela_de_banco", "tela de banco"), ("erro", "erro"),
    ]

    quando = models.DateTimeField("quando", auto_now_add=True, db_index=True)
    pedido = models.CharField("código do pedido", max_length=16, blank=True, db_index=True)
    tipo = models.CharField("tipo", max_length=20, choices=TIPOS, db_index=True)
    pessoa = models.CharField("pessoa", max_length=254, blank=True, db_index=True)
    endereco = models.CharField("endereço de internet", max_length=45, blank=True)
    navegador = models.CharField("navegador", max_length=300, blank=True)
    tela = models.CharField("tela", max_length=300, blank=True)
    detalhe = models.CharField("detalhe", max_length=500, blank=True)

    _somente_inclusao = True  # só a limpeza de um ano apaga (pelo gerenciador base, nunca pelas telas)

    class Meta:
        verbose_name = "registro"
        verbose_name_plural = "registros"
        ordering = ["-quando", "-id"]

    def __str__(self):
        return f"{self.quando:%d/%m/%Y %H:%M} {self.get_tipo_display()} {self.pessoa}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("O registro de acessos não pode ser alterado.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("O registro de acessos não pode ser apagado um a um. Só a limpeza de um ano apaga.")
