"""
Criação de um sistema novo já dentro do Infra Vibecoding.

    uvx --from "git+https://github.com/freitas260710/infra-vibecoding@vX.Y.Z" infra-vibecoding novo-sistema NOME

O sistema nasce com:
- o 00 instalado na mesma versão do comando (versão fixa);
- settings.py herdando as configurações de segurança do 00 (primeira linha);
- login obrigatório, tela inicial declarada e as telas de login do 00 (entrar, primeiro acesso, esqueci a senha);
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

_ENV_EXEMPLO = '''
# Modelo do arquivo .env deste sistema. Copie para um arquivo chamado .env (na mesma pasta) e preencha.
# O .env fica fora do Git (.gitignore): chaves e senhas NUNCA vão para o código nem para o chat.
# Sem provedor de e-mail, os e-mails aparecem no terminal do runserver.

# Provedor de e-mail (dados SMTP da conta do sistema no provedor: Brevo, Mailjet, Resend...)
EMAIL_HOST=
EMAIL_PORT=587
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=

# Quem envia (endereço confirmado no provedor). Ex.: __NOME__ <nao-responda@seudominio.com.br>
EMAIL_REMETENTE=

# Caixa de teste: fora de produção, TODO e-mail vai só para ela (com o destinatário original no assunto)
EMAIL_DE_TESTE=
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

# Apps do sistema entram aqui, depois dos que vêm do 00. Ex.: + ["contas", "nucleo", "atendimento"]
INSTALLED_APPS = INSTALLED_APPS + ["contas"]

# Tabela de usuário do sistema (herda do 00: login por e-mail e trava de leitura). Não trocar depois.
AUTH_USER_MODEL = "contas.Usuario"

TEMPLATES[0]["DIRS"] = [BASE_DIR / "templates"]

# Banco de desenvolvimento. Em produção vira Postgres (etapa 8 do 00).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Nome que aparece nos e-mails do sistema (primeiro acesso, redefinição de senha).
NOME_DO_SISTEMA = "__NOME__"

# Depois de entrar, vai para a tela inicial. Entrar e sair vêm do 00 (não redefinir LOGIN_URL).
LOGIN_REDIRECT_URL = "inicio"

# Cadastro público (a pessoa cria a própria conta): desligado. Para ligar, aponte para a classe de cadastro do
# sistema (subclasse de infra_vibecoding.login.cadastro.Cadastro). Ex.: "contas.cadastro.CadastroDoSistema"
CADASTRO_PUBLICO = None

STATIC_ROOT = BASE_DIR / "staticfiles"
'''

_URLS = '''
"""Endereços do sistema __NOME__. Toda tela precisa declarar quem pode abrir (SEC.E041)."""
from django.contrib import admin
from django.urls import include, path

from . import views

urlpatterns = [
    # Tela de banco (admin), num endereço próprio. Nunca usar 'admin/' (SEC.E072).
    path("__ADMIN__/", admin.site.urls),
    # Telas de login do 00: entrar, sair, primeiro acesso, esqueci a senha, trocar a senha (SEC.E083).
    path("", include("infra_vibecoding.login.urls")),
    path("", views.inicio, name="inicio"),
]
'''

_VIEWS = '''
"""Telas básicas do sistema. Toda tela declara @publica, @logado ou @exige(acao, Model)."""
from django.shortcuts import render

from infra_vibecoding.telas import logado


@logado
def inicio(request):
    return render(request, "inicio.html")
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
  <p><a href="{% url 'trocar_senha' %}">Trocar a senha</a></p>
  <form method="post" action="{% url 'sair' %}">
    {% csrf_token %}
    <button type="submit">Sair</button>
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
    assert settings.AUTH_USER_MODEL == "contas.Usuario"


@pytest.mark.django_db
def test_sem_login_vai_para_entrar():
    resposta = Client().get("/")
    assert resposta.status_code == 302
    assert resposta["Location"].startswith("/entrar/")


@pytest.mark.django_db
def test_tela_de_entrar_abre_sem_login():
    assert Client().get("/entrar/").status_code == 200


@pytest.mark.django_db
def test_login_pelo_email():
    get_user_model().objects.create_user("ana@exemplo.com", password=SENHA)
    assert Client().login(email="ana@exemplo.com", password=SENHA)
    assert not Client().login(email="ana@exemplo.com", password=SENHA + "-errada")


@pytest.mark.django_db
def test_tela_de_entrar_com_email():
    get_user_model().objects.create_user("ana@exemplo.com", password=SENHA)
    cliente = Client()
    resposta = cliente.post("/entrar/", {"username": "ana@exemplo.com", "password": SENHA})
    assert resposta.status_code == 302 and resposta["Location"] == "/"
    assert cliente.get("/").status_code == 200


@pytest.mark.django_db
def test_primeiro_acesso_pelo_link_do_email(mailoutbox):
    import re

    get_user_model().objects.create_user("novo@exemplo.com")  # nasce sem senha
    cliente = Client()
    assert not cliente.login(email="novo@exemplo.com", password=SENHA)
    cliente.post("/primeiro-acesso/", {"email": "novo@exemplo.com"})
    link = re.search(r"http://testserver(/primeiro-acesso/\\S+)", mailoutbox[0].body).group(1)
    tela = cliente.get(link)
    cliente.post(tela["Location"], {"new_password1": SENHA, "new_password2": SENHA})
    assert cliente.get("/").status_code == 200
    assert Client().login(email="novo@exemplo.com", password=SENHA)


@pytest.mark.django_db
def test_tabela_de_usuario_tem_trava():
    from infra_vibecoding.dados import AcessoSemEscopo

    with pytest.raises(AcessoSemEscopo):
        list(get_user_model().objects.all())


@pytest.mark.django_db
def test_logado_ve_a_inicial():
    usuario = get_user_model().objects.create_user("ana@exemplo.com", password=SENHA)
    cliente = Client()
    cliente.force_login(usuario)
    assert cliente.get("/").status_code == 200


@pytest.mark.django_db
def test_admin_nao_fica_no_endereco_padrao():
    cliente = Client()
    cliente.force_login(get_user_model().objects.create_superuser("root@exemplo.com", password=SENHA))
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

- `/entrar/`, `/sair/`, `/primeiro-acesso/`, `/esqueci-a-senha/` e `/trocar-senha/`: telas de login do 00.
- `/__ADMIN__/`: tela de banco (admin). O login é pelo e-mail.

## E-mail

Sem provedor, os e-mails (primeiro acesso, redefinição de senha) aparecem no terminal do runserver. Para mandar de
verdade: copie `.env.exemplo` para `.env` e preencha com os dados SMTP do provedor, o remetente e a caixa de teste.
Fora de produção, todo e-mail vai só para a caixa de teste. O `.env` nunca vai para o Git.

## Usuários

A tabela de usuário é `contas.Usuario` (herda do 00). Para criar o primeiro administrador:
`uv run python manage.py createsuperuser`.

Os outros usuários nascem sem senha: quem cria o acesso (pela tela de banco ou por uma tela do sistema) não
define senha nenhuma. A pessoa recebe um link por e-mail e define a própria senha. No Mac, o e-mail aparece no
terminal onde o runserver está rodando.
'''

_CLAUDE = '''
# Regras para a IA neste sistema (__NOME__)

Este sistema é construído sobre o Infra Vibecoding (o "00"). As regras do 00 ficam no manual que vem dentro do
próprio 00, sempre na versão instalada. A linha abaixo carrega o manual: o próprio 00 a coloca e corrige quando o
sistema liga, e a checagem SEC.E101 confere no GitHub. Se o manual não carregar, rode `uv sync`.

@.venv/lib/python3.13/site-packages/infra_vibecoding/REGRAS_DA_IA.md

## Regras deste sistema
- Aqui entram só as regras do negócio deste sistema (nomes, telas, quem pode o quê). As regras do 00 ficam no
  manual acima: não copie para cá.
'''

_CONTAS_INIT = '''
'''

_CONTAS_APPS = '''
from django.apps import AppConfig


class ContasConfig(AppConfig):
    name = "contas"
    verbose_name = "Contas"
'''

_CONTAS_MODELS = '''
"""
Tabela de usuário do sistema. Herda do Infra Vibecoding: login pelo e-mail e a mesma trava das outras tabelas.
Os campos do sistema (ex.: empresa) entram aqui. Não trocar AUTH_USER_MODEL depois de criado.
"""
from infra_vibecoding.usuarios import UsuarioSeguro


class Usuario(UsuarioSeguro):
    pass
'''

_CONTAS_POLITICAS = '''
"""Regra da tabela de usuário. Começa fechada: cada um vê e edita só a si mesmo."""
from infra_vibecoding.dados import Politica, politica

from .models import Usuario


@politica(Usuario)
class PoliticaUsuario(Politica):
    def escopo(self, usuario, qs):
        return qs.filter(pk=usuario.pk)

    def pode(self, usuario, acao, obj=None):
        return acao == "editar" and obj is not None and obj.pk == usuario.pk
'''

_CONTAS_ADMIN = '''
from django.contrib import admin

from infra_vibecoding.admin import AdminUsuarioSeguro

from .models import Usuario

admin.site.register(Usuario, AdminUsuarioSeguro)
'''

_CONTAS_MIGRACOES_INIT = '''
'''

_CONTAS_MIGRACAO_0001 = '''
# Criada pelo comando novo-sistema do Infra Vibecoding (tabela de usuário do sistema).

import django.utils.timezone
import infra_vibecoding.usuarios
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="Usuario",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                (
                    "last_login",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="last login"
                    ),
                ),
                (
                    "is_superuser",
                    models.BooleanField(
                        default=False,
                        help_text="Designates that this user has all permissions without explicitly assigning them.",
                        verbose_name="superuser status",
                    ),
                ),
                (
                    "email",
                    models.EmailField(
                        max_length=254, unique=True, verbose_name="e-mail"
                    ),
                ),
                (
                    "nome",
                    models.CharField(blank=True, max_length=150, verbose_name="nome"),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="ativo")),
                (
                    "is_staff",
                    models.BooleanField(
                        default=False, verbose_name="acessa a tela de banco"
                    ),
                ),
                (
                    "date_joined",
                    models.DateTimeField(
                        default=django.utils.timezone.now, verbose_name="criado em"
                    ),
                ),
                (
                    "email_confirmado_em",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="e-mail confirmado em"
                    ),
                ),
                (
                    "chave_de_sessao",
                    models.CharField(
                        default=infra_vibecoding.usuarios.nova_chave_de_sessao,
                        editable=False,
                        max_length=64,
                        verbose_name="chave de sessão",
                    ),
                ),
                (
                    "termos_aceitos_em",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="termos aceitos em"
                    ),
                ),
                (
                    "groups",
                    models.ManyToManyField(
                        blank=True,
                        help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.group",
                        verbose_name="groups",
                    ),
                ),
                (
                    "user_permissions",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Specific permissions for this user.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.permission",
                        verbose_name="user permissions",
                    ),
                ),
            ],
            options={
                "verbose_name": "usuário",
                "verbose_name_plural": "usuários",
                "abstract": False,
            },
        ),
    ]
'''

_MODELOS = {
    "pyproject.toml": _PYPROJECT,
    ".python-version": _PYTHON_VERSION,
    ".gitignore": _GITIGNORE,
    ".env.exemplo": _ENV_EXEMPLO,
    "manage.py": _MANAGE,
    "config/__init__.py": _CONFIG_INIT,
    "config/settings.py": _SETTINGS,
    "config/urls.py": _URLS,
    "config/views.py": _VIEWS,
    "config/wsgi.py": _WSGI,
    "config/asgi.py": _ASGI,
    "templates/base.html": _TPL_BASE,
    "templates/inicio.html": _TPL_INICIO,
    "contas/__init__.py": _CONTAS_INIT,
    "contas/apps.py": _CONTAS_APPS,
    "contas/models.py": _CONTAS_MODELS,
    "contas/politicas.py": _CONTAS_POLITICAS,
    "contas/admin.py": _CONTAS_ADMIN,
    "contas/migrations/__init__.py": _CONTAS_MIGRACOES_INIT,
    "contas/migrations/0001_initial.py": _CONTAS_MIGRACAO_0001,
    "tests/__init__.py": _TESTS_INIT,
    "tests/test_base.py": _TESTS_BASE,
    ".github/workflows/verificacao.yml": _WORKFLOW,
    "README.md": _README,
    "CLAUDE.md": _CLAUDE,
}
