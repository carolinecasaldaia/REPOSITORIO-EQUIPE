"""Leitura do número único CNJ — validada contra 360 processos reais do DJEN."""
import pytest

from src.util import cnj


@pytest.mark.parametrize("numero,esperado", [
    ("4000116-76.2026.8.26.0405", 2026),
    ("0752891-20.2023.8.02.0001", 2023),
    ("1520323-05.1984.8.13.0024", 1984),
    ("123", None),
    ("", None),
])
def test_extrai_o_ano_de_ajuizamento(numero, esperado):
    assert cnj.ano(numero) == esperado


def test_ano_absurdo_e_descartado():
    assert cnj.ano("0000000-00.9999.8.02.0001") is None


@pytest.mark.parametrize("numero,sigla,uf", [
    ("4000116-76.2026.8.26.0405", "TJSP", "SP"),
    ("0752891-20.2023.8.02.0001", "TJAL", "AL"),
    ("1520323-05.1984.8.13.0024", "TJMG", "MG"),
    ("0000000-00.2026.8.25.0001", "TJSE", "SE"),
    ("0000000-00.2026.8.17.0001", "TJPE", "PE"),
])
def test_identifica_tribunal_e_uf(numero, sigla, uf):
    assert cnj.sigla(numero) == sigla
    assert cnj.uf(numero) == uf


def test_nao_confunde_sp_com_se():
    """8.26 é São Paulo e 8.25 é Sergipe — trocar os dois inverte o estado."""
    assert cnj.sigla("0000000-00.2026.8.26.0001") == "TJSP"
    assert cnj.sigla("0000000-00.2026.8.25.0001") == "TJSE"


def test_justica_federal_fica_de_fora():
    numero = "5001234-00.2025.4.05.0001"
    assert cnj.eh_estadual(numero) is False
    assert cnj.sigla(numero) == ""


def test_todos_os_27_tribunais_estaduais_mapeados():
    assert len(cnj.TR_PARA_SIGLA) == 27
    assert len(cnj.SIGLA_PARA_UF) == 27
