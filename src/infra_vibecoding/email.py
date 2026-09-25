"""
Envio de e-mail do Infra Vibecoding (US 3.1b, decisões D39 e D45). Vem ligado nas configurações do 00
(EMAIL_BACKEND) e a checagem SEC.E091 impede trocar.

- Com provedor configurado (EMAIL_HOST), envia pelo SMTP do provedor. Sem provedor, mostra no terminal.
- Fora de produção, com provedor, TODO e-mail vai só para a caixa de teste (EMAIL_DE_TESTE), com os
  destinatários originais no assunto ("[para: ana@empresa.com] Seu acesso foi criado"). O sistema dispara
  normalmente, sem lógica de "is live version" em cada fluxo como no Bubble.
- Em produção, vai para os destinatários de verdade.
"""
import copy

from django.conf import settings
from django.core.mail import get_connection
from django.core.mail.backends.base import BaseEmailBackend

ENTREGA_SMTP = "django.core.mail.backends.smtp.EmailBackend"
ENTREGA_TERMINAL = "django.core.mail.backends.console.EmailBackend"


def em_producao():
    return getattr(settings, "AMBIENTE", "producao") == "producao"


def desviar(mensagem, caixa_de_teste):
    """Cópia da mensagem indo só para a caixa de teste, com os destinatários originais no assunto."""
    originais = [*mensagem.to, *mensagem.cc, *mensagem.bcc]
    desviada = copy.copy(mensagem)
    desviada.to, desviada.cc, desviada.bcc = [caixa_de_teste], [], []
    desviada.subject = f"[para: {', '.join(originais)}] {mensagem.subject}"
    desviada.extra_headers = {**mensagem.extra_headers, "X-Destinatario-Original": ", ".join(originais)}
    return desviada


class EnvioComDesvio(BaseEmailBackend):
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.com_provedor = bool(getattr(settings, "EMAIL_HOST", ""))
        caminho = ENTREGA_SMTP if self.com_provedor else ENTREGA_TERMINAL
        self.entrega = get_connection(caminho, fail_silently=fail_silently, **kwargs)

    def open(self):
        return self.entrega.open()

    def close(self):
        return self.entrega.close()

    def send_messages(self, mensagens):
        if not mensagens:
            return 0
        if self.com_provedor and not em_producao():
            caixa = getattr(settings, "EMAIL_DE_TESTE", "")
            if not caixa:  # as configurações já barram isso ao ligar; aqui é a segunda trava
                raise RuntimeError("Envio fora de produção sem EMAIL_DE_TESTE: nenhum e-mail sai sem desvio.")
            mensagens = [desviar(m, caixa) for m in mensagens]
        return self.entrega.send_messages(mensagens)
