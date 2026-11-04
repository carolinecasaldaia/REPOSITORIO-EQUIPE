#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Documento do cliente solto na raiz da pasta vai para DOC CLIENTE.

Decisão dela em 18/08/2026, depois que a correção das subpastas expôs quantos
documentos estavam soltos: CNH, CRLV, comprovante de residência, contrato de
financiamento e holerite (e os equivalentes óbvios, como RG) pertencem a
DOC CLIENTE.

Regra de ouro deste módulo: **na dúvida, não mexe**. Arquivo que não se encaixa
num tipo reconhecido continua onde está e aparece no relatório — é melhor ela
arrastar três arquivos à mão do que a automação enterrar um documento numa
subpasta errada.
"""

import re
import shutil
import unicodedata
from pathlib import Path

DESTINO = "DOC CLIENTE"

# Nome do arquivo (sem acento, maiúsculo) -> tipo. A ordem importa: o primeiro
# padrão que casar decide.
TIPOS = (
    ("CNH", r"\bCNH\b|CARTEIRA (NACIONAL )?DE HABILITACAO|HABILITACAO"),
    ("CRLV", r"\bCRLV\b|CERTIFICADO DE REGISTRO E LICENCIAMENTO"),
    ("comprovante de residência",
     r"COMPROVANTE DE RESID|C DE RESID|COMRPVANTE|RESIDENCIA|CONTA DE (LUZ|ENERGIA|AGUA)|FATURA"),
    ("RG", r"\bRG\b|IDENTIDADE|CARTEIRA DE IDENTIDADE"),
    ("comprovante de renda",
     r"HOLERITE|CONTRACHEQUE|DEMONSTRATIVO DE PAGAMENTO|\bCTPS\b|CARTEIRA DE TRABALHO"
     r"|EXTRATO|BENEFICIO|APOSENTADORIA|\bINSS\b"),
    # Contrato do cliente com o banco. Vem com mil nomes — "contrato honda",
    # "contrato virtuss", "contrato_122749028" —, então a regra é ampla e o
    # cuidado está na exceção logo abaixo: contrato NOSSO nunca entra aqui.
    ("contrato de financiamento", r"\bCONTRATO\b|FINANCIAMENTO|CEDULA DE CREDITO"),
)

# "Contrato" que NÃO é do cliente: é o de honorários, que pertence a CONTRATO HO.
# Sem esta lista, o contrato de prestação de serviços do Roberto Araujo iria
# parar em DOC CLIENTE.
CONTRATO_DO_ESCRITORIO = (r"PRESTACAO DE SERVICOS", r"HONORARIOS", r"\bHO\b",
                          r"PROCURACAO", r"DECLARACAO", r"HIPOSSUFICIENCIA")

# Nunca movidos por este módulo: são do escritório e já têm lugar próprio.
NOSSOS = (r"CONTRATO HO ASSINADO", r"PROCURACAO ASSINADA", r"DECLARACAO DE HIPO",
          r"DECLARACAO DE RESIDENCIA ASSINADA", r"\[ASSINADO\]", r"^ONBOARDING")


def _limpo(texto: str) -> str:
    normal = unicodedata.normalize("NFKD", texto or "")
    normal = "".join(c for c in normal if not unicodedata.combining(c))
    return re.sub(r"[_\-.]+", " ", normal).upper()


def classificar(nome_arquivo: str) -> str:
    """Devolve o tipo do documento, ou "" quando não reconhece."""
    alvo = _limpo(nome_arquivo)
    if any(re.search(padrao, alvo) for padrao in NOSSOS):
        return ""
    for tipo, padrao in TIPOS:
        if not re.search(padrao, alvo):
            continue
        if tipo == "contrato de financiamento" and \
                any(re.search(excecao, alvo) for excecao in CONTRATO_DO_ESCRITORIO):
            return ""            # é contrato de honorários; não é do cliente
        return tipo
    return ""


def documentos_soltos(pasta_cliente) -> list:
    """(arquivo, tipo) de cada documento de cliente solto na raiz da pasta."""
    pasta_cliente = Path(pasta_cliente)
    if not pasta_cliente.is_dir():
        return []
    achados = []
    for arquivo in sorted(pasta_cliente.iterdir()):
        if not arquivo.is_file() or arquivo.name.startswith("."):
            continue
        tipo = classificar(arquivo.name)
        if tipo:
            achados.append((arquivo, tipo))
    return achados


def nao_reconhecidos(pasta_cliente) -> list:
    """Arquivos soltos que a automação NÃO sabe classificar — ficam onde estão."""
    pasta_cliente = Path(pasta_cliente)
    if not pasta_cliente.is_dir():
        return []
    return [a for a in sorted(pasta_cliente.iterdir())
            if a.is_file() and not a.name.startswith(".") and not classificar(a.name)]


def _nome_livre(destino: Path) -> Path:
    if not destino.exists():
        return destino
    n = 2
    while True:
        alternativo = destino.with_name("%s (%d)%s" % (destino.stem, n, destino.suffix))
        if not alternativo.exists():
            return alternativo
        n += 1


def arrumar(pasta_cliente, separador=None) -> list:
    """
    Move os documentos reconhecidos para DOC CLIENTE.

    Devolve [(arquivo, tipo, destino)] do que foi movido. Não sobrescreve nada:
    arquivo de mesmo nome no destino vira "... (2).pdf".
    """
    pasta_cliente = Path(pasta_cliente)
    achados = documentos_soltos(pasta_cliente)
    if not achados:
        return []

    if separador is not None:
        pasta = separador.resolver_subpasta(pasta_cliente, ["DOC CLIENTE", "DOCS CLIENTE"])
    else:
        pasta = pasta_cliente / DESTINO
    pasta.mkdir(parents=True, exist_ok=True)

    movidos = []
    for arquivo, tipo in achados:
        destino = _nome_livre(pasta / arquivo.name)
        try:
            shutil.move(str(arquivo), str(destino))
        except OSError:
            continue
        movidos.append((arquivo.name, tipo, destino))
    return movidos
