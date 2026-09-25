"""
Derrubar sessões (US 3.2, D48).

    from infra_vibecoding.login import desconectar

    usuarios = Usuario.objects.para(request.user).filter(empresa=request.user.empresa)
    derrubados, negados = desconectar(request.user, usuarios, request)

- Para cada usuário da lista, confere a regra do sistema: pode(quem_pede, "desconectar", usuario). No Mindor, por
  exemplo, o dono da empresa só desconecta os usuários da empresa dele. A própria pessoa sempre pode se desconectar.
- Desconectar = trocar a chave de sessão do usuário. Todas as sessões dele, em todos os navegadores e aparelhos
  (inclusive "manter conectado"), caem no próximo clique e voltam para a tela de entrar.
- Quem pede continua conectado na tela que está usando, mesmo se estiver na lista.
- Tudo fica registrado.
"""
import logging

from django.contrib.auth import update_session_auth_hash

from ..dados import pode
from ..usuarios import nova_chave_de_sessao

log = logging.getLogger("infra_vibecoding.auditoria")


def trocar_chave_de_sessao(usuario, motivo):
    """Derruba todas as sessões do usuário. Uso interno do 00 (tela de banco, desconectar)."""
    usuario.chave_de_sessao = nova_chave_de_sessao()
    usuario.salvar_como_sistema(motivo, update_fields=["chave_de_sessao"])


def desconectar(quem_pede, usuarios, request=None):
    """Derruba as sessões de cada usuário que quem_pede pode desconectar. Devolve (derrubados, negados)."""
    derrubados, negados = [], []
    autor = getattr(quem_pede, "email", quem_pede)
    for usuario in usuarios:
        if usuario.pk != quem_pede.pk and not pode(quem_pede, "desconectar", usuario):
            log.warning("login: %s tentou desconectar %s (sem permissão)", autor, usuario.email)
            negados.append(usuario)
            continue
        trocar_chave_de_sessao(usuario, f"login: {autor} desconectou {usuario.email} (todas as sessões)")
        derrubados.append(usuario)
        if request is not None and usuario.pk == quem_pede.pk:
            # Quem pediu continua conectado nesta tela.
            quem_pede.chave_de_sessao = usuario.chave_de_sessao
            update_session_auth_hash(request, quem_pede)
    return derrubados, negados
