"""Testes do campo de arquivo público e do link de compartilhamento (US 4.2, D58)."""
import io
import re

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone
from PIL import Image

from infra_vibecoding.arquivos import CampoArquivo, anexar, arquivo_de, compartilhar
from infra_vibecoding.dados import AcessoSemEscopo, SemPermissao
from infra_vibecoding.models import ArquivoGuardado, LinkDeCompartilhamento
from tests.app_teste.models import Anexo, Pedido
from tests.app_teste.politicas import PoliticaAnexo

pytestmark = pytest.mark.django_db
Usuario = get_user_model()
SENHA = "uma-senha-bem-longa-para-teste"
PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


@pytest.fixture(autouse=True)
def pasta(settings, tmp_path):
    settings.ARQUIVOS_PASTA = tmp_path / "arquivos_privados"


@pytest.fixture
def ana():
    return Usuario.objects.create_user("ana@exemplo.com", password=SENHA, nome="Ana")


@pytest.fixture
def beto():
    return Usuario.objects.create_user("beto@exemplo.com", password=SENHA, nome="Beto")


def png():
    saida = io.BytesIO()
    Image.new("RGB", (20, 20), (0, 90, 200)).save(saida, format="PNG")
    return saida.getvalue()


@pytest.fixture
def anexo(ana):
    pedido = Pedido(dono=ana, titulo="Cadeira")
    pedido.salvar_como_sistema("teste")
    a = Anexo(pedido=pedido)
    anexar(a, "arquivo", SimpleUploadedFile("proposta.pdf", PDF))
    a.salvar(ana)
    return a


def logado(usuario):
    c = Client()
    c.force_login(usuario)
    return c


def codigo_de(url):
    return re.search(r"/c/([^/]+)/", url).group(1)


# 1. Campo público
def test_campo_publico_precisa_de_motivo():
    with pytest.raises(ImproperlyConfigured):
        CampoArquivo(publico=True)
    with pytest.raises(ImproperlyConfigured):
        CampoArquivo(publico="vitrine")  # motivo curto demais
    assert CampoArquivo(publico="foto do produto na vitrine pública").publico


def test_arquivo_publico_abre_sem_login(ana, anexo, django_capture_on_commit_callbacks):
    anexar(anexo, "foto_publica", SimpleUploadedFile("foto.png", png()))
    anexo.salvar(ana)
    ref = arquivo_de(anexo, "foto_publica")
    assert ref.publico and ref.url == f"/arquivos/publico/{ref.id}/"
    r = Client().get(ref.url)
    assert r.status_code == 200 and "public" in r["Cache-Control"] and r["X-Content-Type-Options"] == "nosniff"
    velho = ref.url
    with django_capture_on_commit_callbacks(execute=True):
        anexar(anexo, "foto_publica", SimpleUploadedFile("nova.png", png()))
        anexo.salvar(ana)
    assert Client().get(velho).status_code == 404  # trocou: o endereço antigo morre


def test_arquivo_privado_nao_abre_pelo_endereco_publico(anexo):
    assert Client().get(f"/arquivos/publico/{anexo.arquivo}/").status_code == 404
    assert arquivo_de(anexo, "arquivo").url == f"/arquivos/{anexo.arquivo}/"


def test_arquivo_enviado_quando_o_campo_era_privado_continua_privado(ana, anexo, monkeypatch):
    campo = Anexo._meta.get_field("foto_publica")
    monkeypatch.setattr(campo, "publico", None)  # como se o campo ainda fosse privado
    anexar(anexo, "foto_publica", SimpleUploadedFile("antiga.png", png()))
    anexo.salvar(ana)
    monkeypatch.undo()  # agora o código diz que o campo é público
    assert Client().get(f"/arquivos/publico/{anexo.foto_publica}/").status_code == 404
    assert not ArquivoGuardado._base_manager.get(pk=anexo.foto_publica).publico


# 2. Link de compartilhamento
def test_quem_recebe_baixa_sem_login_e_conta_download(ana, anexo, caplog):
    link, url = compartilhar(ana, anexo, "arquivo", dias=7)
    assert (link.vence_em - timezone.now()).days in (6, 7)
    r = Client().get(url)
    assert r.status_code == 200 and b"".join(r.streaming_content) == PDF
    assert r["X-Robots-Tag"] == "noindex" and "no-store" in r["Cache-Control"]
    Client().get(url)
    link.refresh_from_db()
    assert link.downloads == 2 and link.ultimo_download_em is not None
    assert "baixado por link de compartilhamento criado por ana@exemplo.com" in caplog.text


def test_o_codigo_do_link_nao_fica_no_banco(ana, anexo):
    link, url = compartilhar(ana, anexo, "arquivo")
    codigo = codigo_de(url)
    assert len(codigo) >= 40 and codigo not in link.resumo


def test_quem_nao_ve_o_registro_nao_compartilha(beto, anexo, caplog):
    with pytest.raises(SemPermissao):
        compartilhar(beto, anexo, "arquivo")
    assert logado(beto).get(f"/arquivos/{anexo.arquivo}/compartilhar/").status_code == 404
    assert "tentou compartilhar sem permissão" in caplog.text


def test_regra_liberando_nao_basta_precisa_ver_o_registro(beto, anexo, monkeypatch):
    original = PoliticaAnexo.pode
    monkeypatch.setattr(PoliticaAnexo, "pode",
                        lambda self, u, acao, obj=None: True if acao == "compartilhar" else original(self, u, acao, obj))
    with pytest.raises(SemPermissao):
        compartilhar(beto, anexo, "arquivo")


