# Histórico de versões

## 0.2.1

Correção: ninguém define a senha de outra pessoa (US 3.1a). Achado pelo Claude do projeto Mindor ao testar a 0.2.0.

- Tela de banco: a edição de usuário não tem mais o botão "Definir senha". Mostra só se a senha já foi definida pela própria pessoa ou se ainda espera o primeiro acesso. O endereço de definir senha de outro usuário responde 403 e fica registrado.
- "Alterar senha" no topo da tela de banco leva para a tela de trocar a própria senha do 00 (antes dava erro).
- Comando de terminal `changepassword` (antes dava erro de leitura sem escopo): fora de produção (Mac e dev online) troca a senha para testes, com registro e e-mail de aviso; em produção, bloqueado com mensagem clara (quem esqueceu usa "Esqueci a senha").
- O app do 00 passa a ser o primeiro de INSTALLED_APPS (os comandos de terminal dele têm prioridade).
- SEC.E073 também barra quem reabrir a definição de senha de outra pessoa na tela de banco.
- 245 testes automáticos.

## 0.2.0

Telas de login e primeiro acesso seguro (US 3.1).

- Telas do 00 em `infra_vibecoding.login`: entrar, sair (só por formulário), primeiro acesso, esqueci a senha, trocar a senha e os links do e-mail. O sistema liga com `path("", include("infra_vibecoding.login.urls"))`. Visual trocável por template, lógica no 00.
- Primeiro acesso seguro: usuário criado por outra pessoa nasce sem senha. A pessoa recebe um link por e-mail e define a própria senha. Link de uso único, com prazo (72 horas no convite, 1 hora na redefinição), que morre se o usuário for desativado ou trocar de e-mail. Link de convite não serve como redefinição e vice-versa.
- Telas de primeiro acesso e esqueci a senha respondem sempre a mesma frase (não revelam quais e-mails existem) e têm limite de pedidos (3 por e-mail e 10 por endereço por hora).
- Abrir o link confirma o e-mail (novo campo `email_confirmado_em` no `UsuarioSeguro`: os sistemas precisam de uma migração). E-mail de aviso sempre que a senha é definida ou trocada. Trocar a senha derruba as outras sessões.
- `convidar(autor, request, email, ...)`: abre acesso para um colega conferindo a regra "criar" da tabela de usuário.
- Tela de banco: criar usuário só com e-mail e nome (sem senha), com envio automático do link, e ação "Enviar link de acesso por e-mail".
- Configurações: `LOGIN_URL`, `LOGIN_REDIRECT_URL`, `LOGOUT_REDIRECT_URL` e `NOME_DO_SISTEMA` vêm do 00. No Mac, os e-mails aparecem no terminal.
- Checagens SEC.E083 (o sistema precisa usar as telas de login do 00) e SEC.E073 (a tela de banco não pode criar usuário com senha definida por outra pessoa).
- O comando novo-sistema já liga as telas de login do 00 e ensina no CLAUDE.md a nunca criar senha para outra pessoa.
- 240 testes automáticos.

## 0.1.4

Correção na tela de banco.

- As telas do AdminSeguro rodam inteiras como leitura de sistema: filtros laterais por ligação (ex.: filtrar usuários por empresa), buscas e listas de escolha deixam de dar AcessoSemEscopo. Gravações continuam exigindo "como sistema". Cada tela aberta fica registrada ("admin: <usuário> abriu <endereço>").
- 206 testes automáticos.

## 0.1.3

Usuário seguro e login pelo e-mail.

- `UsuarioSeguro` (`infra_vibecoding.usuarios`): base da tabela de usuário de todo sistema. Login pelo e-mail (sempre em minúsculas), mesma trava das outras tabelas (listar ou buscar usuários sem dizer para quem dá erro), precisa de política. `create_user` e `create_superuser` ficam registrados.
- Login pelo backend do 00 (`infra_vibecoding.autenticacao.BackendSeguro`), que carrega o usuário da sessão sem abrir a tabela. Só a data do último login e a atualização do método de guardar a senha gravam sem dizer quem.
- Tela de banco da tabela de usuário (`AdminUsuarioSeguro`), com criação e troca de senha como sistema e registradas.
- Conferência de campos únicos (ex.: e-mail repetido) funciona nos formulários sem abrir a trava.
- Checagens SEC.E081 (tabela de usuário precisa herdar de UsuarioSeguro) e SEC.E082 (login precisa ser o do 00).
- O comando novo-sistema cria o app `contas` com a tabela de usuário, a regra, a tela de banco e a migração.
- 199 testes automáticos.

## 0.1.2

Regras que consultam outras tabelas.

- `self.consultar(Tabela)` dentro de uma política: lê outra tabela para decidir (ex.: "o usuário tem perfil de Atendimento?"). Só leitura, só enquanto a regra roda (fora dela, e se a consulta for guardada e usada depois, dá AcessoSemEscopo) e sem registro de auditoria a cada uso.
- O escopo de uma política precisa devolver um filtro da própria tabela, feito a partir do qs recebido. Outra coisa dá erro.
- CLAUDE.md dos sistemas novos ensina a usar `self.consultar` e proíbe `como_sistema` dentro de política.
- 166 testes automáticos.

## 0.1.1

Comando de criar sistema e portão para os sistemas.

- `infra-vibecoding novo-sistema NOME`: cria um sistema novo já dentro do 00, com a versão do 00 fixa, `settings.py` herdando as configurações de segurança, login obrigatório, telas de entrar e sair provisórias, admin num endereço sorteado, `CLAUDE.md` com as regras para a IA e testes da base.
- Portão (`.github/workflows/portao.yml`): verificação que mora no 00 e que cada sistema chama numa versão fixa, sem copiar. Roda testes, checagens em dev e produção, migrações pendentes, pip-audit e gitleaks.
- Checagens `SEC.*` não podem ser silenciadas: `SILENCED_SYSTEM_CHECKS` com alguma delas impede o sistema de ligar.
- 144 testes automáticos.

## 0.1.0

Primeira versão oficial: o núcleo do Infra Vibecoding.

- Travas de dados: `ModeloSeguro`, políticas (`@politica`), leitura com `.para(usuario)`, leitura como sistema com motivo, SQL escrito à mão bloqueado. Checagens SEC.E021 e SEC.E022.
- Travas de ações: `pode()`, `exigir()`, `objects.criar(usuario, ...)`, `obj.salvar(usuario)`, `obj.excluir(usuario)`, gravação como sistema com motivo. Edição conferida no registro como está e como vai ficar.
- Travas de telas: `@publica`, `@logado`, `@exige(acao, Model)` e login obrigatório por padrão. Checagens SEC.E041, SEC.E061 e SEC.E062.
- Configurações de segurança herdadas (`infra_vibecoding.configuracoes`): Argon2, política de senha, cookies protegidos, HTTPS e HSTS em produção, cabeçalhos, SECRET_KEY e ALLOWED_HOSTS obrigatórios em produção. Checagens SEC.E010 a SEC.E020 e SEC.E063 a SEC.E065.
- Tela de banco protegida (`AdminSeguro`): só administrador, leitura e gravação como sistema com registro, endereço próprio. Checagens SEC.E071 e SEC.E072.
- Verificação automática no GitHub: testes, checagens em dev e produção, pip-audit, busca de e-mail pessoal e gitleaks.
- 105 testes automáticos.
