"""
Registro de acessos do Infra Vibecoding (US 6.2, decisão D60). Equivalente à parte de acessos da aba Logs do Bubble.

O 00 registra sozinho, numa tabela só:
- entrou, senha errada, bloqueado (login bloqueado ou limite de pedidos, só o primeiro de cada minuto) e saiu;
- acesso negado (a regra barrou a pessoa), no máximo um por clique;
- verificação em duas etapas (ligou, desligou, códigos novos, código errado, código de recuperação usado);
- senha (definiu pelo link, trocou, definiu no cadastro) e link de acesso enviado;
- download de arquivo privado e por link de compartilhamento;
- planilha exportada ou importada na tela de banco e entrada na tela de banco;
- erro interno (o código do erro; o erro completo fica no registro do servidor e, com a US 6.3, no Sentry).

Cada linha guarda quando, o código do pedido (o clique), a pessoa (ou o e-mail digitado, se o login falhou), o
endereço de internet, o navegador, a tela e o que aconteceu. Nunca guarda senha, código, link ou chave.

Não entra: navegação comum, quem leu um registro, conteúdo de formulário ou arquivo, mudanças de dados (estão no
histórico), página que não existe (404) e arquivo de campo público.

Guardado por um ano (D60): limpar_acessos_antigos() apaga o que passou disso. Até a etapa 5 (jobs), rodar o
comando `uv run python manage.py limpar_registros` (por exemplo, uma vez por dia).

O sistema pode registrar um acesso próprio com registrar_acesso("download", "nota fiscal 123"), usando um dos tipos
da tabela.
"""
import logging

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.core.cache import cache
from django.utils import timezone

log = logging.getLogger("infra_vibecoding.auditoria")

GUARDA_DIAS = 365
_LOTE = 5000


def _email(usuario):
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return ""
    return getattr(usuario, "email", "") or str(usuario.pk)


def registrar_acesso(tipo, detalhe="", pessoa=None, request=None):
    """Registra um acesso. Dentro de um clique, a linha é gravada no fim dele (fora da transação da tela)."""
    from .limites import endereco_de
    from .models import Acesso
    from .pedido import pedido_atual

    pedido = pedido_atual()
    if request is None and pedido is not None:
        request = pedido.request
    if pessoa is None:
        pessoa = _email(getattr(request, "user", None))
    meta = getattr(request, "META", {}) if request is not None else {}
    tela = f"{getattr(request, 'method', '') or ''} {getattr(request, 'path', '') or ''}".strip()
    linha = Acesso(
        pedido=pedido.codigo if pedido is not None else "", tipo=tipo, pessoa=str(pessoa or "")[:254],
        endereco=endereco_de(request)[:45] if request is not None else "",
        navegador=str(meta.get("HTTP_USER_AGENT", ""))[:300], tela=tela[:300], detalhe=str(detalhe or "")[:500],
    )
    if pedido is not None and (request is None or request is pedido.request):
        if tipo == "negado" and any(a.tipo == "negado" for a in pedido.acessos):
            return None  # um acesso negado por clique basta (a regra barra e a página 403 aparece em seguida)
        pedido.acessos.append(linha)
        return linha
    gravar_pendentes([linha])
    return linha


def gravar_pendentes(linhas):
    """Grava as linhas de uma vez. Se o banco falhar, o erro vai para o registro do servidor e a tela segue."""
    from .models import Acesso

    try:
        Acesso._base_manager.bulk_create(linhas)
    except Exception:
        log.exception("registro de acessos: não foi possível gravar %s linha(s)", len(linhas))


def registrar_limite(request, quem, detalhe):
    """Limite de pedidos atingido: registra só o primeiro de cada minuto para a mesma pessoa ou endereço."""
    if cache.add(f"infra_vibecoding:acesso-limite:{quem}", True, 60):
        registrar_acesso("bloqueado", detalhe, request=request)


def limpar_acessos_antigos(dias=GUARDA_DIAS):
    """Apaga os acessos com mais de `dias` dias (padrão: um ano). O histórico dos registros não é apagado nunca.
    Devolve quantos apagou."""
    from .models import Acesso

    corte = timezone.now() - timezone.timedelta(days=dias)
    total = 0
    while True:
        pks = list(Acesso._base_manager.filter(quando__lt=corte).values_list("pk", flat=True)[:_LOTE])
        if not pks:
            break
        Acesso._base_manager.filter(pk__in=pks).delete()
        total += len(pks)
    log.info("registro de acessos: limpeza apagou %s linha(s) com mais de %s dias", total, dias)
    return total


