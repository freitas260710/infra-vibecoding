"""
Verificação em duas etapas (2FA) do Infra Vibecoding (US 3.4, D51).

Depois da senha, a pessoa digita um código de 6 números. Dois métodos:
- app autenticador (padrão): Senhas do iPhone, Google Authenticator, Microsoft Authenticator... Ao ativar, o
  sistema mostra um QR code com uma chave secreta só da pessoa. O app e o sistema calculam o mesmo código a partir
  dessa chave e do relógio (muda a cada 30 segundos). Nada é enviado: funciona sem internet no celular.
- código por e-mail: o sistema manda 6 números, que valem 10 minutos e uma vez só.

Regras:
- Na tela do código vale só o método que a pessoa escolheu ao ativar (não dá para "trocar para e-mail" ali: seria
  uma porta dos fundos). Perdeu o celular: usa um dos 10 códigos de recuperação e, já dentro, troca o método.
  Perdeu tudo: o admin zera a verificação na tela de banco e ela ativa de novo.
- Quem é obrigado: quem entra na tela de banco (is_staff), em produção, sempre, e só com app (regra do 00). Além
  disso, o sistema pode obrigar mais gente com uma função no settings.py:

      DOIS_FATORES_OBRIGATORIO = "nucleo.regras.exige_dois_fatores"

      # nucleo/regras.py
      def exige_dois_fatores(usuario):
          return usuario.empresa.exige_2fa     # no Mindor: a empresa decide

  Obrigado e ainda sem 2FA: no próximo clique fica preso na tela de ativar, até ativar.
- Esqueci a senha não pula a verificação: depois de definir a senha nova, o código é pedido.
- Nenhum login escapa: o 00 confere, a cada pedido, que a sessão de quem tem 2FA passou pelo código. Sessão sem
  essa marca (login feito por outro caminho) é derrubada.
- A chave do app fica cifrada no banco (com a SECRET_KEY). Os códigos de recuperação ficam guardados como a senha:
  ninguém consegue ler. Ligar, desligar, zerar e usar código de recuperação mandam e-mail de aviso.
- Errar o código conta como senha errada no bloqueio da US 3.3 (5 erros bloqueiam o e-mail por 15 minutos).
"""
import base64
import hashlib
import hmac
import logging
import secrets
import time

import pyotp
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.hashers import check_password, make_password
from django.http import HttpResponse
from django.shortcuts import redirect, resolve_url
from django.urls import Resolver404, resolve, reverse
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.module_loading import import_string

log = logging.getLogger("infra_vibecoding.auditoria")

APP = "app"
EMAIL = "email"
METODOS = ((APP, "app autenticador"), (EMAIL, "código por e-mail"))

SESSAO_OK = "infra_vibecoding_2fa_ok"            # esta sessão passou pelo código
SESSAO_PENDENTE = "infra_vibecoding_2fa_pendente"  # senha certa, esperando o código
SESSAO_ATIVACAO = "infra_vibecoding_2fa_ativacao"  # chave ou código gerado durante a ativação

VALIDADE_PENDENTE = 10 * 60      # 10 minutos para digitar o código depois da senha
VALIDADE_CODIGO_EMAIL = 10 * 60  # o código por e-mail vale 10 minutos
REENVIOS = (5, 15 * 60)          # até 5 envios de código por e-mail a cada 15 minutos, por usuário
QUANTOS_CODIGOS = 10
_LETRAS = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # sem 0/O, 1/I/L: fáceis de confundir


# Quem é obrigado

def exigencia(usuario):
    """None (não é obrigado), APP (só app) ou "qualquer" (app ou e-mail)."""
    if getattr(settings, "PRODUCAO", False) and usuario.is_staff:
        return APP
    caminho = getattr(settings, "DOIS_FATORES_OBRIGATORIO", None)
    if caminho and import_string(caminho)(usuario):
        return "qualquer"
    return None


def cumpre(usuario, exigido=None):
    exigido = exigencia(usuario) if exigido is None else exigido
    if exigido is None:
        return True
    if exigido == APP:
        return usuario.dois_fatores == APP
    return bool(usuario.dois_fatores)


# Chave do app (cifrada no banco)

def _fernet():
    chaves = [settings.SECRET_KEY, *getattr(settings, "SECRET_KEY_FALLBACKS", [])]
    return MultiFernet([
        Fernet(base64.urlsafe_b64encode(hashlib.sha256(f"infra_vibecoding.2fa:{c}".encode()).digest()))
        for c in chaves
    ])


def cifrar(segredo):
    return _fernet().encrypt(segredo.encode()).decode()


