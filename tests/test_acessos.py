"""Testes do registro de acessos e da tela de Registros (US 6.2, D60)."""
import time

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from infra_vibecoding.acessos import consultar_registros, limpar_acessos_antigos, registrar_acesso
from infra_vibecoding.arquivos import anexar, compartilhar
from infra_vibecoding.dados import AcessoSemEscopo, EscritaSemAutorizacao
from infra_vibecoding.login import dois_fatores as df
from infra_vibecoding.models import Acesso, Historico
from tests.app_teste.models import Anexo, Pedido

pytestmark = pytest.mark.django_db
Usuario = get_user_model()
SENHA = "uma-senha-bem-longa-para-teste"
PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
NAVEGADOR = "Mozilla/5.0 (Macintosh) Teste"


def acessos(**filtros):
    return list(Acesso._base_manager.filter(**filtros).order_by("id"))


@pytest.fixture(autouse=True)
def cache_limpo():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def ana():
    return Usuario.objects.create_user("ana@exemplo.com", password=SENHA, nome="Ana")


@pytest.fixture
def beto():
    return Usuario.objects.create_user("beto@exemplo.com", password=SENHA, nome="Beto")


@pytest.fixture
def chefe():
    return Usuario.objects.create_superuser("chefe@exemplo.com", password=SENHA)


def navegador():
    return Client(HTTP_USER_AGENT=NAVEGADOR, REMOTE_ADDR="203.0.113.7")


def logado(usuario):
    c = navegador()
    c.force_login(usuario)
    Acesso._base_manager.all().delete()  # o force_login também registra "entrou": começa do zero
    return c


# 1. Entrar, errar, bloquear e sair
def test_entrar_registra_pessoa_endereco_navegador_tela_e_codigo(ana):
    r = navegador().post("/entrar/", {"username": "ana@exemplo.com", "password": SENHA})
    [linha] = acessos(tipo="entrou")
    assert linha.pessoa == "ana@exemplo.com" and linha.endereco == "203.0.113.7" and linha.navegador == NAVEGADOR
    assert linha.tela == "POST /entrar/" and linha.pedido == r["X-Codigo-Pedido"]


def test_senha_errada_registra_o_email_digitado_e_nunca_a_senha(ana):
    navegador().post("/entrar/", {"username": "Ana@Exemplo.com", "password": "senha-errada-secreta"})
    navegador().post("/entrar/", {"username": "ninguem@exemplo.com", "password": "outra-secreta"})
    assert [x.pessoa for x in acessos(tipo="senha_errada")] == ["ana@exemplo.com", "ninguem@exemplo.com"]
    for linha in acessos():
        texto = " ".join(str(getattr(linha, c.attname)) for c in Acesso._meta.concrete_fields)
        assert "secreta" not in texto


def test_bloqueio_registra_uma_vez(ana, settings, monkeypatch):
    settings.LIMITES_NOS_TESTES = True
    agora = time.time()
    monkeypatch.setattr(time, "time", lambda: agora)
    for _ in range(7):
        navegador().post("/entrar/", {"username": "ana@exemplo.com", "password": "errada"})
    [bloqueio] = acessos(tipo="bloqueado")
    assert bloqueio.pessoa == "ana@exemplo.com" and "senhas erradas demais" in bloqueio.detalhe
    assert len(acessos(tipo="senha_errada")) == 5  # depois do bloqueio, as tentativas nem chegam a conferir a senha


def test_limite_de_pedidos_registra_so_o_primeiro_de_cada_minuto(client, settings, monkeypatch):
    settings.LIMITES_NOS_TESTES = True
    settings.LIMITE_PEDIDOS_POR_ENDERECO = 3
    agora = time.time()
    monkeypatch.setattr(time, "time", lambda: agora)
    respostas = [client.get("/").status_code for _ in range(10)]
    assert respostas.count(429) == 7
    [linha] = acessos(tipo="bloqueado")
    assert "limite de pedidos" in linha.detalhe


