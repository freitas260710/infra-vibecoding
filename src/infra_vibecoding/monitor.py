"""
Monitor de erros do Infra Vibecoding (US 6.3, decisões D59 e D60): Sentry, plano gratuito, trocável pelo GlitchTip.

Liga sozinho quando o ambiente (ou o .env) tem SENTRY_DSN, o endereço do projeto no Sentry. Sem ele, nada é enviado.
Cada erro interno vai para o Sentry com:
- o código do clique (etiqueta "pedido") e o código do erro que a pessoa vê (etiqueta "codigo_do_erro", E-...);
- o ambiente (AMBIENTE: dev ou producao), a versão do 00 (etiqueta "versao_00") e a versão do sistema, se o
  servidor informar VERSAO_DO_SISTEMA;
- a pessoa só pelo número dela (quem ela é aparece na tela de Registros, dentro do sistema).

Nunca vai: e-mail, nome, senha, cookies, cabeçalhos, conteúdo de formulário, endereço de internet, valores das
variáveis do programa e o caminho completo da tela (vai o modelo da tela, ex.: /redefinir-senha/{uidb64}/{token}/,
porque alguns endereços levam códigos). E-mails, números longos (CPF, CNPJ, telefone, cartão) e "senha=..." que
aparecerem na mensagem do erro são trocados por marcadores antes do envio. O sistema não liga se alguém tentar
afrouxar isso (SEC.E132).

Na tela de Registros, a linha do erro ganha o link "ver no Sentry" quando SENTRY_PAINEL tem o endereço da lista de
erros do projeto no Sentry (ex.: https://mindtopo.sentry.io/issues/?project=123).
"""
import os
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_SENSIVEL = re.compile(r"(?i)\b(senha|password|passwd|token|chave|secret|segredo|codigo|código)(\s*[=:]\s*)\S+")
_NUMERO = re.compile(r"\d[\d.\-/ ]{9,}\d")


def limpar_texto(texto):
    """Troca por marcadores o que parece dado pessoal ou segredo num texto de erro."""
    if not isinstance(texto, str):
        return texto
    texto = _EMAIL.sub("[e-mail]", texto)
    texto = _SENSIVEL.sub(lambda m: f"{m.group(1)}{m.group(2)}[oculto]", texto)
    return _NUMERO.sub(lambda m: "[número]" if sum(c.isdigit() for c in m.group(0)) >= 11 else m.group(0), texto)


def _antes_de_enviar(evento, dica):
    from . import __version__
    from .pedido import pedido_atual

    pedido = pedido_atual()
    requisicao = evento.get("request") or {}
    metodo = requisicao.get("method") or (getattr(pedido.request, "method", "") if pedido is not None else "")
    evento["request"] = {"method": metodo or "", "url": evento.get("transaction") or ""}
    evento.pop("breadcrumbs", None)
    evento.pop("user", None)
    evento.pop("server_name", None)
    tags = evento.setdefault("tags", {})
    tags["versao_00"] = __version__
    if pedido is not None:
        tags["pedido"] = pedido.codigo
        tags["codigo_do_erro"] = "E-" + pedido.codigo
        usuario = getattr(pedido.request, "user", None)
        if usuario is not None and getattr(usuario, "is_authenticated", False):
            evento["user"] = {"id": str(usuario.pk)}
    for excecao in (evento.get("exception") or {}).get("values", []):
        excecao["value"] = limpar_texto(excecao.get("value"))
        for quadro in (excecao.get("stacktrace") or {}).get("frames", []):
            quadro.pop("vars", None)
    if isinstance(evento.get("message"), str):
        evento["message"] = limpar_texto(evento["message"])
    if isinstance(evento.get("logentry"), dict):
        evento["logentry"] = {"message": limpar_texto(evento["logentry"].get("message", "")), "params": []}
    return evento


def _sem_rastros(rastro, dica):
    return None  # rastros (consultas, registros do servidor, chamadas) podem levar dados pessoais: não vão


OPCOES_OBRIGATORIAS = {
    "send_default_pii": False,         # nada de e-mail, endereço de internet, cookies
    "include_local_variables": False,  # nada dos valores das variáveis do programa
    "max_request_body_size": "never",  # nada do conteúdo de formulários
    "auto_session_tracking": False,    # sem contagem de sessões
    "enable_logs": False,              # os registros do servidor não vão
}


def ligar(dsn=None, transporte=None):
    """Liga o envio de erros ao Sentry. Sem DSN, não faz nada e responde False."""
    dsn = os.environ.get("SENTRY_DSN", "") if dsn is None else dsn
    if not dsn:
        return False
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    opcoes = {
        "dsn": dsn,
        "environment": os.environ.get("AMBIENTE", "dev"),
        "release": os.environ.get("VERSAO_DO_SISTEMA") or None,
        "traces_sample_rate": 0,
        "before_send": _antes_de_enviar,
        "before_breadcrumb": _sem_rastros,
        "integrations": [DjangoIntegration(transaction_style="url"),
                         LoggingIntegration(level=None, event_level=None)],
        **OPCOES_OBRIGATORIAS,
    }
    if transporte is not None:
        opcoes["transport"] = transporte
    sentry_sdk.init(**opcoes)
    return True


def configuracao_segura():
    """Se o Sentry está ligado, confere que ninguém afrouxou a proteção dos dados. Devolve a lista de problemas."""
    try:
        import sentry_sdk
    except ImportError:
        return []
    cliente = sentry_sdk.get_client()
    if not cliente.is_active() or not cliente.options.get("dsn"):
        return []  # desligado: nada é enviado
    opcoes = cliente.options
    problemas = [f"{nome}={opcoes.get(nome)!r}" for nome, valor in OPCOES_OBRIGATORIAS.items()
                 if opcoes.get(nome) != valor]
    if opcoes.get("before_send") is not _antes_de_enviar:
        problemas.append("before_send trocado")
    if opcoes.get("before_breadcrumb") is not _sem_rastros:
        problemas.append("before_breadcrumb trocado")
    return problemas


def link_do_erro(codigo):
    """Endereço da lista de erros do Sentry filtrada pelo código do clique, se SENTRY_PAINEL estiver definido."""
    from django.conf import settings

    painel = getattr(settings, "SENTRY_PAINEL", "") or ""
    if not painel or not codigo:
        return ""
    partes = urlsplit(painel)
    consulta = [(k, v) for k, v in parse_qsl(partes.query) if k != "query"] + [("query", f"pedido:{codigo}")]
    return urlunsplit(partes._replace(query=urlencode(consulta)))
