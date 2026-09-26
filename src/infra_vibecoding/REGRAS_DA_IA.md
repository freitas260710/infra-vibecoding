# Manual da IA do Infra Vibecoding (00)

Este arquivo mora DENTRO do pacote do 00 e é atualizado junto com cada versão. Todo sistema feito sobre o 00 importa
este manual no próprio CLAUDE.md (checagem SEC.E101), em vez de copiar as regras. O CLAUDE.md do sistema fica só com
as regras do negócio dele.

O 00 é um pacote importado, igual ao Django. Toda a segurança mora nele. O sistema escreve só o negócio: tabelas,
regras de acesso, telas e ações. Muitas regras abaixo o próprio 00 confere sozinho, e o sistema não liga se forem
quebradas. Mesmo assim, siga todas: acertar de primeira é mais rápido do que esbarrar numa checagem.

"O Ed" é o responsável pelos sistemas. Onde este manual pede autorização do Ed, pare e pergunte.

## Dados (tabelas)
- Toda tabela herda de `infra_vibecoding.dados.ModeloSeguro`, nunca de `models.Model` (SEC.E021).
- Toda tabela tem uma política `@politica(Tabela)` no arquivo `politicas.py` do app (SEC.E022).
  `escopo(usuario, qs)` diz quais registros o usuário vê. `pode(usuario, acao, obj)` diz o que ele pode fazer.
- Ler dados: sempre `Tabela.objects.para(request.user)`. Nunca `.all()`, `.filter()` ou `.get()` direto.
- Gravar: `Tabela.objects.criar(usuario, ...)`, `obj.salvar(usuario)`, `obj.excluir(usuario)`.
- Dentro de uma política, para ler outra tabela (ex.: "o usuário tem perfil de Atendimento?"), use
  `self.consultar(OutraTabela)`: só leitura e só dentro da regra. Nunca `como_sistema` dentro de política.
- `como_sistema("motivo")` ignora as regras (igual ao "ignore privacy rules" do Bubble). Só usar com
  autorização explícita do Ed, com motivo claro. Fica registrado.
- Proibido: SQL escrito à mão (`raw`, `connection.cursor`, `extra`).

## Usuários
- A tabela de usuário do sistema (no sistema criado pelo comando do 00: `contas.Usuario`) herda de `UsuarioSeguro`
  do 00: login pelo e-mail, mesma trava das outras tabelas. Campos do sistema (ex.: empresa) entram nela.
- Nunca usar `django.contrib.auth.models.User`. Para se referir ao usuário: `settings.AUTH_USER_MODEL` em campos e
  `get_user_model()` no código. Ler usuários com `.para(request.user)`, como qualquer tabela.
- Abrir acesso para alguém: `convidar(request.user, request, email=..., outros campos)` de
  `infra_vibecoding.login`. Confere a regra "criar" da tabela de usuário, cria o usuário SEM senha e manda o link
  de primeiro acesso por e-mail. Quem pode abrir acesso para quem é decisão do sistema, na política.
- Nunca definir, sortear, mostrar ou mandar senha de outra pessoa. Nunca criar senha provisória. A pessoa define
  a própria senha pelo link (primeiro acesso) ou por "Esqueci a senha".
- Nunca trocar `AUTH_USER_MODEL`.

## Login
- Entrar, sair, primeiro acesso, esqueci a senha, trocar a senha e os links do e-mail são telas do 00, ligadas
  em `config/urls.py` com `path("", include("infra_vibecoding.login.urls"))` (SEC.E083). Nunca criar telas de
  login, senha ou link próprias. Não redefinir `LOGIN_URL`.
- Derrubar sessões de alguém (ex.: dono da empresa desconectando os usuários dela): `desconectar(request.user,
  usuarios, request)` de `infra_vibecoding.login`. Quem pode desconectar quem fica na política da tabela de usuário
  (ação "desconectar"). Nunca apagar sessões direto no banco.
- Cadastro público (a pessoa cria a própria conta): desligado por padrão. Só ligar com autorização do Ed. Não se
  cria tela de cadastro própria: liga-se a do 00 com `CADASTRO_PUBLICO = "app.modulo.Classe"` no settings.py, uma
  subclasse de `infra_vibecoding.login.cadastro.Cadastro` com `termos_url` e `privacidade_url` (obrigatórios,
  SEC.E084), `campos` (campos a mais do formulário), `validar(dados)` (recusar com ValidationError) e
  `ao_confirmar(usuario, dados, request)` (roda quando a conta nasce, na mesma transação; gravar com
  `salvar_como_sistema(self.motivo(usuario))`). Exemplo completo no começo de `infra_vibecoding/login/cadastro.py`.
