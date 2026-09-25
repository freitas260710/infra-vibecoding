"""Testes das telas de login do 00 e do primeiro acesso seguro (US 3.1, D43)."""
import logging
import re
from datetime import datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import Client

from infra_vibecoding.checagens import sec08_telas_de_login_do_00
from infra_vibecoding.dados import SemPermissao
from infra_vibecoding.login import convidar
from infra_vibecoding.login.links import LINK_CONVITE, LINK_REDEFINIR

pytestmark = pytest.mark.django_db
Usuario = get_user_model()
SENHA = "uma-senha-bem-longa-para-teste"
NOVA = "outra-senha-bem-longa-para-teste"


@pytest.fixture(autouse=True)
def limpar_limites():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def ana():
    return Usuario.objects.create_user("ana@exemplo.com", password=SENHA, nome="Ana")


@pytest.fixture
def novo():
    """Usuário criado por um colega: sem senha."""
    return Usuario.objects.create_user("novo@exemplo.com", nome="Novo")


@pytest.fixture
def chefe():
    return Usuario.objects.create_superuser("chefe@exemplo.com", password=SENHA)


def link_do_email(mensagem):
    return re.search(r"http://testserver(/\S+)", mensagem.body).group(1)


def pedir(client, tela, email):
    return client.post(f"/{tela}/", {"email": email})


def definir(client, link, senha1=NOVA, senha2=None):
    """Abre o link do e-mail e define a senha. Devolve a resposta do envio da senha."""
    aberto = client.get(link)
    assert aberto.status_code == 302, aberto.content.decode()[:500]
    return client.post(aberto["Location"], {"new_password1": senha1, "new_password2": senha2 or senha1})


# 1. Entrar e sair.
def test_tela_de_entrar_abre_sem_login(client):
    r = client.get("/entrar/")
    assert r.status_code == 200
    assert "Esqueci a senha" in r.content.decode() and "Primeiro acesso" in r.content.decode()


def test_entrar_pelo_email(client, ana):
    r = client.post("/entrar/", {"username": "Ana@Exemplo.com", "password": SENHA})
    assert r.status_code == 302 and r["Location"] == "/"
    assert client.get("/painel/").status_code == 200


def test_senha_errada_nao_entra(client, ana):
    r = client.post("/entrar/", {"username": "ana@exemplo.com", "password": SENHA + "x"})
    assert r.status_code == 200
    assert "E-mail ou senha incorretos." in r.content.decode()


def test_usuario_sem_senha_nao_entra_com_nada(client, novo):
    for tentativa in ("", " ", SENHA, "!"):
        r = client.post("/entrar/", {"username": "novo@exemplo.com", "password": tentativa})
        assert r.status_code == 200
    assert client.get("/painel/").status_code == 302


def test_entrar_nao_redireciona_para_outro_site(client, ana):
    r = client.post("/entrar/?next=https://site-falso.com/", {
        "username": "ana@exemplo.com", "password": SENHA, "next": "https://site-falso.com/",
    })
    assert r.status_code == 302 and r["Location"] == "/"


def test_sair_so_por_envio_de_formulario(client, ana):
    client.force_login(ana)
    assert client.get("/sair/").status_code == 405  # link malicioso não desloga ninguém
    r = client.post("/sair/")
    assert r.status_code == 302 and r["Location"] == "/entrar/"
    assert client.get("/painel/").status_code == 302


# 2. Primeiro acesso.
def test_primeiro_acesso_manda_link_e_define_a_senha(client, novo, mailoutbox, caplog):
    r = pedir(client, "primeiro-acesso", " Novo@Exemplo.com ")
    assert r.status_code == 200
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["novo@exemplo.com"]
    assert mailoutbox[0].subject == "[Sistema de Teste] Seu acesso foi criado"
    link = link_do_email(mailoutbox[0])
    assert link.startswith("/primeiro-acesso/")
    assert "72 horas" in mailoutbox[0].body

    with caplog.at_level(logging.INFO, logger="infra_vibecoding.auditoria"):
        r = definir(client, link)
    assert r.status_code == 302 and r["Location"] == "/"
    assert client.get("/painel/").status_code == 200  # já entrou
    novo = Usuario._base_manager.get(pk=novo.pk)
    assert novo.check_password(NOVA)
    assert novo.email_confirmado_em is not None
    assert "novo@exemplo.com definiu a senha pelo link do e-mail" in caplog.text
    # E-mail de aviso: se não foi a pessoa, ela fica sabendo.
    assert len(mailoutbox) == 2
    assert mailoutbox[1].subject == "[Sistema de Teste] Sua senha foi definida"
    assert "foi definida" in mailoutbox[1].body


