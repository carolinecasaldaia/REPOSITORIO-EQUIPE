"""Descaracterização da mora, encargos, repetição do indébito, compensação, honorários, verbas."""

from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cm_calc.motor.auditoria import Origem, TipoRessalva
from cm_calc.motor.compensacao import Posicao, compensar
from cm_calc.motor.encargos import (
    Componente, ContagemAtraso, Descaracterizacao, ParametrosEncargos,
    calcular_encargos, ressalvas_descaracterizacao,
)
from cm_calc.motor.honorarios import BaseHonorarios, ParametrosHonorarios, calcular_honorarios
from cm_calc.motor.indebito import Modalidade, RegraRestituicao, valor_a_restituir
from cm_calc.motor.numeros import D
from cm_calc.motor.verbas import VerbaAutorizada, calcular_verba

TITULO = Origem(documento="Acórdão fictício", localizacao="item 3", trecho="texto fictício")
CONTRATO = Origem(documento="Contrato fictício", localizacao="cláusula 9")


def enc(**kw):
    base = dict(multa=D("0.02"), juros_mora_mensal=D("0.01"), juros_remuneratorios_mora_mensal=D("0.02"),
                remuneratorios_compostos=True, contagem=ContagemAtraso.DIAS_30, origem=CONTRATO)
    base.update(kw)
    return ParametrosEncargos(**base)


VENC, PAG = date(2024, 3, 10), date(2024, 4, 9)       # 30 dias de atraso


# --- Encargos e descaracterização da mora ----------------------------------------

def test_encargos_contratuais(pol_banco, memoria):
    r = calcular_encargos(D(1000), VENC, PAG, enc(), pol_banco, memoria=memoria)
    assert r == {Componente.MULTA: D("20.00"), Componente.JUROS_MORA: D("10.00"),
                 Componente.JUROS_REMUNERATORIOS_MORA: D("20.00")}


def test_pagamento_em_dia_sem_encargos(pol_banco):
    assert calcular_encargos(D(1000), VENC, VENC, enc(), pol_banco) == {}


def test_descaracterizacao_afasta_somente_o_que_o_titulo_listou(pol_banco, memoria):
    desc = Descaracterizacao(componentes_afastados=frozenset({Componente.MULTA, Componente.JUROS_MORA}),
                             origem_titulo=TITULO)
    r = calcular_encargos(D(1000), VENC, PAG, enc(), pol_banco, desc, memoria)
    assert r[Componente.MULTA] == 0 and r[Componente.JUROS_MORA] == 0
    assert r[Componente.JUROS_REMUNERATORIOS_MORA] == D("20.00")     # não afastado: continua devido


def test_descaracterizacao_respeita_periodo(pol_banco):
    desc = Descaracterizacao(componentes_afastados=frozenset({Componente.MULTA}),
                             ate=date(2024, 1, 31), origem_titulo=TITULO)
    r = calcular_encargos(D(1000), VENC, PAG, enc(), pol_banco, desc)
    assert r[Componente.MULTA] == D("20.00")                          # vencimento fora do período


def test_descaracterizacao_nao_gera_verbas_automaticas(memoria):
    desc = Descaracterizacao(componentes_afastados=frozenset({Componente.MULTA}), origem_titulo=TITULO)
    ressalvas_descaracterizacao(desc, memoria)
    textos = " ".join(r.texto for r in memoria.ressalvas)
    assert "NÃO decorrem automaticamente" in textos
    assert any(r.tipo is TipoRessalva.PENDENCIA for r in memoria.ressalvas)   # sem termo final


def test_remuneratorios_na_mora_exigem_regime():
    with pytest.raises(ValueError):
        enc(remuneratorios_compostos=None)


def test_alerta_cumulacao_comissao_permanencia(pol_banco, memoria):
    calcular_encargos(D(1000), VENC, PAG, enc(comissao_permanencia_mensal=D("0.03")), pol_banco, memoria=memoria)
    assert any("comissão de permanência" in r.texto for r in memoria.ressalvas)


# --- Repetição do indébito ---------------------------------------------------------

def test_simples_e_dobro(memoria):
    s = RegraRestituicao(modalidade=Modalidade.SIMPLES, origem_titulo=TITULO)
    d = RegraRestituicao(modalidade=Modalidade.DOBRO, origem_titulo=TITULO)
    assert valor_a_restituir(D("150.37"), date(2023, 5, 1), s, memoria) == D("150.37")
    assert valor_a_restituir(D("150.37"), date(2023, 5, 1), d, memoria) == D("300.74")
    assert all(p.origem for p in memoria.da_etapa("restituicao"))


def test_dobro_a_partir_de_data_de_corte():
    r = RegraRestituicao(modalidade=Modalidade.DOBRO_A_PARTIR_DE, data_corte=date(2023, 6, 1), origem_titulo=TITULO)
    assert valor_a_restituir(D(100), date(2023, 5, 31), r) == D(100)
    assert valor_a_restituir(D(100), date(2023, 6, 1), r) == D(200)


