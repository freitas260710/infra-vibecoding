"""
Histórico automático do Infra Vibecoding (US 6.1, decisões D36 e D60). Equivalente ao [Sd]Historico do Bubble,
só que ninguém precisa lembrar de chamar: o 00 grava sozinho.

- Toda criação, alteração e exclusão de qualquer tabela do sistema (ModeloSeguro), por qualquer caminho: telas,
  tela de banco, importação de planilha, alterações em massa "como sistema" e exclusões em cascata.
- Cada linha guarda: quando, o código do pedido (o clique), a pessoa logada, quem gravou (a pessoa ou "sistema" com
  o motivo), a tabela, o registro e o rótulo dele, a ação e o antes/depois de cada campo, com o nome do campo.
- Senha, chaves e 2FA aparecem só como "alterada". Arquivos aparecem pelo nome. A data do último login não entra.
- Ninguém edita nem apaga (nem pela tela de banco). Guardado para sempre.

Quem vê o registro vê o histórico dele:

    from infra_vibecoding.historico import historico_de, registrar_acao

    linhas = historico_de(chamado, request.user)       # [] se a pessoa não vê o chamado
    {% load historico %} <a href="{{ chamado|historico_url }}">Histórico</a>    # tela pronta do 00

Ações de negócio com nome amigável (entram na mesma linha do tempo do registro):

    registrar_acao(request.user, chamado, "aprovou o chamado", {"prazo": "3 dias"})
"""
import datetime
import decimal
import logging
import uuid

from django.db.models.signals import post_delete
from django.urls import reverse

log = logging.getLogger("infra_vibecoding.auditoria")

OCULTOS = frozenset({"password", "chave_de_sessao", "segredo_do_app", "codigos_de_recuperacao"})
IGNORADOS = frozenset({"last_login", "ultimo_codigo_do_app"})
_MAX_TEXTO = 2000


def deve_registrar(modelo):
    from .dados import ModeloSeguro

    return issubclass(modelo, ModeloSeguro) and modelo._meta.app_label != "infra_vibecoding"


def _campos(modelo, so_estes=None):
    campos = [c for c in modelo._meta.concrete_fields if c.name not in IGNORADOS and not c.primary_key]
    if so_estes is not None:
        nomes = set(so_estes)
        campos = [c for c in campos if c.name in nomes or c.attname in nomes]
    return campos


def foto(obj, so_estes=None):
    """Valores gravados no banco agora (antes de alterar). Uma consulta. None se o registro não existe."""
    if obj.pk is None:
        return None
    nomes = [c.attname for c in _campos(type(obj), so_estes)]
    if not nomes:
        return {}
    return type(obj)._base_manager.filter(pk=obj.pk).values(*nomes).first()


def _valor_legivel(campo, valor, obj=None):
    from .arquivos import ArquivoRef, CampoArquivo

    if valor is None or valor == "":
        return None
    if campo.name in OCULTOS:
        return "(oculto)"
    if isinstance(campo, CampoArquivo):
        return ArquivoRef(valor).nome or str(valor)
    if campo.is_relation:
        relacionado = None
        if obj is not None and campo.is_cached(obj):  # já carregado (ex.: formulário): não consulta o banco
            relacionado = campo.get_cached_value(obj)
            if relacionado is not None and relacionado.pk != valor:
                relacionado = None
        if relacionado is None:
            relacionado = campo.related_model._base_manager.filter(pk=valor).first()
        return f"{_rotulo(relacionado)} (id {valor})" if relacionado is not None else f"id {valor}"
    if campo.choices:
        return str(dict(campo.flatchoices).get(valor, valor))
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if isinstance(valor, datetime.datetime):
        from django.utils import timezone

        if timezone.is_aware(valor):
            valor = timezone.localtime(valor)
        return valor.strftime("%d/%m/%Y %H:%M:%S")
    if isinstance(valor, datetime.date):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, (decimal.Decimal, uuid.UUID)):
        return str(valor)
    if isinstance(valor, (int, float)):
        return valor
    texto = str(valor)
    return texto if len(texto) <= _MAX_TEXTO else texto[:_MAX_TEXTO] + "…"


