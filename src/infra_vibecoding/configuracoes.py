"""
Configurações de segurança do Infra Vibecoding. Todo sistema herda daqui, com uma linha no settings.py:

    from infra_vibecoding.configuracoes import *  # noqa: F401,F403

Depois dessa linha o sistema só preenche o que é dele: BASE_DIR, ROOT_URLCONF, os próprios apps
(INSTALLED_APPS = INSTALLED_APPS + ["meu_app"]), a tabela de usuário (AUTH_USER_MODEL, que herda de
infra_vibecoding.usuarios.UsuarioSeguro), banco de dados e textos. Enfraquecer qualquer item de
segurança faz o sistema não ligar (checagens SEC.E01x e SEC.E06x).

Modos (variável de ambiente AMBIENTE):
- dev       (padrão): no Mac do desenvolvedor. HTTPS relaxado e página de erro detalhada.
- producao: sistema publicado. Exige SECRET_KEY e ALLOWED_HOSTS nas variáveis de ambiente.
"""
import os

from django.core.exceptions import ImproperlyConfigured

AMBIENTE = os.environ.get("AMBIENTE", "dev")
if AMBIENTE not in ("dev", "producao"):
    raise ImproperlyConfigured(f"AMBIENTE deve ser 'dev' ou 'producao', não '{AMBIENTE}'.")

PRODUCAO = AMBIENTE == "producao"

# Modo de desenvolvimento (página de erro com detalhes internos): só fora de produção.
DEBUG = not PRODUCAO

# Chave secreta e endereços: em produção vêm obrigatoriamente das variáveis de ambiente.
if PRODUCAO:
    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    if len(SECRET_KEY) < 50:
        raise ImproperlyConfigured(
            "Em produção, a variável de ambiente SECRET_KEY é obrigatória e precisa ter 50 caracteres ou mais."
        )
    ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]
    if not ALLOWED_HOSTS:
        raise ImproperlyConfigured("Em produção, a variável de ambiente ALLOWED_HOSTS é obrigatória.")
else:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-inseguro-nao-usar-em-producao")
    ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", "testserver"]

# O 00 vem primeiro: os comandos de terminal dele têm prioridade (ex.: changepassword do 00, 0.2.1).
INSTALLED_APPS = [
    "infra_vibecoding",
    "django.contrib.admin",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
STATIC_URL = "static/"

# Login: pelo backend do 00, que carrega o usuário sem abrir a tabela (a tabela de usuário tem trava).
AUTHENTICATION_BACKENDS = ["infra_vibecoding.autenticacao.BackendSeguro"]

# Telas de login do 00 (US 3.1). O sistema inclui: path("", include("infra_vibecoding.login.urls")).
LOGIN_URL = "entrar"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "entrar"
NOME_DO_SISTEMA = ""  # aparece no assunto e no texto dos e-mails; o sistema preenche

# E-mails: no Mac aparecem no terminal (nenhum e-mail sai de verdade). O provedor de e-mail do dev online e de
# produção vem numa próxima versão do 00.
if not PRODUCAO:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Senhas: guardadas com Argon2 (o método mais forte disponível), nunca a senha em si.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Cookie de login: JavaScript não lê, outros sites não usam, só viaja em HTTPS em produção.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = PRODUCAO
SESSION_COOKIE_AGE = 60 * 60 * 12  # 12 horas
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = PRODUCAO

# HTTPS obrigatório em produção (atrás do proxy do servidor, que informa o protocolo original).
SECURE_SSL_REDIRECT = PRODUCAO
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if PRODUCAO else None
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365 if PRODUCAO else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = PRODUCAO
SECURE_HSTS_PRELOAD = PRODUCAO

# Cabeçalhos de proteção do navegador.
X_FRAME_OPTIONS = "DENY"  # não pode ser aberto dentro de outro site
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# Registro das ações sensíveis (leitura e gravação como sistema, acessos negados).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "infra_vibecoding.auditoria": {"handlers": ["console"], "level": "INFO", "propagate": True},
    },
}
