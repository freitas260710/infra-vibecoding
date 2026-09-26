"""
Tela de banco (admin do Django) protegida pelo Infra Vibecoding. Equivalente à aba Data do Bubble.

- Só entra quem é administrador do sistema (is_staff). Visitante e usuário comum vão para o login.
- Tudo que o administrador vê ou altera passa pelo 00 "como sistema" (como a aba Data do Bubble,
  que ignora as privacy rules), com registro de quem mexeu e em quê.
- Cada tela do AdminSeguro roda inteira como leitura de sistema (US 2.6): filtros laterais por ligação
  (ex.: filtrar usuários por empresa), buscas e listas de escolha funcionam. Gravações continuam exigindo
  "como sistema". Cada tela aberta fica registrada ("admin: <usuário> abriu <endereço>").
- Toda tabela do sistema registrada no admin usa AdminSeguro (checagem SEC.E071).
- O endereço não pode ser o padrão "admin/" (checagem SEC.E072). Cada sistema escolhe o seu.

Uso no sistema (arquivo admin.py do app):

    from django.contrib import admin
    from infra_vibecoding.admin import AdminSeguro
    from .models import Pedido

    admin.site.register(Pedido, AdminSeguro)

A tabela de usuário (US 2.4) usa AdminUsuarioSeguro, que também troca a senha como sistema:

    from infra_vibecoding.admin import AdminUsuarioSeguro
    admin.site.register(Usuario, AdminUsuarioSeguro)

Criar usuário pela tela de banco (US 3.1): só e-mail e nome. O usuário nasce sem senha e recebe o link de
primeiro acesso por e-mail. A ação "Enviar link de acesso por e-mail" reenvia o link para os selecionados.

Ninguém define a senha de outra pessoa (US 3.1a, 0.2.1): a edição de usuário só mostra se a senha já foi definida,
sem botão para definir; o endereço de definir senha de outro usuário responde 403 e fica registrado. "Alterar
senha" no topo da tela de banco leva para a tela de trocar a própria senha do 00.
"""
from functools import wraps

from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.forms import ReadOnlyPasswordHashField, UserChangeForm
from django.contrib.auth.hashers import UNUSABLE_PASSWORD_PREFIX
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from .dados import ModeloSeguro, _leitura_da_tela_de_banco, log


def _motivo(request, acao):
    usuario = request.user.get_username() if hasattr(request.user, "get_username") else None
    usuario = usuario or getattr(request.user, "pk", "?")
    return f"admin: {usuario} {acao}"


def _queryset_seguro(model, request):
    if issubclass(model, ModeloSeguro):
        return model.objects.como_sistema(_motivo(request, "consultou"))
    return model._default_manager.all()


class _CamposRelacionadosSeguros:
    """Listas de escolha de campos relacionados (ex.: escolher o pedido de um item) também passam pelo 00."""

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if "queryset" not in kwargs:
            kwargs["queryset"] = _queryset_seguro(db_field.remote_field.model, request)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if "queryset" not in kwargs:
            kwargs["queryset"] = _queryset_seguro(db_field.remote_field.model, request)
        return super().formfield_for_manytomany(db_field, request, **kwargs)


def _tela_como_sistema(view):
    @wraps(view)
    def tela(request, *args, **kwargs):
        log.info("%s", _motivo(request, f"abriu {request.path}"))
        with _leitura_da_tela_de_banco():
            return view(request, *args, **kwargs)

    return tela


