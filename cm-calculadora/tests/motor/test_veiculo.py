"""Venda do veículo, saldo remanescente, multa DL 911 e perdas e danos. Dados FICTÍCIOS."""

from datetime import date
from decimal import Decimal

import pytest

from cm_calc.motor.atualizacao import (
    Acumulacao, ConvencaoCompetencias, CriterioCorrecao, ParametrosAtualizacao, SerieMensal,
)
from cm_calc.motor.auditoria import FICTICIO, Memoria, Origem, TipoRessalva
from cm_calc.motor.compensacao import Posicao, compensar
from cm_calc.motor.controle import ControleUtilizacao, DuplicidadeError
from cm_calc.motor.datas import competencias_entre
from cm_calc.motor.encargos import Componente, Descaracterizacao
from cm_calc.motor.evolucao import Evento, OrdemImputacao
from cm_calc.motor.numeros import D
from cm_calc.motor.taxas import ConvencaoTempo, Regime, Taxa
from cm_calc.motor.veiculo import (
    ComandoVenda, Deducao, Despesa, MultaDL911, PerdasDanosFipe, VendaVeiculo, apurar_saldo_pos_venda,
    calcular_multa_dl911, calcular_perdas_danos_fipe, posicao_saldo_revisado,
)

SENT = Origem(documento="Sentença FICTÍCIA", localizacao="dispositivo", trecho="comando fictício")
SEM_TRECHO = Origem(documento="Sentença FICTÍCIA")
FIPE = Origem(documento="Tabela FIPE (valor fictício)", localizacao="código 000000-0, ref. 2024-08")
DV = date(2024, 9, 10)                     # data da alienação


def venda(valor, comprovado=True, fipe=None):
    return VendaVeiculo(data_alienacao=DV, valor_venda=D(valor), comprovado=comprovado, origem=FICTICIO,
                        valor_fipe_referencia=D(fipe) if fipe else None, origem_fipe=FIPE if fipe else None)


DESPESAS = [
    Despesa(id="remocao", descricao="Remoção (fictícia)", valor=D(1000), data=DV, comprovada=True, origem=FICTICIO),
    Despesa(id="patio", descricao="Pátio (fictício)", valor=D(500), data=DV, comprovada=True, origem=FICTICIO),
    Despesa(id="leiloeiro", descricao="Comissão sem recibo (fictícia)", valor=D(800), data=DV, comprovada=False, origem=FICTICIO),
]
SALDO = Posicao(id="saldo", descricao="Saldo devedor revisado", valor=D(30000), data_base=DV)
CREDITO = Posicao(id="indebito", descricao="Indébito atualizado", valor=D(3000), data_base=DV)


# --- Venda e saldo remanescente -----------------------------------------------------------

def test_saldo_remanescente_a_cargo_do_consumidor(pol_banco):
    m = Memoria()
    cmd = ComandoVenda(abater_despesas_comprovadas=True, compensar_creditos_consumidor=True, origem_titulo=SENT)
    r = apurar_saldo_pos_venda(SALDO, venda(22000), DESPESAS, [CREDITO], cmd, pol_banco, m)
    # 30.000 + 1.500 (comprovadas) − 22.000 − 3.000 = 6.500
    assert r.saldo_remanescente_consumidor == D(6500) and r.valor_a_restituir_consumidor == 0
    assert r.despesas_consideradas == D(1500) and r.despesas_desconsideradas == D(800)
    assert any("sem comprovação" in x.texto for x in m.ressalvas)


def test_sobra_da_venda_a_restituir(pol_banco):
    cmd = ComandoVenda(abater_despesas_comprovadas=True, compensar_creditos_consumidor=True, origem_titulo=SENT)
    r = apurar_saldo_pos_venda(SALDO, venda(35000), DESPESAS, [CREDITO], cmd, pol_banco, Memoria())
    # 30.000 + 1.500 − 35.000 − 3.000 = −6.500
    assert r.valor_a_restituir_consumidor == D(6500) and r.saldo_remanescente_consumidor == 0


def test_titulo_nao_autoriza_despesas_nem_compensacao(pol_banco):
    m = Memoria()
    cmd = ComandoVenda(abater_despesas_comprovadas=False, compensar_creditos_consumidor=False, origem_titulo=SENT)
    r = apurar_saldo_pos_venda(SALDO, venda(22000), DESPESAS, [CREDITO], cmd, pol_banco, m)
    assert r.saldo_remanescente_consumidor == D(8000)
    assert r.despesas_consideradas == 0 and r.creditos_consumidor == 0
    assert sum(1 for x in m.ressalvas if x.tipo is TipoRessalva.PREMISSA) == 2


