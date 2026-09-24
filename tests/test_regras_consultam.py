"""Testes das regras que consultam outras tabelas com self.consultar(...) (US 2.3)."""
import logging

import pytest
from django.contrib.auth import get_user_model

from infra_vibecoding import dados
from infra_vibecoding.dados import (
    AcessoSemEscopo,
    EscritaSemAutorizacao,
    Politica,
    SemPermissao,
    exigir,
    pode,
    politica_de,
)
from tests.app_teste.models import AcessoSetor, Documento, Pedido, Setor

pytestmark = pytest.mark.django_db
User = get_user_model()
MOTIVO = "preparar teste"


@pytest.fixture
def cenario():
    """Ana tem acesso ao Financeiro (pode editar). Beto tem acesso ao RH (só ver)."""
    ana = User.objects.create_user("ana")
    beto = User.objects.create_user("beto")
    carla = User.objects.create_user("carla")  # sem acesso a nada
    sistema = Setor.objects.como_sistema(MOTIVO)
    financeiro = sistema.create(nome="Financeiro")
    rh = sistema.create(nome="RH")
    acessos = AcessoSetor.objects.como_sistema(MOTIVO)
    acesso_ana = acessos.create(usuario=ana, setor=financeiro, pode_editar=True)
    acessos.create(usuario=beto, setor=rh, pode_editar=False)
    docs = Documento.objects.como_sistema(MOTIVO)
    doc_fin = docs.create(setor=financeiro, titulo="Balanço")
    doc_rh = docs.create(setor=rh, titulo="Folha")
    return dict(ana=ana, beto=beto, carla=carla, doc_fin=doc_fin, doc_rh=doc_rh, acesso_ana=acesso_ana)


def titulos(qs):
    return sorted(qs.values_list("titulo", flat=True))


# 1. A regra consulta outra tabela e filtra certo.
def test_cada_um_ve_so_os_documentos_do_proprio_setor(cenario):
    assert titulos(Documento.objects.para(cenario["ana"])) == ["Balanço"]
    assert titulos(Documento.objects.para(cenario["beto"])) == ["Folha"]
    assert titulos(Documento.objects.para(cenario["carla"])) == []


def test_busca_e_filtro_tambem_respeitam_a_regra(cenario):
    ana = cenario["ana"]
    assert not Documento.objects.para(ana).filter(titulo="Folha").exists()
    assert Documento.objects.para(ana).count() == 1
    with pytest.raises(Documento.DoesNotExist):
        Documento.objects.para(ana).get(pk=cenario["doc_rh"].pk)  # link direto para documento do RH


def test_regra_le_tabela_que_e_fechada_para_o_usuario(cenario):
    # A tabela de acessos é fechada: a Ana não lê nada dela direto...
    assert AcessoSetor.objects.para(cenario["ana"]).count() == 0
    # ...mas a regra de Documento consegue consultar para decidir.
    assert Documento.objects.para(cenario["ana"]).count() == 1


def test_tirar_o_acesso_vale_no_pedido_seguinte(cenario):
    cenario["acesso_ana"].excluir_como_sistema("acesso retirado")
    assert titulos(Documento.objects.para(cenario["ana"])) == []


# 2. Ações também usam a consulta.
def test_pode_editar_consultando_outra_tabela(cenario):
    ana, beto = cenario["ana"], cenario["beto"]
    assert pode(ana, "editar", cenario["doc_fin"]) is True
    assert pode(ana, "editar", cenario["doc_rh"]) is False
    assert pode(beto, "editar", cenario["doc_rh"]) is False  # beto só vê


def test_salvar_confere_a_regra_que_consulta(cenario):
    doc = cenario["doc_fin"]
    doc.titulo = "Balanço 2026"
    doc.salvar(cenario["ana"])
    outro = cenario["doc_rh"]
    outro.titulo = "Folha alterada"
    with pytest.raises(SemPermissao):
        outro.salvar(cenario["ana"])
    with pytest.raises(SemPermissao):
        exigir(cenario["beto"], "editar", cenario["doc_rh"])


