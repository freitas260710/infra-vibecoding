# Infra Vibecoding

![verificação](https://github.com/freitas260710/infra-vibecoding/actions/workflows/verificacao.yml/badge.svg)

Motor de segurança obrigatório para sistemas Django feitos com vibecoding.

Todo sistema importa este pacote. O sistema escreve só o negócio (tabelas, regras de acesso, telas e ações) e o Infra Vibecoding faz cumprir a segurança: dados fechados por padrão, permissões checadas no servidor, telas protegidas e checagens que impedem o sistema de ligar se algo for esquecido.

Referência mínima: tudo que o Bubble.io entrega de segurança por padrão, com a diferença de que aqui o padrão é fechado.

Status: versão 0.2.6, núcleo, comando de criar sistema, regras que consultam outras tabelas, usuário seguro com login pelo e-mail, telas de login com primeiro acesso seguro, proteção contra força bruta e verificação em duas etapas. Ainda não usar em produção (faltam contas e login, arquivos, jobs, registros e o portão de deploy).

## O que o 00 faz hoje

- Travas de dados: toda tabela herda de `ModeloSeguro` e tem uma política. Ler sem dizer para quem dá erro. Tabela sem política não liga.
- Travas de ações: criar, editar e excluir exigem dizer quem está fazendo, e a política é conferida antes (inclusive no registro como está no banco e como vai ficar).
- Travas de telas: login obrigatório por padrão e toda tela declara `@publica`, `@logado` ou `@exige(acao, Model)`.
- Configurações de segurança herdadas: senha com Argon2, cookies protegidos, HTTPS e HSTS em produção, cabeçalhos de proteção, chave secreta obrigatória em produção.
- Tela de banco (admin) protegida: só administrador, tudo como sistema e registrado (inclusive filtros laterais e buscas), endereço próprio.
- Checagens `SEC.*`: o sistema não liga se alguma trava for esquecida ou enfraquecida.
- Usuário seguro: a tabela de usuário de cada sistema herda de `UsuarioSeguro`, com login pelo e-mail e a mesma trava das outras tabelas. Checagens SEC.E081 e SEC.E082.
- Telas de login do 00: entrar, sair, primeiro acesso, esqueci a senha e trocar a senha. Usuário criado por um colega nasce sem senha e define a própria senha por um link no e-mail (uso único, com prazo). Nada de senha provisória. Checagem SEC.E083.
- Tela de entrar com "Manter conectado" (até 30 dias) e "Lembrar meu e-mail". Derrubar sessões com `desconectar(quem_pede, usuarios, request)`, conferindo a regra do sistema, e "Sair de todos os meus aparelhos".
- Cadastro público (desligado por padrão): a conta só nasce depois de confirmar o e-mail e definir a senha, com aceite dos termos e da política de privacidade e o encaixe do sistema (`ao_confirmar`). Checagem SEC.E084.
- E-mail: cada sistema liga a própria conta de provedor (SMTP) por variáveis de ambiente ou `.env`. Fora de produção, todo e-mail vai só para a caixa de teste, com o destinatário original no assunto. Em produção, sem provedor e remetente de verdade o sistema não liga. Checagens SEC.E091 e SEC.E092.
- Manual da IA dentro do 00 (`REGRAS_DA_IA.md`), na versão instalada: o CLAUDE.md de cada sistema carrega o manual por uma linha que o próprio 00 coloca e corrige, em vez de copiar as regras. Checagem SEC.E101. Comandos `infra-vibecoding regras` e `infra-vibecoding novidades --desde X.Y.Z`.
- Proteção contra força bruta em tudo: limite de pedidos em todo pedido (120 por minuto por visitante, 240 por usuário), bloqueio de login por 15 minutos após 5 senhas erradas e `@limite(por_minuto=N)` para o sistema apertar ações pesadas. Checagens SEC.E066 e SEC.E067.
- Verificação em duas etapas: app autenticador (padrão) ou código por e-mail, 10 códigos de recuperação, obrigatória em produção para quem entra na tela de banco (só app) e para quem o sistema quiser (`DOIS_FATORES_OBRIGATORIO`). Nenhum login escapa do código. Checagens SEC.E068 e SEC.E069.
- Ninguém silencia as checagens `SEC.*`: se `SILENCED_SYSTEM_CHECKS` tiver alguma, o sistema não liga.
- Verificação automática no GitHub a cada envio.
- Comando que cria um sistema novo já dentro do 00, e portão que os sistemas chamam sem copiar.

## Criar um sistema novo

Na pasta onde o sistema vai ficar:

```
uvx --from "git+https://github.com/freitas260710/infra-vibecoding@v0.2.6" infra-vibecoding novo-sistema NOME
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
uv add "infra-vibecoding @ git+https://github.com/freitas260710/infra-vibecoding@v0.2.6"
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

As telas de login (o comando já liga), no `config/urls.py`:

```python
path("", include("infra_vibecoding.login.urls")),
```

Abrir acesso para um colega (confere a regra "criar" da tabela de usuário, cria sem senha e manda o link):

```python
from infra_vibecoding.login import convidar

convidar(request.user, request, email="colega@empresa.com", nome="Colega")
```

Ler e gravar:

```python
Pedido.objects.para(request.user)             # só o que a política deixa ver
Pedido.objects.criar(request.user, dono=request.user, titulo="x")
pedido.salvar(request.user)
pedido.excluir(request.user)
```

## Próximas versões

Páginas de erro, arquivos privados, jobs, registros e auditoria, portão de deploy.
