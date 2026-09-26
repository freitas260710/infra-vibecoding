"""
Login do Infra Vibecoding (US 2.4).

O backend padrão do Django carrega o usuário da sessão com uma leitura sem dizer para quem, que a trava do 00
barra. Este backend faz o mesmo que o do Django, lendo o usuário direto pela chave, sem abrir a tabela.
Vem ligado nas configurações do 00 (AUTHENTICATION_BACKENDS) e a checagem SEC.E082 impede trocar.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied

from . import limites
from .usuarios import normalizar_email


class BackendSeguro(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        """Login com bloqueio temporário depois de senhas erradas demais (US 3.3, infra_vibecoding.limites)."""
        modelo = get_user_model()
        email = normalizar_email(username if username is not None else kwargs.get(modelo.USERNAME_FIELD))
        if limites.login_bloqueado(email, request):
            raise PermissionDenied("Muitas tentativas de entrar. Espere 15 minutos.")
        usuario = super().authenticate(request, username=username, password=password, **kwargs)
        if usuario is None:
            from .acessos import registrar_acesso

            registrar_acesso("senha_errada", "", pessoa=email, request=request)
            limites.registrar_senha_errada(email, request)
        return usuario

    def get_user(self, user_id):
        modelo = get_user_model()
        usuario = modelo._base_manager.filter(pk=user_id).first()
        return usuario if usuario is not None and self.user_can_authenticate(usuario) else None