# Entrar e sair (sinais do próprio Django: valem para todo login, inclusive com verificação em duas etapas)

def _ao_entrar(sender, request, user, **kwargs):
    registrar_acesso("entrou", "com verificação em duas etapas" if getattr(user, "dois_fatores", "") else "",
                     pessoa=_email(user), request=request)


def _ao_sair(sender, request, user, **kwargs):
    registrar_acesso("saiu", "", pessoa=_email(user), request=request)


user_logged_in.connect(_ao_entrar, dispatch_uid="infra_vibecoding.acessos.entrou")
user_logged_out.connect(_ao_sair, dispatch_uid="infra_vibecoding.acessos.saiu")


# Tela única de Registros (tela de banco, só superusuário): histórico dos dados, acessos e erros juntos

POR_PAGINA = 100


def _codigo_limpo(texto):
    codigo = (texto or "").strip().upper()
    return codigo[2:] if codigo.startswith("E-") else codigo


def consultar_registros(tipo="", pessoa="", de=None, ate=None, tabela="", pedido="", inicio=0,
                        quantos=POR_PAGINA):
    """Histórico dos registros e acessos numa lista só, do mais novo para o mais antigo. Devolve (linhas, total).

    tipo: "" (tudo), "dados", "acessos", "erros", "dados:<ação>" ou "acessos:<tipo>". pedido aceita "E-..." (o
    código do erro). Com tabela, só entram os dados (acessos não têm tabela)."""
    from django.db.models import CharField, F, Q, Value
    from django.db.models.functions import Coalesce, NullIf

    from .models import Acesso, Historico

    h, a = Historico._base_manager.all(), Acesso._base_manager.all()
    usar_h = usar_a = True
    if tipo == "dados":
        usar_a = False
    elif tipo == "acessos":
        usar_h, a = False, a.exclude(tipo="erro")
    elif tipo == "erros":
        usar_h, a = False, a.filter(tipo="erro")
    elif tipo.startswith("dados:"):
        usar_a, h = False, h.filter(acao=tipo[6:])
    elif tipo.startswith("acessos:"):
        usar_h, a = False, a.filter(tipo=tipo[8:])
    if tabela:
        usar_a, h = False, h.filter(tabela__icontains=tabela.strip())
    if pessoa:
        pessoa = pessoa.strip()
        h = h.filter(Q(pessoa__icontains=pessoa) | Q(autor__icontains=pessoa))
        a = a.filter(pessoa__icontains=pessoa)
    if de:
        h, a = h.filter(quando__date__gte=de), a.filter(quando__date__gte=de)
    if ate:
        h, a = h.filter(quando__date__lte=ate), a.filter(quando__date__lte=ate)
    if pedido:
        codigo = _codigo_limpo(pedido)
        h, a = h.filter(pedido=codigo), a.filter(pedido=codigo)

    texto = CharField()
    campos = ("r_origem", "r_id", "r_quando", "r_tipo", "r_pessoa", "r_pedido", "r_onde", "r_o_que", "r_extra")
    partes = []
    if usar_h:
        partes.append(h.annotate(
            r_origem=Value("dados", output_field=texto), r_id=F("id"), r_quando=F("quando"), r_tipo=F("acao"),
            r_pessoa=Coalesce(NullIf(F("pessoa"), Value("")), F("autor"), output_field=texto),
            r_pedido=F("pedido"), r_onde=F("tabela"), r_o_que=F("rotulo"), r_extra=F("nome_da_acao"),
        ).values(*campos).order_by())
    if usar_a:
        from django.db.models import Case, When

        partes.append(a.annotate(
            r_origem=Case(When(tipo="erro", then=Value("erros")), default=Value("acessos"), output_field=texto),
            r_id=F("id"), r_quando=F("quando"), r_tipo=F("tipo"), r_pessoa=F("pessoa"), r_pedido=F("pedido"),
            r_onde=F("tela"), r_o_que=F("detalhe"), r_extra=F("endereco"),
        ).values(*campos).order_by())
    total = (h.count() if usar_h else 0) + (a.count() if usar_a else 0)
    if not partes:
        return [], 0
    consulta = partes[0] if len(partes) == 1 else partes[0].union(partes[1], all=True)
    linhas = list(consulta.order_by("-r_quando", "-r_id")[inicio:inicio + quantos])
    nomes = {**dict(Historico.ACOES), **dict(Acesso.TIPOS)}
    for linha in linhas:
        linha["r_tipo_nome"] = linha["r_extra"] if linha["r_tipo"] == "acao" and linha["r_extra"] else \
            nomes.get(linha["r_tipo"], linha["r_tipo"])
    return linhas, total
