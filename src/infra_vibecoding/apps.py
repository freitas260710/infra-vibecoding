from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class InfraVibecodingConfig(AppConfig):
    name = "infra_vibecoding"
    verbose_name = "Infra Vibecoding"

    def ready(self):
        from django.conf import settings

        from . import checagens  # noqa: F401  (registra as checagens)

        # Ninguém silencia as checagens do 00 (US 2.1).
        checagens.conferir_checagens_silenciadas(getattr(settings, "SILENCED_SYSTEM_CHECKS", []))

        # Carrega o politicas.py de cada app do sistema.
        autodiscover_modules("politicas")

        # O CLAUDE.md do sistema carrega o manual da IA do 00 instalado: o próprio 00 garante a linha (US 3.2b).
        try:
            checagens.garantir_manual_no_claude_md()
        except OSError:
            pass  # pasta só de leitura: a checagem SEC.E101 avisa

        # "Alterar senha" do topo da tela de banco usa a tela de trocar a senha do 00 (0.2.1).
        from django.apps import apps

        if apps.is_installed("django.contrib.admin"):
            from django.contrib import admin

            from .admin import trocar_propria_senha

            admin.site.password_change = trocar_propria_senha
