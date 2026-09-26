"""Testes da verificação em duas etapas (US 3.4, D51): app autenticador (padrão), código por e-mail, códigos de
recuperação, obrigatoriedade (tela de banco em produção e regra do sistema) e a trava em todo pedido."""
import re
import time

import pyotp
import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client

from infra_vibecoding.checagens import sec06_dois_fatores
from infra_vibecoding.login import dois_fatores as df

pytestmark = pytest.mark.django_db
Usuario = get_user_model()
SENHA = "uma-senha-bem-longa-para-teste"
NOVA = "outra-senha-bem-longa-para-teste"


@pytest.fixture(autouse=True)
def relogio_parado(monkeypatch):
    """Relógio parado: o código do app não vira no meio do teste. avancar(s) anda o relógio."""
    agora = [time.time()]
    monkeypatch.setattr(time, "time", lambda: agora[0])
    cache.clear()
    yield agora
    cache.clear()


def avancar(relogio, segundos):
    relogio[0] += segundos


@pytest.fixture
def ana():
    return Usuario.objects.create_user("ana@exemplo.com", password=SENHA, nome="Ana")


def ligar_app(usuario):
    chave = df.nova_chave_do_app()
    codigos = df.ligar(usuario, df.APP, chave=chave)
    return chave, codigos


def ligar_email(usuario):
    return df.ligar(usuario, df.EMAIL)


def codigo_do_app(chave):
    # Pelo relógio parado do teste (time.time), o mesmo que o 00 usa. O .now() do pyotp lê o relógio real e, se o
    # teste cruzasse a virada de 30 segundos, geraria o código do passo seguinte (teste instável, 0.4.2).
    return pyotp.TOTP(chave).at(time.time())


def codigo_do_email(mensagem):
    return re.search(r"^(\d{6})$", mensagem.body, re.M).group(1)


def entrar(client, email="ana@exemplo.com", senha=SENHA, **extra):
    return client.post("/entrar/", {"username": email, "password": senha, **extra})


def logado(client):
    return client.get("/painel/").status_code == 200


# 1. Login com app autenticador.
def test_com_app_a_senha_certa_leva_para_o_codigo_e_ainda_nao_entra(client, ana):
    ligar_app(ana)
    r = entrar(client)
    assert r.status_code == 302 and r["Location"] == "/entrar/codigo/"
    assert not logado(client)
    assert "app autenticador" in client.get("/entrar/codigo/").content.decode()


def test_codigo_certo_do_app_entra(client, ana):
    chave, _ = ligar_app(ana)
    entrar(client)
    r = client.post("/entrar/codigo/", {"codigo": codigo_do_app(chave)})
    assert r.status_code == 302 and r["Location"] == "/"
    assert logado(client)


def test_codigo_errado_nao_entra_e_cinco_erros_voltam_para_o_login(client, ana):
    ligar_app(ana)
    entrar(client)
    r = client.post("/entrar/codigo/", {"codigo": "000000"})
    assert r.status_code == 200 and "Código incorreto" in r.content.decode()
    for _ in range(4):
        r = client.post("/entrar/codigo/", {"codigo": "000000"})
    assert r.status_code == 302 and r["Location"] == "/entrar/"
    assert client.get("/entrar/codigo/")["Location"] == "/entrar/"  # precisa digitar a senha de novo
    assert not logado(client)


def test_codigo_do_app_ja_usado_nao_vale_de_novo(ana):
    chave, _ = ligar_app(ana)
    codigo = codigo_do_app(chave)
    c1, c2 = Client(), Client()
    entrar(c1)
    c1.post("/entrar/codigo/", {"codigo": codigo})
    assert logado(c1)
    entrar(c2)
    r = c2.post("/entrar/codigo/", {"codigo": codigo})
    assert r.status_code == 200 and not logado(c2)


