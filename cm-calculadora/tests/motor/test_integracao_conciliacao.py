"""Caso FICTÍCIO completo: AP01 -> AP02 -> AP03 -> restituição -> compensação -> honorários.

Nenhum dado real. Verifica identidades de conciliação, trilha de auditoria,
ressalvas obrigatórias e determinismo (mesma entrada => mesma saída).
"""

from datetime import date, timedelta
from decimal import Decimal

from cm_calc.motor.atualizacao import (
    Acumulacao, ContagemJuros, ConvencaoCompetencias, CriterioCorrecao, CriterioJuros,
    ParametrosAtualizacao, SerieMensal, TipoJuros,
)
from cm_calc.motor.auditoria import FICTICIO, Memoria, Origem, TipoRessalva
from cm_calc.motor.compensacao import Posicao, compensar
from cm_calc.motor.datas import competencias_entre, vencimentos_mensais
from cm_calc.motor.diferencas import PagamentoEfetivo, demonstrativo_diferencas
from cm_calc.motor.encargos import (
    Componente, ContagemAtraso, Descaracterizacao, ParametrosEncargos, calcular_encargos,
    ressalvas_descaracterizacao,
)
from cm_calc.motor.evolucao import Evento, OrdemImputacao, evoluir_saldo, tabela_contratual
from cm_calc.motor.financiamento import ParcelaPrevista, calcular_parcela_regular
from cm_calc.motor.honorarios import BaseHonorarios, ParametrosHonorarios, calcular_honorarios
from cm_calc.motor.indebito import Modalidade, RegraRestituicao
from cm_calc.motor.numeros import ZERO, D, ModoArredondamento, PoliticaArredondamento, arredondar
from cm_calc.motor.revisao import ItemExcluido, ParametrosRevisao, recalcular_contrato
from cm_calc.motor.taxas import ConvencaoTempo, Regime, Taxa

POL = PoliticaArredondamento(casas=2, modo=ModoArredondamento.MEIO_PARA_CIMA, arredondar_cada_parcela=True)
SENT = Origem(documento="Sentença FICTÍCIA", localizacao="dispositivo", trecho="comando fictício para teste")
CONTRATO = Origem(documento="Contrato FICTÍCIO", localizacao="cláusulas 3 e 9")

LIB = date(2023, 1, 5)
VF = D(40000)                       # inclui tarifa 1.200 e seguro 800 financiados
DATA_BASE = date(2025, 3, 10)
CORTE_DOBRO = date(2023, 6, 1)


