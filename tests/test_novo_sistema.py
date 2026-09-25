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


def test_sistema_nasce_com_modelo_de_env_sem_segredo_e_env_fora_do_git(sistema):
    exemplo = (sistema / ".env.exemplo").read_text()
    for linha in exemplo.splitlines():
        if linha.startswith(("EMAIL_HOST_PASSWORD", "EMAIL_HOST_USER", "EMAIL_HOST=")):
            assert linha.endswith("="), linha  # modelo vazio: nenhum dado de conta
    assert ".env" in (sistema / ".gitignore").read_text().splitlines()


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


def test_regras_da_ia_chegam_ao_sistema_pelo_manual_do_00(sistema):
    """As regras moram no manual do 00 (importado pelo CLAUDE.md), não numa cópia dentro do sistema."""
    manual = (RAIZ / "src" / "infra_vibecoding" / "REGRAS_DA_IA.md").read_text()
    for trecho in ("ModeloSeguro", "@politica", ".para(request.user)", "@exige", "AdminSeguro",
                   "SILENCED_SYSTEM_CHECKS", "como_sistema", "self.consultar", "contas.Usuario"):
        assert trecho in manual
    assert "REGRAS_DA_IA.md" in (sistema / "CLAUDE.md").read_text()


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
        ambiente={
            "AMBIENTE": "producao", "ALLOWED_HOSTS": "exemplo.com", "SECRET_KEY": secrets.token_urlsafe(64),
            "EMAIL_HOST": "smtp.exemplo.com", "EMAIL_REMETENTE": "nao-responda@exemplo.com",
        },
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


# US 3.2b: manual da IA dentro do 00, importado pelo CLAUDE.md do sistema.
def test_sistema_novo_importa_o_manual_do_00_em_vez_de_copiar(sistema):
    claude = (sistema / "CLAUDE.md").read_text()
    assert "@.venv/lib/python3.13/site-packages/infra_vibecoding/REGRAS_DA_IA.md" in claude.splitlines()
    assert "ModeloSeguro" not in claude  # as regras do 00 não são copiadas


def test_manual_da_ia_existe_e_cobre_o_essencial():
    manual = (RAIZ / "src" / "infra_vibecoding" / "REGRAS_DA_IA.md").read_text()
    for trecho in ("ModeloSeguro", "@politica", ".para(request.user)", "convidar(", "desconectar(",
                   "CADASTRO_PUBLICO", "EMAIL_BACKEND", "teste de ataque", "novidades --desde"):
        assert trecho in manual, trecho
    assert len(manual.splitlines()) < 200  # manual curto: a IA segue melhor


def _sistema_com_00_instalado(tmp_path, monkeypatch, linha_no_claude):
    from infra_vibecoding import checagens

    manual = tmp_path / ".venv" / "lib" / "python3.13" / "site-packages" / "infra_vibecoding" / "REGRAS_DA_IA.md"
    manual.parent.mkdir(parents=True)
    manual.write_text("manual")
    monkeypatch.setattr(checagens, "caminho_do_manual", lambda: manual)
    if linha_no_claude is not None:
        (tmp_path / "CLAUDE.md").write_text(f"# Regras\n\n{linha_no_claude}\n")
    return checagens


def test_claude_md_com_o_manual_passa(tmp_path, monkeypatch, settings):
    settings.BASE_DIR = tmp_path
    checagens = _sistema_com_00_instalado(
        tmp_path, monkeypatch, "@.venv/lib/python3.13/site-packages/infra_vibecoding/REGRAS_DA_IA.md"
    )
    assert checagens.sec10_manual_da_ia() == []


@pytest.mark.parametrize("linha", [None, "sem a linha", "@.venv/lib/python3.12/site-packages/infra_vibecoding/REGRAS_DA_IA.md"])
def test_claude_md_sem_o_manual_ou_com_caminho_errado_nao_liga(tmp_path, monkeypatch, settings, linha):
    settings.BASE_DIR = tmp_path
    checagens = _sistema_com_00_instalado(tmp_path, monkeypatch, linha)
    erros = checagens.sec10_manual_da_ia()
    assert [e.id for e in erros] == ["SEC.E101"]
    assert "@.venv/lib/python3.13/site-packages/infra_vibecoding/REGRAS_DA_IA.md" in erros[0].hint


def test_manual_nao_e_cobrado_em_producao(tmp_path, monkeypatch, settings):
    settings.BASE_DIR = tmp_path
    settings.AMBIENTE = "producao"
    checagens = _sistema_com_00_instalado(tmp_path, monkeypatch, None)
    assert checagens.sec10_manual_da_ia() == []


def test_comandos_regras_e_novidades(capsys):
    assert main(["novidades", "--desde", "0.2.1"]) == 0
    saida = capsys.readouterr().out
    assert "## 0.2.2" in saida and "## 0.2.1" not in saida
    assert main(["regras"]) == 0
    saida = capsys.readouterr().out
    assert "REGRAS_DA_IA.md" in saida and "Manual da IA" in saida


def test_o_proprio_00_coloca_a_linha_no_claude_md(tmp_path, monkeypatch, settings):
    settings.BASE_DIR = tmp_path
    monkeypatch.delenv("CI", raising=False)
    checagens = _sistema_com_00_instalado(tmp_path, monkeypatch, None)
    certa = "@.venv/lib/python3.13/site-packages/infra_vibecoding/REGRAS_DA_IA.md"
    # sem CLAUDE.md: cria
    assert checagens.garantir_manual_no_claude_md() is True
    assert certa in (tmp_path / "CLAUDE.md").read_text().splitlines()
    assert checagens.sec10_manual_da_ia() == []
    # já certo: não mexe
    assert checagens.garantir_manual_no_claude_md() is False
    # CLAUDE.md do sistema sem a linha: coloca logo abaixo do título, sem apagar nada
    (tmp_path / "CLAUDE.md").write_text("# Regras do Mindor\n\n- regra do negócio\n")
    assert checagens.garantir_manual_no_claude_md() is True
    texto = (tmp_path / "CLAUDE.md").read_text()
    assert texto.startswith("# Regras do Mindor\n") and "- regra do negócio" in texto and certa in texto
    # caminho antigo (outra versão do Python): troca pela linha certa
    (tmp_path / "CLAUDE.md").write_text(texto.replace("python3.13", "python3.12"))
    assert checagens.garantir_manual_no_claude_md() is True
    novo = (tmp_path / "CLAUDE.md").read_text()
    assert certa in novo and "python3.12" not in novo


@pytest.mark.parametrize("onde", ["CI", "producao"])
def test_na_verificacao_e_em_producao_o_00_nao_mexe_no_claude_md(tmp_path, monkeypatch, settings, onde):
    settings.BASE_DIR = tmp_path
    if onde == "CI":
        monkeypatch.setenv("CI", "true")
    else:
        settings.AMBIENTE = "producao"
    checagens = _sistema_com_00_instalado(tmp_path, monkeypatch, None)
    assert checagens.garantir_manual_no_claude_md() is False
    assert not (tmp_path / "CLAUDE.md").exists()
