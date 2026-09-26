"""Testes dos arquivos privados (US 4.1, D55): envio conferido pelo conteúdo, download só para quem vê o registro,
GPS apagado das fotos, limpeza ao trocar e excluir, limites do sistema e travas."""
import io
import logging

import pytest
from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.uploadhandler import StopUpload
from django.template import Context, Template
from django.test import Client
from PIL import Image

from infra_vibecoding import arquivos
from infra_vibecoding.arquivos import CampoArquivo, anexar, arquivo_de, salvar_formulario
from infra_vibecoding.checagens import sec12_arquivos
from infra_vibecoding.dados import AcessoSemEscopo
from infra_vibecoding.models import ArquivoGuardado
from tests.app_teste.models import Anexo, Pedido

pytestmark = pytest.mark.django_db
Usuario = get_user_model()
SENHA = "uma-senha-bem-longa-para-teste"
PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


@pytest.fixture(autouse=True)
def pasta(settings, tmp_path):
    settings.ARQUIVOS_PASTA = tmp_path / "arquivos_privados"
    return settings.ARQUIVOS_PASTA


@pytest.fixture
def ana():
    return Usuario.objects.create_user("ana@exemplo.com", password=SENHA, nome="Ana")


@pytest.fixture
def beto():
    return Usuario.objects.create_user("beto@exemplo.com", password=SENHA, nome="Beto")


@pytest.fixture
def pedido(ana):
    p = Pedido(dono=ana, titulo="Cadeira")
    p.salvar_como_sistema("teste")
    return p


class FormAnexo(forms.ModelForm):
    class Meta:
        model = Anexo
        fields = ["arquivo", "comprovante"]


def imagem(formato="PNG", gps=False, tamanho=(40, 30)):
    img = Image.new("RGB", tamanho, (200, 30, 30))
    saida = io.BytesIO()
    extras = {}
    if gps:
        exif = Image.Exif()
        exif[0x010F] = "Fabricante"                       # marca da câmera: continua
        exif[0x8825] = {1: "S", 2: (23.0, 33.0, 0.0), 3: "W", 4: (46.0, 38.0, 0.0)}  # GPS: sai
        extras["exif"] = exif.tobytes()
    img.save(saida, format=formato, **extras)
    return saida.getvalue()


def enviar(usuario, pedido, conteudo, nome="print.png", campo="arquivo", instancia=None):
    form = FormAnexo(data={}, files={campo: SimpleUploadedFile(nome, conteudo)},
                     instance=instancia or Anexo(pedido=pedido))
    if campo != "arquivo" and instancia is None:
        form = FormAnexo(data={}, files={"arquivo": SimpleUploadedFile("p.png", imagem()),
                                         campo: SimpleUploadedFile(nome, conteudo)},
                         instance=Anexo(pedido=pedido))
    return form, salvar_formulario(form, usuario)


def guardado_de(anexo, campo="arquivo"):
    return ArquivoGuardado._base_manager.get(pk=getattr(anexo, campo))


# 1. Enviar e baixar
def test_envia_guarda_com_nome_aleatorio_e_registra(ana, pedido, pasta, caplog):
    form, anexo = enviar(ana, pedido, imagem(), "Print da tela.png")
    assert anexo is not None, form.errors
    g = guardado_de(anexo)
    assert g.nome == "Print da tela.png" and g.tipo == "image/png" and g.enviado_por == "ana@exemplo.com"
    assert g.modelo == "app_teste.Anexo" and g.registro == str(anexo.pk) and g.campo == "arquivo"
    guardados = [p for p in pasta.rglob("*") if p.is_file()]
    assert len(guardados) == 1 and "Print" not in guardados[0].name and guardados[0].suffix == ".png"
    assert "arquivos: ana@exemplo.com enviou Print da tela.png" in caplog.text


def test_dono_baixa(client, ana, pedido):
    conteudo = imagem()
    _, anexo = enviar(ana, pedido, conteudo)
    client.force_login(ana)
    r = client.get(arquivo_de(anexo, "arquivo").url)
    assert r.status_code == 200 and b"".join(r.streaming_content) == conteudo
    assert r["Content-Type"] == "image/png" and r["X-Content-Type-Options"] == "nosniff"
    assert r["Content-Security-Policy"].startswith("sandbox") and "no-store" in r["Cache-Control"]


def test_link_vazado_nao_abre_para_quem_nao_ve_o_registro(client, ana, beto, pedido, caplog):
    _, anexo = enviar(ana, pedido, imagem())
    url = arquivo_de(anexo, "arquivo").url
    client.force_login(beto)
    assert client.get(url).status_code == 404
    assert "beto@exemplo.com tentou baixar o arquivo" in caplog.text


