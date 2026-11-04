#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validação e padronização dos dados extraídos.

Princípio que atravessa o arquivo: **corrigir formato, nunca corrigir conteúdo.**
Espaço duplicado, "R$4.499, 95", "( 82) 99185-5820" e "57038 -637" são defeitos
de extração do PDF e podem ser arrumados. Já nome, número de RG e número da casa
não são tocados: se estiverem estranhos, a informação vai para conferência
humana em vez de ser "consertada" por conta própria.

Toda função devolve (valor_padronizado, valido, motivo).
"""

import re

UFS = ("AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS",
       "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC",
       "SE", "SP", "TO")

_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def so_digitos(texto) -> str:
    return re.sub(r"\D", "", str(texto or ""))


# ---------------------------------------------------------------------------
# CPF / CNPJ
# ---------------------------------------------------------------------------

def validar_cpf(bruto):
    """
    Remove pontuação, confere os 11 dígitos e calcula os dois dígitos
    verificadores. Devolve (cpf_formatado, valido, motivo).
    """
    digitos = so_digitos(bruto)
    if not digitos:
        return "", False, "CPF não informado"
    if len(digitos) != 11:
        return digitos, False, "CPF deve ter 11 dígitos (encontrado: %d)" % len(digitos)
    if digitos == digitos[0] * 11:
        return formatar_cpf(digitos), False, "CPF com todos os dígitos iguais"

    for posicao in (9, 10):
        soma = sum(int(digitos[i]) * ((posicao + 1) - i) for i in range(posicao))
        resto = (soma * 10) % 11
        esperado = 0 if resto == 10 else resto
        if esperado != int(digitos[posicao]):
            return formatar_cpf(digitos), False, "CPF com dígito verificador inválido"
    return formatar_cpf(digitos), True, ""


def formatar_cpf(digitos: str) -> str:
    d = so_digitos(digitos)
    if len(d) != 11:
        return d
    return "%s.%s.%s-%s" % (d[:3], d[3:6], d[6:9], d[9:])


def validar_cnpj(bruto):
    digitos = so_digitos(bruto)
    if not digitos:
        return "", False, "CNPJ não informado"
    if len(digitos) != 14:
        return digitos, False, "CNPJ deve ter 14 dígitos (encontrado: %d)" % len(digitos)
    if digitos == digitos[0] * 14:
        return formatar_cnpj(digitos), False, "CNPJ com todos os dígitos iguais"

    def digito(parcial, pesos):
        soma = sum(int(c) * p for c, p in zip(parcial, pesos))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    p2 = [6] + p1
    if digito(digitos[:12], p1) != int(digitos[12]) or \
       digito(digitos[:13], p2) != int(digitos[13]):
        return formatar_cnpj(digitos), False, "CNPJ com dígito verificador inválido"
    return formatar_cnpj(digitos), True, ""


def formatar_cnpj(digitos: str) -> str:
    d = so_digitos(digitos)
    if len(d) != 14:
        return d
    return "%s.%s.%s/%s-%s" % (d[:2], d[2:5], d[5:8], d[8:12], d[12:])


def validar_documento(bruto):
    """CPF ou CNPJ, decidido pela quantidade de dígitos."""
    digitos = so_digitos(bruto)
    if len(digitos) == 14:
        return validar_cnpj(bruto) + ("CNPJ",)
    return validar_cpf(bruto) + ("CPF",)


# ---------------------------------------------------------------------------
# E-mail, telefone, CEP
# ---------------------------------------------------------------------------

def validar_email(bruto):
    valor = re.sub(r"\s+", "", str(bruto or "")).strip(".,;:")
    if not valor:
        return "", False, "e-mail não informado"
    valor = valor.lower()
    if not _EMAIL.match(valor):
        return valor, False, "formato de e-mail inválido"
    return valor, True, ""


def validar_telefone(bruto):
    """
    Padroniza para +55 DD NÚMERO.

    Os PDFs devolvem coisas como "( 82) 99185-5820" e "(82) 99179 -7759" —
    isso é ruído da extração e pode ser normalizado sem risco.
    """
    digitos = so_digitos(bruto)
    if not digitos:
        return "", False, "telefone não informado"
    if digitos.startswith("55") and len(digitos) in (12, 13):
        digitos = digitos[2:]
    if len(digitos) == 11:
        ddd, numero = digitos[:2], digitos[2:]
        if numero[0] != "9":
            return "+55 %s %s" % (ddd, numero), False, \
                   "celular de 11 dígitos deveria começar com 9 após o DDD"
        return "+55 %s %s-%s" % (ddd, numero[:5], numero[5:]), True, ""
    if len(digitos) == 10:
        ddd, numero = digitos[:2], digitos[2:]
        return "+55 %s %s-%s" % (ddd, numero[:4], numero[4:]), True, ""
    return digitos, False, "telefone com %d dígitos (esperado 10 ou 11)" % len(digitos)


def validar_cep(bruto):
    digitos = so_digitos(bruto)
    if not digitos:
        return "", False, "CEP não informado"
    if len(digitos) != 8:
        return digitos, False, "CEP deve ter 8 dígitos (encontrado: %d)" % len(digitos)
    return "%s-%s" % (digitos[:5], digitos[5:]), True, ""


def validar_uf(bruto):
    valor = re.sub(r"[^A-Za-z]", "", str(bruto or "")).upper()
    if not valor:
        return "", False, "UF não informada"
    if valor not in UFS:
        return valor, False, "UF desconhecida: %s" % valor
    return valor, True, ""


# ---------------------------------------------------------------------------
# Nome
# ---------------------------------------------------------------------------

def validar_nome(bruto):
    """
    Só limpeza estrutural: espaços duplicados, espaço antes de vírgula, hífen
    solto vindo da quebra de linha do PDF. A grafia do nome não é alterada.
    """
    valor = str(bruto or "")
    valor = valor.replace(" ", " ")
    valor = re.sub(r"\s+", " ", valor).strip(" ,;.:-–")
    valor = re.sub(r"\s+([,;.])", r"\1", valor)
    if not valor:
        return "", False, "nome não informado"
    if len(valor) < 5:
        return valor, False, "nome muito curto para ser um nome completo"
    if len(valor.split()) < 2:
        return valor, False, "nome sem sobrenome"
    if re.search(r"\d", valor):
        return valor, False, "nome contém números"
    return valor, True, ""


def primeiro_nome(nome: str) -> str:
    partes = (nome or "").split()
    return partes[0].title() if partes else ""


# ---------------------------------------------------------------------------
# Limpezas gerais de texto vindo de PDF
# ---------------------------------------------------------------------------

def limpar_texto(bruto) -> str:
    valor = str(bruto or "").replace(" ", " ")
    valor = re.sub(r"\s+", " ", valor)
    return valor.strip(" ,;.:-–")


def limpar_numero_endereco(bruto) -> str:
    """'nº 105' -> '105'; 'nº 37 A' -> '37 A'. Não inventa número."""
    valor = re.sub(r"^\s*(?:n\s*[º°]|n\.)\s*", "", limpar_texto(bruto), flags=re.I)
    return valor.strip(" ,;.-–")


ESTADOS_CIVIS = {
    "solteiro": "Solteiro(a)", "solteira": "Solteiro(a)",
    "casado": "Casado(a)", "casada": "Casado(a)",
    "divorciado": "Divorciado(a)", "divorciada": "Divorciado(a)",
    "viuvo": "Viúvo(a)", "viuva": "Viúvo(a)",
    "separado": "Separado(a)", "separada": "Separado(a)",
    "uniao estavel": "União estável",
    "convivente em uniao estavel": "União estável",
    "companheiro": "União estável", "companheira": "União estável",
}


def normalizar_estado_civil(bruto):
    """
    Devolve (valor_padrao, reconhecido). Se não reconhecer, devolve o texto
    original — não force o dado numa categoria que o documento não disse.
    """
    import unicodedata
    valor = limpar_texto(bruto).lower()
    chave = "".join(c for c in unicodedata.normalize("NFKD", valor)
                    if not unicodedata.combining(c))
    chave = re.sub(r"\s+", " ", chave).strip()
    if chave in ESTADOS_CIVIS:
        return ESTADOS_CIVIS[chave], True
    for termo, padrao in ESTADOS_CIVIS.items():
        if termo in chave:
            return padrao, True
    return limpar_texto(bruto), False
