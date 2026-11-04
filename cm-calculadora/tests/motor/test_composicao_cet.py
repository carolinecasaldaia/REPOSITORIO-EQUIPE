"""Composição do financiamento, exclusões sem duplicidade e CET. Dados FICTÍCIOS."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cm_calc.motor.auditoria import FICTICIO, Memoria, Origem, TipoRessalva
from cm_calc.motor.compensacao import Posicao, compensar
from cm_calc.motor.composicao import (
    Composicao, Exclusao, FormaPagamento, ItemCusto, TipoItem, aplicar_exclusoes, calcular_cet, fluxo_cet,
)
from cm_calc.motor.controle import ControleUtilizacao, DuplicidadeError
from cm_calc.motor.datas import vencimentos_mensais
from cm_calc.motor.diferencas import demonstrativo_diferencas
from cm_calc.motor.financiamento import ParcelaPrevista, calcular_parcela_regular
from cm_calc.motor.numeros import D
from cm_calc.motor.revisao import ParametrosRevisao, recalcular_contrato
from cm_calc.motor.taxas import ConvencaoTempo, Regime, Taxa, mensal_para_anual

SENT = Origem(documento="Sentença FICTÍCIA", localizacao="dispositivo", trecho="comando fictício")
LIB = date(2023, 1, 5)


def comp(declarado=None, cet=None):
    return Composicao(
        data_liberacao=LIB, valor_liberado=D(36000), origem=FICTICIO,
        valor_financiado_declarado=declarado, cet_anual_declarado=cet,
        itens=[
            ItemCusto(id="iof", tipo=TipoItem.IOF, descricao="IOF", valor=D(1100), forma=FormaPagamento.FINANCIADO, origem=FICTICIO),
            ItemCusto(id="tc", tipo=TipoItem.TARIFA, descricao="Tarifa de cadastro (fictícia)", valor=D(900),
                      forma=FormaPagamento.FINANCIADO, origem=FICTICIO),
            ItemCusto(id="seg", tipo=TipoItem.SEGURO, descricao="Seguro prestamista (fictício)", valor=D(1500),
                      forma=FormaPagamento.FINANCIADO, origem=FICTICIO),
            ItemCusto(id="reg", tipo=TipoItem.TARIFA, descricao="Registro (fictício)", valor=D(500),
                      forma=FormaPagamento.FINANCIADO, origem=FICTICIO),
            ItemCusto(id="aval", tipo=TipoItem.TARIFA, descricao="Avaliação do bem (fictícia)", valor=D(450),
                      forma=FormaPagamento.A_VISTA, data_pagamento=LIB, origem=FICTICIO),
        ],
    )


# --- Composição -------------------------------------------------------------------------

def test_separacao_dos_componentes():
    c = comp()
    assert c.valor_financiado == D(40000)
    assert c.total_financiado_itens == D(4000)
    assert c.total_a_vista == D(450)


def test_divergencia_com_valor_declarado():
    m = Memoria()
    comp(declarado=D(40250)).conferir(m)
    assert any(r.tipo is TipoRessalva.DIVERGENCIA and "250" in r.texto for r in m.ressalvas)
    m2 = Memoria()
    comp(declarado=D(40000)).conferir(m2)
    assert not m2.ressalvas


def test_validacoes_da_composicao():
    with pytest.raises(ValueError, match="data de pagamento"):
        ItemCusto(id="x", tipo=TipoItem.TARIFA, descricao="x", valor=D(1), forma=FormaPagamento.A_VISTA, origem=FICTICIO)
    with pytest.raises(ValueError, match="repetidos"):
        Composicao(data_liberacao=LIB, valor_liberado=D(1), origem=FICTICIO, itens=[
            ItemCusto(id="a", tipo=TipoItem.IOF, descricao="a", valor=D(1), forma=FormaPagamento.FINANCIADO, origem=FICTICIO),
            ItemCusto(id="a", tipo=TipoItem.IOF, descricao="b", valor=D(1), forma=FormaPagamento.FINANCIADO, origem=FICTICIO)])


# --- Exclusões sem duplicidade --------------------------------------------------------

def test_exclusao_distingue_financiado_e_a_vista():
    m, ctl = Memoria(), ControleUtilizacao()
    r = aplicar_exclusoes(comp(), [Exclusao(id_item="tc", origem_titulo=SENT),
                                   Exclusao(id_item="seg", origem_titulo=SENT),
                                   Exclusao(id_item="aval", origem_titulo=SENT)], ctl, m)
    assert r.valor_financiado_revisado == D(37600)
    assert [i.descricao for i in r.excluidos_financiados] == ["Tarifa de cadastro (fictícia)", "Seguro prestamista (fictício)"]
    assert len(r.indebitos_a_vista) == 1 and r.indebitos_a_vista[0].data_pagamento == LIB
    assert any("IOF" in x.texto and x.tipo is TipoRessalva.PENDENCIA for x in m.ressalvas)
    assert any("NÃO são lançados de novo" in x.texto for x in m.ressalvas)


def test_exclusao_duplicada_e_recusada():
    with pytest.raises(DuplicidadeError):
        aplicar_exclusoes(comp(), [Exclusao(id_item="tc", origem_titulo=SENT),
                                   Exclusao(id_item="tc", origem_titulo=SENT)], ControleUtilizacao(), Memoria())


def test_exclusao_de_item_inexistente():
    with pytest.raises(KeyError):
        aplicar_exclusoes(comp(), [Exclusao(id_item="nao_existe", origem_titulo=SENT)], ControleUtilizacao(), Memoria())


def test_credito_nao_compensado_duas_vezes():
    ctl, m, d = ControleUtilizacao(), Memoria(), date(2025, 1, 1)
    cred = Posicao(id="indebito_ap03", descricao="Indébito", valor=D(100), data_base=d)
    compensar([cred], [Posicao(id="saldo", descricao="Saldo", valor=D(50), data_base=d)], SENT, m, ctl)
    with pytest.raises(DuplicidadeError):
        compensar([cred], [Posicao(id="saldo2", descricao="Saldo", valor=D(50), data_base=d)], SENT, m, ctl)


def test_recalculo_sem_duplicar(pol_banco):
    """Fluxo completo: excluídos financiados só no AP02; à vista só no AP03."""
    m, ctl = Memoria(), ControleUtilizacao()
    c = comp()
    r = aplicar_exclusoes(c, [Exclusao(id_item="tc", origem_titulo=SENT),
                              Exclusao(id_item="aval", origem_titulo=SENT)], ctl, m)
    parcelas = [ParcelaPrevista(numero=k + 1, vencimento=v) for k, v in enumerate(vencimentos_mensais(date(2023, 2, 5), 24))]
    taxa = Taxa(mensal=D("0.02"), regime=Regime.COMPOSTO, convencao=ConvencaoTempo.MESES_CIVIS)
    p_orig = calcular_parcela_regular(c.valor_financiado, LIB, parcelas, taxa, pol_banco).parcela_regular
    rev = recalcular_contrato(c.valor_financiado, LIB, parcelas, p_orig,
                              ParametrosRevisao(taxa_revisada=taxa, origem_taxa=SENT,
                                                itens_excluidos=r.excluidos_financiados), pol_banco, m)
    assert rev.valor_financiado_revisado == r.valor_financiado_revisado == D(39100)
    # a mesma taxa: a parcela cai exatamente pelo efeito da tarifa financiada (900 × coeficiente)
    from cm_calc.motor.financiamento import coeficiente_price
    assert abs((p_orig - rev.parcela_regular_revisada) - D(900) * coeficiente_price(D("0.02"), 24)) <= D("0.01")
    # item financiado não é aceito como avulso no AP03 (seria a dupla devolução)
    from cm_calc.motor.atualizacao import Acumulacao, ConvencaoCompetencias, CriterioCorrecao, ParametrosAtualizacao
    from cm_calc.motor.indebito import Modalidade, RegraRestituicao
    atual = ParametrosAtualizacao(correcao=[CriterioCorrecao(inicio=date(2020, 1, 1), fim=date(2030, 1, 1), serie=None, origem=SENT)],
                                  juros=[], competencias=ConvencaoCompetencias(incluir_mes_inicial=True, incluir_mes_final=False),
                                  acumulacao_juros=Acumulacao.SOMA)
    regra = RegraRestituicao(modalidade=Modalidade.SIMPLES, origem_titulo=SENT)
    with pytest.raises(ValueError, match="AP02"):
        demonstrativo_diferencas([], rev, regra, atual, {}, date(2025, 1, 1), pol_banco, m,
                                 itens_avulsos=r.excluidos_financiados)
    ap03 = demonstrativo_diferencas([], rev, regra, atual, {}, date(2025, 1, 1), pol_banco, m,
                                    itens_avulsos=r.indebitos_a_vista)
    assert ap03.total_a_restituir_nominal == D(450)


# --- CET -------------------------------------------------------------------------------------

def test_cet_pagamento_unico_um_ano():
    r = calcular_cet(date(2023, 1, 1), D(1000), [(date(2024, 1, 1), D(1100))])   # 365 dias
    assert abs(r.anual - D("0.10")) < D("1e-20")


def test_cet_dois_anos():
    r = calcular_cet(date(2023, 1, 1), D(1000), [(date(2023, 1, 1) + timedelta(days=730), D(1210))])
    assert abs(r.anual - D("0.10")) < D("1e-20")


def test_cet_sem_custos_igual_taxa_de_contrato_diario_365(pol_exata):
    """Contrato com capitalização diária base 365 e sem custos: CET = taxa anual do contrato."""
    taxa = Taxa(mensal=D(0), anual=D("0.28"), regime=Regime.COMPOSTO, convencao=ConvencaoTempo.DIAS_BASE_365)
    parcelas = [ParcelaPrevista(numero=k + 1, vencimento=v) for k, v in enumerate(vencimentos_mensais(date(2023, 2, 5), 36))]
    pmt = calcular_parcela_regular(D(30000), LIB, parcelas, taxa, pol_exata).parcela_regular_exata
    r = calcular_cet(LIB, D(30000), [(p.vencimento, pmt) for p in parcelas])
    assert abs(r.anual - D("0.28")) < D("1e-18")


def test_cet_com_custos_supera_taxa_nominal(pol_banco):
    m = Memoria()
    c = comp(cet=D("0.40"))
    taxa = Taxa(mensal=D("0.02"), regime=Regime.COMPOSTO, convencao=ConvencaoTempo.MESES_CIVIS)
    parcelas = [ParcelaPrevista(numero=k + 1, vencimento=v) for k, v in enumerate(vencimentos_mensais(date(2023, 2, 5), 24))]
    pmt = calcular_parcela_regular(c.valor_financiado, LIB, parcelas, taxa, pol_banco).parcela_regular
    fc0, fluxos = fluxo_cet(c, [(p.vencimento, pmt) for p in parcelas])
    assert fc0 == D(36000) - D(450)                      # à vista no ato reduz o FC0
    r = calcular_cet(LIB, fc0, fluxos, m, cet_declarado=c.cet_anual_declarado)
    assert r.anual > mensal_para_anual(D("0.02"), Regime.COMPOSTO)
    assert abs(r.residuo) < D("1e-15")
    assert any(x.tipo is TipoRessalva.DIVERGENCIA and "CET" in x.texto for x in m.ressalvas)


def test_cet_revisado_menor_que_original(pol_banco):
    c = comp()
    parcelas = [ParcelaPrevista(numero=k + 1, vencimento=v) for k, v in enumerate(vencimentos_mensais(date(2023, 2, 5), 24))]
    t_orig = Taxa(mensal=D("0.025"), regime=Regime.COMPOSTO, convencao=ConvencaoTempo.MESES_CIVIS)
    t_rev = Taxa(mensal=D("0.018"), regime=Regime.COMPOSTO, convencao=ConvencaoTempo.MESES_CIVIS)
    p1 = calcular_parcela_regular(c.valor_financiado, LIB, parcelas, t_orig, pol_banco).parcela_regular
    p2 = calcular_parcela_regular(c.valor_financiado - D(2400), LIB, parcelas, t_rev, pol_banco).parcela_regular
    fc0, f1 = fluxo_cet(c, [(p.vencimento, p1) for p in parcelas])
    cet1 = calcular_cet(LIB, fc0, f1).anual
    cet2 = calcular_cet(LIB, fc0, [(p.vencimento, p2) for p in parcelas]).anual
    assert cet2 < cet1


def test_cet_dados_invalidos():
    with pytest.raises(ValueError):
        calcular_cet(LIB, D(0), [(date(2024, 1, 1), D(1))])
    with pytest.raises(ValueError, match="menores"):
        calcular_cet(LIB, D(1000), [(date(2024, 1, 1), D(900))])


@settings(max_examples=25, deadline=None)
@given(st.decimals(min_value="0.01", max_value="2.0", places=4), st.integers(30, 1500))
def test_propriedade_cet_pagamento_unico(taxa, dias):
    pv = D(1000)
    fv = pv * (1 + taxa) ** (D(dias) / D(365))
    r = calcular_cet(LIB, pv, [(LIB + timedelta(days=dias), fv)])
    assert abs(r.anual - taxa) < D("1e-15")
