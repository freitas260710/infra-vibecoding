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

        # Páginas de erro em português, sem nada técnico (US 3.5).
        from .erros import ligar_paginas_de_erro

        ligar_paginas_de_erro()

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
            # O login da tela de banco é o do 00 (senha, bloqueio e verificação em duas etapas, US 3.4).
            from .admin import entrar_pela_tela_do_00

            admin.site.login = entrar_pela_tela_do_00
