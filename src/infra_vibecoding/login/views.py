"""Telas de login do Infra Vibecoding (US 3.1). Cada uma declara quem pode abrir, como qualquer tela."""
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth import views as auth_views
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import redirect, render, resolve_url
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.http import urlsafe_base64_decode
from django.views import View
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST
from django.views.generic import FormView

from ..telas import logado, publica
from ..usuarios import normalizar_email
from . import limites
from .cadastro import cadastro_do_sistema, gerar_codigo, ler_codigo
from .convites import _enviar, enviar_aviso_de_senha, enviar_link_de_senha, log
from .formularios import (
    FormularioDefinirSenha,
    FormularioEntrar,
    FormularioPedirLink,
    FormularioSenhaDoCadastro,
    FormularioTrocarSenha,
    formulario_de_cadastro,
)
from .links import LINK_CONVITE, LINK_REDEFINIR
from .sessoes import desconectar

PASTA = "infra_vibecoding/login/"
BACKEND = "infra_vibecoding.autenticacao.BackendSeguro"

# Tela de entrar (US 3.2, D48)
MANTER_CONECTADO = 30 * 24 * 60 * 60  # limite fixo do 00: 30 dias
COOKIE_EMAIL = "iv_email_lembrado"
_SAL_EMAIL = "infra_vibecoding.login.lembrar_email"
_UM_ANO = 365 * 24 * 60 * 60
_SESSAO_CADASTRO = "infra_vibecoding_cadastro"


def _depois_do_login():
    return resolve_url(getattr(settings, "LOGIN_REDIRECT_URL", "/") or "/")


@publica
class Entrar(auth_views.LoginView):
    template_name = PASTA + "entrar.html"
    authentication_form = FormularioEntrar
    redirect_authenticated_user = True

    def get_initial(self):
        email = self.request.get_signed_cookie(COOKIE_EMAIL, default="", salt=_SAL_EMAIL)
        return {"username": email, "lembrar_email": True} if email else {}

    def form_valid(self, form):
        resposta = super().form_valid(form)
        # Manter conectado: até 30 dias neste navegador. Sem marcar: até fechar o navegador (no máximo 12 horas).
        self.request.session.set_expiry(MANTER_CONECTADO if form.cleaned_data.get("manter_conectado") else 0)
        # Lembrar e-mail: só o e-mail, em cookie assinado que o JavaScript não lê. Nunca a senha.
        if form.cleaned_data.get("lembrar_email"):
            resposta.set_signed_cookie(
                COOKIE_EMAIL, form.get_user().email, salt=_SAL_EMAIL, max_age=_UM_ANO,
                httponly=True, secure=settings.SESSION_COOKIE_SECURE, samesite="Lax",
            )
        else:
            resposta.delete_cookie(COOKIE_EMAIL, samesite="Lax")
        return resposta

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["cadastro_publico"] = bool(getattr(settings, "CADASTRO_PUBLICO", None))
        return contexto


@logado
class Sair(auth_views.LogoutView):
    def get_default_redirect_url(self):
        return resolve_url(getattr(settings, "LOGOUT_REDIRECT_URL", None) or "entrar")


def _dentro_dos_limites(request, email):
    dentro = limites.dentro_do_limite("endereco", limites.endereco_de(request), *limites.POR_ENDERECO)
    dentro = limites.dentro_do_limite("email", email, *limites.POR_EMAIL) and dentro
    if not dentro:
        log.warning("login: limite de pedidos atingido (e-mail %s, endereço %s)", email, limites.endereco_de(request))
    return dentro


class _PedirLink(FormView):
    """Pede o link por e-mail. Resposta sempre igual, exista o e-mail ou não (não revela quem tem acesso)."""

    form_class = FormularioPedirLink

    def form_valid(self, form):
        email = normalizar_email(form.cleaned_data["email"])
        if _dentro_dos_limites(self.request, email):
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


@logado
@method_decorator(require_POST, name="dispatch")
class SairDeTodos(View):
    """Sair de todos os meus aparelhos: derruba as outras sessões da pessoa. Esta continua."""

    def post(self, request):
        desconectar(request.user, [request.user], request)
        messages.success(request, "Você saiu de todos os outros aparelhos. Este continua conectado.")
        return redirect("trocar_senha")


# Cadastro público (US 3.2, D47)