class AdminSeguro(_CamposRelacionadosSeguros, admin.ModelAdmin):
    change_list_template = "infra_vibecoding/admin/change_list.html"
    permite_planilha = True  # botões Importar e Exportar (US I.1); tabelas internas do 00 desligam

    def get_urls(self):
        from django.urls import path

        info = self.opts.app_label, self.opts.model_name
        urls = [
            path("importar/", self.admin_site.admin_view(self.importar_planilha), name="%s_%s_importar" % info),
            path("exportar/<str:formato>/", self.admin_site.admin_view(self.exportar_planilha),
                 name="%s_%s_exportar" % info),
            *super().get_urls(),
        ]
        for padrao in urls:
            padrao.callback = _tela_como_sistema(padrao.callback)
        return urls

    # Planilhas (US I.1): exportar a lista e importar com prévia, tudo ou nada.

    def exportar_planilha(self, request, formato):
        from django.http import Http404

        from . import planilhas

        if (formato not in ("csv", "xlsx") or not self.permite_planilha
                or not self.has_view_or_change_permission(request)):
            raise Http404
        lista = self.get_changelist_instance(request)
        queryset = lista.get_queryset(request)
        resposta, total = planilhas.exportar(self.model, queryset, formato, self.opts.model_name)
        log.info("%s", _motivo(request, f"exportou {total} linha(s) de {self.opts.label} ({formato})"))
        return resposta

    def importar_planilha(self, request):
        from django.shortcuts import render
        from django.urls import reverse

        from . import planilhas

        pode_criar = self.has_add_permission(request)
        pode_atualizar = self.has_change_permission(request)
        if not self.permite_planilha or not (pode_criar or pode_atualizar):
            raise PermissionDenied
        contexto = {
            **self.admin_site.each_context(request),
            "opts": self.opts, "title": f"Importar planilha: {self.opts.verbose_name_plural}",
            "max_linhas": planilhas.MAX_LINHAS, "max_mb": planilhas.MAX_BYTES // (1024 * 1024),
            "campos": [c.name for c in planilhas.campos_da_exportacao(self.model)
                       if c.name in planilhas._campos_importaveis(self.model)],
        }
        lista = reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_changelist")
        template = "infra_vibecoding/admin/importar.html"
        if request.method != "POST":
            return render(request, template, contexto)

        token = request.POST.get("token", "")
        if "cancelar" in request.POST:
            planilhas.descartar(token)
            return redirect(lista)
        if "confirmar" in request.POST:
            guardado = planilhas.recuperar(token, self.model, request.user)
            if guardado is None:
                messages.error(request, "A prévia venceu ou não é sua. Envie o arquivo de novo.")
                return redirect(request.path)
            dados, nome = guardado["dados"], guardado["nome"]
        else:
            arquivo = request.FILES.get("arquivo")
            if arquivo is None:
                contexto["erro_do_arquivo"] = "Escolha um arquivo."
                return render(request, template, contexto)
            if arquivo.size > planilhas.MAX_BYTES:
                contexto["erro_do_arquivo"] = f"Arquivo maior que {contexto['max_mb']} MB. Divida em arquivos menores."
                return render(request, template, contexto)
            dados, nome = arquivo.read(), arquivo.name

        try:
            cabecalho, linhas = planilhas.ler_arquivo(dados)
            resultado = planilhas.conferir(self.model, cabecalho, linhas, pode_criar, pode_atualizar)
        except planilhas.ErroPlanilha as erro:
            planilhas.descartar(token)
            contexto["erro_do_arquivo"] = str(erro)
            return render(request, template, contexto)

        if "confirmar" in request.POST and resultado.ok:
            motivo = _motivo(request, f"importou a planilha '{nome}' em {self.opts.label}")
            try:
                planilhas.gravar(resultado, motivo)
            except Exception as erro:  # ex.: o banco recusou uma linha; nada ficou gravado
                log.error("%s: falhou, nada gravado (%s)", motivo, erro)
                contexto["erro_do_arquivo"] = f"O banco recusou a gravação e nada foi gravado: {erro}"
                return render(request, template, contexto)
            planilhas.descartar(token)
            log.info("%s: %s novo(s), %s atualizado(s)", motivo, resultado.novos, resultado.atualizados)
            messages.success(request, f"Planilha '{nome}' importada: {resultado.novos} novo(s) e "
                                      f"{resultado.atualizados} atualizado(s).")
            return redirect(lista)

        if "confirmar" not in request.POST and resultado.ok:
            token = planilhas.guardar_para_confirmar(dados, nome, self.model, request.user)
        contexto.update(resultado=resultado, token=token, nome_do_arquivo=nome, total_de_linhas=len(linhas))
        return render(request, template, contexto)

    def get_queryset(self, request):
        qs = self.model.objects.como_sistema(_motivo(request, "consultou"))
        ordem = self.get_ordering(request)
        return qs.order_by(*ordem) if ordem else qs

    def save_model(self, request, obj, form, change):
        obj.salvar_como_sistema(_motivo(request, "editou" if change else "criou"))

    def delete_model(self, request, obj):
        obj.excluir_como_sistema(_motivo(request, "excluiu"))

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            obj.excluir_como_sistema(_motivo(request, "excluiu em massa"))

    def save_formset(self, request, form, formset, change):
        objs = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.excluir_como_sistema(_motivo(request, "excluiu"))
        for obj in objs:
            obj.salvar_como_sistema(_motivo(request, "editou"))
        formset.save_m2m()


