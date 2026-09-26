# Histórico de versões

## 0.4.0

Histórico automático e código do pedido (US 6.1, etapa 6, decisões D36 e D60).

- Histórico automático de toda tabela do sistema: cada criação, alteração e exclusão vira uma linha com quando, quem
  gravou (a pessoa, ou "sistema" com o motivo), a pessoa logada no clique, a tabela, o registro e o antes/depois de
  cada campo, com o nome do campo. Funciona por qualquer caminho: telas, tela de banco, planilha, `create`,
  `update_or_create`, alterações e exclusões em massa "como sistema" (uma linha por registro afetado) e exclusões em
  cascata. Ninguém precisa lembrar de chamar.
- Tudo ou nada: a gravação e a linha do histórico entram juntas. Se o histórico falhar, a gravação não acontece.
- Senha, chave de sessão, chave do app e códigos de recuperação aparecem só como "alterada". Arquivos aparecem pelo
  nome, relações pelo nome do registro, datas em dd/mm/aaaa. A data do último login não entra.
- Ninguém altera nem apaga o histórico (nem em massa, nem pela tela de banco). Guardado para sempre.
- `registrar_acao(usuario, registro, "aprovou o chamado", detalhes)`: ações de negócio com nome amigável na mesma
  linha do tempo. Criar e cancelar link de compartilhamento já entram assim.
- Quem vê o registro vê o histórico dele: tela pronta `/historico/<app>/<tabela>/<id>/` (filtro
  `{{ registro|historico_url }}`) ou `historico_de(registro, usuario)`. Para quem não vê o registro: "não encontrado".
- Tela de banco: lista do histórico só para superusuário, só leitura, com filtros e busca. A tela única de Registros
  (histórico, acessos e erros juntos) vem na US 6.2.
- Código do pedido: cada clique ganha um código de 8 letras (cabeçalho `X-Codigo-Pedido`), gravado no histórico. O
  código do erro interno agora é o mesmo código do clique (`E-` + 8 letras), para achar tudo o que aconteceu nele.
  O código do pedido é o primeiro item do MIDDLEWARE (SEC.E131).
- Ao atualizar para esta versão: rodar `migrate` (tabela nova de histórico). Sistema que redefine MIDDLEWARE precisa
  incluir `infra_vibecoding.pedido.CodigoDoPedido` em primeiro lugar (o ideal é não redefinir).
- 466 testes automáticos.

## 0.3.1

Campo de arquivo público e link de compartilhamento (US 4.2, decisão D58).

- `CampoArquivo(publico="motivo")`: arquivo que abre sem login, em `/arquivos/publico/<id>/`, com cache no navegador. Sem motivo escrito (mínimo 10 letras), o sistema não liga. Continua com tipo conferido, tamanho e GPS apagado. Arquivos enviados enquanto o campo era privado continuam privados. Trocou o arquivo, o endereço antigo morre.
- Link de compartilhamento de arquivo privado para quem não é usuário: `compartilhar(usuario, registro, campo, dias)` ou a tela pronta `/arquivos/<id>/compartilhar/` (`{{ a.url_compartilhar }}`), com prazo (padrão 7 dias, máximo 30), lista de links ativos e cancelar.
- Fechado por padrão: só compartilha quem vê o registro E tem a ação "compartilhar" liberada na política da tabela.
- Quem recebe abre `/c/<código>/` sem login dentro do prazo. Vencido, cancelado, arquivo trocado ou registro excluído: página "Link indisponível" (410). Contagem de downloads e registro de cada download. O código do link não fica no banco (só um resumo).
- Tela de banco: lista de links de compartilhamento (só superusuário), com situação e ação de cancelar. Sem criar, editar nem planilha.
- Tabelas internas do 00 podem desligar os botões de planilha (`permite_planilha = False` no admin).
- Ao atualizar para esta versão: rodar `migrate` (tabela nova de links e campo novo em arquivos). Para liberar o compartilhamento, a política da tabela responde a ação "compartilhar".
- 439 testes automáticos.

## 0.3.0

Arquivos privados (US 4.1, etapa 4, decisões D55 e D56).

