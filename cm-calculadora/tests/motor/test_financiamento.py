"""Coeficientes, amortização, parcelas reforçadas, capitalização diária e mensal."""

from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cm_calc.motor.evolucao import tabela_contratual
from cm_calc.motor.financiamento import (
    ParcelaPrevista, calcular_parcela_regular, coeficiente_price, cronograma_sac,
    parcela_gauss, parcela_price, valor_presente,
)
from cm_calc.motor.numeros import D
from cm_calc.motor.taxas import ConvencaoTempo, Regime, Taxa
from cm_calc.motor.datas import vencimentos_mensais
from tests.conftest import coef_price_exato, fr

LIB = date(2023, 1, 10)


def cronograma(n, primeiro=date(2023, 2, 10), fixas=None):
    fixas = fixas or {}
    return [ParcelaPrevista(numero=k + 1, vencimento=d, valor_fixo=fixas.get(k + 1))
            for k, d in enumerate(vencimentos_mensais(primeiro, n))]


# --- Coeficiente Price ---------------------------------------------------------

@pytest.mark.parametrize("i,n,pv,pmt", [
    ("0.01", 12, "10000", "888.49"),     # valor de tabela conhecido: 888,4879
    ("0.02", 24, "10000", "528.71"),     # 528,7110
    ("0.0199", 48, "30000", None),
])
def test_coeficiente_price_contra_oraculo_racional(i, n, pv, pmt):
    cf = coeficiente_price(D(i), n)
    exato = coef_price_exato(fr(i), n)
    assert abs(fr(cf) - exato) < Fraction(1, 10**28)
    if pmt:
        assert (D(pv) * cf).quantize(D("0.01")) == D(pmt)


def test_coeficiente_taxa_zero():
    assert coeficiente_price(D(0), 4) == D("0.25")


def test_gauss_formula_e_n1():
    assert parcela_gauss(D(1000), D("0.02"), 1) == D(1020)
    # PMT = 12000·(1+0,01·12)/(12·(1+0,01·11/2)) = 13440/12,66 = 1061,6113...
    assert parcela_gauss(D(12000), D("0.01"), 12).quantize(D("0.0001")) == D("1061.6114")


# --- Capitalização mensal (meses civis) = Price clássica ------------------------

def test_mensal_civil_igual_price(pol_banco, memoria):
    taxa = Taxa(mensal=D("0.015"), regime=Regime.COMPOSTO, convencao=ConvencaoTempo.MESES_CIVIS)
    r = calcular_parcela_regular(D(20000), LIB, cronograma(36), taxa, pol_banco, memoria)
    exato = fr(20000) * coef_price_exato(fr("0.015"), 36)
    assert abs(fr(r.parcela_regular_exata) - exato) < Fraction(1, 10**25)
    assert memoria.da_etapa("prestacao")


# --- Capitalização diária --------------------------------------------------------

def test_diaria_360_com_intervalos_de_30_dias_igual_price(pol_banco, memoria):
    t = Taxa(mensal=D("0.02"), regime=Regime.COMPOSTO, convencao=ConvencaoTempo.DIAS_BASE_360)
    parcelas = [ParcelaPrevista(numero=k, vencimento=LIB + timedelta(days=30 * k)) for k in range(1, 25)]
    r = calcular_parcela_regular(D(10000), LIB, parcelas, t, pol_banco, memoria)
    assert r.parcela_regular == D("528.71")


