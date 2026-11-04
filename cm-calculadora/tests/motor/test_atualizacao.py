"""Correção monetária e juros. Séries de índices FICTÍCIAS (não são índices oficiais)."""

from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cm_calc.motor.atualizacao import (
    Acumulacao, ContagemJuros, ConvencaoCompetencias, CriterioCorrecao, CriterioInvalido,
    CriterioJuros, ParametrosAtualizacao, SerieIncompleta, SerieMensal, TipoJuros, atualizar,
)
from cm_calc.motor.auditoria import Origem
from cm_calc.motor.numeros import D

O = Origem(documento="Sentença fictícia", localizacao="dispositivo")
FIM = date(2030, 1, 1)
CONV = ConvencaoCompetencias(incluir_mes_inicial=True, incluir_mes_final=False)

SERIES = {
    "IDX_X": SerieMensal(nome="IDX_X", fonte="fictícia",
                         valores={"2024-01": D("0.01"), "2024-02": D("0.02"), "2024-03": D("-0.005"),
                                  "2024-04": D("0.003")}),
    "IDX_Y": SerieMensal(nome="IDX_Y", fonte="fictícia",
                         valores={"2024-03": D("0.004"), "2024-04": D("0.004")}),
    "TAXA_S": SerieMensal(nome="TAXA_S", fonte="fictícia", embute_correcao=True,
                          valores={"2024-01": D("0.008"), "2024-02": D("0.009"), "2024-03": D("0.008"),
                                   "2024-04": D("0.009")}),
    "A": SerieMensal(nome="A", fonte="fictícia", valores={"2024-01": D("0.008"), "2024-02": D("0.012")}),
    "B": SerieMensal(nome="B", fonte="fictícia", valores={"2024-01": D("0.010"), "2024-02": D("0.002")}),
}


def corr(serie, ini=date(2000, 1, 1), fim=FIM):
    return CriterioCorrecao(inicio=ini, fim=fim, serie=serie, origem=O)


def juros_fixo(ini, fim=FIM, pctm="0.01", contagem=ContagemJuros.DIAS_30):
    return CriterioJuros(inicio=ini, fim=fim, tipo=TipoJuros.PERCENTUAL_FIXO,
                         percentual_mensal=D(pctm), contagem=contagem, origem=O)


def test_correcao_e_juros_simples(pol_banco, memoria):
    p = ParametrosAtualizacao(correcao=[corr("IDX_X")], juros=[juros_fixo(date(2024, 1, 15))],
                              competencias=CONV, acumulacao_juros=Acumulacao.SOMA)
    r = atualizar(D(1000), date(2024, 1, 15), date(2024, 3, 20), p, SERIES, pol_banco, memoria)
    assert r.fator_correcao == D("1.0302")                  # jan e fev (mês final excluído)
    assert r.valor_corrigido == D("1030.20")
    # 65 dias / 30 × 1% = 2,1666...%  ->  1030,20 × 0,021666... = 22,321
    assert r.juros == D("22.32") and r.total == D("1052.52")
    assert memoria.da_etapa("atualizacao")[0].origem


def test_convencao_inclui_mes_final(pol_banco):
    conv = ConvencaoCompetencias(incluir_mes_inicial=True, incluir_mes_final=True)
    p = ParametrosAtualizacao(correcao=[corr("IDX_X")], juros=[], competencias=conv, acumulacao_juros=Acumulacao.SOMA)
    r = atualizar(D(1000), date(2024, 1, 15), date(2024, 3, 20), p, SERIES, pol_banco)
    assert r.fator_correcao == D("1.0302") * D("0.995")


def test_troca_de_indice_e_juros_por_taxa_que_embute_correcao(pol_banco, memoria):
    """Período 1: IDX_X + 1% a.m.; período 2 (a partir de 01/03): sem índice, juros pela TAXA_S."""
    p = ParametrosAtualizacao(
        correcao=[corr("IDX_X", fim=date(2024, 3, 1)), corr(None, ini=date(2024, 3, 1))],
        juros=[juros_fixo(date(2024, 1, 15), date(2024, 3, 1)),
               CriterioJuros(inicio=date(2024, 3, 1), fim=FIM, tipo=TipoJuros.SERIE, serie="TAXA_S", origem=O)],
        competencias=CONV, acumulacao_juros=Acumulacao.SOMA,
    )
    r = atualizar(D(1000), date(2024, 1, 15), date(2024, 4, 20), p, SERIES, pol_banco, memoria)
    assert r.fator_correcao == D("1.0302")
    # juros: 46 dias/30 × 1% + mar/2024 (0,8%) ; abril excluído pela convenção
    esperado_pct = D("0.01") * D(46) / D(30) + D("0.008")
    assert r.percentual_juros == esperado_pct
    assert r.juros == (D("1030.20") * esperado_pct).quantize(D("0.01"))


def test_mes_de_transicao_nao_conta_duas_vezes(pol_banco):
    p = ParametrosAtualizacao(
        correcao=[corr(None)],
        juros=[CriterioJuros(inicio=date(2024, 1, 1), fim=date(2024, 2, 15), tipo=TipoJuros.SERIE, serie="A", origem=O),
               CriterioJuros(inicio=date(2024, 2, 15), fim=FIM, tipo=TipoJuros.SERIE, serie="B", origem=O)],
        competencias=ConvencaoCompetencias(incluir_mes_inicial=True, incluir_mes_final=True),
        acumulacao_juros=Acumulacao.SOMA,
    )
    r = atualizar(D(1000), date(2024, 1, 1), date(2024, 2, 28), p, SERIES, pol_banco)
    assert r.percentual_juros == D("0.008") + D("0.012")      # fevereiro só uma vez (critério A em 01/02)


