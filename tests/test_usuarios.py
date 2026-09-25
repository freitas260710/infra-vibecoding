"""Testes da tabela de usuário segura e do login pelo e-mail (US 2.4)."""
import logging

import pytest
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management import CommandError, call_command
from django.test import override_settings

from infra_vibecoding.checagens import sec08_usuario_seguro
from infra_vibecoding.dados import AcessoSemEscopo, EscritaSemAutorizacao, SemPermissao

pytestmark = pytest.mark.django_db
Usuario = get_user_model()
SENHA = "uma-senha-bem-longa-para-teste"
ADMIN_USUARIOS = "/gestao-interna/app_teste/usuarioteste/"


@pytest.fixture
def ana():
    return Usuario.objects.create_user("ana@exemplo.com", password=SENHA)


@pytest.fixture
def beto():
    return Usuario.objects.create_user("beto@exemplo.com", password=SENHA)


@pytest.fixture
def chefe():
    return Usuario.objects.create_superuser("chefe@exemplo.com", password=SENHA)


def ids(erros):
    return sorted({e.id for e in erros})


# 1. Login pelo e-mail.
def test_login_pelo_email(client, ana):
    assert client.login(email="ana@exemplo.com", password=SENHA)


def test_login_nao_diferencia_maiusculas_no_email(client, ana):
    assert client.login(email="Ana@Exemplo.COM", password=SENHA)


def test_senha_errada_nao_entra(client, ana):
    assert not client.login(email="ana@exemplo.com", password=SENHA + "x")


def test_email_inexistente_nao_entra(client):
    assert not client.login(email="ninguem@exemplo.com", password=SENHA)


def test_usuario_inativo_nao_entra(client, ana):
    ana.is_active = False
    ana.salvar_como_sistema("teste: desativar")
    assert not client.login(email="ana@exemplo.com", password=SENHA)


def test_login_grava_a_data_do_ultimo_login(client, ana):
    assert ana.last_login is None
    client.login(email="ana@exemplo.com", password=SENHA)
    assert Usuario._base_manager.get(pk=ana.pk).last_login is not None


def test_sessao_carrega_o_usuario_a_cada_pedido(client, ana):
    client.login(email="ana@exemplo.com", password=SENHA)
    r = client.get("/painel/")
    assert r.status_code == 200
    assert "ana@exemplo.com" in r.content.decode()


def test_senha_guardada_em_metodo_antigo_e_atualizada_no_login(ana):
    Usuario._base_manager.filter(pk=ana.pk).update(password=make_password(SENHA, hasher="pbkdf2_sha256"))
    assert authenticate(email="ana@exemplo.com", password=SENHA) is not None
    assert Usuario._base_manager.get(pk=ana.pk).password.startswith("argon2")


def test_email_guardado_em_minusculas():
    u = Usuario.objects.create_user("  Carla@Exemplo.COM ", password=SENHA)
    assert u.email == "carla@exemplo.com"


def test_criar_usuario_fica_registrado(caplog):
    with caplog.at_level(logging.INFO, logger="infra_vibecoding.auditoria"):
        Usuario.objects.create_user("dani@exemplo.com", password=SENHA)
    assert "criação de usuário: dani@exemplo.com" in caplog.text


# 2. A tabela de usuário tem a mesma trava das outras.
@pytest.mark.parametrize("tentativa", [
    lambda: list(Usuario.objects.all()),
    lambda: list(Usuario.objects.filter(email__icontains="exemplo")),
    lambda: Usuario.objects.get(email="ana@exemplo.com"),
    lambda: Usuario.objects.count(),
    lambda: list(Usuario.objects.values_list("email", flat=True)),
    lambda: Usuario.objects.update(is_staff=True),
])
def test_listar_ou_buscar_usuarios_sem_escopo_e_bloqueado(ana, beto, tentativa):
    with pytest.raises((AcessoSemEscopo, EscritaSemAutorizacao)):
        tentativa()


def test_para_mostra_so_o_que_a_regra_deixa(ana, beto):
    assert list(Usuario.objects.para(ana).values_list("email", flat=True)) == ["ana@exemplo.com"]


def test_alterar_usuario_sem_dizer_quem_e_bloqueado(ana):
    ana.nome = "Ana"
    with pytest.raises(EscritaSemAutorizacao):
        ana.save()
    with pytest.raises(EscritaSemAutorizacao):
        ana.save(update_fields=["nome"])
    ana.is_staff = True
    with pytest.raises(EscritaSemAutorizacao):
        ana.save(update_fields=["last_login", "is_staff"])


def test_alterar_usuario_passa_pela_regra(ana, beto):
    ana.nome = "Ana"
    ana.salvar(ana)  # a regra deixa editar a si mesmo
    beto.nome = "Beto"
    with pytest.raises(SemPermissao):
        beto.salvar(ana)


def test_excluir_usuario_sem_dizer_quem_e_bloqueado(ana):
    with pytest.raises(EscritaSemAutorizacao):
        ana.delete()


