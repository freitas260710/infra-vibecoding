"""Telas de login do Infra Vibecoding (US 3.1). Cada uma declara quem pode abrir, como qualquer tela."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import views as auth_views
from django.shortcuts import resolve_url
from django.utils.http import urlsafe_base64_decode
from django.views.generic import FormView

from ..telas import logado, publica
from ..usuarios import normalizar_email
from . import limites
from .convites import enviar_aviso_de_senha, enviar_link_de_senha, log
from .formularios import FormularioDefinirSenha, FormularioEntrar, FormularioPedirLink, FormularioTrocarSenha
from .links import LINK_CONVITE, LINK_REDEFINIR

PASTA = "infra_vibecoding/login/"


def _depois_do_login():
    return resolve_url(getattr(settings, "LOGIN_REDIRECT_URL", "/") or "/")


@publica
class Entrar(auth_views.LoginView):
    template_name = PASTA + "entrar.html"
    authentication_form = FormularioEntrar
    redirect_authenticated_user = True


@logado
class Sair(auth_views.LogoutView):
    def get_default_redirect_url(self):
        return resolve_url(getattr(settings, "LOGOUT_REDIRECT_URL", None) or "entrar")


class _PedirLink(FormView):
    """Pede o link por e-mail. Resposta sempre igual, exista o e-mail ou não (não revela quem tem acesso)."""

    form_class = FormularioPedirLink

    def form_valid(self, form):
        email = normalizar_email(form.cleaned_data["email"])
        dentro = limites.dentro_do_limite("endereco", limites.endereco_de(self.request), *limites.POR_ENDERECO)
        dentro = limites.dentro_do_limite("email", email, *limites.POR_EMAIL) and dentro
        if not dentro:
            log.warning("login: limite de pedidos de link atingido (e-mail %s, endereço %s)",
                        email, limites.endereco_de(self.request))
        else:
            # Leitura interna do 00, só pelo e-mail exato, como o próprio login faz.
            usuario = get_user_model()._base_manager.filter(email=email).first()
            if usuario is not None:
                enviar_link_de_senha(self.request, usuario)
        return self.render_to_response(self.get_context_data(form=None, enviado=True))


@publica
class PrimeiroAcesso(_PedirLink):
    template_name = PASTA + "primeiro_acesso.html"


@publica
class EsqueciASenha(_PedirLink):
    template_name = PASTA + "esqueci_a_senha.html"


class _DefinirSenha(auth_views.PasswordResetConfirmView):
    """Abre o link do e-mail e define a senha. Depois de definir, a pessoa já entra."""

    form_class = FormularioDefinirSenha
    template_name = PASTA + "definir_senha.html"
    reset_url_token = "definir"
    post_reset_login = True
    post_reset_login_backend = "infra_vibecoding.autenticacao.BackendSeguro"

    def get_user(self, uidb64):
        # Leitura interna do 00 pela chave do link. O código do link é conferido logo depois.
        modelo = get_user_model()
        try:
            pk = modelo._meta.pk.to_python(urlsafe_base64_decode(uidb64).decode())
            return modelo._base_manager.filter(pk=pk).first()
        except Exception:
            return None

    def form_valid(self, form):
        primeira_vez = not self.user.has_usable_password()
        resposta = super().form_valid(form)
        enviar_aviso_de_senha(self.request, self.user, primeira_vez)
        messages.success(self.request, "Senha definida. Você já está dentro.")
        return resposta

    def get_success_url(self):
        return _depois_do_login()

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["tipo"] = self.token_generator.tipo
        return contexto


@publica
class DefinirSenhaConvite(_DefinirSenha):
    token_generator = LINK_CONVITE


@publica
class DefinirSenhaRedefinir(_DefinirSenha):
    token_generator = LINK_REDEFINIR


@logado
class TrocarSenha(auth_views.PasswordChangeView):
    form_class = FormularioTrocarSenha
    template_name = PASTA + "trocar_senha.html"

    def form_valid(self, form):
        resposta = super().form_valid(form)
        enviar_aviso_de_senha(self.request, self.request.user, primeira_vez=False)
        messages.success(self.request, "Senha trocada.")
        return resposta

    def get_success_url(self):
        return _depois_do_login()
