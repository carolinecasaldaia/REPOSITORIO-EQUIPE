"""Aperfeiçoamentos após a validação VAL-001 — dados FICTÍCIOS, oráculos independentes."""

from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest

from cm_calc.motor.atualizacao import (
    Acumulacao, ContagemJuros, ConvencaoCompetencias, CriterioCorrecao, CriterioInvalido, CriterioJuros, Fase,
    ParametrosAtualizacao, SerieMensal, TipoJuros, atualizar, atualizar_por_fases,
)
from cm_calc.motor.auditoria import Memoria, Origem, TipoRessalva
from cm_calc.motor.datas import vencimentos_mensais
from cm_calc.motor.financiamento import ParcelaPrevista, calcular_parcela_regular
from cm_calc.motor.numeros import D, ModoArredondamento, PoliticaArredondamento
from cm_calc.motor.revisao import ParametrosRevisao, TratamentoReforcadas, recalcular_contrato
from cm_calc.motor.taxas import ConvencaoTempo, Regime, Taxa

TITULO = Origem(documento="Acórdão fictício", localizacao="fls. 1", trecho="juros de mora desde o vencimento da 1ª parcela")
SEM_TRECHO = Origem(documento="Acórdão fictício")
FIM = date(2100, 1, 1)
SERIES = {
    "IDX": SerieMensal(nome="IDX", fonte="fictícia", valores={f"2024-{m:02d}": D("0.01") for m in range(1, 13)}),
    "TX": SerieMensal(nome="TX", fonte="fictícia", embute_correcao=True,
                      valores={f"2024-{m:02d}": D("0.02") for m in range(1, 13)}),
}
CONV = ConvencaoCompetencias(incluir_mes_inicial=False, incluir_mes_final=True)


# --- 1) políticas de arredondamento ----------------------------------------------------------------

def test_politica_por_texto():
    p = PoliticaArredondamento.de_texto("2;HALF_UP;integral")
    assert not p.arredondar_cada_parcela and not p.arredondar_prestacao and "integral" in p.descricao()
    assert PoliticaArredondamento.de_texto("2;HALF_UP;por_parcela").arredondar_prestacao
    with pytest.raises(ValueError):
        PoliticaArredondamento.de_texto("2;HALF_UP;sempre")


def test_prestacao_integral_nao_e_arredondada():
    parcelas = [ParcelaPrevista(numero=k + 1, vencimento=d) for k, d in enumerate(vencimentos_mensais(date(2024, 2, 1), 12))]
    taxa = Taxa(mensal=D("0.014"), regime=Regime.COMPOSTO, convencao=ConvencaoTempo.MESES_CIVIS)
    integral = calcular_parcela_regular(D(10000), date(2024, 1, 1), parcelas, taxa, PoliticaArredondamento.integral())
    centavo = calcular_parcela_regular(D(10000), date(2024, 1, 1), parcelas, taxa,
                                       PoliticaArredondamento.de_texto("2;HALF_UP;por_parcela"))
    i = Fraction("0.014")
    exato = Fraction(10000) * i / (1 - (1 + i) ** -12)
    assert abs(Fraction(integral.parcela_regular) - exato) < Fraction(1, 10**25)      # todos os dígitos
    assert centavo.parcela_regular == integral.parcela_regular.quantize(D("0.01"))


def test_revisao_proporcional_integral_preserva_razao_exata():
    parcelas = [ParcelaPrevista(numero=k + 1, vencimento=d, valor_fixo=(D("3000") if k + 1 == 6 else None))
                for k, d in enumerate(vencimentos_mensais(date(2024, 2, 1), 12))]
    taxa = Taxa(mensal=D("0.01"), regime=Regime.COMPOSTO, convencao=ConvencaoTempo.MESES_CIVIS)
    p = ParametrosRevisao(taxa_revisada=taxa, origem_taxa=TITULO, tratamento_reforcadas=TratamentoReforcadas.PROPORCIONAL)
    r = recalcular_contrato(D(15000), date(2024, 1, 1), parcelas, D("1100"), p, PoliticaArredondamento.integral(), Memoria())
    assert r.parcelas_revisadas[6] / D("3000") == r.parcelas_revisadas[1] / D("1100")        # mesma proporção, sem arredondar
    assert r.parcelas_revisadas[1] != r.parcelas_revisadas[1].quantize(D("0.01"))


# --- 2) juros de mora com termo inicial anterior ao pagamento ------------------------------------