def executar_caso():
    mem = Memoria()
    parcelas = [ParcelaPrevista(numero=k + 1, vencimento=d)
                for k, d in enumerate(vencimentos_mensais(date(2023, 2, 5), 24))]
    taxa_orig = Taxa(mensal=D("0.022"), regime=Regime.COMPOSTO, convencao=ConvencaoTempo.MESES_CIVIS)
    taxa_rev = Taxa(mensal=D("0.016"), regime=Regime.COMPOSTO, convencao=ConvencaoTempo.MESES_CIVIS)

    # AP01 — evolução original
    p_orig = calcular_parcela_regular(VF, LIB, parcelas, taxa_orig, POL, mem, [CONTRATO], "AP01").parcela_regular
    ap01 = tabela_contratual(VF, LIB, parcelas, p_orig, taxa_orig, POL, mem, "AP01", [CONTRATO])

    # AP02 — evolução revisada
    rev = recalcular_contrato(
        VF, LIB, parcelas, p_orig,
        ParametrosRevisao(
            taxa_revisada=taxa_rev, origem_taxa=SENT,
            itens_excluidos=[
                ItemExcluido(descricao="Tarifa fictícia", valor=D(1200), financiado=True, origem_titulo=SENT),
                ItemExcluido(descricao="Seguro fictício", valor=D(800), financiado=True, origem_titulo=SENT),
            ]),
        POL, mem)
    ap02 = tabela_contratual(rev.valor_financiado_revisado, LIB, parcelas, rev.parcela_regular_revisada,
                             taxa_rev, POL, mem, "AP02-tabela", [SENT])

    # Pagamentos efetivos fictícios: parcelas 1..10; 4 e 7 pagas com atraso e encargos cobrados
    enc_contrato = ParametrosEncargos(multa=D("0.02"), juros_mora_mensal=D("0.01"),
                                      juros_remuneratorios_mora_mensal=D("0.022"), remuneratorios_compostos=True,
                                      contagem=ContagemAtraso.DIAS_30, origem=CONTRATO)
    atrasos = {4: 20, 7: 40}
    pagamentos = []
    for p in parcelas[:10]:
        dp = p.vencimento + timedelta(days=atrasos.get(p.numero, 0))
        enc_pagos = sum(calcular_encargos(p_orig, p.vencimento, dp, enc_contrato, POL).values(), ZERO)
        pagamentos.append(PagamentoEfetivo(numero_parcela=p.numero, vencimento=p.vencimento, data_pagamento=dp,
                                           valor_parcela_pago=p_orig, encargos_pagos=enc_pagos, origem=FICTICIO))

    desc = Descaracterizacao(componentes_afastados=frozenset({Componente.MULTA, Componente.JUROS_MORA}),
                             origem_titulo=SENT)
    ressalvas_descaracterizacao(desc, mem)
    enc_revisados = ParametrosEncargos(multa=D("0.02"), juros_mora_mensal=D("0.01"),
                                       juros_remuneratorios_mora_mensal=D("0.016"), remuneratorios_compostos=True,
                                       contagem=ContagemAtraso.DIAS_30, origem=SENT)

    serie = SerieMensal(nome="IDX_FICT", fonte="fictícia",
                        valores={f"{a:04d}-{m:02d}": D("0.004") for a, m in competencias_entre((2023, 1), (2025, 12))})
    atual = ParametrosAtualizacao(
        correcao=[CriterioCorrecao(inicio=date(2020, 1, 1), fim=date(2030, 1, 1), serie="IDX_FICT", origem=SENT)],
        juros=[CriterioJuros(inicio=date(2024, 3, 1), fim=date(2030, 1, 1), tipo=TipoJuros.PERCENTUAL_FIXO,
                             percentual_mensal=D("0.01"), contagem=ContagemJuros.DIAS_30, origem=SENT)],
        competencias=ConvencaoCompetencias(incluir_mes_inicial=True, incluir_mes_final=False),
        acumulacao_juros=Acumulacao.SOMA,
    )
    regra = RegraRestituicao(modalidade=Modalidade.DOBRO_A_PARTIR_DE, data_corte=CORTE_DOBRO, origem_titulo=SENT)
    avulso = ItemExcluido(descricao="Tarifa fictícia paga à vista", valor=D(400), financiado=False,
                          data_pagamento=LIB, origem_titulo=SENT)

    # AP03 — diferenças, restituição e atualização
    ap03 = demonstrativo_diferencas(pagamentos, rev, regra, atual, {"IDX_FICT": serie}, DATA_BASE, POL, mem,
                                    enc_revisados, desc, [avulso])

    # Saldo devedor revisado na data-base (pagamentos considerados pelo valor revisado devido)
    eventos = [Evento(data=pg.data_pagamento, valor=rev.parcelas_revisadas[pg.numero_parcela],
                      numero_parcela=pg.numero_parcela) for pg in pagamentos]
    saldo = evoluir_saldo(rev.valor_financiado_revisado, LIB, eventos, taxa_rev, POL,
                          OrdemImputacao.JUROS_PRIMEIRO, mem, "saldo_revisado", [SENT], DATA_BASE)

    comp = compensar([Posicao(descricao="Indébito atualizado (AP03)", valor=ap03.total_atualizado, data_base=DATA_BASE)],
                     [Posicao(descricao="Saldo devedor revisado", valor=arredondar(saldo.saldo_final, POL),
                              data_base=DATA_BASE)], SENT, mem)
    hon = calcular_honorarios(
        ParametrosHonorarios(base=BaseHonorarios.CONDENACAO, percentual=D("0.10"), devedor="réu fictício",
                             origem_titulo=SENT),
        ap03.total_atualizado, POL, mem, "total do AP03 (premissa do teste)")
    return dict(mem=mem, p_orig=p_orig, ap01=ap01, rev=rev, ap02=ap02, ap03=ap03, saldo=saldo, comp=comp, hon=hon)


