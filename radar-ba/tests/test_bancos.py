"""Normalização da instituição financeira (item 7)."""
import pytest

from src.servicos.normalizador_bancos import (descrever,
                                              eh_instituicao_financeira,
                                              normalizar_banco)


@pytest.mark.parametrize("grafia", [
    "BANCO VOTORANTIM S.A.", "BANCO BV S/A", "BV FINANCEIRA S.A. - CFI", "banco bv",
])
def test_todas_as_grafias_do_bv_viram_banco_bv(grafia):
    assert normalizar_banco(grafia) == "BANCO BV"


@pytest.mark.parametrize("grafia,esperado", [
    ("ITAU UNIBANCO HOLDING S.A.", "BANCO ITAÚ"),
    ("BANCO ITAUCARD S.A.", "BANCO ITAUCARD"),
    ("BRADESCO FINANCIAMENTOS S.A.", "BRADESCO FINANCIAMENTOS"),
    ("BANCO BRADESCO SA", "BANCO BRADESCO"),
    ("BANCO PANAMERICANO S/A", "BANCO PAN"),
    ("AYMORÉ CRÉDITO FINANCIAMENTO E INVESTIMENTO S.A.", "AYMORÉ"),
    ("OMNI S/A CREDITO FINANCIAMENTO E INVESTIMENTO", "OMNI"),
])
def test_normalizacao_por_banco(grafia, esperado):
    assert normalizar_banco(grafia) == esperado


def test_itaucard_nao_e_capturado_por_itau():
    """A regra mais específica precisa vir antes da genérica."""
    assert normalizar_banco("BANCO ITAUCARD S.A.") == "BANCO ITAUCARD"


def test_bradesco_financiamentos_nao_vira_bradesco():
    assert normalizar_banco("BRADESCO FINANCIAMENTOS S.A.") == "BRADESCO FINANCIAMENTOS"


def test_pessoa_fisica_nao_e_banco():
    assert normalizar_banco("JOSE DA SILVA") == ""
    assert not eh_instituicao_financeira("JOSE DA SILVA")


def test_empresa_comum_nao_e_banco():
    assert not eh_instituicao_financeira("SISTEMA DE ENSINO POLIEDRO LTDA")


def test_fundo_e_reconhecido_como_instituicao():
    nome = "FUNDO DE INVESTIMENTO EM DIREITOS CREDITORIOS NAO PADRONIZADOS"
    assert eh_instituicao_financeira(nome)
    assert "fundo/securitizadora" in descrever(nome)
