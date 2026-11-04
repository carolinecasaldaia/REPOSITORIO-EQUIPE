"""Importador da RODAGEM PROCESSUAL — a carteira real do escritório.

Os testes reproduzem as duas armadilhas encontradas na planilha de verdade.
"""
import pytest

from src.servicos.importador_rodagem import (UF_POR_ABA, _rotulo, _sim,
                                             localizar_cabecalho,
                                             localizar_cpf_por_conteudo)

CPF_A = "111.444.777-35"
CPF_B = "529.982.247-25"


def test_encontra_cabecalho_depois_do_bloco_de_resumo():
    """O cabeçalho fica na 9ª ou 10ª linha, conforme a aba."""
    linhas = [
        ("RODAGEM PROCESSUAL 2026 - CAROLINE MACEDO ADVOGADOS", None),
        (None, None),
        ("SITUAÇÃO", "DESPACHO"),
        ("RESUMO", "LIMINAR DEF."),
        ("DATA (ENTRADA)", "SISTEMA", "NOME", "CPF", "Nº PROCESSO", "BUSCA"),
        ("08.12.2023", "ESAJ", "Fulano de Tal", CPF_A, "0752891-20.2023.8.02.0001", "1.0"),
    ]
    i, mapa = localizar_cabecalho(linhas)
    assert i == 4
    assert mapa["nome"] == 2 and mapa["cpf"] == 3 and mapa["busca"] == 5


def test_rotulo_com_ordinal_e_reconhecido():
    """'Nº PROCESSO' decompõe para 'No PROCESSO' — precisa virar 'NO PROCESSO'."""
    assert _rotulo("Nº PROCESSO") == "NO PROCESSO"
    assert _rotulo("N° PROC. BUSCA/ESPEC.") == "N PROC BUSCA/ESPEC"
    assert _rotulo("  situação  ") == "SITUACAO"


def test_mapeia_a_coluna_de_processo():
    linhas = [("NOME", "CPF", "Nº PROCESSO")]
    _, mapa = localizar_cabecalho(linhas)
    assert mapa["processo"] == 2


def test_acha_cpf_pelo_conteudo_quando_o_cabecalho_nao_nomeia():
    """Caso real de MARANHÃO e AMAPÁ: o cabeçalho pula a coluna de CPF."""
    dados = [
        ("2025-09-10", "PJE", "Fulano de Tal", CPF_A, "0806473-04.2024.8.10.0024"),
        ("2025-09-11", "PJE", "Beltrano Silva", CPF_B, "0806474-04.2024.8.10.0024"),
    ]
    assert localizar_cpf_por_conteudo(dados, ignorar={2}) == 3


def test_deteccao_por_conteudo_ignora_numero_de_processo():
    """Número CNJ tem 20 dígitos e não pode ser confundido com CPF."""
    dados = [("Fulano", "0806473-04.2024.8.10.0024", CPF_A)]
    assert localizar_cpf_por_conteudo(dados, ignorar={0}) == 2


def test_deteccao_por_conteudo_devolve_nada_sem_cpf_valido():
    dados = [("Fulano", "0806473-04.2024.8.10.0024", "000.000.000-00")]
    assert localizar_cpf_por_conteudo(dados, ignorar={0}) is None


@pytest.mark.parametrize("valor,esperado", [
    ("1.0", True), ("1", True), (1.0, True), ("SIM", True),
    ("NÃO", False), ("NAO", False), (None, False), ("", False), ("None", False),
])
def test_leitura_da_coluna_busca(valor, esperado):
    """A planilha marca '1.0' para sim e 'NÃO' para não."""
    assert _sim(valor) is esperado


def test_todas_as_ufs_estao_mapeadas():
    assert len(UF_POR_ABA) == 27
    assert UF_POR_ABA["SAO PAULO"] == "SP"
    assert UF_POR_ABA["ALAGOAS"] == "AL"


def test_cabecalho_ausente_nao_quebra():
    i, mapa = localizar_cabecalho([("RESUMO", "TOTAL"), (1, 2)])
    assert i is None and mapa == {}
