#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entrada no Asaas pelo CPF do cliente responsável (caso Adonias, 29/09/2026)."""

import importlib.util
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src import asaas                                               # noqa: E402

_spec = importlib.util.spec_from_file_location("executar", RAIZ / "executar.py")
E = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(E)

CONTRATANTE, RESPONSAVEL = "049.000.000-40", "055.000.000-66"


class LogFalso(object):
    def __init__(self):
        self.alertas, self.infos = [], []

    def alerta(self, mensagem, **_):
        self.alertas.append(mensagem)

    def info(self, mensagem, **_):
        self.infos.append(mensagem)


class Config(object):
    asaas_api_key = "x"
    asaas_texto_entrada = "ENTRADA"


class TestEntradaDoCliente(unittest.TestCase):

    def setUp(self):
        self._original = asaas.entrada_paga
        self.pagos = {}
        asaas.entrada_paga = lambda cpf, chave, texto: self.pagos.get(E._so_digitos(cpf))
        self.item = {"cpf_cnpj": CONTRATANTE, "cliente": "Adonias Estevam da Silva",
                     "cpf_responsavel": RESPONSAVEL, "nome_responsavel": "JEREMIAS"}
        self.log = LogFalso()

    def tearDown(self):
        asaas.entrada_paga = self._original

    def entrada(self, cpfs_de_clientes=()):
        return E._entrada_do_cliente(self.item, Config(), self.log,
                                     {E._so_digitos(c) for c in cpfs_de_clientes})

    def test_acha_pelo_contratante_primeiro(self):
        self.pagos = {E._so_digitos(CONTRATANTE): {"id": "c1"},
                      E._so_digitos(RESPONSAVEL): {"id": "r1"}}
        self.assertEqual(self.entrada()["id"], "c1")

    def test_cai_para_o_responsavel(self):
        self.pagos = {E._so_digitos(RESPONSAVEL): {"id": "r1"}}
        self.assertEqual(self.entrada([CONTRATANTE])["id"], "r1")
        self.assertIn("responsável", self.log.infos[0])

    def test_responsavel_que_tambem_e_cliente_nao_abre(self):
        self.pagos = {E._so_digitos(RESPONSAVEL): {"id": "r1", "description": "ENTRADA X"}}
        self.assertIsNone(self.entrada([CONTRATANTE, RESPONSAVEL]))
        self.assertIn("NÃO abri", self.log.alertas[0])

    def test_sem_responsavel_nao_procura_mais_nada(self):
        self.item["cpf_responsavel"] = ""
        self.pagos = {E._so_digitos(RESPONSAVEL): {"id": "r1"}}
        self.assertIsNone(self.entrada())

    def test_ninguem_pagou(self):
        self.assertIsNone(self.entrada([CONTRATANTE]))
        self.assertEqual(self.log.alertas, [])


if __name__ == "__main__":
    unittest.main()


class TestPagamentoAVista(unittest.TestCase):
    """
    Cobrança quitada que cobre o contrato inteiro vale como entrada paga
    (decisão dela, 19/10/2026). A Dione pagou R$ 4.948,19 num contrato de
    R$ 4.497,00, e a cobrança se chamava "AÇÃO DE BUSCA E APREENSÃO".
    """

    def cobrancas(self, *valores):
        return {"data": [{"id": "pay_%d" % i, "value": v, "status": "RECEIVED",
                          "description": "AÇÃO DE BUSCA E APREENSÃO"}
                         for i, v in enumerate(valores)], "hasMore": False}

    def preparar(self, resposta):
        from src import asaas
        self.original_chamar = asaas._chamar
        self.original_buscar = asaas.buscar_cliente_por_cpf
        asaas._chamar = lambda *a, **k: resposta
        asaas.buscar_cliente_por_cpf = lambda *a, **k: "cus_1"
        self.addCleanup(self.restaurar)
        return asaas

    def restaurar(self):
        from src import asaas
        asaas._chamar = self.original_chamar
        asaas.buscar_cliente_por_cpf = self.original_buscar

    def test_valor_acima_do_total_vale(self):
        asaas = self.preparar(self.cobrancas(4948.19))
        self.assertIsNotNone(asaas.pagamento_quitado("1", "k", 4497.00))

    def test_desconto_a_vista_de_ate_dez_por_cento_vale(self):
        asaas = self.preparar(self.cobrancas(4047.30))      # 90% de 4497
        self.assertIsNotNone(asaas.pagamento_quitado("1", "k", 4497.00))

    def test_entrada_nao_passa_por_quitacao(self):
        asaas = self.preparar(self.cobrancas(600.00))
        self.assertIsNone(asaas.pagamento_quitado("1", "k", 4497.00))

    def test_parcela_nao_passa_por_quitacao(self):
        asaas = self.preparar(self.cobrancas(533.32, 533.32))
        self.assertIsNone(asaas.pagamento_quitado("1", "k", 4497.00))

    def test_cobranca_em_aberto_nao_vale(self):
        asaas = self.preparar({"data": [{"value": 5000.0, "status": "PENDING",
                                         "description": "X"}], "hasMore": False})
        self.assertIsNone(asaas.pagamento_quitado("1", "k", 4497.00))

    def test_sem_total_do_contrato_nao_chuta(self):
        asaas = self.preparar(self.cobrancas(4948.19))
        self.assertIsNone(asaas.pagamento_quitado("1", "k", 0))
