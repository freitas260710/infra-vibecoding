"""Formulários das telas de login. As senhas são gravadas pelo 00, com registro de quem e por quê."""
from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, SetPasswordForm
from django.utils import timezone


class FormularioEntrar(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "E-mail ou senha incorretos.",
        "inactive": "Este acesso está desativado.",
    }

    manter_conectado = forms.BooleanField(label="Manter conectado", required=False)
    lembrar_email = forms.BooleanField(label="Lembrar meu e-mail", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "E-mail"
        self.fields["password"].label = "Senha"

    def clean(self):
        from ..limites import login_bloqueado
        from ..usuarios import normalizar_email

        if login_bloqueado(normalizar_email(self.data.get("username")), self.request):
            raise forms.ValidationError(
                "Muitas tentativas de entrar. Espere 15 minutos e tente de novo, ou use Esqueci a senha.",
                code="bloqueado",
            )
        return super().clean()


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


def formulario_de_cadastro(cadastro):
    """Formulário do cadastro público: e-mail, campos do sistema, aceite dos termos e campo-armadilha."""
    atributos = {
        "email": forms.EmailField(label="E-mail", max_length=254),
        **{nome: campo for nome, campo in cadastro.campos.items()},
        "aceite": forms.BooleanField(
            label="Li e aceito os termos de uso e a política de privacidade",
            error_messages={"required": "Para criar a conta, é preciso aceitar os termos e a política."},
        ),
        # Armadilha contra robôs: fica escondido na tela. Gente não preenche; robô preenche.
        "site": forms.CharField(label="Deixe em branco", required=False),
    }

    def clean(self):
        dados = self.cleaned_data
        if not self.errors:
            cadastro.validar({nome: dados.get(nome) for nome in cadastro.campos})
        return dados

    atributos["clean"] = clean
    return type("FormularioCadastro", (forms.Form,), atributos)


class FormularioSenhaDoCadastro(forms.Form):
    new_password1 = forms.CharField(label="Senha", widget=forms.PasswordInput, strip=False)
    new_password2 = forms.CharField(label="Senha (de novo)", widget=forms.PasswordInput, strip=False)

    def __init__(self, email, *args, **kwargs):
        self.email = email
        super().__init__(*args, **kwargs)

    def clean(self):
        dados = super().clean()
        s1, s2 = dados.get("new_password1"), dados.get("new_password2")
        if s1 and s2 and s1 != s2:
            raise forms.ValidationError("As senhas não conferem.")
        if s1:
            password_validation.validate_password(s1, get_user_model()(email=self.email))
        return dados