def test_visitante_vai_para_o_login(client, ana, pedido):
    _, anexo = enviar(ana, pedido, imagem())
    r = client.get(arquivo_de(anexo, "arquivo").url)
    assert r.status_code == 302 and "/entrar/" in r["Location"]


def test_tela_de_banco_baixa(client, ana, pedido, caplog):
    _, anexo = enviar(ana, pedido, imagem())
    chefe = Usuario.objects.create_superuser("chefe@exemplo.com", password=SENHA)
    client.force_login(chefe)
    assert client.get(arquivo_de(anexo, "arquivo").url).status_code == 200
    assert "(tela de banco)" in caplog.text


def test_arquivo_que_nao_existe(client, ana):
    client.force_login(ana)
    assert client.get("/arquivos/2b7f9a64-1b6e-4c4e-9d0e-6b1c7a1f0c11/").status_code == 404


def test_pdf_e_outros_tipos_saem_como_download(client, ana, pedido):
    _, anexo = enviar(ana, pedido, PDF, "nota.pdf")
    client.force_login(ana)
    r = client.get(arquivo_de(anexo, "arquivo").url)
    assert r["Content-Type"] == "application/pdf" and "inline" in r["Content-Disposition"]


# 2. Conferência no envio
@pytest.mark.parametrize("conteudo,nome", [
    (b"MZ\x90\x00\x03\x00\x00\x00\x04\x00programa", "foto.png"),
    (b"<html><script>alert(1)</script></html>", "foto.png"),
    (b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "imagem.svg"),
    (b"\x7fELF\x02\x01\x01\x00\x00\x00", "nota.pdf"),
])
def test_tipos_perigosos_sao_recusados(ana, pedido, conteudo, nome):
    form, anexo = enviar(ana, pedido, conteudo, nome)
    assert anexo is None and "Tipo de arquivo não aceito." in str(form.errors)
    assert ArquivoGuardado._base_manager.count() == 0


def test_tipo_certo_mas_nao_aceito_pelo_campo(ana, pedido):
    form, anexo = enviar(ana, pedido, imagem(), "foto.png", campo="comprovante")
    assert anexo is None and "Este campo aceita só: pdf" in str(form.errors)


def test_tamanho_do_campo(ana, pedido):
    form, anexo = enviar(ana, pedido, PDF + b"0" * (1024 * 1024), "grande.pdf")
    assert anexo is None and "Arquivo maior que 1 MB." in str(form.errors)


def test_imagem_corrompida(ana, pedido):
    form, anexo = enviar(ana, pedido, b"\x89PNG\r\n\x1a\n" + b"lixo" * 50, "foto.png")
    assert anexo is None and "corrompida" in str(form.errors)


def test_gps_da_foto_e_apagado(ana, pedido, pasta):
    original = imagem("JPEG", gps=True)
    assert 0x8825 in Image.open(io.BytesIO(original)).getexif()
    _, anexo = enviar(ana, pedido, original, "foto.jpg")
    guardado = next(p for p in pasta.rglob("*.jpg"))
    exif = Image.open(guardado).getexif()
    assert 0x8825 not in exif and exif[0x010F] == "Fabricante"