def test_venda_nao_comprovada_e_fipe_informativa(pol_banco):
    m = Memoria()
    cmd = ComandoVenda(abater_despesas_comprovadas=False, compensar_creditos_consumidor=False, origem_titulo=SENT)
    apurar_saldo_pos_venda(SALDO, venda(20000, comprovado=False, fipe=40000), [], [], cmd, pol_banco, m)
    assert any("sem comprovação documental" in x.texto for x in m.ressalvas)
    passo = next(p for p in m.passos if "FIPE" in p.descricao)
    assert passo.resultado == "0.5"
    assert not any("vil" in x.texto.lower() for x in m.ressalvas)   # sem juízo automático sobre o preço


def test_posicoes_em_datas_diferentes(pol_banco):
    cmd = ComandoVenda(abater_despesas_comprovadas=False, compensar_creditos_consumidor=True, origem_titulo=SENT)
    cred = Posicao(id="c", descricao="Crédito", valor=D(1), data_base=date(2025, 1, 1))
    with pytest.raises(ValueError, match="data da alienação"):
        apurar_saldo_pos_venda(SALDO, venda(1), [], [cred], cmd, pol_banco, Memoria())


def test_credito_usado_na_venda_nao_volta_na_compensacao(pol_banco):
    ctl, m = ControleUtilizacao(), Memoria()
    cmd = ComandoVenda(abater_despesas_comprovadas=True, compensar_creditos_consumidor=True, origem_titulo=SENT)
    apurar_saldo_pos_venda(SALDO, venda(22000), DESPESAS, [CREDITO], cmd, pol_banco, m, ctl)
    with pytest.raises(DuplicidadeError):
        compensar([CREDITO], [Posicao(id="outro", descricao="x", valor=D(1), data_base=DV)], SENT, m, ctl)


def test_saldo_revisado_na_alienacao_com_pagamentos(pol_banco):
    m = Memoria()
    taxa = Taxa(mensal=D("0.01"), regime=Regime.COMPOSTO, convencao=ConvencaoTempo.MESES_CIVIS)
    pgs = [Evento(data=date(2024, 2, 1), valor=D(500))]
    p = posicao_saldo_revisado(D(1000), date(2024, 1, 1), pgs, taxa, pol_banco, OrdemImputacao.JUROS_PRIMEIRO,
                               date(2024, 4, 1), m, [SENT])
    # 1000 -> juros 10, amortiza 490 -> 510 ; 510 × 1,01² = 520,251 (juros 10,25)
    assert p.valor == D("520.25") and p.data_base == date(2024, 4, 1)
    assert any("após o inadimplemento" in x.texto for x in m.ressalvas)
    with pytest.raises(ValueError, match="posterior à alienação"):
        posicao_saldo_revisado(D(1000), date(2024, 1, 1), [Evento(data=date(2024, 5, 1), valor=D(1))], taxa,
                               pol_banco, OrdemImputacao.JUROS_PRIMEIRO, date(2024, 4, 1), m, [SENT])


# --- Multa DL 911/1969 ------------------------------------------------------------------------

SERIE = {"IDX": SerieMensal(nome="IDX", fonte="fictícia",
                            valores={f"{a:04d}-{m_:02d}": D("0.005") for a, m_ in competencias_entre((2022, 1), (2025, 12))})}
ATUAL = ParametrosAtualizacao(
    correcao=[CriterioCorrecao(inicio=date(2020, 1, 1), fim=date(2030, 1, 1), serie="IDX", origem=SENT)],
    juros=[], competencias=ConvencaoCompetencias(incluir_mes_inicial=True, incluir_mes_final=False),
    acumulacao_juros=Acumulacao.SOMA)


def multa(**kw):
    base = dict(percentual=D("0.50"), valor_base=D(40000), descricao_base="valor financiado do contrato (fictício)",
                data_valor_base=date(2023, 1, 5), improcedencia_busca_apreensao=True, bem_alienado=True,
                origem_titulo=SENT)
    base.update(kw)
    return MultaDL911(**base)


