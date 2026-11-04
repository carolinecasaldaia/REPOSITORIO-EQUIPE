#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trava de documentação: a pasta do cliente só anda se estiver completa.

Decisão dela (25/09/2026): nem o cadastro no Astrea, nem a abertura do caso,
nem a cópia da pasta para "A - REVISIONAL"/"A - CÍVEL" acontecem enquanto a
pasta do COMERCIAL não tiver todos os documentos do cliente:

    - RG ou CNH (a CNH vale como identidade)
    - COMPROVANTE DE RESIDÊNCIA
    - CRLV — só nos casos de veículo (Busca e Apreensão e Revisional
      Veicular); tipo de ação não identificado exige também, por segurança

O contrato bancário chegou a fazer parte da lista e foi retirado por ela no
mesmo dia (25/09/2026). O Contrato HO assinado continua exigido, pelo
cadastro (`validators.analise.montar`).

O documento é reconhecido **só pelo nome do arquivo e da subpasta** — decisão
dela: arquivo com nome que não diz o que é ("WhatsApp Image….jpeg") não
conta. A pasta trava, o relatório de pendências diz o que
falta, o comercial renomeia o arquivo e a rodada seguinte libera sozinha
(PENDENTE não é status definitivo — a pasta é reavaliada toda rodada).

Os padrões ficam aqui, separados de `extractors.documentos.classificar`, de
propósito: aquela classificação decide que arquivo é LIDO para conferir
dados (ex.: CEP e CPF no comprovante). Afrouxar lá para a trava mudaria as
conferências de todo cliente; aqui só se decide se o documento está presente.
"""

import os
import re
import unicodedata
from pathlib import Path

TIPOS_VEICULO = ("BUSCA E APREENSÃO", "REVISIONAL VEICULAR")

IDENTIDADE = "RG ou CNH"
COMPROVANTE = "COMPROVANTE DE RESIDÊNCIA"
CRLV = "CRLV"

# Aplicados sobre o caminho dentro da pasta do cliente, sem acento e em maiúsculas.
_IDENTIDADE = re.compile(r"\bRG\b|IDENTIDADE|\bCNH|HABILITACAO|CARTEIRA DE MOTORISTA")
# A DECLARAÇÃO DE RESIDÊNCIA assinada no escritório (Lei 7.115/83) vale como
# comprovante (decisão dela, 20/10/2026, no caso da Angela): é o documento
# emitido justamente para quem não tem conta de luz no próprio nome, e exigir
# as duas coisas travava cliente que já tinha o que o escritório pede. O que
# ela comprova aparece na ficha — ver `analise._checar_divergencias`.
_COMPROVANTE = re.compile(
    r"COMPROVANTE\s*(DE\s*)?RESID|COMP\.?\s*(DE\s*)?RESID|\bC\.?\s*DE\s*RESID|"
    r"CONTA\s+DE\s+(LUZ|ENERGIA|AGUA)|DECLARA[CÇ]AO\s*(DE\s*)?RESID")
_CRLV = re.compile(r"CRLV|\bCRV\b|DOCUMENTO\s+DO\s+VEICULO")
# Documento do responsável financeiro ("CNH RESP FINANCEIRO.pdf") é de outra
# pessoa: não vale como identidade do cliente.
_TERCEIRO = re.compile(r"RESP\.?\s*FINANC|RESPONSAVEL")

_EXTENSOES_IGNORADAS = (".docx", ".doc", ".ogg", ".opus", ".mp3", ".m4a",
                        ".mp4", ".xlsx", ".xls", ".csv", ".txt")


def _normal(texto):
    semacento = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in semacento if not unicodedata.combining(c)).upper()


def _arquivos(pasta):
    saida = []
    for caminho in sorted(Path(pasta).rglob("*")):
        if caminho.is_dir() or caminho.name.startswith("."):
            continue
        if caminho.suffix.lower() in _EXTENSOES_IGNORADAS:
            continue
        saida.append(caminho)
    return saida


def _alvo(caminho, pasta):
    """
    Caminho DENTRO da pasta do cliente ("DOC CLIENTE/CRLV.pdf"). O nome da
    própria pasta do cliente fica de fora: "14 - MARIANA - VEICULO APREENDIDO"
    não pode contar como documento do veículo.
    """
    try:
        relativo = caminho.relative_to(pasta)
    except ValueError:
        relativo = Path(caminho.name)
    return _normal(str(relativo))


def exige_crlv(tipo):
    """CRLV só em caso de veículo; tipo não identificado exige, por segurança."""
    return (not tipo) or tipo in TIPOS_VEICULO


def exigidos(tipo):
    itens = [IDENTIDADE, COMPROVANTE]
    if exige_crlv(tipo):
        itens.append(CRLV)
    return itens


def encontrados(pasta):
    """{item exigido: [arquivos que o comprovam]} — só o que foi achado."""
    pasta = Path(pasta)
    achados = {}
    for caminho in _arquivos(pasta):
        alvo = _alvo(caminho, pasta)
        if _IDENTIDADE.search(alvo) and not _TERCEIRO.search(alvo):
            achados.setdefault(IDENTIDADE, []).append(caminho)
        if _COMPROVANTE.search(alvo):
            achados.setdefault(COMPROVANTE, []).append(caminho)
        if _CRLV.search(alvo):
            achados.setdefault(CRLV, []).append(caminho)
    return achados


def faltantes(pasta, tipo):
    """
    Lista do que falta na pasta para o tipo de ação (nomenclatura do
    escritório, ver `astrea.casos.tipo_do_contrato`). Lista vazia = completa.
    """
    achados = encontrados(pasta)
    return [item for item in exigidos(tipo) if item not in achados]


def mensagem(faltando):
    return ("DOCUMENTAÇÃO INCOMPLETA — falta na pasta: %s. Coloque o documento "
            "na pasta do cliente com o nome dizendo o que ele é (ex.: 'RG.pdf', "
            "'CNH.pdf', 'COMPROVANTE DE RESIDÊNCIA.pdf', 'CRLV.pdf'); a "
            "próxima rodada libera sozinha."
            % ", ".join(faltando))


# ---------------------------------------------------------------------------
# Liberações manuais
# ---------------------------------------------------------------------------

# Decisão dela (20/10/2026, no caso da Angela): há cliente que não pode
# esperar o documento — defesa em busca e apreensão com veículo apreendido
# tem prazo correndo. Em vez de eu desligar a trava no código, ela escreve o
# nome no arquivo e só aquele cliente passa. O que falta continua aparecendo
# na ficha: liberar não é dizer que a pasta está completa.
ARQUIVO_LIBERACOES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "DOCUMENTAÇÃO - LIBERAÇÕES.txt")


def ler_liberacoes(caminho=ARQUIVO_LIBERACOES) -> dict:
    """{nome normalizado: motivo} dos clientes liberados da trava."""
    liberados = {}
    try:
        with open(caminho, encoding="utf-8") as arquivo:
            linhas = arquivo.read().splitlines()
    except OSError:
        return liberados
    for linha in linhas:
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        quem, motivo = (parte.strip() for parte in linha.split("=", 1))
        if quem:
            liberados[_normal(quem)] = motivo or "liberado manualmente"
    return liberados


def liberado(*nomes, liberacoes=None) -> str:
    """Motivo da liberação deste cliente, ou "" se ele não está liberado."""
    tabela = ler_liberacoes() if liberacoes is None else liberacoes
    for nome in nomes:
        motivo = tabela.get(_normal(nome))
        if motivo:
            return motivo
    return ""
