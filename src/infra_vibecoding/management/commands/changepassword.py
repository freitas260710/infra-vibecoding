"""
Comando changepassword do Infra Vibecoding (0.2.1).

- Fora de produção (Mac e dev online): troca a senha de um usuário pelo terminal, para testes. Fica registrado e
  a pessoa recebe o e-mail de aviso (fora de produção, o e-mail não sai para ninguém de verdade).
- Em produção: bloqueado. Ninguém define senha de outra pessoa (D43). Quem esqueceu a senha usa "Esqueci a senha".

    uv run python manage.py changepassword ana@exemplo.com
"""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.management.commands.changepassword import Command as ComandoDoDjango
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError

from ...usuarios import normalizar_email

log = logging.getLogger("infra_vibecoding.auditoria")

TENTATIVAS = 3


class Command(ComandoDoDjango):
    help = "Troca a senha de um usuário pelo terminal. Só fora de produção (testes). Em produção, bloqueado."

    def handle(self, *args, **options):
        ambiente = getattr(settings, "AMBIENTE", "producao")
        if ambiente == "producao":
            raise CommandError(
                "Bloqueado em produção pelo Infra Vibecoding: ninguém define a senha de outra pessoa. "
                "Quem esqueceu a senha usa 'Esqueci a senha' na tela de entrar (/esqueci-a-senha/)."
            )
        email = normalizar_email(options.get("username") or "")
        if not email:
            raise CommandError("Informe o e-mail do usuário. Ex.: manage.py changepassword ana@exemplo.com")
        usuario = get_user_model()._base_manager.using(options["database"]).filter(email=email).first()
        if usuario is None:
            raise CommandError(f"Usuário '{email}' não existe.")

        self.stdout.write(f"Trocando a senha de {usuario.email} (ambiente {ambiente}, só para testes).")
        for _ in range(TENTATIVAS):
            senha = self._get_pass("Nova senha: ")
            if senha != self._get_pass("Nova senha (de novo): "):
                self.stderr.write("As senhas não conferem.")
                continue
            try:
                validate_password(senha, usuario)
            except ValidationError as erro:
                self.stderr.write("\n".join(erro.messages))
                continue
            break
        else:
            raise CommandError(f"Senha não trocada: {TENTATIVAS} tentativas sem sucesso.")

        usuario.set_password(senha)
        usuario.salvar_como_sistema(f"terminal: senha de {usuario.email} trocada pelo changepassword ({ambiente})")
        from ...login.convites import enviar_aviso_de_senha

        enviar_aviso_de_senha(None, usuario, primeira_vez=False)
        self.stdout.write(f"Senha de {usuario.email} trocada.")
