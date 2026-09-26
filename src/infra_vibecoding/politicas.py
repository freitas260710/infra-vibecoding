"""Políticas das tabelas do próprio 00: fechadas. Só as funções do 00 leem e gravam."""
from .dados import Politica, politica
from .models import Acesso, ArquivoGuardado, Historico, LinkDeCompartilhamento


@politica(ArquivoGuardado)
class PoliticaArquivoGuardado(Politica):
    """Ninguém lista arquivos direto. Quem baixa é decidido pela regra do registro dono do arquivo."""


@politica(LinkDeCompartilhamento)
class PoliticaLinkDeCompartilhamento(Politica):
    """Ninguém lista links direto. Quem cria e cancela é quem a política do registro libera ("compartilhar")."""


@politica(Historico)
class PoliticaHistorico(Politica):
    """Ninguém lista o histórico direto: cada um vê o histórico dos registros que vê (historico_de)."""


@politica(Acesso)
class PoliticaAcesso(Politica):
    """Ninguém lista os acessos direto: só a tela de Registros, para superusuário."""