class _InlineSeguroBase(_CamposRelacionadosSeguros):
    def get_queryset(self, request):
        return self.model.objects.como_sistema(_motivo(request, "consultou"))


class InlineTabularSeguro(_InlineSeguroBase, admin.TabularInline):
    pass


class InlineEmpilhadoSeguro(_InlineSeguroBase, admin.StackedInline):
    pass


# Tabela de usuário (US 2.4)

def _formulario_criacao(modelo):
    class FormularioCriacao(forms.ModelForm):
        """Criação sem senha: a pessoa define a própria senha pelo link do e-mail (US 3.1)."""

        class Meta:
            model = modelo
            fields = ("email", "nome")

        def save(self, commit=True):
            usuario = super().save(commit=False)
            usuario.set_unusable_password()
            if commit:
                usuario.salvar_como_sistema("admin: criação de usuário sem senha")
            return usuario

    return FormularioCriacao


class _SituacaoDaSenha(forms.Widget):
    """Mostra só se a senha já foi definida. Sem botão: ninguém define a senha de outra pessoa."""

    template_name = "infra_vibecoding/admin/situacao_da_senha.html"
    read_only = True

    def get_context(self, name, value, attrs):
        contexto = super().get_context(name, value, attrs)
        contexto["definida"] = bool(value) and not str(value).startswith(UNUSABLE_PASSWORD_PREFIX)
        return contexto

    def id_for_label(self, id_):
        return None


class _CampoSituacaoDaSenha(ReadOnlyPasswordHashField):
    widget = _SituacaoDaSenha


def _formulario_edicao(modelo):
    class FormularioEdicao(UserChangeForm):
        password = _CampoSituacaoDaSenha(label="Senha")

        class Meta(UserChangeForm.Meta):
            model = modelo
            fields = "__all__"

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if "password" in self.fields:
                self.fields["password"].help_text = ""

    return FormularioEdicao


def trocar_propria_senha(request, extra_context=None):
    """"Alterar senha" do topo da tela de banco: vai para a tela de trocar a senha do 00 (pede a senha atual)."""
    return redirect("trocar_senha")


@login_not_required
def entrar_pela_tela_do_00(request, extra_context=None):
    """Login da tela de banco: vai para a tela de entrar do 00 (senha, bloqueio e verificação em duas etapas).

    Quem já entrou e acessa a tela de banco segue para ela. Quem já entrou mas não acessa recebe 403 (sem ficar
    indo e voltando do login)."""
    from django.conf import settings
    from django.shortcuts import resolve_url
    from django.urls import reverse
    from django.utils.http import url_has_allowed_host_and_scheme, urlencode

    destino = request.GET.get("next") or ""
    if not url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        destino = reverse("admin:index")
    if request.user.is_authenticated:
        if admin.site.has_permission(request):
            return redirect(destino)
        log.warning("%s", _motivo(request, "tentou abrir a tela de banco sem permissão"))
        raise PermissionDenied("Você não tem acesso à tela de banco.")
    return redirect(f"{resolve_url(settings.LOGIN_URL)}?{urlencode({'next': destino})}")


