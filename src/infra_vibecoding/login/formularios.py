"""Formulários das telas de login. As senhas são gravadas pelo 00, com registro de quem e por quê."""
from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, SetPasswordForm
from django.utils import timezone


class FormularioEntrar(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "E-mail ou senha incorretos.",
        "inactive": "Este acesso está desativado.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "E-mail"
        self.fields["password"].label = "Senha"


class FormularioPedirLink(forms.Form):
    email = forms.EmailField(label="E-mail", max_length=254)


class FormularioDefinirSenha(SetPasswordForm):
    """Definir a senha pelo link do e-mail. Abrir o link confirma o e-mail."""

    def save(self, commit=True):
        usuario = super().save(commit=False)
        if usuario.email_confirmado_em is None:
            usuario.email_confirmado_em = timezone.now()
        if commit:
            usuario.salvar_como_sistema(f"login: {usuario.email} definiu a senha pelo link do e-mail")
        return usuario


class FormularioTrocarSenha(PasswordChangeForm):
    """Trocar a senha estando logado: pede a senha atual."""

    def save(self, commit=True):
        usuario = super().save(commit=False)
        if commit:
            usuario.salvar_como_sistema(f"login: {usuario.email} trocou a própria senha")
        return usuario
