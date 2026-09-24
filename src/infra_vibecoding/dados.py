"""
Travas de dados e de ações do Infra Vibecoding.

Equivalente às privacy rules e às conditions de workflow do Bubble, porém fechado por padrão.

LEITURA (US 1.2)
- Toda tabela do sistema herda de ModeloSeguro e tem uma Politica registrada com @politica(Model).
- Ler sem dizer para quem (Model.objects.all(), .filter(), .get(), .count()...) levanta AcessoSemEscopo.
- Leitura normal: Model.objects.para(usuario). Aplica o escopo da política desse usuário.
- Leitura ignorando as regras: Model.objects.como_sistema("motivo"). Exige motivo e fica registrada.
- SQL escrito à mão (Model.objects.raw) é bloqueado.

AÇÕES (US 1.3)
- A política diz quem pode fazer cada ação em pode(usuario, acao, obj). Ação não prevista = ninguém pode.
- Criar:   Model.objects.criar(usuario, campo=valor, ...)
- Editar:  obj.salvar(usuario)      (confere "editar" no registro como está no banco E como vai ficar)
- Excluir: obj.excluir(usuario)     (confere "excluir" no registro como está no banco)
- Ações do negócio: exigir(usuario, "aprovar", obj) antes de executar; pode(...) para só consultar.
- obj.save(), obj.delete(), Model.objects.create() e alterações em massa sem dizer quem levantam
  EscritaSemAutorizacao.
- Gravação ignorando as regras: obj.salvar_como_sistema("motivo"), obj.excluir_como_sistema("motivo"),
  Model.objects.como_sistema("motivo").create(...) / .update(...) / .delete(). Exigem motivo e ficam registradas.
- Sem permissão levanta SemPermissao, que o Django transforma em "403 sem permissão" nas telas.
"""
import logging
from contextlib import contextmanager
from contextvars import ContextVar

from django.core.exceptions import PermissionDenied
from django.db import models

log = logging.getLogger("infra_vibecoding.auditoria")

_REGISTRO = {}
_AUTORIZADOS = ContextVar("infra_vibecoding_autorizados", default=frozenset())
_MODO_SISTEMA = ContextVar("infra_vibecoding_modo_sistema", default=False)


class AcessoSemEscopo(Exception):
    """Consulta ao banco que não passou pela política de acesso."""


class EscritaSemAutorizacao(Exception):
    """Gravação ou exclusão que não disse quem está fazendo."""


class SemPermissao(PermissionDenied):
    """O usuário não tem permissão para a ação (vira 403 nas telas)."""


class Politica:
    """Base de toda política. Sem sobrescrever nada, ninguém vê e ninguém faz nada."""

    # Se True, visitantes não logados também passam pelo escopo e pelo pode().
    anonimo = False

    def escopo(self, usuario, qs):
        """Quais registros o usuário encontra (o "Find this in searches" do Bubble)."""
        return qs.none()

    def pode(self, usuario, acao, obj=None):
        """Se o usuário pode fazer a ação ("criar", "editar", "excluir", "aprovar"...).

        obj é o registro (ou None quando a pergunta é genérica, ex.: mostrar o botão "Novo").
        """
        return False


def politica(model):
    """Registra a política de uma tabela: @politica(Pedido) acima da classe da política."""

    def registrar(cls):
        if model in _REGISTRO:
            raise ValueError(f"{model.__name__} já tem política registrada.")
        _REGISTRO[model] = cls()
        return cls

    return registrar


def politica_de(model):
    return _REGISTRO.get(model)


def _exigir_motivo(motivo):
    if not motivo or not str(motivo).strip():
        raise ValueError("Ação como sistema exige um motivo por escrito.")


# Ações: pode / exigir

def pode(usuario, acao, obj_ou_model):
    """Consulta se o usuário pode fazer a ação. Nunca levanta erro, só responde True ou False."""
    model = obj_ou_model if isinstance(obj_ou_model, type) else type(obj_ou_model)
    obj = None if isinstance(obj_ou_model, type) else obj_ou_model
    pol = politica_de(model)
    if pol is None or usuario is None:
        return False
    if not usuario.is_authenticated and not pol.anonimo:
        return False
    return bool(pol.pode(usuario, acao, obj))


def exigir(usuario, acao, obj_ou_model):
    """Igual a pode(), mas bloqueia com SemPermissao quando a resposta é não."""
    if not pode(usuario, acao, obj_ou_model):
        model = obj_ou_model if isinstance(obj_ou_model, type) else type(obj_ou_model)
        log.warning(
            "acesso negado: usuario=%s acao=%s tabela=%s",
            getattr(usuario, "pk", None), acao, model.__name__,
        )
        raise SemPermissao(f"Sem permissão para {acao} em {model.__name__}.")


@contextmanager
def _autorizar(*objs):
    token = _AUTORIZADOS.set(_AUTORIZADOS.get() | {id(o) for o in objs})
    try:
        yield
    finally:
        _AUTORIZADOS.reset(token)


@contextmanager
def _modo_sistema():
    token = _MODO_SISTEMA.set(True)
    try:
        yield
    finally:
        _MODO_SISTEMA.reset(token)


def _autorizado(obj):
    return _MODO_SISTEMA.get() or id(obj) in _AUTORIZADOS.get()


# Consultas

