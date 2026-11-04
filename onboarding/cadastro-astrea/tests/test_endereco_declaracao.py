#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Conferência de endereço: declaração de residência e CEP da concessionária.

Nasceu do Leanderson (13/10/2026): a conta da Equatorial foi lida por OCR, o
único CEP legível era o da própria distribuidora, e o cliente virou "DADOS
DIVERGENTES" com o endereço certo no contrato. A declaração de residência
assinada no escritório dizia o mesmo CEP do contrato.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import controle as St                            # noqa: E402
from src.extractors import documentos as D                         # noqa: E402
from tests.test_fluxo import AstreaFalso, BaseFluxo                # noqa: E402

# O CEP do contrato de teste (COMPLETO) é 57084-818.
CEP_DO_CONTRATO = "57084-818"

DECLARACAO = ("DECLARAÇÃO DE RESIDÊNCIA ANDERSON LOPES DA SILVA, brasileiro, "
              "na falta de documentos para comprovação de residência, em "
              "conformidade com a Lei 7.115/83, DECLARO ser residente e "
              "domiciliado na Rua Bom Jesus, 27 A, Benedito Bentes, "
              "Maceió/AL, CEP: " + CEP_DO_CONTRATO)

# Conta de luz como o OCR entrega: só o cabeçalho da distribuidora é legível.
CONTA_DA_CONCESSIONARIA = (
    "Equatorial Alagoas Distribuidora de Energia S.A. Av. Fernandes Lima, "
    "3349 - Gruta de Lurdes Maceió/AL CEP: 57052-902 Insc. Estadual: "
    "24007177-8 CNPJ: 12.272.084/0001-00 CLASSIFICACAO: Residencial "
    "ANDERSON LOPES DA SILVA")


class TestEnderecoPelaDeclaracao(BaseFluxo):

    def setUp(self):
        BaseFluxo.setUp(self)
        self.rodar(AstreaFalso(self.config, self.log))      # ativa a automação

    def montar(self, nome, declaracao=None, comprovante=None):
        extras = []
        if declaracao is not None:
            extras.append("DECLARAÇÃO DE RESIDÊNCIA.pdf")
        pasta = self.criar_cliente(nome, extras=tuple(extras))
        if declaracao is not None:
            self.textos[str(pasta / "DOC CLIENTE" /
                            "DECLARAÇÃO DE RESIDÊNCIA.pdf")] = declaracao
        if comprovante is not None:
            self.textos[str(pasta / "DOC CLIENTE" /
                            "COMPROVANTE DE RESIDÊNCIA.pdf")] = comprovante
        return pasta

    def test_declaracao_confirma_o_cep_do_contrato(self):
        self.montar("30 - DECLARACAO OK", declaracao=DECLARACAO,
                    comprovante=CONTA_DA_CONCESSIONARIA)
        astrea = AstreaFalso(self.config, self.log)
        self.rodar(astrea)
        registro = self.registro("30 - DECLARACAO OK")
        self.assertEqual(registro["status"], St.CADASTRADO)
        self.assertIn("declaração de residência", registro["dados_json"] or "")
        self.assertEqual(len(astrea.cadastrados), 1)

    def test_cep_da_concessionaria_nao_vira_divergencia(self):
        """Sem declaração: o CEP ao lado do CNPJ é da empresa, não do cliente."""
        self.montar("31 - SO CONTA DE LUZ", comprovante=CONTA_DA_CONCESSIONARIA)
        astrea = AstreaFalso(self.config, self.log)
        self.rodar(astrea)
        registro = self.registro("31 - SO CONTA DE LUZ")
        self.assertEqual(registro["status"], St.CADASTRADO)
        self.assertIn("CNPJ de quem", registro["dados_json"] or "")

    def test_declaracao_com_cep_diferente_fica_divergente(self):
        self.montar("32 - DECLARACAO CONTRADIZ",
                    declaracao=DECLARACAO.replace(CEP_DO_CONTRATO, "57000-111"))
        astrea = AstreaFalso(self.config, self.log)
        self.rodar(astrea)
        registro = self.registro("32 - DECLARACAO CONTRADIZ")
        self.assertEqual(registro["status"], St.DIVERGENTE)
        self.assertEqual(astrea.cadastrados, [])

    def test_declaracao_nao_e_confundida_com_comprovante(self):
        pasta = self.montar("33 - TIPOS", declaracao=DECLARACAO)
        docs = D.inventariar(pasta)
        tipos = {d.caminho.name: d.tipo for d in docs}
        self.assertEqual(tipos["DECLARAÇÃO DE RESIDÊNCIA.pdf"],
                         "declaracao_residencia")
        self.assertEqual(tipos["COMPROVANTE DE RESIDÊNCIA.pdf"],
                         "comprovante_residencia")


if __name__ == "__main__":
    unittest.main()
