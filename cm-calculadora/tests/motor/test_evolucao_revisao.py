"""Conta gráfica (pagamentos parciais/antecipados), recálculo de juros e revisão."""

from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest

from cm_calc.motor.auditoria import FICTICIO, Origem, TipoRessalva
from cm_calc.motor.datas import vencimentos_mensais
from cm_calc.motor.evolucao import Evento, OrdemImputacao, evoluir_saldo
from cm_calc.motor.financiamento import ParcelaPrevista, calcular_parcela_regular
from cm_calc.motor.numeros import D
from cm_calc.motor.revisao import (
    ItemExcluido, ParametrosRevisao, TratamentoReforcadas, recalcular_contrato,
)
from cm_calc.motor.taxas import ConvencaoTempo, Regime, Taxa
from tests.conftest import coef_price_exato, fr

TITULO = Origem(documento="Sentença fictícia", localizacao="dispositivo, item a", trecho="texto fictício")


def taxa(i, regime=Regime.COMPOSTO, conv=ConvencaoTempo.MESES_CIVIS):
    return Taxa(mensal=D(i), regime=regime, convencao=conv)


# --- Pagamentos parciais, antecipados e excedentes -------------------------------

def test_pagamento_parcial_menor_que_juros(pol_banco, memoria):
    ev = [Evento(data=date(2024, 2, 1), valor=D(500)),
          Evento(data=date(2024, 3, 1), valor=D(5)),
          Evento(data=date(2024, 4, 1), valor=D(600))]
    r = evoluir_saldo(D(1000), date(2024, 1, 1), ev, taxa("0.01"), pol_banco,
                      OrdemImputacao.JUROS_PRIMEIRO, memoria)
    l1, l2, l3 = r.linhas
    assert (l1.juros_periodo, l1.amortizacao, l1.capital) == (D("10.00"), D(490), D(510))
    assert (l2.juros_periodo, l2.juros_pagos, l2.juros_pendentes) == (D("5.10"), D(5), D("0.10"))
    # composto: juros sobre 510,10 = 5,101 -> 5,10
    assert l3.juros_periodo == D("5.10")
    assert l3.excedente == D("84.80") and r.saldo_final == 0
    assert r.conciliacao(D(1000)) == {"pagamentos": 0, "saldo": 0}
    assert any(x.tipo is TipoRessalva.ALERTA for x in memoria.ressalvas)       # amortização negativa
    assert any("excedentes" in x.texto for x in memoria.ressalvas)


def test_composto_versus_simples_sem_pagamentos(pol_banco):
    ev = [Evento(data=date(2024, 4, 1), valor=D(0))]
    comp = evoluir_saldo(D(1000), date(2024, 1, 1), ev, taxa("0.01"), pol_banco, OrdemImputacao.JUROS_PRIMEIRO)
    simp = evoluir_saldo(D(1000), date(2024, 1, 1), ev, taxa("0.01", Regime.SIMPLES), pol_banco,
                         OrdemImputacao.JUROS_PRIMEIRO)
    assert comp.saldo_final == D("1030.30")     # 1000 × 1,01³
    assert simp.saldo_final == D("1030.00")     # 1000 × (1 + 3 × 0,01)


def test_simples_nao_capitaliza_juros_pendentes(pol_banco):
    ev = [Evento(data=date(2024, m, 1), valor=D(0)) for m in (2, 3, 4)]
    r = evoluir_saldo(D(1000), date(2024, 1, 1), ev, taxa("0.01", Regime.SIMPLES), pol_banco,
                      OrdemImputacao.JUROS_PRIMEIRO)
    assert [l.juros_periodo for l in r.linhas] == [D(10), D(10), D(10)]


def test_pagamento_antecipado_meio_mes(pol_banco):
    t = taxa("0.01", conv=ConvencaoTempo.MESES_30)
    ev = [Evento(data=date(2024, 1, 16), valor=D("1004.99"))]       # 15 dias = 0,5 mês
    r = evoluir_saldo(D(1000), date(2024, 1, 1), ev, t, pol_banco, OrdemImputacao.JUROS_PRIMEIRO)
    assert r.linhas[0].juros_periodo == D("4.99")                   # 1000 × (1,01^0,5 − 1) = 4,9876
    assert r.saldo_final == 0 and r.total_excedente == 0


def test_ordem_capital_primeiro(pol_banco):
    ev = [Evento(data=date(2024, 2, 1), valor=D(100))]
    r = evoluir_saldo(D(1000), date(2024, 1, 1), ev, taxa("0.01"), pol_banco, OrdemImputacao.CAPITAL_PRIMEIRO)
    assert (r.linhas[0].capital, r.linhas[0].juros_pendentes) == (D(900), D(10))


def test_posicao_na_data_base(pol_banco):
    r = evoluir_saldo(D(1000), date(2024, 1, 1), [], taxa("0.01"), pol_banco,
                      OrdemImputacao.JUROS_PRIMEIRO, data_final=date(2024, 3, 1))
    assert r.saldo_final == D("1020.10")