def test_diaria_365_difere_da_mensal_e_fecha_valor_presente(pol_exata):
    """Com dias reais entre vencimentos, a diária difere da mensal, mas o VP fecha."""
    taxa_anual = D("0.30")
    diaria = Taxa(mensal=D(0), anual=taxa_anual, regime=Regime.COMPOSTO, convencao=ConvencaoTempo.DIAS_BASE_365)
    parcelas = cronograma(24)
    r = calcular_parcela_regular(D(15000), LIB, parcelas, diaria, pol_exata)
    vp = valor_presente([(p.vencimento, r.parcela_regular_exata) for p in parcelas], LIB, diaria)
    assert abs(vp - D(15000)) < D("1e-20")

    from cm_calc.motor.taxas import anual_para_mensal
    mensal = Taxa(mensal=anual_para_mensal(taxa_anual, Regime.COMPOSTO), regime=Regime.COMPOSTO,
                  convencao=ConvencaoTempo.MESES_CIVIS)
    r_m = calcular_parcela_regular(D(15000), LIB, parcelas, mensal, pol_exata)
    assert r.parcela_regular_exata != r_m.parcela_regular_exata
    assert abs(r.parcela_regular_exata - r_m.parcela_regular_exata) < D(5)   # mesma ordem de grandeza


def test_diaria_oraculo_independente_float():
    """Oráculo independente em float (tolerância 1e-6) para expoente fracionário."""
    ia = 0.25
    parcelas = cronograma(12)
    t = Taxa(mensal=D(0), anual=D("0.25"), regime=Regime.COMPOSTO, convencao=ConvencaoTempo.DIAS_BASE_365)
    from cm_calc.motor.numeros import ModoArredondamento, PoliticaArredondamento
    pol = PoliticaArredondamento(casas=10, modo=ModoArredondamento.MEIO_PARA_PAR, arredondar_cada_parcela=False)
    r = calcular_parcela_regular(D(5000), LIB, parcelas, t, pol)
    soma = sum((1 + ia) ** (-(p.vencimento - LIB).days / 365) for p in parcelas)
    assert abs(float(str(r.parcela_regular_exata)) - 5000 / soma) < 1e-6


# --- Parcelas reforçadas -------------------------------------------------------

def test_parcelas_intercaladas_contra_oraculo(pol_banco, memoria):
    """24 mensais + 2 reforços de 5.000 (meses 12 e 24), 1,5% a.m."""
    i = fr("0.015")
    v = 1 / (1 + i)
    regulares = cronograma(24)
    reforcos = [
        ParcelaPrevista(numero=101, vencimento=regulares[11].vencimento, valor_fixo=D(5000)),
        ParcelaPrevista(numero=102, vencimento=regulares[23].vencimento, valor_fixo=D(5000)),
    ]
    taxa = Taxa(mensal=D("0.015"), regime=Regime.COMPOSTO, convencao=ConvencaoTempo.MESES_CIVIS)
    r = calcular_parcela_regular(D(50000), LIB, regulares + reforcos, taxa, pol_banco, memoria)
    a_n = (1 - v ** 24) / i
    esperado = (fr(50000) - 5000 * (v ** 12 + v ** 24)) / a_n
    assert abs(fr(r.parcela_regular_exata) - esperado) < Fraction(1, 10**24)


def test_parcela_balao_substitui_ultima(pol_banco, memoria):
    fixas = {12: D(8000)}
    parcelas = cronograma(12, fixas=fixas)
    taxa = Taxa(mensal=D("0.02"), regime=Regime.COMPOSTO, convencao=ConvencaoTempo.MESES_CIVIS)
    r = calcular_parcela_regular(D(20000), LIB, parcelas, taxa, pol_banco, memoria)
    i = fr("0.02"); v = 1 / (1 + i)
    esperado = (fr(20000) - 8000 * v ** 12) / ((1 - v ** 11) / i)
    assert abs(fr(r.parcela_regular_exata) - esperado) < Fraction(1, 10**24)
    tab = tabela_contratual(D(20000), LIB, parcelas, r.parcela_regular, taxa, pol_banco, memoria)
    assert abs(tab.saldo_final - tab.total_excedente) < D("0.10")


def test_cronograma_vazio_e_vencimento_anterior(pol_banco):
    taxa = Taxa(mensal=D("0.01"), regime=Regime.COMPOSTO, convencao=ConvencaoTempo.MESES_CIVIS)
    with pytest.raises(ValueError):
        calcular_parcela_regular(D(1000), LIB, [], taxa, pol_banco)
    with pytest.raises(ValueError):
        calcular_parcela_regular(D(1000), LIB, [ParcelaPrevista(numero=1, vencimento=date(2022, 1, 1))],
                                 taxa, pol_banco)