- `CampoArquivo(tipos=[...], tamanho_max_mb=N)`: campo de arquivo privado, sempre ligado a um registro. Não existe arquivo solto nem público por esquecimento.
- Envio conferido pelo conteúdo (não pelo nome): imagem, pdf, documento, planilha, apresentacao, texto, compactado, audio e video. HTML, SVG, XML e programas são sempre recusados. Imagem corrompida ou disfarçada é recusada.
- Fotos: a localização (GPS) gravada pelo celular é apagada ao enviar (LGPD); o resto dos dados da foto continua.
- Tamanho: padrão 10 MB por arquivo, até 100 MB por campo. Nenhum envio passa de 100 MB: é cortado enquanto ainda está chegando (`FILE_UPLOAD_HANDLERS`, SEC.E121).
- Limites por pessoa ou plano e cota de espaço definidos pelo sistema (`ARQUIVOS_LIMITES`, SEC.E122). O 00 guarda o tamanho de cada arquivo por espaço, para o sistema somar e cobrar.
- Baixar: `/arquivos/<id>/` só abre para quem está logado e pode ver o registro pela política, conferido a cada clique. Link vazado não abre para mais ninguém ("não encontrado", registrado). A tela de banco baixa como sistema. Resposta sem cache e protegida contra execução no navegador.
- Guardado com nome aleatório: local na pasta `arquivos_privados` do sistema (fora do Git); nos servidores, o armazenamento em `STORAGES["arquivos"]` (nuvem, etapa 8). Trocar ou remover o arquivo apaga o antigo; excluir o registro apaga os arquivos dele.
- `salvar_formulario(form, usuario)`, `anexar(registro, campo, arquivo)` e o filtro `{{ registro|arquivo:"campo" }}`.
- Registro de quem enviou e quem baixou. Tabela nova do próprio 00 (`ArquivoGuardado`), fechada: ninguém lista direto.
- Biblioteca nova no 00: Pillow (conferir imagens e apagar o GPS).
- Ao atualizar para esta versão: rodar `migrate` (tabela nova do 00). Nenhuma mudança obrigatória no sistema; o `.gitignore` do sistema deve ter `arquivos_privados/`.
- 421 testes automáticos.

## 0.2.8

Importar e exportar planilha na tela de banco, e a situação do acesso dos usuários (US I.1, decisão D53).

- Toda tabela da tela de banco ganha sozinha "Importar planilha", "Exportar CSV" e "Exportar Excel". O sistema não escreve nada.
- Exportar: sai o que está na lista, com a busca e os filtros aplicados. CSV no padrão do Excel brasileiro (ponto e vírgula, acentos certos). Protegido contra fórmula maliciosa (texto que começa com = + - @ ganha um apóstrofo). Nunca sai senha, chave de sessão, chave do 2FA ou código de recuperação.
- Importar: prévia antes de gravar (linhas novas, atualizadas, colunas ignoradas e erros por linha), tudo ou nada, linha sem "id" cria e com "id" atualiza só as colunas da planilha. Relação pelo id do registro ligado ou por um campo único dele (`empresa__cnpj`). Cada linha passa pelas regras de um cadastro manual e é gravada como sistema, com registro de quem, arquivo e tabela. Durante a conferência e a gravação aparece um carregamento com o nome e o tamanho do arquivo.
- Nunca entram por planilha: senha, chaves, 2FA, `is_staff`, `is_superuser`, datas de login e de aceite. Usuário importado nasce sem senha e nenhum e-mail sai sozinho.
- Até 20.000 linhas e 10 MB por arquivo; tipo conferido pelo conteúdo; proteção contra "bomba zip". Medido: 20.000 linhas conferidas e gravadas em menos de um minuto.
- Lista de usuários com a coluna e o filtro "Acesso": link não enviado, aguardando (com data de envio e vencimento), link vencido e senha definida. Campo novo no usuário: `link_enviado_em`.
- Bibliotecas novas no 00: openpyxl (Excel) e defusedxml (leitura segura do Excel).
- Ao atualizar para esta versão: rodar `makemigrations` (campo novo `link_enviado_em`). Se alguma tabela do sistema tiver `change_list_template` próprio no admin, ele precisa estender `infra_vibecoding/admin/change_list.html` para os botões aparecerem.
- 394 testes automáticos.