def test_evento_anterior_ao_inicio(pol_banco):
    with pytest.raises(ValueError):
        evoluir_saldo(D(1000), date(2024, 1, 1), [Evento(data=date(2023, 12, 1), valor=D(1))],
                      taxa("0.01"), pol_banco, OrdemImputacao.JUROS_PRIMEIRO)


# --- Recálculo de juros remuneratórios / exclusão de tarifas ------------------

LIB = date(2023, 1, 10)


def parcelas(n, fixas=None):
    fixas = fixas or {}
    return [ParcelaPrevista(numero=k + 1, vencimento=d, valor_fixo=fixas.get(k + 1))
            for k, d in enumerate(vencimentos_mensais(date(2023, 2, 10), n))]


def test_revisao_taxa_e_exclusao_de_tarifas(pol_banco, memoria):
    p = parcelas(36)
    orig = calcular_parcela_regular(D(30000), LIB, p, taxa("0.025"), pol_banco).parcela_regular
    params = ParametrosRevisao(
        taxa_revisada=taxa("0.018"), origem_taxa=TITULO,
        itens_excluidos=[
            ItemExcluido(descricao="Tarifa fictícia A", valor=D(1000), financiado=True, origem_titulo=TITULO),
            ItemExcluido(descricao="Seguro fictício", valor=D(500), financiado=True, origem_titulo=TITULO),
        ],
    )
    r = recalcular_contrato(D(30000), LIB, p, orig, params, pol_banco, memoria)
    assert r.valor_financiado_revisado == D(28500)
    exato = fr(28500) * coef_price_exato(fr("0.018"), 36)
    assert abs(fr(r.parcela_regular_revisada) - exato) <= Fraction(1, 200)   # arredondado ao centavo
    assert r.parcela_regular_revisada < orig
    assert all(v == r.parcela_regular_revisada for v in r.parcelas_revisadas.values())
    assert any("IOF" in x.texto and x.tipo is TipoRessalva.PENDENCIA for x in memoria.ressalvas)
    assert all(ps.origem for ps in memoria.da_etapa("AP02"))


def test_revisao_com_reforcadas_exige_criterio(pol_banco, memoria):
    p = parcelas(12, fixas={6: D(3000), 12: D(3000)})
    params = ParametrosRevisao(taxa_revisada=taxa("0.015"), origem_taxa=TITULO)
    with pytest.raises(ValueError, match="reforçadas"):
        recalcular_contrato(D(20000), LIB, p, D(1000), params, pol_banco, memoria)


def test_revisao_reforcadas_manter_valor(pol_banco, memoria):
    p = parcelas(12, fixas={6: D(3000), 12: D(3000)})
    orig = calcular_parcela_regular(D(20000), LIB, p, taxa("0.025"), pol_banco).parcela_regular
    params = ParametrosRevisao(taxa_revisada=taxa("0.015"), origem_taxa=TITULO,
                               tratamento_reforcadas=TratamentoReforcadas.MANTER_VALOR)
    r = recalcular_contrato(D(20000), LIB, p, orig, params, pol_banco, memoria)
    assert r.parcelas_revisadas[6] == D(3000) and r.parcelas_revisadas[12] == D(3000)
    assert r.parcela_regular_revisada < orig


def test_revisao_reforcadas_proporcional(pol_banco, memoria):
    p = parcelas(12, fixas={6: D(3000), 12: D(3000)})
    t_orig = taxa("0.025")
    orig = calcular_parcela_regular(D(20000), LIB, p, t_orig, pol_banco).parcela_regular
    t_rev = taxa("0.015")
    params = ParametrosRevisao(taxa_revisada=t_rev, origem_taxa=TITULO,
                               tratamento_reforcadas=TratamentoReforcadas.PROPORCIONAL)
    r = recalcular_contrato(D(20000), LIB, p, orig, params, pol_banco, memoria)
    vp = sum(r.parcelas_revisadas[x.numero] / t_rev.fator(LIB, x.vencimento) for x in p)
    assert abs(vp - D(20000)) < D("0.01") * len(p)
    razao_reforco = r.parcelas_revisadas[6] / D(3000)
    razao_regular = r.parcela_regular_revisada / orig
    assert abs(razao_reforco - razao_regular) < D("0.0001")


def test_item_avulso_sem_data_recusado(pol_banco, memoria):
    params = ParametrosRevisao(
        taxa_revisada=taxa("0.015"), origem_taxa=TITULO,
        itens_excluidos=[ItemExcluido(descricao="Tarifa", valor=D(100), financiado=False, origem_titulo=TITULO)],
    )
    with pytest.raises(ValueError, match="data de pagamento"):
        recalcular_contrato(D(1000), LIB, parcelas(6), D(180), params, pol_banco, memoria)