def test_codigo_do_app_de_um_minuto_atras_nao_vale(client, ana, relogio_parado):
    chave, _ = ligar_app(ana)
    codigo = codigo_do_app(chave)
    avancar(relogio_parado, 90)
    entrar(client)
    assert client.post("/entrar/codigo/", {"codigo": codigo}).status_code == 200
    assert not logado(client)


def test_tempo_para_digitar_o_codigo_acaba(client, ana, relogio_parado):
    chave, _ = ligar_app(ana)
    entrar(client)
    avancar(relogio_parado, 11 * 60)
    r = client.post("/entrar/codigo/", {"codigo": codigo_do_app(chave)})
    assert r["Location"] == "/entrar/" and not logado(client)


def test_manter_conectado_e_lembrar_email_continuam_valendo_com_2fa(client, ana):
    chave, _ = ligar_app(ana)
    entrar(client, manter_conectado="on", lembrar_email="on")
    r = client.post("/entrar/codigo/", {"codigo": codigo_do_app(chave)})
    assert client.session.get_expiry_age() == 30 * 24 * 60 * 60
    assert "iv_email_lembrado" in r.cookies


def test_next_e_respeitado_depois_do_codigo(client, ana):
    chave, _ = ligar_app(ana)
    entrar(client, next="/sobre/")
    r = client.post("/entrar/codigo/", {"codigo": codigo_do_app(chave)})
    assert r["Location"] == "/sobre/"


# 2. Login com código por e-mail.
def test_com_email_o_codigo_chega_e_entra(client, ana, mailoutbox):
    ligar_email(ana)
    entrar(client)
    assert len(mailoutbox) == 1 and "Seu código de acesso" in mailoutbox[0].subject
    tela = client.get("/entrar/codigo/").content.decode()
    assert "ana*****@exemplo.com" in tela
    client.post("/entrar/codigo/", {"codigo": codigo_do_email(mailoutbox[0])})
    assert logado(client)


def test_codigo_por_email_vence_em_10_minutos(client, ana, mailoutbox, relogio_parado):
    ligar_email(ana)
    entrar(client)
    avancar(relogio_parado, 9 * 60)
    client.post("/entrar/codigo/reenviar/")  # renova o tempo da tela, mas o código antigo foi trocado
    avancar(relogio_parado, 2 * 60)
    r = client.post("/entrar/codigo/", {"codigo": codigo_do_email(mailoutbox[0])})
    assert r.status_code == 200 and not logado(client)
    client.post("/entrar/codigo/", {"codigo": codigo_do_email(mailoutbox[1])})
    assert logado(client)


def test_reenviar_tem_limite(client, ana, mailoutbox):
    ligar_email(ana)
    entrar(client)
    for _ in range(6):
        client.post("/entrar/codigo/reenviar/")
    assert len(mailoutbox) == 5  # 1 do login + 4 reenvios


def test_quem_usa_app_nao_consegue_pedir_codigo_por_email(client, ana, mailoutbox):
    ligar_app(ana)
    entrar(client)
    client.post("/entrar/codigo/reenviar/")
    assert len(mailoutbox) == 0


# 3. Códigos de recuperação.
def test_codigo_de_recuperacao_entra_uma_vez_e_avisa(ana, mailoutbox):
    _, codigos = ligar_app(ana)
    assert len(codigos) == 10 and all(re.fullmatch(r"[A-Z0-9]{4}-[A-Z0-9]{4}", c) for c in codigos)
    c1 = Client()
    entrar(c1)
    r = c1.post("/entrar/codigo/", {"codigo": codigos[0].lower().replace("-", " ")})
    assert r.status_code == 302 and logado(c1)
    assert "código de recuperação" in mailoutbox[-1].body and "Restam 9" in mailoutbox[-1].body
    c2 = Client()
    entrar(c2)
    c2.post("/entrar/codigo/", {"codigo": codigos[0]})
    assert not logado(c2)


