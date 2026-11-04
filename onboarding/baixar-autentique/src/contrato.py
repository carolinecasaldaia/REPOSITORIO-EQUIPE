#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lê do próprio contrato o nome de quem contratou.

Por que não usar só o nome do signatário do Autentique: ele é digitado no
cadastro e vem abreviado com frequência — "Felipe De Assis F De Souza",
"Telma Cristiane E". Nome abreviado erra a pasta do cliente e, pior, batiza
pasta nova errado.

O contrato tem a qualificação completa, em texto, sempre no mesmo formato:

    ... e do outro lado, como Cliente Contratante EBER ROBERTO ALMEIDA,
    brasileiro, divorciado, motorista de aplicativo, portador do RG ...

É a mesma decisão já tomada no cadastro do Astrea: quem manda é o documento,
não o que foi digitado no cadastro.
"""

import re
import unicodedata

# "como Cliente Contratante FULANO DE TAL," — o nome vai até a primeira vírgula
# (onde começa a nacionalidade). Aceita quebra de linha no meio do nome.
_CONTRATANTE = re.compile(
    r"Cliente\s+Contratante[\s:,\-]+((?:[A-ZÀ-ÜÇ][A-ZÀ-ÜÇ'’.\-]*\s+){1,7}"
    r"[A-ZÀ-ÜÇ][A-ZÀ-ÜÇ'’.\-]*)\s*,",
    re.UNICODE)

# Reserva: contratos antigos escrevem só "Contratante".
_CONTRATANTE_CURTO = re.compile(
    r"(?<!Advogada\s)(?<!Advogado\s)Contratante[\s:,\-]+((?:[A-ZÀ-ÜÇ][A-ZÀ-ÜÇ'’.\-]*\s+){1,7}"
    r"[A-ZÀ-ÜÇ][A-ZÀ-ÜÇ'’.\-]*)\s*,",
    re.UNICODE)

# Corresponsável que paga: extraído só para o relatório, nunca vira pasta.
_RESPONSAVEL = re.compile(
    r"Cliente\s+Respons[áa]vel[\s:,\-]+((?:[A-ZÀ-ÜÇ][A-ZÀ-ÜÇ'’.\-]*\s+){1,7}"
    r"[A-ZÀ-ÜÇ][A-ZÀ-ÜÇ'’.\-]*)\s*,",
    re.UNICODE)

# Pedaços que às vezes grudam no nome quando o PDF quebra a linha.
_RUIDO = ("CONTRATO DE PRESTACAO", "ADVOCATICIOS", "OAB", "CNPJ", "CPF",
          "SOCIEDADE INDIVIDUAL DE ADVOCACIA", "CAROLINE MACEDO")


def _sem_acento(texto: str) -> str:
    normal = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in normal if not unicodedata.combining(c))


def texto_inicial(reader, paginas: int = 2) -> str:
    """Texto das primeiras páginas do contrato, com espaços normalizados."""
    partes = []
    for pagina in reader.pages[:paginas]:
        try:
            partes.append(pagina.extract_text() or "")
        except Exception:            # página estranha não derruba a leitura
            continue
    return re.sub(r"[ \t]+", " ", "\n".join(partes))


def _limpar(bruto: str) -> str:
    nome = re.sub(r"\s+", " ", (bruto or "").replace("\n", " ")).strip(" ,.-")
    if not nome:
        return ""
    alvo = _sem_acento(nome).upper()
    for ruido in _RUIDO:
        if ruido in alvo:
            return ""
    # Nome de gente: pelo menos duas palavras, nada de número.
    if re.search(r"\d", nome) or len(nome.split()) < 2:
        return ""
    return nome


def nome_do_contratante(texto: str) -> str:
    """Nome completo do cliente contratante, ou "" se o contrato não disser."""
    for regex in (_CONTRATANTE, _CONTRATANTE_CURTO):
        for achado in regex.finditer(texto or ""):
            nome = _limpar(achado.group(1))
            if nome:
                return nome
    return ""


def nome_do_responsavel(texto: str) -> str:
    """Corresponsável (quem paga), quando o contrato tiver. Só para o relatório."""
    achado = _RESPONSAVEL.search(texto or "")
    return _limpar(achado.group(1)) if achado else ""
