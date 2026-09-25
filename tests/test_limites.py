"""Testes da proteção contra força bruta (US 3.3, D50)."""
import logging
import time

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client

from infra_vibecoding import limites
from infra_vibecoding.checagens import sec06_limite_de_pedidos

pytestmark = pytest.mark.django_db
Usuario = get_user_model()
SENHA = "uma-senha-bem-longa-para-teste"


@pytest.fixture(autouse=True)
def limites_ligados(settings, monkeypatch):
    settings.LIMITES_NOS_TESTES = True
    # Relógio parado durante o teste: as janelas de 1 minuto não viram no meio da contagem.
    agora = time.time()
    monkeypatch.setattr(time, "time", lambda: agora)
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def ana():
    return Usuario.objects.create_user("ana@exemplo.com", password=SENHA)


def adiantar(monkeypatch, segundos):
    agora = time.time()
    monkeypatch.setattr(time, "time", lambda: agora + segundos)  # a partir do relógio parado


# 1. Limite geral.
def test_visitante_ate_120_por_minuto(client, caplog):
    for _ in range(120):
        assert client.get("/").status_code == 200
    with caplog.at_level(logging.WARNING, logger="infra_vibecoding.auditoria"):
        r = client.get("/")
    assert r.status_code == 429 and r["Retry-After"] == "60"
    assert "Muitas tentativas" in r.content.decode()
    assert "passou de 120 pedidos por minuto" in caplog.text


def test_limite_vale_para_qualquer_endereco_do_sistema(client):
    for _ in range(120):
        client.get("/sobre/")
    assert client.get("/painel/").status_code == 429       # outra tela
    assert client.post("/entrar/", {}).status_code == 429  # e formulário


def test_janela_de_um_minuto_libera_depois(client, monkeypatch):
    for _ in range(121):
        client.get("/")
    assert client.get("/").status_code == 429
    adiantar(monkeypatch, 61)
    assert client.get("/").status_code == 200


def test_usuario_logado_ate_240_e_nao_atrapalha_colegas(ana):
    beto = Usuario.objects.create_user("beto@exemplo.com", password=SENHA)
    c_ana, c_beto, visitante = Client(), Client(), Client()
    c_ana.force_login(ana)
    c_beto.force_login(beto)
    for _ in range(240):
        assert c_ana.get("/painel/").status_code == 200
    assert c_ana.get("/painel/").status_code == 429
    assert c_beto.get("/painel/").status_code == 200  # mesmo endereço, outro usuário
    assert visitante.get("/").status_code == 200


def test_sistema_pode_apertar(client, settings):
    settings.LIMITE_PEDIDOS_POR_ENDERECO = 10
    for _ in range(10):
        client.get("/")
    assert client.get("/").status_code == 429


def test_sistema_nao_pode_afrouxar(client, settings):
    settings.LIMITE_PEDIDOS_POR_ENDERECO = 10_000
    assert [e.id for e in sec06_limite_de_pedidos()] == ["SEC.E067"]
    for _ in range(120):
        client.get("/")
    assert client.get("/").status_code == 429  # mesmo afrouxado, o 00 segura no máximo dele


def test_sem_o_limite_o_sistema_nao_liga(settings):
    settings.MIDDLEWARE = [m for m in settings.MIDDLEWARE if "LimiteDePedidos" not in m]
    assert [e.id for e in sec06_limite_de_pedidos()] == ["SEC.E066"]
    mw = [m for m in settings.MIDDLEWARE]
    settings.MIDDLEWARE = ["infra_vibecoding.limites.LimiteDePedidos", *mw]  # antes do login: fora de ordem
    assert [e.id for e in sec06_limite_de_pedidos()] == ["SEC.E066"]


def test_projeto_de_teste_passa():
    assert sec06_limite_de_pedidos() == []