- Verificação em duas etapas (2FA) é do 00: app autenticador (padrão) ou código por e-mail, códigos de recuperação,
  telas em `/dois-fatores/` e `/entrar/codigo/`. Nunca criar 2FA próprio, nunca fazer login por fora da tela de
  entrar (o 00 derruba sessão de quem tem 2FA e não passou pelo código) e nunca ler ou gravar os campos
  `dois_fatores`, `segredo_do_app` e `codigos_de_recuperacao`. Tela de banco em produção: obrigatório, só app
  (regra do 00). Para obrigar mais gente: `DOIS_FATORES_OBRIGATORIO = "app.modulo.funcao"` no settings.py, uma
  função que recebe o usuário e responde True/False (ex.: a empresa dele exige). Ela roda a cada pedido: manter
  simples. Perdeu o celular e os códigos: ação "Zerar a verificação em duas etapas" na tela de banco.
- Para mudar só o visual: criar no sistema `templates/infra_vibecoding/login/<tela>.html` (entrar, primeiro_acesso,
  esqueci_a_senha, definir_senha, trocar_senha, criar_conta, cadastro_senha, verificar_codigo, dois_fatores,
  ativar_app, ativar_email, codigos_de_recuperacao, desligar_dois_fatores, base), mantendo os campos do formulário
  e o `{% csrf_token %}`. Na tela ativar_app, manter `{{ qr_code }}` e `{{ chave }}`. O `base.html` do sistema
  precisa mostrar as mensagens (`messages`): as telas do 00 avisam por elas (ex.: "entrou com código de recuperação").

## Telas
- Toda tela declara quem pode abrir, com `infra_vibecoding.telas`: `@publica`, `@logado` ou
  `@exige("acao", Tabela)` (SEC.E041). Login é obrigatório por padrão.
- `@publica` só com autorização do Ed (ex.: entrar, cadastro, página de apresentação).
- Esconder botão ou menu na tela é só visual. A permissão é sempre conferida no servidor (política e @exige).
- Telas feitas com templates do Django e HTMX.
- Proibido: `@csrf_exempt`, `mark_safe`, `|safe` e `autoescape off` com dado vindo de usuário.

## Arquivos
- Arquivo enviado por usuário é sempre privado e pertence a um registro: `CampoArquivo(tipos=[...], tamanho_max_mb=N)`
  de `infra_vibecoding.arquivos` na tabela (tipos: imagem, pdf, documento, planilha, apresentacao, texto, compactado,
  audio, video; até 100 MB). Nunca usar `FileField`/`ImageField` do Django, `MEDIA_URL` ou pasta pública para
  arquivo de usuário. Vários anexos num registro: uma tabela de anexos ligada a ele, com política própria.
- Gravar formulário com arquivo: `salvar_formulario(form, request.user)` (devolve None e mostra os erros de tamanho
  e cota no próprio formulário). Em código: `anexar(registro, "campo", arquivo)` e depois `registro.salvar(usuario)`.
- Mostrar e baixar: `{% load arquivos %}` e `{{ registro|arquivo:"campo" }}` (nome, tamanho, tipo, eh_imagem, url).
  O link só abre para quem vê o registro pela política, conferido a cada clique. Nunca servir arquivo por outra view.
- Limites por pessoa ou plano e cota de espaço: `ARQUIVOS_LIMITES = "app.modulo.funcao"` no settings.py (exemplo
  no começo de `infra_vibecoding/arquivos.py`).
- Campo público (abre sem login) só com autorização do Ed e motivo escrito: `CampoArquivo(publico="motivo")`.
  Arquivos enviados enquanto o campo era privado continuam privados.
- Mandar arquivo privado para quem não é usuário: só pelo link de compartilhamento do 00 (tela pronta em
  `{{ a.url_compartilhar }}` ou `compartilhar(usuario, registro, "campo", dias)`), liberado pela ação
  "compartilhar" na política da tabela (fechado se a política não liberar). Prazo de 1 a 30 dias, cancelável.

## Páginas de erro
- As páginas de erro são do 00, em português e sem nada técnico: 404, 403, 403 de formulário vencido (CSRF), 400,
  500 (com código do erro que também vai para o registro) e 429. Nunca criar `handler404`, `handler500` etc. no
  urls.py (SEC.E111) nem `CSRF_FAILURE_VIEW` próprio (SEC.E112). Nunca mostrar erro técnico na tela.
- Visual: criar na pasta templates do sistema `404.html`, `403.html`, `403_csrf.html`, `400.html`, `500.html` ou
  `infra_vibecoding/limite.html`. O `500.html` não usa banco, usuário nem `{% url %}` e mantém `{{ codigo }}`
  (SEC.E113). Para conferir no Mac: `/erros/ver/404/` (também 400, 403, 403_csrf, 429, 500).