class FiltroAcesso(admin.SimpleListFilter):
    """Situação do acesso: link não enviado, aguardando, link vencido, senha definida (US I.1)."""

    title = "acesso"
    parameter_name = "acesso"

    def lookups(self, request, model_admin):
        return (("nao_enviado", "Link não enviado"), ("aguardando", "Aguardando primeiro acesso"),
                ("vencido", "Link vencido"), ("definida", "Senha definida"))

    def queryset(self, request, queryset):
        from django.utils import timezone

        from .login.links import LINK_CONVITE

        limite = timezone.now() - timezone.timedelta(seconds=LINK_CONVITE.validade)
        sem_senha = queryset.filter(password__startswith=UNUSABLE_PASSWORD_PREFIX)
        return {
            "nao_enviado": lambda: sem_senha.filter(link_enviado_em__isnull=True),
            "aguardando": lambda: sem_senha.filter(link_enviado_em__gte=limite),
            "vencido": lambda: sem_senha.filter(link_enviado_em__lt=limite),
            "definida": lambda: queryset.exclude(password__startswith=UNUSABLE_PASSWORD_PREFIX),
        }.get(self.value(), lambda: queryset)()


def situacao_do_acesso(usuario):
    """Texto da coluna Acesso."""
    from django.utils import timezone

    from .login.links import LINK_CONVITE

    if not usuario.is_active:
        return "Desativado"
    if usuario.has_usable_password():
        return "Senha definida"
    if usuario.link_enviado_em is None:
        return "Link não enviado"
    vence = usuario.link_enviado_em + timezone.timedelta(seconds=LINK_CONVITE.validade)
    if vence < timezone.now():
        return "Link vencido, reenviar"
    envio, fim = timezone.localtime(usuario.link_enviado_em), timezone.localtime(vence)
    return f"Aguardando: link enviado em {envio:%d/%m %H:%M}, vence em {fim:%d/%m %H:%M}"


