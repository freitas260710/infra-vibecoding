"""
Tela de banco (admin do Django) protegida pelo Infra Vibecoding. Equivalente à aba Data do Bubble.

- Só entra quem é administrador do sistema (is_staff). Visitante e usuário comum vão para o login.
- Tudo que o administrador vê ou altera passa pelo 00 "como sistema" (como a aba Data do Bubble,
  que ignora as privacy rules), com registro de quem mexeu e em quê.
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
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm, AdminUserCreationForm, UserChangeForm

from .dados import ModeloSeguro


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


class AdminSeguro(_CamposRelacionadosSeguros, admin.ModelAdmin):
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
    class FormularioCriacao(AdminUserCreationForm):
        class Meta(AdminUserCreationForm.Meta):
            model = modelo
            fields = ("email",)

    return FormularioCriacao


def _formulario_edicao(modelo):
    class FormularioEdicao(UserChangeForm):
        class Meta(UserChangeForm.Meta):
            model = modelo
            fields = "__all__"

    return FormularioEdicao


class _FormularioTrocaSenha(AdminPasswordChangeForm):
    """Troca de senha pela tela de banco: grava como sistema, com registro."""

    motivo = "admin: troca de senha"

    def save(self, commit=True):
        usuario = super().save(commit=False)
        if commit:
            usuario.salvar_como_sistema(f"{self.motivo} de {usuario.get_username()}")
        return usuario


class AdminUsuarioSeguro(AdminSeguro, UserAdmin):
    """Tela de banco da tabela de usuário (login por e-mail), passando pelo 00 como as outras."""

    change_password_form = _FormularioTrocaSenha
    ordering = ("email",)
    list_display = ("email", "nome", "is_staff", "is_active")
    list_filter = ("is_staff", "is_superuser", "is_active")
    search_fields = ("email", "nome")
    readonly_fields = ("last_login", "date_joined")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Dados", {"fields": ("nome",)}),
        ("Permissões", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Datas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "usable_password", "password1", "password2")}),
    )

    def get_form(self, request, obj=None, **kwargs):
        if "form" not in kwargs:
            kwargs["form"] = _formulario_criacao(self.model) if obj is None else _formulario_edicao(self.model)
        return super().get_form(request, obj, **kwargs)