def _juros(antes, origem=TITULO):
    return ParametrosAtualizacao(
        correcao=[CriterioCorrecao(inicio=date(1900, 1, 1), fim=FIM, serie=None, origem=TITULO)],
        juros=[CriterioJuros(inicio=date(2024, 1, 10), fim=FIM, tipo=TipoJuros.PERCENTUAL_FIXO, percentual_mensal=D("0.01"),
                             contagem=ContagemJuros.MESES_CIVIS, origem=TITULO)],
        competencias=CONV, acumulacao_juros=Acumulacao.SOMA, juros_desde_antes_do_valor=antes,
        origem_juros_antes_do_valor=origem if antes else None)


def test_padrao_continua_contando_juros_so_desde_o_pagamento():
    m = Memoria()
    r = atualizar(D(100), date(2024, 4, 10), date(2024, 7, 10), _juros(False), {}, PoliticaArredondamento.integral(), m)
    assert r.percentual_juros == D("0.03")                                        # abr→jul = 3 meses
    assert any("posterior ao termo inicial" in x.texto for x in m.ressalvas)


def test_juros_desde_antes_do_pagamento_quando_o_titulo_determina():
    m = Memoria()
    r = atualizar(D(100), date(2024, 4, 10), date(2024, 7, 10), _juros(True), {}, PoliticaArredondamento.integral(), m)
    assert r.percentual_juros == D("0.06")                                        # jan→jul = 6 meses
    assert any("ANTES da data do valor" in x.texto and x.tipo is TipoRessalva.PREMISSA for x in m.ressalvas)


def test_juros_antes_do_pagamento_exigem_trecho_do_titulo():
    with pytest.raises(ValueError, match="trecho do título"):
        _juros(True, origem=SEM_TRECHO)


# --- 3) atualização em fases com consolidação do subtotal ----------------------------------------

def _fase1():
    return ParametrosAtualizacao(
        correcao=[CriterioCorrecao(inicio=date(1900, 1, 1), fim=FIM, serie="IDX", origem=TITULO)],
        juros=[CriterioJuros(inicio=date(2024, 1, 15), fim=FIM, tipo=TipoJuros.PERCENTUAL_FIXO, percentual_mensal=D("0.01"),
                             contagem=ContagemJuros.MESES_CIVIS, origem=TITULO)],
        competencias=CONV, acumulacao_juros=Acumulacao.SOMA)


def _fase2(acum):
    return ParametrosAtualizacao(
        correcao=[CriterioCorrecao(inicio=date(1900, 1, 1), fim=FIM, serie=None, origem=TITULO)],
        juros=[CriterioJuros(inicio=date(2024, 4, 15), fim=FIM, tipo=TipoJuros.SERIE, serie="TX", origem=TITULO)],
        competencias=ConvencaoCompetencias(incluir_mes_inicial=False, incluir_mes_final=False), acumulacao_juros=acum)


@pytest.mark.parametrize("acum,fator_fase2", [(Acumulacao.PRODUTO, D("1.02") ** 3), (Acumulacao.SOMA, D("1.06"))])
def test_selic_sobre_subtotal_consolidado(acum, fator_fase2):
    pol = PoliticaArredondamento.integral()
    fases = [Fase(fim=date(2024, 4, 15), descricao="índice + mora até a citação", parametros=_fase1(), origem=TITULO),
             Fase(fim=date(2024, 8, 20), descricao="taxa única após a citação", parametros=_fase2(acum), origem=TITULO)]
    r = atualizar_por_fases(D(100), date(2024, 1, 15), fases, SERIES, pol, Memoria())
    # fase 1: fev, mar, abr de IDX (1%) = 1,01³; juros 3 meses = 3% sobre o corrigido
    sub = D(100) * D("1.01") ** 3 * D("1.03")
    assert abs(r.fases[0].total_exato - sub) < D("1e-25")
    # fase 2: mai, jun, jul (agosto excluído) sobre o SUBTOTAL consolidado
    assert abs(r.total_exato - sub * fator_fase2) < D("1e-25")
    assert r.total == r.total_exato.quantize(D("0.01"))


def test_fases_fora_de_ordem():
    f = Fase(fim=date(2024, 4, 15), descricao="x", parametros=_fase1(), origem=TITULO)
    with pytest.raises(CriterioInvalido):
        atualizar_por_fases(D(1), date(2024, 1, 1), [f, f], SERIES, PoliticaArredondamento.integral())


def test_consolidacao_por_parcela_usa_total_arredondado():
    pol = PoliticaArredondamento.de_texto("2;HALF_UP;por_parcela")
    fases = [Fase(fim=date(2024, 4, 15), descricao="f1", parametros=_fase1(), origem=TITULO),
             Fase(fim=date(2024, 8, 20), descricao="f2", parametros=_fase2(Acumulacao.PRODUTO), origem=TITULO)]
    r = atualizar_por_fases(D("0.04"), date(2024, 1, 15), fases, SERIES, pol)
    assert r.fases[1].valor_original == r.fases[0].total                          # base = subtotal arredondado