## 0.2.7

Páginas de erro em português (US 3.5).

- O 00 liga sozinho as páginas de erro, sem nada técnico na tela: 404 "não encontrado" (também para registro que a regra não deixa ver, sem confirmar que existe), 403 "sem permissão" (registrado), 403 "a página ficou aberta muito tempo" (proteção CSRF), 400 "pedido inválido" e 500 "algo deu errado" com um código curto (ex.: E-7F3K2). O mesmo código vai para o registro com o erro completo.
- Pedido feito por um pedaço da tela (HTMX): a resposta é só uma frase curta. O script `infra_vibecoding/erros.js` mostra a frase num aviso no topo da tela.
- No Mac continua a página detalhada do Django. Para ver as páginas de erro como o usuário vê: `/erros/ver/404/` (também 400, 403, 403_csrf, 429 e 500), só com DEBUG ligado.
- O sistema troca o visual criando `404.html`, `403.html`, `403_csrf.html`, `400.html` ou `500.html` na pasta templates dele. Checagens SEC.E111 (sem `handler404` etc. no urls.py), SEC.E112 (`CSRF_FAILURE_VIEW` do 00) e SEC.E113 (`500.html` mostra o código do erro).
- Ao atualizar para esta versão: nenhuma migração. Se o urls.py do sistema tiver `handler404`, `handler500` etc., apagar. Se usar HTMX, carregar o `erros.js` no base.html.
- 364 testes automáticos.

## 0.2.6

Verificação em duas etapas (US 3.4, decisão D51).

- Depois da senha, um código de 6 números. Dois métodos: app autenticador (padrão: Senhas do iPhone, Google Authenticator, Microsoft Authenticator; o código nasce no app a cada 30 segundos, sem nada ser enviado) ou código por e-mail (vale 10 minutos, uma vez só, com "reenviar" limitado). SMS fica para o futuro.
- Na tela do código vale só o método escolhido ao ativar (sem porta dos fundos para o e-mail). 10 códigos de recuperação, mostrados uma única vez e guardados como a senha. Perdeu o celular: entra com um código de recuperação e troca o método. Perdeu tudo: ação "Zerar a verificação em duas etapas" na tela de banco (derruba as sessões da pessoa e avisa por e-mail).
- Telas novas: `/entrar/codigo/` (segunda etapa do login) e `/dois-fatores/` (ligar, trocar o método, códigos novos e desligar; ligar, desligar e códigos novos pedem a senha).
- Quem é obrigado: quem entra na tela de banco, em produção, sempre e só com app (regra do 00). O sistema obriga mais gente com `DOIS_FATORES_OBRIGATORIO` (função que recebe o usuário). Obrigado sem 2FA fica preso na tela de ativar no próximo clique.
- Nenhum login escapa: trava nova no MIDDLEWARE (`infra_vibecoding.login.dois_fatores.ExigeDoisFatores`) derruba a sessão de quem tem 2FA e não passou pelo código. O login da tela de banco passa a ser a tela de entrar do 00. "Esqueci a senha" não pula o código.
- A chave do app fica cifrada no banco com a `SECRET_KEY`. Trocar a `SECRET_KEY` só com `SECRET_KEY_FALLBACKS`.
- Errar o código conta como senha errada no bloqueio de login da 0.2.5. E-mails de aviso ao ligar, trocar, desligar, zerar, gerar códigos novos e usar código de recuperação.
- Checagens SEC.E068 (trava de 2FA ligada e na ordem) e SEC.E069 (`DOIS_FATORES_OBRIGATORIO` aponta para uma função).
- Bibliotecas novas no 00: pyotp (códigos do app), segno (QR code gerado dentro do sistema) e cryptography (cifrar a chave).
- Ao atualizar para esta versão: rodar `makemigrations` (campos novos do usuário: `dois_fatores`, `dois_fatores_desde`, `segredo_do_app`, `ultimo_codigo_do_app`, `codigos_de_recuperacao`). Se o sistema redefinir MIDDLEWARE, ele não liga (SEC.E068). Se o sistema quiser obrigar 2FA por regra própria, criar a função e apontar `DOIS_FATORES_OBRIGATORIO`.
- 350 testes automáticos.

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
