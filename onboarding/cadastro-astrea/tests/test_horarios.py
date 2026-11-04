#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Leitura de HORARIOS do .env.

A faixa "08-20:40" nasceu em 08/09/2026: ela pediu o cadastro de hora em hora,
o que passou a ser possível porque o Claude tem login próprio no Astrea e não
derruba mais a sessão dela.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config.settings import Config                             # noqa: E402

ler = Config._ler_horarios


class TestHorarios(unittest.TestCase):

    def test_horas_soltas(self):
        self.assertEqual(ler("06:00,21:00"), [(6, 0), (21, 0)])

    def test_hora_sem_minuto(self):
        self.assertEqual(ler("7"), [(7, 0)])

    def test_faixa_de_hora_em_hora(self):
        self.assertEqual(ler("08-11:40"),
                         [(8, 40), (9, 40), (10, 40), (11, 40)])

    def test_faixa_sem_minuto_cai_na_hora_cheia(self):
        self.assertEqual(ler("22-23"), [(22, 0), (23, 0)])

    def test_faixa_misturada_com_hora_solta(self):
        self.assertEqual(ler("08-09:40,23:30"), [(8, 40), (9, 40), (23, 30)])

    def test_nao_repete_horario(self):
        """'08:40' junto da faixa que já inclui 08:40 não pode duplicar."""
        self.assertEqual(ler("08-09:40,08:40"), [(8, 40), (9, 40)])

    def test_sai_em_ordem(self):
        self.assertEqual(ler("21:00,06:00"), [(6, 0), (21, 0)])

    def test_hora_invalida_e_ignorada(self):
        self.assertEqual(ler("99:00,08:40"), [(8, 40)])

    def test_faixa_invertida_nao_gera_nada(self):
        self.assertEqual(ler("20-08:40"), [(6, 0), (21, 0)])   # cai no padrão

    def test_vazio_cai_no_padrao(self):
        self.assertEqual(ler(""), [(6, 0), (21, 0)])


if __name__ == "__main__":
    unittest.main()
