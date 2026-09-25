"""Configuração de Django usada nos testes do Infra Vibecoding. Herda as configurações de segurança do 00."""
from pathlib import Path

from infra_vibecoding.configuracoes import *  # noqa: F401,F403
from infra_vibecoding.configuracoes import INSTALLED_APPS

BASE_DIR = Path(__file__).resolve().parent
INSTALLED_APPS = INSTALLED_APPS + ["tests.app_teste"]
ROOT_URLCONF = "tests.urls"
LOGIN_URL = "/entrar/"
AUTH_USER_MODEL = "app_teste.UsuarioTeste"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
