"""
Checagens do Infra Vibecoding. Rodam sempre que o sistema liga (runserver, migrate, check, deploy).
Qualquer erro aqui impede o sistema de subir.
"""
import sysconfig
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.checks import Error, Tags, register

from .dados import ModeloSeguro, politica_de

_PASTAS_DE_BIBLIOTECAS = {
    Path(p).resolve()
    for p in (sysconfig.get_paths()["purelib"], sysconfig.get_paths()["platlib"])
}


def _eh_do_sistema(app_config):
    """App escrito no próprio sistema: fica dentro de BASE_DIR e fora das bibliotecas instaladas."""
    base = getattr(settings, "BASE_DIR", None)
    if base is None or app_config.name == "infra_vibecoding":
        return False
    caminho = Path(app_config.path).resolve()
    if any(caminho == p or p in caminho.parents for p in _PASTAS_DE_BIBLIOTECAS):
        return False
    base = Path(base).resolve()
    return caminho == base or base in caminho.parents


def verificar_modelo(model):
    """Erros de trava de dados de uma tabela (lista vazia = ok)."""
    nome = f"{model._meta.app_label}.{model.__name__}"
    if not issubclass(model, ModeloSeguro):
        return [Error(
            f"{nome} não herda de ModeloSeguro.",
            hint="Troque models.Model por infra_vibecoding.dados.ModeloSeguro.",
            obj=model,
            id="SEC.E021",
        )]
    if politica_de(model) is None:
        return [Error(
            f"{nome} não tem política de acesso.",
            hint=f"Crie @politica({model.__name__}) no arquivo politicas.py do app {model._meta.app_label}.",
            obj=model,
            id="SEC.E022",
        )]
    return []


@register(Tags.models)
def sec02_toda_tabela_tem_politica(app_configs=None, **kwargs):
    configs = app_configs if app_configs is not None else apps.get_app_configs()
    erros = []
    for cfg in configs:
        if _eh_do_sistema(cfg):
            for model in cfg.get_models():
                erros.extend(verificar_modelo(model))
    return erros


# Telas (US 1.4)

NAMESPACES_IGNORADOS = {"admin"}  # o admin tem proteção própria (endurecida na US 1.7)
_MW_AUTH = "django.contrib.auth.middleware.AuthenticationMiddleware"
_MW_LOGIN = "django.contrib.auth.middleware.LoginRequiredMiddleware"


def _percorrer_rotas(padroes, prefixo="", namespace=None):
    from django.urls import URLPattern, URLResolver

    for p in padroes:
        if isinstance(p, URLResolver):
            ns = p.namespace or namespace
            if ns in NAMESPACES_IGNORADOS:
                continue
            yield from _percorrer_rotas(p.url_patterns, prefixo + str(p.pattern), ns)
        elif isinstance(p, URLPattern):
            yield prefixo + str(p.pattern), p.callback


@register(Tags.urls)
def sec04_toda_tela_declara_acesso(app_configs=None, **kwargs):
    from django.urls import get_resolver

    from .telas import acesso_declarado

    if not getattr(settings, "ROOT_URLCONF", None):
        return []
    erros = []
    for rota, view in _percorrer_rotas(get_resolver().url_patterns):
        if acesso_declarado(view) is None:
            nome = getattr(view, "__name__", repr(view))
            erros.append(Error(
                f"Tela '/{rota}' ({nome}) não declara quem pode abrir.",
                hint="Use @publica, @logado ou @exige(acao, Model) de infra_vibecoding.telas.",
                id="SEC.E041",
            ))
    return erros


