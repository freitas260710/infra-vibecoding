"""Políticas das tabelas do próprio 00: fechadas. Só as funções do 00 leem e gravam."""
from .dados import Politica, politica
from .models import ArquivoGuardado


@politica(ArquivoGuardado)
class PoliticaArquivoGuardado(Politica):
    """Ninguém lista arquivos direto. Quem baixa é decidido pela regra do registro dono do arquivo."""
