#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testes da leitura do contrato pelo gerador de onboarding.

Rode com:  ~/.gerador-onboarding/venv/bin/python3 teste_leitura.py

Cada teste aqui nasceu de um contrato real que saiu errado. Não são exemplos
inventados: são as frases exatas que o PDF entregou.
"""

import unittest

from gerar_onboarding import ler_banco, ler_servico, ler_veiculo


class TestServico(unittest.TestCase):

    def test_dano_moral_no_singular(self):
        """'Morais?' não pega 'Moral' — a Juliana saía sem serviço nenhum."""
        self.assertEqual(ler_servico("ingresso da Ação de Dano Moral, referente"),
                         "Ação de Danos Morais")

    def test_obrigacao_de_fazer_ganha_da_regra_de_dano_moral(self):
        self.assertEqual(
            ler_servico("Ação de Obrigação de Fazer c/c Dano Moral, referente"),
            "Ação de Obrigação de Fazer c/c Dano Moral")

    def test_palavra_partida_pelo_pdf(self):
        """O contrato da Juliana traz 'Obri gação'; o do Lucas, inteiro."""
        self.assertEqual(
            ler_servico("Ação de Obri gação de Fazer c/c Dano Moral, referente"),
            "Ação de Obrigação de Fazer c/c Dano Moral")

    def test_busca_e_apreensao_partida(self):
        self.assertEqual(ler_servico("a defesa da Ação de Busca e Apreens ão sob o nº"),
                         "Busca e Apreensão (Defesa)")

    def test_contrato_sem_acao_conhecida_nao_chuta(self):
        self.assertEqual(ler_servico("prestação de serviços diversos"), "")


class TestParteAdversa(unittest.TestCase):

    def test_revisional_le_o_banco(self):
        self.assertEqual(
            ler_banco("Ação Revisional em desfavor do Banco BV, referente ao contrato"),
            "Banco BV")

    def test_loja_de_obrigacao_de_fazer(self):
        self.assertEqual(
            ler_banco("PLACA SAJ3H63; firmado com a empresa: MEGA MOTOS VENDAS E "
                      "SERVIÇOS LTDA. – CNPJ: 64.487.552/0001-59."),
            "MEGA MOTOS VENDAS E SERVIÇOS LTDA")

    def test_escola_de_obrigacao_de_fazer(self):
        self.assertEqual(
            ler_banco("serviços educacionais na empresa, COLÉGIO INÊS MENDES – "
                      "CNPJ: 09.3183.16-0001/09 – ENDEREÇO: RUA JOSÉ VIEIRA"),
            "COLÉGIO INÊS MENDES")

    def test_instituicao_de_pagamento(self):
        """Sofia, contrato 1: a adversa é a fintech do débito automático."""
        self.assertEqual(
            ler_banco("referente ao débito automático de boletos com a instituição: "
                      "NU PAGAMENTOS S.A. – CNPJ: 18.236.120/0001-58."),
            "NU PAGAMENTOS S.A")     # o ponto final do contrato é aparado

    def test_prefeitura_como_adversa(self):
        """Sofia, contrato 2: verbas salariais contra o município."""
        self.assertEqual(
            ler_banco("do contrato de prestação de serviço com o: MUNICÍPIO DE JEQUIÁ "
                      "DA PRAIA - AL. – CNPJ: 02.917.132/0001-08."),
            "MUNICÍPIO DE JEQUIÁ DA PRAIA - AL")

    def test_sem_adversa_devolve_vazio(self):
        self.assertEqual(ler_banco("cláusula sem parte adversa nenhuma"), "")


class TestVeiculo(unittest.TestCase):

    def test_para_no_ponto_e_virgula(self):
        """Depois do ';' vem a empresa, não o carro."""
        self.assertEqual(
            ler_veiculo("referente ao contrato do veículo HONDA POP 110I – 2021/2021 – "
                        "PLACA SAJ3H63; firmado com a empresa: MEGA MOTOS"),
            "HONDA POP 110I – 2021/2021 – PLACA SAJ3H63")

    def test_revisional_traz_o_carro_inteiro(self):
        self.assertIn("PLACA: IVA9H35", ler_veiculo(
            "referente ao contrato de financiamento do veículo CHEVROLET/ONIX 1.4MT LT "
            "- COR: PRATA - PLACA: IVA9H35 - ANO: 2013/2014"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