def test_multa_dl911_atualizada(pol_banco):
    m = Memoria()
    v = calcular_multa_dl911(multa(), date(2023, 4, 5), pol_banco, m, ATUAL, SERIE)
    # jan, fev, mar/2023 a 0,5%: 40.000 × 1,005³ = 40.603,005 -> 40.603,01 ; × 50% = 20.301,505 -> 20.301,51
    assert v == D("20301.51")
    assert any("valor originalmente financiado" in x.texto for x in m.ressalvas)


def test_multa_exige_trecho_do_titulo(pol_banco):
    with pytest.raises(ValueError, match="sem trecho"):
        calcular_multa_dl911(multa(origem_titulo=SEM_TRECHO), DV, pol_banco, Memoria())


def test_multa_fora_das_hipoteses_exige_confirmacao(pol_banco):
    with pytest.raises(ValueError, match="confirmação da advogada"):
        calcular_multa_dl911(multa(bem_alienado=False), DV, pol_banco, Memoria())
    m = Memoria()
    calcular_multa_dl911(multa(bem_alienado=False, confirmacao_advogada=Origem(documento="Despacho interno fictício")),
                         DV, pol_banco, m)
    assert any(x.tipo is TipoRessalva.ALERTA for x in m.ressalvas)


def test_multa_percentual_divergente_e_sem_atualizacao(pol_banco):
    m = Memoria()
    v = calcular_multa_dl911(multa(percentual=D("0.30")), DV, pol_banco, m)
    assert v == D("12000.00")
    tipos = {x.tipo for x in m.ressalvas}
    assert TipoRessalva.DIVERGENCIA in tipos and TipoRessalva.PENDENCIA in tipos


# --- Perdas e danos (FIPE) ---------------------------------------------------------------------

def pd(**kw):
    base = dict(valor_fipe=D(45000), mes_referencia_fipe="2024-08", codigo_fipe="000000-0", origem_fipe=FIPE,
                data_base=date(2024, 9, 10), origem_titulo=SENT,
                deducoes=[Deducao(descricao="Saldo devedor revisado (conforme título fictício)", valor=D(30000), origem=SENT)])
    base.update(kw)
    return PerdasDanosFipe(**base)


def test_perdas_danos_fipe_menos_deducoes(pol_banco):
    m = Memoria()
    assert calcular_perdas_danos_fipe(pd(), DV, pol_banco, m) == D("15000.00")
    assert any("não atualizado" in x.texto for x in m.ressalvas)


def test_perdas_danos_atualizadas(pol_banco):
    v = calcular_perdas_danos_fipe(pd(), date(2024, 12, 10), pol_banco, Memoria(), ATUAL, SERIE)
    # set, out, nov/2024: 15.000 × 1,005³ = 15.226,13
    assert v == D("15226.13")


def test_perdas_danos_deducoes_maiores_que_fipe(pol_banco):
    m = Memoria()
    v = calcular_perdas_danos_fipe(pd(deducoes=[Deducao(descricao="x", valor=D(50000), origem=SENT)]), DV, pol_banco, m)
    assert v == 0 and any(x.tipo is TipoRessalva.ALERTA for x in m.ressalvas)


def test_perdas_danos_exigem_titulo(pol_banco):
    with pytest.raises(ValueError, match="sem trecho"):
        calcular_perdas_danos_fipe(pd(origem_titulo=SEM_TRECHO), DV, pol_banco, Memoria())


def test_cumulacao_multa_e_perdas_gera_ressalva(pol_banco):
    m = Memoria()
    calcular_multa_dl911(multa(), DV, pol_banco, m)
    calcular_perdas_danos_fipe(pd(), DV, pol_banco, m)
    assert any("cumulativamente" in x.texto for x in m.ressalvas)


def test_descaracterizacao_da_mora_nao_gera_indenizacao_nem_multa(pol_banco):
    """Mesmo com descaracterização da mora no título, sem comando expresso não há multa nem perdas e danos."""
    Descaracterizacao(componentes_afastados=frozenset({Componente.MULTA}), origem_titulo=SENT)
    with pytest.raises(ValueError):
        calcular_multa_dl911(multa(origem_titulo=SEM_TRECHO), DV, pol_banco, Memoria())
    with pytest.raises(ValueError):
        calcular_perdas_danos_fipe(pd(origem_titulo=SEM_TRECHO), DV, pol_banco, Memoria())