def _normalizar(campo, valor):
    """Mesmo tipo dos dois lados: "10.00" digitado na tela e Decimal("10.00") do banco são o mesmo valor."""
    if valor is None:
        return None
    try:
        return campo.to_python(valor)
    except Exception:  # valor que o campo não converte: compara como veio
        return valor


def _diferencas(modelo, antes, depois, so_estes=None, obj=None):
    mudancas = {}
    for campo in _campos(modelo, so_estes):
        a = _normalizar(campo, antes.get(campo.attname) if antes else None)
        d = _normalizar(campo, depois.get(campo.attname))
        if a == d:
            continue
        nome = str(campo.verbose_name)
        if campo.name in OCULTOS:
            mudancas[campo.name] = {"nome": nome, "antes": None, "depois": "alterada"}
        else:
            mudancas[campo.name] = {"nome": nome, "antes": _valor_legivel(campo, a, obj),
                                    "depois": _valor_legivel(campo, d, obj)}
    return mudancas


def _valores_do_objeto(obj, so_estes=None):
    return {c.attname: getattr(obj, c.attname) for c in _campos(type(obj), so_estes)}


def _quem():
    from .dados import _AUTOR

    tipo, quem = _AUTOR.get()
    if tipo == "usuario":
        return getattr(quem, "email", None) or str(getattr(quem, "pk", "?")), False, ""
    return "sistema", True, str(quem or "")


def _linha(tabela, registro, rotulo, acao, mudancas=None, nome_da_acao="", autor=None, como_sistema=None,
           motivo=None):
    from .models import Historico
    from .pedido import codigo_atual, pessoa_atual

    padrao_autor, padrao_sistema, padrao_motivo = _quem()
    return Historico(
        pedido=codigo_atual(), pessoa=pessoa_atual()[:254],
        autor=(autor if autor is not None else padrao_autor)[:254],
        como_sistema=padrao_sistema if como_sistema is None else como_sistema,
        motivo=padrao_motivo if motivo is None else motivo,
        tabela=tabela, registro=str(registro)[:64], rotulo=str(rotulo)[:200], acao=acao,
        nome_da_acao=nome_da_acao, mudancas=mudancas or {},
    )


def _gravar(*args, **kwargs):
    from .dados import _autorizar

    linha = _linha(*args, **kwargs)
    with _autorizar(linha):
        linha.save(force_insert=True)
    return linha


def _gravar_varias(linhas):
    """Alterações em massa: grava as linhas do histórico em lotes (uma ida ao banco a cada 500)."""
    from .models import Historico

    if linhas:
        Historico._base_manager.bulk_create(linhas, batch_size=500)


def _rotulo(obj):
    try:
        return str(obj)
    except Exception:  # um __str__ quebrado do sistema não pode derrubar a gravação
        return f"{type(obj).__name__} {obj.pk}"


# Ganchos chamados pelo ModeloSeguro e pelo QuerySetSeguro

def depois_de_salvar(obj, antes, criando, so_estes=None):
    modelo = type(obj)
    if not deve_registrar(modelo):
        return
    if criando:
        mudancas = _diferencas(modelo, None, _valores_do_objeto(obj), obj=obj)
        _gravar(modelo._meta.label, obj.pk, _rotulo(obj), "criou", mudancas)
        return
    mudancas = _diferencas(modelo, antes or {}, _valores_do_objeto(obj, so_estes), so_estes, obj=obj)
    if mudancas:
        _gravar(modelo._meta.label, obj.pk, _rotulo(obj), "alterou", mudancas)


def fotos_em_massa(queryset):
    """Antes de uma alteração em massa: os valores de cada registro que vai ser alterado."""
    modelo = queryset.model
    if not deve_registrar(modelo):
        return {}
    nomes = [c.attname for c in _campos(modelo)]
    pks = queryset.model._base_manager.filter(pk__in=queryset.values("pk"))
    return {linha.pop("pk"): linha for linha in pks.values("pk", *nomes)}


