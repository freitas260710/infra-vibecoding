"""
Configurações de segurança do Infra Vibecoding. Todo sistema herda daqui, com uma linha no settings.py:

    from infra_vibecoding.configuracoes import *  # noqa: F401,F403

Depois dessa linha o sistema só preenche o que é dele: BASE_DIR, ROOT_URLCONF, os próprios apps
(INSTALLED_APPS = INSTALLED_APPS + ["meu_app"]), a tabela de usuário (AUTH_USER_MODEL, que herda de
infra_vibecoding.usuarios.UsuarioSeguro), banco de dados e textos. Enfraquecer qualquer item de
segurança faz o sistema não ligar (checagens SEC.E01x e SEC.E06x).

Modos (variável de ambiente AMBIENTE):
- dev       (padrão): no Mac do desenvolvedor. HTTPS relaxado e página de erro detalhada.
- producao: sistema publicado. Exige SECRET_KEY, ALLOWED_HOSTS e o provedor de e-mail nas variáveis de ambiente.

Variáveis de ambiente podem vir de um arquivo .env na pasta do sistema (fora do Git: o .gitignore dos sistemas
já ignora). Uma variável já definida no ambiente vale mais que a do arquivo. Segredos nunca no código.
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


def _carregar_arquivo_env(caminho=None):
    """Lê o arquivo .env da pasta de onde o sistema foi ligado (linhas NOME=valor). Não sobrescreve o ambiente."""
    arquivo = Path(caminho) if caminho else Path.cwd() / ".env"
    if not arquivo.is_file():
        return
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        nome, valor = linha.split("=", 1)
        nome, valor = nome.strip(), valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        os.environ.setdefault(nome, valor)


_carregar_arquivo_env()

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
    "infra_vibecoding.limites.LimiteDePedidos",  # limite de pedidos em tudo (US 3.3)
    "infra_vibecoding.login.dois_fatores.ExigeDoisFatores",  # verificação em duas etapas (US 3.4)
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
# Cadastro público (US 3.2): desligado. Para ligar: CADASTRO_PUBLICO = "app.modulo.ClasseDeCadastro"
# (subclasse de infra_vibecoding.login.cadastro.Cadastro, com termos_url e privacidade_url; SEC.E084).
CADASTRO_PUBLICO = None
# Verificação em duas etapas (US 3.4): quem entra na tela de banco é obrigado em produção (regra do 00). O sistema
# obriga mais gente apontando para uma função sua que recebe o usuário e responde True/False.
# Ex.: DOIS_FATORES_OBRIGATORIO = "nucleo.regras.exige_dois_fatores"
DOIS_FATORES_OBRIGATORIO = None

# E-mails (US 3.1b, D45). O 00 não tem conta em provedor nenhum: cada sistema configura a própria conta nas
# variáveis de ambiente (ou no .env). Qualquer provedor que aceite SMTP (Brevo, Mailjet, Resend...).
#   EMAIL_HOST, EMAIL_PORT (587), EMAIL_HOST_USER, EMAIL_HOST_PASSWORD: dados SMTP do provedor
#   EMAIL_REMETENTE: quem envia, ex.: Mindor <nao-responda@mindtopo.com.br>
#   EMAIL_DE_TESTE: caixa de teste. Fora de produção, TODO e-mail vai só para ela (desvio, D39)
# Sem provedor (fora de produção), os e-mails aparecem no terminal. Em produção, sem provedor o sistema não liga.
EMAIL_BACKEND = "infra_vibecoding.email.EnvioComDesvio"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = True
EMAIL_TIMEOUT = 15
EMAIL_REMETENTE = os.environ.get("EMAIL_REMETENTE", "")
EMAIL_DE_TESTE = os.environ.get("EMAIL_DE_TESTE", "")
DEFAULT_FROM_EMAIL = SERVER_EMAIL = EMAIL_REMETENTE or "nao-responda@localhost"

if PRODUCAO:
    if not EMAIL_HOST:
        raise ImproperlyConfigured("Em produção, o provedor de e-mail é obrigatório (variável EMAIL_HOST e dados SMTP).")
    if not EMAIL_REMETENTE or "localhost" in EMAIL_REMETENTE.lower():
        raise ImproperlyConfigured(
            "Em produção, EMAIL_REMETENTE é obrigatório e precisa ser um endereço de verdade do sistema "
            "(ex.: Mindor <nao-responda@mindtopo.com.br>)."
        )
elif EMAIL_HOST:
    if not EMAIL_DE_TESTE:
        raise ImproperlyConfigured(
            "Provedor de e-mail ligado fora de produção sem EMAIL_DE_TESTE: todo e-mail precisa ser desviado para "
            "uma caixa de teste (D39). Preencha EMAIL_DE_TESTE."
        )
    if not EMAIL_REMETENTE:
        raise ImproperlyConfigured("Provedor de e-mail ligado sem EMAIL_REMETENTE (o remetente confirmado no provedor).")

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

# Limite de pedidos (US 3.3): máximos do 00. O sistema pode apertar (valores menores), nunca afrouxar (SEC.E067).
LIMITE_PEDIDOS_POR_ENDERECO = 120  # por minuto, visitante
LIMITE_PEDIDOS_POR_USUARIO = 240   # por minuto, usuário logado

# Contagem dos limites: no Mac, na memória; em produção, no banco (vale para todas as cópias do sistema).
# A tabela do cache é criada na publicação com "manage.py createcachetable" (etapa 8).
if PRODUCAO:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "infra_vibecoding_cache"}}

# Registro das ações sensíveis (leitura e gravação como sistema, acessos negados).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "infra_vibecoding.auditoria": {"handlers": ["console"], "level": "INFO", "propagate": True},
    },
}
