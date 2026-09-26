"""
Arquivos privados do Infra Vibecoding (US 4.1, decisões D55 e D56). Equivalente ao arquivo "private" do Bubble,
só que obrigatório: não existe arquivo solto nem público por esquecimento.

No sistema, a tabela declara o campo:

    from infra_vibecoding.arquivos import CampoArquivo

    class Chamado(ModeloSeguro):
        ...
        print_do_erro = CampoArquivo(tipos=["imagem", "pdf"], tamanho_max_mb=10)

- Tipos (famílias): imagem (jpg, png, gif, webp), pdf, documento (docx, doc, odt), planilha (xlsx, xls, ods, csv),
  apresentacao (pptx, ppt, odp), texto, compactado (zip), audio (mp3, m4a, wav, ogg), video (mp4, mov, webm).
  O tipo é conferido pelo CONTEÚDO, não pelo nome. HTML, SVG, XML e programas são sempre recusados.
- Tamanho: padrão 10 MB por arquivo; o campo pode ir até 100 MB (teto do 00). O sistema pode apertar por pessoa ou
  por plano e ter cota de espaço (ARQUIVOS_LIMITES, abaixo).
- Fotos: a localização (GPS) que o celular grava dentro da foto é apagada ao enviar (LGPD).
- Guardado com nome aleatório, fora de qualquer pasta pública. Local (Mac): pasta arquivos_privados do sistema.
  Nuvem (dev online e produção): o armazenamento configurado em STORAGES["arquivos"] (etapa 8).
- Apagou o registro, os arquivos dele somem junto. Trocou o arquivo, o antigo é apagado.

Enviar: o formulário do Django (ModelForm) já traz o campo de arquivo. Gravar com a função do 00, que devolve os erros
de arquivo (tamanho, cota) para o próprio formulário:

    from infra_vibecoding.arquivos import salvar_formulario

    chamado = salvar_formulario(form, request.user)   # None se houve erro (o form mostra)

Em código, sem formulário: anexar(chamado, "print_do_erro", arquivo) e depois chamado.salvar(usuario).

Baixar: no template, {% load arquivos %} e {{ chamado|arquivo:"print_do_erro" }} dá nome, tamanho e url. O link
(/arquivos/<id>/) só funciona para quem está logado e pode ver o registro pela regra da tabela, conferido a cada
clique: se vazar, não abre para mais ninguém. A tela de banco baixa como sistema (quem tem acesso à tabela lá).

Limites por pessoa ou plano (ex.: cobrar por mais espaço), no settings.py:

    ARQUIVOS_LIMITES = "contas.regras.limites_de_arquivo"

    def limites_de_arquivo(usuario, registro, campo):
        empresa = registro.empresa
        return {"por_arquivo": 20 * 1024 * 1024,      # nunca passa do tamanho_max_mb do campo
                "espaco": f"empresa-{empresa.pk}",     # os arquivos com o mesmo espaço somam na cota
                "total": empresa.plano.gb * 1024 ** 3}  # cota total do espaço, em bytes
"""
import io
import logging
import uuid
import zipfile
from pathlib import Path

from django import forms
from django.apps import apps
from django.conf import settings
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured, ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadhandler import FileUploadHandler, StopUpload
from django.db import models, transaction
from django.db.models import Sum, signals
from django.http import FileResponse, Http404
from django.urls import reverse
from django.utils.module_loading import import_string

log = logging.getLogger("infra_vibecoding.auditoria")

MB = 1024 * 1024
TETO_MB = 100            # nenhum campo passa disso (Cloudflare gratuito também não aceita mais que 100 MB)
PADRAO_MB = 10
TIPOS_PADRAO = ("imagem", "pdf")
FAMILIAS = ("imagem", "pdf", "documento", "planilha", "apresentacao", "texto", "compactado", "audio", "video")
_EXIBIR_NO_NAVEGADOR = {"image/jpeg", "image/png", "image/gif", "image/webp", "application/pdf"}


# Tipo pelo conteúdo

def _zip_com(arquivo_zip, *nomes):
    return any(n in arquivo_zip for n in nomes)


