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
    path("sair-de-todos/", views.SairDeTodos.as_view(), name="sair_de_todos"),
    # Cadastro público (desligado por padrão: responde 404 enquanto o sistema não ligar)
    path("criar-conta/", views.CriarConta.as_view(), name="criar_conta"),
    path("criar-conta/confirmar/<str:codigo>/", views.ConfirmarCadastro.as_view(), name="confirmar_cadastro"),
    path("criar-conta/senha/", views.SenhaDoCadastro.as_view(), name="senha_do_cadastro"),
]
