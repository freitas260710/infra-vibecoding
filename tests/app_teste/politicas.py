from infra_vibecoding.dados import Politica, politica

from .models import AcessoSetor, Anexo, Documento, ItemPedido, Pedido, Rascunho, Setor, UsuarioTeste


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


# US 2.4: tabela de usuário. Cada um vê e edita só a si mesmo.

@politica(UsuarioTeste)
class PoliticaUsuario(Politica):
    def escopo(self, usuario, qs):
        return qs.filter(pk=usuario.pk)

    def pode(self, usuario, acao, obj=None):
        if acao == "criar":  # US 3.1: só administrador abre acesso para colegas
            return usuario.is_staff
        if acao == "desconectar":  # US 3.2: só administrador derruba sessões de outra pessoa
            return usuario.is_staff
        return acao == "editar" and obj is not None and obj.pk == usuario.pk


@politica(Anexo)
class PoliticaAnexo(Politica):
    """Anexo segue o pedido: quem é dono do pedido vê, envia e troca os anexos dele."""

    def escopo(self, usuario, qs):
        return qs.filter(pedido__dono=usuario)

    def pode(self, usuario, acao, obj=None):
        if acao in ("criar", "editar", "excluir"):
            return obj is None or obj.pedido.dono_id == usuario.id
        return False

