#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Achar o banco adverso no contrato de financiamento do cliente.

O texto do teste é o começo real do contrato da Telma Cristiane Domingues.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import banco  # noqa: E402

TELMA = ("IMPORTANTE: estas são as principais condições do seu financiamento. "
         "AYMORÉ CRÉDITO, FINANCIAMENTO E INVESTIMENTO S.A. CNPJ: 07.707.650/0001-10 "
         "CONDIÇÕES ESPECÍFICAS DE OPERAÇÃO DE CRÉDITO DIRETO AO CONSUMIDOR (CDC) – VEÍCULOS")


def test_acha_o_banco_no_contrato_de_financiamento():
    assert banco.identificar(TELMA) == "Aymoré Crédito"


def test_reconhece_as_financiadoras_mais_comuns():
    modelo = "CÉDULA DE CRÉDITO BANCÁRIO - FINANCIAMENTO DE VEÍCULO. Credor: %s"
    esperado = {"BANCO PAN S.A.": "Banco Pan", "BV FINANCEIRA S.A.": "Banco BV",
                "BANCO SANTANDER (BRASIL) S.A.": "Banco Santander",
                "BANCO BRADESCO FINANCIAMENTOS S.A.": "Banco Bradesco Financiamentos S.A.",
                "BANCO ITAÚ UNIBANCO S.A.": "Banco Itaú Unibanco"}
    for texto, nome in esperado.items():
        assert banco.identificar(modelo % texto) == nome, texto


def test_documento_que_nao_e_financiamento_nao_conta():
    """Comprovante de residência do Santander não faz do Santander o adverso."""
    assert banco.identificar("Extrato de conta corrente Banco Santander agência 0001") == ""
    assert banco.identificar("") == ""


def test_nome_do_arquivo_nao_decide_nada(tmp_path):
    """'contrato honda.pdf' sem texto de financiamento não vira Honda."""
    pasta = tmp_path / "FULANO"
    (pasta / "DOC CLIENTE").mkdir(parents=True)
    (pasta / "DOC CLIENTE" / "contrato honda.pdf").write_bytes(b"%PDF")
    nome, _arquivo = banco.procurar_no_cliente(pasta, ler_pdf=lambda c: "página em branco")
    assert nome == ""


def test_procura_primeiro_em_doc_cliente(tmp_path):
    pasta = tmp_path / "TELMA"
    (pasta / "DOC CLIENTE").mkdir(parents=True)
    (pasta / "DOC CLIENTE" / "contrato virtuss.pdf").write_bytes(b"%PDF")
    nome, arquivo = banco.procurar_no_cliente(pasta, ler_pdf=lambda c: TELMA)
    assert nome == "Aymoré Crédito"
    assert arquivo.name == "contrato virtuss.pdf"


def test_ignora_o_contrato_de_honorarios(tmp_path):
    pasta = tmp_path / "FULANO"
    (pasta / "CONTRATO HO").mkdir(parents=True)
    (pasta / "CONTRATO HO" / "Contrato HO Assinado.pdf").write_bytes(b"%PDF")
    nome, _a = banco.procurar_no_cliente(pasta, ler_pdf=lambda c: TELMA)
    assert nome == "", "o contrato do escritório não é fonte de banco adverso"


def test_creditas_nao_sai_pela_metade():
    """
    "Banco Credita" era o nome truncado: a chave antiga era "CREDITA", e o
    contrato do Rafael diz CREDITAS SOCIEDADE DE CREDITO DIRETO S.A.
    """
    texto = ("CEDULA DE CREDITO BANCARIO. Esta é a sua CCB com a CREDITAS "
             "SOCIEDADE DE CREDITO DIRETO S.A. TAXA DE JUROS 2,9% ao mês.")
    assert banco.identificar(texto) == "Banco Creditas"


def test_palavra_comum_de_contrato_nao_vira_banco():
    """'valor creditado' não pode virar banco adverso."""
    texto = ("CONTRATO DE FINANCIAMENTO. O valor será creditado na conta do "
             "cliente. ALIENACAO FIDUCIARIA do veículo.")
    assert banco.identificar(texto) == ""
