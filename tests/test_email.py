"""Testes do envio de e-mail com desvio para a caixa de teste fora de produção (US 3.1b, D39 e D45)."""
import importlib
import os
import re

import pytest
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage, get_connection
from django.test import Client

from infra_vibecoding import configuracoes
from infra_vibecoding import email as envio
from infra_vibecoding.checagens import sec09_email

ENVIO_00 = "infra_vibecoding.email.EnvioComDesvio"
CAIXA = "caixa-de-teste@exemplo.com"
LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


@pytest.fixture
def provedor(settings, monkeypatch):
    """Provedor ligado, com a entrega SMTP trocada por uma caixa de mentira (nada sai de verdade no teste)."""
    monkeypatch.setattr(envio, "ENTREGA_SMTP", LOCMEM)
    settings.EMAIL_HOST = "smtp.exemplo.com"
    settings.EMAIL_DE_TESTE = CAIXA
    settings.AMBIENTE = "dev"
    return settings


def enviar(para, cc=(), assunto="Assunto"):
    conexao = get_connection(ENVIO_00)
    return EmailMessage(assunto, "corpo", "nao-responda@exemplo.com", list(para), cc=list(cc),
                        connection=conexao).send()


# 1. Desvio.
def test_fora_de_producao_tudo_vai_para_a_caixa_de_teste(provedor):
    enviar(["ana@cliente.com"], cc=["beto@cliente.com"])
    assert len(mail.outbox) == 1
    m = mail.outbox[0]
    assert m.to == [CAIXA] and m.cc == [] and m.bcc == []
    assert m.subject == "[para: ana@cliente.com, beto@cliente.com] Assunto"
    assert m.extra_headers["X-Destinatario-Original"] == "ana@cliente.com, beto@cliente.com"


def test_em_producao_vai_para_os_destinatarios_de_verdade(provedor):
    provedor.AMBIENTE = "producao"
    enviar(["ana@cliente.com"])
    assert mail.outbox[0].to == ["ana@cliente.com"]
    assert mail.outbox[0].subject == "Assunto"


def test_sem_provedor_aparece_no_terminal_e_nada_sai(settings, capsys):
    settings.EMAIL_HOST = ""
    enviar(["ana@cliente.com"], assunto="Teste terminal")
    saida = capsys.readouterr().out
    assert "Teste terminal" in saida and "ana@cliente.com" in saida
    assert mail.outbox == []


def test_provedor_sem_caixa_de_teste_nao_envia(provedor):
    provedor.EMAIL_DE_TESTE = ""
    with pytest.raises(RuntimeError, match="EMAIL_DE_TESTE"):
        enviar(["ana@cliente.com"])
    assert mail.outbox == []


@pytest.mark.django_db
def test_primeiro_acesso_de_verdade_chega_na_caixa_de_teste(provedor):
    """Fluxo inteiro com o envio do 00: o link de primeiro acesso vai para a caixa de teste e funciona."""
    from django.contrib.auth import get_user_model

    cache.clear()
    provedor.EMAIL_BACKEND = ENVIO_00
    get_user_model().objects.create_user("novo@cliente.com")
    cliente = Client()
    cliente.post("/primeiro-acesso/", {"email": "novo@cliente.com"})
    m = mail.outbox[0]
    assert m.to == [CAIXA]
    assert m.subject.startswith("[para: novo@cliente.com] [Sistema de Teste] Seu acesso foi criado")
    link = re.search(r"http://testserver(/\S+)", m.body).group(1)
    aberto = cliente.get(link)
    senha = "uma-senha-bem-longa-para-teste"
    r = cliente.post(aberto["Location"], {"new_password1": senha, "new_password2": senha})
    assert r.status_code == 302
    assert Client().login(email="novo@cliente.com", password=senha)


# 2. Configurações ao ligar.
@pytest.fixture
def recarregar(monkeypatch):
    for nome in ("EMAIL_HOST", "EMAIL_REMETENTE", "EMAIL_DE_TESTE", "AMBIENTE"):
        monkeypatch.delenv(nome, raising=False)
    yield lambda: importlib.reload(configuracoes)
    monkeypatch.undo()
    importlib.reload(configuracoes)


