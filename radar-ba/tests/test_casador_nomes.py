"""Casamento de nomes — o ponto onde nascem falso positivo e falso negativo."""
import pytest

from src.servicos.casador_nomes import casa, similaridade, variantes_consulta


@pytest.mark.parametrize("a,b", [
    ("CAMILA COSTA ALVES", "CAMILA COSTA ALVES"),
    ("Camila Costa Alves", "CAMILA COSTA ALVES"),
    ("MARIA DA SILVA SANTOS", "MARIA SILVA SANTOS"),
    ("JOSÉ CARLOS PEREIRA", "JOSE CARLOS PEREIRA"),
])
def test_mesma_pessoa_e_reconhecida(a, b):
    ok, nota, _ = casa(a, b)
    assert ok and nota >= 0.9


@pytest.mark.parametrize("a,b", [
    ("CAMILA COSTA ALVEZ", "CAMILA COSTA ALVES"),   # erro de digitação
    ("ANA PAULA SOUZA", "ANA PAULA SOUSA"),          # variante regional
    ("LUIS TEIXEIRA LIMA", "LUIS TEIXERA LIMA"),
])
def test_variacao_de_grafia_nao_perde_o_processo(a, b):
    """Uma letra de diferença não pode fazer o radar perder a busca e apreensão."""
    ok, _, _ = casa(a, b)
    assert ok


def test_cadastro_incompleto_ainda_alcanca_o_processo():
    ok, _, _ = casa("CAMILA COSTA", "CAMILA COSTA ALVES")
    assert ok


def test_sufixo_de_geracao_nao_atrapalha():
    ok, _, _ = casa("JOSE CARLOS PEREIRA", "JOSE CARLOS PEREIRA JUNIOR")
    assert ok


@pytest.mark.parametrize("a,b", [
    ("CAMILA COSTA ALVES", "CAMILA RODRIGUES LIMA"),
    ("JOAO SILVA", "MARIA SILVA"),
    ("PEDRO HENRIQUE", "PEDRO AUGUSTO"),
    ("ANA CLARA MOTA", "BEATRIZ MOTA"),
])
def test_pessoas_diferentes_nao_casam(a, b):
    ok, _, _ = casa(a, b)
    assert not ok


def test_nome_vazio_nao_casa_com_nada():
    assert similaridade("", "CAMILA COSTA ALVES") == 0.0


def test_variantes_incluem_prefixo_para_contornar_busca_exata():
    """O DJEN casa por sequência exata; o prefixo amplia o alcance."""
    v = variantes_consulta("MARIA DA SILVA SANTOS OLIVEIRA")
    assert v[0] == "MARIA DA SILVA SANTOS OLIVEIRA"
    assert "MARIA SILVA" in v


def test_nome_curto_nao_gera_prefixo_redundante():
    assert variantes_consulta("ANA LIMA") == ["ANA LIMA"]