def depois_de_alterar_em_massa(modelo, antes_por_pk):
    """Alteração em massa (update/bulk_update como sistema): uma linha de histórico por registro que mudou."""
    if not deve_registrar(modelo) or not antes_por_pk:
        return
    nomes = [c.attname for c in _campos(modelo)]
    pks = list(antes_por_pk)
    linhas = []
    for inicio in range(0, len(pks), 500):
        lote = pks[inicio:inicio + 500]
        objs = modelo._base_manager.in_bulk(lote)
        for depois in modelo._base_manager.filter(pk__in=lote).values("pk", *nomes):
            pk = depois.pop("pk")
            mudancas = _diferencas(modelo, antes_por_pk[pk], depois)
            if mudancas:
                obj = objs.get(pk)
                linhas.append(_linha(modelo._meta.label, pk, _rotulo(obj) if obj else pk, "alterou", mudancas))
    _gravar_varias(linhas)


def depois_de_criar_em_massa(objs):
    linhas = []
    for obj in objs:
        modelo = type(obj)
        if obj.pk is None or not deve_registrar(modelo):
            continue
        mudancas = _diferencas(modelo, None, _valores_do_objeto(obj), obj=obj)
        linhas.append(_linha(modelo._meta.label, obj.pk, _rotulo(obj), "criou", mudancas))
    _gravar_varias(linhas)


def _ao_excluir(sender, instance, **kwargs):
    if not deve_registrar(sender):
        return
    antes = _valores_do_objeto(instance)
    _gravar(sender._meta.label, instance.pk, _rotulo(instance), "excluiu", _diferencas(sender, antes, {}, obj=instance))


post_delete.connect(_ao_excluir, dispatch_uid="infra_vibecoding.historico.excluir")


# Para o sistema

def registrar_acao(usuario, registro, nome, detalhes=None):
    """Ação de negócio com nome amigável ("aprovou o chamado"), na linha do tempo do registro."""
    detalhes = {str(k): {"nome": str(k), "antes": None, "depois": _valor_simples(v)}
                for k, v in (detalhes or {}).items()}
    autor = getattr(usuario, "email", None) or "sistema"
    return _gravar(registro._meta.label, registro.pk, _rotulo(registro), "acao", detalhes, nome_da_acao=nome[:120],
                   autor=autor, como_sistema=usuario is None, motivo="")


def _valor_simples(v):
    if isinstance(v, bool):
        return "sim" if v else "não"
    if isinstance(v, (str, int, float)) or v is None:
        return v
    if isinstance(v, datetime.datetime):
        from django.utils import timezone

        return (timezone.localtime(v) if timezone.is_aware(v) else v).strftime("%d/%m/%Y %H:%M")
    if isinstance(v, datetime.date):
        return v.strftime("%d/%m/%Y")
    return str(v)


def historico_de(registro, usuario):
    """O histórico do registro, do mais novo para o mais antigo, se a pessoa vê o registro. Senão, lista vazia."""
    from .models import Historico

    modelo = type(registro)
    ve = modelo.objects.para(usuario).filter(pk=registro.pk).exists()
    if not ve:
        return []
    return list(Historico._base_manager.filter(tabela=modelo._meta.label, registro=str(registro.pk)))


def historico_url(registro):
    return reverse("historico_do_registro", args=[registro._meta.app_label, registro._meta.model_name, registro.pk])


def tela_historico(request, app, modelo, pk):
    """Tela pronta do 00: histórico de um registro. "Não encontrado" para quem não vê o registro."""
    from django.apps import apps
    from django.http import Http404
    from django.shortcuts import render

    try:
        classe = apps.get_model(app, modelo)
    except LookupError:
        raise Http404 from None
    if not deve_registrar(classe):
        raise Http404
    registro = classe.objects.para(request.user).filter(pk=pk).first()
    if registro is None:
        raise Http404
    return render(request, "infra_vibecoding/historico/registro.html", {
        "registro": registro, "tabela": classe._meta.verbose_name, "linhas": historico_de(registro, request.user),
    })


def _declarar():
    from .telas import logado

    return logado(tela_historico)


tela_historico = _declarar()
