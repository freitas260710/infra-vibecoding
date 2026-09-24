"""Testes das configurações de segurança herdadas do 00 (US 1.5)."""
import importlib
import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ImproperlyConfigured, ValidationError

from infra_vibecoding import configuracoes
from infra_vibecoding.checagens import sec01_configuracoes_de_seguranca

RAIZ = Path(__file__).resolve().parent.parent
CHAVE_BOA = "k" * 60


def ids(erros):
    return sorted({e.id for e in erros})


@pytest.fixture
def recarregar(monkeypatch):
    """Recarrega o módulo de configurações com outras variáveis de ambiente e desfaz no final."""
    yield lambda: importlib.reload(configuracoes)
    monkeypatch.undo()
    importlib.reload(configuracoes)


# 1. Modos dev e produção.
def test_modo_dev_por_padrao(monkeypatch, recarregar):
    monkeypatch.delenv("AMBIENTE", raising=False)
    c = recarregar()
    assert c.AMBIENTE == "dev" and c.DEBUG is True and c.SESSION_COOKIE_SECURE is False


def test_producao_sem_chave_secreta_nao_liga(monkeypatch, recarregar):
    monkeypatch.setenv("AMBIENTE", "producao")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("ALLOWED_HOSTS", "exemplo.com")
    with pytest.raises(ImproperlyConfigured):
        recarregar()


def test_producao_sem_endereco_nao_liga(monkeypatch, recarregar):
    monkeypatch.setenv("AMBIENTE", "producao")
    monkeypatch.setenv("SECRET_KEY", CHAVE_BOA)
    monkeypatch.delenv("ALLOWED_HOSTS", raising=False)
    with pytest.raises(ImproperlyConfigured):
        recarregar()


def test_ambiente_invalido_nao_liga(monkeypatch, recarregar):
    monkeypatch.setenv("AMBIENTE", "homologacao")
    with pytest.raises(ImproperlyConfigured):
        recarregar()


def test_producao_liga_tudo(monkeypatch, recarregar):
    monkeypatch.setenv("AMBIENTE", "producao")
    monkeypatch.setenv("SECRET_KEY", CHAVE_BOA)
    monkeypatch.setenv("ALLOWED_HOSTS", "exemplo.com, www.exemplo.com")
    c = recarregar()
    assert c.DEBUG is False
    assert c.ALLOWED_HOSTS == ["exemplo.com", "www.exemplo.com"]
    assert c.SESSION_COOKIE_SECURE and c.CSRF_COOKIE_SECURE and c.SECURE_SSL_REDIRECT
    assert c.SECURE_HSTS_SECONDS >= 31536000


def test_producao_passa_no_check_deploy_do_django():
    """Roda o 'check --deploy' do próprio Django em modo produção, como um sistema publicado."""
    env = {
        **os.environ,
        "AMBIENTE": "producao",
        "SECRET_KEY": secrets.token_urlsafe(64),
        "ALLOWED_HOSTS": "exemplo.com",
        "DJANGO_SETTINGS_MODULE": "tests.settings",
    }
    r = subprocess.run(
        [sys.executable, "-m", "django", "check", "--deploy", "--fail-level", "WARNING"],
        cwd=RAIZ, env=env, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr


# 2. Senhas.
@pytest.mark.django_db
def test_senha_guardada_com_argon2():
    u = get_user_model().objects.create_user("ana", password="uma-senha-longa-e-boa")
    assert u.password.startswith("argon2")
    assert "uma-senha-longa-e-boa" not in u.password


@pytest.mark.parametrize("senha", ["123456", "curta", "12345678901", "password123"])
def test_senha_fraca_e_recusada(senha):
    with pytest.raises(ValidationError):
        validate_password(senha)


def test_senha_boa_e_aceita():
    validate_password("cavalo-bateria-grampo-2026")


# 3. Cabeçalhos de proteção.
@pytest.mark.django_db
def test_cabecalhos_de_protecao(client):
    r = client.get("/")
    assert r["X-Frame-Options"] == "DENY"
    assert r["X-Content-Type-Options"] == "nosniff"
    assert r["Referrer-Policy"] == "same-origin"
    assert r["Cross-Origin-Opener-Policy"] == "same-origin"


# 4. Checagens: enfraquecer qualquer item faz o sistema não ligar.
def test_projeto_de_teste_passa():
    assert sec01_configuracoes_de_seguranca() == []


def test_sem_importar_as_configuracoes(settings):
    del settings.AMBIENTE
    assert ids(sec01_configuracoes_de_seguranca()) == ["SEC.E010"]


@pytest.mark.parametrize("nome, valor, esperado", [
    ("PASSWORD_HASHERS", ["django.contrib.auth.hashers.MD5PasswordHasher"], "SEC.E011"),
    ("SESSION_COOKIE_HTTPONLY", False, "SEC.E012"),
    ("SESSION_COOKIE_AGE", 60 * 60 * 24 * 365, "SEC.E019"),
    ("AUTH_PASSWORD_VALIDATORS", [], "SEC.E017"),
    ("X_FRAME_OPTIONS", "SAMEORIGIN", "SEC.E016"),
])
def test_enfraquecer_configuracao_e_barrado(settings, nome, valor, esperado):
    setattr(settings, nome, valor)
    assert esperado in ids(sec01_configuracoes_de_seguranca())


@pytest.mark.parametrize("middleware, esperado", [
    ("django.middleware.security.SecurityMiddleware", "SEC.E063"),
    ("django.middleware.csrf.CsrfViewMiddleware", "SEC.E064"),
    ("django.middleware.clickjacking.XFrameOptionsMiddleware", "SEC.E065"),
])
def test_remover_protecao_e_barrado(settings, middleware, esperado):
    settings.MIDDLEWARE = [m for m in settings.MIDDLEWARE if m != middleware]
    assert esperado in ids(sec01_configuracoes_de_seguranca())


def test_producao_enfraquecida_e_barrada(settings):
    settings.AMBIENTE = "producao"
    settings.DEBUG = True
    settings.SECRET_KEY = "dev-inseguro-nao-usar-em-producao"
    settings.ALLOWED_HOSTS = ["*"]
    settings.SESSION_COOKIE_SECURE = False
    settings.SECURE_HSTS_SECONDS = 0
    assert {"SEC.E013", "SEC.E014", "SEC.E015", "SEC.E020"} <= set(ids(sec01_configuracoes_de_seguranca()))


def test_chave_secreta_repetitiva_e_barrada(settings):
    settings.AMBIENTE = "producao"
    settings.DEBUG = False
    settings.SECRET_KEY = "a" * 60
    assert "SEC.E015" in ids(sec01_configuracoes_de_seguranca())
