"""URLs de teste de um sistema que tenta trocar as páginas de erro do 00 (SEC.E111)."""
from tests.urls import urlpatterns  # noqa: F401

handler404 = "tests.app_teste.views.inicio"