# --- Amortização (tabela) --------------------------------------------------------

def test_tabela_price_primeiras_linhas(pol_banco, memoria):
    """10.000 a 1% a.m. em 12x de 888,49 — valores de tabela conhecidos."""
    taxa = Taxa(mensal=D("0.01"), regime=Regime.COMPOSTO, convencao=ConvencaoTempo.MESES_CIVIS)
    tab = tabela_contratual(D(10000), LIB, cronograma(12), D("888.49"), taxa, pol_banco, memoria)
    l1, l2 = tab.linhas[0], tab.linhas[1]
    assert (l1.juros_periodo, l1.amortizacao, l1.saldo) == (D("100.00"), D("788.49"), D("9211.51"))
    assert (l2.juros_periodo, l2.amortizacao, l2.saldo) == (D("92.12"), D("796.37"), D("8415.14"))
    assert tab.conciliacao(D(10000)) == {"pagamentos": 0, "saldo": 0}
    # resíduo de arredondamento exibido, não absorvido
    assert abs(tab.saldo_final - tab.total_excedente) < D("0.10")


def test_sac(pol_banco):
    linhas = cronograma_sac(D(12000), D("0.01"), 12, pol_banco)
    assert linhas[0]["juros"] == D("120.00") and linhas[0]["parcela"] == D("1120.00")
    assert linhas[-1]["saldo"] == 0
    assert sum(l["amortizacao"] for l in linhas) == D(12000)


@settings(max_examples=60, deadline=None)
@given(
    vf=st.decimals(min_value=1000, max_value=500000, places=2),
    i=st.decimals(min_value="0.001", max_value="0.06", places=4),
    n=st.integers(min_value=1, max_value=96),
)
def test_propriedade_price_quita_exatamente_sem_arredondamento(vf, i, n):
    from cm_calc.motor.numeros import ModoArredondamento, PoliticaArredondamento
    pol = PoliticaArredondamento(casas=20, modo=ModoArredondamento.MEIO_PARA_PAR, arredondar_cada_parcela=False)
    taxa = Taxa(mensal=i, regime=Regime.COMPOSTO, convencao=ConvencaoTempo.MESES_CIVIS)
    p = cronograma(n)
    r = calcular_parcela_regular(vf, LIB, p, taxa, pol)
    tab = tabela_contratual(vf, LIB, p, r.parcela_regular_exata, taxa, pol)
    assert abs(tab.saldo_final) < D("1e-15")
    assert abs(sum(l.amortizacao for l in tab.linhas) - vf) < D("1e-15")


@settings(max_examples=60, deadline=None)
@given(
    vf=st.decimals(min_value=1000, max_value=500000, places=2),
    i=st.decimals(min_value="0.001", max_value="0.06", places=4),
    n=st.integers(min_value=1, max_value=96),
)
def test_propriedade_residuo_de_arredondamento_limitado(vf, i, n, ):
    from cm_calc.motor.numeros import ModoArredondamento, PoliticaArredondamento
    pol = PoliticaArredondamento(casas=2, modo=ModoArredondamento.MEIO_PARA_CIMA, arredondar_cada_parcela=True)
    taxa = Taxa(mensal=i, regime=Regime.COMPOSTO, convencao=ConvencaoTempo.MESES_CIVIS)
    p = cronograma(n)
    r = calcular_parcela_regular(vf, LIB, p, taxa, pol)
    tab = tabela_contratual(vf, LIB, p, r.parcela_regular, taxa, pol)
    residuo = tab.saldo_final - tab.total_excedente
    # cota: meio centavo da parcela capitalizado + meio centavo de juros por período
    cota = D("0.01") * n * (D(1) + i) ** n
    assert abs(residuo) <= cota
    assert tab.conciliacao(vf) == {"pagamentos": 0, "saldo": 0}
