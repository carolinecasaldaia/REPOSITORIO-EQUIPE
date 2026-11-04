"""Interface Streamlit testada com o simulador oficial (AppTest), sem navegador. Dados FICTÍCIOS."""

from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from cm_calc.casos import Caso
from cm_calc.extracao import aprovacao as ap
from cm_calc.extracao.modelos import StatusParametro as S
from cm_calc.servicos.indices import salvar_serie, serie_de_csv
from tests.extracao.test_quadro_aprovacao import ADV, aprovar_tudo

APP = str(Path(__file__).resolve().parents[2] / "src" / "cm_calc" / "interface" / "app.py")
CSV = "competencia;variacao\n" + "\n".join(f"{a}-{m:02d};0,40" for a in (2023, 2024, 2025) for m in range(1, 13))


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("CM_CALC_DADOS", str(tmp_path / "dados"))
    monkeypatch.setenv("CM_CALC_MODO", "demonstracao")


def novo_app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def ir(at: AppTest, pagina: str) -> AppTest:
    at.sidebar.radio(key="pagina").set_value(pagina).run()
    assert not at.exception, at.exception
    return at


def textos(at: AppTest) -> str:
    return " ".join([m.value for m in at.markdown] + [m.value for m in at.caption] + [e.value for e in at.error]
                    + [s.value for s in at.success] + [w.value for w in at.warning] + [i.value for i in at.info])


def preparar_caso(at: AppTest, cid: str = "DEMO-001") -> AppTest:
    at.sidebar.text_input(key="novo_caso").input(cid)
    at.sidebar.button(key="criar_caso").click().run()
    assert at.session_state["sel_caso"] == cid
    ir(at, "Documentos")
    at.button(key="demo").click().run()
    at.button(key="extrair").click().run()
    assert not at.exception, at.exception
    return at


def test_painel_inicial_identifica_o_escritorio():
    at = novo_app()
    t = textos(at)
    assert "Caroline Macedo Advocacia" in t and "CM | Calculadora Judicial Bancária" in t
    assert "Modo demonstração" in t and "Processamento 100% local" in t


def test_identificador_de_caso_invalido_e_recusado():
    at = novo_app()
    at.sidebar.text_input(key="novo_caso").input("Joana Silva")
    at.sidebar.button(key="criar_caso").click().run()
    assert at.session_state["sel_caso"] is None
    assert any("identificador" in e.value for e in at.sidebar.error)


def test_todas_as_paginas_abrem_sem_erro():
    at = preparar_caso(novo_app())
    for pagina in ("Início", "Documentos", "Dados contratuais", "Comandos judiciais", "Pendências", "Conferência",
                   "Cálculo", "Resultados"):
        ir(at, pagina)


def test_importacao_extracao_e_quadros():
    at = preparar_caso(novo_app())
    assert "10 documento(s) lidos" in textos(at)
    ir(at, "Dados contratuais")
    contrato = at.dataframe[0].value
    assert "Valor total financiado" in list(contrato["Parâmetro"])
    ir(at, "Comandos judiciais")
    t = textos(at)
    assert "repetição do indébito" in t and "'simples'" in t                  # modificação pelo acórdão
    assert "exclusao:registro de contrato" in t                               # alegação não reconhecida
    ir(at, "Pendências")
    assert any("impedem o cálculo definitivo" in e.value for e in at.error)


def test_calculo_bloqueado_com_pendencias():
    at = preparar_caso(novo_app())
    ir(at, "Cálculo")
    at.date_input(key="data_base").set_value(date(2025, 3, 10)).run()
    assert at.button(key="executar").disabled
    assert any("Cálculo definitivo bloqueado" in e.value for e in at.error)


def test_conferencia_pela_tela():
    at = preparar_caso(novo_app())
    ir(at, "Conferência")
    assert at.button(key="c_contrato_n_parcelas").disabled                    # sem responsável
    at.sidebar.text_input(key="responsavel").input(ADV).run()
    at.button(key="c_contrato_n_parcelas").click().run()
    # parâmetro com lacuna: a taxa revisada é informada nos detalhes
    at.text_area(key="d_titulo_juros_remuneratorios").input(
        "criterio=taxa média de mercado (BACEN)\ntaxa_mensal=1,60").run()
    at.button(key="c_titulo_juros_remuneratorios").click().run()
    # parâmetro técnico: escolha obrigatória
    at.selectbox(key="v_calculo_convencao_tempo").set_value("meses_civis").run()
    at.button(key="c_calculo_convencao_tempo").click().run()
    # rejeição exige motivo
    at.button(key="r_titulo_exclusao_registro_de_contrato").click().run()
    assert any("motivo" in e.value for e in at.error)
    assert not at.exception, at.exception
    q = ap.carregar(Caso("DEMO-001").arquivo_quadro)
    assert q.parametros["contrato.n_parcelas"].status is S.CONFIRMADO
    assert q.parametros["contrato.n_parcelas"].confirmado_por == ADV
    assert q.parametros["titulo.juros_remuneratorios"].detalhes_vigentes()["taxa_mensal"] == "1,60"
    assert q.parametros["calculo.convencao_tempo"].valor_vigente() == "meses_civis"


