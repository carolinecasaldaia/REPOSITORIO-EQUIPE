#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trava de documentação: sem RG/CNH, comprovante de residência e (veículo)
CRLV, nada anda (decisão dela, 25/09/2026).
Os nomes de arquivo abaixo são os que aparecem nas pastas reais.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.validators import documentacao as T                        # noqa: E402

BA = "BUSCA E APREENSÃO"


def pasta_com(raiz, nome, arquivos):
    pasta = Path(raiz) / nome
    for relativo in arquivos:
        caminho = pasta / relativo
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(b"%PDF-1.4")
    return pasta


COMPLETA = ["DOC CLIENTE/CNH-e.pdf (30).pdf", "DOC CLIENTE/C DE RESIDÊNCIA.pdf",
            "DOC CLIENTE/CONTRATO DE FINANCIAMENTO.pdf",
            "DOC CLIENTE/CRLV-e_1929022071179BD1667.pdf.pdf",
            "CONTRATO HO/Contrato HO Assinado.pdf"]


class TestFaltantes(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_pasta_completa_libera(self):
        pasta = pasta_com(self.raiz, "01 - FULANO", COMPLETA)
        self.assertEqual(T.faltantes(pasta, BA), [])

    def test_sem_contrato_bancario_libera(self):
        # Contrato bancário saiu da lista (decisão dela, 25/09/2026).
        arquivos = [a for a in COMPLETA if "FINANCIAMENTO" not in a]
        pasta = pasta_com(self.raiz, "ADONIAS", arquivos)
        self.assertEqual(T.faltantes(pasta, BA), [])

    def test_rg_ou_identidade_valem_como_cnh(self):
        for nome in ("IDENTIDADE.pdf", "RG FRENTE.jpeg", "CNH_250330_090342.pdf"):
            arquivos = [a for a in COMPLETA if "CNH" not in a] + ["DOC CLIENTE/" + nome]
            pasta = pasta_com(self.raiz, "X " + nome, arquivos)
            self.assertNotIn(T.IDENTIDADE, T.faltantes(pasta, BA), nome)

    def test_cnh_do_responsavel_financeiro_nao_vale(self):
        arquivos = [a for a in COMPLETA if "CNH" not in a]
        arquivos.append("DOC CLIENTE/CNH RESP FINANCEIRO.pdf")
        pasta = pasta_com(self.raiz, "Y", arquivos)
        self.assertEqual(T.faltantes(pasta, BA), [T.IDENTIDADE])

    def test_arquivo_sem_nome_claro_nao_conta(self):
        # Decisão dela: só vale o que o nome do arquivo diz.
        arquivos = [a for a in COMPLETA if "RESID" not in a]
        arquivos.append("DOC CLIENTE/fatura-cemig-0925.pdf.jpeg")
        pasta = pasta_com(self.raiz, "V", arquivos)
        self.assertEqual(T.faltantes(pasta, BA), [T.COMPROVANTE])

    def test_crlv_so_em_caso_de_veiculo(self):
        arquivos = [a for a in COMPLETA if "CRLV" not in a]
        pasta = pasta_com(self.raiz, "U", arquivos)
        self.assertEqual(T.faltantes(pasta, BA), [T.CRLV])
        self.assertEqual(T.faltantes(pasta, "REVISIONAL VEICULAR"), [T.CRLV])
        self.assertEqual(T.faltantes(pasta, "REVISIONAL EMPRÉSTIMO"), [])
        self.assertEqual(T.faltantes(pasta, "CÍVEL"), [])
        # Tipo não identificado: exige, por segurança.
        self.assertEqual(T.faltantes(pasta, ""), [T.CRLV])

    def test_nome_da_pasta_do_cliente_nao_conta_como_documento(self):
        arquivos = [a for a in COMPLETA if "CRLV" not in a]
        pasta = pasta_com(self.raiz, "14 - MARIANA - DOCUMENTO DO VEICULO", arquivos)
        self.assertEqual(T.faltantes(pasta, BA), [T.CRLV])

    def test_docx_nao_conta(self):
        arquivos = [a for a in COMPLETA if "CRLV" not in a]
        arquivos.append("CRLV.docx")
        pasta = pasta_com(self.raiz, "T", arquivos)
        self.assertEqual(T.faltantes(pasta, BA), [T.CRLV])

    def test_pasta_vazia_falta_tudo(self):
        pasta = pasta_com(self.raiz, "VAZIA", [])
        pasta.mkdir(parents=True, exist_ok=True)
        self.assertEqual(T.faltantes(pasta, BA),
                         [T.IDENTIDADE, T.COMPROVANTE, T.CRLV])


if __name__ == "__main__":
    unittest.main()


class TestDeclaracaoEhComprovante(unittest.TestCase):
    """Declaração de residência assinada vale como comprovante (20/10/2026)."""

    def pasta_com(self, *arquivos):
        import tempfile
        from pathlib import Path
        base = Path(tempfile.mkdtemp())
        (base / "DOC CLIENTE").mkdir()
        (base / "DOC ESCRITÓRIO").mkdir()
        for arq in arquivos:
            caminho = base / arq
            caminho.parent.mkdir(parents=True, exist_ok=True)
            caminho.write_bytes(b"%PDF-1.4 fake")
        return base

    def test_declaracao_substitui_o_comprovante(self):
        pasta = self.pasta_com("DOC CLIENTE/CNH.pdf", "DOC CLIENTE/CRLV.pdf",
                               "DOC ESCRITÓRIO/Declaracao de Residencia Assinada.pdf")
        self.assertEqual(T.faltantes(pasta, "BUSCA E APREENSÃO"), [])

    def test_sem_nenhum_dos_dois_continua_faltando(self):
        pasta = self.pasta_com("DOC CLIENTE/CNH.pdf", "DOC CLIENTE/CRLV.pdf")
        self.assertEqual(T.faltantes(pasta, "BUSCA E APREENSÃO"),
                         [T.COMPROVANTE])

    def test_declaracao_de_hipossuficiencia_nao_serve(self):
        pasta = self.pasta_com("DOC CLIENTE/CNH.pdf", "DOC CLIENTE/CRLV.pdf",
                               "DOC ESCRITÓRIO/Declaracao de Hipo Assinada.pdf")
        self.assertEqual(T.faltantes(pasta, "BUSCA E APREENSÃO"),
                         [T.COMPROVANTE])


class TestLiberacaoManual(unittest.TestCase):
    """
    Liberação manual da trava (20/10/2026, Angela): cliente com prazo correndo
    passa mesmo faltando documento, e o que falta continua registrado.
    """

    def tabela(self, texto):
        import tempfile, os as _os
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as arq:
            arq.write(texto)
        tabela = T.ler_liberacoes(arq.name)
        _os.remove(arq.name)
        return tabela

    def test_le_nome_e_motivo(self):
        tabela = self.tabela("# nota\nANGELA CAVALCANTE DE ALMEIDA = prazo correndo\n")
        self.assertEqual(tabela["ANGELA CAVALCANTE DE ALMEIDA"], "prazo correndo")

    def test_sem_arquivo_ninguem_liberado(self):
        self.assertEqual(T.ler_liberacoes("/nao/existe.txt"), {})

    def test_liberado_ignora_acento_e_caixa(self):
        tabela = {"ANGELA CAVALCANTE DE ALMEIDA": "prazo"}
        self.assertEqual(T.liberado("Ângela Cavalcante de Almeida",
                                    liberacoes=tabela), "prazo")

    def test_quem_nao_esta_na_lista_nao_e_liberado(self):
        tabela = {"ANGELA CAVALCANTE DE ALMEIDA": "prazo"}
        self.assertEqual(T.liberado("Outro Cliente", liberacoes=tabela), "")

    def test_liberacao_nao_apaga_o_que_falta(self):
        """A trava é contornada, mas `faltantes` continua dizendo a verdade."""
        import tempfile
        from pathlib import Path
        base = Path(tempfile.mkdtemp())
        (base / "DOC CLIENTE").mkdir()
        (base / "DOC CLIENTE" / "CNH.pdf").write_bytes(b"%PDF fake")
        self.assertIn(T.CRLV, T.faltantes(base, "BUSCA E APREENSÃO"))
