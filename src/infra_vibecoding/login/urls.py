"""Endereços das telas de login. O sistema inclui com: path("", include("infra_vibecoding.login.urls"))."""
from django.urls import path

from ..erros import ver_pagina_de_erro
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
    # Verificação em duas etapas (US 3.4)
    path("entrar/codigo/", views.VerificarCodigo.as_view(), name="verificar_codigo"),
    path("entrar/codigo/reenviar/", views.ReenviarCodigo.as_view(), name="reenviar_codigo"),
    path("dois-fatores/", views.MeusDoisFatores.as_view(), name="dois_fatores"),
    path("dois-fatores/app/", views.AtivarApp.as_view(), name="ativar_app"),
    path("dois-fatores/email/", views.AtivarEmail.as_view(), name="ativar_email"),
    path("dois-fatores/novos-codigos/", views.NovosCodigos.as_view(), name="novos_codigos"),
    path("dois-fatores/desligar/", views.DesligarDoisFatores.as_view(), name="desligar_dois_fatores"),
    # Ver as páginas de erro como o usuário vê (só no computador do desenvolvedor, US 3.5)
    path("erros/ver/<str:tipo>/", ver_pagina_de_erro, name="ver_pagina_de_erro"),
    # Cadastro público (desligado por padrão: responde 404 enquanto o sistema não ligar)
    path("criar-conta/", views.CriarConta.as_view(), name="criar_conta"),
    path("criar-conta/confirmar/<str:codigo>/", views.ConfirmarCadastro.as_view(), name="confirmar_cadastro"),
    path("criar-conta/senha/", views.SenhaDoCadastro.as_view(), name="senha_do_cadastro"),
]
