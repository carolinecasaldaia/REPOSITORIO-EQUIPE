"""Documento da parte: CPF ou CNPJ.

A carteira do escritório tem pessoa física e jurídica — uma empresa que
financia veículo também sofre busca e apreensão. Este módulo trata os dois com
a mesma proteção: hash determinístico para comparar, criptografia para guardar
e máscara para exibir.

As primitivas de hash e criptografia vêm de `cpf.py`; aqui entra a validação e
o mascaramento específicos de cada tipo.
"""
from src.seguranca.cpf import ChaveAusente, decifrar  # noqa: F401
from src.seguranca.cpf import cifrar_digitos, gerar_chave, hash_digitos
from src.seguranca.cpf import mascarar as _mascarar_cpf
from src.seguranca.cpf import normalizar
from src.seguranca.cpf import validar as validar_cpf

CPF = "CPF"
CNPJ = "CNPJ"

_PESOS_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_PESOS_2 = [6] + _PESOS_1


def validar_cnpj(documento):
    """Valida os dois dígitos verificadores do CNPJ."""
    d = normalizar(documento)
    if len(d) != 14 or d == d[0] * 14:
        return False
    for tamanho, pesos in ((12, _PESOS_1), (13, _PESOS_2)):
        soma = sum(int(d[i]) * pesos[i] for i in range(tamanho))
        resto = soma % 11
        digito = 0 if resto < 2 else 11 - resto
        if digito != int(d[tamanho]):
            return False
    return True


def tipo(documento):
    """Devolve "CPF", "CNPJ" ou "" quando não for nenhum dos dois."""
    d = normalizar(documento)
    if len(d) == 11:
        return CPF if validar_cpf(d) else ""
    if len(d) == 14:
        return CNPJ if validar_cnpj(d) else ""
    return ""


def validar(documento):
    return tipo(documento) != ""


def formatar(documento):
    d = normalizar(documento)
    if len(d) == 11:
        return "%s.%s.%s-%s" % (d[0:3], d[3:6], d[6:9], d[9:11])
    if len(d) == 14:
        return "%s.%s.%s/%s-%s" % (d[0:2], d[2:5], d[5:8], d[8:12], d[12:14])
    return str(documento or "")


def mascarar(documento):
    """CPF -> ***.***.***-12 · CNPJ -> **.***.***/****-12

    Em ambos, só os dois últimos dígitos sobrevivem — é o que basta para
    conferir um cadastro sem expor o número.
    """
    d = normalizar(documento)
    if len(d) == 14:
        return "**.***.***/****-" + d[12:14]
    return _mascarar_cpf(documento)


def hash_deterministico(documento):
    """Mesmo documento -> mesmo hash, seja CPF ou CNPJ."""
    d = normalizar(documento)
    if len(d) not in (11, 14):
        raise ValueError("documento inválido para hash")
    return hash_digitos(d)


def cifrar(documento):
    d = normalizar(documento)
    if len(d) not in (11, 14):
        raise ValueError("documento inválido para cifragem")
    return cifrar_digitos(d)
