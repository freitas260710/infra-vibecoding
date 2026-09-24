from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class InfraVibecodingConfig(AppConfig):
    name = "infra_vibecoding"
    verbose_name = "Infra Vibecoding"

    def ready(self):
        from . import checagens  # noqa: F401  (registra as checagens)

        # Carrega o politicas.py de cada app do sistema.
        autodiscover_modules("politicas")
