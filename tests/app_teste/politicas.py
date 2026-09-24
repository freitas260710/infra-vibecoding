from infra_vibecoding.dados import Politica, politica

from .models import AcessoSetor, Documento, ItemPedido, Pedido, Rascunho, Setor


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


@politica(ItemPedido)
class PoliticaItemPedido(Politica):
    def escopo(self, usuario, qs):
        return qs.filter(pedido__dono=usuario)


# US 2.3: regras que consultam outras tabelas com self.consultar(...).

@politica(Setor)
class PoliticaSetor(Politica):
    pass


@politica(AcessoSetor)
class PoliticaAcessoSetor(Politica):
    """Fechada: ninguém lê a tabela de acessos direto. Só as regras consultam."""


@politica(Documento)
class PoliticaDocumento(Politica):
    def escopo(self, usuario, qs):
        # Consulta a tabela de acessos (fechada para o usuário) só para decidir o filtro.
        setores = self.consultar(AcessoSetor).filter(usuario=usuario).values("setor")
        return qs.filter(setor__in=setores)

    def pode(self, usuario, acao, obj=None):
        if acao == "editar" and obj is not None:
            return self.consultar(AcessoSetor).filter(
                usuario=usuario, setor_id=obj.setor_id, pode_editar=True
            ).exists()
        return False

