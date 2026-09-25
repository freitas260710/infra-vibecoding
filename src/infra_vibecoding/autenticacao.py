"""
Login do Infra Vibecoding (US 2.4).

O backend padrão do Django carrega o usuário da sessão com uma leitura sem dizer para quem, que a trava do 00
barra. Este backend faz o mesmo que o do Django, lendo o usuário direto pela chave, sem abrir a tabela.
Vem ligado nas configurações do 00 (AUTHENTICATION_BACKENDS) e a checagem SEC.E082 impede trocar.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class BackendSeguro(ModelBackend):
    def get_user(self, user_id):
        modelo = get_user_model()
        usuario = modelo._base_manager.filter(pk=user_id).first()
        return usuario if usuario is not None and self.user_can_authenticate(usuario) else None
