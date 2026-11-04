"""Datas: contagem de dias, meses civis e vencimentos mensais."""

from __future__ import annotations

import calendar
from datetime import date


def dias_corridos(inicio: date, fim: date) -> int:
    return (fim - inicio).days


def somar_meses(d: date, meses: int, dia_base: int | None = None) -> date:
    """Mesmo dia no mês alvo; se não existir (ex.: 31/02), usa o último dia do mês.

    ``dia_base`` preserva o dia original da série (31/01 -> 28/02 -> 31/03).
    """
    dia = dia_base or d.day
    total = d.year * 12 + (d.month - 1) + meses
    ano, mes = divmod(total, 12)
    mes += 1
    ultimo = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, min(dia, ultimo))


def vencimentos_mensais(primeiro: date, quantidade: int) -> list[date]:
    return [somar_meses(primeiro, k, dia_base=primeiro.day) for k in range(quantidade)]


def meses_civis_e_dias(inicio: date, fim: date) -> tuple[int, int]:
    """Meses completos de calendário entre as datas e dias remanescentes.

    Ex.: 15/01 -> 20/03 = (2 meses, 5 dias). Usa aniversário mensal pelo dia inicial.
    """
    if fim < inicio:
        raise ValueError("data final anterior à inicial")
    meses = (fim.year - inicio.year) * 12 + (fim.month - inicio.month)
    while meses > 0 and somar_meses(inicio, meses, dia_base=inicio.day) > fim:
        meses -= 1
    ancora = somar_meses(inicio, meses, dia_base=inicio.day)
    return meses, (fim - ancora).days


def competencia(d: date) -> tuple[int, int]:
    return d.year, d.month


def competencias_entre(inicio: tuple[int, int], fim: tuple[int, int]) -> list[tuple[int, int]]:
    """Lista (ano, mês) de ``inicio`` a ``fim``, ambos inclusive."""
    a, m = inicio
    out = []
    while (a, m) <= fim:
        out.append((a, m))
        m += 1
        if m == 13:
            a, m = a + 1, 1
    return out
