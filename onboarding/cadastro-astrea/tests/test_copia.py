#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cópia da pasta do cliente para "A - REVISIONAL" / "A - CÍVEL", depois do
caso aberto (decisão dela, 23/09/2026).
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services import copia as P                                 # noqa: E402


class LogFalso(object):
    def __init__(self):
        self.oks, self.alertas = [], []

    def ok(self, mensagem, **_extra):
        self.oks.append(mensagem)

    def alerta(self, mensagem, **_extra):
        self.alertas.append(mensagem)


class ConfigFalsa(object):
    def __init__(self, pasta_revisional, pasta_civel):
        self.pasta_revisional = pasta_revisional
        self.pasta_civel = pasta_civel


class TestPastaDestino(unittest.TestCase):

    def setUp(self):
        self.config = ConfigFalsa(Path("/rev"), Path("/civel"))

    def test_busca_e_apreensao_vai_para_revisional(self):
        self.assertEqual(P.pasta_destino(self.config, "BUSCA E APREENSÃO"), Path("/rev"))

    def test_qualquer_revisional_vai_para_revisional(self):
        for tipo in ("REVISIONAL VEICULAR", "REVISIONAL EMPRÉSTIMO",
                     "REVISIONAL CARTÃO DE CRÉDITO"):
            self.assertEqual(P.pasta_destino(self.config, tipo), Path("/rev"))

    def test_civel_vai_para_civel(self):
        self.assertEqual(P.pasta_destino(self.config, "CÍVEL"), Path("/civel"))

    def test_tipo_desconhecido_nao_copia_as_cegas(self):
        self.assertIsNone(P.pasta_destino(self.config, "NEGOCIAR EXTRAJUDICIAL"))
        self.assertIsNone(P.pasta_destino(self.config, ""))


class TestNomeDaCopia(unittest.TestCase):

    def test_tira_o_prefixo_numero_ok(self):
        self.assertEqual(P.nome_da_copia("1 - OK - FULANO DE TAL", "Fulano de Tal"),
                         "FULANO DE TAL")

    def test_tira_o_prefixo_so_numero(self):
        self.assertEqual(P.nome_da_copia("12 - FULANA SILVA", "Fulana Silva"),
                         "FULANA SILVA")

    def test_sem_prefixo_mantem_o_nome(self):
        self.assertEqual(P.nome_da_copia("FULANO DE TAL", "Fulano de Tal"), "FULANO DE TAL")

    def test_pasta_de_origem_vazia_cai_no_nome_do_cliente(self):
        self.assertEqual(P.nome_da_copia("", "Fulano de Tal"), "Fulano de Tal")


