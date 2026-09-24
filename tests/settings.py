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
    "infra_vibecoding",
    "tests.app_teste",
]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
