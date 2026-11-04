#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR dos documentos digitalizados, pelo reconhecimento do próprio macOS.

Este arquivo é a fonte; cada projeto tem uma cópia ao lado do seu código, do
mesmo jeito que o separador e o gerador de onboarding são reaproveitados.

Quem lê de verdade é `~/.ocr-escritorio/ler-pdf`, um programa compilado a
partir de OCR/ler_pdf.swift. Escolha de 08/09/2026: a máquina não tem Homebrew,
e o reconhecimento da Apple é melhor em português do que o Tesseract — é o
mesmo que a Visualização usa para selecionar texto numa foto.

**O resultado é guardado em cache.** Sem isso, a rodada de hora em hora
reconheceria os mesmos CRLVs treze vezes por dia. A chave é o conteúdo do
arquivo: documento trocado é lido de novo, documento igual sai do cache.
"""

import hashlib
import subprocess
from pathlib import Path

PROGRAMA = Path.home() / ".ocr-escritorio" / "ler-pdf"
CACHE = Path.home() / ".ocr-escritorio" / "cache"
PAGINAS_PADRAO = 5
SEGUNDOS = 180


def disponivel() -> bool:
    """O OCR está instalado? Sem ele, tudo continua funcionando como antes."""
    return PROGRAMA.exists()


def _chave(caminho: Path, paginas: int) -> str:
    resumo = hashlib.sha1()
    with open(str(caminho), "rb") as arquivo:
        for pedaco in iter(lambda: arquivo.read(1 << 20), b""):
            resumo.update(pedaco)
    resumo.update(str(paginas).encode("ascii"))
    return resumo.hexdigest()


def ler(caminho, paginas: int = PAGINAS_PADRAO, usar_cache: bool = True) -> str:
    """
    Texto reconhecido do PDF. Devolve "" quando não dá — nunca levanta erro.

    Falha de OCR não pode derrubar rodada: o documento apenas continua
    ilegível, como era antes de existir OCR.
    """
    caminho = Path(caminho)
    if not disponivel() or not caminho.is_file():
        return ""

    guardado = None
    if usar_cache:
        try:
            CACHE.mkdir(parents=True, exist_ok=True)
            guardado = CACHE / ("%s.txt" % _chave(caminho, paginas))
            if guardado.exists():
                return guardado.read_text(encoding="utf-8", errors="replace")
        except OSError:
            guardado = None

    try:
        resultado = subprocess.run(
            [str(PROGRAMA), str(caminho), str(paginas)],
            capture_output=True, text=True, timeout=SEGUNDOS)
    except (subprocess.TimeoutExpired, OSError):
        return ""
    if resultado.returncode != 0:
        return ""

    texto = resultado.stdout or ""
    if guardado is not None:
        try:
            guardado.write_text(texto, encoding="utf-8")
        except OSError:
            pass
    return texto