class TestCopiarParaArea(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self._tmp.name)
        self.revisional = self.raiz / "A - REVISIONAL"
        self.civel = self.raiz / "A - CÍVEL"
        self.revisional.mkdir()
        self.civel.mkdir()
        self.config = ConfigFalsa(self.revisional, self.civel)
        self.log = LogFalso()
        self.origem = self.raiz / "PREPARAÇÃO PARA INGRESSO" / "1 - OK - FULANO DE TAL"
        self.origem.mkdir(parents=True)
        (self.origem / "CONTRATO HO Assinado.pdf").write_text("contrato")
        # Pasta completa: a trava de documentação (25/09/2026) não copia
        # pasta sem estes — ver TestTravaNaCopia.
        for nome in ("RG.pdf", "COMPROVANTE DE RESIDÊNCIA.pdf", "CRLV.pdf"):
            (self.origem / nome).write_text("doc")

    def tearDown(self):
        self._tmp.cleanup()

    def test_copia_para_revisional_com_nome_limpo(self):
        ok = P.copiar_para_area(self.origem, "1 - OK - FULANO DE TAL", "Fulano de Tal",
                                "BUSCA E APREENSÃO", self.config, self.log)
        self.assertTrue(ok)
        destino = self.revisional / "FULANO DE TAL"
        self.assertTrue(destino.is_dir())
        self.assertTrue((destino / "CONTRATO HO Assinado.pdf").exists())
        # o original continua intacto — é cópia, não mudança de lugar
        self.assertTrue(self.origem.exists())
        self.assertEqual(self.log.oks, ["Pasta de Fulano de Tal copiada para A - REVISIONAL."])

    def test_copia_para_civel(self):
        ok = P.copiar_para_area(self.origem, "1 - OK - FULANO DE TAL", "Fulano de Tal",
                                "CÍVEL", self.config, self.log)
        self.assertTrue(ok)
        self.assertTrue((self.civel / "FULANO DE TAL").is_dir())

    def test_tipo_sem_area_nao_copia(self):
        ok = P.copiar_para_area(self.origem, "1 - OK - FULANO DE TAL", "Fulano de Tal",
                                "NEGOCIAR EXTRAJUDICIAL", self.config, self.log)
        self.assertFalse(ok)
        self.assertEqual(len(self.log.alertas), 1)

    def test_pasta_de_origem_sumida_nao_estoura(self):
        ok = P.copiar_para_area(self.raiz / "não existe", "X", "Fulano",
                                "CÍVEL", self.config, self.log)
        self.assertFalse(ok)
        self.assertEqual(len(self.log.alertas), 1)

    def test_pasta_ja_existente_no_destino_nao_e_sobrescrita(self):
        """
        Cliente que volta a comprar do escritório pode ter nome batendo com
        uma pasta que já existe lá — decidir sozinha se é a mesma matéria ou
        não é arriscado. Regra dela, 23/09/2026: na dúvida, questionar.
        """
        destino = self.revisional / "FULANO DE TAL"
        destino.mkdir()
        (destino / "arquivo antigo.pdf").write_text("já estava aqui")
        ok = P.copiar_para_area(self.origem, "1 - OK - FULANO DE TAL", "Fulano de Tal",
                                "BUSCA E APREENSÃO", self.config, self.log)
        self.assertFalse(ok)
        self.assertEqual(len(self.log.alertas), 1)
        # não mexeu no que já estava lá
        self.assertTrue((destino / "arquivo antigo.pdf").exists())
        self.assertFalse((destino / "CONTRATO HO Assinado.pdf").exists())


class TestMarcarPastaOk(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _criar(self, nome):
        pasta = self.raiz / nome
        pasta.mkdir()
        return pasta

    def test_insere_ok_depois_do_numero(self):
        pasta = self._criar("15 - FULANO DE TAL")
        novo = P.marcar_pasta_ok(pasta)
        self.assertEqual(novo.name, "15 - OK - FULANO DE TAL")
        self.assertTrue(novo.exists())
        self.assertFalse(pasta.exists())

    def test_sem_numero_usa_01_ok(self):
        pasta = self._criar("FULANO DE TAL")
        novo = P.marcar_pasta_ok(pasta)
        self.assertEqual(novo.name, "01 - OK - FULANO DE TAL")

    def test_ja_marcada_nao_mexe(self):
        pasta = self._criar("01 - OK - FULANO DE TAL")
        novo = P.marcar_pasta_ok(pasta)
        self.assertEqual(novo, pasta)
        self.assertTrue(pasta.exists())

    def test_nao_sobrescreve_se_ja_existir_pasta_com_o_novo_nome(self):
        pasta = self._criar("15 - FULANO DE TAL")
        (self.raiz / "15 - OK - FULANO DE TAL").mkdir()
        novo = P.marcar_pasta_ok(pasta)
        self.assertEqual(novo, pasta)
        self.assertTrue(pasta.exists(), "não pode apagar a pasta original nesse caso")


if __name__ == "__main__":
    unittest.main()


class TestTravaNaCopia(unittest.TestCase):
    """Pasta sem a documentação completa não vai para o jurídico (25/09/2026)."""

    def test_pasta_incompleta_nao_e_copiada(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            revisional, civel = raiz / "A - REVISIONAL", raiz / "A - CÍVEL"
            revisional.mkdir()
            civel.mkdir()
            origem = raiz / "PREPARAÇÃO PARA INGRESSO" / "2 - SICRANO"
            origem.mkdir(parents=True)
            for nome in ("CONTRATO HO Assinado.pdf", "RG.pdf", "CRLV.pdf"):
                (origem / nome).write_text("doc")
            log = LogFalso()
            ok = P.copiar_para_area(origem, "2 - SICRANO", "Sicrano",
                                    "BUSCA E APREENSÃO",
                                    ConfigFalsa(revisional, civel), log)
            self.assertFalse(ok)
            self.assertFalse((revisional / "SICRANO").exists())
            self.assertIn("DOCUMENTAÇÃO INCOMPLETA", log.alertas[0])
