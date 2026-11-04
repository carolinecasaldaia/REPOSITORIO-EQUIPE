#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Leitura do nome do cliente no próprio contrato.

Os trechos abaixo são o texto real extraído dos contratos assinados de
17/08/2026 (com os nomes preservados, porque é justamente a variação deles que
o extrator precisa aguentar).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import contrato  # noqa: E402

CABECALHO = (
    "CONTRATO DE PRESTAÇÃO DE SERVIÇOS ADVOCATÍCIOS \n"
    "Pelo presente Instrumento Particular de Contrato de Prestação de Serviços \n"
    "Advocatícios que entre si fazem, de um lado, como Advogada Contratada, CAROLINE MACEDO \n"
    "SOCIEDADE INDIVIDUAL DE ADVOCACIA, pessoa jurídica de direito privado com CNPJ \n"
    "sob o nº 58.173. 643/0001-17, inscrita na OAB/AL, sob o nº 2400582, e sua sócia administradora \n"
    "CAROLINE NEIVA CHRISTOFANO MACEDO , advogada inscrita na OAB/AL 15.766 , \n"
)


def contrato_de(qualificacao):
    return CABECALHO + qualificacao


def test_pega_o_nome_do_cliente_contratante():
    texto = contrato_de("e do outro lado, como Cliente Contratante EBER ROBERTO ALMEIDA, "
                        "brasileiro, divorciado, motorista de aplicativo, portador do RG")
    assert contrato.nome_do_contratante(texto) == "EBER ROBERTO ALMEIDA"


def test_nao_confunde_a_advogada_contratada_com_o_cliente():
    """"Contratada" aparece antes no texto — não pode virar nome de pasta."""
    nome = contrato.nome_do_contratante(contrato_de(
        "e do outro lado, como Cliente Contratante JOSEFA MARIA DOS SANTOS, brasileira,"))
    assert nome == "JOSEFA MARIA DOS SANTOS"
    assert "CAROLINE" not in nome


def test_nome_quebrado_em_duas_linhas_continua_inteiro():
    texto = contrato_de("como Cliente Contratante MARIA NIZETE SANTOS DO \n"
                        "NASCIMENTO ARAÚJO, brasileira, viúva, do lar,")
    assert contrato.nome_do_contratante(texto) == "MARIA NIZETE SANTOS DO NASCIMENTO ARAÚJO"


def test_corresponsavel_e_lido_a_parte_e_nao_vira_o_cliente():
    """
    Nos contratos com corresponsável, quem assina primeiro no Autentique às
    vezes é ele. O cliente é sempre o Contratante.
    """
    texto = contrato_de(
        "como Cliente Contratante CRISTIANE FLAUZINO ROCHA DE SOUZA, brasileira, casada, "
        "do lar, e como Cliente Responsável EVANDRO DE PAULO SANTOS, brasileiro, casado,")
    assert contrato.nome_do_contratante(texto) == "CRISTIANE FLAUZINO ROCHA DE SOUZA"
    assert contrato.nome_do_responsavel(texto) == "EVANDRO DE PAULO SANTOS"


def test_contrato_sem_a_qualificacao_devolve_vazio():
    assert contrato.nome_do_contratante("PROCURAÇÃO\nOUTORGANTE: ...") == ""
    assert contrato.nome_do_responsavel(CABECALHO) == ""


def test_nao_aceita_lixo_como_nome():
    assert contrato.nome_do_contratante(contrato_de("Cliente Contratante 12345678,")) == ""
    assert contrato.nome_do_contratante(contrato_de("Cliente Contratante FULANO,")) == "", \
        "um nome de uma palavra só não é qualificação de cliente"
