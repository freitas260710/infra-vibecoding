"""Testes da US 3.2: manter conectado, lembrar e-mail, derrubar sessões e cadastro público (D47, D48)."""
import logging
import re

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client

from infra_vibecoding.checagens import sec08_cadastro_publico
from infra_vibecoding.login import cadastro as modulo_cadastro
from infra_vibecoding.login import desconectar
from infra_vibecoding.login.views import COOKIE_EMAIL, MANTER_CONECTADO
from tests.app_teste.models import AcessoSetor, Setor

pytestmark = pytest.mark.django_db
Usuario = get_user_model()
SENHA = "uma-senha-bem-longa-para-teste"
NOVA = "outra-senha-bem-longa-para-teste"
CADASTRO = "tests.app_teste.cadastro.CadastroTeste"


@pytest.fixture(autouse=True)
def limpar_limites():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def ana():
    return Usuario.objects.create_user("ana@exemplo.com", password=SENHA)


@pytest.fixture
def chefe():
    return Usuario.objects.create_superuser("chefe@exemplo.com", password=SENHA)


def entrar(client, email="ana@exemplo.com", **opcoes):
    return client.post("/entrar/", {"username": email, "password": SENHA, **opcoes})


def conectado(client):
    return client.get("/painel/").status_code == 200


def link_do_email(mensagem):
    return re.search(r"http://testserver(/\S+)", mensagem.body).group(1)


# 1. Manter conectado.
def test_sem_manter_conectado_a_sessao_acaba_ao_fechar_o_navegador(client, ana):
    r = entrar(client)
    assert r.status_code == 302
    assert client.session.get_expire_at_browser_close()
    assert not r.cookies["sessionid"]["max-age"]


def test_manter_conectado_vale_30_dias(client, ana):
    r = entrar(client, manter_conectado="on")
    assert not client.session.get_expire_at_browser_close()
    assert client.session.get_expiry_age() == MANTER_CONECTADO == 30 * 24 * 60 * 60
    assert int(r.cookies["sessionid"]["max-age"]) == MANTER_CONECTADO


def test_caixinhas_vem_desmarcadas(client):
    pagina = client.get("/entrar/").content.decode()
    assert 'name="manter_conectado"' in pagina and 'name="lembrar_email"' in pagina
    assert "checked" not in pagina


# 2. Lembrar e-mail.
def test_lembrar_email_preenche_na_proxima_vez(client, ana):
    r = entrar(client, lembrar_email="on")
    cookie = r.cookies[COOKIE_EMAIL]
    assert cookie["httponly"] and cookie["samesite"] == "Lax"
    assert SENHA not in cookie.value
    client.post("/sair/")
    pagina = client.get("/entrar/").content.decode()
    assert 'value="ana@exemplo.com"' in pagina
    assert re.search(r'name="lembrar_email"[^>]*checked', pagina)


def test_desmarcar_lembrar_email_apaga(client, ana):
    entrar(client, lembrar_email="on")
    client.post("/sair/")
    r = entrar(client)
    assert r.cookies[COOKIE_EMAIL].value == ""
    client.post("/sair/")
    assert 'value="ana@exemplo.com"' not in client.get("/entrar/").content.decode()


def test_cookie_de_email_adulterado_e_ignorado(client):
    client.cookies[COOKIE_EMAIL] = "invasor@exemplo.com:assinatura-falsa"
    assert "invasor@exemplo.com" not in client.get("/entrar/").content.decode()


# 3. Derrubar sessões.
def test_desconectar_derruba_todas_as_sessoes_inclusive_manter_conectado(ana, chefe, caplog):
    no_celular, no_notebook = Client(), Client()
    entrar(no_celular)
    entrar(no_notebook, manter_conectado="on")
    with caplog.at_level(logging.INFO, logger="infra_vibecoding.auditoria"):
        derrubados, negados = desconectar(chefe, [ana])
    assert derrubados == [ana] and negados == []
    assert not conectado(no_celular) and not conectado(no_notebook)
    assert "chefe@exemplo.com desconectou ana@exemplo.com" in caplog.text
    assert conectado(Client()) is False
    novo = Client()
    entrar(novo)
    assert conectado(novo)  # pode entrar de novo normalmente


def test_sem_permissao_nao_derruba(ana):
    beto = Usuario.objects.create_user("beto@exemplo.com", password=SENHA)
    sessao_da_ana = Client()
    entrar(sessao_da_ana)
    derrubados, negados = desconectar(beto, [ana])
    assert derrubados == [] and negados == [ana]
    assert conectado(sessao_da_ana)


