"""
Usuário seguro do Infra Vibecoding (US 2.4). Equivalente ao tipo User do Bubble, porém fechado por padrão.

Todo sistema tem uma tabela de usuário própria que herda daqui (o Django recomenda criar a própria tabela de
usuário no início do projeto). O comando novo-sistema já cria o app "contas" com ela:

    # contas/models.py
    from infra_vibecoding.usuarios import UsuarioSeguro

    class Usuario(UsuarioSeguro):
        pass            # o sistema acrescenta os campos dele aqui (ex.: empresa)

    # settings.py
    AUTH_USER_MODEL = "contas.Usuario"

O que muda em relação ao usuário padrão do Django:
- Login pelo e-mail (guardado sempre em minúsculas). Não existe nome de usuário.
- A tabela tem a mesma trava das outras (ModeloSeguro): listar ou buscar usuários sem dizer para quem dá
  AcessoSemEscopo. Precisa de @politica(Usuario), como qualquer tabela.
- Só o login busca alguém pelo e-mail exato (get_by_natural_key), e só o backend do 00 carrega o usuário da
  sessão a cada pedido (infra_vibecoding.autenticacao.BackendSeguro).
- Criar usuário: Usuario.objects.create_user(email, senha) e create_superuser(email, senha). Ficam registrados.
- Usuário criado sem senha nasce com a senha travada (ninguém entra). A pessoa define a própria senha pelo link
  de primeiro acesso enviado por e-mail (US 3.1, infra_vibecoding.login.convidar).
- email_confirmado_em: preenchido quando a pessoa abre um link recebido no e-mail (prova de que o e-mail é dela).
- Gravações liberadas sem dizer quem: só a data do último login (feita pelo próprio login) e a troca do método
  de guardar a senha durante a conferência da senha. Todo o resto usa salvar(usuario) ou salvar_como_sistema.
"""
import logging

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone

from .dados import GerenciadorSeguro, ModeloSeguro, _autorizar

log = logging.getLogger("infra_vibecoding.auditoria")


def normalizar_email(email):
    return (email or "").strip().lower()


class GerenciadorUsuarios(GerenciadorSeguro):
    """Gerenciador da tabela de usuário: trava de leitura igual às outras tabelas, mais o que o login precisa."""

    @classmethod
    def normalize_email(cls, email):
        return normalizar_email(email)

    def get_by_natural_key(self, email):
        """Busca pelo e-mail exato. Usado só pelo login e pelo comando createsuperuser."""
        return self.model._base_manager.using(self._db).get(
            **{self.model.USERNAME_FIELD: normalizar_email(email)}
        )

    def _criar(self, email, password, motivo, **campos):
        if not email:
            raise ValueError("O e-mail é obrigatório.")
        usuario = self.model(email=normalizar_email(email), **campos)
        usuario.set_password(password)
        log.info("criação de usuário: %s (%s)", usuario.email, motivo)
        with _autorizar(usuario):
            usuario.save(using=self._db)
        return usuario

    def create_user(self, email, password=None, **campos):
        campos.setdefault("is_staff", False)
        campos.setdefault("is_superuser", False)
        return self._criar(email, password, "create_user", **campos)

    def create_superuser(self, email, password=None, **campos):
        campos["is_staff"] = True
        campos["is_superuser"] = True
        return self._criar(email, password, "create_superuser", **campos)


# Campos que podem ser gravados sem dizer quem: só a data do último login (o próprio login grava).
_GRAVACOES_DO_LOGIN = frozenset({"last_login"})


class UsuarioSeguro(ModeloSeguro, AbstractBaseUser, PermissionsMixin):
    """Base da tabela de usuário de todo sistema que usa o Infra Vibecoding."""

    email = models.EmailField("e-mail", unique=True)
    nome = models.CharField("nome", max_length=150, blank=True)
    is_active = models.BooleanField("ativo", default=True)
    is_staff = models.BooleanField("acessa a tela de banco", default=False)
    date_joined = models.DateTimeField("criado em", default=timezone.now)
    email_confirmado_em = models.DateTimeField("e-mail confirmado em", null=True, blank=True)

    objects = GerenciadorUsuarios()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        abstract = True
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    def __str__(self):
        return self.email

    def clean(self):
        super().clean()
        self.email = normalizar_email(self.email)

    def get_full_name(self):
        return self.nome or self.email

    def get_short_name(self):
        return (self.nome or self.email).split(" ")[0]

    def check_password(self, raw_password):
        # Se o método de guardar a senha mudou, o Django regrava a senha aqui. Só isso é liberado.
        with _autorizar(self):
            return super().check_password(raw_password)

    def save(self, *args, **kwargs):
        self.email = normalizar_email(self.email)
        if self._state.adding and not self.password:
            # Nasce sem senha: senha travada. Só entra depois de definir pelo link do e-mail (US 3.1).
            self.set_unusable_password()
        campos = kwargs.get("update_fields")
        if campos is not None and set(campos) <= _GRAVACOES_DO_LOGIN and not self._state.adding:
            with _autorizar(self):
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)
