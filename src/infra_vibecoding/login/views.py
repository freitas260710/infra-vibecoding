"""Telas de login do Infra Vibecoding (US 3.1). Cada uma declara quem pode abrir, como qualquer tela."""
import time
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
from django.views.generic import FormView, TemplateView

from ..telas import logado, publica
from ..usuarios import normalizar_email
from . import dois_fatores, limites
from .cadastro import cadastro_do_sistema, gerar_codigo, ler_codigo
from .convites import _enviar, enviar_aviso_de_senha, enviar_link_de_senha, log
from .formularios import (
    FormularioDefinirSenha,
    FormularioEntrar,
    FormularioCodigo,
    FormularioPedirLink,
    FormularioSenhaAtual,
    FormularioSenhaDoCadastro,
    FormularioSenhaECodigo,
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


def _concluir_login(request, usuario, manter, lembrar, destino):
    """Depois do login: tempo da sessão e o cookie do e-mail lembrado."""
    # Manter conectado: até 30 dias neste navegador. Sem marcar: até fechar o navegador (no máximo 12 horas).
    request.session.set_expiry(MANTER_CONECTADO if manter else 0)
    resposta = redirect(destino)
    # Lembrar e-mail: só o e-mail, em cookie assinado que o JavaScript não lê. Nunca a senha.
    if lembrar:
        resposta.set_signed_cookie(
            COOKIE_EMAIL, usuario.email, salt=_SAL_EMAIL, max_age=_UM_ANO,
            httponly=True, secure=settings.SESSION_COOKIE_SECURE, samesite="Lax",
        )
    elif lembrar is not None:
        resposta.delete_cookie(COOKIE_EMAIL, samesite="Lax")
    return resposta


def _iniciar_verificacao(request, usuario, manter, lembrar, destino):
    """Guarda na sessão que a senha estava certa e manda o código por e-mail, se for o método da pessoa."""
    pendente = {
        "pk": str(usuario.pk), "manter": manter, "lembrar": lembrar, "destino": destino,
        "vence": time.time() + dois_fatores.VALIDADE_PENDENTE, "erros": 0,
    }
    if usuario.dois_fatores == dois_fatores.EMAIL:
        if dois_fatores.pode_reenviar(usuario):
            pendente["email"] = dois_fatores.novo_codigo_por_email(request, usuario)
        else:
            log.warning("2fa: limite de envio de código atingido para %s", usuario.email)
            messages.error(request, "Muitos envios de código seguidos. Espere alguns minutos e entre de novo.")
    request.session[dois_fatores.SESSAO_PENDENTE] = pendente


@publica
class Entrar(auth_views.LoginView):
    template_name = PASTA + "entrar.html"
    authentication_form = FormularioEntrar
    redirect_authenticated_user = True

    def get_initial(self):
        email = self.request.get_signed_cookie(COOKIE_EMAIL, default="", salt=_SAL_EMAIL)
        return {"username": email, "lembrar_email": True} if email else {}

    def form_valid(self, form):
        usuario = form.get_user()
        manter = bool(form.cleaned_data.get("manter_conectado"))
        lembrar = bool(form.cleaned_data.get("lembrar_email"))
        destino = self.get_success_url()
        if usuario.dois_fatores:
            # Senha certa, mas ainda não entra: falta o código da verificação em duas etapas (US 3.4).
            _iniciar_verificacao(self.request, usuario, manter, lembrar, destino)
            return redirect("verificar_codigo")
        login(self.request, usuario, backend=BACKEND)
        return _concluir_login(self.request, usuario, manter, lembrar, destino)

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
        if self.user.dois_fatores:
            # Esqueci a senha não pula a verificação em duas etapas (US 3.4): depois da senha, o código.
            self.post_reset_login = False
            super().form_valid(form)
            enviar_aviso_de_senha(self.request, self.user, primeira_vez)
            _iniciar_verificacao(self.request, self.user, False, None, _depois_do_login())
            messages.success(self.request, "Senha definida. Agora digite o código da verificação em duas etapas.")
            return redirect("verificar_codigo")
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


# Verificação em duas etapas (US 3.4, D51)

_BLOQUEADO = "Muitas tentativas de entrar. Espere 15 minutos e tente de novo, ou use Esqueci a senha."
_MAXIMO_DE_ERROS = 5


def _senha_confere(request, usuario, senha):
    """Confere a senha de novo (para ligar, desligar ou trocar códigos). Senha errada conta no bloqueio."""
    from ..limites import login_bloqueado, registrar_senha_errada

    if login_bloqueado(usuario.email, request):
        return False
    if usuario.check_password(senha):
        return True
    registrar_senha_errada(usuario.email, request)
    log.warning("2fa: %s errou a senha ao mexer na verificação em duas etapas", usuario.email)
    return False


def _mostrar_codigos(request, codigos, ligou=False):
    return render(request, PASTA + "codigos_de_recuperacao.html", {"codigos": codigos, "ligou": ligou})


@publica
@method_decorator(sensitive_post_parameters(), name="dispatch")
class VerificarCodigo(FormView):
    """Segunda etapa do login: o código do app, o do e-mail ou um código de recuperação."""

    template_name = PASTA + "verificar_codigo.html"
    form_class = FormularioCodigo

    def dispatch(self, request, *args, **kwargs):
        self.pendente = request.session.get(dois_fatores.SESSAO_PENDENTE)
        self.usuario = None
        if self.pendente and time.time() <= self.pendente.get("vence", 0):
            modelo = get_user_model()
            pk = modelo._meta.pk.to_python(self.pendente["pk"])
            # Leitura interna do 00 pela chave guardada na sessão depois da senha certa.
            self.usuario = modelo._base_manager.filter(pk=pk, is_active=True).first()
        if self.usuario is None or not self.usuario.dois_fatores:
            if self.pendente:
                messages.error(request, "O tempo para digitar o código acabou. Entre de novo.")
            request.session.pop(dois_fatores.SESSAO_PENDENTE, None)
            return redirect("entrar")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update(
            metodo=self.usuario.dois_fatores,
            email_mascarado=dois_fatores.mascarar_email(self.usuario.email),
        )
        return contexto

    def _desistir(self, mensagem):
        self.request.session.pop(dois_fatores.SESSAO_PENDENTE, None)
        messages.error(self.request, mensagem)
        return redirect("entrar")

    def form_valid(self, form):
        from ..limites import login_bloqueado, registrar_senha_errada

        usuario = self.usuario
        if login_bloqueado(usuario.email, self.request):
            return self._desistir(_BLOQUEADO)
        resultado = dois_fatores.conferir(usuario, form.cleaned_data["codigo"], self.pendente.get("email"))
        if resultado is None:
            registrar_senha_errada(usuario.email, self.request)
            self.pendente["erros"] = self.pendente.get("erros", 0) + 1
            self.request.session[dois_fatores.SESSAO_PENDENTE] = self.pendente
            log.warning("2fa: código errado para %s (%s)", usuario.email, limites.endereco_de(self.request))
            if self.pendente["erros"] >= _MAXIMO_DE_ERROS or login_bloqueado(usuario.email, self.request):
                return self._desistir("Código errado muitas vezes. Entre de novo.")
            form.add_error("codigo", "Código incorreto ou vencido.")
            return self.form_invalid(form)
        pendente = self.request.session.pop(dois_fatores.SESSAO_PENDENTE)
        login(self.request, usuario, backend=BACKEND)
        self.request.session[dois_fatores.SESSAO_OK] = True
        log.info("2fa: %s entrou com a verificação em duas etapas", usuario.email)
        if resultado == "recuperacao":
            dois_fatores.avisar(self.request, usuario, "recuperacao")
            restam = len(usuario.codigos_de_recuperacao)
            messages.warning(self.request, f"Você entrou com um código de recuperação. Restam {restam}. Se perdeu o "
                                           "celular, troque o método na tela de verificação em duas etapas.")
        return _concluir_login(self.request, usuario, pendente["manter"], pendente["lembrar"], pendente["destino"])


@publica
@method_decorator(require_POST, name="dispatch")
class ReenviarCodigo(View):
    """Manda outro código por e-mail (só para quem escolheu o método e-mail). Tem limite de envios."""

    def post(self, request):
        pendente = request.session.get(dois_fatores.SESSAO_PENDENTE)
        if not pendente or time.time() > pendente.get("vence", 0):
            return redirect("entrar")
        modelo = get_user_model()
        usuario = modelo._base_manager.filter(pk=modelo._meta.pk.to_python(pendente["pk"]), is_active=True).first()
        if usuario is None or usuario.dois_fatores != dois_fatores.EMAIL:
            return redirect("verificar_codigo")
        if dois_fatores.pode_reenviar(usuario):
            pendente["email"] = dois_fatores.novo_codigo_por_email(request, usuario)
            pendente["vence"] = time.time() + dois_fatores.VALIDADE_PENDENTE
            request.session[dois_fatores.SESSAO_PENDENTE] = pendente
            messages.success(request, "Enviamos um novo código.")
        else:
            messages.error(request, "Muitos envios seguidos. Espere alguns minutos para pedir outro código.")
        return redirect("verificar_codigo")


@logado
class MeusDoisFatores(TemplateView):
    """Situação da verificação em duas etapas da pessoa: ligar, trocar o método, códigos novos, desligar."""

    template_name = PASTA + "dois_fatores.html"

    def get_context_data(self, **kwargs):
        usuario = self.request.user
        exigido = dois_fatores.exigencia(usuario)
        contexto = super().get_context_data(**kwargs)
        contexto.update(
            metodo=usuario.dois_fatores,
            metodo_nome=usuario.get_dois_fatores_display(),
            desde=usuario.dois_fatores_desde,
            restam=len(usuario.codigos_de_recuperacao or []),
            obrigatoria=exigido is not None,
            so_app=exigido == dois_fatores.APP,
            pendente=not dois_fatores.cumpre(usuario, exigido),
            form_senha=FormularioSenhaAtual(),
        )
        return contexto


class _Ativar(FormView):
    form_class = FormularioSenhaECodigo
    metodo = None

    def _guardado(self):
        guardado = self.request.session.get(dois_fatores.SESSAO_ATIVACAO)
        return guardado if guardado and guardado.get("metodo") == self.metodo else None

    def _salvar_guardado(self, guardado):
        self.request.session[dois_fatores.SESSAO_ATIVACAO] = {**guardado, "metodo": self.metodo}

    def _errou(self, form, campo, mensagem):
        guardado = self._guardado() or {}
        guardado["erros"] = guardado.get("erros", 0) + 1
        if guardado["erros"] >= _MAXIMO_DE_ERROS:
            self.request.session.pop(dois_fatores.SESSAO_ATIVACAO, None)
            messages.error(self.request, "Erros demais. Comece a ativação de novo.")
            return redirect("dois_fatores")
        self._salvar_guardado(guardado)
        form.add_error(campo, mensagem)
        return self.form_invalid(form)

    def _ligou(self, chave=None, passo=0):
        usuario = self.request.user
        trocou = bool(usuario.dois_fatores)
        acao = "trocou o método para" if trocou else "ligou"
        codigos = dois_fatores.ligar(
            usuario, self.metodo, chave=chave, passo=passo,
            motivo=f"2fa: {usuario.email} {acao} a verificação em duas etapas ({self.metodo})",
        )
        self.request.session.pop(dois_fatores.SESSAO_ATIVACAO, None)
        self.request.session[dois_fatores.SESSAO_OK] = True
        dois_fatores.avisar(self.request, usuario, "trocou" if trocou else "ligou")
        return _mostrar_codigos(self.request, codigos, ligou=True)


@logado
@method_decorator(sensitive_post_parameters(), name="dispatch")
class AtivarApp(_Ativar):
    """Ligar com app autenticador: QR code, a pessoa escaneia e digita um código para confirmar."""

    template_name = PASTA + "ativar_app.html"
    metodo = dois_fatores.APP

    def _chave(self):
        guardado = self._guardado()
        chave = dois_fatores.decifrar(guardado["chave"]) if guardado else None
        if not chave:
            chave = dois_fatores.nova_chave_do_app()
            self._salvar_guardado({"chave": dois_fatores.cifrar(chave), "erros": 0})
        return chave

    def get_context_data(self, **kwargs):
        from django.utils.safestring import mark_safe

        chave = self._chave()
        contexto = super().get_context_data(**kwargs)
        contexto.update(
            qr_code=mark_safe(dois_fatores.qr_code_svg(dois_fatores.endereco_do_app(self.request.user, chave))),
            chave=" ".join(chave[i:i + 4] for i in range(0, len(chave), 4)),
            trocando=bool(self.request.user.dois_fatores),
        )
        return contexto

    def form_valid(self, form):
        if not _senha_confere(self.request, self.request.user, form.cleaned_data["senha"]):
            return self._errou(form, "senha", "Senha incorreta.")
        chave = self._chave()
        passo = dois_fatores.conferir_codigo_do_app(chave, form.cleaned_data["codigo"].replace(" ", ""))
        if passo is None:
            return self._errou(form, "codigo", "Código incorreto. Confira se o relógio do celular está certo.")
        return self._ligou(chave=chave, passo=passo)


@logado
@method_decorator(sensitive_post_parameters(), name="dispatch")
class AtivarEmail(_Ativar):
    """Ligar com código por e-mail: o sistema manda um código e a pessoa digita para confirmar."""

    template_name = PASTA + "ativar_email.html"
    metodo = dois_fatores.EMAIL

    def dispatch(self, request, *args, **kwargs):
        if dois_fatores.exigencia(request.user) == dois_fatores.APP:
            messages.error(request, "Para a sua conta, a verificação em duas etapas só vale com o app autenticador.")
            return redirect("dois_fatores")
        return super().dispatch(request, *args, **kwargs)

    def _enviar(self):
        if dois_fatores.pode_reenviar(self.request.user):
            self._salvar_guardado({**dois_fatores.novo_codigo_por_email(self.request, self.request.user), "erros": 0})
            return True
        messages.error(self.request, "Muitos envios seguidos. Espere alguns minutos para pedir outro código.")
        return False

    def get(self, request, *args, **kwargs):
        guardado = self._guardado()
        if guardado is None or time.time() > guardado.get("vence", 0):
            self._enviar()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if "reenviar" in request.POST:
            if self._enviar():
                messages.success(request, "Enviamos um novo código.")
            return redirect("ativar_email")
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update(email_mascarado=dois_fatores.mascarar_email(self.request.user.email),
                        trocando=bool(self.request.user.dois_fatores))
        return contexto

    def form_valid(self, form):
        if not _senha_confere(self.request, self.request.user, form.cleaned_data["senha"]):
            return self._errou(form, "senha", "Senha incorreta.")
        if not dois_fatores.conferir_codigo_por_email(self._guardado(), form.cleaned_data["codigo"].replace(" ", "")):
            return self._errou(form, "codigo", "Código incorreto ou vencido.")
        return self._ligou()


@logado
@method_decorator(require_POST, name="dispatch")
@method_decorator(sensitive_post_parameters(), name="dispatch")
class NovosCodigos(View):
    """Gera 10 códigos de recuperação novos (os antigos deixam de valer). Pede a senha."""

    def post(self, request):
        usuario = request.user
        form = FormularioSenhaAtual(request.POST)
        if not usuario.dois_fatores:
            return redirect("dois_fatores")
        if not form.is_valid() or not _senha_confere(request, usuario, form.cleaned_data["senha"]):
            messages.error(request, "Senha incorreta. Os códigos não foram trocados.")
            return redirect("dois_fatores")
        codigos = dois_fatores.trocar_codigos(usuario, f"2fa: {usuario.email} gerou códigos de recuperação novos")
        dois_fatores.avisar(request, usuario, "codigos")
        return _mostrar_codigos(request, codigos)


@logado
@method_decorator(sensitive_post_parameters(), name="dispatch")
class DesligarDoisFatores(FormView):
    """Desliga a verificação em duas etapas: pede a senha e um código. Quem é obrigado não desliga."""

    template_name = PASTA + "desligar_dois_fatores.html"
    form_class = FormularioSenhaECodigo

    def dispatch(self, request, *args, **kwargs):
        if not request.user.dois_fatores:
            return redirect("dois_fatores")
        if dois_fatores.exigencia(request.user) is not None:
            messages.error(request, "A verificação em duas etapas é obrigatória para a sua conta. Você pode trocar "
                                    "o método, mas não desligar.")
            return redirect("dois_fatores")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if request.user.dois_fatores == dois_fatores.EMAIL:
            if dois_fatores.pode_reenviar(request.user):
                request.session[dois_fatores.SESSAO_ATIVACAO] = {
                    **dois_fatores.novo_codigo_por_email(request, request.user), "metodo": "desligar"}
            else:
                messages.error(request, "Muitos envios seguidos. Espere alguns minutos.")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update(metodo=self.request.user.dois_fatores,
                        email_mascarado=dois_fatores.mascarar_email(self.request.user.email))
        return contexto

    def form_valid(self, form):
        usuario = self.request.user
        if not _senha_confere(self.request, usuario, form.cleaned_data["senha"]):
            form.add_error("senha", "Senha incorreta.")
            return self.form_invalid(form)
        guardado = self.request.session.get(dois_fatores.SESSAO_ATIVACAO) or {}
        guardado = guardado if guardado.get("metodo") == "desligar" else None
        if dois_fatores.conferir(usuario, form.cleaned_data["codigo"], guardado) is None:
            form.add_error("codigo", "Código incorreto ou vencido.")
            return self.form_invalid(form)
        self.request.session.pop(dois_fatores.SESSAO_ATIVACAO, None)
        dois_fatores.desligar(usuario, f"2fa: {usuario.email} desligou a verificação em duas etapas")
        dois_fatores.avisar(self.request, usuario, "desligou")
        messages.success(self.request, "Verificação em duas etapas desligada.")
        return redirect("dois_fatores")
