"""Camada de serviço: pendências do cálculo, execução dos três tipos e registro. Dados FICTÍCIOS."""

from datetime import date
from decimal import Decimal

import pytest

from cm_calc.extracao.adaptador import QuadroBloqueado
from cm_calc.extracao.quadro import montar_quadro
from cm_calc.motor.atualizacao import Acumulacao, ContagemJuros
from cm_calc.motor.encargos import ContagemAtraso
from cm_calc.servicos import demonstrativos as dm
from cm_calc.servicos import liquidacao as lq
from cm_calc.servicos.indices import carregar_series, lacunas, salvar_serie, serie_de_csv
from tests.extracao.conftest import ler
from tests.extracao.test_quadro_aprovacao import aprovar_tudo
from tests.fixtures.documentos_ficticios import gerar_caso_completo

CSV = "competencia;variacao\n" + "\n".join(f"{a}-{m:02d};0,40" for a in (2023, 2024, 2025) for m in range(1, 13))


@pytest.fixture(autouse=True)
def dados(tmp_path, monkeypatch):
    monkeypatch.setenv("CM_CALC_DADOS", str(tmp_path / "dados"))


@pytest.fixture
def q_aprovado(tmp_path):
    docs, av = ler(gerar_caso_completo(tmp_path / "docs").values())
    q = montar_quadro("FICT-010", docs, av)
    aprovar_tudo(q)
    return q


@pytest.fixture
def series():
    return {"IDX_FICT": serie_de_csv("IDX_FICT", CSV.encode(), "série fictícia de teste")}


def criterios(**kw):
    base = dict(serie_correcao="IDX_FICT", incluir_mes_inicial=True, incluir_mes_final=False,
                juros_taxa_mensal=Decimal("0.01"), juros_inicio=date(2024, 4, 15), juros_contagem=ContagemJuros.DIAS_30,
                acumulacao=Acumulacao.SOMA, contagem_atraso=ContagemAtraso.DIAS_30,
                justificativa="título fictício: INPC desde cada desembolso; 1% a.m. desde a citação")
    base.update(kw)
    return lq.CriteriosAtualizacao(**base)


def op(tipo=lq.TipoCalculo.LIQUIDACAO, **kw):
    base = dict(tipo=tipo, data_base=date(2025, 3, 10), responsavel="Advogada (teste)", criterios=criterios())
    base.update(kw)
    return lq.OpcoesCalculo(**base)


# --- Séries de índices -------------------------------------------------------------------

def test_serie_csv_e_persistencia():
    s = serie_de_csv("INPC_FICT", b"competencia;variacao\n01/2024;0,42\n2024-02;-0,10\n", "fonte fictícia")
    assert s.valores == {"2024-01": Decimal("0.0042"), "2024-02": Decimal("-0.001")}
    assert "sha256" in s.fonte
    salvar_serie(s)
    assert carregar_series()["INPC_FICT"].valores == s.valores
    assert lacunas(s, (2024, 1), (2024, 4)) == ["2024-03", "2024-04"]


@pytest.mark.parametrize("conteudo,nome,fonte,erro", [
    (b"2024-01;0,4\n2024-01;0,5\n", "X1", "f", "repetida"),
    (b"13/2024;0,4\n", "X1", "f", "mês inválido"),
    (b"2024-01;abc\n", "X1", "f", "variação inválida"),
    (b"2024-01;0,4\n", "inpc", "f", "MAIÚSCULAS"),
    (b"2024-01;0,4\n", "X1", " ", "fonte"),
])
def test_serie_invalida(conteudo, nome, fonte, erro):
    with pytest.raises(ValueError, match=erro):
        serie_de_csv(nome, conteudo, fonte)


# --- Pendências do cálculo ----------------------------------------------------------------

def test_quadro_sem_aprovacao_bloqueia(tmp_path, series):
    docs, av = ler(gerar_caso_completo(tmp_path / "d").values())
    q = montar_quadro("FICT-011", docs, av)
    pend = lq.pendencias_calculo(q, op(), series)
    assert any("calculo.convencao_tempo" in p for p in pend)
    with pytest.raises(QuadroBloqueado):
        lq.executar(q, op(), series)


@pytest.mark.parametrize("ajuste,trecho", [
    (dict(responsavel=" "), "responsável"),
    (dict(data_base=date(2023, 3, 1)), "anterior ao último pagamento"),
    (dict(criterios=None), "critérios de correção"),
    (dict(criterios=criterios(juros_inicio=None)), "termo inicial dos juros"),
    (dict(criterios=criterios(justificativa="")), "fundamentação"),
    (dict(criterios=criterios(serie_correcao="NAO_CARREGADA")), "não carregada"),
    (dict(data_base=date(2026, 6, 1)), "sem valores para 2026-01"),
    (dict(honorarios_sobre_ap03=False), "base dos honorários"),
])
def test_pendencias_especificas(q_aprovado, series, ajuste, trecho):
    pend = lq.pendencias_calculo(q_aprovado, op(**ajuste), series)
    assert any(trecho in p for p in pend), pend


