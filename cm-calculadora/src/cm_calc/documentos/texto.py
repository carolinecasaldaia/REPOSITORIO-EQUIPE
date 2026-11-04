"""Normalização e leitura de números, percentuais e datas em português."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
    "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}


def sem_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def normalizar(s: str) -> str:
    """Minúsculas, sem acentos. Mantém o comprimento (posições batem com o original)."""
    out = []
    for c in s:
        n = sem_acentos(c).lower()
        out.append(n[0] if n else c)
    return "".join(out)


RE_VALOR = r"R\$\s*(-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2})"
RE_PERCENT = r"(\d{1,3}(?:,\d{1,6})?)\s*%"
RE_DATA_NUM = r"(\d{1,2})/(\d{1,2})/(\d{4})"
RE_DATA_EXT = r"(\d{1,2})[ºo]?\s+de\s+(janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+(\d{4})"


def valor_br(s: str) -> Decimal:
    """'40.000,00' -> Decimal('40000.00')."""
    try:
        return Decimal(s.replace(".", "").replace(",", ".").strip())
    except InvalidOperation as e:
        raise ValueError(f"valor monetário ilegível: {s!r}") from e


def percentual_br(s: str) -> Decimal:
    """'1,99' -> Decimal('0.0199') (fração)."""
    return valor_br(s) / Decimal(100)


def data_num(d: str, m: str, a: str) -> date | None:
    try:
        return date(int(a), int(m), int(d))
    except ValueError:
        return None


def datas_no_texto(texto: str) -> list[tuple[int, date]]:
    """Todas as datas (numéricas e por extenso) com a posição no texto."""
    norm = normalizar(texto)
    achadas: list[tuple[int, date]] = []
    for m in re.finditer(RE_DATA_NUM, norm):
        d = data_num(*m.groups())
        if d:
            achadas.append((m.start(), d))
    for m in re.finditer(RE_DATA_EXT, norm):
        d = data_num(m.group(1), str(MESES[m.group(2)]), m.group(3))
        if d:
            achadas.append((m.start(), d))
    return sorted(achadas)


def primeira_data(texto: str) -> date | None:
    ds = datas_no_texto(texto)
    return ds[0][1] if ds else None


def dividir_clausulas(texto: str) -> list[tuple[int, int]]:
    """Divide um dispositivo em cláusulas (por ';', '.' final de frase e itens a), b)...).

    Retorna (início, fim) no texto original.
    """
    limites = [0]
    for m in re.finditer(r";|\.\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])|\n\s*[a-z]\)\s|\n\s*[ivx]+\s*[-–)]\s", texto):
        limites.append(m.end())
    limites.append(len(texto))
    return [(a, b) for a, b in zip(limites, limites[1:]) if texto[a:b].strip()]
