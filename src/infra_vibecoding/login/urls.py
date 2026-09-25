"""Endereços das telas de login. O sistema inclui com: path("", include("infra_vibecoding.login.urls"))."""
from django.urls import path

from . import views

urlpatterns = [
    path("entrar/", views.Entrar.as_view(), name="entrar"),
    path("sair/", views.Sair.as_view(), name="sair"),
    path("primeiro-acesso/", views.PrimeiroAcesso.as_view(), name="primeiro_acesso"),
    path("primeiro-acesso/<uidb64>/<token>/", views.DefinirSenhaConvite.as_view(), name="definir_senha_convite"),
    path("esqueci-a-senha/", views.EsqueciASenha.as_view(), name="esqueci_a_senha"),
    path("redefinir-senha/<uidb64>/<token>/", views.DefinirSenhaRedefinir.as_view(),
         name="definir_senha_redefinir"),
    path("trocar-senha/", views.TrocarSenha.as_view(), name="trocar_senha"),
]
