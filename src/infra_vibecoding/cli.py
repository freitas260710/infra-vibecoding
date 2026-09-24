"""
Comando de linha do Infra Vibecoding.

    infra-vibecoding novo-sistema NOME [--destino PASTA]
    infra-vibecoding versao
"""
import argparse
import sys

from . import __version__
from .novo_sistema import NomeInvalido, criar_sistema


def main(argv=None):
    parser = argparse.ArgumentParser(prog="infra-vibecoding", description="Comandos do Infra Vibecoding (00).")
    sub = parser.add_subparsers(dest="comando", required=True)

    novo = sub.add_parser("novo-sistema", help="Cria um sistema novo já dentro do 00.")
    novo.add_argument("nome", help="Nome do sistema: letras minúsculas, números e hífen. Ex.: mindor")
    novo.add_argument("--destino", default=".", help="Pasta onde o sistema será criado (padrão: a atual).")

    sub.add_parser("versao", help="Mostra a versão do 00.")

    args = parser.parse_args(argv)

    if args.comando == "versao":
        print(__version__)
        return 0

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


if __name__ == "__main__":
    sys.exit(main())
