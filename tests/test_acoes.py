"""Testes das travas de ações (US 1.3)."""
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied

from infra_vibecoding.dados import EscritaSemAutorizacao, SemPermissao, exigir, pode
from tests.app_teste.models import Pedido, Rascunho

pytestmark = pytest.mark.django_db
User = get_user_model()
SISTEMA = "preparar teste"


@pytest.fixture
def ana():
    return User.objects.create_user("ana", password="x")


@pytest.fixture
def beto():
    return User.objects.create_user("beto", password="x")


@pytest.fixture
def chefe():
    return User.objects.create_user("chefe", password="x", is_staff=True)


@pytest.fixture
def pedido_da_ana(ana):
    return Pedido.objects.como_sistema(SISTEMA).create(dono=ana, titulo="Pedido da Ana", valor=10)


def no_banco(pedido):
    return Pedido.objects.como_sistema(SISTEMA).get(pk=pedido.pk)


# 1. Gravar sem dizer quem está fazendo é bloqueado, por qualquer caminho.
def test_save_direto_de_registro_novo_e_bloqueado(ana):
    with pytest.raises(EscritaSemAutorizacao):
        Pedido(dono=ana, titulo="x").save()
    assert Pedido.objects.como_sistema(SISTEMA).count() == 0


def test_save_direto_de_registro_existente_e_bloqueado(pedido_da_ana):
    pedido_da_ana.titulo = "alterado"
    with pytest.raises(EscritaSemAutorizacao):
        pedido_da_ana.save()
    assert no_banco(pedido_da_ana).titulo == "Pedido da Ana"


def test_delete_direto_e_bloqueado(pedido_da_ana):
    with pytest.raises(EscritaSemAutorizacao):
        pedido_da_ana.delete()
    assert Pedido.objects.como_sistema(SISTEMA).count() == 1


def test_create_sem_dizer_quem_e_bloqueado(ana):
    with pytest.raises(EscritaSemAutorizacao):
        Pedido.objects.create(dono=ana, titulo="x")
    with pytest.raises(EscritaSemAutorizacao):
        ana.pedido_set.create(titulo="x")


def test_alteracao_em_massa_pelo_usuario_e_bloqueada(ana, pedido_da_ana):
    with pytest.raises(EscritaSemAutorizacao):
        Pedido.objects.para(ana).update(valor=0)
    with pytest.raises(EscritaSemAutorizacao):
        Pedido.objects.para(ana).delete()
    with pytest.raises(EscritaSemAutorizacao):
        Pedido.objects.para(ana).bulk_create([Pedido(dono=ana, titulo="y")])
    assert no_banco(pedido_da_ana).valor == 10


# 2. Criar confere a permissão.
def test_dono_cria_o_proprio_pedido(ana):
    pedido = Pedido.objects.criar(ana, dono=ana, titulo="Novo")
    assert no_banco(pedido).dono == ana


def test_criar_pedido_em_nome_de_outro_e_bloqueado(ana, beto):
    with pytest.raises(SemPermissao):
        Pedido.objects.criar(beto, dono=ana, titulo="Golpe")
    assert Pedido.objects.como_sistema(SISTEMA).count() == 0


def test_tabela_sem_regra_de_acao_ninguem_cria(chefe):
    with pytest.raises(SemPermissao):
        Rascunho.objects.criar(chefe, texto="x")


# 3. Editar confere a permissão no registro como está e como vai ficar.
def test_dono_edita(ana, pedido_da_ana):
    pedido_da_ana.titulo = "Editado"
    pedido_da_ana.salvar(ana)
    assert no_banco(pedido_da_ana).titulo == "Editado"


def test_outro_usuario_nao_edita(beto, pedido_da_ana):
    pedido_da_ana.titulo = "Invadido"
    with pytest.raises(SemPermissao):
        pedido_da_ana.salvar(beto)
    assert no_banco(pedido_da_ana).titulo == "Pedido da Ana"


def test_golpe_trocar_o_dono_pelo_formulario(ana, beto, pedido_da_ana):
    """A dona tenta passar o pedido para outra pessoa: o registro novo não seria mais dela."""
    pedido_da_ana.dono = beto
    with pytest.raises(SemPermissao):
        pedido_da_ana.salvar(ana)
    assert no_banco(pedido_da_ana).dono == ana