def test_sair_registra(ana):
    c = navegador()
    c.post("/entrar/", {"username": "ana@exemplo.com", "password": SENHA})
    c.post("/sair/")
    assert [x.tipo for x in acessos()] == ["entrou", "saiu"] and acessos(tipo="saiu")[0].pessoa == "ana@exemplo.com"


# 2. Acesso negado
def test_acesso_negado_um_por_clique_com_o_detalhe_da_regra(ana):
    r = logado(ana).get("/aprovacoes/")
    assert r.status_code == 403
    [negado] = acessos(tipo="negado")
    assert negado.pessoa == "ana@exemplo.com" and negado.pedido == r["X-Codigo-Pedido"]


def test_negado_dentro_de_transacao_desfeita_continua_registrado(ana):
    r = logado(ana).get("/negado-em-transacao/")
    assert r.status_code == 403 and Pedido._base_manager.count() == 0  # a gravação da tela foi desfeita
    [negado] = acessos(tipo="negado")
    assert negado.detalhe == "aprovar em app_teste.Pedido"


def test_negado_fora_de_um_clique_grava_na_hora(ana, beto):
    p = Pedido(dono=ana, titulo="Cadeira")
    p.salvar(ana)
    p.titulo = "Mesa"
    with pytest.raises(Exception):
        p.salvar(beto)
    [negado] = acessos(tipo="negado")
    assert negado.pessoa == "beto@exemplo.com" and negado.detalhe == "editar em app_teste.Pedido" and negado.pedido == ""


# 3. Verificação em duas etapas, senha e links
def test_dois_fatores_ligar_desligar_e_codigo_errado(ana):
    chave = df.nova_chave_do_app()
    df.ligar(ana, df.APP, chave=chave)
    c = navegador()
    c.post("/entrar/", {"username": "ana@exemplo.com", "password": SENHA})
    c.post("/entrar/codigo/", {"codigo": "000000"})
    df.desligar(ana, "2fa: ana@exemplo.com desligou")
    detalhes = [x.detalhe for x in acessos(tipo="dois_fatores")]
    assert detalhes[0] == "ligou (app autenticador)"
    assert detalhes[1] == "código errado ao entrar"
    assert detalhes[2].startswith("desligou")
    assert acessos(tipo="entrou") == []  # a senha estava certa, mas sem o código não entrou


def test_trocar_senha_e_link_de_acesso(ana):
    c = logado(ana)
    c.post("/trocar-senha/", {"old_password": SENHA, "new_password1": "nova-senha-bem-longa-9",
                              "new_password2": "nova-senha-bem-longa-9"})
    navegador().post("/esqueci-a-senha/", {"email": "ana@exemplo.com"})
    assert acessos(tipo="senha")[0].detalhe == "trocou a própria senha"
    [link] = acessos(tipo="link")
    assert link.pessoa == "ana@exemplo.com" and link.detalhe == "redefinição de senha"


# 4. Downloads
def test_download_de_arquivo_privado_e_negado_para_quem_nao_ve(ana, beto, settings, tmp_path):
    settings.ARQUIVOS_PASTA = tmp_path
    p = Pedido(dono=ana, titulo="Cadeira")
    p.salvar(ana)
    a = Anexo(pedido=p)
    anexar(a, "arquivo", SimpleUploadedFile("proposta.pdf", PDF))
    a.salvar(ana)
    assert logado(ana).get(f"/arquivos/{a.arquivo}/").status_code == 200
    [download] = acessos(tipo="download")
    assert download.pessoa == "ana@exemplo.com" and download.detalhe.startswith("proposta.pdf de app_teste.Anexo")
    assert logado(beto).get(f"/arquivos/{a.arquivo}/").status_code == 404
    [negado] = acessos(tipo="negado")
    assert negado.pessoa == "beto@exemplo.com"


def test_download_por_link_de_compartilhamento(ana, settings, tmp_path):
    settings.ARQUIVOS_PASTA = tmp_path
    p = Pedido(dono=ana, titulo="Cadeira")
    p.salvar(ana)
    a = Anexo(pedido=p)
    anexar(a, "arquivo", SimpleUploadedFile("proposta.pdf", PDF))
    a.salvar(ana)
    _, url = compartilhar(ana, a, "arquivo")
    navegador().get(url)
    navegador().get("/c/inventado/")
    [download] = acessos(tipo="download")
    assert download.pessoa == "" and "criado por ana@exemplo.com" in download.detalhe
    assert "inválido" in acessos(tipo="negado")[0].detalhe