def test_cumulacao_de_indice_com_taxa_que_embute_correcao_e_bloqueada(pol_banco):
    p = ParametrosAtualizacao(
        correcao=[corr("IDX_X")],
        juros=[CriterioJuros(inicio=date(2024, 1, 1), fim=FIM, tipo=TipoJuros.SERIE, serie="TAXA_S", origem=O)],
        competencias=CONV, acumulacao_juros=Acumulacao.SOMA,
    )
    with pytest.raises(CriterioInvalido, match="embute correção"):
        atualizar(D(1000), date(2024, 1, 15), date(2024, 3, 20), p, SERIES, pol_banco)


@pytest.mark.parametrize("piso,esperado", [(True, D("0") + D("0.010")), (False, D("-0.002") + D("0.010"))])
def test_serie_menos_serie_com_e_sem_piso(pol_banco, piso, esperado):
    p = ParametrosAtualizacao(
        correcao=[corr(None)],
        juros=[CriterioJuros(inicio=date(2024, 1, 1), fim=FIM, tipo=TipoJuros.SERIE_MENOS_SERIE,
                             serie="A", serie_deduzir="B", piso_zero=piso, origem=O)],
        competencias=ConvencaoCompetencias(incluir_mes_inicial=True, incluir_mes_final=True),
        acumulacao_juros=Acumulacao.SOMA,
    )
    r = atualizar(D(1000), date(2024, 1, 1), date(2024, 2, 28), p, SERIES, pol_banco)
    assert r.percentual_juros == esperado


def test_acumulacao_soma_versus_produto(pol_banco):
    def com(acc):
        return ParametrosAtualizacao(
            correcao=[corr(None)],
            juros=[CriterioJuros(inicio=date(2024, 1, 1), fim=FIM, tipo=TipoJuros.SERIE, serie="A", origem=O)],
            competencias=ConvencaoCompetencias(incluir_mes_inicial=True, incluir_mes_final=True),
            acumulacao_juros=acc)
    s = atualizar(D(1000), date(2024, 1, 1), date(2024, 2, 28), com(Acumulacao.SOMA), SERIES, pol_banco)
    pr = atualizar(D(1000), date(2024, 1, 1), date(2024, 2, 28), com(Acumulacao.PRODUTO), SERIES, pol_banco)
    assert s.percentual_juros == D("0.020")
    assert pr.percentual_juros == D("1.008") * D("1.012") - 1


def test_juros_meses_civis(pol_banco):
    p = ParametrosAtualizacao(correcao=[corr(None)],
                              juros=[juros_fixo(date(2024, 1, 15), contagem=ContagemJuros.MESES_CIVIS)],
                              competencias=CONV, acumulacao_juros=Acumulacao.SOMA)
    r = atualizar(D(1000), date(2024, 1, 15), date(2024, 3, 20), p, SERIES, pol_banco)
    assert r.percentual_juros == D("0.01") * (D(2) + D(5) / D(30))


def test_termo_inicial_dos_juros_posterior(pol_banco):
    p = ParametrosAtualizacao(correcao=[corr(None)], juros=[juros_fixo(date(2024, 3, 1))],
                              competencias=CONV, acumulacao_juros=Acumulacao.SOMA)
    r = atualizar(D(1000), date(2024, 1, 15), date(2024, 3, 31), p, SERIES, pol_banco)
    assert r.percentual_juros == D("0.01") * D(30) / D(30)


def test_lacuna_nos_criterios(pol_banco):
    p = ParametrosAtualizacao(correcao=[corr("IDX_X", fim=date(2024, 2, 1)), corr(None, ini=date(2024, 2, 10))],
                              juros=[], competencias=CONV, acumulacao_juros=Acumulacao.SOMA)
    with pytest.raises(CriterioInvalido, match="lacuna"):
        atualizar(D(1000), date(2024, 1, 15), date(2024, 3, 20), p, SERIES, pol_banco)


def test_criterio_nao_cobre_periodo(pol_banco):
    p = ParametrosAtualizacao(correcao=[corr("IDX_X", ini=date(2024, 2, 1))], juros=[],
                              competencias=CONV, acumulacao_juros=Acumulacao.SOMA)
    with pytest.raises(CriterioInvalido, match="não cobrem"):
        atualizar(D(1000), date(2024, 1, 15), date(2024, 3, 20), p, SERIES, pol_banco)


def test_indice_ausente_nao_e_estimado(pol_banco):
    p = ParametrosAtualizacao(correcao=[corr("IDX_X")], juros=[], competencias=CONV,
                              acumulacao_juros=Acumulacao.SOMA)
    with pytest.raises(SerieIncompleta, match="2024-05"):
        atualizar(D(1000), date(2024, 1, 15), date(2024, 6, 20), p, SERIES, pol_banco)


@settings(max_examples=40, deadline=None)
@given(st.decimals(min_value="0.01", max_value=10**6, places=2))
def test_propriedade_linearidade(v):
    from cm_calc.motor.numeros import ModoArredondamento, PoliticaArredondamento
    pol = PoliticaArredondamento(casas=20, modo=ModoArredondamento.MEIO_PARA_PAR, arredondar_cada_parcela=False)
    p = ParametrosAtualizacao(correcao=[corr("IDX_X")], juros=[juros_fixo(date(2024, 1, 15))],
                              competencias=CONV, acumulacao_juros=Acumulacao.SOMA)
    r1 = atualizar(v, date(2024, 1, 15), date(2024, 3, 20), p, SERIES, pol)
    r2 = atualizar(2 * v, date(2024, 1, 15), date(2024, 3, 20), p, SERIES, pol)
    assert abs(r2.total - 2 * r1.total) < D("1e-15")
