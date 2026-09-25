"""
Limite de pedidos das telas que mandam e-mail (primeiro acesso e esqueci a senha).

Evita que alguém use essas telas para lotar a caixa de e-mail de uma pessoa ou para testar e-mails em massa.
Quem passa do limite recebe a mesma resposta de sempre, mas nenhum e-mail sai.

Conta pelo cache do Django. A proteção completa de login (bloqueio após senhas erradas e limite geral de
pedidos) vem na US 3.3.
"""
import hashlib

from django.core.cache import cache

POR_EMAIL = (3, 60 * 60)   # até 3 links por e-mail por hora
POR_ENDERECO = (10, 60 * 60)  # até 10 pedidos por endereço de internet (IP) por hora


def _chave(tipo, valor):
    return "infra_vibecoding:limite:" + tipo + ":" + hashlib.sha256(str(valor).encode()).hexdigest()


def dentro_do_limite(tipo, valor, maximo, janela_segundos):
    """Conta mais um pedido e responde se ainda está dentro do limite."""
    chave = _chave(tipo, valor)
    cache.add(chave, 0, janela_segundos)
    try:
        total = cache.incr(chave)
    except ValueError:  # a contagem venceu entre as duas linhas acima
        cache.set(chave, 1, janela_segundos)
        total = 1
    return total <= maximo


def endereco_de(request):
    return request.META.get("REMOTE_ADDR", "")
