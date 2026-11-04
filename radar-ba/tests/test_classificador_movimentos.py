"""Liminar deferida e mandado expedido — os dois avisos que o escritório quer.

Os textos abaixo são trechos reais de publicações de classe 81 do TJAL,
colhidos em 14/08/2026.
"""
import pytest

from src.servicos.classificador_movimentos import (CITACAO, LIMINAR_DEFERIDA,
                                                   LIMINAR_INDEFERIDA,
                                                   MANDADO_CUMPRIDO,
                                                   MANDADO_EXPEDIDO,
                                                   VEICULO_APREENDIDO,
                                                   classificar_movimento_datajud,
                                                   classificar_texto)


def tipos(texto):
    return [e.tipo for e in classificar_texto(texto).eventos]


# --- textos reais -------------------------------------------------------

def test_liminar_deferida_texto_real():
    t = ("com base no art. 3º do Decreto-lei n.º 911/69, concedo liminarmente a "
         "BUSCA E APREENSÃO do veículo descrito na inicial")
    assert LIMINAR_DEFERIDA in tipos(t)


def test_mandado_expedido_texto_real():
    t = "AUTOR: Banco Honda S/A. - Expeça-se novo mandado de busca e apreensão"
    assert MANDADO_EXPEDIDO in tipos(t)


def test_liminar_indeferida_texto_real():
    t = "razão pela qual INDEFIRO, neste momento, o pedido de tutela provisória de urgência"
    assert LIMINAR_INDEFERIDA in tipos(t)
    assert LIMINAR_DEFERIDA not in tipos(t)


# --- falsos positivos reais, que os vetos precisam barrar ---------------

def test_mandado_nao_cumprido_nao_e_mandado_cumprido():
    """'se não cumprido em trinta dias' é advertência, não cumprimento."""
    t = ("sob pena de o Oficial de Justiça encarregado devolver o mandado, "
         "se não cumprido em trinta dias")
    assert MANDADO_CUMPRIDO not in tipos(t)


def test_liminar_antiga_confirmada_nao_e_liminar_nova():
    """Sentença que confirma liminar antiga não pode virar alerta urgente."""
    t = "em favor do autor, tornando definitiva a liminar outrora concedida"
    assert LIMINAR_DEFERIDA not in tipos(t)


def test_indeferimento_vence_deferimento_no_mesmo_texto():
    t = "Deixo de conceder a liminar de busca e apreensão neste momento"
    assert LIMINAR_INDEFERIDA in tipos(t)
    assert LIMINAR_DEFERIDA not in tipos(t)


# --- comportamento geral ------------------------------------------------

def test_um_texto_pode_trazer_dois_eventos():
    t = "DEFIRO a liminar de busca e apreensão. Expeça-se mandado."
    achados = tipos(t)
    assert LIMINAR_DEFERIDA in achados and MANDADO_EXPEDIDO in achados


def test_texto_sem_evento_nao_inventa():
    assert tipos("Nada consta nos autos sobre o tema") == []
    assert tipos("") == []
    assert tipos(None) == []


def test_apreensao_do_veiculo():
    assert VEICULO_APREENDIDO in tipos("o veículo foi apreendido e entregue ao depositário")


def test_citacao_nao_e_urgente():
    leitura = classificar_texto("cite-se a parte demandada para, querendo, reaver o bem")
    assert leitura.tem(CITACAO)
    assert leitura.urgentes == []


def test_eventos_urgentes_sao_sinalizados():
    leitura = classificar_texto("Expeça-se mandado de busca e apreensão")
    assert leitura.urgentes and leitura.urgentes[0].tipo == MANDADO_EXPEDIDO


def test_trecho_de_evidencia_e_guardado():
    leitura = classificar_texto("blá blá concedo liminarmente a busca e apreensão do veículo")
    assert "liminarmente" in leitura.eventos[0].trecho


# --- DataJud ------------------------------------------------------------

def test_datajud_mandado_pelo_complemento():
    """Movimento 60 só é mandado quando o complemento diz que é."""
    mov = {"codigo": 60, "complementosTabelados": [
        {"descricao": "tipo_de_documento", "nome": "Mandado"}]}
    assert classificar_movimento_datajud(mov).tipo == MANDADO_EXPEDIDO


def test_datajud_movimento_60_de_certidao_nao_e_mandado():
    mov = {"codigo": 60, "complementosTabelados": [
        {"descricao": "tipo_de_documento", "nome": "Certidão"}]}
    assert classificar_movimento_datajud(mov) is None


def test_datajud_mandado_entregue_e_cumprimento():
    mov = {"codigo": 106, "complementosTabelados": [
        {"descricao": "resultado", "nome": "entregue ao destinatário"}]}
    assert classificar_movimento_datajud(mov).tipo == MANDADO_CUMPRIDO


def test_datajud_liminar_tem_confianca_baixa():
    """O código 339 é só 'Liminar' — não diz se foi deferida."""
    evento = classificar_movimento_datajud({"codigo": 339})
    assert evento.tipo == LIMINAR_DEFERIDA
    assert evento.confianca < 0.7
    assert "não informa o resultado" in evento.trecho


def test_datajud_movimento_irrelevante():
    assert classificar_movimento_datajud({"codigo": 92}) is None
    assert classificar_movimento_datajud(None) is None
