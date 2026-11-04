"""Nenhum CPF completo pode escapar para o log (item 9)."""
from src.util.log import mascarar_cpf


def test_mascara_cpf_pontuado():
    assert mascarar_cpf("cliente 123.456.789-12") == "cliente ***.***.***-12"


def test_mascara_cpf_sem_pontuacao():
    assert mascarar_cpf("doc 98765432100 fim") == "doc ***.***.***-00 fim"


def test_mascara_varios_cpfs_na_mesma_linha():
    saida = mascarar_cpf("A 111.444.777-35 B 52998224725")
    assert "444" not in saida and "982" not in saida
    assert saida.count("***.***.***") == 2


def test_nao_estraga_numero_de_processo():
    """Número CNJ tem 20 dígitos e não pode ser confundido com CPF."""
    numero = "4000116-76.2026.8.26.0405"
    assert mascarar_cpf(numero) == numero


def test_texto_sem_cpf_fica_intacto():
    assert mascarar_cpf("nenhum documento aqui") == "nenhum documento aqui"
