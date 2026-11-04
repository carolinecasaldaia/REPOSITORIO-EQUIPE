#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR e leitura do banco no mandado.

O caso que motivou tudo: em 01/09/2026 a Joice ficou sem onboarding porque o
banco dela não estava em lugar nenhum legível — só no MANDADO, que é
digitalizado. Ela teve que digitar "Santander" na mão. Com o OCR do macOS, o
mandado passou a ser lido e o banco sai sozinho.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import banco, ocr                                          # noqa: E402

MANDADO_SC = """
ESTADO DE SANTA CATARINA PODER JUDICIÁRIO Vara Estadual de Direito Bancário
BUSCA E APREENSÃO EM ALIENAÇÃO FIDUCIÁRIA N° 5092826-32.2026.8.24.0930/SC
AUTOR: SANTANDER SOCIEDADE DE CREDITO, FINANCIAMENTO E INVESTIMENTO S.A.
RÉU: JOICE LEVANDOWSKI
BEM: Marca: VW - VOLKSWAGEN Modelo: GOLF SPORTLINE 1.6 Placa: MIY3E40
"""

MANDADO_BA = """
PODER JUDICIÁRIO DO ESTADO DA BAHIA
AÇÃO DE BUSCA E APREENSÃO EM ALIENAÇÃO FIDUCIÁRIA
REQUERENTE: BANCO PSA FINANCE BRASIL LTDA
REQUERIDO: ADESON SOUZA DE ALMEIDA
"""

MANDADO_SEM_BANCO = """
PODER JUDICIÁRIO. AÇÃO DE COBRANÇA.
AUTOR: MARIA JOSE DE ALMEIDA SANTOS
RÉU: FULANO DE TAL
"""


class TestBancoNoMandado(unittest.TestCase):

    def test_autor_de_santa_catarina(self):
        self.assertEqual(banco.identificar_no_mandado(MANDADO_SC), "Banco Santander")

    def test_requerente_da_bahia(self):
        """Cada tribunal usa um rótulo: AUTOR em SC, REQUERENTE na BA."""
        self.assertEqual(banco.identificar_no_mandado(MANDADO_BA),
                         "Banco PSA Finance Brasil")

    def test_pessoa_fisica_no_polo_ativo_nao_vira_banco(self):
        """Cobrança movida por pessoa não pode virar 'banco adverso'."""
        self.assertEqual(banco.identificar_no_mandado(MANDADO_SEM_BANCO), "")

    def test_documento_que_nao_e_de_busca_e_apreensao_e_ignorado(self):
        self.assertEqual(banco.identificar_no_mandado(
            "AUTOR: BANCO BRADESCO S.A. AÇÃO MONITÓRIA"), "")

    def test_mandado_entra_na_lista_de_arquivos_procurados(self):
        import re
        self.assertTrue(re.search(banco.ARQUIVOS_PROVAVEIS, "MANDADO"))


class TestOcr(unittest.TestCase):

    def test_arquivo_inexistente_devolve_vazio(self):
        self.assertEqual(ocr.ler(Path("/nao/existe/arquivo.pdf")), "")

    def test_sem_o_programa_instalado_nao_estoura(self):
        original = ocr.PROGRAMA
        ocr.PROGRAMA = Path("/nao/existe/ler-pdf")
        try:
            self.assertFalse(ocr.disponivel())
            self.assertEqual(ocr.ler(Path(__file__)), "")
        finally:
            ocr.PROGRAMA = original


if __name__ == "__main__":
    unittest.main()


class TestPdfComSenha(unittest.TestCase):
    """
    PDF protegido: senha vazia e senha escrita no nome do arquivo.

    Autorizado por ela em 08/09/2026, depois que apareceram dois contratos de
    banco protegidos — um deles chamado "CONTRATO, SENHA: 448.pdf".
    """

    def _senha(self, nome):
        from src import pdf_protegido
        return pdf_protegido.senha_no_nome(nome)

    def test_le_a_senha_escrita_no_nome(self):
        self.assertEqual(self._senha("CONTRATO, SENHA: 448.pdf"), "448")

    def test_aceita_outras_grafias(self):
        self.assertEqual(self._senha("contrato senha 1234.pdf"), "1234")
        self.assertEqual(self._senha("CONTRATO-SENHA=abc12.pdf"), "abc12")

    def test_nome_sem_senha_nao_inventa(self):
        self.assertEqual(self._senha("CONTRATO 14774.pdf"), "")

    def test_a_senha_vazia_vem_primeiro(self):
        """A maioria dos PDFs protegidos abre sem senha nenhuma."""
        from src import pdf_protegido
        self.assertEqual(pdf_protegido.senhas_possiveis("CONTRATO, SENHA: 448.pdf"),
                         ["", "448"])

    def test_nao_tenta_senha_que_nao_foi_entregue(self):
        """
        Nada de lista de senhas comuns, CPF ou data de nascimento: isso seria
        quebrar a proteção, não ler o que o cliente entregou aberto.
        """
        from src import pdf_protegido
        self.assertEqual(pdf_protegido.senhas_possiveis("CONTRATO 14774.pdf"), [""])


class TestNomeDeEmpresa(unittest.TestCase):
    """O nome lido do mandado vai para o onboarding que o cliente recebe."""

    def test_fundo_da_gisleine_sai_inteiro_e_legivel(self):
        self.assertEqual(
            banco.nome_de_empresa("COOPERA FUNDO DE INVESTIMENTO EM DIREITOS "
                                  "CREDITORIOS - RESPONSABILIDADE LIMITADA"),
            "Coopera Fundo de Investimento em Direitos Creditorios")

    def test_particula_no_comeco_continua_maiuscula(self):
        self.assertEqual(banco.nome_de_empresa("DE PAULA FINANCEIRA S/A"),
                         "De Paula Financeira S/A")

    def test_forma_juridica_em_maiusculas(self):
        self.assertEqual(banco.nome_de_empresa("MOVA SOCIEDADE DE EMPRESTIMO ENTRE PESSOAS S.A."),
                         "Mova Sociedade de Emprestimo Entre Pessoas S.A")

    def test_mandado_com_fundo_no_polo_ativo(self):
        mandado = ("BUSCA E APREENSÃO EM ALIENAÇÃO FIDUCIÁRIA AUTOR: COOPERA FUNDO DE "
                   "INVESTIMENTO EM DIREITOS CREDITORIOS - RESPONSABILIDADE LIMITADA "
                   "RÉU: GISLEINE PEREIRA JARDIM")
        self.assertEqual(banco.identificar_no_mandado(mandado),
                         "Coopera Fundo de Investimento em Direitos Creditorios")
