from django.http import HttpResponse
from django.views import View

from infra_vibecoding.telas import exige, logado, publica

from .models import Pedido


@publica
def inicio(request):
    return HttpResponse("página inicial")


@logado
def painel(request):
    return HttpResponse(f"painel de {request.user.get_username()}")


@exige("criar", Pedido)
def novo_pedido(request):
    return HttpResponse("formulário de novo pedido")


@exige("aprovar", Pedido)
def aprovacoes(request):
    return HttpResponse("fila de aprovação")


@publica
class SobreView(View):
    def get(self, request):
        return HttpResponse("sobre")


@exige("aprovar", Pedido)
class RelatorioView(View):
    def get(self, request):
        return HttpResponse("relatório de aprovações")


def esquecida(request):
    """Tela sem declaração: só aparece no urls_sem_declaracao.py dos testes."""
    return HttpResponse("aberta?")
