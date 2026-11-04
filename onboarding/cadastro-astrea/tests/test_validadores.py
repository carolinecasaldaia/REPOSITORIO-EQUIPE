#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validação de CPF, CNPJ, e-mail, telefone, CEP e nome."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.validators import campos as V   # noqa: E402


class TestCPF(unittest.TestCase):

    def test_cpf_valido_com_pontuacao(self):
        valor, ok, motivo = V.validar_cpf("529.982.247-25")
        self.assertTrue(ok, motivo)
        self.assertEqual(valor, "529.982.247-25")

    def test_cpf_valido_sem_pontuacao_e_com_espacos(self):
        # O PDF costuma devolver "1 22.794.664-30".
        valor, ok, _ = V.validar_cpf(" 529 982 247 25 ")
        self.assertTrue(ok)
        self.assertEqual(valor, "529.982.247-25")

    def test_cpf_digito_verificador_errado(self):
        _, ok, motivo = V.validar_cpf("529.982.247-26")
        self.assertFalse(ok)
        self.assertIn("dígito verificador", motivo)

    def test_cpf_todos_digitos_iguais(self):
        _, ok, motivo = V.validar_cpf("111.111.111-11")
        self.assertFalse(ok)
        self.assertIn("iguais", motivo)

    def test_cpf_quantidade_errada(self):
        _, ok, motivo = V.validar_cpf("529.982.247")
        self.assertFalse(ok)
        self.assertIn("11 dígitos", motivo)

    def test_cpf_ausente(self):
        valor, ok, motivo = V.validar_cpf("")
        self.assertFalse(ok)
        self.assertEqual(valor, "")
        self.assertIn("não informado", motivo)


class TestCNPJ(unittest.TestCase):

    def test_cnpj_valido(self):
        valor, ok, motivo = V.validar_cnpj("58.173.643/0001-17")
        self.assertTrue(ok, motivo)
        self.assertEqual(valor, "58.173.643/0001-17")

    def test_cnpj_invalido(self):
        _, ok, _ = V.validar_cnpj("58.173.643/0001-18")
        self.assertFalse(ok)

    def test_documento_escolhe_pelo_tamanho(self):
        _, ok, _, tipo = V.validar_documento("58.173.643/0001-17")
        self.assertTrue(ok)
        self.assertEqual(tipo, "CNPJ")
        _, ok, _, tipo = V.validar_documento("529.982.247-25")
        self.assertEqual(tipo, "CPF")


class TestContato(unittest.TestCase):

    def test_email_valido_normaliza_caixa(self):
        valor, ok, _ = V.validar_email("  Fulano@Gmail.COM ")
        self.assertTrue(ok)
        self.assertEqual(valor, "fulano@gmail.com")

    def test_email_invalido(self):
        _, ok, motivo = V.validar_email("fulano@gmail")
        self.assertFalse(ok)
        self.assertIn("formato", motivo)

    def test_telefone_celular_com_ruido_do_pdf(self):
        valor, ok, _ = V.validar_telefone("( 82) 99185 -5820")
        self.assertTrue(ok)
        self.assertEqual(valor, "+55 82 99185-5820")

    def test_telefone_fixo_dez_digitos(self):
        valor, ok, _ = V.validar_telefone("(73) 9868-2920")
        self.assertTrue(ok)
        self.assertEqual(valor, "+55 73 9868-2920")

    def test_telefone_ja_com_ddi(self):
        valor, ok, _ = V.validar_telefone("+55 (82) 99188-6196")
        self.assertTrue(ok)
        self.assertEqual(valor, "+55 82 99188-6196")

    def test_telefone_curto_demais(self):
        _, ok, motivo = V.validar_telefone("9918")
        self.assertFalse(ok)
        self.assertIn("dígitos", motivo)

    def test_cep_com_espaco_intruso(self):
        valor, ok, _ = V.validar_cep("57038 -637")
        self.assertTrue(ok)
        self.assertEqual(valor, "57038-637")

    def test_uf_desconhecida(self):
        _, ok, motivo = V.validar_uf("XX")
        self.assertFalse(ok)
        self.assertIn("desconhecida", motivo)