class _ComCadastro:
    def dispatch(self, request, *args, **kwargs):
        self.cadastro = cadastro_do_sistema()
        if self.cadastro is None:
            raise Http404("Cadastro público desligado neste sistema.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update(termos_url=self.cadastro.termos_url, privacidade_url=self.cadastro.privacidade_url)
        return contexto


@publica
class CriarConta(_ComCadastro, FormView):
    template_name = PASTA + "criar_conta.html"

    def get_form_class(self):
        return formulario_de_cadastro(self.cadastro)

    def form_valid(self, form):
        email = normalizar_email(form.cleaned_data["email"])
        if form.cleaned_data.get("site"):
            log.warning("login: cadastro público recusado pela armadilha contra robôs (endereço %s)",
                        limites.endereco_de(self.request))
        elif _dentro_dos_limites(self.request, email):
            existente = get_user_model()._base_manager.filter(email=email).first()
            if existente is not None:
                link = self.request.build_absolute_uri(reverse("esqueci_a_senha"))
                _enviar(self.request, existente, "conta_existente", {"link": link})
            else:
                dados = {nome: self.request.POST.get(nome, "") for nome in self.cadastro.campos}
                codigo = gerar_codigo(email, dados, timezone.now().isoformat())
                link = self.request.build_absolute_uri(reverse("confirmar_cadastro", args=[codigo]))
                _enviar(self.request, get_user_model()(email=email, nome=dados.get("nome", "")), "cadastro",
                        {"link": link})
                log.info("login: link de cadastro público enviado para %s", email)
        return self.render_to_response(self.get_context_data(form=None, enviado=True))


@publica
class ConfirmarCadastro(_ComCadastro, View):
    """Abre o link do e-mail. Guarda o código na sessão e segue para a senha (o código não fica no endereço)."""

    def get(self, request, codigo):
        if ler_codigo(codigo) is None:
            return render(request, PASTA + "cadastro_senha.html", {"link_invalido": True}, status=200)
        request.session[_SESSAO_CADASTRO] = codigo
        return redirect("senha_do_cadastro")


@publica
@method_decorator(sensitive_post_parameters(), name="dispatch")
class SenhaDoCadastro(_ComCadastro, FormView):
    """Define a senha. Só aqui a conta nasce: e-mail confirmado, aceite registrado e o encaixe do sistema."""

    template_name = PASTA + "cadastro_senha.html"
    form_class = FormularioSenhaDoCadastro

    def dispatch(self, request, *args, **kwargs):
        codigo = request.session.get(_SESSAO_CADASTRO)
        self.conteudo = ler_codigo(codigo) if codigo else None
        if self.conteudo is None and cadastro_do_sistema() is not None:
            return render(request, PASTA + "cadastro_senha.html", {"link_invalido": True})
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "email": self.conteudo["email"]}

    def _falhou(self, motivo):
        self.request.session.pop(_SESSAO_CADASTRO, None)
        return render(self.request, PASTA + "cadastro_senha.html", {"nao_concluido": motivo})

    def form_valid(self, form):
        email = self.conteudo["email"]
        modelo = get_user_model()
        if modelo._base_manager.filter(email=email).exists():
            return self._falhou("Este e-mail já tem uma conta. Use Entrar ou Esqueci a senha.")
        conferencia = formulario_de_cadastro(self.cadastro)(
            data={"email": email, **self.conteudo["dados"], "aceite": "on"}
        )
        if not conferencia.is_valid():
            erros = "; ".join(e for lista in conferencia.errors.values() for e in lista)
            return self._falhou(f"Não foi possível concluir o cadastro: {erros}")
        extras = {nome: conferencia.cleaned_data.get(nome) for nome in self.cadastro.campos}
        try:
            with transaction.atomic():
                usuario = modelo(email=email)
                usuario.set_password(form.cleaned_data["new_password1"])
                usuario.email_confirmado_em = timezone.now()
                usuario.termos_aceitos_em = datetime.fromisoformat(self.conteudo["termos"])
                usuario.salvar_como_sistema(self.cadastro.motivo(usuario))
                self.cadastro.ao_confirmar(usuario, extras, self.request)
        except IntegrityError:
            return self._falhou("Este e-mail já tem uma conta. Use Entrar ou Esqueci a senha.")
        self.request.session.pop(_SESSAO_CADASTRO, None)
        login(self.request, usuario, backend=BACKEND)
        self.request.session.set_expiry(0)
        enviar_aviso_de_senha(self.request, usuario, primeira_vez=True)
        messages.success(self.request, "Conta criada. Você já está dentro.")
        return redirect(_depois_do_login())