def test_desconectar_uma_lista_so_derruba_quem_pode(chefe, ana):
    beto = Usuario.objects.create_user("beto@exemplo.com", password=SENHA)
    sessoes = {}
    for email in ("ana@exemplo.com", "beto@exemplo.com"):
        sessoes[email] = Client()
        entrar(sessoes[email], email)
    derrubados, _ = desconectar(chefe, [ana, beto])
    assert {u.email for u in derrubados} == {"ana@exemplo.com", "beto@exemplo.com"}
    assert not any(conectado(c) for c in sessoes.values())


def test_quem_pede_continua_conectado(chefe, rf):
    tela_do_chefe, outra_do_chefe = Client(), Client()
    entrar(tela_do_chefe, "chefe@exemplo.com")
    entrar(outra_do_chefe, "chefe@exemplo.com")
    tela_do_chefe.post("/sair-de-todos/")
    assert conectado(tela_do_chefe)
    assert not conectado(outra_do_chefe)


def test_sair_de_todos_so_por_formulario(client, ana):
    entrar(client)
    assert client.get("/sair-de-todos/").status_code == 405
    assert client.post("/sair-de-todos/").status_code == 302


def test_acao_desconectar_na_tela_de_banco(chefe, ana, caplog):
    sessao_da_ana = Client()
    entrar(sessao_da_ana)
    admin = Client()
    admin.force_login(chefe)
    with caplog.at_level(logging.INFO, logger="infra_vibecoding.auditoria"):
        r = admin.post("/gestao-interna/app_teste/usuarioteste/", {
            "action": "desconectar_de_todos_os_aparelhos", "_selected_action": [ana.pk],
        })
    assert r.status_code == 302
    assert not conectado(sessao_da_ana)
    assert "admin: chefe@exemplo.com desconectou ana@exemplo.com" in caplog.text


def test_trocar_a_senha_tambem_derruba_as_outras(client, ana):
    outra = Client()
    entrar(outra, manter_conectado="on")
    entrar(client)
    client.post("/trocar-senha/", {"old_password": SENHA, "new_password1": NOVA, "new_password2": NOVA})
    assert conectado(client) and not conectado(outra)


# 4. Cadastro público.
@pytest.fixture
def cadastro_ligado(settings):
    settings.CADASTRO_PUBLICO = CADASTRO
    return settings


def pedir_cadastro(client, email="nova@cliente.com", **extras):
    dados = {"email": email, "nome": "Nova", "empresa": "Cliente SA", "aceite": "on", **extras}
    return client.post("/criar-conta/", dados)


def test_cadastro_desligado_por_padrao(client):
    assert client.get("/criar-conta/").status_code == 404
    assert "Criar conta" not in client.get("/entrar/").content.decode()
    assert sec08_cadastro_publico() == []


def test_cadastro_completo(client, cadastro_ligado, mailoutbox, caplog):
    assert "Criar conta" in client.get("/entrar/").content.decode()
    r = pedir_cadastro(client)
    assert r.status_code == 200 and "Enviamos um link" in r.content.decode()
    assert not Usuario._base_manager.filter(email="nova@cliente.com").exists()  # a conta ainda não existe
    assert mailoutbox[0].to == ["nova@cliente.com"]
    assert mailoutbox[0].subject == "[Sistema de Teste] Confirme o seu e-mail para criar a conta"
    link = link_do_email(mailoutbox[0])
    aberto = client.get(link)
    assert aberto.status_code == 302 and aberto["Location"] == "/criar-conta/senha/"
    with caplog.at_level(logging.INFO, logger="infra_vibecoding.auditoria"):
        r = client.post("/criar-conta/senha/", {"new_password1": NOVA, "new_password2": NOVA})
    assert r.status_code == 302 and r["Location"] == "/"
    assert conectado(client)
    nova = Usuario._base_manager.get(email="nova@cliente.com")
    assert nova.nome == "Nova" and nova.check_password(NOVA)
    assert nova.email_confirmado_em is not None and nova.termos_aceitos_em is not None
    setor = Setor._base_manager.get(nome="Cliente SA")
    assert AcessoSetor._base_manager.filter(usuario=nova, setor=setor, pode_editar=True).exists()
    assert "cadastro público: nova@cliente.com criou a própria conta" in caplog.text
    assert "foi definida" in mailoutbox[-1].body


