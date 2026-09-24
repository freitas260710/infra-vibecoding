"""
Criação de um sistema novo já dentro do Infra Vibecoding.

    uvx --from "git+https://github.com/freitas260710/infra-vibecoding@vX.Y.Z" infra-vibecoding novo-sistema NOME

O sistema nasce com:
- o 00 instalado na mesma versão do comando (versão fixa);
- settings.py herdando as configurações de segurança do 00 (primeira linha);
- login obrigatório, tela inicial e tela de entrar já declaradas;
- admin num endereço próprio (nunca 'admin/');
- CLAUDE.md com as regras para a IA;
- verificação automática no GitHub chamando o portão que mora no 00 (não é uma cópia).

O que é gerado aqui são só as ligações com o 00. A segurança continua morando no pacote.
"""
import re
import secrets
from pathlib import Path

from . import __version__

REPOSITORIO_00 = "https://github.com/freitas260710/infra-vibecoding"
PORTAO_00 = "freitas260710/infra-vibecoding/.github/workflows/portao.yml"

_NOME_VALIDO = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
_NOMES_PROIBIDOS = {
    "infra-vibecoding", "infra", "django", "config", "tests", "test", "site", "admin", "static", "templates",
}


class NomeInvalido(ValueError):
    pass


def validar_nome(nome):
    if not _NOME_VALIDO.match(nome) or nome.endswith("-") or "--" in nome:
        raise NomeInvalido(
            f"Nome '{nome}' inválido. Use só letras minúsculas, números e hífen, começando com letra "
            "(2 a 40 caracteres). Ex.: mindor, sistema-02."
        )
    if nome in _NOMES_PROIBIDOS:
        raise NomeInvalido(f"Nome '{nome}' é reservado. Escolha outro.")
    return nome


def arquivos_do_sistema(nome, versao=__version__, endereco_admin=None):
    """Conteúdo de cada arquivo do sistema novo: {caminho relativo: texto}."""
    validar_nome(nome)
    tag = f"v{versao}"
    endereco_admin = endereco_admin or f"gestao-{secrets.token_hex(3)}"
    trocas = {
        "__NOME__": nome,
        "__TAG__": tag,
        "__VERSAO__": versao,
        "__REPOSITORIO__": REPOSITORIO_00,
        "__PORTAO__": PORTAO_00,
        "__ADMIN__": endereco_admin,
    }

    def preencher(texto):
        for chave, valor in trocas.items():
            texto = texto.replace(chave, valor)
        return texto.lstrip("\n")

    return {caminho: preencher(texto) for caminho, texto in _MODELOS.items()}


def criar_sistema(nome, destino="."):
    """Cria a pasta do sistema dentro de `destino`. Recusa se a pasta já existir."""
    validar_nome(nome)
    pasta = Path(destino).resolve() / nome
    if pasta.exists():
        raise FileExistsError(f"A pasta {pasta} já existe. Nada foi criado.")
    arquivos = arquivos_do_sistema(nome)
    for caminho, texto in arquivos.items():
        alvo = pasta / caminho
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(texto, encoding="utf-8")
    return pasta, sorted(arquivos)


# Modelos dos arquivos. Marcadores __ASSIM__ são trocados na criação.

_PYPROJECT = '''
[project]
name = "__NOME__"
version = "0.1.0"
description = "Sistema __NOME__, construído sobre o Infra Vibecoding"
requires-python = ">=3.13"
dependencies = [
    "infra-vibecoding",
]

[tool.uv]
package = false

# Versão fixa do 00. Para atualizar, trocar a tag aqui e em .github/workflows/verificacao.yml.
[tool.uv.sources]
infra-vibecoding = { git = "__REPOSITORIO__", tag = "__TAG__" }

[dependency-groups]
dev = [
    "pytest>=9.1.1",
    "pytest-django>=4.14.0",
]

[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings"
pythonpath = ["."]
testpaths = ["tests"]
'''

_PYTHON_VERSION = '''
3.13
'''

_GITIGNORE = '''
# Python
__pycache__/
*.py[oc]

# Ambiente virtual
.venv

# Banco local de desenvolvimento e arquivos gerados
db.sqlite3
staticfiles/

# Segredos
.env

# Testes
.pytest_cache/
'''

_MANAGE = '''
#!/usr/bin/env python
"""Comandos do Django para este sistema (runserver, migrate, check...)."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
'''

_CONFIG_INIT = '''
'''

