"""Cumprimento de sentença a partir da ficha — dados FICTÍCIOS."""

import json
from datetime import date
from decimal import Decimal as D

import pytest

from cm_calc.motor.atualizacao import SerieMensal
from cm_calc.motor.taxas import ConvencaoTempo, Regime, Taxa
from cm_calc.servicos import cumprimento as cs

TRECHO = "Dados fictícios de teste — trecho do dispositivo"
F = {"documento": "Dados fictícios de teste", "localizacao": "fls. 1"}
FT = {**F, "trecho": TRECHO}


def _venc(n):
    m = 2 + n - 1
    return date(2021 + (m - 1) // 12, (m - 1) % 12 + 1, 10)


def _series():
    inpc = {f"{a:04d}-{m:02d}": D("0.004") for a in range(2020, 2027) for m in range(1, 13)}
    selic = {f"{a:04d}-{m:02d}": D("0.01") for a in range(2020, 2027) for m in range(1, 13)}
    return {"INPC": SerieMensal(nome="INPC", valores=inpc, fonte="fictícia"),
            "SELIC": SerieMensal(nome="SELIC", valores=selic, fonte="fictícia", embute_correcao=True)}


def _fases():
    return {"fases": [
        {"fim": "10/03/2024", "descricao": "INPC + mora 1% a.m. até a citação", "correcao": "INPC",
         "juros": {"tipo": "percentual_fixo", "percentual_mensal": "1", "inicio": "10/02/2021", "contagem": "meses_civis"},
         "incluir_mes_inicial": False, "incluir_mes_final": True, "acumulacao_juros": "soma",
         "juros_desde_antes_do_valor": True},
        {"fim": "data_base", "descricao": "Selic após a citação", "correcao": None,
         "juros": {"tipo": "serie", "serie": "SELIC"},
         "incluir_mes_inicial": False, "incluir_mes_final": False, "acumulacao_juros": "produto"}],
        "fonte": FT}


def ficha(**extra):
    parcelas = [{"numero": n, "vencimento": _venc(n).strftime("%d/%m/%Y")} for n in range(1, 25)]
    pagamentos = [{"numero": n, "data": _venc(n).strftime("%d/%m/%Y"), "valor": "1600.00", "fonte": F}
                  for n in range(1, 25)]
    base = {
        "caso": "TESTE-CUMPRIMENTO-001", "responsavel": "Teste", "data_base": "31/08/2026",
        "arredondamento": "2;HALF_UP;por_parcela",
        "contrato": {"data_liberacao": "10/01/2021", "valor_financiado": "30000.00", "taxa_mensal": "2,0",
                     "regime": "composto", "convencao": "meses_30", "parcela_regular": "1600.00",
                     "parcelas": parcelas, "fonte": F},
        "revisao": {"taxa_mensal": "1,5", "regime": "composto", "convencao": "meses_civis", "fonte": FT},
        "restituicao": {"modalidade": "simples", "fonte": FT},
        "pagamentos": pagamentos,
        "atualizacao": _fases(),
    }
    base.update(extra)
    return cs.Ficha.model_validate(base)


def test_ap03_em_fases_inpc_mora_ate_citacao_e_selic_depois():
    r = cs.calcular(ficha(), _series())
    assert r.revisao.parcela_regular_revisada < D("1600.00")
    assert len(r.ap03.linhas) == 24 and not r.ap03.pagos_a_menor
    # cada linha: (diferença × INPC × (1 + mora)) consolidado na citação × Selic até a data-base
    assert all(l.atualizado > l.a_restituir for l in r.ap03.linhas)
    assert r.condenacao == r.ap03.total_atualizado
    assert any("Selic" in p.descricao for p in r.memoria.passos)


def test_ultima_fase_precisa_terminar_na_data_base():
    f = _fases()
    f["fases"][-1]["fim"] = "01/01/2026"
    with pytest.raises(ValueError, match="data-base"):
        cs.calcular(ficha(atualizacao=f), _series())


def test_criterio_do_titulo_sem_trecho_e_recusado():
    with pytest.raises(ValueError, match="trecho"):
        ficha(restituicao={"modalidade": "simples", "fonte": F})


def test_antecipada_com_desconto_traz_o_devido_a_valor_presente():
    f = ficha()
    taxa = Taxa(D("0.015"), Regime.COMPOSTO, ConvencaoTempo.MESES_CIVIS)
    pag = f.pagamentos[-1]
    pag.data = "10/06/2022"                      # 20 meses antes do vencimento (10/01/2023)… com desconto
    pag.valor = "1200.00"
    pag.antecipada_com_desconto = True
    r = cs.calcular(f, _series())
    linha = next(l for l in r.ap03.linhas + r.ap03.pagos_a_menor if l.descricao == "Parcela 24")
    esperado = (r.revisao.parcelas_revisadas[24] / taxa.fator(date(2022, 6, 10), _venc(24))).quantize(D("0.01"))
    assert linha.devido == esperado
    assert linha.devido < r.revisao.parcelas_revisadas[24]


def test_juros_simples_reduzem_a_prestacao_frente_ao_composto():
    comp = cs.calcular(ficha(), _series()).revisao.parcela_regular_revisada
    rev = {"taxa_mensal": "1,5", "regime": "simples", "convencao": "meses_civis", "fonte": FT}
    simp = cs.calcular(ficha(revisao=rev), _series()).revisao.parcela_regular_revisada
    assert simp < comp


def test_dobro_a_partir_de_data_de_corte():
    simples = cs.calcular(ficha(), _series()).ap03.total_a_restituir_nominal
    dobro = cs.calcular(ficha(restituicao={"modalidade": "dobro_a_partir_de", "data_corte": "30/03/2021",
                                           "fonte": FT}), _series()).ap03.total_a_restituir_nominal
    assert simples < dobro < 2 * simples


def test_exclusao_de_seguro_financiado_reduz_o_valor_financiado():
    rev = {"taxa_mensal": "2,0", "regime": "composto", "convencao": "meses_30", "fonte": FT,
           "itens_excluidos": [{"descricao": "Seguro prestamista", "valor": "900.00", "financiado": True, "fonte": FT}]}
    r = cs.calcular(ficha(revisao=rev), _series())
    assert r.revisao.valor_financiado_revisado == D("29100.00")
    assert r.ap03.total_a_restituir_nominal > 0


def test_dano_moral_atualizado_e_honorarios_sobre_a_condenacao():
    verba = {"descricao": "Dano moral", "valor_fixo": "5000.00", "data_base_verba": "10/03/2025",
             "atualizacao": {"fases": [{"fim": "data_base", "descricao": "Selic desde o arbitramento",
                                        "correcao": None, "juros": {"tipo": "serie", "serie": "SELIC"},
                                        "incluir_mes_inicial": False, "incluir_mes_final": False,
                                        "acumulacao_juros": "produto"}], "fonte": FT},
             "fonte": FT}
    hon = {"base": "valor da condenação", "percentual": "10", "devedor": "réu", "fonte": FT}
    r = cs.calcular(ficha(verbas=[verba], honorarios=hon), _series())
    (_, original, atual), = r.verbas
    assert original == D("5000.00") and atual > original
    assert r.condenacao == r.ap03.total_atualizado + atual
    assert r.honorarios == (r.condenacao * D("0.10")).quantize(D("0.01"))
    assert r.total == r.condenacao + r.honorarios


def test_revisao_sem_pagamentos_gera_so_o_ap02():
    r = cs.calcular(ficha(pagamentos=[], restituicao=None, atualizacao=None), _series())
    assert r.ap02 is not None and r.ap03 is None and r.condenacao == 0


def test_honorarios_sobre_valor_da_causa_ipca_e_juros_selic_menos_ipca():
    s = _series()
    s["IPCA"] = SerieMensal(nome="IPCA", valores={k: D("0.003") for k in s["INPC"].valores}, fonte="fictícia")
    verba = {"descricao": "Honorários de sucumbência (10% do valor da causa)", "percentual": "10",
             "valor_base": "10000.00", "data_base_verba": "20/05/2025",
             "atualizacao": {"fases": [
                 {"fim": "24/07/2026", "descricao": "IPCA até o trânsito", "correcao": "IPCA",
                  "incluir_mes_inicial": False, "incluir_mes_final": True, "acumulacao_juros": "soma"},
                 {"fim": "data_base", "descricao": "IPCA + juros legais (Selic − IPCA)", "correcao": "IPCA",
                  "juros": {"tipo": "serie_menos_serie", "serie": "SELIC", "serie_deduzir": "IPCA", "piso_zero": True},
                  "incluir_mes_inicial": False, "incluir_mes_final": False, "acumulacao_juros": "soma"}],
                 "fonte": FT},
             "fonte": FT}
    r = cs.calcular(ficha(pagamentos=[], restituicao=None, atualizacao=None, verbas=[verba],
                          data_base="31/10/2026"), s)
    (_, original, atual), = r.verbas
    assert original == D("1000.00")
    # 14 meses de IPCA (jun/25–jul/26) na 1ª fase; ago e set/26 com IPCA + 0,7% de juros na 2ª
    f1 = D("1000.00") * D("1.003") ** 14
    esperado = (f1.quantize(D("0.01")) * D("1.003") ** 2 * (1 + D("0.014"))).quantize(D("0.01"))
    assert abs(atual - esperado) <= D("0.02")


def test_verba_sem_trecho_do_titulo_e_recusada():
    with pytest.raises(ValueError, match="trecho"):
        ficha(verbas=[{"descricao": "Dano moral", "valor_fixo": "5000", "data_base_verba": "10/03/2025", "fonte": F}])


def test_cli_gera_planilha_e_resumo(tmp_path):
    from cm_calc.cli import main
    arq = tmp_path / "ficha.json"
    arq.write_text(ficha().model_dump_json(), encoding="utf-8")
    ind = tmp_path / "indices"
    ind.mkdir()
    for nome, v in (("INPC", "0,40"), ("SELIC", "1,00")):
        (ind / f"{nome}.csv").write_text("\n".join(f"{a:04d}-{m:02d};{v}" for a in range(2020, 2027)
                                                    for m in range(1, 13)), encoding="utf-8")
        (ind / f"{nome}.fonte.txt").write_text("série fictícia de teste", encoding="utf-8")
    assert main(["cumprimento", str(arq), "--indices", str(ind), "--saida", str(tmp_path / "saida")]) == 0
    assert list((tmp_path / "saida").glob("memoria-*.xlsx")) and list((tmp_path / "saida").glob("memoria-*.md"))
    dados = json.loads(next((tmp_path / "saida").glob("memoria-*.json")).read_text(encoding="utf-8"))
    assert D(str(dados["total"])) > 0


def test_cumprimento_so_de_honorarios_sem_contrato():
    hon_verba = {"descricao": "Honorários de sucumbência — 10% do valor da causa", "percentual": "10",
                 "valor_base": "10000.00", "data_base_verba": "20/05/2025", "fonte": FT}
    f = cs.Ficha.model_validate({"caso": "TESTE-HON-001", "responsavel": "Teste", "data_base": "31/10/2026",
                                 "arredondamento": "2;HALF_UP;por_parcela", "verbas": [hon_verba]})
    r = cs.calcular(f, _series())
    assert r.ap01 is None and r.ap02 is None and r.total == D("1000.00")
    assert "Prestação" not in cs.markdown(r)


def test_ficha_vazia_e_recusada():
    with pytest.raises(ValueError, match="nada a calcular"):
        cs.Ficha.model_validate({"caso": "TESTE-X", "responsavel": "Teste", "data_base": "31/10/2026",
                                 "arredondamento": "2;HALF_UP;por_parcela"})
