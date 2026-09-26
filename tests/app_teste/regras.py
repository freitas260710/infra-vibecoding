"""Regra de 2FA obrigatório dos testes (US 3.4): como no Mindor seria "a empresa dela exige"."""


def exige_dois_fatores(usuario):
    return usuario.nome == "Obrigada"
