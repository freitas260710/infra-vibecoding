"""
Convite (primeiro acesso) e envio dos links de senha por e-mail.

    from infra_vibecoding.login import convidar

    @exige("criar", Usuario)
    def novo_colega(request):
        ...
        convidar(request.user, request, email=form.cleaned_data["email"], nome=..., empresa=...)

convidar confere a regra "criar" da tabela de usuário (quem pode abrir acesso para quem é decisão do sistema,
na política), cria o usuário sem senha e manda o link de primeiro acesso.
"""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from ..usuarios import normalizar_email
from .links import LINK_CONVITE, LINK_REDEFINIR

log = logging.getLogger("infra_vibecoding.auditoria")

_ASSUNTOS = {
    "convite": "Seu acesso foi criado",
    "redefinir": "Redefinição de senha",
    "aviso": "Sua senha foi definida",
}


def nome_do_sistema(request=None):
    nome = getattr(settings, "NOME_DO_SISTEMA", "")
    if nome:
        return nome
    return request.get_host() if request is not None else "sistema"


def _enviar(request, usuario, tipo, contexto):
    sistema = nome_do_sistema(request)
    contexto = {"usuario": usuario, "sistema": sistema, **contexto}
    corpo = render_to_string(f"infra_vibecoding/login/email/{tipo}.txt", contexto, request=request)
    send_mail(f"[{sistema}] {_ASSUNTOS[tipo]}", corpo, None, [usuario.email])


def link_de_senha(request, usuario):
    """Endereço completo do link para o usuário definir a senha. Tipo conforme ele já tem senha ou não."""
    if usuario.has_usable_password():
        tipo, gerador, rota = "redefinir", LINK_REDEFINIR, "definir_senha_redefinir"
    else:
        tipo, gerador, rota = "convite", LINK_CONVITE, "definir_senha_convite"
    caminho = reverse(rota, kwargs={
        "uidb64": urlsafe_base64_encode(force_bytes(usuario.pk)),
        "token": gerador.make_token(usuario),
    })
    return tipo, gerador, request.build_absolute_uri(caminho)


def enviar_link_de_senha(request, usuario):
    """Manda por e-mail o link de primeiro acesso (sem senha) ou de redefinição (com senha).

    Usuário desativado não recebe nada. Responde se enviou.
    """
    if not usuario.is_active:
        return False
    tipo, gerador, link = link_de_senha(request, usuario)
    _enviar(request, usuario, tipo, {"link": link, "horas": gerador.validade // 3600})
    log.info("login: link de %s enviado para %s", "primeiro acesso" if tipo == "convite" else "redefinição",
             usuario.email)
    return True


def enviar_aviso_de_senha(request, usuario, primeira_vez):
    """E-mail avisando que a senha foi definida ou trocada. Se não foi a pessoa, ela fica sabendo na hora."""
    _enviar(request, usuario, "aviso", {"primeira_vez": primeira_vez, "quando": timezone.localtime()})


def convidar(autor, request, email, **campos):
    """Abre acesso para um colega: cria o usuário sem senha e manda o link de primeiro acesso.

    Confere a permissão "criar" da tabela de usuário para o autor (SemPermissao se não puder) e valida os
    campos (ValidationError se, por exemplo, o e-mail já existir).
    """
    modelo = get_user_model()
    usuario = modelo(email=normalizar_email(email), **campos)
    usuario.set_unusable_password()
    usuario.full_clean(exclude=["password"])
    usuario.salvar(autor)
    log.info("login: %s abriu acesso para %s", getattr(autor, "email", autor), usuario.email)
    enviar_link_de_senha(request, usuario)
    return usuario