def test_regras_invalidas():
    with pytest.raises(ValueError):
        RegraRestituicao(modalidade=Modalidade.DOBRO_A_PARTIR_DE, origem_titulo=TITULO)
    with pytest.raises(ValueError):
        RegraRestituicao(modalidade=Modalidade.SIMPLES, data_corte=date(2023, 1, 1), origem_titulo=TITULO)
    with pytest.raises(ValueError):
        valor_a_restituir(D(-1), date(2023, 1, 1), RegraRestituicao(modalidade=Modalidade.SIMPLES, origem_titulo=TITULO))


@given(st.decimals(min_value=0, max_value=10**7, places=2))
def test_propriedade_dobro_e_o_dobro_do_simples(v):
    s = RegraRestituicao(modalidade=Modalidade.SIMPLES, origem_titulo=TITULO)
    d = RegraRestituicao(modalidade=Modalidade.DOBRO, origem_titulo=TITULO)
    assert valor_a_restituir(v, date(2024, 1, 1), d) == 2 * valor_a_restituir(v, date(2024, 1, 1), s)


# --- Compensação ----------------------------------------------------------------------

def test_compensacao_a_favor_do_consumidor(memoria):
    db = date(2025, 3, 10)
    r = compensar([Posicao(descricao="Indébito atualizado", valor=D("5000.00"), data_base=db)],
                  [Posicao(descricao="Saldo revisado", valor=D("3000.00"), data_base=db)], TITULO, memoria)
    assert (r.saldo_a_favor_consumidor, r.saldo_a_favor_credor) == (D(2000), D(0))


def test_compensacao_a_favor_do_credor(memoria):
    db = date(2025, 3, 10)
    r = compensar([Posicao(descricao="c", valor=D(1000), data_base=db)],
                  [Posicao(descricao="d", valor=D(2500), data_base=db)], TITULO, memoria)
    assert (r.saldo_a_favor_consumidor, r.saldo_a_favor_credor) == (D(0), D(1500))


def test_compensacao_exige_mesma_data(memoria):
    with pytest.raises(ValueError, match="mesma data-base"):
        compensar([Posicao(descricao="c", valor=D(1), data_base=date(2025, 1, 1))],
                  [Posicao(descricao="d", valor=D(1), data_base=date(2025, 2, 1))], TITULO, memoria)


# --- Honorários ------------------------------------------------------------------------

def test_honorarios_percentual_e_sucumbencia_reciproca(pol_banco, memoria):
    p = ParametrosHonorarios(base=BaseHonorarios.CONDENACAO, percentual=D("0.10"), cota_devedor=D("0.70"),
                             devedor="réu (fictício)", origem_titulo=TITULO)
    assert calcular_honorarios(p, D("20000.00"), pol_banco, memoria) == D("1400.00")


def test_honorarios_valor_fixo(pol_banco, memoria):
    p = ParametrosHonorarios(base=BaseHonorarios.VALOR_FIXO, valor_fixo=D(3000), devedor="réu",
                             origem_titulo=TITULO)
    assert calcular_honorarios(p, None, pol_banco, memoria) == D("3000.00")


def test_honorarios_validacoes(pol_banco, memoria):
    with pytest.raises(ValueError):
        ParametrosHonorarios(base=BaseHonorarios.CONDENACAO, devedor="réu", origem_titulo=TITULO)
    with pytest.raises(ValueError):
        ParametrosHonorarios(base=BaseHonorarios.VALOR_FIXO, valor_fixo=D(1), percentual=D("0.1"),
                             devedor="réu", origem_titulo=TITULO)
    p = ParametrosHonorarios(base=BaseHonorarios.PROVEITO_ECONOMICO, percentual=D("0.1"), devedor="réu",
                             origem_titulo=TITULO)
    with pytest.raises(ValueError, match="valor da base"):
        calcular_honorarios(p, None, pol_banco, memoria)


# --- Verbas adicionais ---------------------------------------------------------------

def test_verba_sem_trecho_do_titulo_e_recusada():
    with pytest.raises(ValueError, match="sem trecho"):
        VerbaAutorizada(descricao="Perdas e danos", data_base=date(2024, 1, 1), valor_fixo=D(1000),
                        origem_titulo=Origem(documento="Sentença"))


def test_verba_autorizada(pol_banco, memoria):
    v = VerbaAutorizada(descricao="Multa fixada no título (fictícia)", data_base=date(2024, 1, 1),
                        percentual=D("0.5"), valor_base=D("18000"), descricao_base="valor fictício",
                        origem_titulo=TITULO)
    assert calcular_verba(v, pol_banco, memoria) == D("9000.00")