def test_codigo_do_link_nao_fica_no_endereco_da_tela_de_senha(client, novo, mailoutbox):
    pedir(client, "primeiro-acesso", "novo@exemplo.com")
    link = link_do_email(mailoutbox[0])
    codigo = link.rstrip("/").rsplit("/", 1)[1]
    aberto = client.get(link)
    assert codigo not in aberto["Location"]
    assert aberto["Location"].endswith("/definir/")
    assert client.get(aberto["Location"]).status_code == 200


def test_resposta_igual_exista_o_email_ou_nao(client, novo, mailoutbox):
    existe = pedir(Client(), "primeiro-acesso", "novo@exemplo.com").content
    nao_existe = pedir(Client(), "primeiro-acesso", "ninguem@exemplo.com").content
    assert existe == nao_existe
    assert len(mailoutbox) == 1


def test_usuario_desativado_nao_recebe_link(client, novo, mailoutbox):
    novo.is_active = False
    novo.salvar_como_sistema("teste: desativar")
    pedir(client, "primeiro-acesso", "novo@exemplo.com")
    assert mailoutbox == []


def test_link_vale_uma_vez_so(client, novo, mailoutbox):
    pedir(client, "primeiro-acesso", "novo@exemplo.com")
    link = link_do_email(mailoutbox[0])
    definir(client, link)
    outro = Client()
    r = outro.get(link)
    assert r.status_code == 200
    assert "Link inválido ou vencido" in r.content.decode()


def test_link_de_convite_vence_em_72_horas(client, novo, mailoutbox, monkeypatch):
    pedir(client, "primeiro-acesso", "novo@exemplo.com")
    link = link_do_email(mailoutbox[0])
    monkeypatch.setattr(LINK_CONVITE, "_now", lambda: datetime.now() + timedelta(hours=71))
    assert client.get(link).status_code == 302
    monkeypatch.setattr(LINK_CONVITE, "_now", lambda: datetime.now() + timedelta(hours=73))
    assert "Link inválido ou vencido" in Client().get(link).content.decode()


def test_link_morre_se_o_usuario_for_desativado_ou_trocar_de_email(novo, mailoutbox):
    pedir(Client(), "primeiro-acesso", "novo@exemplo.com")
    link = link_do_email(mailoutbox[0])
    novo.email = "trocado@exemplo.com"
    novo.salvar_como_sistema("teste: trocar e-mail")
    assert "Link inválido" in Client().get(link).content.decode()

    cache.clear()
    pedir(Client(), "primeiro-acesso", "trocado@exemplo.com")
    link = link_do_email(mailoutbox[1])
    novo.is_active = False
    novo.salvar_como_sistema("teste: desativar")
    assert "Link inválido" in Client().get(link).content.decode()


def test_codigo_inventado_ou_de_outro_usuario_nao_serve(client, novo, ana, mailoutbox):
    pedir(client, "primeiro-acesso", "novo@exemplo.com")
    link = link_do_email(mailoutbox[0])
    _, _, uid, codigo, _ = link.split("/")
    assert "Link inválido" in client.get(f"/primeiro-acesso/{uid}/{codigo[:-1]}x/").content.decode()
    assert "Link inválido" in client.get(f"/primeiro-acesso/{uid}/1-abc/").content.decode()
    assert "Link inválido" in client.get(f"/primeiro-acesso/lixo/{codigo}/").content.decode()
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    uid_ana = urlsafe_base64_encode(force_bytes(ana.pk))
    assert "Link inválido" in client.get(f"/primeiro-acesso/{uid_ana}/{codigo}/").content.decode()
    assert "Link inválido" in client.get(f"/primeiro-acesso/{uid}/definir/").content.decode()


