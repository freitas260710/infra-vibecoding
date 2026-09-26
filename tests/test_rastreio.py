"""Testes do painel de rastreio (US 6.4, D60): ?debug_mode=true, só superusuário, só fora de produção."""
import json
import re

import pytest
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.checks import run_checks
from django.test import Client

from infra_vibecoding.novo_sistema import arquivos_do_sistema
from infra_vibecoding.pedido import anotar_regra
from tests.app_teste.models import Pedido

pytestmark = pytest.mark.django_db
Usuario = get_user_model()
SENHA = "uma-senha-bem-longa-para-teste"


@pytest.fixture
def chefe():
    return Usuario.objects.create_superuser("chefe@exemplo.com", password=SENHA)


@pytest.fixture
def ana():
    return Usuario.objects.create_user("ana@exemplo.com", password=SENHA)


def logado(usuario):
    c = Client()
    c.force_login(usuario)
    return c


def tem_painel(resposta):
    return 'id="djDebug"' in resposta.content.decode()


def aba(cliente, resposta, nome):
    """Conteúdo de uma aba do painel, como o navegador carrega ao clicar nela."""
    achado = re.search(r'data-request-id="([^"]+)"', resposta.content.decode())
    request_id = achado.group(1) if achado else resposta["djdt-request-id"]  # redirecionamento: vem no cabeçalho
    r = cliente.get("/__debug__/render_panel/", {"request_id": request_id, "panel_id": nome})
    assert r.status_code == 200
    return json.loads(r.content)["content"]


# 1. Quem vê e quando
def test_superusuario_com_debug_mode_ve_o_painel_e_o_script_que_mantem_o_modo(chefe):
    r = logado(chefe).get("/rastreio/?debug_mode=true")
    assert tem_painel(r) and "infra_vibecoding/modo_depuracao.js" in r.content.decode()
    assert tem_painel(logado(chefe).get("/gestao-interna/?debug_mode=true"))  # vale em qualquer tela


def test_sem_debug_mode_nao_aparece_nem_anota(chefe):
    r = logado(chefe).get("/rastreio/")
    assert not tem_painel(r) and "modo_depuracao.js" not in r.content.decode()


def test_quem_nao_e_superusuario_nunca_ve(ana):
    ana.is_staff = True
    ana.salvar_como_sistema("teste: da tela de banco, mas não superusuário")
    c = logado(ana)
    assert not tem_painel(c.get("/rastreio/?debug_mode=true"))
    assert c.get("/__debug__/render_panel/", {"request_id": "x", "panel_id": "Regras"}).status_code == 404
    assert Client().get("/__debug__/render_panel/", {"request_id": "x", "panel_id": "Regras"}).status_code == 404


def test_em_producao_o_debug_mode_e_ignorado(chefe, settings):
    settings.AMBIENTE = "producao"
    assert not tem_painel(logado(chefe).get("/rastreio/?debug_mode=true"))


def test_debug_mode_diferente_de_true_nao_liga(chefe):
    assert not tem_painel(logado(chefe).get("/rastreio/?debug_mode=false"))
    assert not tem_painel(logado(chefe).get("/rastreio/?debug_mode=1"))


# 2. Abas do 00
def test_aba_regras_mostra_o_que_liberou_e_o_que_barrou(chefe):
    c = logado(chefe)
    r = c.get("/rastreio/?debug_mode=true")
    conteudo = aba(c, r, "Regras")
    assert "ver (lista filtrada pela regra)" in conteudo and "app_teste.Pedido" in conteudo
    assert "aprovar" in conteudo and "liberou" in conteudo
    assert "excluir" in conteudo and "barrou" in conteudo
    assert r["X-Codigo-Pedido"] in conteudo and "chefe@exemplo.com" in conteudo


def test_abas_historico_e_acessos_mostram_o_clique(chefe):
    c = logado(chefe)
    r = c.post("/rastreio/salvar/?debug_mode=true", {"titulo": "Mesa"})
    assert r.status_code == 302 and r["Location"] == "/rastreio/?debug_mode=true"  # depois de salvar, continua
    historico = aba(c, r, "Historico")
    assert "criou" in historico and "app_teste.Pedido" in historico and "Mesa" in historico
    assert f"?pedido={r['X-Codigo-Pedido']}" in historico  # atalho para Registros
    r2 = c.get("/gestao-interna/?debug_mode=true")
    assert "entrou na tela de banco" in aba(c, r2, "Acessos")


def test_redirecionamento_para_outro_site_nao_ganha_debug_mode():
    from infra_vibecoding.rastreio import com_debug_mode

    assert com_debug_mode("https://outro.exemplo/x", "testserver") == "https://outro.exemplo/x"
    assert com_debug_mode("/chamados/?a=1", "testserver") == "/chamados/?a=1&debug_mode=true"
    assert com_debug_mode("/x/?debug_mode=false", "testserver") == "/x/?debug_mode=true"
    assert com_debug_mode("/__debug__/render_panel/", "testserver") == "/__debug__/render_panel/"


def test_sem_painel_nada_e_anotado(ana):
    anotar_regra("pode", ana, "ver", Pedido, None, True)  # fora de um clique: não faz nada nem quebra
    r = logado(ana).get("/rastreio/")
    assert r.status_code == 200


# 3. Travas
def test_painel_em_producao_nao_liga(settings):
    assert "SEC.E141" not in [e.id for e in run_checks()]
    settings.AMBIENTE = "producao"
    assert "SEC.E141" in [e.id for e in run_checks()]


def test_abrir_o_painel_para_todos_nao_liga(settings):
    assert "SEC.E142" not in [e.id for e in run_checks()]
    settings.DEBUG_TOOLBAR_CONFIG = {"SHOW_TOOLBAR_CALLBACK": "debug_toolbar.middleware.show_toolbar"}
    assert "SEC.E142" in [e.id for e in run_checks()]


def test_script_do_debug_mode_existe():
    caminho = finders.find("infra_vibecoding/modo_depuracao.js")
    assert caminho and "debug_mode" in open(caminho, encoding="utf-8").read()


# 4. Passo a passo no VS Code
def test_sistema_novo_nasce_com_o_depurador_do_vscode():
    arquivos = arquivos_do_sistema("teste-painel")
    config = json.loads(arquivos[".vscode/launch.json"])
    nomes = [c["name"] for c in config["configurations"]]
    assert "Depurar o sistema (passo a passo)" in nomes
    assert config["configurations"][0]["django"] is True
    assert "?debug_mode=true" in arquivos["README.md"]


def test_enderecos_internos_do_painel_nao_quebram_a_checagem_de_telas():
    # Os endereços internos do painel (/__debug__/) vêm marcados pela própria ferramenta como abertos, mas respondem
    # "não encontrado" para quem não é superusuário com o painel permitido (teste acima).
    assert not [e for e in run_checks() if e.id == "SEC.E041"]
