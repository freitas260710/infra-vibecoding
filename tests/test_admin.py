"""Testes da tela de banco protegida (US 1.6)."""
import pytest
from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.auth import get_user_model

from infra_vibecoding.checagens import sec07_admin_protegido, sec07_endereco_do_admin, verificar_admin
from tests.app_teste.models import ItemPedido, Pedido, Rascunho

pytestmark = pytest.mark.django_db
User = get_user_model()
ADMIN = "/gestao-interna/"
SISTEMA = "preparar teste"


@pytest.fixture
def ana():
    return User.objects.create_user("ana", password="x")


@pytest.fixture
def chefe():
    return User.objects.create_superuser("chefe", password="x")


@pytest.fixture
def pedido_da_ana(ana):
    return Pedido.objects.como_sistema(SISTEMA).create(dono=ana, titulo="Pedido da Ana", valor=10)


def total():
    return Pedido.objects.como_sistema(SISTEMA).count()


# 1. Quem entra.
def test_visitante_nao_entra(client):
    r = client.get(ADMIN)
    assert r.status_code == 302
    assert "login" in r["Location"]


def test_usuario_comum_nao_entra(client, ana):
    client.force_login(ana)
    r = client.get(ADMIN)
    assert r.status_code == 302
    assert "login" in r["Location"]


def test_administrador_entra(client, chefe):
    client.force_login(chefe)
    assert client.get(ADMIN).status_code == 200


def test_endereco_padrao_nao_existe(client, chefe):
    client.force_login(chefe)
    assert client.get("/admin/").status_code == 404


# 2. O administrador vê e altera tudo, como sistema, com registro.
def test_administrador_ve_registros_de_todos(client, chefe, pedido_da_ana, caplog):
    client.force_login(chefe)
    with caplog.at_level("INFO", logger="infra_vibecoding.auditoria"):
        r = client.get(f"{ADMIN}app_teste/pedido/")
    assert r.status_code == 200
    assert b"Pedido da Ana" in r.content
    assert "admin: chefe consultou" in caplog.text


def test_administrador_cria_e_fica_registrado(client, chefe, ana, caplog):
    client.force_login(chefe)
    dados = {
        "dono": ana.pk, "titulo": "Criado no admin", "valor": "5",
        "itens-TOTAL_FORMS": "0", "itens-INITIAL_FORMS": "0",
    }
    with caplog.at_level("INFO", logger="infra_vibecoding.auditoria"):
        r = client.post(f"{ADMIN}app_teste/pedido/add/", dados)
    assert r.status_code == 302, r.content[:500]
    assert total() == 1
    assert "admin: chefe criou" in caplog.text


def test_administrador_edita(client, chefe, pedido_da_ana):
    client.force_login(chefe)
    dados = {
        "dono": pedido_da_ana.dono_id, "titulo": "Editado no admin", "valor": "7",
        "itens-TOTAL_FORMS": "0", "itens-INITIAL_FORMS": "0",
    }
    r = client.post(f"{ADMIN}app_teste/pedido/{pedido_da_ana.pk}/change/", dados)
    assert r.status_code == 302
    assert Pedido.objects.como_sistema(SISTEMA).get(pk=pedido_da_ana.pk).titulo == "Editado no admin"


def test_administrador_exclui(client, chefe, pedido_da_ana, caplog):
    client.force_login(chefe)
    with caplog.at_level("INFO", logger="infra_vibecoding.auditoria"):
        r = client.post(f"{ADMIN}app_teste/pedido/{pedido_da_ana.pk}/delete/", {"post": "yes"})
    assert r.status_code == 302
    assert total() == 0
    assert "admin: chefe excluiu" in caplog.text


def test_tela_com_campo_relacionado_abre(client, chefe, pedido_da_ana):
    """A lista para escolher o pedido de um item também passa pelo 00 e não quebra."""
    client.force_login(chefe)
    r = client.get(f"{ADMIN}app_teste/itempedido/add/")
    assert r.status_code == 200
    assert b"Pedido da Ana" in r.content or b"Pedido object" in r.content


def test_item_criado_no_admin(client, chefe, pedido_da_ana):
    client.force_login(chefe)
    r = client.post(f"{ADMIN}app_teste/itempedido/add/", {"pedido": pedido_da_ana.pk, "descricao": "Caneta"})
    assert r.status_code == 302
    assert ItemPedido.objects.como_sistema(SISTEMA).count() == 1


# 3. Checagens.
def test_projeto_de_teste_passa():
    assert sec07_admin_protegido() == []
    assert sec07_endereco_do_admin() == []


def test_tabela_no_admin_sem_admin_seguro_e_barrada():
    site = AdminSite(name="teste")
    site.register(Rascunho, admin.ModelAdmin)
    assert [e.id for e in verificar_admin(site)] == ["SEC.E071"]


def test_admin_no_endereco_padrao_e_barrado(settings):
    settings.ROOT_URLCONF = "tests.urls_admin_padrao"
    assert [e.id for e in sec07_endereco_do_admin()] == ["SEC.E072"]


# US 2.6: filtros laterais por ligação e busca na tela de banco.
def test_lista_com_filtro_por_ligacao_abre(client, chefe, pedido_da_ana, ana):
    client.force_login(chefe)
    r = client.get(ADMIN + "app_teste/pedido/")
    assert r.status_code == 200
    assert "Pedido da Ana" in r.content.decode()


def test_filtro_lateral_por_ligacao_filtra(client, chefe, pedido_da_ana, ana):
    client.force_login(chefe)
    r = client.get(ADMIN + f"app_teste/pedido/?dono__id__exact={ana.pk}")
    assert r.status_code == 200 and "Pedido da Ana" in r.content.decode()
    r = client.get(ADMIN + f"app_teste/pedido/?dono__id__exact={chefe.pk}")
    assert r.status_code == 200 and "Pedido da Ana" not in r.content.decode()


def test_busca_na_tela_de_banco(client, chefe, pedido_da_ana):
    client.force_login(chefe)
    r = client.get(ADMIN + "app_teste/pedido/?q=Ana")
    assert r.status_code == 200 and "Pedido da Ana" in r.content.decode()


def test_tela_aberta_fica_registrada(client, chefe, caplog):
    client.force_login(chefe)
    with caplog.at_level("INFO", logger="infra_vibecoding.auditoria"):
        client.get(ADMIN + "app_teste/pedido/")
    assert "abriu /gestao-interna/app_teste/pedido/" in caplog.text


def test_leitura_como_sistema_termina_com_a_tela(client, chefe, pedido_da_ana):
    from infra_vibecoding.dados import AcessoSemEscopo

    client.force_login(chefe)
    client.get(ADMIN + "app_teste/pedido/")
    with pytest.raises(AcessoSemEscopo):
        list(Pedido.objects.all())


def test_tela_de_banco_continua_so_para_administrador(client, ana):
    client.force_login(ana)
    r = client.get(ADMIN + "app_teste/pedido/?dono__id__exact=1")
    assert r.status_code == 302 and "login" in r["Location"]


def test_leitura_da_tela_de_banco_nao_libera_gravacao_em_massa():
    from infra_vibecoding.dados import EscritaSemAutorizacao, _leitura_da_tela_de_banco

    with _leitura_da_tela_de_banco():
        with pytest.raises(EscritaSemAutorizacao):
            Pedido.objects.update(valor=0)
        with pytest.raises(EscritaSemAutorizacao):
            Pedido.objects.all().delete()