def _aprovar_fora_da_tela(cid: str = "DEMO-001") -> None:
    c = Caso(cid)
    q = ap.carregar(c.arquivo_quadro)
    aprovar_tudo(q)
    ap.salvar(q, c.arquivo_quadro)
    salvar_serie(serie_de_csv("IDX_FICT", CSV.encode(), "série fictícia de teste"))


def preencher_criterios(at: AppTest) -> None:
    at.selectbox(key="crit_serie").set_value("IDX_FICT")
    at.radio(key="crit_mini").set_value("sim")
    at.radio(key="crit_mfim").set_value("não")
    at.number_input(key="crit_juros").set_value(1.0)
    at.date_input(key="crit_jini").set_value(date(2024, 4, 15))
    at.radio(key="crit_jcont").set_value("dias_30")
    at.radio(key="crit_acum").set_value("soma")
    at.radio(key="crit_atraso").set_value("dias_30")
    at.text_area(key="crit_just").input("Sentença fictícia: INPC desde cada desembolso; 1% a.m. desde a citação.")


def test_liquidacao_completa_pela_tela():
    at = preparar_caso(novo_app())
    _aprovar_fora_da_tela()
    at.sidebar.text_input(key="responsavel").input(ADV)
    ir(at, "Pendências")
    assert any("Nenhuma pendência obrigatória" in s.value for s in at.success)
    ir(at, "Cálculo")
    at.radio(key="tipo").set_value("Liquidação revisional (AP01, AP02, AP03 e honorários)").run()
    at.date_input(key="data_base").set_value(date(2025, 3, 10)).run()
    preencher_criterios(at)
    at.run()
    assert at.button(key="executar").disabled                                  # falta a base dos honorários
    at.radio(key="hon_base").set_value("Total atualizado do AP03").run()
    assert not at.button(key="executar").disabled, [e.value for e in at.error]
    at.button(key="executar").click().run()
    assert any("Cálculo executado e registrado" in s.value for s in at.success), textos(at)
    ir(at, "Resultados")
    rotulos = [m.label for m in at.metric]
    assert {"Parcela original", "Parcela revisada", "Indébito atualizado"} <= set(rotulos)
    assert len(at.dataframe) >= 6                                              # resumo, AP01, AP02, AP03, ressalvas, memória
    assert at.button(key="exp_xlsx").disabled and at.button(key="exp_pdf").disabled
    assert not at.exception, at.exception


def test_recalculo_e_aviso_de_quadro_alterado():
    at = preparar_caso(novo_app())
    _aprovar_fora_da_tela()
    at.sidebar.text_input(key="responsavel").input(ADV)
    ir(at, "Cálculo")
    at.date_input(key="data_base").set_value(date(2025, 3, 10)).run()
    at.button(key="executar").click().run()
    assert any("registrado" in s.value for s in at.success)
    c = Caso("DEMO-001")
    q = ap.carregar(c.arquivo_quadro)
    ap.confirmar(q, "contrato.n_parcelas", ADV, observacao="reconferido")     # altera o quadro
    ap.salvar(q, c.arquivo_quadro)
    ir(at, "Resultados")
    assert any("foi alterado depois desta execução" in w.value for w in at.warning)


def test_venda_do_veiculo_pela_tela():
    at = preparar_caso(novo_app())
    _aprovar_fora_da_tela()
    at.sidebar.text_input(key="responsavel").input(ADV)
    ir(at, "Cálculo")
    at.radio(key="tipo").set_value("Busca e apreensão — saldo após a venda do veículo").run()
    at.date_input(key="v_data").set_value(date(2024, 9, 10))
    at.number_input(key="v_valor").set_value(28000.0)
    at.checkbox(key="v_compr").check()
    at.text_area(key="v_trecho").input("Trecho fictício do título sobre a venda.")
    at.run()
    assert not at.button(key="executar").disabled, [e.value for e in at.error]
    at.button(key="executar").click().run()
    ir(at, "Resultados")
    assert "Saldo remanescente" in [m.label for m in at.metric]