def test_codigos_ficam_guardados_como_senha(ana):
    chave, codigos = ligar_app(ana)
    ana.refresh_from_db()
    guardado = str(ana.codigos_de_recuperacao) + ana.segredo_do_app
    assert chave not in guardado and not any(c in guardado or c.replace("-", "") in guardado for c in codigos)
    assert df.decifrar(ana.segredo_do_app) == chave


# 4. Ativar pelo próprio usuário.
def test_ativar_app_mostra_qr_code_e_pede_senha_e_codigo(client, ana, mailoutbox):
    client.force_login(ana)
    tela = client.get("/dois-fatores/app/").content.decode()
    assert "<svg" in tela
    chave = client.session[df.SESSAO_ATIVACAO]
    chave = df.decifrar(chave["chave"])
    assert " ".join(chave[i:i + 4] for i in range(0, len(chave), 4)) in tela
    r = client.post("/dois-fatores/app/", {"senha": "errada", "codigo": codigo_do_app(chave)})
    assert "Senha incorreta" in r.content.decode()
    r = client.post("/dois-fatores/app/", {"senha": SENHA, "codigo": "000000"})
    assert "Código incorreto" in r.content.decode()
    r = client.post("/dois-fatores/app/", {"senha": SENHA, "codigo": codigo_do_app(chave)})
    tela = r.content.decode()
    assert "Guarde estes códigos agora" in tela and len(re.findall(r"<code>[A-Z0-9]{4}-[A-Z0-9]{4}</code>", tela)) == 10
    ana.refresh_from_db()
    assert ana.dois_fatores == "app" and df.decifrar(ana.segredo_do_app) == chave
    assert "foi ligada" in mailoutbox[-1].body
    assert logado(client)  # quem ativou continua dentro


def test_ativar_email(client, ana, mailoutbox):
    client.force_login(ana)
    client.get("/dois-fatores/email/")
    codigo = codigo_do_email(mailoutbox[-1])
    client.post("/dois-fatores/email/", {"senha": SENHA, "codigo": codigo})
    ana.refresh_from_db()
    assert ana.dois_fatores == "email" and ana.segredo_do_app == ""
    assert logado(client)


def test_ligar_derruba_as_outras_sessoes_que_nao_passaram_pelo_codigo(ana):
    outro = Client()
    outro.force_login(ana)
    assert logado(outro)
    ligar_app(ana)
    r = outro.get("/painel/")
    assert r.status_code == 302 and r["Location"] == "/entrar/"
    assert not logado(outro)


def test_novos_codigos_pedem_senha_e_os_antigos_deixam_de_valer(client, ana):
    chave, antigos = ligar_app(ana)
    entrar(client)
    client.post("/entrar/codigo/", {"codigo": codigo_do_app(chave)})
    r = client.post("/dois-fatores/novos-codigos/", {"senha": "errada"})
    assert r["Location"] == "/dois-fatores/"
    r = client.post("/dois-fatores/novos-codigos/", {"senha": SENHA})
    novos = re.findall(r"<code>([A-Z0-9]{4}-[A-Z0-9]{4})</code>", r.content.decode())
    assert len(novos) == 10
    ana.refresh_from_db()
    assert not df.usar_codigo_de_recuperacao(ana, antigos[0])
    assert df.usar_codigo_de_recuperacao(ana, novos[0])


def test_desligar_pede_senha_e_codigo(client, ana, mailoutbox):
    chave, _ = ligar_app(ana)
    entrar(client)
    client.post("/entrar/codigo/", {"codigo": codigo_do_app(chave)})
    r = client.post("/dois-fatores/desligar/", {"senha": SENHA, "codigo": "000000"})
    assert r.status_code == 200
    ana.refresh_from_db()
    assert ana.dois_fatores == "app"
    avancar_passo = pyotp.TOTP(chave).at(time.time() + 30)  # o código do momento já foi usado no login
    client.post("/dois-fatores/desligar/", {"senha": SENHA, "codigo": avancar_passo})
    ana.refresh_from_db()
    assert ana.dois_fatores == "" and ana.codigos_de_recuperacao == [] and ana.segredo_do_app == ""
    assert "foi desligada" in mailoutbox[-1].body


