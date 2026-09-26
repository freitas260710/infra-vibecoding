"""Regra de 2FA obrigatório dos testes (US 3.4): como no Mindor seria "a empresa dela exige"."""


def exige_dois_fatores(usuario):
    return usuario.nome == "Obrigada"


def limites_de_arquivo(usuario, registro, campo):
    """Limites de arquivo dos testes (US 4.1): como o Mindor faria por plano da empresa."""
    dono = registro.pedido.dono
    if dono.nome == "Plano pequeno":
        return {"por_arquivo": 1000, "espaco": f"dono-{dono.pk}", "total": 3000}
    return {"espaco": f"dono-{dono.pk}"}
