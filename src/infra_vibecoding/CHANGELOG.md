# Histórico de versões

## 0.2.5

Proteção contra força bruta em tudo (US 3.3, decisão D50).

- Limite geral em todo pedido, ligado pelo 00 (`infra_vibecoding.limites.LimiteDePedidos` no MIDDLEWARE): até 120 pedidos por minuto por visitante (endereço de internet) e 240 por usuário logado. Passou: página "Muitas tentativas" (código 429), com registro.
- Login: 5 senhas erradas para o mesmo e-mail em 15 minutos bloqueiam aquele e-mail por 15 minutos; 20 tentativas erradas do mesmo endereço em 15 minutos bloqueiam o endereço. Vale também para a tela de banco. O bloqueio é temporário e não revela se o e-mail existe; "Esqueci a senha" continua funcionando.
- `@limite(por_minuto=N)` para o sistema apertar ações pesadas do negócio.
- O sistema pode apertar os limites gerais (`LIMITE_PEDIDOS_POR_ENDERECO`, `LIMITE_PEDIDOS_POR_USUARIO`), nunca afrouxar. Checagens SEC.E066 (limite ligado e na ordem) e SEC.E067 (sem afrouxar).
- Em produção, a contagem fica no banco (`DatabaseCache`, tabela criada na publicação com `createcachetable`, etapa 8). Atenção para a etapa 8: atrás do servidor de publicação, o endereço de internet verdadeiro precisa ser lido do cabeçalho do proxy confiável, senão todos os visitantes contam como um só.
- Nos testes automáticos dos sistemas, os limites gerais e o bloqueio de login ficam desligados.
- Ao atualizar para esta versão: nenhuma migração, nenhum ajuste de código. Se o sistema redefinir MIDDLEWARE, ele não liga (SEC.E066): usar o MIDDLEWARE do 00.
- 317 testes automáticos.

## 0.2.4

Manual da IA dentro do 00 (US 3.2b).

- As regras de como usar o 00 passam a morar dentro do pacote, em `REGRAS_DA_IA.md`, e viajam com cada versão. O CLAUDE.md de cada sistema carrega o manual com uma linha (`@.venv/lib/python3.13/site-packages/infra_vibecoding/REGRAS_DA_IA.md`) em vez de copiar as regras, e fica só com as regras do negócio do sistema.
- O próprio 00 coloca e corrige essa linha no CLAUDE.md quando o sistema liga no computador do desenvolvedor, e avisa no terminal. Na verificação do GitHub e em produção ele não mexe em nada: a checagem SEC.E101 confere a linha que foi enviada.
- Comandos novos: `infra-vibecoding regras` (mostra o manual e a linha) e `infra-vibecoding novidades --desde X.Y.Z` (o que mudou no 00 desde uma versão, com o que cada sistema precisa fazer).
- O histórico de versões passa a morar dentro do pacote (`src/infra_vibecoding/CHANGELOG.md`).
- Ao atualizar para esta versão: o sistema pode apagar do CLAUDE.md a cópia das regras do 00 e deixar só as regras dele. Nenhuma migração, nenhum ajuste de código.
- 298 testes automáticos.

## 0.2.3

Manter conectado, lembrar e-mail, derrubar sessões e cadastro público (US 3.2, decisões D47 e D48).

- Tela de entrar: "Manter conectado" (até 30 dias naquele navegador; sem marcar, a sessão acaba ao fechar o navegador e dura no máximo 12 horas) e "Lembrar meu e-mail" (só o e-mail, em cookie assinado que o JavaScript não lê). As duas vêm desmarcadas.
- Chave de sessão por usuário (campo novo `chave_de_sessao`): todo login fica amarrado a ela e à senha. Os sistemas precisam de uma migração; ao atualizar, todo mundo precisa entrar de novo uma vez.
- `desconectar(quem_pede, usuarios, request)`: derruba todas as sessões de cada usuário que a regra do sistema permitir (ação "desconectar"), inclusive "manter conectado". A pessoa sempre pode derrubar as próprias. Quem pede continua conectado. Tudo registrado.
- Tela de trocar a senha com "Sair de todos os meus aparelhos". Tela de banco com a ação "Desconectar de todos os aparelhos".
- Cadastro público, desligado por padrão (`CADASTRO_PUBLICO`): e-mail, campos do sistema e aceite dos termos de uso e da política de privacidade; link por e-mail (24 horas); a conta só nasce ao definir a senha, com e-mail confirmado, data do aceite (campo novo `termos_aceitos_em`) e o encaixe do sistema (`ao_confirmar`), tudo na mesma transação. Resposta sempre igual, aviso para quem já tem conta, limite de pedidos e campo-armadilha contra robôs.
- Checagem SEC.E084: cadastro público ligado precisa de uma classe de cadastro do 00 com os endereços dos termos e da política.
- 287 testes automáticos.

## 0.2.2

Envio de e-mail com provedor e desvio para a caixa de teste (US 3.1b, decisões D39 e D45).

- O 00 não tem conta em provedor nenhum: cada sistema configura a própria conta por variáveis de ambiente ou pelo arquivo `.env` (fora do Git): `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_REMETENTE` e `EMAIL_DE_TESTE`. Funciona com qualquer provedor SMTP.
- Envio do 00 (`infra_vibecoding.email.EnvioComDesvio`): fora de produção, com provedor, todo e-mail vai só para a caixa de teste, com os destinatários originais no assunto e no cabeçalho `X-Destinatario-Original`. Sem provedor, aparece no terminal. Em produção, vai para quem deve.
- Não liga: provedor fora de produção sem caixa de teste ou sem remetente; produção sem provedor ou com remetente de mentira (localhost).
- Checagens SEC.E091 (envio precisa ser o do 00) e SEC.E092 (produção com provedor e remetente de verdade).
- O arquivo `.env` da pasta do sistema é lido ao ligar (o ambiente vale mais que o arquivo).
- O portão passa a informar um provedor e um remetente de mentira no passo de checagens em modo produção.
- O comando novo-sistema cria o `.env.exemplo` e ensina no CLAUDE.md a mandar e-mail sem lógica de "está em produção?".
- 260 testes automáticos.

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
