"""
Comando limpar_registros do Infra Vibecoding (US 6.2, D60).

Apaga do registro de acessos o que tem mais de um ano. O histórico dos registros (quem mudou o quê) nunca é apagado.
Até a etapa 5 (jobs), rodar uma vez por dia; depois, roda sozinho.

    uv run python manage.py limpar_registros
"""
from django.core.management.base import BaseCommand

from ...acessos import GUARDA_DIAS, limpar_acessos_antigos


class Command(BaseCommand):
    help = "Apaga do registro de acessos o que tem mais de um ano. O histórico dos registros fica para sempre."

    def handle(self, *args, **options):
        total = limpar_acessos_antigos()
        self.stdout.write(f"Registro de acessos: {total} linha(s) com mais de {GUARDA_DIAS} dias apagada(s).")
