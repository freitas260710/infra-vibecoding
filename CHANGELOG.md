# Histórico de versões

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
