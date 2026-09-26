"""Testes das páginas de erro do 00 (US 3.5): em português, sem nada técnico, com o código do erro no 500."""
import re

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from infra_vibecoding.checagens import sec11_paginas_de_erro
from tests.app_teste.models import Pedido

pytestmark = pytest.mark.django_db
Usuario = get_user_model()
SENHA = "uma-senha-bem-longa-para-teste"
HTMX = {"HX-Request": "true"}


@pytest.fixture
def ana():
    return Usuario.objects.create_user("ana@exemplo.com", password=SENHA, nome="Ana")


@pytest.fixture
def cliente():
    return Client(raise_request_exception=False)


def test_nao_encontrado_em_portugues(client):
    r = client.get("/nao-existe/")
    assert r.status_code == 404
    assert "Esta página não existe ou você não tem acesso a ela." in r.content.decode()


def test_registro_de_outra_pessoa_responde_nao_encontrado(client, ana):
    beto = Usuario.objects.create_user("beto@exemplo.com", password=SENHA)
    pedido = Pedido(dono=beto, titulo="do beto")
    pedido.salvar_como_sistema("teste")
    client.force_login(ana)
    r = client.get(f"/pedidos/{pedido.pk}/")
    assert r.status_code == 404 and "do beto" not in r.content.decode()


def test_sem_permissao_em_portugues_e_registrado(client, ana, caplog):
    client.force_login(ana)
    r = client.get("/aprovacoes/")
    assert r.status_code == 403
    assert "Você não tem permissão para fazer isso." in r.content.decode()
    assert "acesso negado: ana@exemplo.com em GET /aprovacoes/" in caplog.text


def test_erro_interno_mostra_so_o_codigo_e_registra_o_erro_completo(cliente, caplog):
    r = cliente.get("/quebrada/")
    tela = r.content.decode()
    assert r.status_code == 500 and "Algo deu errado" in tela
    codigo = re.search(r"E-[2-9A-Z]{5}", tela).group(0)
    assert r["X-Codigo-Erro"] == codigo
    assert "senha=abc123" not in tela and "RuntimeError" not in tela and "Traceback" not in tela
    registro = [x for x in caplog.records if x.name == "infra_vibecoding.erros"][0]
    assert codigo in registro.getMessage() and "/quebrada/" in registro.getMessage()
    assert registro.exc_info and registro.exc_info[0] is RuntimeError  # o erro completo fica no registro, junto com o código, não na tela
    assert "senha=abc123" in caplog.text


def test_cada_erro_tem_um_codigo_diferente(cliente):
    c1 = cliente.get("/quebrada/")["X-Codigo-Erro"]
    c2 = cliente.get("/quebrada/")["X-Codigo-Erro"]
    assert c1 != c2


def test_pedido_invalido_em_portugues(cliente):
    r = cliente.get("/pedido-ruim/")
    assert r.status_code == 400 and "Pedido inválido" in r.content.decode()
    assert "detalhe técnico" not in r.content.decode()


def test_formulario_vencido_csrf(ana, caplog):
    c = Client(enforce_csrf_checks=True)
    r = c.post("/entrar/", {"username": "ana@exemplo.com", "password": SENHA})
    assert r.status_code == 403
    assert "A página ficou aberta muito tempo" in r.content.decode()
    assert "proteção CSRF" in caplog.text


def test_htmx_recebe_so_uma_frase(cliente, ana):
    r = cliente.get("/quebrada/", headers=HTMX)
    assert r.status_code == 500 and r["Content-Type"].startswith("text/plain")
    assert r.content.decode().startswith("Algo deu errado. Código do erro: E-")
    cliente.force_login(ana)
    r = cliente.get("/aprovacoes/", headers=HTMX)
    assert r.content.decode() == "Você não tem permissão para fazer isso."
    r = cliente.get("/nao-existe/", headers=HTMX)
    assert r.status_code == 404 and "<html" not in r.content.decode()


def test_ver_paginas_so_no_computador_do_desenvolvedor(client, settings):
    r = client.get("/erros/ver/500/")  # DEBUG desligado (servidor): a tela de ver não existe
    assert r.status_code == 404 and "E-EXEMP" not in r.content.decode()
    settings.DEBUG = True
    for tipo, status in (("400", 400), ("403", 403), ("403_csrf", 403), ("404", 404), ("429", 429), ("500", 500)):
        assert client.get(f"/erros/ver/{tipo}/").status_code == status
    assert "E-EXEMP" in client.get("/erros/ver/500/").content.decode()


def test_sistema_troca_o_visual_pela_pasta_templates(client, settings, tmp_path):
    (tmp_path / "404.html").write_text("<h1>Página do Mindor: não achamos</h1>", encoding="utf-8")
    settings.TEMPLATES = [{**settings.TEMPLATES[0], "DIRS": [tmp_path]}]
    r = client.get("/nao-existe/")
    assert r.status_code == 404 and "Página do Mindor" in r.content.decode()


# Checagens
def test_configuracao_padrao_passa():
    assert sec11_paginas_de_erro() == []


def test_handler_proprio_no_urls_e_barrado(settings):
    settings.ROOT_URLCONF = "tests.urls_com_handler"
    assert [e.id for e in sec11_paginas_de_erro()] == ["SEC.E111"]


def test_csrf_failure_view_proprio_e_barrado(settings):
    settings.CSRF_FAILURE_VIEW = "django.views.csrf.csrf_failure"
    assert [e.id for e in sec11_paginas_de_erro()] == ["SEC.E112"]


def test_500_sem_codigo_e_barrado(settings, tmp_path):
    (tmp_path / "500.html").write_text("<h1>Erro</h1>", encoding="utf-8")
    settings.TEMPLATES = [{**settings.TEMPLATES[0], "DIRS": [tmp_path]}]
    assert [e.id for e in sec11_paginas_de_erro()] == ["SEC.E113"]
