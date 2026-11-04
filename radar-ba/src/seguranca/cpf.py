"""Tratamento seguro de CPF.

Três operações distintas, cada uma com um propósito:

  hash_determinístico  comparar e deduplicar sem guardar o número
  cifrar / decifrar    guardar recuperável, quando for mesmo necessário
  mascarar             exibir em log, tela e relatório

O sistema falha fechado: sem chave configurada, ele se recusa a cifrar em vez
de gravar em texto puro.
"""
import base64
import hashlib
import hmac
import os

from src.config import ajustes


class ChaveAusente(Exception):
    """Faltou CPF_PEPPER ou CPF_CHAVE no .env."""


def normalizar(cpf):
    """Devolve apenas os 11 dígitos."""
    return "".join(c for c in str(cpf or "") if c.isdigit())


def validar(cpf):
    """Valida os dois dígitos verificadores."""
    d = normalizar(cpf)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(d[i]) * (tamanho + 1 - i) for i in range(tamanho))
        resto = (soma * 10) % 11
        if resto == 10:
            resto = 0
        if resto != int(d[tamanho]):
            return False
    return True


def formatar(cpf):
    d = normalizar(cpf)
    if len(d) != 11:
        return str(cpf or "")
    return "%s.%s.%s-%s" % (d[0:3], d[3:6], d[6:9], d[9:11])


def mascarar(cpf):
    """***.***.***-12 — o único formato que pode aparecer em log ou relatório."""
    d = normalizar(cpf)
    if len(d) != 11:
        return "***.***.***-**"
    return "***.***.***-" + d[9:11]


def hash_deterministico(cpf):
    """HMAC-SHA256 com pepper. Mesmo CPF -> mesmo hash, permitindo comparar
    e deduplicar sem nunca guardar o número. Sem o pepper, o hash não pode ser
    recalculado a partir de uma lista de CPFs vazada."""
    if not ajustes.CPF_PEPPER:
        raise ChaveAusente(
            "CPF_PEPPER não configurado no .env — não é possível gerar hash de CPF"
        )
    d = normalizar(cpf)
    if len(d) != 11:
        raise ValueError("CPF inválido para hash")
    return hash_digitos(d)


def hash_digitos(digitos):
    """Primitiva sem validação de tamanho — usada também para CNPJ."""
    if not ajustes.CPF_PEPPER:
        raise ChaveAusente(
            "CPF_PEPPER não configurado no .env — não é possível gerar hash"
        )
    return hmac.new(
        ajustes.CPF_PEPPER.encode("utf-8"), str(digitos).encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


# --- criptografia reversível (AES-256-GCM) ------------------------------

def gerar_chave():
    """Gera uma chave nova para colar no .env como CPF_CHAVE."""
    return base64.b64encode(os.urandom(32)).decode("ascii")


def _chave():
    if not ajustes.CPF_CHAVE:
        raise ChaveAusente(
            "CPF_CHAVE não configurada no .env — o sistema não grava CPF sem criptografia"
        )
    bruta = base64.b64decode(ajustes.CPF_CHAVE)
    if len(bruta) != 32:
        raise ChaveAusente("CPF_CHAVE deve ter 32 bytes em base64")
    return bruta


def _aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        raise ChaveAusente(
            "pacote 'cryptography' não instalado — rode o atalho do RADAR para instalar"
        )
    return AESGCM(_chave())


def cifrar(cpf):
    """Devolve base64(nonce + texto cifrado)."""
    d = normalizar(cpf)
    if len(d) != 11:
        raise ValueError("CPF inválido para cifragem")
    return cifrar_digitos(d)


def cifrar_digitos(digitos):
    """Primitiva sem validação de tamanho — usada também para CNPJ."""
    nonce = os.urandom(12)
    return base64.b64encode(
        nonce + _aesgcm().encrypt(nonce, str(digitos).encode("utf-8"), None)
    ).decode("ascii")


def decifrar(cifrado):
    bruto = base64.b64decode(cifrado)
    return _aesgcm().decrypt(bruto[:12], bruto[12:], None).decode("utf-8")