def test_padrao_sem_provedor(recarregar):
    c = recarregar()
    assert c.EMAIL_BACKEND == ENVIO_00 and c.EMAIL_HOST == ""
    assert c.DEFAULT_FROM_EMAIL == "nao-responda@localhost"


def test_provedor_fora_de_producao_exige_caixa_de_teste(monkeypatch, recarregar):
    monkeypatch.setenv("EMAIL_HOST", "smtp.exemplo.com")
    monkeypatch.setenv("EMAIL_REMETENTE", "nao-responda@exemplo.com")
    with pytest.raises(ImproperlyConfigured, match="EMAIL_DE_TESTE"):
        recarregar()


def test_provedor_exige_remetente(monkeypatch, recarregar):
    monkeypatch.setenv("EMAIL_HOST", "smtp.exemplo.com")
    monkeypatch.setenv("EMAIL_DE_TESTE", CAIXA)
    with pytest.raises(ImproperlyConfigured, match="EMAIL_REMETENTE"):
        recarregar()


def test_provedor_completo_liga(monkeypatch, recarregar):
    monkeypatch.setenv("EMAIL_HOST", "smtp.exemplo.com")
    monkeypatch.setenv("EMAIL_DE_TESTE", CAIXA)
    monkeypatch.setenv("EMAIL_REMETENTE", "Sistema <nao-responda@exemplo.com>")
    c = recarregar()
    assert c.DEFAULT_FROM_EMAIL == "Sistema <nao-responda@exemplo.com>" and c.EMAIL_USE_TLS


@pytest.mark.parametrize("host,remetente", [
    ("", "nao-responda@exemplo.com"),
    ("smtp.exemplo.com", ""),
    ("smtp.exemplo.com", "webmaster@localhost"),
])
def test_producao_sem_provedor_ou_remetente_de_verdade_nao_liga(monkeypatch, recarregar, host, remetente):
    monkeypatch.setenv("AMBIENTE", "producao")
    monkeypatch.setenv("SECRET_KEY", "k" * 60)
    monkeypatch.setenv("ALLOWED_HOSTS", "exemplo.com")
    monkeypatch.setenv("EMAIL_HOST", host)
    monkeypatch.setenv("EMAIL_REMETENTE", remetente)
    with pytest.raises(ImproperlyConfigured):
        recarregar()


def test_arquivo_env(tmp_path, monkeypatch):
    nomes = ("IV_TESTE_A", "IV_TESTE_B", "IV_TESTE_C", "IV_TESTE_D")
    for n in nomes:
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setenv("IV_TESTE_D", "do-ambiente")
    (tmp_path / ".env").write_text(
        "# comentário\n\nIV_TESTE_A=simples\nIV_TESTE_B = \"com aspas\"\nIV_TESTE_C='x=y'\nIV_TESTE_D=do-arquivo\n",
        encoding="utf-8",
    )
    try:
        configuracoes._carregar_arquivo_env(tmp_path / ".env")
        assert os.environ["IV_TESTE_A"] == "simples"
        assert os.environ["IV_TESTE_B"] == "com aspas"
        assert os.environ["IV_TESTE_C"] == "x=y"
        assert os.environ["IV_TESTE_D"] == "do-ambiente"  # o ambiente vale mais que o arquivo
    finally:
        for n in nomes[:3]:
            os.environ.pop(n, None)


# 3. Checagens.
def test_envio_trocado_nao_liga(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    assert [e.id for e in sec09_email()] == ["SEC.E091"]
    settings.EMAIL_BACKEND = ENVIO_00
    assert sec09_email() == []
    settings.EMAIL_BACKEND = LOCMEM  # caixa de mentira dos testes
    assert sec09_email() == []


def test_producao_sem_email_de_verdade_nao_liga(settings):
    settings.AMBIENTE = "producao"
    settings.EMAIL_HOST = ""
    settings.DEFAULT_FROM_EMAIL = "nao-responda@exemplo.com"
    assert [e.id for e in sec09_email()] == ["SEC.E092"]
    settings.EMAIL_HOST = "smtp.exemplo.com"
    settings.DEFAULT_FROM_EMAIL = "webmaster@localhost"
    assert [e.id for e in sec09_email()] == ["SEC.E092"]
    settings.DEFAULT_FROM_EMAIL = "nao-responda@exemplo.com"
    assert sec09_email() == []