# 3. Comando createsuperuser.
def test_createsuperuser_pelo_email(monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", SENHA)
    call_command("createsuperuser", email="Root@Exemplo.com", interactive=False, verbosity=0)
    root = Usuario._base_manager.get(email="root@exemplo.com")
    assert root.is_superuser and root.is_staff


def test_createsuperuser_com_email_repetido_recusa(monkeypatch, chefe):
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", SENHA)
    with pytest.raises(CommandError):
        call_command("createsuperuser", email="chefe@exemplo.com", interactive=False, verbosity=0)


# 4. Tela de banco (admin) da tabela de usuário.
def test_admin_lista_usuarios(client, chefe, ana):
    client.force_login(chefe)
    r = client.get(ADMIN_USUARIOS)
    assert r.status_code == 200
    assert "ana@exemplo.com" in r.content.decode()


def test_admin_cria_usuario_sem_senha_e_manda_o_link(client, chefe, caplog, mailoutbox):
    client.force_login(chefe)
    with caplog.at_level(logging.INFO, logger="infra_vibecoding.auditoria"):
        r = client.post(ADMIN_USUARIOS + "add/", {
            "email": "Novo@Exemplo.com", "nome": "Novo",
            # tentativa de mandar senha junto: ignorada, o formulário não tem campo de senha
            "usable_password": "true", "password1": SENHA, "password2": SENHA,
        })
    assert r.status_code == 302, r.content.decode()[:2000]
    novo = Usuario._base_manager.get(email="novo@exemplo.com")
    assert not novo.has_usable_password()
    assert not novo.check_password(SENHA)
    assert "admin: chefe@exemplo.com criou" in caplog.text
    assert len(mailoutbox) == 1 and mailoutbox[0].to == ["novo@exemplo.com"]
    assert "/primeiro-acesso/" in mailoutbox[0].body


def test_admin_recusa_email_repetido_sem_quebrar(client, chefe, ana):
    client.force_login(chefe)
    r = client.post(ADMIN_USUARIOS + "add/", {"email": "ana@exemplo.com"})
    assert r.status_code == 200  # volta para o formulário com o erro
    assert Usuario._base_manager.filter(email="ana@exemplo.com").count() == 1


def test_admin_nao_define_senha_de_outra_pessoa(client, chefe, ana, caplog):
    client.force_login(chefe)
    nova = SENHA + "-nova"
    with caplog.at_level(logging.INFO, logger="infra_vibecoding.auditoria"):
        abrir = client.get(f"{ADMIN_USUARIOS}{ana.pk}/password/")
        enviar = client.post(f"{ADMIN_USUARIOS}{ana.pk}/password/", {
            "usable_password": "true", "password1": nova, "password2": nova,
        })
    assert abrir.status_code == 403 and enviar.status_code == 403
    assert Usuario._base_manager.get(pk=ana.pk).check_password(SENHA)
    assert f"tentou definir a senha do usuário {ana.pk} pela tela de banco (bloqueado)" in caplog.text


def test_edicao_de_usuario_so_mostra_a_situacao_da_senha(client, chefe, ana):
    client.force_login(chefe)
    pagina = client.get(f"{ADMIN_USUARIOS}{ana.pk}/change/").content.decode()
    assert "Definida pela própria pessoa." in pagina
    assert "../password/" not in pagina and "/password/" not in pagina
    novo = Usuario.objects.create_user("novo@exemplo.com")
    pagina = client.get(f"{ADMIN_USUARIOS}{novo.pk}/change/").content.decode()
    assert "Ainda não definida: aguardando o primeiro acesso." in pagina


def test_alterar_a_propria_senha_no_topo_da_tela_de_banco_vai_para_a_tela_do_00(client, chefe):
    client.force_login(chefe)
    r = client.get("/gestao-interna/password_change/")
    assert r.status_code == 302 and r["Location"] == "/trocar-senha/"


def _senhas_digitadas(monkeypatch, *senhas):
    import getpass

    fila = list(senhas)
    monkeypatch.setattr(getpass, "getpass", lambda *a, **k: fila.pop(0))


def test_changepassword_fora_de_producao_troca_com_registro_e_aviso(ana, monkeypatch, caplog, mailoutbox):
    nova = SENHA + "-teste"
    _senhas_digitadas(monkeypatch, "123456", "123456", nova, nova)  # a fraca é recusada, a segunda passa
    with caplog.at_level(logging.INFO, logger="infra_vibecoding.auditoria"):
        call_command("changepassword", "Ana@Exemplo.com")
    assert Usuario._base_manager.get(pk=ana.pk).check_password(nova)
    assert "terminal: senha de ana@exemplo.com trocada pelo changepassword (dev)" in caplog.text
    assert mailoutbox[-1].to == ["ana@exemplo.com"] and "foi trocada" in mailoutbox[-1].body


def test_changepassword_em_producao_bloqueado(ana, settings, monkeypatch):
    settings.AMBIENTE = "producao"
    _senhas_digitadas(monkeypatch, SENHA + "-x", SENHA + "-x")
    with pytest.raises(CommandError, match="Bloqueado em produção"):
        call_command("changepassword", "ana@exemplo.com")
    assert Usuario._base_manager.get(pk=ana.pk).check_password(SENHA)


def test_changepassword_usuario_inexistente(monkeypatch):
    with pytest.raises(CommandError, match="não existe"):
        call_command("changepassword", "ninguem@exemplo.com")


def test_admin_edita_usuario(client, chefe, ana):
    client.force_login(chefe)
    r = client.get(f"{ADMIN_USUARIOS}{ana.pk}/change/")
    assert r.status_code == 200


# 5. Checagens.
def test_checagens_ok_com_usuario_seguro():
    assert sec08_usuario_seguro() == []


@override_settings(AUTH_USER_MODEL="auth.User")
def test_usuario_padrao_do_django_nao_liga():
    assert "SEC.E081" in ids(sec08_usuario_seguro())


@pytest.mark.parametrize("backends", [
    ["django.contrib.auth.backends.ModelBackend"],
    ["infra_vibecoding.autenticacao.BackendSeguro", "django.contrib.auth.backends.ModelBackend"],
    [],
])
def test_trocar_o_login_do_00_nao_liga(backends):
    with override_settings(AUTHENTICATION_BACKENDS=backends):
        assert "SEC.E082" in ids(sec08_usuario_seguro())
