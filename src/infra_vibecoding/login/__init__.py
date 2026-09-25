"""
Login do Infra Vibecoding (US 3.1): entrar, sair, primeiro acesso, esqueci a senha e trocar a senha.

O sistema liga as telas com uma linha no config/urls.py (a checagem SEC.E083 confere):

    path("", include("infra_vibecoding.login.urls")),

Endereços: /entrar/, /sair/, /primeiro-acesso/, /esqueci-a-senha/, /trocar-senha/ e os links enviados por
e-mail (/primeiro-acesso/<id>/<código>/ e /redefinir-senha/<id>/<código>/).

Primeiro acesso seguro (D43). Substitui a senha provisória do Bubble, em que qualquer um com o e-mail tomava a conta:
- Quem abre acesso para um colega usa convidar(autor, request, email, ...). O usuário nasce SEM senha (ninguém
  sabe senha nenhuma) e recebe por e-mail um link para definir a própria senha.
- O link vale uma vez só (morre quando a senha é definida), vence sozinho (72 horas no convite, 1 hora no
  esqueci a senha) e deixa de valer se o usuário for desativado ou trocar de e-mail.
- As telas de primeiro acesso e de esqueci a senha só reenviam o link. Respondem sempre a mesma frase, para não
  revelar quais e-mails existem, e têm limite de pedidos.
- Abrir o link confirma o e-mail. Definir ou trocar a senha manda um e-mail de aviso para a pessoa.

Tela de entrar (US 3.2): "Manter conectado" (até 30 dias) e "Lembrar meu e-mail", desmarcados por padrão.
Derrubar sessões: desconectar(quem_pede, usuarios, request), conferindo a regra "desconectar" do sistema.
Cadastro público (US 3.2): desligado por padrão; o sistema liga com CADASTRO_PUBLICO no settings.py.

Visual: cada tela usa um template em infra_vibecoding/login/. O sistema troca o visual criando um arquivo com o
mesmo nome na pasta templates dele (ex.: templates/infra_vibecoding/login/entrar.html). A lógica continua no 00.
"""
from .convites import convidar, enviar_link_de_senha
from .sessoes import desconectar

__all__ = ["convidar", "desconectar", "enviar_link_de_senha"]