def test_venda_exige_trecho_do_titulo(q_aprovado, series):
    v = lq.DadosVenda(data_alienacao=date(2024, 9, 10), valor_venda=Decimal(1), venda_comprovada=True,
                      abater_despesas=False, compensar_creditos=False, trecho_titulo="")
    assert any("trecho do título" in p for p in lq.pendencias_calculo(q_aprovado, op(lq.TipoCalculo.VENDA, venda=v), series))


# --- Execução -------------------------------------------------------------------------------

def test_recalculo(q_aprovado, series):
    r = lq.executar(q_aprovado, op(lq.TipoCalculo.RECALCULO, criterios=None), series)
    assert r.revisao.valor_financiado_revisado == Decimal("37600.00")
    assert r.ap01.conciliacao(Decimal("40000.00")) == {"pagamentos": 0, "saldo": 0}
    assert r.ap03 is None and r.honorarios is None
    assert len(dm.linhas_evolucao(r.ap01)) == 24


def test_liquidacao_completa(q_aprovado, series):
    r = lq.executar(q_aprovado, op(compensar_saldo_revisado=True), series)
    a = r.ap03
    assert len(a.linhas) == 5 and not a.pagos_a_menor
    assert all(l.a_restituir == l.diferenca for l in a.linhas)           # restituição simples (acórdão)
    p4 = next(l for l in a.linhas if l.descricao == "Parcela 4")
    p3 = next(l for l in a.linhas if l.descricao == "Parcela 3")
    assert p4.diferenca > p3.diferenca                                   # encargos afastados pela descaracterização
    assert r.honorarios == (a.total_atualizado * Decimal("0.12")).quantize(Decimal("0.01"))
    c = r.compensacao
    assert c.saldo_a_favor_consumidor - c.saldo_a_favor_credor == c.credito_consumidor - c.saldo_devedor
    assert {"AP01", "AP02", "AP03", "atualizacao", "honorarios", "compensacao"} <= {p.etapa for p in r.memoria.passos}
    assert dm.resumo(r) and dm.linhas_diferencas(r) and dm.linhas_memoria(r)


def test_honorarios_sobre_valor_informado(q_aprovado, series):
    r = lq.executar(q_aprovado, op(honorarios_sobre_ap03=False, valor_base_honorarios=Decimal("10000")), series)
    assert r.honorarios == Decimal("1200.00")


def test_venda_com_compensacao_do_ap03(q_aprovado, series):
    v = lq.DadosVenda(data_alienacao=date(2024, 9, 10), valor_venda=Decimal("28000"), venda_comprovada=True,
                      despesas=[lq.DespesaVenda(descricao="pátio", valor=Decimal("800"), data=date(2024, 9, 1), comprovada=True),
                                lq.DespesaVenda(descricao="sem recibo", valor=Decimal("300"), data=date(2024, 9, 1), comprovada=False)],
                      abater_despesas=True, compensar_creditos=True, trecho_titulo="trecho fictício do título")
    r = lq.executar(q_aprovado, op(lq.TipoCalculo.VENDA, venda=v), series)
    vd = r.venda
    assert r.ap03 is not None and r.ap03.data_base == date(2024, 9, 10)
    assert vd.creditos_consumidor == r.ap03.total_atualizado
    assert vd.despesas_consideradas == Decimal("800") and vd.despesas_desconsideradas == Decimal("300")
    esperado = vd.saldo_devedor_revisado + Decimal("800") - Decimal("28000") - vd.creditos_consumidor
    assert vd.saldo_remanescente_consumidor == esperado.quantize(Decimal("0.01"))


def test_registro_do_resultado(q_aprovado, series, tmp_path):
    r = lq.executar(q_aprovado, op(), series)
    arq = lq.salvar_resultado(r, tmp_path / "res")
    r2 = lq.carregar_resultado(arq)
    assert r2.model_dump() == r.model_dump()
    assert r2.hash_quadro == lq.hash_quadro(q_aprovado) and r2.executado_por == "Advogada (teste)"
    assert lq.listar_resultados(tmp_path / "res") == [arq]


def test_mesma_entrada_mesmo_resultado(q_aprovado, series):
    a = lq.executar(q_aprovado, op(), series)
    b = lq.executar(q_aprovado, op(), series)
    assert a.ap03.model_dump() == b.ap03.model_dump() and a.memoria.model_dump() == b.memoria.model_dump()
