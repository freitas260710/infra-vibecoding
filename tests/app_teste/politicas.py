from infra_vibecoding.dados import Politica, politica

from .models import Pedido, Rascunho


@politica(Pedido)
class PoliticaPedido(Politica):
    def escopo(self, usuario, qs):
        return qs.filter(dono=usuario)

    def pode(self, usuario, acao, obj=None):
        if acao == "criar":
            # Botão "Novo" (sem registro): qualquer usuário logado.
            # Registro concreto: só criando para si mesmo.
            return obj is None or obj.dono_id == usuario.id
        if acao in ("editar", "excluir"):
            return obj is not None and obj.dono_id == usuario.id
        if acao == "aprovar":
            return usuario.is_staff
        return False


@politica(Rascunho)
class PoliticaRascunho(Politica):
    pass