def test_cadastro_exige_aceite_dos_termos(client, cadastro_ligado, mailoutbox):
    r = pedir_cadastro(client, aceite="")
    assert "é preciso aceitar os termos" in r.content.decode()
    assert mailoutbox == []
    pagina = client.get("/criar-conta/").content.decode()
    assert 'href="/termos/"' in pagina and 'href="/privacidade/"' in pagina


def test_armadilha_contra_robos(client, cadastro_ligado, mailoutbox):
    normal = pedir_cadastro(Client(), "a@cliente.com").content
    robo = pedir_cadastro(Client(), "b@cliente.com", site="http://spam").content
    assert mailoutbox and all(m.to != ["b@cliente.com"] for m in mailoutbox)
    assert normal.replace(b"a@cliente.com", b"") == robo.replace(b"b@cliente.com", b"")


def test_email_que_ja_tem_conta_recebe_aviso_e_a_tela_nao_revela(cadastro_ligado, ana, mailoutbox):
    existe = pedir_cadastro(Client(), "ana@exemplo.com").content
    nao_existe = pedir_cadastro(Client(), "nova@cliente.com").content
    assert existe == nao_existe
    aviso = next(m for m in mailoutbox if m.to == ["ana@exemplo.com"])
    assert aviso.subject.endswith("Você já tem uma conta")
    assert "/esqueci-a-senha/" in aviso.body and "/criar-conta/" not in aviso.body


def test_regra_do_sistema_pode_recusar(client, cadastro_ligado, mailoutbox):
    r = pedir_cadastro(client, empresa="Proibida")
    assert "Nome de empresa não permitido." in r.content.decode()
    assert mailoutbox == []


def test_link_adulterado_ou_vencido(client, cadastro_ligado, mailoutbox, monkeypatch):
    pedir_cadastro(client)
    link = link_do_email(mailoutbox[0])
    assert "Link inválido" in client.get(link[:-5] + "xxxx/").content.decode()
    assert "Link inválido" in Client().get("/criar-conta/senha/").content.decode()
    monkeypatch.setattr(modulo_cadastro, "VALIDADE_DO_LINK", -1)
    assert "Link inválido" in Client().get(link).content.decode()


def test_link_reusado_depois_de_criar_a_conta(client, cadastro_ligado, mailoutbox):
    pedir_cadastro(client)
    link = link_do_email(mailoutbox[0])
    client.get(link)
    client.post("/criar-conta/senha/", {"new_password1": NOVA, "new_password2": NOVA})
    outro = Client()
    outro.get(link)
    r = outro.post("/criar-conta/senha/", {"new_password1": NOVA + "x", "new_password2": NOVA + "x"})
    assert "já tem uma conta" in r.content.decode()
    assert Usuario._base_manager.get(email="nova@cliente.com").check_password(NOVA)


def test_senha_fraca_no_cadastro(client, cadastro_ligado, mailoutbox):
    pedir_cadastro(client)
    client.get(link_do_email(mailoutbox[0]))
    for s1, s2 in (("123456", "123456"), ("nova@cliente.com", "nova@cliente.com"), (NOVA, NOVA + "x")):
        r = client.post("/criar-conta/senha/", {"new_password1": s1, "new_password2": s2})
        assert r.status_code == 200
    assert not Usuario._base_manager.filter(email="nova@cliente.com").exists()


def test_falha_no_encaixe_desfaz_tudo(client, cadastro_ligado, mailoutbox):
    pedir_cadastro(client, empresa="explode")
    client.get(link_do_email(mailoutbox[0]))
    with pytest.raises(RuntimeError):
        client.post("/criar-conta/senha/", {"new_password1": NOVA, "new_password2": NOVA})
    assert not Usuario._base_manager.filter(email="nova@cliente.com").exists()
    assert not Setor._base_manager.filter(nome="explode").exists()


def test_limite_de_pedidos_no_cadastro(cadastro_ligado, mailoutbox):
    for _ in range(5):
        pedir_cadastro(Client())
    assert len(mailoutbox) == 3


@pytest.mark.parametrize("caminho", ["tests.app_teste.cadastro.CadastroSemTermos", "tests.app_teste.nao_existe.X"])
def test_cadastro_mal_configurado_nao_liga(settings, caminho):
    settings.CADASTRO_PUBLICO = caminho
    assert [e.id for e in sec08_cadastro_publico()] == ["SEC.E084"]


def test_cadastro_bem_configurado_passa(cadastro_ligado):
    assert sec08_cadastro_publico() == []
