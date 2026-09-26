from django.contrib import admin
from django.urls import include, path

from tests.app_teste import views

urlpatterns = [
    path("gestao-interna/", admin.site.urls),
    path("", include("infra_vibecoding.login.urls")),
    path("", views.inicio),
    path("painel/", views.painel),
    path("pedidos/novo/", views.novo_pedido),
    path("aprovacoes/", views.aprovacoes),
    path("sobre/", views.SobreView.as_view()),
    path("relatorio/", views.RelatorioView.as_view()),
    path("exportar/", views.exportar),
    path("relatorio-pesado/", views.Relatorio2View.as_view()),
    path("quebrada/", views.quebrada),
    path("pedido-ruim/", views.pedido_ruim),
    path("pedidos/<int:pk>/", views.pedido_de_outro),
]
