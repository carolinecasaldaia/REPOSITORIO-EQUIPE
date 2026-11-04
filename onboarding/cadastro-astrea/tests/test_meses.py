#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MESES="a partir de SETEMBRO 2026": setembro em diante, nunca antes (25/09/2026)."""

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.drive import scanner as S                                  # noqa: E402


class TestAPartirDe(unittest.TestCase):

    def test_em_setembro_olha_setembro_e_a_pasta_adiantada_de_outubro(self):
        self.assertEqual(S._meses_desde("SETEMBRO 2026", datetime(2026, 9, 25)),
                         ["SETEMBRO 2026", "OUTUBRO 2026"])

    def test_virada_do_mes_nao_larga_setembro(self):
        meses = S._meses_desde("SETEMBRO 2026", datetime(2026, 10, 1))
        self.assertIn("SETEMBRO 2026", meses)
        self.assertNotIn("AGOSTO 2026", meses)

    def test_virada_do_ano(self):
        self.assertEqual(S._meses_desde("SETEMBRO 2026", datetime(2027, 1, 2))[-2:],
                         ["JANEIRO 2027", "FEVEREIRO 2027"])

    def test_configuracao_aceita_desde_e_minusculas(self):
        self.assertIn("SETEMBRO 2026", S.meses_aceitos("desde setembro 2026"))
        self.assertIn("SETEMBRO 2026", S.meses_aceitos("a partir de SETEMBRO 2026"))

    def test_mes_escrito_errado_nao_vira_todos_os_meses(self):
        with self.assertRaises(ValueError):
            S.meses_aceitos("a partir de SETEMBR 2026")

    def test_varredura_ignora_meses_anteriores(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            for mes, cliente in (("AGOSTO 2026", "ANTIGO"), ("SETEMBRO 2026", "NOVO")):
                (raiz / mes / cliente).mkdir(parents=True)
            original = S.id_do_drive
            S.id_do_drive = lambda caminho: ("local:x", "local")
            try:
                nomes = [p.nome_pasta for p in
                         S.varrer(raiz, S.meses_aceitos("a partir de SETEMBRO 2026"))]
            finally:
                S.id_do_drive = original
            self.assertEqual(nomes, ["NOVO"])


if __name__ == "__main__":
    unittest.main()