def test_link_de_convite_nao_serve_na_redefinicao(client, novo, mailoutbox):
    pedir(client, "primeiro-acesso", "novo@exemplo.com")
    link = link_do_email(mailoutbox[0]).replace("/primeiro-acesso/", "/redefinir-senha/")
    assert "Link inválido" in client.get(link).content.decode()


def test_senha_fraca_ou_diferente_e_recusada(client, novo, mailoutbox):
    pedir(client, "primeiro-acesso", "novo@exemplo.com")
    link = link_do_email(mailoutbox[0])
    aberto = client.get(link)
    for s1, s2 in (("123456", "123456"), ("curta", "curta"), ("12345678901", "12345678901"),
                   ("novo@exemplo.com", "novo@exemplo.com"), (NOVA, NOVA + "x")):
        r = client.post(aberto["Location"], {"new_password1": s1, "new_password2": s2})
        assert r.status_code == 200
    assert not Usuario._base_manager.get(pk=novo.pk).has_usable_password()


def test_limite_de_links_por_email(client, novo, mailoutbox):
    for _ in range(5):
        r = pedir(Client(), "primeiro-acesso", "novo@exemplo.com")
        assert r.status_code == 200
    assert len(mailoutbox) == 3


def test_limite_de_pedidos_por_endereco(client, chefe, mailoutbox):
    for i in range(12):
        Usuario.objects.create_user(f"pessoa{i}@exemplo.com")
        pedir(client, "primeiro-acesso", f"pessoa{i}@exemplo.com")
    assert len(mailoutbox) == 10


def test_endereco_falso_no_pedido_nao_gera_link(novo, mailoutbox):
    """Envenenamento do link: alguém pede o link fingindo outro endereço de site."""
    r = Client().post("/primeiro-acesso/", {"email": "novo@exemplo.com"}, HTTP_HOST="site-falso.com")
    assert r.status_code == 400
    assert mailoutbox == []


# 3. Esqueci a senha.
def test_esqueci_a_senha_manda_link_de_redefinicao(client, ana, mailoutbox):
    pedir(client, "esqueci-a-senha", "ana@exemplo.com")
    assert len(mailoutbox) == 1
    assert mailoutbox[0].subject == "[Sistema de Teste] Redefinição de senha"
    link = link_do_email(mailoutbox[0])
    assert link.startswith("/redefinir-senha/")
    r = definir(client, link)
    assert r.status_code == 302
    assert not Client().login(email="ana@exemplo.com", password=SENHA)
    assert Client().login(email="ana@exemplo.com", password=NOVA)
    assert "foi trocada" in mailoutbox[1].body
    assert "Link inválido" in Client().get(link).content.decode()


def test_link_de_redefinicao_vence_em_1_hora(client, ana, mailoutbox, monkeypatch):
    pedir(client, "esqueci-a-senha", "ana@exemplo.com")
    link = link_do_email(mailoutbox[0])
    monkeypatch.setattr(LINK_REDEFINIR, "_now", lambda: datetime.now() + timedelta(minutes=61))
    assert "Link inválido" in client.get(link).content.decode()


def test_esqueci_a_senha_de_quem_nunca_definiu_manda_o_primeiro_acesso(client, novo, mailoutbox):
    pedir(client, "esqueci-a-senha", "novo@exemplo.com")
    assert link_do_email(mailoutbox[0]).startswith("/primeiro-acesso/")


def test_esqueci_a_senha_nao_revela_email(novo, mailoutbox):
    assert (pedir(Client(), "esqueci-a-senha", "novo@exemplo.com").content
            == pedir(Client(), "esqueci-a-senha", "nao-existe@exemplo.com").content)


# 4. Trocar a senha (logado).
def test_trocar_senha_exige_login(client):
    r = client.get("/trocar-senha/")
    assert r.status_code == 302 and r["Location"].startswith("/entrar/")


