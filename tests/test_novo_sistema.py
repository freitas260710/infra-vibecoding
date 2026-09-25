"""Testes do comando de criar sistema novo e da trava contra silenciar checagens (US 2.1)."""
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from infra_vibecoding import __version__
from infra_vibecoding.checagens import conferir_checagens_silenciadas
from infra_vibecoding.cli import main
from infra_vibecoding.novo_sistema import NomeInvalido, arquivos_do_sistema, criar_sistema, validar_nome

RAIZ = Path(__file__).resolve().parent.parent


def rodar(pasta, *args, ambiente=None):
    """Roda um comando Python dentro da pasta do sistema gerado, com o 00 desta cópia instalado."""
    env = {k: v for k, v in os.environ.items() if k not in ("DJANGO_SETTINGS_MODULE", "AMBIENTE")}
    env.update(ambiente or {})
    return subprocess.run(
        [sys.executable, *args], cwd=pasta, env=env, capture_output=True, text=True, timeout=180
    )


@pytest.fixture(scope="module")
def sistema(tmp_path_factory):
    pasta, _ = criar_sistema("sistema-teste", tmp_path_factory.mktemp("sistemas"))
    return pasta


# 1. Nome do sistema.
@pytest.mark.parametrize("nome", ["mindor", "sistema-02", "ab"])
def test_nomes_validos(nome):
    assert validar_nome(nome) == nome


@pytest.mark.parametrize(
    "nome", ["Mindor", "1sistema", "a", "meu sistema", "sistema_02", "-x", "x-", "a--b", "../fora", "django",
             "config", "infra-vibecoding"],
)
def test_nomes_invalidos(nome):
    with pytest.raises(NomeInvalido):
        validar_nome(nome)


# 2. O que é gerado.
def test_arquivos_gerados(sistema):
    esperados = set(arquivos_do_sistema("xx"))
    gerados = {str(p.relative_to(sistema)) for p in sistema.rglob("*") if p.is_file()}
    assert esperados == gerados
    assert {"CLAUDE.md", "config/settings.py", ".github/workflows/verificacao.yml", "pyproject.toml"} <= gerados


def test_settings_herda_do_00_na_primeira_linha_de_codigo(sistema):
    texto = (sistema / "config/settings.py").read_text()
    codigo = [l for l in texto.split('"""')[-1].splitlines() if l.strip()]
    assert codigo[0] == "from infra_vibecoding.configuracoes import *  # noqa: F401,F403"


def test_sistema_nasce_com_usuario_seguro(sistema):
    settings = (sistema / "config/settings.py").read_text()
    assert 'AUTH_USER_MODEL = "contas.Usuario"' in settings
    assert 'INSTALLED_APPS + ["contas"]' in settings
    assert "class Usuario(UsuarioSeguro)" in (sistema / "contas/models.py").read_text()
    assert "@politica(Usuario)" in (sistema / "contas/politicas.py").read_text()
    assert "AdminUsuarioSeguro" in (sistema / "contas/admin.py").read_text()
    assert (sistema / "contas/migrations/0001_initial.py").exists()


def test_versao_do_00_fixa_e_igual_no_pyproject_e_no_portao(sistema):
    tag = f"v{__version__}"
    pyproject = (sistema / "pyproject.toml").read_text()
    workflow = (sistema / ".github/workflows/verificacao.yml").read_text()
    assert f'tag = "{tag}"' in pyproject
    assert f"portao.yml@{tag}" in workflow
    assert "freitas260710/infra-vibecoding" in pyproject


def test_admin_em_endereco_proprio_e_diferente_por_sistema():
    a = arquivos_do_sistema("a1")["config/urls.py"]
    b = arquivos_do_sistema("a1")["config/urls.py"]
    endereco = re.search(r'path\("([^"]+)/", admin\.site\.urls\)', a).group(1)
    assert endereco.startswith("gestao-") and endereco != "admin"
    assert a != b  # cada sistema ganha um endereço sorteado


def test_workflow_do_sistema_so_chama_o_portao_do_00(sistema):
    workflow = (sistema / ".github/workflows/verificacao.yml").read_text()
    assert "uses: freitas260710/infra-vibecoding/.github/workflows/portao.yml@" in workflow
    assert "steps:" not in workflow  # nada copiado: os passos moram no 00


def test_claude_md_tem_as_regras(sistema):
    texto = (sistema / "CLAUDE.md").read_text()
    for trecho in ("ModeloSeguro", "@politica", ".para(request.user)", "@exige", "AdminSeguro",
                   "SILENCED_SYSTEM_CHECKS", "como_sistema", "self.consultar", "contas.Usuario", __version__):
        assert trecho in texto


def test_nenhuma_senha_escrita_nos_arquivos_gerados():
    for caminho, texto in arquivos_do_sistema("sem-senha").items():
        assert 'password="' not in texto, caminho
        assert "password='" not in texto, caminho