class QuerySetSeguro(models.QuerySet):
    # None = sem escopo, "usuario" = via para(usuario), "sistema" = via como_sistema(motivo)
    _escopo = None

    def _clone(self):
        c = super()._clone()
        c._escopo = self._escopo
        return c

    def _exigir_escopo(self):
        if self._escopo is None:
            raise AcessoSemEscopo(
                f"{self.model.__name__}: leitura sem dizer para quem. "
                f"Use {self.model.__name__}.objects.para(usuario) ou "
                f".como_sistema('motivo')."
            )

    def _exigir_sistema(self, operacao):
        self._exigir_escopo()
        if self._escopo != "sistema":
            raise EscritaSemAutorizacao(
                f"{self.model.__name__}: {operacao} em massa só como sistema. "
                f"Para o usuário, grave um registro por vez com obj.salvar(usuario) "
                f"ou obj.excluir(usuario)."
            )

    def para(self, usuario):
        pol = politica_de(self.model)
        qs = self._clone()
        qs._escopo = "usuario"
        if pol is None or usuario is None:
            return qs.none()
        if not usuario.is_authenticated and not pol.anonimo:
            return qs.none()
        return pol.escopo(usuario, qs)

    def como_sistema(self, motivo):
        _exigir_motivo(motivo)
        log.info("como sistema: %s (motivo: %s)", self.model.__name__, motivo)
        qs = self._clone()
        qs._escopo = "sistema"
        return qs

    # Leitura: todos os pontos em que o Django vai ao banco.
    def _fetch_all(self):
        self._exigir_escopo()
        return super()._fetch_all()

    def iterator(self, *args, **kwargs):
        self._exigir_escopo()
        return super().iterator(*args, **kwargs)

    def count(self):
        self._exigir_escopo()
        return super().count()

    def exists(self):
        self._exigir_escopo()
        return super().exists()

    def aggregate(self, *args, **kwargs):
        self._exigir_escopo()
        return super().aggregate(*args, **kwargs)

    def explain(self, *args, **kwargs):
        self._exigir_escopo()
        return super().explain(*args, **kwargs)

    # Escrita.
    def criar(self, usuario, **campos):
        """Cria um registro conferindo a permissão "criar" do usuário."""
        obj = self.model(**campos)
        obj.salvar(usuario)
        return obj

    def create(self, **campos):
        if self._escopo != "sistema":
            raise EscritaSemAutorizacao(
                f"{self.model.__name__}: criação sem dizer quem está fazendo. "
                f"Use {self.model.__name__}.objects.criar(usuario, ...) "
                f"ou .como_sistema('motivo').create(...)."
            )
        obj = self.model(**campos)
        with _autorizar(obj):
            obj.save(force_insert=True, using=self.db)
        return obj

    def update_or_create(self, *args, **kwargs):
        self._exigir_sistema("atualizar ou criar")
        with _modo_sistema():
            return super().update_or_create(*args, **kwargs)

    def bulk_create(self, objs, *args, **kwargs):
        self._exigir_sistema("criação")
        return super().bulk_create(objs, *args, **kwargs)

    def bulk_update(self, objs, *args, **kwargs):
        self._exigir_sistema("alteração")
        return super().bulk_update(objs, *args, **kwargs)

    def update(self, **kwargs):
        self._exigir_sistema("alteração")
        return super().update(**kwargs)

    def delete(self):
        self._exigir_sistema("exclusão")
        return super().delete()


class GerenciadorSeguro(models.Manager.from_queryset(QuerySetSeguro)):
    def raw(self, *args, **kwargs):
        raise AcessoSemEscopo(
            f"{self.model.__name__}: SQL escrito à mão (raw) é bloqueado pelo Infra Vibecoding."
        )


# Tabelas

class ModeloSeguro(models.Model):
    """Base de toda tabela de um sistema que usa o Infra Vibecoding."""

    objects = GerenciadorSeguro()

    class Meta:
        abstract = True
        # Relações diretas (item.pedido) e exclusões em cascata usam o manager base do Django,
        # sem trava, porque partem de um registro que já foi autorizado.

    def _versao_no_banco(self):
        return type(self)._base_manager.using(self._state.db or "default").filter(pk=self.pk).first()

    def salvar(self, usuario, *args, **kwargs):
        """Grava conferindo a permissão: "criar" se é novo, "editar" se já existe."""
        if self._state.adding:
            exigir(usuario, "criar", self)
        else:
            original = self._versao_no_banco()
            if original is None:
                raise SemPermissao(f"Registro de {type(self).__name__} não encontrado.")
            exigir(usuario, "editar", original)  # pode editar o registro como está hoje
            exigir(usuario, "editar", self)      # e como ele vai ficar
        with _autorizar(self):
            self.save(*args, **kwargs)
        return self

    def excluir(self, usuario):
        """Exclui conferindo a permissão "excluir" no registro como está no banco."""
        original = self._versao_no_banco()
        if original is None:
            raise SemPermissao(f"Registro de {type(self).__name__} não encontrado.")
        exigir(usuario, "excluir", original)
        with _autorizar(self):
            return self.delete()

    def salvar_como_sistema(self, motivo, *args, **kwargs):
        _exigir_motivo(motivo)
        log.info("gravação como sistema: %s pk=%s (motivo: %s)", type(self).__name__, self.pk, motivo)
        with _autorizar(self):
            self.save(*args, **kwargs)
        return self

    def excluir_como_sistema(self, motivo):
        _exigir_motivo(motivo)
        log.info("exclusão como sistema: %s pk=%s (motivo: %s)", type(self).__name__, self.pk, motivo)
        with _autorizar(self):
            return self.delete()

    def save(self, *args, **kwargs):
        if not _autorizado(self):
            raise EscritaSemAutorizacao(
                f"{type(self).__name__}: gravação sem dizer quem está fazendo. "
                f"Use obj.salvar(usuario) ou obj.salvar_como_sistema('motivo')."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if not _autorizado(self):
            raise EscritaSemAutorizacao(
                f"{type(self).__name__}: exclusão sem dizer quem está fazendo. "
                f"Use obj.excluir(usuario) ou obj.excluir_como_sistema('motivo')."
            )
        return super().delete(*args, **kwargs)
