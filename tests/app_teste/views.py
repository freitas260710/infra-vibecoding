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


# US 6.2: a regra barra dentro de uma transação (as gravações da tela são desfeitas; o acesso negado fica).
@logado
def negado_em_transacao(request):
    from django.db import transaction

    from infra_vibecoding.dados import exigir

    with transaction.atomic():
        Pedido(dono=request.user, titulo="desfeito").salvar(request.user)
        exigir(request.user, "aprovar", Pedido)
    return HttpResponse("não chega aqui")


# US 6.4: telas para o painel de rastreio (página HTML de verdade, com </body>).
@logado
def rastreio_tela(request):
    from infra_vibecoding.dados import pode

    quantos = Pedido.objects.para(request.user).count()
    pode(request.user, "aprovar", Pedido)
    pode(request.user, "excluir", Pedido)  # sem registro: a regra de teste responde não
    return HttpResponse(f"<html><body><p>{quantos} pedido(s)</p><a href='/rastreio/'>de novo</a></body></html>")


@logado
def rastreio_salvar(request):
    from django.shortcuts import redirect

    Pedido(dono=request.user, titulo=request.POST.get("titulo", "Mesa")).salvar(request.user)
    return redirect("/rastreio/")