# 3. Fora de uma regra, consultar não funciona.
def test_consultar_fora_da_regra_e_bloqueado(cenario):
    with pytest.raises(AcessoSemEscopo):
        politica_de(Documento).consultar(AcessoSetor)


def test_consultar_numa_politica_qualquer_fora_da_regra_e_bloqueado(cenario):
    with pytest.raises(AcessoSemEscopo):
        Politica().consultar(Pedido)


def test_consulta_guardada_e_usada_depois_da_regra_e_bloqueada(cenario):
    pol = politica_de(Documento)
    with dados._rodando_regra():
        guardada = pol.consultar(AcessoSetor)
    with pytest.raises(AcessoSemEscopo):
        list(guardada)
    with pytest.raises(AcessoSemEscopo):
        guardada.count()


# 4. Dentro da regra, consultar só lê.
@pytest.mark.parametrize("tentativa", [
    lambda q: q.update(pode_editar=True),
    lambda q: q.delete(),
    lambda q: q.create(usuario_id=9999, setor_id=9999),
    lambda q: q.get_or_create(usuario_id=9999, setor_id=9999),
    lambda q: q.update_or_create(usuario_id=9999, setor_id=9999),
    lambda q: q.bulk_create([]),
])
def test_consultar_nao_grava_em_massa(cenario, tentativa):
    pol = politica_de(Documento)
    with dados._rodando_regra():
        with pytest.raises(EscritaSemAutorizacao):
            tentativa(pol.consultar(AcessoSetor))


def test_registro_lido_pela_consulta_nao_pode_ser_salvo_nem_excluido(cenario):
    pol = politica_de(Documento)
    with dados._rodando_regra():
        acesso = pol.consultar(AcessoSetor).get(usuario=cenario["beto"])
        acesso.pode_editar = True
        with pytest.raises(EscritaSemAutorizacao):
            acesso.save()
        with pytest.raises(EscritaSemAutorizacao):
            acesso.delete()


# 5. O escopo precisa devolver um filtro da própria tabela.
class _EscopoDevolveOutraTabela(Politica):
    def escopo(self, usuario, qs):
        return self.consultar(AcessoSetor)


class _EscopoDevolveConsultaDeRegra(Politica):
    def escopo(self, usuario, qs):
        return self.consultar(Documento)  # tudo, sem filtro, por fora do qs recebido


class _EscopoDevolveLista(Politica):
    def escopo(self, usuario, qs):
        return []


@pytest.mark.parametrize("ruim", [_EscopoDevolveOutraTabela, _EscopoDevolveConsultaDeRegra, _EscopoDevolveLista])
def test_escopo_que_nao_devolve_filtro_da_propria_tabela_da_erro(cenario, monkeypatch, ruim):
    monkeypatch.setitem(dados._REGISTRO, Documento, ruim())
    with pytest.raises(TypeError):
        Documento.objects.para(cenario["ana"])


# 6. Sem registro de auditoria a cada uso (a regra roda em todo pedido).
def test_consultar_nao_gera_registro_de_auditoria(cenario, caplog):
    with caplog.at_level(logging.INFO, logger="infra_vibecoding.auditoria"):
        caplog.clear()
        list(Documento.objects.para(cenario["ana"]))
        pode(cenario["ana"], "editar", cenario["doc_fin"])
    assert caplog.records == []


# 7. O que já existia continua igual.
def test_leitura_sem_escopo_continua_bloqueada(cenario):
    with pytest.raises(AcessoSemEscopo):
        list(AcessoSetor.objects.all())
    with pytest.raises(AcessoSemEscopo):
        list(Documento.objects.filter(titulo="Folha"))


def test_regra_terminada_com_erro_nao_deixa_a_porta_aberta(cenario):
    class Explode(Politica):
        def escopo(self, usuario, qs):
            raise RuntimeError("falha na regra")

    pol = Explode()
    with pytest.raises(RuntimeError):
        with dados._rodando_regra():
            pol.escopo(cenario["ana"], None)
    with pytest.raises(AcessoSemEscopo):
        pol.consultar(AcessoSetor)
