"""Testes das travas de dados (US 1.2)."""
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.management import call_command
from django.db import models
from django.test.utils import isolate_apps

from infra_vibecoding.checagens import sec02_toda_tabela_tem_politica, verificar_modelo
from infra_vibecoding.dados import AcessoSemEscopo, ModeloSeguro
from tests.app_teste.models import Pedido, Rascunho

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def ana():
    return User.objects.create_user("ana", password="x")


@pytest.fixture
def beto():
    return User.objects.create_user("beto", password="x")


@pytest.fixture
def pedido_da_ana(ana):
    return Pedido.objects.create(dono=ana, titulo="Pedido da Ana", valor=10)


# 1. Ler sem dizer para quem é bloqueado, por qualquer caminho.
@pytest.mark.parametrize("tentativa", [
    lambda: list(Pedido.objects.all()),
    lambda: list(Pedido.objects.filter(valor__gt=0)),
    lambda: Pedido.objects.get(titulo="Pedido da Ana"),
    lambda: Pedido.objects.first(),
    lambda: Pedido.objects.count(),
    lambda: Pedido.objects.exists(),
    lambda: list(Pedido.objects.values("titulo")),
    lambda: list(Pedido.objects.values_list("titulo", flat=True)),
    lambda: list(Pedido.objects.iterator()),
    lambda: Pedido.objects.aggregate(total=models.Sum("valor")),
    lambda: Pedido.objects.in_bulk(),
    lambda: Pedido.objects.update(valor=0),
    lambda: Pedido.objects.all().delete(),
    lambda: list(Pedido.objects.raw("SELECT * FROM app_teste_pedido")),
])
def test_leitura_sem_escopo_e_bloqueada(pedido_da_ana, tentativa):
    with pytest.raises(AcessoSemEscopo):
        tentativa()


def test_relacao_reversa_sem_escopo_e_bloqueada(ana, pedido_da_ana):
    with pytest.raises(AcessoSemEscopo):
        list(ana.pedido_set.all())


# 2. A política filtra por usuário.
def test_dono_ve_o_proprio_pedido(ana, pedido_da_ana):
    assert list(Pedido.objects.para(ana)) == [pedido_da_ana]


def test_outro_usuario_nao_ve(beto, pedido_da_ana):
    assert Pedido.objects.para(beto).count() == 0
    with pytest.raises(Pedido.DoesNotExist):
        Pedido.objects.para(beto).get(pk=pedido_da_ana.pk)


def test_filtros_depois_do_escopo_continuam_valendo(ana, pedido_da_ana):
    assert Pedido.objects.para(ana).filter(valor__gt=5).count() == 1
    assert Pedido.objects.para(ana).filter(valor__gt=50).count() == 0


# 3. Fechado por padrão.
def test_anonimo_e_usuario_ausente_nao_veem_nada(pedido_da_ana):
    assert Pedido.objects.para(AnonymousUser()).count() == 0
    assert Pedido.objects.para(None).count() == 0


def test_politica_vazia_nao_mostra_nada(ana):
    Rascunho.objects.create(texto="segredo")
    assert Rascunho.objects.para(ana).count() == 0


# 4. Exceção controlada: como sistema.
def test_como_sistema_exige_motivo(pedido_da_ana):
    with pytest.raises(ValueError):
        Pedido.objects.como_sistema("")
    with pytest.raises(ValueError):
        Pedido.objects.como_sistema("   ")


def test_como_sistema_le_tudo_e_registra(pedido_da_ana, caplog):
    with caplog.at_level("INFO", logger="infra_vibecoding.auditoria"):
        assert Pedido.objects.como_sistema("teste automatizado").count() == 1
    assert "teste automatizado" in caplog.text


# 5. Checagens: o sistema não liga com tabela desprotegida.
@isolate_apps("tests.app_teste")
def test_tabela_comum_e_barrada():
    class TabelaComum(models.Model):
        nome = models.CharField(max_length=10)

        class Meta:
            app_label = "app_teste"

    erros = verificar_modelo(TabelaComum)
    assert [e.id for e in erros] == ["SEC.E021"]


@isolate_apps("tests.app_teste")
def test_tabela_sem_politica_e_barrada():
    class TabelaSemPolitica(ModeloSeguro):
        nome = models.CharField(max_length=10)

        class Meta:
            app_label = "app_teste"

    erros = verificar_modelo(TabelaSemPolitica)
    assert [e.id for e in erros] == ["SEC.E022"]


def test_projeto_de_teste_passa_nas_checagens():
    assert sec02_toda_tabela_tem_politica() == []
    call_command("check")


def test_apps_de_bibliotecas_nao_sao_checados():
    from django.apps import apps
    from infra_vibecoding.checagens import _eh_do_sistema

    assert not _eh_do_sistema(apps.get_app_config("auth"))
    assert not _eh_do_sistema(apps.get_app_config("infra_vibecoding"))
    assert _eh_do_sistema(apps.get_app_config("app_teste"))


def test_bibliotecas_dentro_da_pasta_do_projeto_nao_sao_checadas(settings):
    """Com o uv, a .venv fica dentro da pasta do projeto. Django e outras bibliotecas não entram na checagem."""
    from pathlib import Path

    from django.apps import apps
    from infra_vibecoding.checagens import _eh_do_sistema

    settings.BASE_DIR = Path(__file__).resolve().parent.parent  # raiz do repositório, que contém a .venv
    assert not _eh_do_sistema(apps.get_app_config("auth"))
    assert not _eh_do_sistema(apps.get_app_config("contenttypes"))
    assert _eh_do_sistema(apps.get_app_config("app_teste"))
