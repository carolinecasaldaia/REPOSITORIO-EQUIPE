"""Base numérica, arredondamentos e equivalência de taxas."""

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cm_calc.motor.datas import meses_civis_e_dias, somar_meses, vencimentos_mensais
from cm_calc.motor.numeros import (
    ModoArredondamento, PoliticaArredondamento, D, arredondar, brl, pct,
)
from cm_calc.motor.taxas import (
    ConvencaoTempo, Regime, Taxa, anual_para_mensal, mensal_para_anual,
)

MOTOR = Path(__file__).resolve().parents[2] / "src" / "cm_calc" / "motor"


# --- Decimal e proibição de float --------------------------------------------

def test_float_recusado():
    with pytest.raises(TypeError):
        D(0.1)


def test_motor_nao_usa_float():
    for arq in MOTOR.glob("*.py"):
        codigo = arq.read_text(encoding="utf-8")
        assert not re.search(r"\bfloat\(", codigo), f"float() em {arq.name}"
        assert "import math" not in codigo, f"math (float) em {arq.name}"


def test_pct_aceita_virgula():
    assert pct("1,99") == D("0.0199")
    assert pct("1.234,5") == D("12.345")
    assert pct("2") == D("0.02")


# --- Arredondamento ------------------------------------------------------------

@pytest.mark.parametrize("modo,esperado", [
    (ModoArredondamento.MEIO_PARA_CIMA, "2.35"),
    (ModoArredondamento.MEIO_PARA_PAR, "2.34"),
    (ModoArredondamento.TRUNCAR, "2.34"),
    (ModoArredondamento.PARA_CIMA, "2.35"),
])
def test_modos_de_arredondamento(modo, esperado):
    pol = PoliticaArredondamento(casas=2, modo=modo, arredondar_cada_parcela=True)
    assert arredondar(D("2.345"), pol) == D(esperado)


def test_arredondamento_negativo_half_up():
    pol = PoliticaArredondamento(casas=2, modo=ModoArredondamento.MEIO_PARA_CIMA, arredondar_cada_parcela=True)
    assert arredondar(D("-2.345"), pol) == D("-2.35")


@given(st.decimals(min_value=-10**9, max_value=10**9, allow_nan=False, allow_infinity=False, places=6))
def test_arredondar_idempotente(x):
    pol = PoliticaArredondamento(casas=2, modo=ModoArredondamento.MEIO_PARA_CIMA, arredondar_cada_parcela=True)
    assert arredondar(arredondar(x, pol), pol) == arredondar(x, pol)
    assert abs(arredondar(x, pol) - x) <= D("0.005")


def test_formatacao_brl():
    assert brl(D("1234567.891")) == "R$ 1.234.567,89"


# --- Equivalência de taxas (valores de referência conhecidos) -------------------

def test_mensal_para_anual_composto():
    # 1,01^12 = 1,126825030131969720661201
    assert mensal_para_anual(D("0.01"), Regime.COMPOSTO) == D("0.126825030131969720661201")


def test_mensal_para_anual_simples():
    assert mensal_para_anual(D("0.01"), Regime.SIMPLES) == D("0.12")


@given(st.decimals(min_value="0.0001", max_value="0.10", places=6))
def test_ida_e_volta_mensal_anual(i):
    volta = anual_para_mensal(mensal_para_anual(i, Regime.COMPOSTO), Regime.COMPOSTO)
    assert abs(volta - i) < D("1e-28")


def test_taxa_diaria_base_360_em_30_dias_equivale_a_mensal():
    t = Taxa(mensal=D("0.02"), regime=Regime.COMPOSTO, convencao=ConvencaoTempo.DIAS_BASE_360)
    f = t.fator(date(2024, 1, 1), date(2024, 1, 31))   # 30 dias
    assert abs(f - D("1.02")) < D("1e-30")


@given(st.integers(0, 400), st.integers(0, 400),
       st.sampled_from([ConvencaoTempo.DIAS_BASE_365, ConvencaoTempo.DIAS_BASE_360, ConvencaoTempo.MESES_30]))
def test_fator_composto_independe_do_fracionamento(d1, d2, conv):
    """Capitalizar em etapas = capitalizar de uma vez (consistência da conta gráfica)."""
    t = Taxa(mensal=D("0.0185"), regime=Regime.COMPOSTO, convencao=conv)
    a = date(2023, 1, 1)
    b = date.fromordinal(a.toordinal() + d1)
    c = date.fromordinal(b.toordinal() + d2)
    assert abs(t.fator(a, b) * t.fator(b, c) - t.fator(a, c)) < D("1e-28")


def test_fator_simples_e_linear():
    t = Taxa(mensal=D("0.01"), regime=Regime.SIMPLES, convencao=ConvencaoTempo.MESES_30)
    assert t.fator(date(2024, 1, 1), date(2024, 3, 1)) == D(1) + D("0.01") * D(60) / D(30)


# --- Datas ----------------------------------------------------------------------

def test_somar_meses_fim_de_mes():
    assert somar_meses(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert vencimentos_mensais(date(2023, 1, 31), 3) == [date(2023, 1, 31), date(2023, 2, 28), date(2023, 3, 31)]


def test_meses_civis_e_dias():
    assert meses_civis_e_dias(date(2024, 1, 15), date(2024, 3, 20)) == (2, 5)
    assert meses_civis_e_dias(date(2024, 1, 31), date(2024, 2, 29)) == (1, 0)
    assert meses_civis_e_dias(date(2024, 1, 15), date(2024, 1, 15)) == (0, 0)
