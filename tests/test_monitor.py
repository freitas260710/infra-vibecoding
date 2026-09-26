"""Testes do monitor de erros (US 6.3, D59): Sentry de mentira, nada sai para a internet."""
import json

import pytest
import sentry_sdk
from django.contrib.auth import get_user_model
from django.core.checks import run_checks
from django.test import Client
from sentry_sdk.transport import Transport

from infra_vibecoding import monitor
from infra_vibecoding.models import Acesso

pytestmark = pytest.mark.django_db
Usuario = get_user_model()
SENHA = "uma-senha-bem-longa-para-teste"
DSN = "https://chavepublica@sentry.exemplo.invalid/1"


class SentryDeMentira(Transport):
    def __init__(self, options=None):
        super().__init__(options)
        self.eventos = []

    def capture_envelope(self, envelope):
        for item in envelope.items:
            if item.type == "event":
                self.eventos.append(item.payload.json)


@pytest.fixture
def sentry(monkeypatch):
    monkeypatch.setenv("AMBIENTE", "producao")
    monkeypatch.setenv("VERSAO_DO_SISTEMA", "mindor@1.2.3")
    caixa = SentryDeMentira()
    assert monitor.ligar(DSN, transporte=caixa)
    yield caixa
    sentry_sdk.get_client().close()
    sentry_sdk.init()  # desliga (sem DSN)


@pytest.fixture
def ana():
    return Usuario.objects.create_user("ana@exemplo.com", password=SENHA, nome="Ana")


def sem_codigo_fonte(evento):
    """O trecho do código do programa em volta do erro vai (é código, não dado de ninguém): tira para conferir o resto."""
    copia = json.loads(json.dumps(evento))
    for excecao in copia["exception"]["values"]:
        for quadro in excecao["stacktrace"]["frames"]:
            for campo in ("pre_context", "context_line", "post_context"):
                quadro.pop(campo, None)
    return json.dumps(copia, ensure_ascii=False)


def cliente(usuario=None):
    c = Client(raise_request_exception=False, HTTP_USER_AGENT="Navegador de Teste", REMOTE_ADDR="203.0.113.7")
    if usuario is not None:
        c.force_login(usuario)
    return c


def test_sem_dsn_nao_liga(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert monitor.ligar() is False
    assert not sentry_sdk.get_client().options.get("dsn")


def test_erro_vai_com_codigos_ambiente_e_versoes(sentry, ana):
    r = cliente(ana).get("/quebrada/?busca=ana@exemplo.com")
    assert r.status_code == 500
    [evento] = sentry.eventos
    assert evento["tags"]["pedido"] == r["X-Codigo-Pedido"]
    assert evento["tags"]["codigo_do_erro"] == r["X-Codigo-Erro"]
    assert evento["environment"] == "producao" and evento["release"] == "mindor@1.2.3"
    assert evento["tags"]["versao_00"]
    assert evento["user"] == {"id": str(ana.pk)}
    assert evento["exception"]["values"][-1]["type"] == "RuntimeError"


def test_nada_de_dado_pessoal_sai(sentry, ana):
    cliente(ana).get("/quebrada/?busca=ana@exemplo.com", HTTP_COOKIE="extra=biscoito-secreto")
    [evento] = sentry.eventos
    texto = sem_codigo_fonte(evento)
    for proibido in ("ana@exemplo.com", "Ana", "203.0.113.7", "biscoito-secreto", "sessionid", "Navegador de Teste",
                     "busca=", "abc123"):
        assert proibido not in texto, proibido
    assert evento["request"] == {"method": "GET", "url": "/quebrada/"}
    assert "breadcrumbs" not in evento or not evento["breadcrumbs"].get("values")
    for excecao in evento["exception"]["values"]:
        for quadro in excecao["stacktrace"]["frames"]:
            assert "vars" not in quadro
    assert "senha=[oculto]" in evento["exception"]["values"][-1]["value"]


def test_endereco_com_codigo_vai_so_pelo_modelo_da_tela(sentry, monkeypatch):
    from infra_vibecoding.login import views

    def quebra(*a, **k):
        raise RuntimeError("falhou")

    monkeypatch.setattr(views.DefinirSenhaRedefinir, "dispatch", quebra)
    cliente().get("/redefinir-senha/MQ/codigo-secreto-do-link/")
    [evento] = sentry.eventos
    assert "codigo-secreto-do-link" not in sem_codigo_fonte(evento)
    assert "{token}" in evento["request"]["url"]


def test_limpa_email_numeros_longos_e_segredos_da_mensagem():
    texto = monitor.limpar_texto(
        "Key (email)=(ana@exemplo.com) already exists; cpf 123.456.789-01; cnpj 12.345.678/0001-90; "
        "cartão 4111 1111 1111 1111; token=abc.def; em 2026-09-26 14:05; pedido 42")
    assert "ana@exemplo.com" not in texto and "123.456.789-01" not in texto and "0001-90" not in texto
    assert "4111" not in texto and "abc.def" not in texto
    assert "2026-09-26 14:05" in texto and "pedido 42" in texto  # datas e números curtos continuam


def test_sistema_nao_pode_afrouxar(sentry):
    assert "SEC.E132" not in [e.id for e in run_checks()]
    sentry_sdk.init(dsn=DSN, transport=SentryDeMentira(), send_default_pii=True)
    assert "SEC.E132" in [e.id for e in run_checks()]


def test_sem_sentry_a_checagem_passa():
    assert "SEC.E132" not in [e.id for e in run_checks()]


def test_link_na_tela_de_registros(settings):
    settings.SENTRY_PAINEL = "https://mindtopo.sentry.io/issues/?project=123"
    r = cliente().get("/quebrada/")
    chefe = Usuario.objects.create_superuser("chefe@exemplo.com", password=SENHA)
    c = Client()
    c.force_login(chefe)
    tela = c.get("/gestao-interna/infra_vibecoding/acesso/?tipo=erros").content.decode()
    link = f"https://mindtopo.sentry.io/issues/?project=123&amp;query=pedido%3A{r['X-Codigo-Pedido']}"
    assert link in tela and "ver no Sentry" in tela
    settings.SENTRY_PAINEL = ""
    assert "ver no Sentry" not in c.get("/gestao-interna/infra_vibecoding/acesso/?tipo=erros").content.decode()
    assert Acesso._base_manager.filter(tipo="erro").count() == 1


def test_opcoes_de_protecao_ligadas(sentry):
    opcoes = sentry_sdk.get_client().options
    assert opcoes["send_default_pii"] is False and opcoes["include_local_variables"] is False
    assert opcoes["max_request_body_size"] == "never" and opcoes["auto_session_tracking"] is False
    assert opcoes["enable_logs"] is False and opcoes["traces_sample_rate"] == 0


def test_trocar_o_filtro_de_envio_tambem_barra(sentry):
    opcoes = {**monitor.OPCOES_OBRIGATORIAS, "before_breadcrumb": monitor._sem_rastros}
    sentry_sdk.init(dsn=DSN, transport=SentryDeMentira(), before_send=lambda e, h: e, **opcoes)
    assert "SEC.E132" in [e.id for e in run_checks()]
