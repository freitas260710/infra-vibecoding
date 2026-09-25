"""
Cadastro público (US 3.2, D47): a pessoa cria a própria conta, sem convite.

Vem DESLIGADO. O sistema liga no settings.py apontando para a classe de cadastro dele:

    CADASTRO_PUBLICO = "contas.cadastro.CadastroMindor"

    # contas/cadastro.py
    from django import forms
    from infra_vibecoding.login.cadastro import Cadastro

    class CadastroMindor(Cadastro):
        termos_url = "/termos-de-uso/"
        privacidade_url = "/politica-de-privacidade/"
        campos = {
            "nome": forms.CharField(label="Seu nome", max_length=150),
            "empresa": forms.CharField(label="Nome da empresa", max_length=150),
        }

        def ao_confirmar(self, usuario, dados, request):
            # Roda quando a conta nasce (depois de confirmar o e-mail e definir a senha), na mesma transação.
            # Aqui o sistema cria o que precisa, como sistema e com motivo (fica registrado).
            empresa = Empresa(nome_fantasia=dados["empresa"], usuario_admin=usuario, em_periodo_teste=True)
            empresa.salvar_como_sistema(self.motivo(usuario))
            ...

Fluxo: formulário (e-mail, campos do sistema, aceite dos termos) -> link por e-mail (vale 24 horas) -> a pessoa
define a senha -> só então a conta nasce, com o e-mail confirmado e a data do aceite, e roda ao_confirmar. Quem já
tem conta recebe um aviso para usar "Esqueci a senha". A tela responde sempre igual e tem limite de pedidos e um
campo-armadilha contra robôs.
"""
from django.conf import settings
from django.core import signing
from django.utils.module_loading import import_string

VALIDADE_DO_LINK = 24 * 60 * 60
_SAL = "infra_vibecoding.login.cadastro"


class Cadastro:
    """Base do cadastro público de um sistema."""

    # Endereços dos textos do sistema (obrigatórios: SEC.E084).
    termos_url = ""
    privacidade_url = ""
    # Campos a mais no formulário de cadastro: {"nome_do_campo": forms.Field(...)}
    campos = {}

    def validar(self, dados):
        """Conferências a mais do sistema. Levante django.core.exceptions.ValidationError para recusar."""

    def ao_confirmar(self, usuario, dados, request):
        """Roda quando a conta nasce, na mesma transação. Grave com salvar_como_sistema(self.motivo(usuario))."""

    @staticmethod
    def motivo(usuario):
        return f"cadastro público: {usuario.email} criou a própria conta"


def cadastro_do_sistema():
    """A classe de cadastro ligada no settings.py (instância), ou None se o cadastro público está desligado."""
    caminho = getattr(settings, "CADASTRO_PUBLICO", None)
    if not caminho:
        return None
    return import_string(caminho)()


def gerar_codigo(email, dados, termos_aceitos_em):
    return signing.dumps(
        {"email": email, "dados": dados, "termos": termos_aceitos_em}, salt=_SAL, compress=True
    )


def ler_codigo(codigo):
    """Conteúdo do link, ou None se foi alterado ou venceu."""
    try:
        return signing.loads(codigo, salt=_SAL, max_age=VALIDADE_DO_LINK)
    except signing.BadSignature:
        return None
