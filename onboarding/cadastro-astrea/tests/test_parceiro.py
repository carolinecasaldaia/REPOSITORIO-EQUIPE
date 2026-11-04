#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Assunto do parceiro não entra na automação do Astrea (regra de 02/10/2026).

"Adicional de insalubridade e reflexos" é tocado pelo escritório parceiro:
não cadastra contato e não abre caso. O contrato continua sendo arquivado e o
onboarding gerado — isso é da automação do Autentique, não desta.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import controle as St                            # noqa: E402
from src.validators import parceiro                                # noqa: E402
from tests.test_extrator import CABECALHO, COMPLETO                # noqa: E402
from tests.test_fluxo import AstreaFalso, BaseFluxo                # noqa: E402

RODAPE_PARCEIRO = (" Cláusula 1ª. Advogada contratada obriga-se, diante de "
                   "mandato judicial que lhe foi outorgado, para realizar o "
                   "ingresso da Ação Trabalhista para cobrança de adicional "
                   "de insalubridade e reflexos, a prestar seus serviços "
                   "jurídicos profissionais.")


class TestReconhecimento(unittest.TestCase):

    def test_reconhece_com_e_sem_acento_e_maiuscula(self):
        for objeto in ("adicional de insalubridade e reflexos",
                       "ADICIONAL DE INSALUBRIDADE E REFLEXOS",
                       "Cobranca de Insalubridade e reflexos"):
            self.assertTrue(parceiro.e_do_parceiro(objeto), objeto)

    def test_nao_pega_o_que_e_nosso(self):
        for objeto in ("Ação Revisional em desfavor do Banco Santander",
                       "Ação de Busca e Apreensão", ""):
            self.assertFalse(parceiro.e_do_parceiro(objeto), objeto)

    def test_motivo_diz_o_assunto(self):
        self.assertIn("insalubridade",
                      parceiro.motivo("adicional de insalubridade e reflexos"))


class TestFluxoDoParceiro(BaseFluxo):

    def setUp(self):
        BaseFluxo.setUp(self)
        self.rodar(AstreaFalso(self.config, self.log))      # ativa a automação

    def criar_do_parceiro(self, nome):
        pasta = self.criar_cliente(nome)
        arquivo = pasta / "CONTRATO HO" / "Contrato HO Assinado.pdf"
        self.textos[str(arquivo)] = CABECALHO + COMPLETO + RODAPE_PARCEIRO
        return pasta

    def test_nao_cadastra_e_marca_como_do_parceiro(self):
        self.criar_do_parceiro("90 - INSALUBRIDADE")
        astrea = AstreaFalso(self.config, self.log)
        resumo = self.rodar(astrea)
        registro = self.registro("90 - INSALUBRIDADE")
        self.assertEqual(astrea.cadastrados, [],
                         "cliente do parceiro não pode ser cadastrado no Astrea")
        self.assertEqual(astrea.casos, [])
        self.assertEqual(registro["status"], St.PARCEIRO)
        self.assertEqual(resumo.parceiros, 1)
        self.assertEqual(resumo.pendentes, 0, "não é pendência do comercial")
        self.assertEqual(resumo.erros, 0)

    def test_nao_volta_na_rodada_seguinte(self):
        self.criar_do_parceiro("91 - INSALUBRIDADE DE NOVO")
        self.rodar(AstreaFalso(self.config, self.log))
        astrea = AstreaFalso(self.config, self.log)
        resumo = self.rodar(astrea)
        self.assertEqual(astrea.cadastrados, [])
        self.assertEqual(resumo.parceiros, 0, "status definitivo não se repete")

    def test_sem_documentos_pessoais_tambem_e_do_parceiro(self):
        """A trava de documentação não pode falar antes: o cliente não é nosso."""
        pasta = self.criar_cliente("92 - SEM DOCS", com_documentos=False)
        arquivo = pasta / "CONTRATO HO" / "Contrato HO Assinado.pdf"
        self.textos[str(arquivo)] = CABECALHO + COMPLETO + RODAPE_PARCEIRO
        resumo = self.rodar(AstreaFalso(self.config, self.log))
        self.assertEqual(self.registro("92 - SEM DOCS")["status"], St.PARCEIRO)
        self.assertEqual(resumo.pendentes, 0)

    def test_cliente_normal_segue_cadastrando(self):
        self.criar_cliente("93 - NOSSO")
        astrea = AstreaFalso(self.config, self.log)
        resumo = self.rodar(astrea)
        self.assertEqual(len(astrea.cadastrados), 1)
        self.assertEqual(resumo.parceiros, 0)


if __name__ == "__main__":
    unittest.main()