def decifrar(cifrado):
    try:
        return _fernet().decrypt(cifrado.encode()).decode()
    except (InvalidToken, ValueError):
        log.error("2fa: não foi possível ler a chave do app (a SECRET_KEY mudou sem SECRET_KEY_FALLBACKS?)")
        return None


def nova_chave_do_app():
    return pyotp.random_base32()


def endereco_do_app(usuario, chave):
    """O que vai dentro do QR code (padrão otpauth://, que todo app autenticador entende)."""
    from .convites import nome_do_sistema

    return pyotp.TOTP(chave).provisioning_uri(name=usuario.email, issuer_name=nome_do_sistema())


def qr_code_svg(texto):
    """QR code gerado aqui dentro (nunca por um site de fora: ele carrega a chave secreta)."""
    import segno

    return segno.make(texto, error="m").svg_inline(scale=5, border=2)


def conferir_codigo_do_app(chave, codigo, ultimo_passo=0):
    """Confere o código de 6 números. Aceita o código do momento e o vizinho (relógio do celular um pouco
    adiantado ou atrasado). Um código já usado não vale de novo. Devolve o passo usado, ou None."""
    if not chave or not (codigo.isdigit() and len(codigo) == 6):
        return None
    totp = pyotp.TOTP(chave)
    agora = int(time.time()) // totp.interval
    for passo in (agora - 1, agora, agora + 1):
        if passo > ultimo_passo and hmac.compare_digest(totp.generate_otp(passo), codigo):
            return passo
    return None


# Código por e-mail

def _resumo(codigo):
    return salted_hmac("infra_vibecoding.2fa.email", codigo, algorithm="sha256").hexdigest()


