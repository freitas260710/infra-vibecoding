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

REGRAS QUE CONSULTAM OUTRAS TABELAS (US 2.3)
- Dentro de uma política (escopo ou pode), self.consultar(OutraTabela) lê outra tabela para decidir.
  Ex.: "o usuário tem perfil de Atendimento?" olhando a tabela de perfis.
- Só funciona enquanto o 00 está rodando uma regra. Fora dela (tela, ação, script) levanta AcessoSemEscopo,
  inclusive se a consulta for guardada e usada depois.
- Só lê: criar, alterar ou excluir por ela levanta EscritaSemAutorizacao.
- Não gera registro de auditoria a cada uso (a regra roda em todo pedido). O resultado da regra continua sendo
  só "sim ou não" ou o filtro da própria tabela: o que ela consultou não sai dali.
- escopo() precisa devolver um filtro da própria tabela, a partir do qs recebido. Outra coisa dá erro.
"""
import logging
from contextlib import contextmanager
from contextvars import ContextVar

from django.core.exceptions import PermissionDenied
from django.db import models, transaction

log = logging.getLogger("infra_vibecoding.auditoria")

_REGISTRO = {}
_AUTORIZADOS = ContextVar("infra_vibecoding_autorizados", default=frozenset())
_MODO_SISTEMA = ContextVar("infra_vibecoding_modo_sistema", default=False)
_EM_REGRA = ContextVar("infra_vibecoding_em_regra", default=False)
_VALIDANDO_UNICOS = ContextVar("infra_vibecoding_validando_unicos", default=False)
_LEITURA_ADMIN = ContextVar("infra_vibecoding_leitura_admin", default=False)
_AUTOR = ContextVar("infra_vibecoding_autor", default=("sistema", ""))  # quem está gravando (arquivos, US 4.1)


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

    def consultar(self, model):
        """Lê outra tabela de dentro da regra, só para decidir (o "Do a search for" dentro da privacy rule).

        Só leitura, só enquanto a regra está rodando e sem registro de auditoria a cada uso.
        """
        if not _EM_REGRA.get():
            raise AcessoSemEscopo(
                f"consultar({getattr(model, '__name__', model)}) só funciona dentro de uma regra "
                f"(escopo ou pode de uma política). Fora dela, use .para(usuario) ou .como_sistema('motivo')."
            )
        if not (isinstance(model, type) and issubclass(model, ModeloSeguro)):
            return model._default_manager.all()
        qs = model.objects.all()
        qs._escopo = "regra"
        return qs


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
    with _rodando_regra():
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


@contextmanager
def _rodando_regra():
    token = _EM_REGRA.set(True)
    try:
        yield
    finally:
        _EM_REGRA.reset(token)


@contextmanager
def _validando_unicos():
    token = _VALIDANDO_UNICOS.set(True)
    try:
        yield
    finally:
        _VALIDANDO_UNICOS.reset(token)


@contextmanager
def _leitura_da_tela_de_banco():
    """Durante uma tela da tela de banco (admin), leituras sem escopo são leituras como sistema (US 2.6).

    Só leitura: gravações continuam exigindo salvar_como_sistema / excluir_como_sistema, que o AdminSeguro faz.
    Quem abre a tela e o endereço ficam registrados pelo AdminSeguro.
    """
    token = _LEITURA_ADMIN.set(True)
    try:
        yield
    finally:
        _LEITURA_ADMIN.reset(token)


def _autorizado(obj):
    return _MODO_SISTEMA.get() or id(obj) in _AUTORIZADOS.get()


# Consultas

class QuerySetSeguro(models.QuerySet):
    # None = sem escopo, "usuario" = via para(usuario), "sistema" = via como_sistema(motivo),
    # "regra" = via Politica.consultar(Model), só leitura e só enquanto a regra roda
    _escopo = None
    _motivo = ""

    def _clone(self):
        c = super()._clone()
        c._escopo = self._escopo
        c._motivo = self._motivo
        return c

    def _exigir_escopo(self):
        if self._escopo is None:
            if _VALIDANDO_UNICOS.get():
                return  # conferência de valor repetido (ex.: e-mail já usado): só responde sim ou não
            if _LEITURA_ADMIN.get():
                return  # tela de banco: lê como sistema (filtros laterais, listas de escolha), com registro
            raise AcessoSemEscopo(
                f"{self.model.__name__}: leitura sem dizer para quem. "
                f"Use {self.model.__name__}.objects.para(usuario) ou "
                f".como_sistema('motivo')."
            )
        if self._escopo == "regra" and not _EM_REGRA.get():
            raise AcessoSemEscopo(
                f"{self.model.__name__}: consulta de regra usada fora da regra. "
                f"self.consultar(...) só vale enquanto a política está rodando."
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
        with _rodando_regra():
            resultado = pol.escopo(usuario, qs)
        if (
            not isinstance(resultado, QuerySetSeguro)
            or resultado.model is not self.model
            or resultado._escopo != "usuario"
        ):
            raise TypeError(
                f"A política de {self.model.__name__} precisa devolver, no escopo, um filtro da própria tabela "
                f"feito a partir do qs recebido (ex.: return qs.filter(...)). Nada de devolver outra tabela "
                f"ou uma consulta de regra."
            )
        return resultado

    def como_sistema(self, motivo):
        _exigir_motivo(motivo)
        log.info("como sistema: %s (motivo: %s)", self.model.__name__, motivo)
        qs = self._clone()
        qs._escopo = "sistema"
        qs._motivo = motivo
        return qs

    @contextmanager
    def _como_autor_sistema(self):
        """Gravações feitas por esta consulta "como sistema" entram no histórico com o motivo dela (US 6.1)."""
        token = _AUTOR.set(("sistema", self._motivo))
        try:
            yield
        finally:
            _AUTOR.reset(token)

    def _exigir_que_aceita_mudanca(self, operacao):
        if getattr(self.model, "_somente_inclusao", False):
            raise EscritaSemAutorizacao(f"{self.model.__name__}: {operacao} não é permitida. Só inclusão.")

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
        with self._como_autor_sistema(), _autorizar(obj):
            obj.save(force_insert=True, using=self.db)
        return obj

    def update_or_create(self, *args, **kwargs):
        self._exigir_sistema("atualizar ou criar")
        with self._como_autor_sistema(), _modo_sistema():
            return super().update_or_create(*args, **kwargs)

    # Operações em massa: cada registro afetado entra no histórico (US 6.1, D60), na mesma transação.
    def bulk_create(self, objs, *args, **kwargs):
        self._exigir_sistema("criação")
        from . import historico

        with transaction.atomic(using=self.db), self._como_autor_sistema():
            criados = super().bulk_create(objs, *args, **kwargs)
            historico.depois_de_criar_em_massa(criados)
        return criados

    def bulk_update(self, objs, *args, **kwargs):
        self._exigir_sistema("alteração")
        self._exigir_que_aceita_mudanca("alteração")
        from . import historico

        objs = list(objs)
        with transaction.atomic(using=self.db), self._como_autor_sistema():
            antes = historico.fotos_em_massa(self.model._base_manager.filter(pk__in=[o.pk for o in objs]))
            resultado = super().bulk_update(objs, *args, **kwargs)
            historico.depois_de_alterar_em_massa(self.model, antes)
        return resultado

    def update(self, **kwargs):
        self._exigir_sistema("alteração")
        self._exigir_que_aceita_mudanca("alteração")
        from . import historico

        with transaction.atomic(using=self.db), self._como_autor_sistema():
            antes = historico.fotos_em_massa(self)
            resultado = super().update(**kwargs)
            historico.depois_de_alterar_em_massa(self.model, antes)
        return resultado

    def delete(self):
        self._exigir_sistema("exclusão")
        self._exigir_que_aceita_mudanca("exclusão")
        with transaction.atomic(using=self.db), self._como_autor_sistema():
            return super().delete()  # o histórico de cada registro excluído vem pelo sinal post_delete


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

    # Conferência de campos únicos (ex.: "este e-mail já existe?") feita pelos formulários do Django.
    # É uma leitura que só responde sim ou não, então é liberada durante a conferência (US 2.4).
    def validate_unique(self, exclude=None):
        with _validando_unicos():
            return super().validate_unique(exclude=exclude)

    def validate_constraints(self, exclude=None):
        with _validando_unicos():
            return super().validate_constraints(exclude=exclude)

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
        token = _AUTOR.set(("usuario", usuario))
        try:
            with _autorizar(self):
                self.save(*args, **kwargs)
        finally:
            _AUTOR.reset(token)
        return self

    def excluir(self, usuario):
        """Exclui conferindo a permissão "excluir" no registro como está no banco."""
        original = self._versao_no_banco()
        if original is None:
            raise SemPermissao(f"Registro de {type(self).__name__} não encontrado.")
        exigir(usuario, "excluir", original)
        token = _AUTOR.set(("usuario", usuario))
        try:
            with _autorizar(self):
                return self.delete()
        finally:
            _AUTOR.reset(token)

    def salvar_como_sistema(self, motivo, *args, **kwargs):
        _exigir_motivo(motivo)
        log.info("gravação como sistema: %s pk=%s (motivo: %s)", type(self).__name__, self.pk, motivo)
        token = _AUTOR.set(("sistema", motivo))
        try:
            with _autorizar(self):
                self.save(*args, **kwargs)
        finally:
            _AUTOR.reset(token)
        return self

    def excluir_como_sistema(self, motivo):
        _exigir_motivo(motivo)
        log.info("exclusão como sistema: %s pk=%s (motivo: %s)", type(self).__name__, self.pk, motivo)
        token = _AUTOR.set(("sistema", motivo))
        try:
            with _autorizar(self):
                return self.delete()
        finally:
            _AUTOR.reset(token)

    def save(self, *args, **kwargs):
        if not _autorizado(self):
            raise EscritaSemAutorizacao(
                f"{type(self).__name__}: gravação sem dizer quem está fazendo. "
                f"Use obj.salvar(usuario) ou obj.salvar_como_sistema('motivo')."
            )
        from . import historico

        if not historico.deve_registrar(type(self)):
            return super().save(*args, **kwargs)
        # Histórico automático (US 6.1): a gravação e a linha do histórico entram juntas ou nenhuma entra.
        campos = kwargs.get("update_fields")
        with transaction.atomic(using=kwargs.get("using") or self._state.db or "default"):
            criando = self._state.adding
            antes = None if criando else historico.foto(self, campos)
            resultado = super().save(*args, **kwargs)
            historico.depois_de_salvar(self, antes, criando or antes is None, campos)
        return resultado

    def delete(self, *args, **kwargs):
        if not _autorizado(self):
            raise EscritaSemAutorizacao(
                f"{type(self).__name__}: exclusão sem dizer quem está fazendo. "
                f"Use obj.excluir(usuario) ou obj.excluir_como_sistema('motivo')."
            )
        with transaction.atomic(using=kwargs.get("using") or self._state.db or "default"):
            return super().delete(*args, **kwargs)  # o histórico vem pelo sinal post_delete, na mesma transação