def test_nos_testes_dos_sistemas_os_limites_ficam_desligados(client, settings):
    settings.LIMITES_NOS_TESTES = False
    for _ in range(300):
        assert client.get("/").status_code == 200


# 2. Login.
def entrar(client, email="ana@exemplo.com", senha=SENHA):
    return client.post("/entrar/", {"username": email, "password": senha})


def test_cinco_senhas_erradas_bloqueiam_o_email_por_15_minutos(client, ana, caplog, monkeypatch):
    for _ in range(5):
        assert "E-mail ou senha incorretos." in entrar(client, senha="errada").content.decode()
    with caplog.at_level(logging.WARNING, logger="infra_vibecoding.auditoria"):
        r = entrar(Client())  # até com a senha certa
    assert "Muitas tentativas de entrar" in r.content.decode()
    assert not Client().login(email="ana@exemplo.com", password=SENHA)
    assert "login bloqueado por 15 minutos para ana@exemplo.com" in caplog.text
    adiantar(monkeypatch, 15 * 60 + 1)
    assert entrar(Client()).status_code == 302


def test_bloqueio_nao_revela_se_o_email_existe(client):
    for _ in range(5):
        entrar(client, "ninguem@exemplo.com", "errada")
    assert "Muitas tentativas de entrar" in entrar(client, "ninguem@exemplo.com", "x").content.decode()


def test_bloqueio_de_um_email_nao_tranca_os_outros(ana):
    Usuario.objects.create_user("beto@exemplo.com", password=SENHA)
    for _ in range(5):
        entrar(Client(), "ana@exemplo.com", "errada")
    assert entrar(Client(), "beto@exemplo.com").status_code == 302


def test_vinte_tentativas_erradas_do_mesmo_endereco_bloqueiam_o_endereco(ana):
    for i in range(20):
        entrar(Client(), f"pessoa{i}@exemplo.com", "errada")
    assert "Muitas tentativas de entrar" in entrar(Client()).content.decode()


def test_login_da_tela_de_banco_tambem_bloqueia(client):
    chefe = Usuario.objects.create_superuser("chefe@exemplo.com", password=SENHA)
    for _ in range(5):
        client.post("/gestao-interna/login/", {"username": "chefe@exemplo.com", "password": "errada"})
    client.post("/gestao-interna/login/", {"username": "chefe@exemplo.com", "password": SENHA})
    assert client.get("/gestao-interna/").status_code == 302  # não entrou
    assert chefe.pk


def test_esqueci_a_senha_continua_funcionando_com_bloqueio(client, ana, mailoutbox):
    for _ in range(5):
        entrar(client, senha="errada")
    client.post("/esqueci-a-senha/", {"email": "ana@exemplo.com"})
    assert len(mailoutbox) == 1


def test_acertar_a_senha_nao_conta(client, ana):
    for _ in range(10):
        c = Client()
        assert entrar(c).status_code == 302
    assert entrar(Client()).status_code == 302


# 3. @limite nas ações do sistema.
def test_limite_apertado_numa_acao(client, ana):
    for _ in range(3):
        assert client.get("/exportar/").status_code == 200
    assert client.get("/exportar/").status_code == 429
    outro = Client()
    outro.force_login(ana)
    assert outro.get("/exportar/").status_code == 200  # conta por usuário
    assert client.get("/").status_code == 200           # as outras telas seguem normais


def test_limite_apertado_em_tela_de_classe(client):
    for _ in range(2):
        assert client.get("/relatorio-pesado/").status_code == 200
    assert client.get("/relatorio-pesado/").status_code == 429


def test_limites_do_00(settings):
    assert limites.MAXIMO_POR_ENDERECO == 120 and limites.MAXIMO_POR_USUARIO == 240
    assert (limites.LOGIN_POR_EMAIL, limites.LOGIN_POR_ENDERECO) == (5, 20)
    assert limites.LOGIN_JANELA == limites.LOGIN_BLOQUEIO == 15 * 60
