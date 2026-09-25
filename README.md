# Infra Vibecoding

![verificação](https://github.com/freitas260710/infra-vibecoding/actions/workflows/verificacao.yml/badge.svg)

Motor de segurança obrigatório para sistemas Django feitos com vibecoding.

Todo sistema importa este pacote. O sistema escreve só o negócio (tabelas, regras de acesso, telas e ações) e o Infra Vibecoding faz cumprir a segurança: dados fechados por padrão, permissões checadas no servidor, telas protegidas e checagens que impedem o sistema de ligar se algo for esquecido.

Referência mínima: tudo que o Bubble.io entrega de segurança por padrão, com a diferença de que aqui o padrão é fechado.

Status: versão 0.1.3, núcleo, comando de criar sistema, regras que consultam outras tabelas e usuário seguro com login pelo e-mail. Ainda não usar em produção (faltam contas e login, arquivos, jobs, registros e o portão de deploy).

## O que o 00 faz hoje

- Travas de dados: toda tabela herda de `ModeloSeguro` e tem uma política. Ler sem dizer para quem dá erro. Tabela sem política não liga.
- Travas de ações: criar, editar e excluir exigem dizer quem está fazendo, e a política é conferida antes (inclusive no registro como está no banco e como vai ficar).
- Travas de telas: login obrigatório por padrão e toda tela declara `@publica`, `@logado` ou `@exige(acao, Model)`.
- Configurações de segurança herdadas: senha com Argon2, cookies protegidos, HTTPS e HSTS em produção, cabeçalhos de proteção, chave secreta obrigatória em produção.
- Tela de banco (admin) protegida: só administrador, tudo como sistema e registrado, endereço próprio.
- Checagens `SEC.*`: o sistema não liga se alguma trava for esquecida ou enfraquecida.
- Usuário seguro: a tabela de usuário de cada sistema herda de `UsuarioSeguro`, com login pelo e-mail e a mesma trava das outras tabelas. Checagens SEC.E081 e SEC.E082.
- Ninguém silencia as checagens `SEC.*`: se `SILENCED_SYSTEM_CHECKS` tiver alguma, o sistema não liga.
- Verificação automática no GitHub a cada envio.
- Comando que cria um sistema novo já dentro do 00, e portão que os sistemas chamam sem copiar.

## Criar um sistema novo

Na pasta onde o sistema vai ficar:

```
uvx --from "git+https://github.com/freitas260710/infra-vibecoding@v0.1.3" infra-vibecoding novo-sistema NOME
```

O sistema nasce com o 00 na mesma versão do comando (fixa no `pyproject.toml`), a tabela de usuário segura (app `contas`, login pelo e-mail), `settings.py` herdando as configurações de segurança, login obrigatório, admin num endereço próprio, `CLAUDE.md` com as regras para a IA e a verificação no GitHub chamando o portão do 00 (`.github/workflows/portao.yml`). Depois:

```
cd NOME
uv sync
uv run pytest
```

## Como um sistema usa

O comando acima já faz a instalação e a ligação. Para referência, a instalação numa versão fixa é:

```
uv add "infra-vibecoding @ git+https://github.com/freitas260710/infra-vibecoding@v0.1.3"
```

No `settings.py`, primeira linha:

```python
from infra_vibecoding.configuracoes import *  # noqa: F401,F403
```

A tabela de usuário (o comando já cria):

```python
# contas/models.py
from infra_vibecoding.usuarios import UsuarioSeguro

class Usuario(UsuarioSeguro):
    pass  # campos do sistema aqui

# settings.py
AUTH_USER_MODEL = "contas.Usuario"
```

Uma tabela e a regra dela:

```python
# models.py
from infra_vibecoding.dados import ModeloSeguro

class Pedido(ModeloSeguro):
    ...

# politicas.py
from infra_vibecoding.dados import Politica, politica
from .models import Pedido

@politica(Pedido)
class PoliticaPedido(Politica):
    def escopo(self, usuario, qs):
        return qs.filter(dono=usuario)

    def pode(self, usuario, acao, obj=None):
        return obj is not None and obj.dono_id == usuario.id
```

Uma regra que consulta outra tabela para decidir (ex.: só vê os documentos dos setores a que tem acesso):

```python
@politica(Documento)
class PoliticaDocumento(Politica):
    def escopo(self, usuario, qs):
        setores = self.consultar(AcessoSetor).filter(usuario=usuario).values("setor")
        return qs.filter(setor__in=setores)
```

`self.consultar(...)` só funciona dentro de uma política, só lê e não gera registro a cada uso. Fora da regra, dá erro.

Uma tela:

```python
from infra_vibecoding.telas import exige

@exige("criar", Pedido)
def novo_pedido(request):
    ...
```

Ler e gravar:

```python
Pedido.objects.para(request.user)             # só o que a política deixa ver
Pedido.objects.criar(request.user, dono=request.user, titulo="x")
pedido.salvar(request.user)
pedido.excluir(request.user)
```

## Próximas versões

Contas e login (cadastro, e-mail, reset, 2FA, bloqueio de tentativas), arquivos privados, jobs, registros e auditoria, portão de deploy.
