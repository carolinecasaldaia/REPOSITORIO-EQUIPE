#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Envelope com mais de um contrato de honorários no mesmo PDF.

Por que existe: em 01/09/2026 a Sofia Evangelista assinou **dois** contratos no
mesmo envelope do Autentique — um contra a NU PAGAMENTOS e outro contra o
Município de Jequiá da Praia. O separador juntou os dois num só
"Contrato HO Assinado.pdf", e o extrator leu apenas o primeiro **em silêncio**.
Sem ela ter percebido a olho, o segundo caso simplesmente não existiria.

O módulo conta, avisa **e separa**: decisão dela em 01/09/2026, depois de ver o
caso da Sofia. As pastas saem como "<CLIENTE> - CONTRATO 1" e
"<CLIENTE> - CONTRATO 2", nomes provisórios que ela troca à mão pelo que o caso
é de verdade (a Sofia virou "… - NU PAGAMENTOS" e "… - MUNICIPIO DE JEQUIA DA
PRAIA"). A automação não tenta adivinhar esse nome: ela sabe contar contratos,
não sabe batizar casos.

O que a separação faz, por pasta: o contrato daquele caso em "Contrato HO
Assinado.pdf", o envelope inteiro junto (nada se perde) e **cópia** dos
documentos do cliente e do escritório — procuração e declaração valem para os
dois casos.
"""

import re
import shutil
import unicodedata
from pathlib import Path

# Primeira linha de todo contrato de honorários do escritório.
_TITULO = re.compile(r"CONTRATO\s+DE\s+PRESTACAO\s+DE\s+SERVICOS\s+ADVOCATICIOS", re.I)

# O que cada contrato promete fazer. Serve para descrever os achados no aviso —
# dois contratos com objetos diferentes é o caso da Sofia.
_OBJETO = re.compile(r"para\s+realizar\s+(.{15,180}?)(?:,\s*referente|\.|Cl[áa]usula)", re.I | re.S)


def _sem_acento(texto: str) -> str:
    normal = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in normal if not unicodedata.combining(c))


def _paginas_de_texto(reader) -> list:
    paginas = []
    for pagina in reader.pages:
        try:
            paginas.append(re.sub(r"\s+", " ", pagina.extract_text() or ""))
        except Exception:                       # página estranha não derruba a rodada
            paginas.append("")
    return paginas


def conferir(reader) -> dict:
    """
    Diz se o PDF tem mais de um contrato. Devolve None quando é só um.

    {'quantos': 2, 'paginas': [1, 6], 'objetos': ['o ingresso da Ação ...', ...]}
    As páginas são numeradas como a pessoa lê: a primeira é 1.
    """
    if reader is None:
        return None
    paginas = _paginas_de_texto(reader)
    inicios = [n for n, texto in enumerate(paginas, 1)
               if _TITULO.search(_sem_acento(texto))]
    if len(inicios) < 2:
        return None

    objetos = []
    for posicao, comeco in enumerate(inicios):
        fim = inicios[posicao + 1] - 1 if posicao + 1 < len(inicios) else len(paginas)
        trecho = " ".join(paginas[comeco - 1:fim])
        achado = _OBJETO.search(trecho)
        objetos.append(re.sub(r"\s+", " ", achado.group(1)).strip() if achado else "")
    return {"quantos": len(inicios), "paginas": inicios, "objetos": objetos}


def recado(achado: dict, nome_cliente: str = "") -> str:
    """Frase para o relatório e para o aviso da tela."""
    if not achado:
        return ""
    quem = (" de %s" % nome_cliente) if nome_cliente else ""
    partes = ["ATENÇÃO: o envelope%s tem %d contratos de honorários, não um "
              "(páginas %s)." % (quem, achado["quantos"],
                                 ", ".join(str(p) for p in achado["paginas"]))]
    for numero, objeto in enumerate(achado["objetos"], 1):
        if objeto:
            partes.append("Contrato %d: %s." % (numero, objeto[:120]))
    partes.append("O onboarding e o caso saem só do primeiro. Se forem ações "
                  "diferentes, separe em uma pasta por contrato.")
    return " ".join(partes)


# Páginas de auditoria do Autentique, no fim do arquivo. Não são contrato: são a
# prova das assinaturas, e por isso acompanham TODOS os contratos separados.
#
# Cuidado que já custou uma tentativa: "Assinado com Assinatura Eletrônica" é
# **rodapé de todas as páginas** do contrato — usá-lo como marca fazia o
# programa achar que o documento inteiro era folha de assinatura. As marcas
# abaixo só aparecem na página de auditoria, e ainda assim se exige que a
# página **não** tenha corpo de contrato ("Cláusula").
_PAGINA_DE_ASSINATURA = re.compile(
    r"Identificador:|Data/Hora em GMT|(?:visualizou|assinou) o documento", re.I)
_CORPO_DE_CONTRATO = re.compile(r"Cl[áa]usula\s*\d|CLIENTE/CONTRATANTE", re.I)

SUFIXO = "CONTRATO %d"


def _paginas_comuns(paginas: list, ultimo_inicio: int) -> list:
    """Páginas de assinatura no fim do arquivo (1-based), depois do último contrato."""
    comuns = []
    for numero in range(len(paginas), ultimo_inicio, -1):
        texto = paginas[numero - 1]
        if _PAGINA_DE_ASSINATURA.search(texto) and not _CORPO_DE_CONTRATO.search(texto):
            comuns.insert(0, numero)
        else:
            break
    return comuns


def fatiar(reader) -> list:
    """
    Divide o PDF em contratos. Devolve [[páginas do contrato 1], [do 2], ...].

    As páginas de assinatura entram em todos. Numeração como a pessoa lê (1).
    """
    achado = conferir(reader)
    if not achado:
        return []
    paginas = _paginas_de_texto(reader)
    inicios = achado["paginas"]
    comuns = _paginas_comuns(paginas, inicios[-1])
    primeira_comum = comuns[0] if comuns else len(paginas) + 1

    fatias = []
    for posicao, comeco in enumerate(inicios):
        fim = (inicios[posicao + 1] - 1) if posicao + 1 < len(inicios) else (primeira_comum - 1)
        fatias.append(list(range(comeco, fim + 1)) + comuns)
    return fatias


def _copiar_paginas(reader, paginas: list, destino):
    from pypdf import PdfWriter
    escritor = PdfWriter()
    for numero in paginas:
        escritor.add_page(reader.pages[numero - 1])
    with open(str(destino), "wb") as saida:
        escritor.write(saida)


def separar(pasta_cliente, contrato_pdf, envelope_pdf=None, separador=None) -> list:
    """
    Uma pasta por contrato. Devolve a lista de pastas (a primeira é a renomeada).

    A pasta do cliente vira "<nome> - CONTRATO 1" e as demais nascem ao lado.
    Não faz nada — e devolve [] — se já houver pasta com esses nomes, para que
    rodar duas vezes não crie pasta repetida nem sobrescreva o que ela renomeou.
    """
    import io

    from pypdf import PdfReader
    from . import arquivar

    pasta_cliente = Path(pasta_cliente)
    contrato_pdf = Path(contrato_pdf)
    if not contrato_pdf.exists():
        return []
    if re.search(r" - CONTRATO \d+$", pasta_cliente.name):
        return []                          # já separada numa rodada anterior

    # O PDF inteiro para a memória ANTES de qualquer coisa. Dois motivos, os
    # dois descobertos na primeira tentativa (01/09/2026): a pasta é renomeada
    # no meio do caminho, o que deixa o caminho do arquivo para trás; e o
    # contrato 1 é gravado por cima do próprio arquivo que estava sendo lido —
    # ler e sobrescrever ao mesmo tempo saiu com 11 páginas em vez de 7.
    dados = contrato_pdf.read_bytes()
    reader = PdfReader(io.BytesIO(dados))
    fatias = fatiar(reader)
    if len(fatias) < 2:
        return []

    destinos = [pasta_cliente.with_name("%s - %s" % (pasta_cliente.name, SUFIXO % n))
                for n in range(1, len(fatias) + 1)]
    if any(d.exists() for d in destinos):
        return []                          # não mexe no que já existe

    # A pasta do cliente vira a do contrato 1; as outras nascem ao lado dela.
    pasta_cliente.rename(destinos[0])
    # Depois do rename, os caminhos de antes não existem mais.
    contrato_pdf = destinos[0] / contrato_pdf.parent.name / contrato_pdf.name
    if envelope_pdf:
        envelope_pdf = Path(envelope_pdf)
        envelope_pdf = destinos[0] / envelope_pdf.parent.name / envelope_pdf.name

    for destino in destinos[1:]:
        destino.mkdir()
        arquivar.garantir_subpastas(destino, separador)
        for sub in ("DOC CLIENTE", "DOC ESCRITÓRIO"):
            origem = destinos[0] / sub
            if not origem.is_dir():
                continue
            for arquivo in sorted(origem.glob("*")):
                if arquivo.is_file() and not arquivo.name.startswith("."):
                    shutil.copy2(str(arquivo), str(destino / sub / arquivo.name))
        if envelope_pdf and envelope_pdf.exists():
            shutil.copy2(str(envelope_pdf), str(destino / "CONTRATO HO" / envelope_pdf.name))

    for destino, paginas in zip(destinos, fatias):
        _copiar_paginas(reader, paginas, destino / "CONTRATO HO" / contrato_pdf.name)
    return destinos
