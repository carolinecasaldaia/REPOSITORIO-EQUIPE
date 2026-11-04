"""Fixtures comuns. TODOS os dados aqui são fictícios."""

from fractions import Fraction

import pytest

from cm_calc.motor.auditoria import Memoria
from cm_calc.motor.numeros import ModoArredondamento, PoliticaArredondamento


@pytest.fixture
def pol_banco():
    """Arredondamento típico de sistema bancário: centavo, HALF_UP, por parcela."""
    return PoliticaArredondamento(casas=2, modo=ModoArredondamento.MEIO_PARA_CIMA,
                                  arredondar_cada_parcela=True)


@pytest.fixture
def pol_exata():
    """Sem arredondamento intermediário (casas altas) — para testar identidades exatas."""
    return PoliticaArredondamento(casas=20, modo=ModoArredondamento.MEIO_PARA_PAR,
                                  arredondar_cada_parcela=False)


@pytest.fixture
def memoria():
    return Memoria()


def fr(x) -> Fraction:
    """Oráculo independente: aritmética racional exata (sem Decimal, sem float)."""
    return Fraction(str(x))


def coef_price_exato(i: Fraction, n: int) -> Fraction:
    v = 1 / (1 + i)
    return i / (1 - v ** n)