# 5. Tela de banco, planilha e erros
def test_entrada_na_tela_de_banco_uma_vez_por_login_e_planilha(chefe, ana):
    c = logado(chefe)
    c.get("/gestao-interna/")
    c.get("/gestao-interna/app_teste/pedido/")
    c.get("/gestao-interna/app_teste/pedido/exportar/csv/")
    assert len(acessos(tipo="tela_de_banco")) == 1
    [planilha] = acessos(tipo="planilha")
    assert planilha.pessoa == "chefe@exemplo.com" and planilha.detalhe.startswith("exportou")


def sem_estourar():
    return Client(raise_request_exception=False)


def test_erro_interno_registra_o_codigo_do_erro():
    r = sem_estourar().get("/quebrada/")
    [erro] = acessos(tipo="erro")
    assert erro.detalhe == r["X-Codigo-Erro"] and erro.pedido == r["X-Codigo-Pedido"] and erro.tela == "GET /quebrada/"


def test_navegacao_comum_e_pagina_que_nao_existe_nao_entram(ana):
    c = logado(ana)
    c.get("/painel/")
    c.get("/nao-existe/")
    assert acessos() == []


def test_se_o_registro_falhar_a_tela_segue(ana, monkeypatch, caplog):
    def quebra(*a, **k):
        raise RuntimeError("banco fora")

    monkeypatch.setattr(Acesso._base_manager, "bulk_create", quebra)
    r = navegador().post("/entrar/", {"username": "ana@exemplo.com", "password": SENHA})
    assert r.status_code == 302 and "não foi possível gravar" in caplog.text


# 6. Ninguém mexe; limpeza de um ano
def test_registro_de_acessos_nao_se_altera_nem_se_apaga_um_a_um(ana):
    linha = registrar_acesso("download", "teste", pessoa="ana@exemplo.com")
    linha = Acesso._base_manager.get(pk=linha.pk)
    with pytest.raises(PermissionError):
        linha.save()
    with pytest.raises(PermissionError):
        linha.delete()
    with pytest.raises(EscritaSemAutorizacao):
        Acesso.objects.como_sistema("tentativa").delete()
    with pytest.raises(EscritaSemAutorizacao):
        Acesso.objects.como_sistema("tentativa").update(pessoa="outra")
    with pytest.raises(AcessoSemEscopo):
        list(Acesso.objects.all())
    assert Acesso.objects.para(ana).count() == 0


def test_limpeza_apaga_so_o_que_passou_de_um_ano(ana, capsys):
    velho = registrar_acesso("download", "velho", pessoa="ana@exemplo.com")
    limite = registrar_acesso("download", "364 dias", pessoa="ana@exemplo.com")
    novo = registrar_acesso("download", "novo", pessoa="ana@exemplo.com")
    agora = timezone.now()
    Acesso._base_manager.filter(pk=velho.pk).update(quando=agora - timezone.timedelta(days=366))
    Acesso._base_manager.filter(pk=limite.pk).update(quando=agora - timezone.timedelta(days=364))
    Historico._base_manager.update(quando=agora - timezone.timedelta(days=4000))
    assert limpar_acessos_antigos() == 1
    assert {x.detalhe for x in acessos()} == {"364 dias", "novo"}
    assert Historico._base_manager.count() >= 1  # o histórico dos registros fica para sempre
    Acesso._base_manager.filter(pk=novo.pk).update(quando=agora - timezone.timedelta(days=400))
    call_command("limpar_registros")
    assert "1 linha(s)" in capsys.readouterr().out and {x.detalhe for x in acessos()} == {"364 dias"}


