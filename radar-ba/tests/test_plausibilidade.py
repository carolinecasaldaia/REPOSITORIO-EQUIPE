"""Plausibilidade — o freio contra homônimo.

Números da carga real de 18/08/2026: 358 clientes consultados devolveram 362
processos, 272 deles (75%) em estado diferente do cadastro.
"""
from src.servicos.plausibilidade import avaliar

SP = "4000116-76.2026.8.26.0405"
AL = "0752891-20.2023.8.02.0001"
FEDERAL = "5001234-00.2025.4.05.0001"


def test_mesmo_estado_mantem_a_confianca():
    fator, obs = avaliar(SP, ["SP"], "Ana Beatriz Kowalski")
    assert fator == 1.0
    assert "mesmo estado" in obs


def test_estado_diferente_rebaixa():
    fator, obs = avaliar(SP, ["AL"], "Ana Beatriz Kowalski")
    assert fator < 0.6
    assert "cliente cadastrado em AL" in obs


def test_cliente_com_processo_em_dois_estados_nao_e_penalizado():
    fator, _ = avaliar(SP, ["AL", "SP"], "Ana Beatriz Kowalski")
    assert fator == 1.0


def test_justica_federal_e_fortemente_rebaixada():
    fator, obs = avaliar(FEDERAL, ["AL"], "Ana Beatriz Kowalski")
    assert fator <= 0.35
    assert "fora da Justiça Estadual" in obs


def test_nome_pouco_distintivo_rebaixa():
    """'Marcos da Silva' casa com meio país; 'Ana Kowalski' não."""
    comum, _ = avaliar(AL, ["AL"], "Marcos da Silva")
    raro, _ = avaliar(AL, ["AL"], "Ana Beatriz Kowalski")
    assert comum < raro


def test_muitos_achados_denunciam_homonimo():
    """Um nome que puxa 24 processos não tem 24 processos — tem homônimos."""
    poucos, _ = avaliar(AL, ["AL"], "Ana Beatriz Kowalski", achados_do_cliente=1)
    muitos, obs = avaliar(AL, ["AL"], "Ana Beatriz Kowalski", achados_do_cliente=24)
    assert muitos < poucos / 1.5
    assert "homônimo" in obs


def test_fator_nunca_zera():
    """Rebaixar é diferente de descartar: a decisão final é humana."""
    fator, _ = avaliar(FEDERAL, ["AL"], "Marcos da Silva", achados_do_cliente=30)
    assert fator >= 0.1


def test_sem_uf_cadastrada_nao_penaliza_por_estado():
    fator, _ = avaliar(SP, [], "Ana Beatriz Kowalski")
    assert fator == 1.0
