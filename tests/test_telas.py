"""Testes das travas de telas (US 1.4)."""
import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from infra_vibecoding.checagens import sec04_toda_tela_declara_acesso, sec06_login_obrigatorio_por_padrao

pytestmark = pytest.mark.django_db
User = get_user_model()
LOGIN = "/entrar/"


@pytest.fixture
def ana():
    return User.objects.create_user("ana", password="x")


@pytest.fixture
def chefe():
    return User.objects.create_user("chefe", password="x", is_staff=True)


# 1. Visitante não logado.
@pytest.mark.parametrize("url", ["/", "/sobre/"])
def test_visitante_abre_tela_publica(client, url):
    assert client.get(url).status_code == 200


@pytest.mark.parametrize("url", ["/painel/", "/pedidos/novo/", "/aprovacoes/", "/relatorio/"])
def test_visitante_vai_para_o_login(client, url):
    resposta = client.get(url)
    assert resposta.status_code == 302
    assert resposta["Location"].startswith(LOGIN)


# 2. Usuário logado.
def test_logado_abre_tela_de_logado(client, ana):
    client.force_login(ana)
    resposta = client.get("/painel/")
    assert resposta.status_code == 200
    assert b"ana" in resposta.content


def test_logado_abre_tela_que_a_politica_permite(client, ana):
    client.force_login(ana)
    assert client.get("/pedidos/novo/").status_code == 200


@pytest.mark.parametrize("url", ["/aprovacoes/", "/relatorio/"])
def test_logado_sem_permissao_recebe_403(client, ana, url):
    client.force_login(ana)
    assert client.get(url).status_code == 403


@pytest.mark.parametrize("url", ["/aprovacoes/", "/relatorio/"])
def test_quem_tem_permissao_abre(client, chefe, url):
    client.force_login(chefe)
    assert client.get(url).status_code == 200


# 3. Checagens.
def test_projeto_de_teste_passa_nas_checagens():
    assert sec04_toda_tela_declara_acesso() == []
    assert sec06_login_obrigatorio_por_padrao() == []
    call_command("check")


def test_tela_sem_declaracao_impede_o_sistema_de_ligar(settings):
    settings.ROOT_URLCONF = "tests.urls_sem_declaracao"
    erros = sec04_toda_tela_declara_acesso()
    assert [e.id for e in erros] == ["SEC.E041"]
    assert "esquecida" in erros[0].msg


def test_sem_login_obrigatorio_o_sistema_nao_liga(settings):
    settings.MIDDLEWARE = [m for m in settings.MIDDLEWARE if "LoginRequired" not in m]
    assert [e.id for e in sec06_login_obrigatorio_por_padrao()] == ["SEC.E061"]


def test_login_obrigatorio_fora_de_ordem_o_sistema_nao_liga(settings):
    mw = [m for m in settings.MIDDLEWARE if "LoginRequired" not in m]
    settings.MIDDLEWARE = ["django.contrib.auth.middleware.LoginRequiredMiddleware"] + mw
    assert [e.id for e in sec06_login_obrigatorio_por_padrao()] == ["SEC.E062"]


def test_marcar_uma_classe_nao_afeta_as_outras():
    from django.views import View

    from tests.app_teste.views import SobreView

    assert getattr(View.dispatch, "_acesso", None) is None
    assert getattr(View.dispatch, "login_required", True) is True
    assert SobreView._acesso == "publica"
