"""Log com mascaramento obrigatório de CPF.

Regra do projeto: nenhum CPF completo entra em log, relatório ou mensagem de
erro. O mascaramento é aplicado no próprio formatter, então mesmo um log escrito
por engano com CPF cru sai mascarado.
"""
import logging
import re
import sys

from src.config import ajustes

# 11 dígitos, com ou sem pontuação, isolados de outros números.
_CPF = re.compile(r"(?<!\d)(\d{3})[.\s]?(\d{3})[.\s]?(\d{3})[-.\s]?(\d{2})(?!\d)")


def mascarar_cpf(texto):
    """123.456.789-12 -> ***.***.***-12 (preserva só os 2 últimos dígitos)."""
    if not texto:
        return texto
    return _CPF.sub(lambda m: "***.***.***-" + m.group(4), str(texto))


class _FiltroCPF(logging.Filter):
    def filter(self, registro):
        if isinstance(registro.msg, str):
            registro.msg = mascarar_cpf(registro.msg)
        if registro.args:
            try:
                registro.args = tuple(
                    mascarar_cpf(a) if isinstance(a, str) else a for a in registro.args
                )
            except TypeError:
                pass
        return True


_configurado = False


def obter(nome):
    global _configurado
    if not _configurado:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)-7s %(name)-22s %(message)s",
            datefmt="%d/%m %H:%M:%S",
        ))
        h.addFilter(_FiltroCPF())
        raiz = logging.getLogger("radar")
        raiz.handlers = [h]
        raiz.setLevel(getattr(logging, ajustes.LOG_NIVEL.upper(), logging.INFO))
        raiz.propagate = False
        _configurado = True
    return logging.getLogger("radar." + nome)
