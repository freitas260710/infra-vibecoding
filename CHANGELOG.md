# Histórico de versões

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
