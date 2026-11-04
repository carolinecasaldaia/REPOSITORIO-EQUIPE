#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Envelope com mais de um contrato — o caso da Sofia Evangelista (01/09/2026).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import multicontrato                                       # noqa: E402

TITULO = "CONTRATO DE PRESTAÇÃO DE SERVIÇOS ADVOCATÍCIOS"
ASSINATURA = "Identificador: 5a60671 Data/Hora em GMT -3:00 por Google Trusted"


class LeitorFalso(object):
    """Um PdfReader de mentira: só precisa de páginas com extract_text()."""

    class Pagina(object):
        def __init__(self, texto):
            self._texto = texto

        def extract_text(self):
            if self._texto is None:
                raise ValueError("página ilegível")
            return self._texto

    def __init__(self, textos):
        self.pages = [self.Pagina(t) for t in textos]


def contrato(objeto):
    return ("%s Pelo presente Instrumento Particular, como Cliente Contratante "
            "SOFIA EVANGELISTA ARRUDA DE OLIVEIRA. Cláusula 1ª. Advogada contratada "
            "obriga-se, para realizar %s, referente ao que segue. Cláusula 2ª."
            % (TITULO, objeto))


class TestConferir(unittest.TestCase):

    def test_envelope_de_um_contrato_so_nao_vira_aviso(self):
        leitor = LeitorFalso([contrato("o ingresso da Ação Revisional"), ASSINATURA])
        self.assertIsNone(multicontrato.conferir(leitor))

    def test_dois_contratos_sao_apontados_com_pagina_e_objeto(self):
        leitor = LeitorFalso([
            contrato("o ingresso da Ação de Obrigação de Fazer c/Dano Moral"),
            "continuação do primeiro contrato",
            contrato("o ingresso da Ação de Danos Morais"),
            ASSINATURA,
        ])
        achado = multicontrato.conferir(leitor)
        self.assertEqual(achado["quantos"], 2)
        self.assertEqual(achado["paginas"], [1, 3])
        self.assertIn("Obrigação de Fazer", achado["objetos"][0])
        self.assertIn("Danos Morais", achado["objetos"][1])

    def test_pagina_ilegivel_nao_derruba_a_conferencia(self):
        leitor = LeitorFalso([contrato("o ingresso da Ação Revisional"), None,
                              contrato("a defesa da Ação de Busca e Apreensão")])
        self.assertEqual(multicontrato.conferir(leitor)["quantos"], 2)

    def test_sem_leitor_nao_estoura(self):
        self.assertIsNone(multicontrato.conferir(None))

    def test_titulo_sem_acento_tambem_conta(self):
        """O PDF às vezes entrega o texto sem acentuação."""
        leitor = LeitorFalso(["CONTRATO DE PRESTACAO DE SERVICOS ADVOCATICIOS ...",
                              "CONTRATO DE PRESTACAO DE SERVICOS ADVOCATICIOS ..."])
        self.assertEqual(multicontrato.conferir(leitor)["quantos"], 2)


class TestFatiar(unittest.TestCase):
    """Quais páginas vão para cada contrato."""

    def _leitor(self):
        rodape = " Assinado com Assinatura Eletrônica (Lei 14.063/2020) Hash SHA256"
        return LeitorFalso([
            contrato("o ingresso da Ação de Obrigação de Fazer") + rodape,
            "Cláusula 5ª. continuação do primeiro" + rodape,
            contrato("o ingresso da Ação de Danos Morais") + rodape,
            "Cláusula 5ª. continuação do segundo" + rodape,
            ASSINATURA,
        ])

    def test_cada_contrato_leva_a_folha_de_assinatura(self):
        self.assertEqual(multicontrato.fatiar(self._leitor()), [[1, 2, 5], [3, 4, 5]])

    def test_o_rodape_de_assinatura_nao_transforma_o_contrato_em_folha_de_assinatura(self):
        """
        A pegadinha: "Assinado com Assinatura Eletrônica" está no rodapé de
        TODAS as páginas. Tomá-lo como marca fazia o contrato 1 sair com 11
        páginas em vez de 7 (01/09/2026).
        """
        fatias = multicontrato.fatiar(self._leitor())
        self.assertNotIn(3, fatias[0])          # a página 3 é do contrato 2
        self.assertNotIn(4, fatias[0])

    def test_sem_folha_de_assinatura_no_fim(self):
        leitor = LeitorFalso([contrato("a defesa da Ação de Busca e Apreensão"),
                              contrato("o ingresso da Ação Revisional")])
        self.assertEqual(multicontrato.fatiar(leitor), [[1], [2]])

    def test_um_contrato_so_nao_fatia(self):
        self.assertEqual(multicontrato.fatiar(LeitorFalso([contrato("x"), ASSINATURA])), [])


class TestRecado(unittest.TestCase):

    def test_recado_diz_quantos_onde_e_o_que_fazer(self):
        achado = {"quantos": 2, "paginas": [1, 6],
                  "objetos": ["o ingresso da Ação de Obrigação de Fazer", ""]}
        texto = multicontrato.recado(achado, "SOFIA EVANGELISTA")
        self.assertIn("2 contratos", texto)
        self.assertIn("páginas 1, 6", texto)
        self.assertIn("SOFIA EVANGELISTA", texto)
        self.assertIn("uma pasta por contrato", texto)

    def test_sem_achado_nao_ha_recado(self):
        self.assertEqual(multicontrato.recado(None), "")


if __name__ == "__main__":
    unittest.main()