# 3. Trocar, remover, excluir
def test_trocar_apaga_o_antigo(ana, pedido, pasta, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        _, anexo = enviar(ana, pedido, imagem(), "um.png")
    velho = guardado_de(anexo)
    with django_capture_on_commit_callbacks(execute=True):
        _, anexo = enviar(ana, pedido, PDF, "dois.pdf", instancia=anexo)
    assert anexo is not None
    assert not ArquivoGuardado._base_manager.filter(pk=velho.pk).exists()
    assert [p.suffix for p in pasta.rglob("*") if p.is_file()] == [".pdf"]


def test_limpar_o_campo_remove(ana, pedido, pasta, django_capture_on_commit_callbacks):
    form = FormAnexo(data={}, files={"arquivo": SimpleUploadedFile("p.png", imagem()),
                                     "comprovante": SimpleUploadedFile("c.pdf", PDF)},
                     instance=Anexo(pedido=pedido))
    anexo = salvar_formulario(form, ana)
    with django_capture_on_commit_callbacks(execute=True):
        anexar(anexo, "comprovante", None)
        anexo.salvar(ana)
    assert anexo.comprovante is None and ArquivoGuardado._base_manager.count() == 1
    assert [p.suffix for p in pasta.rglob("*") if p.is_file()] == [".png"]


def test_excluir_o_registro_apaga_os_arquivos(ana, pedido, pasta, django_capture_on_commit_callbacks):
    _, anexo = enviar(ana, pedido, imagem())
    with django_capture_on_commit_callbacks(execute=True):
        anexo.excluir(ana)
    assert ArquivoGuardado._base_manager.count() == 0
    assert [p for p in pasta.rglob("*") if p.is_file()] == []


def test_excluir_o_pai_em_cascata_apaga_os_arquivos(ana, pedido, pasta, django_capture_on_commit_callbacks):
    enviar(ana, pedido, imagem())
    with django_capture_on_commit_callbacks(execute=True):
        pedido.excluir_como_sistema("teste")
    assert ArquivoGuardado._base_manager.count() == 0 and [p for p in pasta.rglob("*") if p.is_file()] == []


# 4. Limites do sistema (plano) e cota
def test_limite_por_pessoa_e_cota_do_espaco(settings, ana, pedido):
    settings.ARQUIVOS_LIMITES = "tests.app_teste.regras.limites_de_arquivo"
    ana.nome = "Plano pequeno"
    ana.salvar_como_sistema("teste")
    assert len(PDF * 13) > 1000 >= len(PDF * 12)
    form, anexo = enviar(ana, pedido, PDF * 13, "grande.pdf")
    assert anexo is None and "maior que o permitido" in str(form.errors)
    for i in range(3):
        _, anexo = enviar(ana, pedido, PDF * 12, f"n{i}.pdf")
        assert anexo is not None
    form, anexo = enviar(ana, pedido, PDF * 12, "cheio.pdf")
    assert anexo is None and "espaço de arquivos está cheio" in str(form.errors)
    assert ArquivoGuardado._base_manager.filter(espaco=f"dono-{ana.pk}").count() == 3


# 5. Travas
def test_ninguem_lista_os_arquivos_direto():
    with pytest.raises(AcessoSemEscopo):
        list(ArquivoGuardado.objects.all())


def test_campo_com_tamanho_acima_do_teto_ou_tipo_desconhecido():
    with pytest.raises(ImproperlyConfigured):
        CampoArquivo(tamanho_max_mb=500)
    with pytest.raises(ImproperlyConfigured):
        CampoArquivo(tipos=["executavel"])


def test_envio_gigante_e_cortado_na_chegada():
    manipulador = arquivos.LimiteDeEnvio()
    assert manipulador.receive_data_chunk(b"x" * 10, 0) == b"x" * 10
    with pytest.raises(StopUpload):
        manipulador.receive_data_chunk(b"x" * 10, arquivos.TETO_MB * 1024 * 1024 + 1024 * 1024)


def test_checagens(settings):
    assert sec12_arquivos() == []
    settings.FILE_UPLOAD_HANDLERS = ["django.core.files.uploadhandler.TemporaryFileUploadHandler"]
    settings.ARQUIVOS_LIMITES = "tests.app_teste.regras.nao_existe"
    assert [e.id for e in sec12_arquivos()] == ["SEC.E121", "SEC.E122"]


# 6. Template, tela de banco e planilha
def test_filtro_do_template(ana, pedido):
    _, anexo = enviar(ana, pedido, imagem(), "Print.png")
    html = Template('{% load arquivos %}{% with a=anexo|arquivo:"arquivo" %}{{ a.nome }} {{ a.url }} '
                    '{{ a.eh_imagem }}{% endwith %}').render(Context({"anexo": anexo}))
    assert html == f"Print.png /arquivos/{anexo.arquivo}/ True"


def test_envio_pela_tela_de_banco(client, ana, pedido):
    chefe = Usuario.objects.create_superuser("chefe@exemplo.com", password=SENHA)
    client.force_login(chefe)
    r = client.post("/gestao-interna/app_teste/anexo/add/", {
        "pedido": pedido.pk, "arquivo": SimpleUploadedFile("p.pdf", PDF)})
    assert r.status_code == 302, r.content.decode()[:2000]
    anexo = Anexo.objects.como_sistema("teste").get()
    assert guardado_de(anexo).enviado_por.startswith("sistema (admin: chefe@exemplo.com")
    tela = client.get(f"/gestao-interna/app_teste/anexo/{anexo.pk}/change/").content.decode()
    assert f"/arquivos/{anexo.arquivo}/" in tela and "p.pdf" in tela


def test_campo_de_arquivo_nao_entra_por_planilha(client, ana, pedido):
    from infra_vibecoding.planilhas import mapear_colunas

    _, ignoradas = mapear_colunas(Anexo, ["pedido", "arquivo"])
    assert ignoradas == [("arquivo", "não é importado por segurança")]