@register(Tags.security)
def sec06_login_obrigatorio_por_padrao(app_configs=None, **kwargs):
    mw = list(getattr(settings, "MIDDLEWARE", []))
    if _MW_LOGIN not in mw:
        return [Error(
            "LoginRequiredMiddleware ausente: as telas ficariam abertas por padrão.",
            hint=f"Inclua '{_MW_LOGIN}' em MIDDLEWARE, logo depois do AuthenticationMiddleware.",
            id="SEC.E061",
        )]
    if _MW_AUTH not in mw or mw.index(_MW_LOGIN) < mw.index(_MW_AUTH):
        return [Error(
            "LoginRequiredMiddleware precisa vir depois do AuthenticationMiddleware.",
            id="SEC.E062",
        )]
    return []


# Configurações de segurança (US 1.5)

_MW_OBRIGATORIOS = {
    "django.middleware.security.SecurityMiddleware": "SEC.E063",
    "django.middleware.csrf.CsrfViewMiddleware": "SEC.E064",
    "django.middleware.clickjacking.XFrameOptionsMiddleware": "SEC.E065",
}
_HSTS_MINIMO = 60 * 60 * 24 * 365
_SESSAO_MAXIMA = 60 * 60 * 24 * 30


@register(Tags.security)
def sec01_configuracoes_de_seguranca(app_configs=None, **kwargs):
    s = settings
    erros = []

    def erro(msg, id, hint=None):
        erros.append(Error(msg, hint=hint, id=id))

    if not hasattr(s, "AMBIENTE"):
        erro(
            "As configurações do Infra Vibecoding não foram importadas.",
            "SEC.E010",
            hint="Coloque 'from infra_vibecoding.configuracoes import *' no início do settings.py.",
        )
        return erros

    hashers = list(getattr(s, "PASSWORD_HASHERS", []))
    if not hashers or not hashers[0].endswith("Argon2PasswordHasher"):
        erro("A senha não é guardada com Argon2 (primeiro item de PASSWORD_HASHERS).", "SEC.E011")

    if not s.SESSION_COOKIE_HTTPONLY:
        erro("SESSION_COOKIE_HTTPONLY desligado: o cookie de login ficaria legível por JavaScript.", "SEC.E012")

    if s.SESSION_COOKIE_AGE > _SESSAO_MAXIMA:
        erro("SESSION_COOKIE_AGE acima de 30 dias.", "SEC.E019")

    validadores = {v.get("NAME", "").rsplit(".", 1)[-1]: v for v in getattr(s, "AUTH_PASSWORD_VALIDATORS", [])}
    minimo = validadores.get("MinimumLengthValidator", {}).get("OPTIONS", {}).get("min_length", 8)
    if "MinimumLengthValidator" not in validadores or minimo < 10:
        erro("Política de senha fraca: tamanho mínimo precisa ser 10 ou mais.", "SEC.E017")
    if "CommonPasswordValidator" not in validadores:
        erro("Política de senha fraca: senhas comuns (ex.: 123456) não estão bloqueadas.", "SEC.E017")

    if getattr(s, "X_FRAME_OPTIONS", None) != "DENY":
        erro("X_FRAME_OPTIONS precisa ser 'DENY' (o sistema não pode ser aberto dentro de outro site).", "SEC.E016")

    mw = list(getattr(s, "MIDDLEWARE", []))
    for caminho, id in _MW_OBRIGATORIOS.items():
        if caminho not in mw:
            erro(f"{caminho.rsplit('.', 1)[-1]} ausente de MIDDLEWARE.", id)

    if s.AMBIENTE == "producao":
        if s.DEBUG:
            erro("DEBUG ligado em produção.", "SEC.E014")
        if len(s.SECRET_KEY) < 50 or len(set(s.SECRET_KEY)) < 5 or s.SECRET_KEY.startswith("dev-inseguro"):
            erro("SECRET_KEY de produção ausente, curta, repetitiva ou de desenvolvimento.", "SEC.E015")
        if not s.ALLOWED_HOSTS or "*" in s.ALLOWED_HOSTS:
            erro("ALLOWED_HOSTS de produção vazio ou com '*'.", "SEC.E020")
        for nome in ("SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "SECURE_SSL_REDIRECT"):
            if not getattr(s, nome, False):
                erro(f"{nome} desligado em produção.", "SEC.E013")
        if getattr(s, "SECURE_HSTS_SECONDS", 0) < _HSTS_MINIMO:
            erro("SECURE_HSTS_SECONDS abaixo de 1 ano em produção.", "SEC.E013")

    return erros


# Tela de banco / admin (US 1.6)

def verificar_admin(site=None):
    """Toda tabela do sistema registrada no admin precisa usar AdminSeguro."""
    from django.contrib import admin as dj_admin

    from .admin import AdminSeguro

    from django.contrib.admin.utils import flatten_fieldsets

    from .admin import AdminUsuarioSeguro

    site = site or dj_admin.site
    erros = []
    for model, model_admin in site._registry.items():
        if issubclass(model, ModeloSeguro) and not isinstance(model_admin, AdminSeguro):
            erros.append(Error(
                f"{model._meta.label} está no admin sem AdminSeguro.",
                hint="Registre com admin.site.register(Model, AdminSeguro) de infra_vibecoding.admin.",
                obj=model,
                id="SEC.E071",
            ))
        if isinstance(model_admin, AdminUsuarioSeguro):
            campos = set(flatten_fieldsets(getattr(model_admin, "add_fieldsets", ()) or ()))
            reabriu = type(model_admin).user_change_password is not AdminUsuarioSeguro.user_change_password
            if campos & _CAMPOS_DE_SENHA_NA_CRIACAO or reabriu:
                erros.append(Error(
                    f"A tela de banco de {model._meta.label} permite definir a senha de outra pessoa.",
                    hint=(
                        "Tire password1, password2 e usable_password do add_fieldsets e não sobrescreva "
                        "user_change_password. O usuário define a própria senha pelo link do e-mail (D43)."
                    ),
                    obj=model,
                    id="SEC.E073",
                ))
    return erros


_CAMPOS_DE_SENHA_NA_CRIACAO = {"password", "password1", "password2", "usable_password"}


@register(Tags.admin)
def sec07_admin_protegido(app_configs=None, **kwargs):
    if not apps.is_installed("django.contrib.admin"):
        return []
    return verificar_admin()


@register(Tags.urls)
def sec07_endereco_do_admin(app_configs=None, **kwargs):
    from django.urls import URLResolver, get_resolver

    if not getattr(settings, "ROOT_URLCONF", None):
        return []
    for p in get_resolver().url_patterns:
        if isinstance(p, URLResolver) and p.namespace == "admin" and str(p.pattern) in ("admin/", "admin"):
            return [Error(
                "O admin está no endereço padrão 'admin/', que robôs testam o tempo todo.",
                hint="Troque por um endereço próprio, ex.: path('gestao-interna/', admin.site.urls).",
                id="SEC.E072",
            )]
    return []


# Checagens silenciadas (US 2.1)

def conferir_checagens_silenciadas(silenciadas):
    """Impede silenciar checagens do 00. Roda ao ligar, antes das checagens.

    Não é uma checagem comum de propósito: uma checagem comum também poderia ser silenciada.
    Aqui o sistema simplesmente não liga.
    """
    from django.core.exceptions import ImproperlyConfigured

    proibidas = sorted(c for c in silenciadas if str(c).strip().upper().startswith("SEC"))
    if proibidas:
        raise ImproperlyConfigured(
            "SILENCED_SYSTEM_CHECKS tenta silenciar checagens do Infra Vibecoding: "
            + ", ".join(proibidas)
            + ". Checagens SEC.* não podem ser silenciadas. Corrija a causa do erro."
        )


# Tabela de usuário e login (US 2.4)

_BACKEND_00 = "infra_vibecoding.autenticacao.BackendSeguro"
_BACKEND_DJANGO = "django.contrib.auth.backends.ModelBackend"


@register(Tags.security)
def sec08_usuario_seguro(app_configs=None, **kwargs):
    from django.contrib.auth import get_user_model

    from .usuarios import UsuarioSeguro

    erros = []
    try:
        modelo = get_user_model()
    except Exception:  # AUTH_USER_MODEL apontando para tabela que não existe: o próprio Django acusa
        return erros
    if not issubclass(modelo, UsuarioSeguro):
        erros.append(Error(
            f"A tabela de usuário ({modelo._meta.label}) não herda de UsuarioSeguro: ficaria sem trava.",
            hint=(
                "Crie o app 'contas' com 'class Usuario(UsuarioSeguro): pass' "
                "(from infra_vibecoding.usuarios import UsuarioSeguro) e coloque "
                "AUTH_USER_MODEL = 'contas.Usuario' no settings.py, antes da primeira migração."
            ),
            id="SEC.E081",
        ))
    backends = list(getattr(settings, "AUTHENTICATION_BACKENDS", []))
    if _BACKEND_00 not in backends or _BACKEND_DJANGO in backends:
        erros.append(Error(
            "AUTHENTICATION_BACKENDS precisa usar o login do 00 e não o padrão do Django.",
            hint=f"Não redefina AUTHENTICATION_BACKENDS: ele vem do 00 como ['{_BACKEND_00}'].",
            id="SEC.E082",
        ))
    return erros


# Telas de login do 00 (US 3.1)

_ROTAS_DE_LOGIN = ("sair", "primeiro_acesso", "esqueci_a_senha", "trocar_senha")


@register(Tags.urls)
def sec08_telas_de_login_do_00(app_configs=None, **kwargs):
    """O login do sistema é o do 00: entrar, primeiro acesso, esqueci a senha e trocar a senha."""
    from django.shortcuts import resolve_url
    from django.urls import NoReverseMatch, Resolver404, resolve, reverse

    from .login.views import Entrar

    if not getattr(settings, "ROOT_URLCONF", None):
        return []
    try:
        tela = resolve(resolve_url(settings.LOGIN_URL)).func
        ok = getattr(tela, "view_class", None) is Entrar or (
            isinstance(getattr(tela, "view_class", None), type) and issubclass(tela.view_class, Entrar)
        )
        for nome in _ROTAS_DE_LOGIN:
            reverse(nome)
    except (NoReverseMatch, Resolver404):
        ok = False
    if ok:
        return []
    return [Error(
        "O sistema não usa as telas de login do 00 (entrar, sair, primeiro acesso, esqueci a senha).",
        hint=(
            "Inclua path(\"\", include(\"infra_vibecoding.login.urls\")) no config/urls.py, apague as telas de "
            "entrar e sair próprias e não redefina LOGIN_URL (vem do 00 como 'entrar')."
        ),
        id="SEC.E083",
    )]


# E-mail (US 3.1b)

_ENVIO_00 = "infra_vibecoding.email.EnvioComDesvio"
_ENVIO_DOS_TESTES = "django.core.mail.backends.locmem.EmailBackend"  # caixa de mentira que o pytest-django liga


@register(Tags.security)
def sec09_email(app_configs=None, **kwargs):
    erros = []
    if getattr(settings, "EMAIL_BACKEND", "") not in (_ENVIO_00, _ENVIO_DOS_TESTES):
        erros.append(Error(
            "EMAIL_BACKEND trocado: o envio de e-mail precisa ser o do 00 (desvio para a caixa de teste fora de "
            "produção).",
            hint=f"Não redefina EMAIL_BACKEND: ele vem do 00 como '{_ENVIO_00}'.",
            id="SEC.E091",
        ))
    if getattr(settings, "AMBIENTE", None) == "producao":
        remetente = str(getattr(settings, "DEFAULT_FROM_EMAIL", "")).lower()
        if not getattr(settings, "EMAIL_HOST", "") or not remetente or "localhost" in remetente:
            erros.append(Error(
                "Produção sem provedor de e-mail ou com remetente de mentira (localhost).",
                hint="Preencha EMAIL_HOST, os dados SMTP e EMAIL_REMETENTE nas variáveis de ambiente do servidor.",
                id="SEC.E092",
            ))
    return erros


# Cadastro público (US 3.2)

@register(Tags.security)
def sec08_cadastro_publico(app_configs=None, **kwargs):
    caminho = getattr(settings, "CADASTRO_PUBLICO", None)
    if not caminho:
        return []
    from django.utils.module_loading import import_string

    from .login.cadastro import Cadastro

    try:
        classe = import_string(caminho)
    except ImportError:
        classe = None
    if not (isinstance(classe, type) and issubclass(classe, Cadastro)):
        problema = f"CADASTRO_PUBLICO aponta para '{caminho}', que não é uma classe de cadastro do 00."
    elif not (classe.termos_url and classe.privacidade_url):
        problema = "Cadastro público ligado sem os endereços dos termos de uso e da política de privacidade (LGPD)."
    else:
        return []
    return [Error(
        problema,
        hint=(
            "Crie uma subclasse de infra_vibecoding.login.cadastro.Cadastro com termos_url e privacidade_url "
            "preenchidos, ou deixe CADASTRO_PUBLICO = None."
        ),
        id="SEC.E084",
    )]


# Manual da IA (US 3.2b)

def caminho_do_manual():
    from pathlib import Path as _P

    return _P(__file__).resolve().parent / "REGRAS_DA_IA.md"


def linha_do_manual(base):
    """A linha que o CLAUDE.md do sistema precisa ter para carregar o manual do 00 instalado."""
    import os

    return "@" + os.path.relpath(caminho_do_manual(), base).replace(os.sep, "/")


@register()
def sec10_manual_da_ia(app_configs=None, **kwargs):
    """O CLAUDE.md do sistema carrega o manual da IA do 00 instalado (não uma cópia das regras)."""
    base = getattr(settings, "BASE_DIR", None)
    if base is None or getattr(settings, "AMBIENTE", None) == "producao":
        return []
    base = Path(base).resolve()
    if base not in caminho_do_manual().parents:
        return []  # o 00 não está instalado dentro da pasta do sistema (ex.: o próprio repositório do 00)
    esperada = linha_do_manual(base)
    claude = base / "CLAUDE.md"
    linhas = claude.read_text(encoding="utf-8").splitlines() if claude.is_file() else []
    if esperada in (linha.strip() for linha in linhas):
        return []
    return [Error(
        "O CLAUDE.md do sistema não carrega o manual da IA do 00 (as regras de como usar o 00 na versão instalada).",
        hint=f"Coloque no CLAUDE.md, numa linha sozinha: {esperada}   (o comando 'uv run infra-vibecoding regras' "
             "mostra a mesma linha). Não copie as regras do 00 para o CLAUDE.md.",
        id="SEC.E101",
    )]


_LINHA_DE_MANUAL = __import__("re").compile(r"^@\S*infra_vibecoding/REGRAS_DA_IA\.md\s*$")


def garantir_manual_no_claude_md(base=None):
    """O próprio 00 coloca (ou corrige) a linha do manual no CLAUDE.md do sistema, quando ele liga no computador
    do desenvolvedor. Não roda em produção nem na verificação do GitHub (lá a SEC.E101 confere o que foi enviado).
    Devolve True se mexeu no arquivo."""
    import os
    import sys

    base = base or getattr(settings, "BASE_DIR", None)
    if base is None or getattr(settings, "AMBIENTE", None) == "producao" or os.environ.get("CI"):
        return False
    base = Path(base).resolve()
    if base not in caminho_do_manual().parents:
        return False
    esperada = linha_do_manual(base)
    claude = base / "CLAUDE.md"
    linhas = claude.read_text(encoding="utf-8").splitlines() if claude.is_file() else []
    if esperada in (linha.strip() for linha in linhas):
        return False
    antigas = [i for i, linha in enumerate(linhas) if _LINHA_DE_MANUAL.match(linha.strip())]
    if antigas:  # caminho antigo (ex.: mudou a versão do Python): troca pela linha certa
        for i in antigas:
            linhas[i] = esperada
    else:
        bloco = ["", "Regras do Infra Vibecoding (00), na versão instalada (colocada pelo próprio 00):", esperada, ""]
        posicao = 1 if linhas and linhas[0].startswith("#") else 0
        linhas[posicao:posicao] = bloco if linhas else ["# Regras para a IA neste sistema", *bloco]
    claude.write_text("\n".join(linhas).rstrip("\n") + "\n", encoding="utf-8")
    print(f"Infra Vibecoding: coloquei no CLAUDE.md a linha do manual da IA ({esperada}). Inclua no próximo commit.",
          file=sys.stderr)
    return True


# Limite de pedidos (US 3.3)

_MW_LIMITE = "infra_vibecoding.limites.LimiteDePedidos"


@register(Tags.security)
def sec06_limite_de_pedidos(app_configs=None, **kwargs):
    from .limites import MAXIMO_POR_ENDERECO, MAXIMO_POR_USUARIO

    erros = []
    mw = list(getattr(settings, "MIDDLEWARE", []))
    if _MW_LIMITE not in mw or _MW_AUTH not in mw or mw.index(_MW_LIMITE) < mw.index(_MW_AUTH):
        erros.append(Error(
            "Limite de pedidos desligado ou fora de ordem: o sistema ficaria aberto a força bruta.",
            hint=f"Não redefina MIDDLEWARE: '{_MW_LIMITE}' vem do 00, logo depois do AuthenticationMiddleware.",
            id="SEC.E066",
        ))
    if (getattr(settings, "LIMITE_PEDIDOS_POR_ENDERECO", MAXIMO_POR_ENDERECO) > MAXIMO_POR_ENDERECO
            or getattr(settings, "LIMITE_PEDIDOS_POR_USUARIO", MAXIMO_POR_USUARIO) > MAXIMO_POR_USUARIO):
        erros.append(Error(
            "Limite de pedidos afrouxado acima do máximo do 00.",
            hint=f"O sistema só pode apertar: até {MAXIMO_POR_ENDERECO} por endereço e {MAXIMO_POR_USUARIO} "
                 "por usuário, por minuto.",
            id="SEC.E067",
        ))
    return erros


# Verificação em duas etapas (US 3.4)

_MW_2FA = "infra_vibecoding.login.dois_fatores.ExigeDoisFatores"


@register(Tags.security)
def sec06_dois_fatores(app_configs=None, **kwargs):
    erros = []
    mw = list(getattr(settings, "MIDDLEWARE", []))
    if _MW_2FA not in mw or _MW_AUTH not in mw or mw.index(_MW_2FA) < mw.index(_MW_AUTH):
        erros.append(Error(
            "Verificação em duas etapas desligada ou fora de ordem: quem tem 2FA poderia entrar sem o código.",
            hint=f"Não redefina MIDDLEWARE: '{_MW_2FA}' vem do 00, depois do AuthenticationMiddleware.",
            id="SEC.E068",
        ))
    caminho = getattr(settings, "DOIS_FATORES_OBRIGATORIO", None)
    if caminho:
        from django.utils.module_loading import import_string

        try:
            funcao = import_string(caminho)
        except ImportError:
            funcao = None
        if not callable(funcao):
            erros.append(Error(
                f"DOIS_FATORES_OBRIGATORIO aponta para '{caminho}', que não é uma função do sistema.",
                hint="Aponte para uma função que recebe o usuário e responde True (obrigado) ou False, "
                     "ou deixe DOIS_FATORES_OBRIGATORIO = None.",
                id="SEC.E069",
            ))
    return erros
