#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Abertura de casos respeita a trava de execução (29/09/2026)."""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.database.controle import TravaDeExecucao                   # noqa: E402

_spec = importlib.util.spec_from_file_location("executar", RAIZ / "executar.py")
E = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(E)


class LogFalso(object):
    def __init__(self):
        self.alertas, self.erros = [], []

    def alerta(self, mensagem, **_):
        self.alertas.append(mensagem)

    def erro(self, mensagem, **_):
        self.erros.append(mensagem)

    def info(self, mensagem, **_):
        pass


class ConfigFalsa(object):
    def __init__(self, pasta):
        self.pasta_dados = Path(pasta)
        self.asaas_api_key = ""        # sem chave: para logo depois da trava


class TestTravaNaAberturaDeCasos(unittest.TestCase):

    def test_trava_ocupada_pula_a_etapa(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, log = ConfigFalsa(tmp), LogFalso()
            with TravaDeExecucao(config.pasta_dados / "execucao.lock"):
                saida = E.abrir_casos_com_entrada_paga(config, log)
            self.assertEqual(saida, ([], [], [], False))
            self.assertIn("pulada", log.alertas[0])
            self.assertEqual(log.erros, [])       # nem chegou a olhar o Asaas

    def test_trava_livre_segue_e_devolve_a_trava(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, log = ConfigFalsa(tmp), LogFalso()
            self.assertTrue(E.abrir_casos_com_entrada_paga(config, log)[3])  # sem_chave
            with TravaDeExecucao(config.pasta_dados / "execucao.lock"):
                pass                               # a trava foi solta


if __name__ == "__main__":
    unittest.main()