_SETTINGS = '''
"""
Configurações do sistema __NOME__.

A primeira linha traz todas as configurações de segurança do Infra Vibecoding (00). Este arquivo só
acrescenta o que é do sistema: pastas, endereços, apps e banco. Enfraquecer qualquer item de segurança
faz o sistema não ligar (checagens SEC.*).
"""
from infra_vibecoding.configuracoes import *  # noqa: F401,F403
from infra_vibecoding.configuracoes import INSTALLED_APPS, TEMPLATES

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# Apps do sistema entram aqui, depois dos que vêm do 00. Ex.: + ["nucleo", "atendimento"]
INSTALLED_APPS = INSTALLED_APPS + []

TEMPLATES[0]["DIRS"] = [BASE_DIR / "templates"]

# Banco de desenvolvimento. Em produção vira Postgres (etapa 8 do 00).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LOGIN_URL = "entrar"
LOGIN_REDIRECT_URL = "inicio"
LOGOUT_REDIRECT_URL = "entrar"

STATIC_ROOT = BASE_DIR / "staticfiles"
'''

_URLS = '''
"""Endereços do sistema __NOME__. Toda tela precisa declarar quem pode abrir (SEC.E041)."""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    # Tela de banco (admin), num endereço próprio. Nunca usar 'admin/' (SEC.E072).
    path("__ADMIN__/", admin.site.urls),
    # Entrar e sair. Provisórias: as telas oficiais de conta chegam na etapa 3 do 00.
    path("entrar/", auth_views.LoginView.as_view(), name="entrar"),
    path("sair/", views.Sair.as_view(), name="sair"),
    path("", views.inicio, name="inicio"),
]
'''

_VIEWS = '''
"""Telas básicas do sistema. Toda tela declara @publica, @logado ou @exige(acao, Model)."""
from django.contrib.auth import views as auth_views
from django.shortcuts import render

from infra_vibecoding.telas import logado


@logado
def inicio(request):
    return render(request, "inicio.html")


@logado
class Sair(auth_views.LogoutView):
    pass
'''

_WSGI = '''
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()
'''

_ASGI = '''
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_asgi_application()
'''

_TPL_BASE = '''
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block titulo %}__NOME__{% endblock %}</title>
</head>
<body>
  {% block conteudo %}{% endblock %}
</body>
</html>
'''

_TPL_INICIO = '''
{% extends "base.html" %}
{% block conteudo %}
  <h1>__NOME__</h1>
  <p>Olá, {{ request.user.get_username }}.</p>
  <form method="post" action="{% url 'sair' %}">
    {% csrf_token %}
    <button type="submit">Sair</button>
  </form>
{% endblock %}
'''

_TPL_LOGIN = '''
{% extends "base.html" %}
{% block titulo %}Entrar{% endblock %}
{% block conteudo %}
  <h1>Entrar</h1>
  <form method="post">
    {% csrf_token %}
    {{ form.as_p }}
    <button type="submit">Entrar</button>
  </form>
{% endblock %}
'''

_TESTS_INIT = '''
'''

_TESTS_BASE = '''
"""Testes da base do sistema: ele nasce dentro do 00 e com as travas ligadas."""
import secrets

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client

# Senha de teste sorteada a cada execução: nenhuma senha fica escrita no código.
SENHA = secrets.token_urlsafe(16)


def test_checagens_do_00_passam():
    call_command("check", fail_level="WARNING")


def test_configuracoes_vem_do_00():
    from django.conf import settings

    assert settings.AMBIENTE == "dev"
    assert "infra_vibecoding" in settings.INSTALLED_APPS
    assert "django.contrib.auth.middleware.LoginRequiredMiddleware" in settings.MIDDLEWARE


@pytest.mark.django_db
def test_sem_login_vai_para_entrar():
    resposta = Client().get("/")
    assert resposta.status_code == 302
    assert resposta["Location"].startswith("/entrar/")


@pytest.mark.django_db
def test_tela_de_entrar_abre_sem_login():
    assert Client().get("/entrar/").status_code == 200


@pytest.mark.django_db
def test_logado_ve_a_inicial():
    usuario = get_user_model().objects.create_user("ana", password=SENHA)
    cliente = Client()
    cliente.force_login(usuario)
    assert cliente.get("/").status_code == 200


@pytest.mark.django_db
def test_admin_nao_fica_no_endereco_padrao():
    cliente = Client()
    cliente.force_login(get_user_model().objects.create_superuser("root", password=SENHA))
    assert cliente.get("/admin/").status_code == 404
'''

_WORKFLOW = '''
# Verificação automática do sistema __NOME__.
# O portão mora no Infra Vibecoding (00). Aqui o sistema só chama o portão, na mesma versão do 00
# usada no pyproject.toml. Se qualquer passo do portão falhar, fica vermelho.
name: verificacao

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  portao:
    uses: __PORTAO__@__TAG__
'''

_README = '''
# __NOME__

Sistema construído sobre o [Infra Vibecoding](__REPOSITORIO__) versão __VERSAO__.

O sistema escreve só o negócio (tabelas, regras de acesso, telas e ações). A segurança vem do 00: dados
fechados por padrão, permissões checadas no servidor, login obrigatório e checagens que impedem o sistema
de ligar se algo for esquecido.

## Rodar no Mac

```
uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

## Conferir antes de enviar

```
uv run pytest
uv run python manage.py check
```

## Endereços

- `/entrar/` e `/sair/`: provisórios, até as telas de conta do 00 (etapa 3).
- `/__ADMIN__/`: tela de banco (admin).
'''

