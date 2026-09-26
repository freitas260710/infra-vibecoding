"""Testes do histórico automático e do código do pedido (US 6.1, D36 e D60)."""
import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.checks import run_checks
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from infra_vibecoding import historico
from infra_vibecoding.arquivos import anexar, compartilhar
from infra_vibecoding.dados import AcessoSemEscopo, EscritaSemAutorizacao
from infra_vibecoding.historico import historico_de, historico_url, registrar_acao
from infra_vibecoding.models import Historico
from tests.app_teste.models import Anexo, ItemPedido, Pedido, Setor

pytestmark = pytest.mark.django_db
Usuario = get_user_model()
SENHA = "uma-senha-bem-longa-para-teste"
PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


def linhas(obj=None, **filtros):
    qs = Historico._base_manager.all()
    if obj is not None:
        qs = qs.filter(tabela=obj._meta.label, registro=str(obj.pk))
    return list(qs.filter(**filtros).order_by("id"))


@pytest.fixture
def ana():
    return Usuario.objects.create_user("ana@exemplo.com", password=SENHA, nome="Ana")


@pytest.fixture
def beto():
    return Usuario.objects.create_user("beto@exemplo.com", password=SENHA, nome="Beto")


@pytest.fixture
def pedido(ana):
    p = Pedido(dono=ana, titulo="Cadeira", valor="10.00")
    p.salvar(ana)
    return p


def logado(usuario):
    c = Client()
    c.force_login(usuario)
    return c


# 1. Criar, alterar e excluir, pelo usuário
def test_criar_registra_quem_e_os_valores(ana, pedido):
    [linha] = linhas(pedido)
    assert linha.acao == "criou" and linha.autor == "ana@exemplo.com" and not linha.como_sistema
    assert linha.tabela == "app_teste.Pedido" and linha.rotulo == str(pedido)
    assert linha.mudancas["titulo"] == {"nome": "titulo", "antes": None, "depois": "Cadeira"}
    assert linha.mudancas["dono"]["depois"] == f"ana@exemplo.com (id {ana.pk})"
    assert linha.mudancas["valor"]["depois"] == "10.00"
    assert "id" not in linha.mudancas  # o id já está na coluna do registro


def test_alterar_registra_so_o_que_mudou_com_antes_e_depois(ana, pedido):
    pedido.titulo = "Mesa"
    pedido.salvar(ana)
    alterou = linhas(pedido, acao="alterou")
    assert len(alterou) == 1
    assert alterou[0].mudancas == {"titulo": {"nome": "titulo", "antes": "Cadeira", "depois": "Mesa"}}
    pedido.salvar(ana)  # nada mudou: nada entra
    assert len(linhas(pedido, acao="alterou")) == 1


def test_gravar_so_alguns_campos_registra_so_esses(ana, pedido):
    pedido.titulo = "Mesa"
    pedido.valor = "99.00"  # mudou na memória, mas não vai ser gravado
    pedido.salvar(ana, update_fields=["titulo"])
    [alterou] = linhas(pedido, acao="alterou")
    assert set(alterou.mudancas) == {"titulo"}
    pedido.refresh_from_db()
    assert str(pedido.valor) == "10.00"


def test_excluir_registra_quem_e_os_valores_e_as_exclusoes_em_cascata(ana, pedido):
    item = ItemPedido(pedido=pedido, descricao="parafuso")
    item.salvar_como_sistema("teste")
    pk_item, pk_pedido = item.pk, pedido.pk
    pedido.excluir(ana)
    [excluiu] = linhas(acao="excluiu", tabela="app_teste.Pedido", registro=str(pk_pedido))
    assert excluiu.autor == "ana@exemplo.com" and excluiu.mudancas["titulo"]["antes"] == "Cadeira"
    [cascata] = linhas(acao="excluiu", tabela="app_teste.ItemPedido", registro=str(pk_item))
    assert cascata.autor == "ana@exemplo.com" and cascata.mudancas["descricao"]["antes"] == "parafuso"


# 2. Como sistema e em massa
def test_como_sistema_registra_o_motivo(ana):
    p = Pedido(dono=ana, titulo="Cadeira")
    p.salvar_como_sistema("importação inicial")
    [linha] = linhas(p)
    assert linha.como_sistema and linha.autor == "sistema" and linha.motivo == "importação inicial"
    p.excluir_como_sistema("limpeza de teste")
    assert linhas(acao="excluiu")[0].motivo == "limpeza de teste"