# 5. Esqueci a senha não pula o 2FA.
def test_esqueci_a_senha_pede_o_codigo_depois_da_senha_nova(client, ana, mailoutbox):
    chave, _ = ligar_app(ana)
    client.post("/esqueci-a-senha/", {"email": "ana@exemplo.com"})
    link = re.search(r"http://testserver(/\S+)", mailoutbox[-1].body).group(1)
    aberto = client.get(link)
    r = client.post(aberto["Location"], {"new_password1": NOVA, "new_password2": NOVA})
    assert r["Location"] == "/entrar/codigo/"
    assert not logado(client)
    client.post("/entrar/codigo/", {"codigo": codigo_do_app(chave)})
    assert logado(client)


# 6. Obrigatório: regra do sistema e tela de banco em produção.
@pytest.fixture
def obrigada(settings):
    settings.DOIS_FATORES_OBRIGATORIO = "tests.app_teste.regras.exige_dois_fatores"
    return Usuario.objects.create_user("obrigada@exemplo.com", password=SENHA, nome="Obrigada")


def test_obrigado_sem_2fa_fica_preso_na_tela_de_ativar(client, obrigada, ana):
    entrar(client, "obrigada@exemplo.com")
    r = client.get("/painel/")
    assert r.status_code == 302 and r["Location"] == "/dois-fatores/"
    assert "obrigatória para a sua conta" in client.get("/dois-fatores/").content.decode()
    assert client.get("/dois-fatores/app/").status_code == 200
    htmx = client.get("/painel/", headers={"HX-Request": "true"})
    assert htmx["HX-Redirect"] == "/dois-fatores/"
    # Quem não é obrigado usa normalmente.
    c = Client()
    entrar(c)
    assert logado(c)


def test_obrigado_depois_de_ativar_usa_o_sistema_e_nao_desliga(client, obrigada):
    entrar(client, "obrigada@exemplo.com")
    client.get("/dois-fatores/app/")
    chave = df.decifrar(client.session[df.SESSAO_ATIVACAO]["chave"])
    client.post("/dois-fatores/app/", {"senha": SENHA, "codigo": codigo_do_app(chave)})
    assert logado(client)
    r = client.get("/dois-fatores/desligar/")
    assert r["Location"] == "/dois-fatores/"
    obrigada.refresh_from_db()
    assert obrigada.dois_fatores == "app"


def test_obrigado_pode_usar_email(client, obrigada, mailoutbox):
    entrar(client, "obrigada@exemplo.com")
    client.get("/dois-fatores/email/")
    client.post("/dois-fatores/email/", {"senha": SENHA, "codigo": codigo_do_email(mailoutbox[-1])})
    assert logado(client)


def test_tela_de_banco_em_producao_exige_app(client, settings, mailoutbox):
    settings.PRODUCAO = True
    chefe = Usuario.objects.create_superuser("chefe@exemplo.com", password=SENHA)
    entrar(client, "chefe@exemplo.com")
    assert client.get("/gestao-interna/")["Location"] == "/dois-fatores/"
    r = client.get("/dois-fatores/email/")
    assert r["Location"] == "/dois-fatores/"  # e-mail não vale para a tela de banco
    # Quem tinha e-mail também é mandado trocar para o app.
    ligar_email(chefe)
    c = Client()
    entrar(c, "chefe@exemplo.com")
    c.post("/entrar/codigo/", {"codigo": codigo_do_email(mailoutbox[-1])})
    assert c.get("/gestao-interna/")["Location"] == "/dois-fatores/"


