"""
Códigos dos links enviados por e-mail (primeiro acesso e redefinição de senha).

O código é uma assinatura feita com a chave secreta do sistema sobre: o usuário, a senha guardada (ou a trava
de "sem senha"), o último login, o e-mail, se está ativo e o horário em que o link foi gerado. Por isso:
- ninguém consegue inventar um código (precisa da chave secreta);
- definiu a senha, o código morre (a senha guardada mudou);
- trocou o e-mail ou foi desativado, o código morre;
- cada tipo de link tem assinatura própria: link de redefinição não serve como convite e vice-versa;
- passou do prazo, o código morre.
"""
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.crypto import constant_time_compare
from django.utils.http import base36_to_int

HORA = 60 * 60


class GeradorDeLink(PasswordResetTokenGenerator):
    """Gerador do Django com prazo e assinatura próprios por tipo de link."""

    def __init__(self, tipo, validade_segundos):
        super().__init__()
        self.tipo = tipo
        self.validade = validade_segundos
        self.key_salt = f"infra_vibecoding.login.{tipo}"

    def _make_hash_value(self, usuario, timestamp):
        return f"{super()._make_hash_value(usuario, timestamp)}{usuario.is_active}"

    def check_token(self, usuario, token):
        if not (usuario and token):
            return False
        try:
            ts_b36, _ = token.split("-")
            ts = base36_to_int(ts_b36)
        except ValueError:
            return False
        for segredo in [self.secret, *self.secret_fallbacks]:
            if constant_time_compare(self._make_token_with_timestamp(usuario, ts, segredo), token):
                break
        else:
            return False
        idade = self._num_seconds(self._now()) - ts
        return 0 <= idade <= self.validade


LINK_CONVITE = GeradorDeLink("convite", 72 * HORA)
LINK_REDEFINIR = GeradorDeLink("redefinir", 1 * HORA)
