"""
Painel de rastreio do Infra Vibecoding (US 6.4, decisão D60). Parecido com o debugger do Bubble: mostra o que
aconteceu por trás de um clique.

Como usar: logado como superusuário, no Mac ou no dev online, acrescente ?debug_mode=true ao endereço de qualquer
tela (ex.: /chamados/?debug_mode=true). O painel aparece na lateral. Navegando pelos links e formulários da tela,
o debug_mode continua; tirando do endereço, o painel some. Em produção nunca aparece (SEC.E141), e para quem não é
superusuário o debug_mode não faz nada.

Abas do painel: as da ferramenta django-debug-toolbar (consultas ao banco, tempo, telas, cabeçalhos) e as do 00:
- Regras: cada permissão conferida no clique (quem, ação, tabela, registro) e se liberou ou barrou;
- Histórico: o que foi gravado no histórico dos registros naquele clique;
- Acessos: o que entrou no registro de acessos naquele clique.
Cada aba do 00 mostra o código do clique, com atalho para a tela de Registros filtrada por ele.

Sem o debug_mode na tela, o painel não anota nada: não pesa. Este módulo só é carregado fora de produção.
"""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from debug_toolbar.middleware import DebugToolbarMiddleware
from debug_toolbar.panels import Panel
from debug_toolbar.utils import is_processable_html_response
from django.conf import settings
from django.templatetags.static import static
from django.urls import NoReverseMatch, reverse

from .pedido import PARAMETRO_DO_PAINEL, pedido_atual

PREFIXO = "/__debug__/"
_REDIRECIONAMENTOS = (301, 302, 303, 307, 308)


def _superusuario(request):
    usuario = getattr(request, "user", None)
    return bool(usuario is not None and usuario.is_authenticated and usuario.is_active and usuario.is_superuser)


def mostrar_painel(request):
    """O painel aparece neste pedido? Só fora de produção, só para superusuário, só com ?debug_mode=true."""
    if getattr(settings, "AMBIENTE", "producao") == "producao":
        return False
    if not _superusuario(request):
        return False
    if request.path.startswith(PREFIXO):
        return True  # as abas do painel carregam o conteúdo por esses endereços
    return request.GET.get(PARAMETRO_DO_PAINEL) == "true"


def com_debug_mode(endereco, host):
    """O mesmo endereço com ?debug_mode=true (só para endereços do próprio sistema)."""
    partes = urlsplit(endereco)
    if (partes.netloc and partes.netloc != host) or partes.path.startswith(PREFIXO):
        return endereco
    consulta = [(k, v) for k, v in parse_qsl(partes.query, keep_blank_values=True) if k != PARAMETRO_DO_PAINEL]
    consulta.append((PARAMETRO_DO_PAINEL, "true"))
    return urlunsplit(partes._replace(query=urlencode(consulta)))


class PainelDeRastreio(DebugToolbarMiddleware):
    """Middleware do painel: o django-debug-toolbar com o liga-desliga pelo ?debug_mode=true."""

    def __call__(self, request):
        if self.async_mode:
            return super().__call__(request)
        ligado = mostrar_painel(request) and not request.path.startswith(PREFIXO)
        pedido = pedido_atual()
        if ligado and pedido is not None:
            pedido.regras = []  # a partir daqui, as permissões conferidas são anotadas
        resposta = super().__call__(request)
        if not ligado:
            return resposta
        if resposta.status_code in _REDIRECIONAMENTOS and resposta.get("Location"):
            # Depois de salvar (a tela volta por GET), o painel continua na tela seguinte.
            resposta["Location"] = com_debug_mode(resposta["Location"], request.get_host())
        elif is_processable_html_response(resposta):
            conteudo = resposta.content.decode(resposta.charset)
            posicao = conteudo.lower().rfind("</body>")
            if posicao != -1:
                script = f'<script src="{static("infra_vibecoding/modo_depuracao.js")}" defer></script>'
                resposta.content = (conteudo[:posicao] + script + conteudo[posicao:]).encode(resposta.charset)
                if resposta.get("Content-Length"):
                    resposta["Content-Length"] = str(len(resposta.content))
        return resposta


# Abas do 00

class _AbaDo00(Panel):
    is_async = False

    def _comum(self):
        pedido = pedido_atual()
        codigo = pedido.codigo if pedido is not None else ""
        try:
            registros = reverse("admin:infra_vibecoding_acesso_changelist") + f"?pedido={codigo}"
        except NoReverseMatch:
            registros = ""
        return pedido, {"codigo": codigo, "registros_url": registros}


class Regras(_AbaDo00):
    title = "Regras (00)"
    template = "infra_vibecoding/rastreio/regras.html"

    @property
    def nav_subtitle(self):
        stats = self.get_stats()
        return f"{len(stats.get('regras', []))} conferida(s), {stats.get('barradas', 0)} barrada(s)"

    def generate_stats(self, request, response):
        pedido, dados = self._comum()
        regras = list(pedido.regras or []) if pedido is not None else []
        dados.update(regras=regras, barradas=sum(1 for r in regras if r["resultado"] is False))
        self.record_stats(dados)


class Historico(_AbaDo00):
    title = "Histórico dos dados (00)"
    template = "infra_vibecoding/rastreio/historico.html"

    @property
    def nav_subtitle(self):
        return f"{len(self.get_stats().get('linhas', []))} gravação(ões)"

    def generate_stats(self, request, response):
        from .models import Historico as Tabela

        _, dados = self._comum()
        linhas = []
        if dados["codigo"]:
            for h in Tabela._base_manager.filter(pedido=dados["codigo"]).order_by("id"):
                linhas.append({
                    "acao": h.nome_da_acao if h.acao == "acao" else h.get_acao_display(),
                    "tabela": h.tabela, "registro": h.registro, "rotulo": h.rotulo,
                    "quem": f"sistema ({h.motivo})" if h.como_sistema and h.motivo else h.autor,
                    "mudancas": [{"nome": str(m.get("nome", c)), "antes": str(m.get("antes") or ""),
                                  "depois": str(m.get("depois") or "")} for c, m in (h.mudancas or {}).items()],
                })
        dados.update(linhas=linhas)
        self.record_stats(dados)


class Acessos(_AbaDo00):
    title = "Acessos (00)"
    template = "infra_vibecoding/rastreio/acessos.html"

    @property
    def nav_subtitle(self):
        return f"{len(self.get_stats().get('linhas', []))} registro(s)"

    def generate_stats(self, request, response):
        pedido, dados = self._comum()
        linhas = [{"tipo": str(a.get_tipo_display()), "pessoa": a.pessoa, "detalhe": a.detalhe}
                  for a in (pedido.acessos if pedido is not None else [])]
        dados.update(linhas=linhas)
        self.record_stats(dados)