def test_tela_de_banco_fora_de_producao_nao_exige(client):
    Usuario.objects.create_superuser("chefe@exemplo.com", password=SENHA)
    entrar(client, "chefe@exemplo.com")
    assert client.get("/gestao-interna/").status_code == 200


# 7. Nenhum login escapa.
def test_sessao_sem_o_codigo_e_derrubada(client, ana, caplog):
    ligar_app(ana)
    client.force_login(ana)  # login por outro caminho, sem passar pelo código
    r = client.get("/painel/")
    assert r.status_code == 302 and r["Location"] == "/entrar/"
    assert not logado(client)
    assert "sem a verificação em duas etapas foi derrubada" in caplog.text


def test_login_da_tela_de_banco_vai_para_a_tela_de_entrar_do_00(client, ana):
    r = client.get("/gestao-interna/login/?next=/gestao-interna/")
    assert r.status_code == 302 and r["Location"].startswith("/entrar/?next=")
    r = client.post("/gestao-interna/login/", {"username": "ana@exemplo.com", "password": SENHA})
    assert r["Location"].startswith("/entrar/") and not logado(client)
    client.force_login(ana)
    assert client.get("/gestao-interna/login/").status_code == 403  # logado sem acesso: sem ir e voltar


def test_administrador_entra_na_tela_de_banco_pela_tela_de_entrar(client):
    Usuario.objects.create_superuser("chefe@exemplo.com", password=SENHA)
    r = client.get("/gestao-interna/", follow=True)
    assert r.redirect_chain[-1][0] == "/entrar/?next=%2Fgestao-interna%2F"
    r = client.post("/entrar/?next=/gestao-interna/", {"username": "chefe@exemplo.com", "password": SENHA,
                                                        "next": "/gestao-interna/"}, follow=True)
    assert r.status_code == 200 and r.redirect_chain[-1][0] == "/gestao-interna/"
    assert client.get("/gestao-interna/login/?next=/gestao-interna/")["Location"] == "/gestao-interna/"


def test_admin_zera_o_2fa_derruba_as_sessoes_e_avisa(client, ana, mailoutbox):
    chave, _ = ligar_app(ana)
    c_ana = Client()
    entrar(c_ana)
    c_ana.post("/entrar/codigo/", {"codigo": codigo_do_app(chave)})
    assert logado(c_ana)
    chefe = Usuario.objects.create_superuser("chefe@exemplo.com", password=SENHA)
    client.force_login(chefe)
    r = client.post("/gestao-interna/app_teste/usuarioteste/", {
        "action": "zerar_verificacao_em_duas_etapas", "_selected_action": [ana.pk]})
    assert r.status_code == 302
    ana.refresh_from_db()
    assert ana.dois_fatores == "" and ana.segredo_do_app == ""
    assert not logado(c_ana)
    assert "zerou a verificação" in mailoutbox[-1].body


def test_errar_o_codigo_conta_no_bloqueio_de_login(client, ana, settings):
    settings.LIMITES_NOS_TESTES = True
    chave, _ = ligar_app(ana)
    for _ in range(5):
        c = Client()
        entrar(c)
        c.post("/entrar/codigo/", {"codigo": "000000"})
    c = Client()
    r = entrar(c)
    assert "Muitas tentativas de entrar" in r.content.decode()


# 8. Checagens.
def test_sem_a_trava_de_2fa_o_sistema_nao_liga(settings):
    settings.MIDDLEWARE = [m for m in settings.MIDDLEWARE if "ExigeDoisFatores" not in m]
    assert [e.id for e in sec06_dois_fatores()] == ["SEC.E068"]


def test_regra_de_obrigatorio_inexistente_e_barrada(settings):
    settings.DOIS_FATORES_OBRIGATORIO = "tests.app_teste.regras.nao_existe"
    assert [e.id for e in sec06_dois_fatores()] == ["SEC.E069"]


def test_configuracao_padrao_passa_na_checagem():
    assert sec06_dois_fatores() == []
    call_command("check")
