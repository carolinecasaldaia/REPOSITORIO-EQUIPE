"""Classificador de Busca e Apreensão (item 6)."""
import pytest

from src.servicos.classificador_busca_apreensao import (CLASSES_EXCLUIDAS,
                                                        classificar,
                                                        codigo_pelo_nome)


def test_classe_81_e_busca_e_apreensao_com_alta_confianca():
    r = classificar(classe_codigo=81)
    assert r.eh_busca_apreensao and r.confianca >= 0.95


def test_assunto_e_banco_reforcam_a_confianca():
    base = classificar(classe_codigo=81).confianca
    reforcado = classificar(classe_codigo=81,
                            assuntos=[{"codigo": 9582, "nome": "Alienação Fiduciária"}],
                            banco_normalizado="BANCO PAN")
    assert reforcado.confianca > base


@pytest.mark.parametrize("codigo", sorted(CLASSES_EXCLUIDAS))
def test_classes_excluidas_nunca_sao_busca_e_apreensao(codigo):
    """Criminal, infracional, infância e Fazenda jamais podem virar alerta."""
    r = classificar(classe_codigo=codigo)
    assert r.eh_busca_apreensao is False
    assert "Excluído" in r.motivo


def test_exclusao_vence_mesmo_com_banco_no_polo_ativo():
    r = classificar(classe_codigo=309, banco_normalizado="BANCO PAN")
    assert r.eh_busca_apreensao is False


def test_execucao_sem_banco_tem_confianca_baixa():
    sem = classificar(classe_codigo=12154)
    com = classificar(classe_codigo=12154, banco_normalizado="BANCO BV")
    assert sem.confianca < com.confianca
    assert sem.confianca < 0.6


def test_classe_alheia_nao_e_alvo():
    assert classificar(classe_codigo=436).eh_busca_apreensao is False


def test_texto_livre_sem_codigo_tem_confianca_moderada():
    """Descrição solta, que não é nome exato de classe: confiança baixa."""
    r = classificar(classe_nome="Ação de busca e apreensão fundada no Decreto-Lei 911/69")
    assert r.eh_busca_apreensao and r.confianca < 0.8


def test_texto_que_nao_menciona_o_tema_nao_e_alvo():
    r = classificar(classe_nome="ação de cobrança de veículo alienado")
    assert r.eh_busca_apreensao is False


def test_nome_exato_de_classe_vale_como_codigo():
    """O e-SAJ devolve o NOME da classe, não o código.

    Sem essa ponte, um processo confirmado por CPF e chamado exatamente
    "Busca e Apreensão em Alienação Fiduciária" saía com confiança de texto
    genérico (0,65) em vez da confiança de classe (0,98+).
    """
    assert codigo_pelo_nome("Busca e Apreensão em Alienação Fiduciária") == 81
    r = classificar(classe_nome="Busca e Apreensão em Alienação Fiduciária")
    assert r.eh_busca_apreensao and r.confianca >= 0.95


def test_ponte_de_nome_respeita_as_exclusoes():
    """Nome exato de classe criminal continua excluído."""
    assert codigo_pelo_nome("Pedido de Busca e Apreensão Criminal") == 309
    assert classificar(classe_nome="Pedido de Busca e Apreensão Criminal").eh_busca_apreensao is False


def test_ponte_de_nome_ignora_acento_e_caixa():
    assert codigo_pelo_nome("BUSCA E APREENSAO EM ALIENACAO FIDUCIARIA") == 81
    assert codigo_pelo_nome("busca e apreensão em alienação fiduciária") == 81


def test_nome_desconhecido_nao_vira_codigo():
    assert codigo_pelo_nome("Procedimento do Juizado Especial Cível") is None
    assert codigo_pelo_nome("") is None


def test_texto_criminal_e_descartado():
    r = classificar(classe_nome="Pedido de Busca e Apreensão Criminal")
    assert r.eh_busca_apreensao is False


def test_formato_json_da_especificacao():
    j = classificar(classe_codigo=81).para_json()
    assert set(j) == {"isSearchAndSeizure", "confidence", "reason"}
    assert j["isSearchAndSeizure"] is True


def test_assunto_nao_transforma_classe_alheia_em_busca_e_apreensao():
    """Falso positivo real, achado na varredura por CPF do e-SAJ.

    "Procedimento Comum Cível" com assunto "Alienação Fiduciária" é
    tipicamente a REVISIONAL do próprio escritório. Enquanto o assunto entrava
    na regra de texto, ela era alertada como busca e apreensão contra o cliente.
    """
    r = classificar(classe_nome="Procedimento Comum Cível",
                    assuntos=["Alienação Fiduciária"])
    assert r.eh_busca_apreensao is False


def test_juizado_com_assunto_de_alienacao_tambem_e_descartado():
    r = classificar(classe_nome="Procedimento do Juizado Especial Cível",
                    assuntos=["Alienação Fiduciária"])
    assert r.eh_busca_apreensao is False


def test_assunto_ainda_reforca_quando_a_classe_e_alvo():
    """Assunto reforça uma classe alvo; só não pode estabelecê-la sozinho."""
    sem = classificar(classe_codigo=81).confianca
    com = classificar(classe_codigo=81,
                      assuntos=[{"codigo": 9582, "nome": "Alienação Fiduciária"}]).confianca
    assert com > sem