- Registro de outra pessoa ou empresa: buscar sempre com `.para(request.user)` e `get_object_or_404`, que responde
  "não encontrado" sem confirmar que o registro existe.
- HTMX: carregar no base.html, depois do htmx, `<script src="{% static 'infra_vibecoding/erros.js' %}" defer>`.
  Ele mostra no topo da tela a frase curta que o 00 responde quando um pedido dá erro.

## Limite de pedidos (força bruta)
- O 00 limita TODO pedido (120 por minuto por visitante, 240 por usuário logado) e bloqueia o login por 15 minutos
  depois de 5 senhas erradas (SEC.E066). Não redefinir MIDDLEWARE.
- Ações pesadas do negócio (exportar, enviar muitos e-mails, relatórios grandes) ganham um limite apertado:
  `@limite(por_minuto=N)` de `infra_vibecoding.limites`. O sistema só aperta: nunca afrouxar o limite do 00 (SEC.E067).
- Nos testes automáticos os limites ficam desligados. Nunca usar `LIMITES_NOS_TESTES` nem mexer em `mail.outbox`
  fora dos testes.

## Tela de banco (admin)
- Registrar tabelas com `admin.site.register(Tabela, AdminSeguro)` (`infra_vibecoding.admin`) (SEC.E071).
- O admin fica no endereço próprio definido em `config/urls.py`. Nunca `admin/` (SEC.E072).
- Importar e exportar planilha (CSV e Excel) já vem em toda tabela do AdminSeguro, com prévia e tudo ou nada. Nunca
  criar importação própria nem gravar dados de planilha por outro caminho. Relação na planilha: o id do registro
  ligado ou um campo único dele (`empresa__cnpj`). Para trazer dados de outro sistema, a tabela precisa de um campo
  único que identifique a origem (ex.: `id_origem`), se não houver outro. Senha, chaves, 2FA, `is_staff` e
  `is_superuser` nunca entram por planilha. Usuário importado nasce sem senha; o link sai pela ação "Enviar link de
  acesso". A coluna e o filtro "Acesso" da lista de usuários mostram quem está aguardando ou com link vencido.

## Configurações
- A primeira linha do `config/settings.py` importa as configurações do 00. Não remover (SEC.E010).
- Não redefinir nem enfraquecer nenhum item de segurança vindo do 00 (senha, cookies, HTTPS, cabeçalhos,
  middlewares, DEBUG). O sistema não liga (SEC.E011 a SEC.E020, SEC.E061 a SEC.E065).
- Nunca silenciar checagens do 00: `SILENCED_SYSTEM_CHECKS` com `SEC.*` impede o sistema de ligar.
- Segredos (chaves, senhas, tokens) nunca no código. Sempre em variável de ambiente ou no `.env` (fora do Git).
  Trocar a `SECRET_KEY` só com a antiga em `SECRET_KEY_FALLBACKS`: sem isso, as chaves do app de 2FA deixam de abrir.
- E-mail: mandar com `send_mail` do Django, normalmente. O 00 cuida do provedor e do desvio para a caixa de teste
  fora de produção. Nunca redefinir `EMAIL_BACKEND` (SEC.E091) nem escrever lógica de "está em produção?" no fluxo.

## Versão do 00
- A versão do 00 fica fixa em dois lugares: `pyproject.toml` ([tool.uv.sources]) e
  `.github/workflows/verificacao.yml`. Só atualizar quando o Ed pedir, sempre os dois juntos.
- Se algo de segurança ou infra faltar no 00, não criar por conta própria no sistema. Parar e avisar o Ed:
  isso vira uma mudança no 00.

## Testes
- Toda tabela ou tela nova vem com teste de ataque: um usuário sem permissão (ex.: de outra empresa) tentando ver,
  criar, editar ou excluir, pelo endereço e pelo formulário. O teste precisa provar que ele é barrado.
- Nunca enfraquecer um teste existente para ele passar.

## Atualizar o 00
- Ao trocar a versão do 00, ler o que mudou: `uv run infra-vibecoding novidades --desde X.Y.Z` (a versão de antes).
  Cada versão diz se precisa de migração, de ajuste no código ou de configuração nova.

## Trabalho
- Usar `uv` para tudo (`uv add`, `uv run`). Não usar pip.
- Antes de cada commit: `uv run pytest` e `uv run python manage.py check` sem erro.
- Mudou uma tabela: `uv run python manage.py makemigrations` e incluir a migração no commit.
- Trabalhar só dentro da pasta deste sistema. Nunca `git config --global`.
- Branch principal: main. Textos, comentários e mensagens de commit em português do Brasil.
- Se um passo falhar ou uma checagem SEC.* barrar, parar e relatar. Nunca contornar.
