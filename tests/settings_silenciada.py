"""Configuração de teste que tenta silenciar uma checagem do 00 (não pode ligar)."""
from tests.settings import *  # noqa: F401,F403

SILENCED_SYSTEM_CHECKS = ["SEC.E022"]
