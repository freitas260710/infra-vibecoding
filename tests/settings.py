"""Configuração mínima de Django usada só nos testes do Infra Vibecoding."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SECRET_KEY = "somente-para-testes"
DEBUG = False
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "infra_vibecoding",
    "tests.app_teste",
]
ROOT_URLCONF = "tests.urls"
LOGIN_URL = "/entrar/"
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