def detectar(conteudo):
    """(família, tipo, extensão) pelo conteúdo do arquivo, ou None se não for um tipo aceito."""
    inicio = conteudo[:4096]
    if inicio.startswith(b"\xff\xd8\xff"):
        return "imagem", "image/jpeg", ".jpg"
    if inicio.startswith(b"\x89PNG\r\n\x1a\n"):
        return "imagem", "image/png", ".png"
    if inicio[:6] in (b"GIF87a", b"GIF89a"):
        return "imagem", "image/gif", ".gif"
    if inicio[:4] == b"RIFF" and inicio[8:12] == b"WEBP":
        return "imagem", "image/webp", ".webp"
    if inicio[:4] == b"RIFF" and inicio[8:12] == b"WAVE":
        return "audio", "audio/wav", ".wav"
    if inicio.startswith(b"%PDF-"):
        return "pdf", "application/pdf", ".pdf"
    if inicio.startswith(b"ID3") or inicio[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio", "audio/mpeg", ".mp3"
    if inicio.startswith(b"OggS"):
        return "audio", "audio/ogg", ".ogg"
    if inicio.startswith(b"\x1a\x45\xdf\xa3"):
        return "video", "video/webm", ".webm"
    if inicio[4:8] == b"ftyp":
        marca = inicio[8:12]
        if marca in (b"M4A ", b"M4B "):
            return "audio", "audio/mp4", ".m4a"
        if marca == b"qt  ":
            return "video", "video/quicktime", ".mov"
        if marca in (b"isom", b"iso2", b"mp41", b"mp42", b"avc1", b"MSNV", b"M4V "):
            return "video", "video/mp4", ".mp4"
        return None  # heic e outros: não aceitos (o navegador nem mostra)
    if inicio.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "documento", "application/msword", ".doc"  # formato antigo do Office (doc/xls/ppt)
    if inicio.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
                nomes = set(z.namelist())
                mimetype = z.read("mimetype").decode(errors="ignore") if "mimetype" in nomes else ""
        except (zipfile.BadZipFile, KeyError, OSError):
            return None
        if _zip_com(nomes, "word/document.xml"):
            return "documento", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"
        if _zip_com(nomes, "xl/workbook.xml"):
            return "planilha", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"
        if _zip_com(nomes, "ppt/presentation.xml"):
            return ("apresentacao", "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    ".pptx")
        if mimetype == "application/vnd.oasis.opendocument.text":
            return "documento", mimetype, ".odt"
        if mimetype == "application/vnd.oasis.opendocument.spreadsheet":
            return "planilha", mimetype, ".ods"
        if mimetype == "application/vnd.oasis.opendocument.presentation":
            return "apresentacao", mimetype, ".odp"
        return "compactado", "application/zip", ".zip"
    return _detectar_texto(inicio)


_MARCAS_PERIGOSAS = (b"<html", b"<!doctype", b"<svg", b"<script", b"<?xml", b"<iframe", b"<body", b"<head",
                     b"javascript:", b"<object", b"<embed")


def _detectar_texto(inicio):
    if b"\x00" in inicio:
        return None  # binário que não é de nenhum tipo aceito (ex.: programa)
    try:
        texto = inicio.decode("utf-8")
    except UnicodeDecodeError:
        try:
            texto = inicio.decode("cp1252")
        except UnicodeDecodeError:
            return None
    if any(ord(c) < 9 or 13 < ord(c) < 32 for c in texto):
        return None
    minusculo = inicio.lower()
    if minusculo.lstrip().startswith(b"<") or any(m in minusculo for m in _MARCAS_PERIGOSAS):
        return None  # HTML, SVG, XML: rodariam código se abertos no navegador
    primeira = texto.split("\n", 1)[0]
    if primeira.count(";") >= 1 or primeira.count(",") >= 2:
        return "planilha", "text/csv", ".csv"
    return "texto", "text/plain", ".txt"


def _limpar_foto(conteudo, tipo):
    """Confere que a imagem é de verdade e apaga a localização (GPS) de dentro dela."""
    import warnings

    from PIL import Image

    Image.MAX_IMAGE_PIXELS = 60_000_000
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(conteudo)) as img:
                img.verify()
            img = Image.open(io.BytesIO(conteudo))
            img.load()
    except Exception:
        raise ValidationError("A imagem está corrompida ou não é uma imagem de verdade.") from None
    if tipo not in ("image/jpeg", "image/png", "image/webp"):
        return conteudo
    exif = img.getexif()
    if 0x8825 not in exif:  # sem GPS: guarda como veio
        return conteudo
    del exif[0x8825]
    saida = io.BytesIO()
    extras = {"exif": exif.tobytes()}
    if img.info.get("icc_profile"):
        extras["icc_profile"] = img.info["icc_profile"]
    if tipo == "image/jpeg":
        img.save(saida, format="JPEG", quality="keep", **extras)
    elif tipo == "image/png":
        img.save(saida, format="PNG", **extras)
    else:
        img.save(saida, format="WEBP", quality=95, **extras)
    return saida.getvalue()


# O campo

class ArquivoRef:
    """O que o campo mostra: nome, tamanho, tipo e o endereço de download (/arquivos/<id>/)."""

    def __init__(self, id_):
        self.id = id_ if isinstance(id_, uuid.UUID) else uuid.UUID(str(id_))
        self._guardado = None

    @property
    def guardado(self):
        if self._guardado is None:
            from .models import ArquivoGuardado

            self._guardado = ArquivoGuardado._base_manager.filter(pk=self.id).first()
        return self._guardado

    @property
    def nome(self):
        return self.guardado.nome if self.guardado else ""

    @property
    def tamanho(self):
        return self.guardado.tamanho if self.guardado else 0

    @property
    def tipo(self):
        return self.guardado.tipo if self.guardado else ""

    @property
    def eh_imagem(self):
        return self.tipo.startswith("image/")

    @property
    def url(self):
        if self.guardado and self.guardado.publico:
            return reverse("arquivo_publico", args=[self.id])
        return reverse("baixar_arquivo", args=[self.id])

    @property
    def url_compartilhar(self):
        """Tela do 00 para criar e cancelar links de compartilhamento (só abre para quem a política libera)."""
        return reverse("compartilhar_arquivo", args=[self.id])

    @property
    def publico(self):
        return bool(self.guardado and self.guardado.publico)

    def __str__(self):
        return self.nome

    def __eq__(self, outro):
        return isinstance(outro, ArquivoRef) and outro.id == self.id

    def __hash__(self):
        return hash(self.id)


class FormularioCampoArquivo(forms.FileField):
    """Campo de envio: confere o tamanho e o tipo pelo conteúdo antes de aceitar."""

    widget = forms.ClearableFileInput

    def __init__(self, *args, campo=None, **kwargs):
        self.campo_modelo = campo
        super().__init__(*args, **kwargs)
        if campo is not None:
            self.widget.attrs.setdefault("accept", ",".join(_extensoes(campo.tipos)))

    def clean(self, data, initial=None):
        valor = super().clean(data, initial)
        if hasattr(valor, "read") and hasattr(valor, "size"):
            conferir_envio(self.campo_modelo, valor)
        return valor


def _extensoes(tipos):
    mapa = {"imagem": ".jpg,.jpeg,.png,.gif,.webp", "pdf": ".pdf", "documento": ".docx,.doc,.odt",
            "planilha": ".xlsx,.xls,.ods,.csv", "apresentacao": ".pptx,.ppt,.odp", "texto": ".txt",
            "compactado": ".zip", "audio": ".mp3,.m4a,.wav,.ogg", "video": ".mp4,.mov,.webm"}
    return [e for t in tipos for e in mapa[t].split(",")]


def _ler(arquivo):
    if hasattr(arquivo, "seek"):
        arquivo.seek(0)
    conteudo = arquivo.read()
    if hasattr(arquivo, "seek"):
        arquivo.seek(0)
    return conteudo


def conferir_envio(campo, arquivo):
    """Tamanho do campo e tipo pelo conteúdo. Guarda o que descobriu no próprio arquivo enviado."""
    if arquivo.size > campo.max_bytes:
        raise ValidationError(f"Arquivo maior que {campo.tamanho_max_mb} MB.")
    if arquivo.size == 0:
        raise ValidationError("O arquivo está vazio.")
    conteudo = _ler(arquivo)
    achado = detectar(conteudo)
    if achado is None:
        raise ValidationError("Tipo de arquivo não aceito.")
    familia, tipo, extensao = achado
    if familia not in campo.tipos:
        aceitos = ", ".join(campo.tipos)
        raise ValidationError(f"Este campo aceita só: {aceitos}. O arquivo enviado é {familia}.")
    if familia == "imagem":
        conteudo = _limpar_foto(conteudo, tipo)
    arquivo._iv_conferido = (familia, tipo, extensao, conteudo)
    return arquivo._iv_conferido


class CampoArquivo(models.UUIDField):
    """Campo de arquivo privado de uma tabela. Guarda a referência; o arquivo fica no armazenamento do 00."""

    description = "Arquivo privado (Infra Vibecoding)"

    def __init__(self, *args, tipos=TIPOS_PADRAO, tamanho_max_mb=PADRAO_MB, publico=None, **kwargs):
        if publico is not None and (not isinstance(publico, str) or len(publico.strip()) < 10):
            raise ImproperlyConfigured(
                'CampoArquivo: campo público precisa de um motivo escrito, ex.: publico="foto do produto na vitrine '
                'pública" (e autorização do Ed). Sem motivo, o arquivo é privado.')
        self.publico = publico.strip() if publico else None
        tipos = tuple(tipos)
        desconhecidos = [t for t in tipos if t not in FAMILIAS]
        if desconhecidos or not tipos:
            raise ImproperlyConfigured(f"CampoArquivo: tipos desconhecidos {desconhecidos}. Use: {', '.join(FAMILIAS)}.")
        if not 0 < tamanho_max_mb <= TETO_MB:
            raise ImproperlyConfigured(f"CampoArquivo: tamanho_max_mb vai de 1 a {TETO_MB}.")
        self.tipos = tipos
        self.tamanho_max_mb = tamanho_max_mb
        kwargs.setdefault("null", True)
        kwargs.setdefault("blank", True)
        super().__init__(*args, **kwargs)

    @property
    def max_bytes(self):
        return int(self.tamanho_max_mb * MB)

    def deconstruct(self):
        nome, _, args, kwargs = super().deconstruct()
        return nome, "infra_vibecoding.arquivos.CampoArquivo", args, kwargs  # tipos e tamanho não mudam o banco

    def contribute_to_class(self, cls, name, *args, **kwargs):
        super().contribute_to_class(cls, name, *args, **kwargs)
        if not cls._meta.abstract:
            signals.post_save.connect(_depois_de_salvar, sender=cls, weak=False,
                                      dispatch_uid=f"infra_vibecoding.arquivos.salvar.{cls._meta.label}")
            signals.post_delete.connect(_depois_de_excluir, sender=cls, weak=False,
                                        dispatch_uid=f"infra_vibecoding.arquivos.excluir.{cls._meta.label}")

    def to_python(self, value):
        if isinstance(value, ArquivoRef):
            return value.id
        if hasattr(value, "read"):
            return None
        return super().to_python(value)

    def get_prep_value(self, value):
        if isinstance(value, ArquivoRef):
            value = value.id
        return super().get_prep_value(value)

    def validate(self, value, model_instance):
        pendente = (model_instance.__dict__.get("_iv_arquivos_pendentes", {}).get(self.name)
                    if model_instance is not None else None)
        if pendente is not None:
            return  # arquivo novo chegando: ainda não tem referência, mas o campo não está vazio
        super().validate(value, model_instance)

    def value_from_object(self, obj):
        valor = getattr(obj, self.attname)
        return ArquivoRef(valor) if valor else None

    def value_to_string(self, obj):
        valor = getattr(obj, self.attname)
        return str(valor) if valor else ""

    def formfield(self, **kwargs):
        return FormularioCampoArquivo(campo=self, required=not self.blank, label=self.verbose_name.capitalize(),
                                      help_text=self.help_text)

    def save_form_data(self, instance, data):
        if data is False:
            anexar(instance, self.name, None)
        elif hasattr(data, "read"):
            anexar(instance, self.name, data)

    def pre_save(self, instance, add):
        pendentes = instance.__dict__.get("_iv_arquivos_pendentes", {})
        if self.name in pendentes:
            arquivo = pendentes.pop(self.name)
            antigo = getattr(instance, self.attname)
            novo = None if arquivo is None else _guardar(instance, self, arquivo)
            instance.__dict__.setdefault("_iv_arquivos_feitos", []).append((self.name, antigo, novo))
            setattr(instance, self.attname, novo["id"] if novo else None)
        return super().pre_save(instance, add)


def anexar(registro, campo, arquivo):
    """Marca um arquivo para ser guardado (ou None para remover) na próxima gravação do registro."""
    registro.__dict__.setdefault("_iv_arquivos_pendentes", {})[campo] = arquivo


def arquivo_de(registro, campo):
    valor = getattr(registro, registro._meta.get_field(campo).attname)
    return ArquivoRef(valor) if valor else None


# Guardar

def armazenamento():
    from django.core.files.storage import FileSystemStorage, storages

    if "arquivos" in getattr(settings, "STORAGES", {}):
        return storages["arquivos"]
    pasta = getattr(settings, "ARQUIVOS_PASTA", None) or Path(settings.BASE_DIR) / "arquivos_privados"
    return FileSystemStorage(location=pasta, file_permissions_mode=0o600, directory_permissions_mode=0o700)


def _autor():
    from .dados import _AUTOR

    return _AUTOR.get()


def _limites(usuario, registro, campo):
    caminho = getattr(settings, "ARQUIVOS_LIMITES", None)
    if not caminho:
        return {}
    return import_string(caminho)(usuario, registro, campo.name) or {}


def _guardar(registro, campo, arquivo):
    tipo_autor, quem = _autor()
    usuario = quem if tipo_autor == "usuario" else None
    conferido = getattr(arquivo, "_iv_conferido", None)
    try:
        if conferido is None:
            conferido = conferir_envio(campo, arquivo)
        familia, tipo, extensao, conteudo = conferido
        limites = _limites(usuario, registro, campo)
        por_arquivo = min(campo.max_bytes, limites.get("por_arquivo") or campo.max_bytes)
        if len(conteudo) > por_arquivo:
            raise ValidationError(f"Arquivo maior que o permitido ({por_arquivo // MB} MB).")
        espaco = str(limites.get("espaco") or "")
        total = limites.get("total")
        if espaco and total is not None:
            from .models import ArquivoGuardado

            usado = ArquivoGuardado._base_manager.filter(espaco=espaco).aggregate(s=Sum("tamanho"))["s"] or 0
            if usado + len(conteudo) > total:
                raise ValidationError("O espaço de arquivos está cheio. Apague arquivos antigos ou aumente o plano.")
    except ValidationError as erro:
        raise ValidationError({campo.name: erro.messages}) from None
    id_ = uuid.uuid4()
    caminho = armazenamento().save(f"{registro._meta.label_lower.replace('.', '/')}/{id_.hex}{extensao}",
                                   ContentFile(conteudo))
    nome = Path(getattr(arquivo, "name", "") or f"arquivo{extensao}").name[:255]
    if tipo_autor == "usuario":
        autor = getattr(quem, "email", None) or str(getattr(quem, "pk", "?"))
    else:
        autor = f"sistema ({quem})"[:254]
    return {"id": id_, "nome": nome, "tipo": tipo, "tamanho": len(conteudo), "caminho": caminho,
            "espaco": espaco, "autor": autor, "publico": bool(campo.publico)}


def _apagar_do_armazenamento(caminhos):
    loja = armazenamento()
    for caminho in caminhos:
        try:
            loja.delete(caminho)
        except Exception:  # não deixa a limpeza derrubar a gravação; fica no registro
            log.exception("arquivos: não foi possível apagar %s do armazenamento", caminho)


def _remover(ids):
    from .models import ArquivoGuardado

    velhos = list(ArquivoGuardado._base_manager.filter(pk__in=[i for i in ids if i]))
    if not velhos:
        return
    caminhos = [a.caminho for a in velhos]
    for a in velhos:
        a.excluir_como_sistema(f"arquivos: {a.nome} substituído ou removido de {a.modelo} {a.registro}")
    transaction.on_commit(lambda: _apagar_do_armazenamento(caminhos))


def _depois_de_salvar(sender, instance, **kwargs):
    from .models import ArquivoGuardado

    feitos = instance.__dict__.pop("_iv_arquivos_feitos", [])
    for campo, antigo, novo in feitos:
        if novo:
            ArquivoGuardado(
                id=novo["id"], modelo=instance._meta.label, registro=str(instance.pk), campo=campo,
                nome=novo["nome"], tipo=novo["tipo"], tamanho=novo["tamanho"], caminho=novo["caminho"],
                espaco=novo["espaco"], enviado_por=novo["autor"], publico=novo["publico"],
            ).salvar_como_sistema(f"arquivos: {novo['autor']} enviou {novo['nome']} para {instance._meta.label} "
                                  f"{instance.pk} ({campo})", force_insert=True)
            log.info("arquivos: %s enviou %s (%s bytes) para %s %s", novo["autor"], novo["nome"], novo["tamanho"],
                     instance._meta.label, instance.pk)
        if antigo and (not novo or antigo != novo["id"]):
            _remover([antigo])


def _depois_de_excluir(sender, instance, **kwargs):
    ids = [getattr(instance, c.attname) for c in instance._meta.concrete_fields if isinstance(c, CampoArquivo)]
    _remover([i for i in ids if i])


# Gravar um formulário devolvendo os erros de arquivo para ele

def salvar_formulario(form, usuario):
    """form.save() conferindo a permissão (obj.salvar) e devolvendo ao formulário os erros de arquivo (tamanho,
    cota). Devolve o registro gravado, ou None se o formulário tem erro."""
    if not form.is_valid():
        return None
    obj = form.save(commit=False)
    try:
        with transaction.atomic():
            obj.salvar(usuario)
            form.save_m2m()
    except ValidationError as erro:
        campos = getattr(erro, "error_dict", {})
        for campo, mensagens in campos.items():
            form.add_error(campo if campo in form.fields else None, mensagens)
        if not campos:
            form.add_error(None, erro)
        return None
    return obj


# Baixar

def _pode_baixar(usuario, guardado):
    try:
        modelo = apps.get_model(guardado.modelo)
    except LookupError:
        return None, False
    campo = modelo._meta.get_field(guardado.campo)
    if usuario.is_staff and usuario.has_perm(f"{modelo._meta.app_label}.view_{modelo._meta.model_name}"):
        # Tela de banco: quem tem acesso à tabela lá baixa como sistema (e fica registrado).
        registro, como = modelo._base_manager.filter(pk=guardado.registro).first(), "tela de banco"
    else:
        registro, como = modelo.objects.para(usuario).filter(pk=guardado.registro).first(), "regra da tabela"
    if registro is not None and getattr(registro, campo.attname) == guardado.pk:
        return registro, como
    return None, False


def _entregar(guardado, publico=False):
    resposta = FileResponse(armazenamento().open(guardado.caminho, "rb"), content_type=guardado.tipo,
                            as_attachment=guardado.tipo not in _EXIBIR_NO_NAVEGADOR, filename=guardado.nome)
    resposta["X-Content-Type-Options"] = "nosniff"
    resposta["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"
    resposta["Cache-Control"] = "public, max-age=86400" if publico else "private, no-store"
    return resposta


def _ainda_no_registro(guardado):
    """O arquivo continua sendo o do campo do registro (não foi trocado nem o registro excluído)?"""
    try:
        modelo = apps.get_model(guardado.modelo)
        campo = modelo._meta.get_field(guardado.campo)
    except (LookupError, FieldDoesNotExist):
        return None
    registro = modelo._base_manager.filter(pk=guardado.registro).first()
    if registro is not None and getattr(registro, campo.attname) == guardado.pk:
        return registro
    return None


def baixar(request, id):
    """Entrega o arquivo para quem pode ver o registro. Para os outros: "não encontrado" (não confirma que existe)."""
    from .models import ArquivoGuardado

    guardado = ArquivoGuardado._base_manager.filter(pk=id).first()
    registro, como = (None, False) if guardado is None else _pode_baixar(request.user, guardado)
    if not como or registro is None:
        log.warning("arquivos: %s tentou baixar o arquivo %s sem permissão", request.user.email, id)
        raise Http404
    log.info("arquivos: %s baixou %s de %s %s (%s)", request.user.email, guardado.nome, guardado.modelo,
             guardado.registro, como)
    return _entregar(guardado)


def baixar_publico(request, id):
    """Arquivo de campo público (US 4.2): abre sem login, enquanto for o arquivo atual do registro."""
    from .models import ArquivoGuardado

    guardado = ArquivoGuardado._base_manager.filter(pk=id, publico=True).first()
    if guardado is None or _ainda_no_registro(guardado) is None:
        raise Http404
    return _entregar(guardado, publico=True)


# Link de compartilhamento (US 4.2, D58)

PRAZO_PADRAO_DIAS = 7
PRAZO_MAXIMO_DIAS = 30


def _resumo_do_codigo(codigo):
    import hashlib

    return hashlib.sha256(codigo.encode()).hexdigest()


def _registro_para_compartilhar(usuario, guardado):
    """O registro do arquivo, se o usuário vê o registro E a política libera "compartilhar". Senão None."""
    from .dados import pode

    registro = _ainda_no_registro(guardado)
    if registro is None:
        return None
    visivel = type(registro).objects.para(usuario).filter(pk=registro.pk).exists()
    if not (visivel and pode(usuario, "compartilhar", registro)):
        return None
    return registro


def compartilhar(usuario, registro, campo, dias=PRAZO_PADRAO_DIAS, request=None):
    """Cria um link do arquivo para quem não é usuário. Devolve (link, endereço completo ou caminho).
    SemPermissao se a política não libera "compartilhar" para este usuário e registro."""
    import secrets

    from django.utils import timezone

    from .dados import SemPermissao
    from .models import ArquivoGuardado, LinkDeCompartilhamento

    ref = arquivo_de(registro, campo)
    guardado = ArquivoGuardado._base_manager.filter(pk=ref.id).first() if ref else None
    if guardado is None or _registro_para_compartilhar(usuario, guardado) is None:
        log.warning("arquivos: %s tentou compartilhar sem permissão (%s %s)", getattr(usuario, "email", usuario),
                    registro._meta.label, registro.pk)
        raise SemPermissao("Sem permissão para compartilhar este arquivo.")
    dias = int(dias)
    if not 1 <= dias <= PRAZO_MAXIMO_DIAS:
        raise ValidationError(f"O prazo vai de 1 a {PRAZO_MAXIMO_DIAS} dias.")
    codigo = secrets.token_urlsafe(32)
    link = LinkDeCompartilhamento(arquivo=guardado, resumo=_resumo_do_codigo(codigo), criado_por=usuario.email,
                                  vence_em=timezone.now() + timezone.timedelta(days=dias))
    link.salvar_como_sistema(f"arquivos: {usuario.email} compartilhou {guardado.nome} por {dias} dia(s)")
    from .historico import registrar_acao

    registrar_acao(usuario, registro, "criou link de compartilhamento",
                   {"arquivo": guardado.nome, "prazo": f"{dias} dia(s)", "vence em": link.vence_em})
    caminho = reverse("baixar_compartilhado", args=[codigo])
    log.info("arquivos: %s criou link de %s para %s, vence em %s", usuario.email, dias, guardado.nome,
             link.vence_em)
    return link, request.build_absolute_uri(caminho) if request is not None else caminho


def cancelar_compartilhamento(usuario, link):
    from django.utils import timezone

    from .dados import SemPermissao

    registro = _registro_para_compartilhar(usuario, link.arquivo)
    if registro is None:
        raise SemPermissao("Sem permissão para cancelar este link.")
    if link.cancelado_em is None:
        link.cancelado_em, link.cancelado_por = timezone.now(), usuario.email
        link.salvar_como_sistema(f"arquivos: {usuario.email} cancelou um link de {link.arquivo.nome}",
                                 update_fields=["cancelado_em", "cancelado_por"])
        from .historico import registrar_acao

        registrar_acao(usuario, registro, "cancelou link de compartilhamento",
                       {"arquivo": link.arquivo.nome, "criado por": link.criado_por})
    return link


def tela_compartilhar(request, id):
    """Tela pronta do 00: criar link (prazo), ver os links ativos do arquivo e cancelar. 404 para quem não pode."""
    from django.contrib import messages
    from django.shortcuts import redirect, render
    from django.utils import timezone

    from .models import ArquivoGuardado, LinkDeCompartilhamento

    guardado = ArquivoGuardado._base_manager.filter(pk=id).first()
    registro = None if guardado is None else _registro_para_compartilhar(request.user, guardado)
    if registro is None:
        raise Http404
    novo = request.session.pop("infra_vibecoding_link_novo", None)  # mostrado uma vez só
    if request.method == "POST":
        if "cancelar" in request.POST:
            link = LinkDeCompartilhamento._base_manager.filter(pk=request.POST["cancelar"], arquivo=guardado).first()
            if link is not None:
                cancelar_compartilhamento(request.user, link)
                messages.success(request, "Link cancelado.")
            return redirect(request.path)
        try:
            dias = int(request.POST.get("dias") or PRAZO_PADRAO_DIAS)
            _, endereco = compartilhar(request.user, registro, guardado.campo, dias, request)
            # Volta para a tela por GET: recarregar a página não cria outro link.
            request.session["infra_vibecoding_link_novo"] = endereco
        except (ValueError, ValidationError):
            messages.error(request, f"O prazo vai de 1 a {PRAZO_MAXIMO_DIAS} dias.")
        return redirect(request.path)
    ativos = LinkDeCompartilhamento._base_manager.filter(arquivo=guardado, cancelado_em__isnull=True,
                                                         vence_em__gt=timezone.now())
    return render(request, "infra_vibecoding/arquivos/compartilhar.html", {
        "arquivo": guardado, "novo": novo, "ativos": ativos,
        "prazo_padrao": PRAZO_PADRAO_DIAS, "prazo_maximo": PRAZO_MAXIMO_DIAS,
    })


def baixar_compartilhado(request, codigo):
    """Quem recebeu o link baixa sem login, dentro do prazo. Vencido, cancelado ou arquivo trocado: página própria."""
    from django.db.models import F
    from django.shortcuts import render
    from django.utils import timezone

    from .limites import endereco_de
    from .models import LinkDeCompartilhamento

    link = LinkDeCompartilhamento._base_manager.select_related("arquivo").filter(
        resumo=_resumo_do_codigo(codigo)).first()
    if link is None or not link.ativo or _ainda_no_registro(link.arquivo) is None:
        log.warning("arquivos: link de compartilhamento inválido, vencido ou cancelado (%s)", endereco_de(request))
        return render(request, "infra_vibecoding/arquivos/link_indisponivel.html", status=410)
    type(link)._base_manager.filter(pk=link.pk).update(downloads=F("downloads") + 1,
                                                        ultimo_download_em=timezone.now())
    log.info("arquivos: %s baixado por link de compartilhamento criado por %s (%s)", link.arquivo.nome,
             link.criado_por, endereco_de(request))
    resposta = _entregar(link.arquivo)
    resposta["X-Robots-Tag"] = "noindex"
    return resposta


def _declarar():
    from .telas import logado, publica

    return logado(baixar), publica(baixar_publico), logado(tela_compartilhar), publica(baixar_compartilhado)


baixar, baixar_publico, tela_compartilhar, baixar_compartilhado = _declarar()


# Proteção no recebimento: nenhum envio passa de 100 MB (antes mesmo de chegar na tela)

class LimiteDeEnvio(FileUploadHandler):
    """Corta o envio de um arquivo maior que o teto do 00 enquanto ele ainda está chegando."""

    def receive_data_chunk(self, raw_data, start):
        if start + len(raw_data) > TETO_MB * MB + MB:
            log.warning("arquivos: envio cortado por passar de %s MB", TETO_MB)
            raise StopUpload(connection_reset=True)
        return raw_data

    def file_complete(self, file_size):
        return None
