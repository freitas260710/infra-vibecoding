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