class TestNome(unittest.TestCase):

    def test_remove_espacos_duplicados_sem_alterar_grafia(self):
        valor, ok, _ = V.validar_nome("  ANDERSON   LOPES  DA SILVA ")
        self.assertTrue(ok)
        self.assertEqual(valor, "ANDERSON LOPES DA SILVA")

    def test_nao_corrige_grafia_do_nome(self):
        # "ANDESON" é como está na pasta; o validador não pode "consertar".
        valor, ok, _ = V.validar_nome("ANDESON LOPES DA SILVA")
        self.assertTrue(ok)
        self.assertEqual(valor, "ANDESON LOPES DA SILVA")

    def test_nome_sem_sobrenome_reprovado(self):
        _, ok, motivo = V.validar_nome("Denise")
        self.assertFalse(ok)
        self.assertIn("sobrenome", motivo)

    def test_nome_com_numero_reprovado(self):
        _, ok, motivo = V.validar_nome("Fulano 123 Silva")
        self.assertFalse(ok)
        self.assertIn("números", motivo)


class TestEstadoCivil(unittest.TestCase):

    def test_reconhece_variacoes(self):
        for entrada, esperado in (("solteira", "Solteiro(a)"),
                                  ("casado", "Casado(a)"),
                                  ("união estável", "União estável"),
                                  ("convivente em união estável", "União estável"),
                                  ("divorciada", "Divorciado(a)")):
            valor, reconhecido = V.normalizar_estado_civil(entrada)
            self.assertTrue(reconhecido, entrada)
            self.assertEqual(valor, esperado)

    def test_nao_reconhecido_devolve_original(self):
        valor, reconhecido = V.normalizar_estado_civil("amasiado")
        self.assertFalse(reconhecido)
        self.assertEqual(valor, "amasiado")


class TestGravacaoDeSenha(unittest.TestCase):
    """
    A senha vai para o .env e tem que voltar idêntica.

    Senha de sistema jurídico costuma ter símbolo, e uma senha que volta
    truncada faria a automação falhar o login sem ninguém entender por quê.
    """

    def roundtrip(self, senha):
        import tempfile
        from pathlib import Path as P
        from src.config import settings as S
        arquivo = P(tempfile.mkdtemp()) / ".env"
        arquivo.write_text("ASTREA_SENHA=%s\n" % S.escapar_para_env(senha),
                           encoding="utf-8")
        return S._ler_env(arquivo).get("ASTREA_SENHA")

    def test_senha_simples(self):
        self.assertEqual(self.roundtrip("SenhaBoba123"), "SenhaBoba123")

    def test_senha_com_simbolos(self):
        for senha in ('S3nh@ #forte!', 'a"b\\c', "com espaço no fim ",
                      "acentuação~ç", "=igual=", "#comentario"):
            self.assertEqual(self.roundtrip(senha), senha,
                             "quebrou com: %r" % senha)


class TestJanelaDeSenha(unittest.TestCase):
    """
    Leitura da resposta da janela do macOS.

    O osascript devolve 'button returned:OK, text returned:xxx' — e em algumas
    versões na ordem inversa. Errar isso significaria gravar uma senha com lixo
    grudado e o login falhar sem explicação.
    """

    def responder(self, saida, returncode=0):
        import executar
        original = executar.subprocess.run

        class Resposta(object):
            def __init__(self):
                self.returncode = returncode
                self.stdout = saida
                self.stderr = ""

        executar.subprocess.run = lambda *a, **k: Resposta()
        try:
            return executar._perguntar_em_janela("Senha:", oculto=True)
        finally:
            executar.subprocess.run = original

    def test_ordem_normal(self):
        self.assertEqual(
            self.responder("button returned:OK, text returned:S3nh@!"), "S3nh@!")

    def test_ordem_invertida(self):
        self.assertEqual(
            self.responder("text returned:S3nh@!, button returned:OK"), "S3nh@!")

    def test_senha_com_virgula(self):
        self.assertEqual(
            self.responder("button returned:OK, text returned:a,b,c"), "a,b,c")

    def test_cancelou(self):
        self.assertIsNone(self.responder("", returncode=1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
