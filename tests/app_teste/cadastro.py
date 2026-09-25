"""Cadastro público de teste (US 3.2): cria um setor para a pessoa, como o Mindor criaria a empresa."""
from django import forms
from django.core.exceptions import ValidationError

from infra_vibecoding.login.cadastro import Cadastro

from .models import AcessoSetor, Setor


class CadastroTeste(Cadastro):
    termos_url = "/termos/"
    privacidade_url = "/privacidade/"
    campos = {
        "nome": forms.CharField(label="Seu nome", max_length=150),
        "empresa": forms.CharField(label="Nome da empresa", max_length=50),
    }

    def validar(self, dados):
        if dados.get("empresa", "").lower() == "proibida":
            raise ValidationError("Nome de empresa não permitido.")

    def ao_confirmar(self, usuario, dados, request):
        usuario.nome = dados["nome"]
        usuario.salvar_como_sistema(self.motivo(usuario))
        setor = Setor(nome=dados["empresa"])
        setor.salvar_como_sistema(self.motivo(usuario))
        AcessoSetor(usuario=usuario, setor=setor, pode_editar=True).salvar_como_sistema(self.motivo(usuario))
        if dados["empresa"] == "explode":
            raise RuntimeError("falha no meio do encaixe")


class CadastroSemTermos(Cadastro):
    pass
