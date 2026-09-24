from infra_vibecoding.dados import Politica, politica

from .models import Pedido, Rascunho


@politica(Pedido)
class PoliticaPedido(Politica):
    def escopo(self, usuario, qs):
        return qs.filter(dono=usuario)


@politica(Rascunho)
class PoliticaRascunho(Politica):
    pass
