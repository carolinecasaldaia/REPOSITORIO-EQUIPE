#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Documento de cliente solto vai para DOC CLIENTE.

Os nomes usados aqui são os reais das pastas de agosto — inclusive o
"COMRPVANTE DE RESIDÊNCIA.pdf", com o erro de digitação que existe de verdade.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import documentos  # noqa: E402


def test_reconhece_os_documentos_do_cliente():
    esperado = {
        "CNH.pdf": "CNH",
        "CNH-e.pdf (14).pdf": "CNH",
        "CRLV.pdf": "CRLV",
        "CRLV-e_1415523464589BF0047.pdf.pdf": "CRLV",
        "C DE RESIDÊNCIA.pdf": "comprovante de residência",
        "COMPROVANTE DE RESIDÊNCIA.pdf": "comprovante de residência",
        "COMRPVANTE DE RESIDÊNCIA.pdf": "comprovante de residência",
        "IDENTIDADE.pdf": "RG",
        "CONTRATO DE FINANCIAMENTO.pdf": "contrato de financiamento",
        "HOLERITE.pdf": "comprovante de renda",
    }
    for arquivo, tipo in esperado.items():
        assert documentos.classificar(arquivo) == tipo, arquivo


def test_nao_toca_no_que_e_do_escritorio():
    for arquivo in ("Contrato HO Assinado.pdf", "Procuracao Assinada.pdf",
                    "Declaracao de Hipo Assinada.pdf",
                    "CONTRATO - PROCURAÇÃO - DECLARAÇÃO [assinado].pdf",
                    "onboarding_maria.pdf"):
        assert documentos.classificar(arquivo) == "", arquivo


def test_na_duvida_nao_mexe():
    """
    Arquivo que não se encaixa continua onde está — e aparece no relatório.

    (O extrato do Uber saiu desta lista em 18/08/2026: ela pediu para tratar
    comprovante de renda como documento do cliente.)
    """
    for arquivo in ("Documentos sistema solar.pdf", "boleto (2).pdf",
                    "PROPOSTA COMERCIAL 1800KWATS.pdf"):
        assert documentos.classificar(arquivo) == "", arquivo


def test_move_para_doc_cliente_sem_sobrescrever(tmp_path):
    pasta = tmp_path / "FULANO DE TAL"
    (pasta / "DOC CLIENTE").mkdir(parents=True)
    (pasta / "CNH.pdf").write_bytes(b"%PDF novo")
    (pasta / "DOC CLIENTE" / "CNH.pdf").write_bytes(b"%PDF ja estava la")
    (pasta / "boleto (2).pdf").write_bytes(b"%PDF sei la")

    movidos = documentos.arrumar(pasta)

    assert [t for _n, t, _d in movidos] == ["CNH"]
    assert (pasta / "DOC CLIENTE" / "CNH (2).pdf").exists(), "não pode sobrescrever"
    assert (pasta / "DOC CLIENTE" / "CNH.pdf").read_bytes() == b"%PDF ja estava la"
    assert (pasta / "boleto (2).pdf").exists(), "o não reconhecido fica onde está"
    assert [a.name for a in documentos.nao_reconhecidos(pasta)] == ["boleto (2).pdf"]


# --- ampliação pedida por ela em 18/08/2026 --------------------------------

def test_contrato_do_banco_com_qualquer_nome_e_do_cliente():
    for arquivo in ("contrato honda.pdf", "contrato virtuss.pdf",
                    "contrato_122749028.pdf.pdf", "CONTRATO.pdf",
                    "CONTRATO, SENHA: 448.pdf", "CONTRATO DE FINANCIAMENTO.pdf"):
        assert documentos.classificar(arquivo) == "contrato de financiamento", arquivo


def test_contrato_de_honorarios_nunca_vai_para_doc_cliente():
    """A regra ampla de "contrato" não pode engolir o contrato do escritório."""
    for arquivo in ("CONTRATO DE PRESTAÇÃO DE SERVIÇOS COMPLETO - ATUALIZADO 06:2026.pdf",
                    "2. CONTRATO DE PRESTAÇÃO DE SERVIÇOS COMPLETO.docx",
                    "Contrato HO Assinado.pdf", "CONTRATO DE HONORÁRIOS.pdf"):
        assert documentos.classificar(arquivo) == "", arquivo


def test_comprovantes_de_renda_de_todo_tipo():
    for arquivo in ("HOLERITE.pdf", "CTPS.pdf", "EXTRATO MENSAL UBER.pdf",
                    "extrato_informacao_do_beneficio.pdf"):
        assert documentos.classificar(arquivo) == "comprovante de renda", arquivo