def test_alteracao_em_massa_registra_cada_registro_que_mudou(ana):
    for titulo in ("A", "B", "C"):
        Pedido(dono=ana, titulo=titulo).salvar(ana)
    Pedido.objects.como_sistema("reajuste").filter(titulo__in=["A", "B"]).update(valor="5.00")
    alterou = linhas(acao="alterou")
    assert len(alterou) == 2 and {x.motivo for x in alterou} == {"reajuste"}
    assert {x.rotulo for x in alterou} == {str(p) for p in Pedido._base_manager.filter(titulo__in=["A", "B"])}
    assert alterou[0].mudancas == {"valor": {"nome": "valor", "antes": "0.00", "depois": "5.00"}}
    Pedido.objects.como_sistema("de novo").filter(titulo="A").update(valor="5.00")  # não mudou nada
    assert len(linhas(acao="alterou")) == 2


def test_bulk_update_bulk_create_create_e_delete_em_massa(ana):
    criados = Pedido.objects.como_sistema("carga").bulk_create(
        [Pedido(dono=ana, titulo="X"), Pedido(dono=ana, titulo="Y")])
    assert {(x.registro, x.motivo) for x in linhas(acao="criou", tabela="app_teste.Pedido")} == {
        (str(p.pk), "carga") for p in criados}
    for p in criados:
        p.titulo += "!"
    Pedido.objects.como_sistema("ajuste").bulk_update(criados, ["titulo"])
    assert {x.mudancas["titulo"]["depois"] for x in linhas(acao="alterou")} == {"X!", "Y!"}
    novo = Pedido.objects.como_sistema("criado pelo sistema").create(dono=ana, titulo="Z")
    assert linhas(novo)[0].motivo == "criado pelo sistema"
    Pedido.objects.como_sistema("apagar tudo").delete()
    assert len(linhas(acao="excluiu", motivo="apagar tudo")) == 3


def test_update_or_create_registra_com_o_motivo(ana):
    obj, _ = Pedido.objects.como_sistema("sincronizar").update_or_create(titulo="S", defaults={"dono": ana})
    assert linhas(obj)[0].motivo == "sincronizar" and linhas(obj)[0].acao == "criou"


def test_alteracao_em_massa_consulta_o_banco_poucas_vezes(ana, django_assert_max_num_queries):
    Pedido.objects.como_sistema("carga").bulk_create([Pedido(dono=ana, titulo=f"P{i}") for i in range(600)])
    with django_assert_max_num_queries(20):
        Pedido.objects.como_sistema("reajuste").update(valor="1.00")
    assert len(linhas(acao="alterou")) == 600


