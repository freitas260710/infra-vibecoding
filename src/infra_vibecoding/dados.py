"""
Travas de dados do Infra Vibecoding (equivalente às privacy rules do Bubble, porém fechado por padrão).

Regras:
- Toda tabela do sistema herda de ModeloSeguro e tem uma Politica registrada com @politica(Model).
- Ler sem dizer para quem (Model.objects.all(), .filter(), .get(), .count()...) levanta AcessoSemEscopo.
- Leitura normal: Model.objects.para(usuario). Aplica a política desse usuário.
- Leitura ignorando as regras: Model.objects.como_sistema("motivo"). Exige motivo e fica registrada no log.
- SQL escrito à mão (Model.objects.raw) é bloqueado.
- Política que não define escopo não mostra nada. Usuário ausente ou anônimo não vê nada
  (a não ser que a política declare anonimo = True).
"""
import logging

from django.db import models

log = logging.getLogger("infra_vibecoding.auditoria")

_REGISTRO = {}


class AcessoSemEscopo(Exception):
    """Consulta ao banco que não passou pela política de acesso."""


class Politica:
    """Base de toda política. Sem sobrescrever nada, ninguém vê nada."""

    # Se True, visitantes não logados também passam pelo escopo (ex.: catálogo público).
    anonimo = False

    def escopo(self, usuario, qs):
        """Quais registros o usuário encontra (o "Find this in searches" do Bubble)."""
        return qs.none()


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


class QuerySetSeguro(models.QuerySet):
    _com_escopo = False

    def _clone(self):
        c = super()._clone()
        c._com_escopo = self._com_escopo
        return c

    def _exigir_escopo(self):
        if not self._com_escopo:
            raise AcessoSemEscopo(
                f"{self.model.__name__}: leitura sem dizer para quem. "
                f"Use {self.model.__name__}.objects.para(usuario) ou "
                f".como_sistema('motivo')."
            )

    def para(self, usuario):
        pol = politica_de(self.model)
        qs = self._clone()
        qs._com_escopo = True
        if pol is None or usuario is None:
            return qs.none()
        if not usuario.is_authenticated and not pol.anonimo:
            return qs.none()
        return pol.escopo(usuario, qs)

    def como_sistema(self, motivo):
        if not motivo or not str(motivo).strip():
            raise ValueError("como_sistema exige um motivo por escrito.")
        log.info("leitura como sistema: %s (motivo: %s)", self.model.__name__, motivo)
        qs = self._clone()
        qs._com_escopo = True
        return qs

    # Todos os pontos em que o Django vai ao banco para ler ou alterar em massa.
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

    def update(self, **kwargs):
        self._exigir_escopo()
        return super().update(**kwargs)

    def delete(self):
        self._exigir_escopo()
        return super().delete()

    def explain(self, *args, **kwargs):
        self._exigir_escopo()
        return super().explain(*args, **kwargs)


class GerenciadorSeguro(models.Manager.from_queryset(QuerySetSeguro)):
    def raw(self, *args, **kwargs):
        raise AcessoSemEscopo(
            f"{self.model.__name__}: SQL escrito à mão (raw) é bloqueado pelo Infra Vibecoding."
        )


class ModeloSeguro(models.Model):
    """Base de toda tabela de um sistema que usa o Infra Vibecoding."""

    objects = GerenciadorSeguro()

    class Meta:
        abstract = True
        # Relações diretas (item.pedido) e exclusões em cascata usam o manager base do Django,
        # sem trava, porque partem de um registro que já foi autorizado.
