from django.http import HttpResponse
from django.views import View

from infra_vibecoding.limites import limite
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


# US 3.3: ações do negócio com limite apertado.
@publica
@limite(por_minuto=3)
def exportar(request):
    return HttpResponse("exportado")


@publica
@limite(por_minuto=2)
class Relatorio2View(View):
    def get(self, request):
        return HttpResponse("relatório pesado")


# US 3.5: telas que dão erro de propósito.
@publica
def quebrada(request):
    raise RuntimeError("detalhe técnico que não pode aparecer na tela: senha=abc123")


@publica
def pedido_ruim(request):
    from django.core.exceptions import SuspiciousOperation

    raise SuspiciousOperation("detalhe técnico do pedido ruim")


@logado
def pedido_de_outro(request, pk):
    from django.shortcuts import get_object_or_404

    pedido = get_object_or_404(Pedido.objects.para(request.user), pk=pk)
    return HttpResponse(pedido.titulo)


# US 6.1: grava dentro de um clique (o histórico leva o código do pedido e a pessoa logada).
@logado
def renomear_pedido(request, pk):
    pedido = Pedido.objects.para(request.user).get(pk=pk)
    pedido.titulo = request.GET.get("titulo", "novo")
    pedido.salvar(request.user)
    return HttpResponse("ok")