def test_conciliacao_ap01_ap02():
    r = executar_caso()
    assert r["ap01"].conciliacao(VF) == {"pagamentos": 0, "saldo": 0}
    assert r["ap02"].conciliacao(r["rev"].valor_financiado_revisado) == {"pagamentos": 0, "saldo": 0}
    for ap in (r["ap01"], r["ap02"]):
        assert abs(ap.saldo_final - ap.total_excedente) < D("0.10")      # só resíduo de arredondamento
    assert r["rev"].valor_financiado_revisado == D(38000)
    assert r["rev"].parcela_regular_revisada < r["p_orig"]


def test_conciliacao_ap03():
    ap03 = executar_caso()["ap03"]
    soma_dif = sum((l.diferenca for l in ap03.linhas), ZERO) + sum((l.diferenca for l in ap03.pagos_a_menor), ZERO)
    assert ap03.total_pago - ap03.total_devido == soma_dif
    for l in ap03.linhas:
        mult = D(2) if l.data_pagamento >= CORTE_DOBRO else D(1)
        assert l.a_restituir == l.diferenca * mult
        assert l.atualizado == l.corrigido + l.juros
        assert l.atualizado >= l.a_restituir                      # série fictícia só positiva
    assert ap03.total_atualizado == sum((l.atualizado for l in ap03.linhas), ZERO)
    assert len(ap03.linhas) == 11                                  # 10 parcelas + 1 tarifa avulsa
    antes = [l for l in ap03.linhas if l.data_pagamento < CORTE_DOBRO]
    assert antes and all(l.a_restituir == l.diferenca for l in antes)


def test_encargos_afastados_entram_no_indebito():
    r = executar_caso()
    ap03 = r["ap03"]
    p4 = next(l for l in ap03.linhas if l.descricao == "Parcela 4")
    p3 = next(l for l in ap03.linhas if l.descricao == "Parcela 3")
    # Parcela 4 (atrasada) tem diferença maior que a 3 (em dia): multa e juros de mora afastados
    assert p4.diferenca > p3.diferenca


def test_compensacao_e_honorarios():
    r = executar_caso()
    c = r["comp"]
    assert c.saldo_a_favor_consumidor - c.saldo_a_favor_credor == c.credito_consumidor - c.saldo_devedor
    assert r["hon"] == arredondar(r["ap03"].total_atualizado * D("0.10"), POL)


def test_trilha_de_auditoria_e_ressalvas():
    mem = executar_caso()["mem"]
    etapas = {p.etapa for p in mem.passos}
    for e in ("AP01", "AP02", "AP03", "AP03-encargos", "restituicao", "atualizacao",
              "saldo_revisado", "compensacao", "honorarios"):
        assert e in etapas, e
    for p in mem.passos:
        assert p.formula and p.origem, f"passo sem fórmula/origem: {p.etapa} {p.descricao}"
    tipos = {(r.tipo, r.texto.split(":")[0]) for r in mem.ressalvas}
    textos = " ".join(r.texto for r in mem.ressalvas)
    assert "IOF" in textos                                         # IOF reflexo pendente
    assert "NÃO decorrem automaticamente" in textos                # limites da descaracterização
    assert any(t is TipoRessalva.PENDENCIA for t, _ in tipos)


def test_determinismo():
    a, b = executar_caso(), executar_caso()
    assert a["ap03"].model_dump() == b["ap03"].model_dump()
    assert a["mem"].model_dump() == b["mem"].model_dump()
