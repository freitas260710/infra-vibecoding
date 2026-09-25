"""
Comando de linha do Infra Vibecoding.

    infra-vibecoding novo-sistema NOME [--destino PASTA]
    infra-vibecoding versao
    infra-vibecoding regras                  mostra o manual da IA do 00 instalado e a linha para o CLAUDE.md
    infra-vibecoding novidades [--desde X.Y.Z]   o que mudou no 00 (desde uma versão)
"""
import argparse
import os
import re
import sys
from pathlib import Path

from . import __version__
from .novo_sistema import NomeInvalido, criar_sistema


def main(argv=None):
    parser = argparse.ArgumentParser(prog="infra-vibecoding", description="Comandos do Infra Vibecoding (00).")
    sub = parser.add_subparsers(dest="comando", required=True)

    novo = sub.add_parser("novo-sistema", help="Cria um sistema novo já dentro do 00.")
    novo.add_argument("nome", help="Nome do sistema: letras minúsculas, números e hífen. Ex.: mindor")
    novo.add_argument("--destino", default=".", help="Pasta onde o sistema será criado (padrão: a atual).")

    sub.add_parser("versao", help="Mostra a versão do 00.")
    sub.add_parser("regras", help="Mostra o manual da IA do 00 e a linha que o CLAUDE.md do sistema precisa ter.")
    nov = sub.add_parser("novidades", help="O que mudou no 00.")
    nov.add_argument("--desde", help="Versão de antes (ex.: 0.2.1): mostra só o que veio depois dela.")

    args = parser.parse_args(argv)

    if args.comando == "versao":
        print(__version__)
        return 0
    if args.comando == "regras":
        return _regras()
    if args.comando == "novidades":
        return _novidades(args.desde)

    try:
        pasta, arquivos = criar_sistema(args.nome, args.destino)
    except (NomeInvalido, FileExistsError) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1

    print(f"Sistema '{args.nome}' criado em {pasta} com o Infra Vibecoding {__version__}.")
    print("Arquivos:")
    for arquivo in arquivos:
        print(f"  {arquivo}")
    print("Próximos passos: entrar na pasta, 'uv sync' e 'uv run pytest'.")
    return 0


_PASTA = Path(__file__).resolve().parent


def _regras():
    manual = _PASTA / "REGRAS_DA_IA.md"
    linha = "@" + os.path.relpath(manual, Path.cwd()).replace(os.sep, "/")
    print(f"Linha para o CLAUDE.md do sistema (rodando na pasta do sistema):\n\n{linha}\n")
    print(manual.read_text(encoding="utf-8"))
    return 0


def _versao(texto):
    return tuple(int(p) for p in texto.split("."))


def _novidades(desde):
    texto = (_PASTA / "CHANGELOG.md").read_text(encoding="utf-8")
    partes = re.split(r"(?m)^## (\d+\.\d+\.\d+)\s*$", texto)
    saida = []
    for i in range(1, len(partes), 2):
        versao, corpo = partes[i], partes[i + 1]
        if desde is None or _versao(versao) > _versao(desde):
            saida.append(f"## {versao}\n{corpo.rstrip()}\n")
    print("\n".join(saida) if saida else f"Nada novo depois da {desde}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
