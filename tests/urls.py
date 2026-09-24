from django.urls import path

from tests.app_teste import views

urlpatterns = [
    path("", views.inicio),
    path("painel/", views.painel),
    path("pedidos/novo/", views.novo_pedido),
    path("aprovacoes/", views.aprovacoes),
    path("sobre/", views.SobreView.as_view()),
    path("relatorio/", views.RelatorioView.as_view()),
]