def test_trocar_senha(client, ana, mailoutbox, caplog):
    client.login(email="ana@exemplo.com", password=SENHA)
    outra_sessao = Client()
    outra_sessao.login(email="ana@exemplo.com", password=SENHA)

    r = client.post("/trocar-senha/", {"old_password": "errada", "new_password1": NOVA, "new_password2": NOVA})
    assert r.status_code == 200
    with caplog.at_level(logging.INFO, logger="infra_vibecoding.auditoria"):
        r = client.post("/trocar-senha/", {"old_password": SENHA, "new_password1": NOVA, "new_password2": NOVA})
    assert r.status_code == 302
    assert "ana@exemplo.com trocou a própria senha" in caplog.text
    assert client.get("/painel/").status_code == 200        # esta sessão continua
    assert outra_sessao.get("/painel/").status_code == 302  # as outras caem
    assert Client().login(email="ana@exemplo.com", password=NOVA)
    assert mailoutbox[-1].subject == "[Sistema de Teste] Sua senha foi definida"
    assert "foi trocada" in mailoutbox[-1].body


# 5. convidar(): abrir acesso para um colega.
def test_convidar_cria_sem_senha_e_manda_link(rf, chefe, mailoutbox, caplog):
    request = rf.get("/")
    with caplog.at_level(logging.INFO, logger="infra_vibecoding.auditoria"):
        colega = convidar(chefe, request, email=" Colega@Exemplo.com ", nome="Colega")
    assert colega.email == "colega@exemplo.com"
    assert not colega.has_usable_password()
    assert "chefe@exemplo.com abriu acesso para colega@exemplo.com" in caplog.text
    assert len(mailoutbox) == 1 and link_do_email(mailoutbox[0]).startswith("/primeiro-acesso/")
    r = definir(Client(), link_do_email(mailoutbox[0]))
    assert r.status_code == 302
    assert Client().login(email="colega@exemplo.com", password=NOVA)


def test_convidar_confere_a_regra_de_quem_pode_abrir_acesso(rf, ana, mailoutbox):
    with pytest.raises(SemPermissao):
        convidar(ana, rf.get("/"), email="colega@exemplo.com")
    assert not Usuario._base_manager.filter(email="colega@exemplo.com").exists()
    assert mailoutbox == []


def test_convidar_email_repetido(rf, chefe, ana, mailoutbox):
    with pytest.raises(ValidationError):
        convidar(chefe, rf.get("/"), email="ANA@exemplo.com")
    assert mailoutbox == []


def test_usuario_criado_sem_senha_nasce_travado(chefe):
    u = Usuario(email="x@exemplo.com")
    u.salvar(chefe)
    assert not Usuario._base_manager.get(pk=u.pk).has_usable_password()


# 6. Checagem: o sistema precisa usar as telas de login do 00.
def test_projeto_de_teste_usa_as_telas_do_00():
    assert sec08_telas_de_login_do_00() == []


def test_sistema_sem_as_telas_de_login_do_00_nao_liga(settings):
    settings.ROOT_URLCONF = "tests.urls_sem_declaracao"
    assert [e.id for e in sec08_telas_de_login_do_00()] == ["SEC.E083"]


def test_login_proprio_no_lugar_do_00_nao_liga(settings):
    settings.LOGIN_URL = "/painel/"
    assert [e.id for e in sec08_telas_de_login_do_00()] == ["SEC.E083"]


def test_emails_no_mac_aparecem_no_terminal():
    from infra_vibecoding import configuracoes

    assert configuracoes.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend"


def test_tela_de_banco_que_cria_usuario_com_senha_nao_liga():
    from django.contrib.admin import AdminSite

    from infra_vibecoding.admin import AdminUsuarioSeguro
    from infra_vibecoding.checagens import verificar_admin

    class ComSenha(AdminUsuarioSeguro):
        add_fieldsets = ((None, {"fields": ("email", "usable_password", "password1", "password2")}),)

    site = AdminSite(name="teste-senha")
    site.register(Usuario, ComSenha)
    assert [e.id for e in verificar_admin(site)] == ["SEC.E073"]

    class Reaberta(AdminUsuarioSeguro):
        def user_change_password(self, request, id, form_url=""):
            return None

    site = AdminSite(name="teste-reaberta")
    site.register(Usuario, Reaberta)
    assert [e.id for e in verificar_admin(site)] == ["SEC.E073"]

    site = AdminSite(name="teste-sem-senha")
    site.register(Usuario, AdminUsuarioSeguro)
    assert verificar_admin(site) == []
