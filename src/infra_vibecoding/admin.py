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
    def get_urls(self):
        urls = super().get_urls()
        for padrao in urls:
            padrao.callback = _tela_como_sistema(padrao.callback)
        return urls

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


class AdminUsuarioSeguro(AdminSeguro, UserAdmin):
    """Tela de banco da tabela de usuário (login por e-mail), passando pelo 00 como as outras."""

    ordering = ("email",)
    list_display = ("email", "nome", "is_staff", "is_active")
    list_filter = ("is_staff", "is_superuser", "is_active")
    search_fields = ("email", "nome")
    readonly_fields = ("last_login", "date_joined", "email_confirmado_em", "termos_aceitos_em")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Dados", {"fields": ("nome",)}),
        ("Permissões", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Datas", {"fields": ("last_login", "date_joined", "email_confirmado_em", "termos_aceitos_em")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "nome"),
            "description": "O usuário nasce sem senha e recebe por e-mail o link para definir a própria senha.",
        }),
    )
    actions = ["enviar_link_de_acesso", "desconectar_de_todos_os_aparelhos"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            from .login import enviar_link_de_senha

            enviar_link_de_senha(request, obj)
            self.message_user(request, f"Link de primeiro acesso enviado para {obj.email}.", messages.SUCCESS)

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