def test_nao_sobrescreve_pasta_existente(tmp_path):
    criar_sistema("repetido", tmp_path)
    with pytest.raises(FileExistsError):
        criar_sistema("repetido", tmp_path)


# 3. O sistema gerado funciona e nasce dentro do 00.
def test_sistema_gerado_passa_nas_checagens(sistema):
    r = rodar(sistema, "manage.py", "check", "--fail-level", "WARNING")
    assert r.returncode == 0, r.stdout + r.stderr


def test_sistema_gerado_passa_nas_checagens_de_producao(sistema):
    r = rodar(
        sistema, "manage.py", "check", "--deploy", "--fail-level", "WARNING",
        ambiente={"AMBIENTE": "producao", "ALLOWED_HOSTS": "exemplo.com", "SECRET_KEY": secrets.token_urlsafe(64)},
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_sistema_gerado_sem_migracao_pendente(sistema):
    r = rodar(sistema, "manage.py", "makemigrations", "--check", "--dry-run")
    assert r.returncode == 0, r.stdout + r.stderr


def test_testes_do_sistema_gerado_passam(sistema):
    r = rodar(sistema, "-m", "pytest", "-q", "-p", "no:cacheprovider")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "10 passed" in r.stdout


def test_tabela_sem_trava_no_sistema_gerado_nao_liga(tmp_path):
    pasta, _ = criar_sistema("com-falha", tmp_path)
    app = pasta / "loja"
    app.mkdir()
    (app / "__init__.py").write_text("")
    (app / "models.py").write_text(
        "from django.db import models\n\n\nclass Produto(models.Model):\n    nome = models.CharField(max_length=50)\n"
    )
    settings = pasta / "config/settings.py"
    settings.write_text(settings.read_text().replace('INSTALLED_APPS + ["contas"]', 'INSTALLED_APPS + ["contas", "loja"]'))
    r = rodar(pasta, "manage.py", "check")
    assert r.returncode != 0
    assert "SEC.E021" in r.stdout + r.stderr


def test_sistema_gerado_que_silencia_checagem_nao_liga(tmp_path):
    pasta, _ = criar_sistema("silenciado", tmp_path)
    settings = pasta / "config/settings.py"
    settings.write_text(settings.read_text() + '\nSILENCED_SYSTEM_CHECKS = ["SEC.E021"]\n')
    r = rodar(pasta, "manage.py", "check")
    assert r.returncode != 0
    assert "não podem ser silenciadas" in r.stdout + r.stderr


# 4. Trava contra silenciar checagens.
@pytest.mark.parametrize("lista", [["SEC.E022"], ["admin.E408", "SEC.E041"], ["sec.e010"], [" SEC.E072"]])
def test_silenciar_checagem_do_00_nao_liga(lista):
    with pytest.raises(ImproperlyConfigured):
        conferir_checagens_silenciadas(lista)


def test_silenciar_checagem_de_outros_e_permitido():
    conferir_checagens_silenciadas(["admin.E408", "fields.W342"])
    conferir_checagens_silenciadas([])


def test_django_nao_liga_com_checagem_do_00_silenciada():
    r = rodar(
        RAIZ, "-c", "import django; django.setup()",
        ambiente={"DJANGO_SETTINGS_MODULE": "tests.settings_silenciada", "PYTHONPATH": str(RAIZ)},
    )
    assert r.returncode != 0
    assert "SEC.E022" in r.stderr


# 5. Comando de linha.
def test_comando_cria_sistema(tmp_path, capsys):
    assert main(["novo-sistema", "pelo-comando", "--destino", str(tmp_path)]) == 0
    assert (tmp_path / "pelo-comando" / "config" / "settings.py").exists()
    assert __version__ in capsys.readouterr().out


def test_comando_recusa_pasta_existente_e_nome_invalido(tmp_path, capsys):
    assert main(["novo-sistema", "duas-vezes", "--destino", str(tmp_path)]) == 0
    assert main(["novo-sistema", "duas-vezes", "--destino", str(tmp_path)]) == 1
    assert main(["novo-sistema", "Nome Errado", "--destino", str(tmp_path)]) == 1
    assert "Erro" in capsys.readouterr().err


def test_comando_versao(capsys):
    assert main(["versao"]) == 0
    assert capsys.readouterr().out.strip() == __version__


# 6. Portão do 00, chamado pelos sistemas.
def test_portao_existe_e_so_roda_quando_chamado():
    portao = (RAIZ / ".github/workflows/portao.yml").read_text()
    assert "workflow_call:" in portao
    assert "push:" not in portao
    for passo in ("uv sync --locked", "pytest", "manage.py check", "--deploy", "makemigrations --check",
                  "pip-audit", "gitleaks"):
        assert passo in portao