def novo_codigo_por_email(request, usuario):
    """Gera o código, manda por e-mail e devolve o que fica guardado na sessão (só o resumo, nunca o código)."""
    from .convites import _enviar

    codigo = f"{secrets.randbelow(10 ** 6):06d}"
    _enviar(request, usuario, "codigo", {"codigo": codigo, "minutos": VALIDADE_CODIGO_EMAIL // 60})
    log.info("2fa: código por e-mail enviado para %s", usuario.email)
    return {"resumo": _resumo(codigo), "vence": time.time() + VALIDADE_CODIGO_EMAIL}


def conferir_codigo_por_email(guardado, codigo):
    if not guardado or time.time() > guardado.get("vence", 0) or not codigo.isdigit():
        return False
    return hmac.compare_digest(guardado.get("resumo", ""), _resumo(codigo))


def pode_reenviar(usuario):
    from .limites import dentro_do_limite

    return dentro_do_limite("2fa-reenvio", usuario.pk, *REENVIOS)


def mascarar_email(email):
    """ana@exemplo.com vira ana*****@exemplo.com"""
    nome, _, dominio = email.partition("@")
    return f"{nome[:3]}*****@{dominio}"


# Códigos de recuperação

def _normalizar_recuperacao(texto):
    return "".join(c for c in texto.upper() if c.isalnum())


def parece_codigo_de_recuperacao(texto):
    return len(_normalizar_recuperacao(texto)) == 8  # o código do app e o do e-mail têm 6 números


def novos_codigos_de_recuperacao():
    """Devolve (códigos para mostrar uma vez, resumos para guardar)."""
    codigos = []
    for _ in range(QUANTOS_CODIGOS):
        bruto = "".join(secrets.choice(_LETRAS) for _ in range(8))
        codigos.append(f"{bruto[:4]}-{bruto[4:]}")
    return codigos, [make_password(_normalizar_recuperacao(c)) for c in codigos]


def usar_codigo_de_recuperacao(usuario, texto):
    """Confere e gasta um código de recuperação. Devolve True se valeu (o código deixa de existir)."""
    normal = _normalizar_recuperacao(texto)
    for i, resumo in enumerate(usuario.codigos_de_recuperacao or []):
        if check_password(normal, resumo):
            usuario.codigos_de_recuperacao = [r for j, r in enumerate(usuario.codigos_de_recuperacao) if j != i]
            usuario.salvar_como_sistema(
                f"2fa: {usuario.email} entrou com um código de recuperação "
                f"(restam {len(usuario.codigos_de_recuperacao)})",
                update_fields=["codigos_de_recuperacao"],
            )
            _registrar(usuario, f"usou um código de recuperação (restam {len(usuario.codigos_de_recuperacao)})")
            return True
    return False


# Conferência do código na hora de entrar (e para desligar)

def conferir(usuario, codigo, guardado_email=None):
    """Confere o código do método da pessoa ou um código de recuperação. Devolve "codigo", "recuperacao" ou None."""
    codigo = (codigo or "").strip().replace(" ", "")
    if parece_codigo_de_recuperacao(codigo):
        return "recuperacao" if usar_codigo_de_recuperacao(usuario, codigo) else None
    if usuario.dois_fatores == APP:
        passo = conferir_codigo_do_app(decifrar(usuario.segredo_do_app), codigo, usuario.ultimo_codigo_do_app)
        if passo is None:
            return None
        usuario.ultimo_codigo_do_app = passo
        usuario.salvar_como_sistema(f"2fa: {usuario.email} usou o código do app",
                                    update_fields=["ultimo_codigo_do_app"])
        return "codigo"
    if usuario.dois_fatores == EMAIL and conferir_codigo_por_email(guardado_email, codigo):
        return "codigo"
    return None


# Ligar, desligar e zerar

def ligar(usuario, metodo, chave=None, passo=0, motivo=""):
    """Grava o método escolhido e gera códigos de recuperação novos. Devolve os códigos (mostrados uma vez)."""
    codigos, resumos = novos_codigos_de_recuperacao()
    usuario.dois_fatores = metodo
    usuario.dois_fatores_desde = timezone.now()
    usuario.segredo_do_app = cifrar(chave) if metodo == APP else ""
    usuario.ultimo_codigo_do_app = passo if metodo == APP else 0
    usuario.codigos_de_recuperacao = resumos
    usuario.salvar_como_sistema(motivo or f"2fa: {usuario.email} ligou a verificação em duas etapas ({metodo})",
                                update_fields=list(_CAMPOS))
    _registrar(usuario, f"ligou ({'app autenticador' if metodo == APP else 'código por e-mail'})", motivo)
    return codigos


def desligar(usuario, motivo):
    usuario.dois_fatores = ""
    usuario.dois_fatores_desde = None
    usuario.segredo_do_app = ""
    usuario.ultimo_codigo_do_app = 0
    usuario.codigos_de_recuperacao = []
    usuario.salvar_como_sistema(motivo, update_fields=list(_CAMPOS))
    _registrar(usuario, "desligou", motivo)


def trocar_codigos(usuario, motivo):
    codigos, resumos = novos_codigos_de_recuperacao()
    usuario.codigos_de_recuperacao = resumos
    usuario.salvar_como_sistema(motivo, update_fields=["codigos_de_recuperacao"])
    _registrar(usuario, "gerou códigos de recuperação novos", motivo)
    return codigos


def _registrar(usuario, o_que, motivo=""):
    from ..acessos import registrar_acesso

    registrar_acesso("dois_fatores", f"{o_que} ({motivo})" if motivo else o_que, pessoa=usuario.email)


_CAMPOS = ("dois_fatores", "dois_fatores_desde", "segredo_do_app", "ultimo_codigo_do_app", "codigos_de_recuperacao")


def avisar(request, usuario, o_que):
    """E-mail de aviso: ligou, desligou, zerou, códigos novos ou código de recuperação usado."""
    from .convites import _enviar

    _enviar(request, usuario, "dois_fatores", {
        "o_que": o_que,
        "quando": timezone.localtime(),
        "restam": len(usuario.codigos_de_recuperacao or []),
    })


# Trava em todo pedido

_TELAS_LIVRES = frozenset({"dois_fatores", "ativar_app", "ativar_email", "sair"})


def _redirecionar(request, destino):
    if request.headers.get("HX-Request"):
        resposta = HttpResponse(status=200)
        resposta["HX-Redirect"] = destino
        return resposta
    return redirect(destino)


class ExigeDoisFatores:
    """Middleware da verificação em duas etapas. Vem ligado nas configurações do 00 (SEC.E068).

    1. Quem tem 2FA ligado só usa o sistema numa sessão que passou pelo código. Outra sessão é derrubada.
    2. Quem é obrigado e ainda não ativou fica preso na tela de ativar (só ela e "sair" abrem).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        if usuario is not None and usuario.is_authenticated:
            resposta = self.conferir(request, usuario)
            if resposta is not None:
                return resposta
        return self.get_response(request)

    def conferir(self, request, usuario):
        if getattr(usuario, "dois_fatores", "") and not request.session.get(SESSAO_OK):
            log.warning("2fa: sessão de %s sem a verificação em duas etapas foi derrubada (%s)",
                        usuario.email, request.path)
            _registrar(usuario, "sessão sem a verificação em duas etapas derrubada")
            logout(request)
            return _redirecionar(request, resolve_url(settings.LOGIN_URL))
        exigido = exigencia(usuario)
        if exigido is None or cumpre(usuario, exigido):
            return None
        static = getattr(settings, "STATIC_URL", None)
        if static and request.path.startswith("/" + static.lstrip("/")):
            return None
        try:
            nome = resolve(request.path_info).url_name
        except Resolver404:
            nome = None
        if nome in _TELAS_LIVRES:
            return None
        return _redirecionar(request, reverse("dois_fatores"))