_CLAUDE = '''
# Regras para a IA neste sistema (__NOME__)

Este sistema é construído sobre o Infra Vibecoding (o "00"), versão __VERSAO__. O 00 é um pacote importado,
igual ao Django. Toda a segurança mora nele. Este sistema escreve só o negócio.

Muitas regras abaixo o próprio 00 confere sozinho e o sistema não liga se forem quebradas. Mesmo assim,
siga todas: acertar de primeira é mais rápido do que esbarrar numa checagem.

## Dados (tabelas)
- Toda tabela herda de `infra_vibecoding.dados.ModeloSeguro`, nunca de `models.Model` (SEC.E021).
- Toda tabela tem uma política `@politica(Tabela)` no arquivo `politicas.py` do app (SEC.E022).
  `escopo(usuario, qs)` diz quais registros o usuário vê. `pode(usuario, acao, obj)` diz o que ele pode fazer.
- Ler dados: sempre `Tabela.objects.para(request.user)`. Nunca `.all()`, `.filter()` ou `.get()` direto.
- Gravar: `Tabela.objects.criar(usuario, ...)`, `obj.salvar(usuario)`, `obj.excluir(usuario)`.
- `como_sistema("motivo")` ignora as regras (igual ao "ignore privacy rules" do Bubble). Só usar com
  autorização explícita do Ed, com motivo claro. Fica registrado.
- Proibido: SQL escrito à mão (`raw`, `connection.cursor`, `extra`).

## Telas
- Toda tela declara quem pode abrir, com `infra_vibecoding.telas`: `@publica`, `@logado` ou
  `@exige("acao", Tabela)` (SEC.E041). Login é obrigatório por padrão.
- `@publica` só com autorização do Ed (ex.: entrar, cadastro, página de apresentação).
- Esconder botão ou menu na tela é só visual. A permissão é sempre conferida no servidor (política e @exige).
- Telas feitas com templates do Django e HTMX.
- Proibido: `@csrf_exempt`, `mark_safe`, `|safe` e `autoescape off` com dado vindo de usuário.

## Tela de banco (admin)
- Registrar tabelas com `admin.site.register(Tabela, AdminSeguro)` (`infra_vibecoding.admin`) (SEC.E071).
- O admin fica no endereço próprio definido em `config/urls.py`. Nunca `admin/` (SEC.E072).

## Configurações
- A primeira linha do `config/settings.py` importa as configurações do 00. Não remover (SEC.E010).
- Não redefinir nem enfraquecer nenhum item de segurança vindo do 00 (senha, cookies, HTTPS, cabeçalhos,
  middlewares, DEBUG). O sistema não liga (SEC.E011 a SEC.E020, SEC.E061 a SEC.E065).
- Nunca silenciar checagens do 00: `SILENCED_SYSTEM_CHECKS` com `SEC.*` impede o sistema de ligar.
- Segredos (chaves, senhas, tokens) nunca no código. Sempre em variável de ambiente.

## Versão do 00
- A versão do 00 fica fixa em dois lugares: `pyproject.toml` ([tool.uv.sources]) e
  `.github/workflows/verificacao.yml`. Só atualizar quando o Ed pedir, sempre os dois juntos.
- Se algo de segurança ou infra faltar no 00, não criar por conta própria no sistema. Parar e avisar o Ed:
  isso vira uma mudança no 00.

## Trabalho
- Usar `uv` para tudo (`uv add`, `uv run`). Não usar pip.
- Antes de cada commit: `uv run pytest` e `uv run python manage.py check` sem erro.
- Mudou uma tabela: `uv run python manage.py makemigrations` e incluir a migração no commit.
- Trabalhar só dentro da pasta deste sistema. Nunca `git config --global`.
- Branch principal: main. Textos, comentários e mensagens de commit em português do Brasil.
- Se um passo falhar ou uma checagem SEC.* barrar, parar e relatar. Nunca contornar.
'''

_MODELOS = {
    "pyproject.toml": _PYPROJECT,
    ".python-version": _PYTHON_VERSION,
    ".gitignore": _GITIGNORE,
    "manage.py": _MANAGE,
    "config/__init__.py": _CONFIG_INIT,
    "config/settings.py": _SETTINGS,
    "config/urls.py": _URLS,
    "config/views.py": _VIEWS,
    "config/wsgi.py": _WSGI,
    "config/asgi.py": _ASGI,
    "templates/base.html": _TPL_BASE,
    "templates/inicio.html": _TPL_INICIO,
    "templates/registration/login.html": _TPL_LOGIN,
    "tests/__init__.py": _TESTS_INIT,
    "tests/test_base.py": _TESTS_BASE,
    ".github/workflows/verificacao.yml": _WORKFLOW,
    "README.md": _README,
    "CLAUDE.md": _CLAUDE,
}