# 3. Tudo ou nada
def test_se_o_historico_falha_a_gravacao_tambem_nao_acontece(ana, monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError("banco do histórico fora")

    monkeypatch.setattr(historico, "_gravar", quebra)
    p = Pedido(dono=ana, titulo="Cadeira")
    with pytest.raises(RuntimeError):
        p.salvar(ana)
    assert Pedido._base_manager.count() == 0


def test_se_o_historico_em_massa_falha_a_alteracao_em_massa_tambem_nao_acontece(ana, monkeypatch):
    Pedido(dono=ana, titulo="A").salvar(ana)
    monkeypatch.setattr(historico, "_gravar_varias", lambda linhas: (_ for _ in ()).throw(RuntimeError("fora")))
    with pytest.raises(RuntimeError):
        Pedido.objects.como_sistema("reajuste").update(titulo="B")
    assert Pedido._base_manager.get().titulo == "A"


# 4. Dados sensíveis e campos que não entram
def test_senha_e_chaves_aparecem_so_como_alterada(ana):
    hash_antigo = ana.password
    ana.set_password("outra-senha-bem-longa-para-teste")
    ana.segredo_do_app = "segredo-cifrado"
    ana.salvar_como_sistema("troca de senha")
    [linha] = linhas(ana, acao="alterou")
    assert linha.mudancas["password"] == {"nome": "senha", "antes": None, "depois": "alterada"}
    assert linha.mudancas["segredo_do_app"]["depois"] == "alterada"
    texto = json.dumps([x.mudancas for x in linhas(ana)])
    assert hash_antigo not in texto and ana.password not in texto and "segredo-cifrado" not in texto


def test_data_do_ultimo_login_nao_entra(ana):
    assert Client().post("/entrar/", {"username": "ana@exemplo.com", "password": SENHA}).status_code == 302
    assert linhas(ana, acao="alterou") == []


def test_troca_do_metodo_de_guardar_a_senha_no_login_diz_o_motivo(ana, settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher",
                                 "django.contrib.auth.hashers.MD5PasswordHasher"]
    ana.password = make_password(SENHA, hasher="md5")
    ana.salvar_como_sistema("teste")
    assert ana.check_password(SENHA)
    ultima = linhas(ana, acao="alterou")[-1]
    assert set(ultima.mudancas) == {"password"} and ultima.motivo.startswith("atualização do método")


def test_tabelas_internas_do_00_nao_entram_mas_o_arquivo_aparece_pelo_nome(ana, pedido, settings, tmp_path):
    settings.ARQUIVOS_PASTA = tmp_path
    anexo = Anexo(pedido=pedido)
    anexar(anexo, "arquivo", SimpleUploadedFile("proposta.pdf", PDF))
    anexo.salvar(ana)
    assert linhas(anexo)[0].mudancas["arquivo"]["depois"] == "proposta.pdf"
    assert linhas(tabela="infra_vibecoding.ArquivoGuardado") == []
    assert linhas(tabela="infra_vibecoding.Historico") == []


def test_rotulo_quebrado_nao_derruba_a_gravacao(ana, monkeypatch):
    monkeypatch.setattr(Setor, "__str__", lambda self: 1 / 0)
    s = Setor(nome="Compras")
    s.salvar_como_sistema("teste")
    assert linhas(s)[0].rotulo == f"Setor {s.pk}"


# 5. Ninguém mexe no histórico
def test_historico_nao_se_altera_nem_se_apaga(ana, pedido):
    linha = linhas(pedido)[0]
    with pytest.raises(PermissionError):
        linha.save()
    with pytest.raises(PermissionError):
        linha.delete()
    with pytest.raises(EscritaSemAutorizacao):
        Historico.objects.como_sistema("tentativa").update(autor="outro")
    with pytest.raises(EscritaSemAutorizacao):
        Historico.objects.como_sistema("tentativa").delete()
    with pytest.raises(EscritaSemAutorizacao):
        Historico.objects.como_sistema("tentativa").bulk_update([linha], ["autor"])
    with pytest.raises(AcessoSemEscopo):
        list(Historico.objects.all())
    assert Historico.objects.para(ana).count() == 0  # política fechada: ninguém lista direto
    assert linhas(pedido)[0].autor == "ana@exemplo.com"


# 6. Código do pedido e pessoa logada
def test_gravacao_num_clique_leva_o_codigo_do_pedido_e_a_pessoa(ana, pedido):
    r = logado(ana).get(f"/pedidos/{pedido.pk}/renomear/?titulo=Mesa")
    assert r.status_code == 200
    codigo = r["X-Codigo-Pedido"]
    assert len(codigo) == 8
    [alterou] = linhas(pedido, acao="alterou")
    assert alterou.pedido == codigo and alterou.pessoa == "ana@exemplo.com"


def test_cada_clique_tem_um_codigo_diferente_e_fora_do_clique_fica_vazio(ana, pedido, client):
    assert client.get("/").get("X-Codigo-Pedido") != client.get("/").get("X-Codigo-Pedido")
    assert linhas(pedido)[0].pedido == "" and linhas(pedido)[0].pessoa == ""


def test_codigo_do_pedido_precisa_ser_o_primeiro_middleware(settings):
    ids = [e.id for e in run_checks()]
    assert "SEC.E131" not in ids
    settings.MIDDLEWARE = [m for m in settings.MIDDLEWARE if m != "infra_vibecoding.pedido.CodigoDoPedido"]
    assert "SEC.E131" in [e.id for e in run_checks()]
    settings.MIDDLEWARE = [*settings.MIDDLEWARE[:1], "infra_vibecoding.pedido.CodigoDoPedido",
                           *settings.MIDDLEWARE[1:]]
    assert "SEC.E131" in [e.id for e in run_checks()]


# 7. Quem vê o registro vê o histórico
def test_historico_de_so_para_quem_ve_o_registro(ana, beto, pedido):
    assert [x.acao for x in historico_de(pedido, ana)] == ["criou"]
    assert historico_de(pedido, beto) == []


def test_tela_de_historico(ana, beto, pedido):
    pedido.titulo = "Mesa"
    pedido.salvar(ana)
    url = historico_url(pedido)
    assert url == f"/historico/app_teste/pedido/{pedido.pk}/"
    tela = logado(ana).get(url).content.decode()
    assert "Cadeira → Mesa" in tela and "ana@exemplo.com" in tela and "criou" in tela
    assert logado(beto).get(url).status_code == 404
    assert Client().get(url).status_code == 302  # sem login: vai para o login
    assert logado(ana).get("/historico/app_teste/naoexiste/1/").status_code == 404
    assert logado(ana).get("/historico/auth/group/1/").status_code == 404  # tabela fora da trava do 00
    assert logado(ana).get(f"/historico/infra_vibecoding/historico/{linhas()[0].pk}/").status_code == 404


def test_filtro_de_template(pedido):
    from django.template import Context, Template

    html = Template("{% load historico %}{{ p|historico_url }}").render(Context({"p": pedido}))
    assert html == f"/historico/app_teste/pedido/{pedido.pk}/"


# 8. Ações de negócio
def test_registrar_acao_entra_na_linha_do_tempo(ana, pedido):
    registrar_acao(ana, pedido, "aprovou o pedido", {"prazo": "3 dias", "urgente": True})
    linha = linhas(pedido, acao="acao")[0]
    assert linha.nome_da_acao == "aprovou o pedido" and linha.autor == "ana@exemplo.com"
    assert linha.mudancas["urgente"]["depois"] == "sim"
    assert "aprovou o pedido" in logado(ana).get(historico_url(pedido)).content.decode()


def test_compartilhar_arquivo_entra_no_historico_do_registro(ana, pedido, settings, tmp_path):
    settings.ARQUIVOS_PASTA = tmp_path
    anexo = Anexo(pedido=pedido)
    anexar(anexo, "arquivo", SimpleUploadedFile("proposta.pdf", PDF))
    anexo.salvar(ana)
    link, _ = compartilhar(ana, anexo, "arquivo", dias=3)
    from infra_vibecoding.arquivos import cancelar_compartilhamento

    cancelar_compartilhamento(ana, link)
    acoes = [x.nome_da_acao for x in linhas(anexo, acao="acao")]
    assert acoes == ["criou link de compartilhamento", "cancelou link de compartilhamento"]
    assert linhas(anexo, acao="acao")[0].mudancas["prazo"]["depois"] == "3 dia(s)"


# 9. Tela de banco: só lê
def test_tela_de_banco_so_le_o_historico(ana, pedido):
    chefe = Usuario.objects.create_superuser("chefe@exemplo.com", password=SENHA)
    c = logado(chefe)
    lista = "/gestao-interna/infra_vibecoding/historico/"
    tela = c.get(lista).content.decode()
    assert "app_teste.Pedido" in tela and "historico/add/" not in tela and "Exportar" not in tela
    linha = linhas(pedido)[0]
    detalhe = c.get(f"{lista}{linha.pk}/change/").content.decode()
    assert "<strong>titulo</strong>: Cadeira" in detalhe
    assert c.post(f"{lista}{linha.pk}/delete/", {"post": "yes"}).status_code == 403
    assert Historico._base_manager.filter(pk=linha.pk).exists()
    assert logado(ana).get(lista).status_code == 302  # quem não é da tela de banco nem entra


def test_historico_ligado_desde_o_inicio_do_sistema():
    """Num processo novo (ex.: um comando que só exclui), o registro das exclusões já está ligado."""
    import os
    import subprocess
    import sys

    codigo = ("import django; django.setup(); from django.db.models.signals import post_delete; "
              "print(any(r[0][0] == 'infra_vibecoding.historico.excluir' for r in post_delete.receivers))")
    ambiente = {**os.environ, "DJANGO_SETTINGS_MODULE": "tests.settings"}
    saida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, env=ambiente,
                           cwd=os.path.dirname(os.path.dirname(__file__)), check=True)
    assert saida.stdout.strip().endswith("True")