def test_golpe_tomar_pedido_alheio(ana, beto, pedido_da_ana):
    """Beto consegue o registro da Ana e troca o dono para si: no banco o pedido é da Ana."""
    pedido_da_ana.dono = beto
    with pytest.raises(SemPermissao):
        pedido_da_ana.salvar(beto)
    assert no_banco(pedido_da_ana).dono == ana


# 4. Excluir confere a permissão no registro como está no banco.
def test_dono_exclui(ana, pedido_da_ana):
    pedido_da_ana.excluir(ana)
    assert Pedido.objects.como_sistema(SISTEMA).count() == 0


def test_outro_usuario_nao_exclui(ana, beto, pedido_da_ana):
    pedido_da_ana.dono = beto  # tentativa de enganar mudando só a cópia em memória
    with pytest.raises(SemPermissao):
        pedido_da_ana.excluir(beto)
    assert Pedido.objects.como_sistema(SISTEMA).count() == 1


# 5. Ações do negócio e consulta de permissão.
def test_acao_de_negocio_aprovar(ana, chefe, pedido_da_ana):
    exigir(chefe, "aprovar", pedido_da_ana)
    with pytest.raises(SemPermissao):
        exigir(ana, "aprovar", pedido_da_ana)


def test_pode_so_responde(ana, beto, pedido_da_ana):
    assert pode(ana, "editar", pedido_da_ana) is True
    assert pode(beto, "editar", pedido_da_ana) is False
    assert pode(ana, "criar", Pedido) is True  # botão "Novo"
    assert pode(ana, "acao_inexistente", pedido_da_ana) is False


def test_anonimo_e_usuario_ausente_nao_fazem_nada(pedido_da_ana):
    for ninguem in (AnonymousUser(), None):
        assert pode(ninguem, "criar", Pedido) is False
        with pytest.raises(SemPermissao):
            pedido_da_ana.salvar(ninguem)


def test_sem_permissao_vira_403():
    assert issubclass(SemPermissao, PermissionDenied)


# 6. Exceção controlada: como sistema.
def test_gravacao_como_sistema_exige_motivo(ana):
    pedido = Pedido(dono=ana, titulo="x")
    with pytest.raises(ValueError):
        pedido.salvar_como_sistema("")
    with pytest.raises(ValueError):
        Pedido.objects.como_sistema(" ").create(dono=ana, titulo="x")


def test_gravacao_como_sistema_funciona_e_registra(ana, caplog):
    with caplog.at_level("INFO", logger="infra_vibecoding.auditoria"):
        pedido = Pedido(dono=ana, titulo="Importado").salvar_como_sistema("importação inicial")
        Pedido.objects.como_sistema("reajuste anual").update(valor=99)
        pedido.excluir_como_sistema("limpeza")
    assert "importação inicial" in caplog.text
    assert "reajuste anual" in caplog.text
    assert "limpeza" in caplog.text
    assert Pedido.objects.como_sistema(SISTEMA).count() == 0


def test_acesso_negado_fica_registrado(beto, pedido_da_ana, caplog):
    with caplog.at_level("WARNING", logger="infra_vibecoding.auditoria"):
        with pytest.raises(SemPermissao):
            pedido_da_ana.excluir(beto)
    assert "acesso negado" in caplog.text


def test_atualizar_ou_criar_so_como_sistema(ana, pedido_da_ana):
    with pytest.raises(EscritaSemAutorizacao):
        Pedido.objects.para(ana).update_or_create(pk=pedido_da_ana.pk, defaults={"valor": 1})
    Pedido.objects.como_sistema("sincronização").update_or_create(
        pk=pedido_da_ana.pk, defaults={"valor": 1}
    )
    assert no_banco(pedido_da_ana).valor == 1


def test_modo_sistema_nao_vaza_para_fora(ana, pedido_da_ana):
    Pedido.objects.como_sistema("sincronização").update_or_create(pk=pedido_da_ana.pk, defaults={"valor": 2})
    with pytest.raises(EscritaSemAutorizacao):
        pedido_da_ana.save()