# 7. Tela de Registros
def tabela(resposta):
    """Só as linhas da lista (os nomes dos tipos também aparecem no filtro)."""
    texto = resposta.content.decode()
    return texto.split("<tbody>")[1].split("</tbody>")[0] if "<tbody>" in texto else ""


def test_tela_de_registros_junta_dados_acessos_e_erros(chefe, ana):
    c = logado(chefe)
    Pedido(dono=ana, titulo="Cadeira").salvar(ana)
    erro = sem_estourar().get("/quebrada/")
    navegador().post("/entrar/", {"username": "ana@exemplo.com", "password": "errada"})
    url = "/gestao-interna/infra_vibecoding/acesso/"
    tudo = tabela(c.get(url))
    assert "app_teste.Pedido" in tudo and "senha errada" in tudo and erro["X-Codigo-Erro"] in tudo
    so_erros = tabela(c.get(url + "?tipo=erros"))
    assert erro["X-Codigo-Erro"] in so_erros and "app_teste.Pedido" not in so_erros
    pelo_codigo = c.get(url + "?pedido=" + erro["X-Codigo-Erro"].lower()).content.decode()
    assert "1 registro(s)" in pelo_codigo
    por_tabela = tabela(c.get(url + "?tabela=pedido"))
    assert "app_teste.Pedido" in por_tabela and "senha errada" not in por_tabela
    por_pessoa = tabela(c.get(url + "?pessoa=ana@"))
    assert "senha errada" in por_pessoa and "erro interno" not in por_pessoa
    assert "Nenhum registro" in c.get(url + "?de=2000-01-01&ate=2000-01-02").content.decode()


def test_tela_de_registros_pagina_de_100_em_100(chefe):
    c = logado(chefe)
    for i in range(130):
        registrar_acesso("download", f"arquivo {i}", pessoa="ana@exemplo.com")
    url = "/gestao-interna/infra_vibecoding/acesso/?tipo=acessos:download"
    tela = c.get(url).content.decode()
    assert "130 registro(s), mostrando 1 a 100" in tela and "arquivo 129" in tela and "arquivo 29<" not in tela
    segunda = c.get(url + "&inicio=100").content.decode()
    assert "mostrando 101 a 130" in segunda and "arquivo 0<" in segunda


def test_so_superusuario_ve_os_registros(ana):
    ana.is_staff = True
    ana.salvar_como_sistema("teste: da tela de banco, mas não superusuário")
    assert logado(ana).get("/gestao-interna/infra_vibecoding/acesso/").status_code == 403
    assert Client().get("/gestao-interna/infra_vibecoding/acesso/").status_code == 302


def test_detalhe_de_um_acesso_so_le(chefe):
    c = logado(chefe)
    linha = registrar_acesso("download", "teste", pessoa="ana@exemplo.com")
    url = f"/gestao-interna/infra_vibecoding/acesso/{linha.pk}/change/"
    assert "teste" in c.get(url).content.decode()
    assert c.post(f"/gestao-interna/infra_vibecoding/acesso/{linha.pk}/delete/", {"post": "yes"}).status_code == 403
    assert Acesso._base_manager.filter(pk=linha.pk).exists()


def test_consulta_direta_filtra_pelo_codigo_do_erro():
    r = sem_estourar().get("/quebrada/")
    linhas, total = consultar_registros(pedido=r["X-Codigo-Erro"])
    assert total == 1 and linhas[0]["r_origem"] == "erros"


def test_registro_de_entrar_e_sair_ligado_desde_o_inicio_do_sistema():
    import os
    import subprocess
    import sys

    codigo = ("import django; django.setup(); from django.contrib.auth.signals import user_logged_in, user_logged_out; "
              "print(any(r[0][0] == 'infra_vibecoding.acessos.entrou' for r in user_logged_in.receivers), "
              "any(r[0][0] == 'infra_vibecoding.acessos.saiu' for r in user_logged_out.receivers))")
    ambiente = {**os.environ, "DJANGO_SETTINGS_MODULE": "tests.settings"}
    saida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, env=ambiente,
                           cwd=os.path.dirname(os.path.dirname(__file__)), check=True)
    assert saida.stdout.strip().endswith("True True")