class AdminUsuarioSeguro(AdminSeguro, UserAdmin):
    """Tela de banco da tabela de usuário (login por e-mail), passando pelo 00 como as outras."""

    ordering = ("email",)
    list_display = ("email", "nome", "acesso", "is_staff", "is_active")
    list_filter = (FiltroAcesso, "is_staff", "is_superuser", "is_active")
    search_fields = ("email", "nome")
    readonly_fields = ("last_login", "date_joined", "email_confirmado_em", "termos_aceitos_em", "dois_fatores",
                       "dois_fatores_desde", "link_enviado_em", "acesso")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Dados", {"fields": ("nome",)}),
        ("Permissões", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Acesso", {"fields": ("acesso", "link_enviado_em")}),
        ("Datas", {"fields": ("last_login", "date_joined", "email_confirmado_em", "termos_aceitos_em")}),
        ("Verificação em duas etapas", {"fields": ("dois_fatores", "dois_fatores_desde")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "nome"),
            "description": "O usuário nasce sem senha e recebe por e-mail o link para definir a própria senha.",
        }),
    )
    actions = ["enviar_link_de_acesso", "desconectar_de_todos_os_aparelhos", "zerar_verificacao_em_duas_etapas"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            from .login import enviar_link_de_senha

            enviar_link_de_senha(request, obj)
            self.message_user(request, f"Link de primeiro acesso enviado para {obj.email}.", messages.SUCCESS)

    @admin.display(description="Acesso")
    def acesso(self, obj):
        return situacao_do_acesso(obj)

    def get_list_display(self, request):
        # A coluna Acesso aparece mesmo quando o sistema define a própria lista de colunas.
        colunas = list(super().get_list_display(request))
        if "acesso" not in colunas:
            colunas.insert(min(2, len(colunas)), "acesso")
        return colunas

    def get_list_filter(self, request):
        filtros = list(super().get_list_filter(request))
        if FiltroAcesso not in filtros:
            filtros.insert(0, FiltroAcesso)
        return filtros

    def user_change_password(self, request, id, form_url=""):
        """Definir a senha de outra pessoa pela tela de banco: bloqueado (D43)."""
        log.warning("%s", _motivo(request, f"tentou definir a senha do usuário {id} pela tela de banco (bloqueado)"))
        raise PermissionDenied(
            "Ninguém define a senha de outra pessoa. Use a ação 'Enviar link de acesso por e-mail' na lista de "
            "usuários: a pessoa define a própria senha pelo link."
        )

    @admin.action(description="Desconectar de todos os aparelhos (derrubar sessões)")
    def desconectar_de_todos_os_aparelhos(self, request, queryset):
        from .login.sessoes import trocar_chave_de_sessao

        quantos = 0
        for usuario in queryset:
            trocar_chave_de_sessao(usuario, _motivo(request, f"desconectou {usuario.email} (todas as sessões)"))
            quantos += 1
            if usuario.pk == request.user.pk:
                from django.contrib.auth import update_session_auth_hash

                request.user.chave_de_sessao = usuario.chave_de_sessao
                update_session_auth_hash(request, request.user)
        self.message_user(request, f"{quantos} usuário(s) desconectado(s) de todos os aparelhos.", messages.SUCCESS)

    @admin.action(description="Zerar a verificação em duas etapas (perdeu o celular e os códigos)")
    def zerar_verificacao_em_duas_etapas(self, request, queryset):
        """A pessoa ativa de novo no próximo login. Derruba as sessões dela e avisa por e-mail. Ninguém vê a chave."""
        from django.contrib.auth import update_session_auth_hash

        from .login import dois_fatores
        from .login.sessoes import trocar_chave_de_sessao

        zerados = []
        for usuario in queryset:
            if not usuario.dois_fatores:
                continue
            dois_fatores.desligar(usuario, _motivo(request, f"zerou a verificação em duas etapas de {usuario.email}"))
            trocar_chave_de_sessao(usuario, _motivo(request, f"derrubou as sessões de {usuario.email} (2FA zerado)"))
            dois_fatores.avisar(request, usuario, "zerou")
            zerados.append(usuario.email)
            if usuario.pk == request.user.pk:
                request.user.chave_de_sessao = usuario.chave_de_sessao
                update_session_auth_hash(request, request.user)
        self.message_user(request, f"Verificação em duas etapas zerada para {len(zerados)} usuário(s).",
                          messages.SUCCESS)

    @admin.action(description="Enviar link de acesso por e-mail")
    def enviar_link_de_acesso(self, request, queryset):
        from .login import enviar_link_de_senha

        enviados = [u.email for u in queryset if enviar_link_de_senha(request, u)]
        log.info("%s", _motivo(request, f"enviou link de acesso para {', '.join(enviados) or 'ninguém'}"))
        self.message_user(request, f"Link enviado para {len(enviados)} usuário(s) ativo(s).", messages.SUCCESS)

    def get_form(self, request, obj=None, **kwargs):
        if "form" not in kwargs:
            kwargs["form"] = _formulario_criacao(self.model) if obj is None else _formulario_edicao(self.model)
        return super().get_form(request, obj, **kwargs)


# Links de compartilhamento de arquivos (US 4.2): a tela de banco lista e cancela, nunca cria nem edita.

class AdminLinkDeCompartilhamento(AdminSeguro):
    permite_planilha = False
    list_display = ("arquivo", "criado_por", "criado_em", "vence_em", "situacao", "downloads")
    list_filter = ("criado_em", "vence_em")
    search_fields = ("criado_por", "arquivo__nome")
    readonly_fields = ("arquivo", "criado_por", "criado_em", "vence_em", "cancelado_em", "cancelado_por",
                       "downloads", "ultimo_download_em")
    fields = readonly_fields
    actions = ["cancelar_links"]

    @admin.display(description="situação")
    def situacao(self, obj):
        if obj.cancelado_em:
            return "Cancelado"
        return "Ativo" if obj.ativo else "Vencido"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff and request.user.is_superuser

    @admin.action(description="Cancelar os links selecionados")
    def cancelar_links(self, request, queryset):
        from django.utils import timezone

        quantos = 0
        for link in queryset:
            if link.cancelado_em is None:
                link.cancelado_em, link.cancelado_por = timezone.now(), request.user.email
                link.salvar_como_sistema(_motivo(request, f"cancelou um link de {link.arquivo.nome}"),
                                         update_fields=["cancelado_em", "cancelado_por"])
                quantos += 1
        self.message_user(request, f"{quantos} link(s) cancelado(s).", messages.SUCCESS)


def _registrar_tabelas_do_00():
    from .models import LinkDeCompartilhamento

    if not admin.site.is_registered(LinkDeCompartilhamento):
        admin.site.register(LinkDeCompartilhamento, AdminLinkDeCompartilhamento)


_registrar_tabelas_do_00()