def test_fechado_por_padrao_sem_a_regra_ninguem_compartilha(ana, anexo, monkeypatch):
    original = PoliticaAnexo.pode
    monkeypatch.setattr(PoliticaAnexo, "pode",
                        lambda self, u, acao, obj=None: False if acao == "compartilhar" else original(self, u, acao, obj))
    with pytest.raises(SemPermissao):
        compartilhar(ana, anexo, "arquivo")
    assert logado(ana).get(f"/arquivos/{anexo.arquivo}/compartilhar/").status_code == 404


def test_prazo_de_1_a_30_dias(ana, anexo):
    with pytest.raises(ValidationError):
        compartilhar(ana, anexo, "arquivo", dias=31)
    with pytest.raises(ValidationError):
        compartilhar(ana, anexo, "arquivo", dias=0)
    link, _ = compartilhar(ana, anexo, "arquivo", dias=30)
    assert (link.vence_em - timezone.now()).days in (29, 30)


def test_link_vencido_cancelado_ou_arquivo_trocado_nao_abre(ana, anexo, django_capture_on_commit_callbacks):
    vencido, url_vencido = compartilhar(ana, anexo, "arquivo")
    vencido.vence_em = timezone.now() - timezone.timedelta(minutes=1)
    vencido.salvar_como_sistema("teste", update_fields=["vence_em"])
    r = Client().get(url_vencido)
    assert r.status_code == 410 and "Link indisponível" in r.content.decode()

    cancelado, url_cancelado = compartilhar(ana, anexo, "arquivo")
    from infra_vibecoding.arquivos import cancelar_compartilhamento

    cancelar_compartilhamento(ana, cancelado)
    assert Client().get(url_cancelado).status_code == 410

    _, url = compartilhar(ana, anexo, "arquivo")
    with django_capture_on_commit_callbacks(execute=True):
        anexar(anexo, "arquivo", SimpleUploadedFile("nova.pdf", PDF + b"%"))
        anexo.salvar(ana)
    assert Client().get(url).status_code == 410


def test_registro_excluido_derruba_o_link(ana, anexo, django_capture_on_commit_callbacks):
    _, url = compartilhar(ana, anexo, "arquivo")
    with django_capture_on_commit_callbacks(execute=True):
        anexo.excluir(ana)
    assert Client().get(url).status_code == 410
    assert LinkDeCompartilhamento._base_manager.count() == 0


def test_codigo_inventado(client):
    assert client.get("/c/inventado123/").status_code == 410


def test_ninguem_lista_links_direto():
    with pytest.raises(AcessoSemEscopo):
        list(LinkDeCompartilhamento.objects.all())


# 3. Tela pronta de compartilhar
def test_tela_de_compartilhar(ana, anexo):
    c = logado(ana)
    url = f"/arquivos/{anexo.arquivo}/compartilhar/"
    tela = c.get(url).content.decode()
    assert 'Compartilhar "proposta.pdf"' in tela and "Nenhum link ativo." in tela
    r = c.post(url, {"dias": "3"})
    assert r.status_code == 302  # volta por GET: recarregar a página não cria outro link
    tela = c.get(url).content.decode()
    novo = re.search(r'value="(http://testserver/c/[^"]+)"', tela).group(1)
    assert "Copie agora" in tela and Client().get(novo).status_code == 200
    link = LinkDeCompartilhamento._base_manager.get()
    assert (link.vence_em - timezone.now()).days in (2, 3)
    segunda_vez = c.get(url).content.decode()
    assert "Copie agora" not in segunda_vez  # o link aparece uma vez só
    assert f'name="cancelar" value="{link.pk}"' in segunda_vez
    c.post(url, {"cancelar": str(link.pk)})
    assert Client().get(novo).status_code == 410
    assert "Nenhum link ativo." in c.get(url).content.decode()


def test_tela_recusa_prazo_fora_do_limite(ana, anexo):
    r = logado(ana).post(f"/arquivos/{anexo.arquivo}/compartilhar/", {"dias": "90"}, follow=True)
    assert "O prazo vai de 1 a 30 dias." in r.content.decode()
    assert LinkDeCompartilhamento._base_manager.count() == 0


def test_url_de_compartilhar_no_template(anexo):
    assert arquivo_de(anexo, "arquivo").url_compartilhar == f"/arquivos/{anexo.arquivo}/compartilhar/"


# 4. Tela de banco
def test_tela_de_banco_lista_e_cancela_links(ana, anexo):
    _, url = compartilhar(ana, anexo, "arquivo")
    link = LinkDeCompartilhamento._base_manager.get()
    chefe = Usuario.objects.create_superuser("chefe@exemplo.com", password=SENHA)
    c = logado(chefe)
    lista = "/gestao-interna/infra_vibecoding/linkdecompartilhamento/"
    tela = c.get(lista).content.decode()
    assert "proposta.pdf" in tela and "Ativo" in tela
    assert "linkdecompartilhamento/add/" not in tela and "Exportar CSV" not in tela
    assert c.get(lista + "exportar/csv/").status_code == 404
    c.post(lista, {"action": "cancelar_links", "_selected_action": [str(link.pk)]})
    assert Client().get(url).status_code == 410
