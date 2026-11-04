#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Contrato sem CPF: aproveitar o da CNH/RG da pasta (regra de 14/10/2026).

Nasceu da Priscila: contrato de honorários sem o CPF, CNH na pasta com o
número legível por OCR, e o cliente travado como "CPF não localizado".
Aproveitar é bom; aproveitar errado é muito pior do que a pendência — por
isso os testes de recusa são a maior parte deste arquivo.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import controle as St                            # noqa: E402
from tests.test_extrator import SEM_CPF                           # noqa: E402
from tests.test_fluxo import AstreaFalso, BaseFluxo               # noqa: E402

# Como o OCR entrega uma CNH: tudo em uma linha, números soltos no meio.
CNH = ("VALIDA EM TODO O TERRITORIO NACIONAL 2226406189 CARTEIRA NACIONAL DE "
       "HABILITACAO NOME ANDERSON LOPES DA SILVA DOC. IDENTIDADE 34048615 "
       "SSP/AL CPF - 529.982.247-25 DATA NASCIMENTO 13/11/1983 N REGISTRO "
       "05182475100 VALIDADE 15/07/2031")


class TestCpfDaIdentidade(BaseFluxo):

    def setUp(self):
        BaseFluxo.setUp(self)
        self.rodar(AstreaFalso(self.config, self.log))      # ativa a automação

    def criar_com_cnh(self, nome, texto_cnh=CNH, texto_contrato=SEM_CPF):
        pasta = self.criar_cliente(nome, texto_contrato=texto_contrato)
        cnh = pasta / "DOC CLIENTE" / "CNH.pdf"
        self.textos[str(cnh)] = texto_cnh
        return pasta

    # -- aproveita -------------------------------------------------------

    def test_cadastra_com_o_cpf_lido_da_cnh(self):
        self.criar_com_cnh("20 - CPF NA CNH")
        astrea = AstreaFalso(self.config, self.log)
        self.rodar(astrea)
        registro = self.registro("20 - CPF NA CNH")
        self.assertEqual(registro["status"], St.CADASTRADO)
        self.assertEqual(registro["cpf_cnpj"], "529.982.247-25")
        self.assertEqual(len(astrea.cadastrados), 1)

    def test_avisa_que_o_cpf_nao_veio_do_contrato(self):
        self.criar_com_cnh("21 - AVISO")
        self.rodar(AstreaFalso(self.config, self.log))
        dados = self.registro("21 - AVISO")["dados_json"] or ""
        self.assertIn("lido de 'CNH.pdf'", dados)

    def test_contrato_com_cpf_nao_consulta_a_cnh(self):
        """Quem manda é o contrato assinado; a CNH é só o reforço."""
        pasta = self.criar_cliente("22 - CONTRATO MANDA")   # COMPLETO tem CPF
        cnh = pasta / "DOC CLIENTE" / "CNH.pdf"
        self.textos[str(cnh)] = CNH.replace("529.982.247-25", "111.444.777-35")
        self.rodar(AstreaFalso(self.config, self.log))
        self.assertEqual(self.registro("22 - CONTRATO MANDA")["cpf_cnpj"],
                         "529.982.247-25")

    # -- recusa ----------------------------------------------------------

    def test_cnh_de_outra_pessoa_nao_serve(self):
        self.criar_com_cnh("23 - CNH DE TERCEIRO",
                           texto_cnh=CNH.replace("ANDERSON LOPES DA SILVA",
                                                 "JOSE PEREIRA DOS SANTOS"))
        astrea = AstreaFalso(self.config, self.log)
        self.rodar(astrea)
        self.assertEqual(self.registro("23 - CNH DE TERCEIRO")["status"],
                         St.PENDENTE)
        self.assertEqual(astrea.cadastrados, [])

    def test_numero_solto_sem_rotulo_nao_serve(self):
        """Sem o rótulo CPF, nº de registro da CNH passaria por CPF."""
        self.criar_com_cnh("24 - SEM ROTULO",
                           texto_cnh=CNH.replace("CPF - 529.982.247-25",
                                                 "529.982.247-25"))
        self.rodar(AstreaFalso(self.config, self.log))
        self.assertEqual(self.registro("24 - SEM ROTULO")["status"], St.PENDENTE)

    def test_digito_verificador_errado_nao_serve(self):
        self.criar_com_cnh("25 - DIGITO ERRADO",
                           texto_cnh=CNH.replace("529.982.247-25",
                                                 "529.982.247-99"))
        self.rodar(AstreaFalso(self.config, self.log))
        self.assertEqual(self.registro("25 - DIGITO ERRADO")["status"],
                         St.PENDENTE)

    def test_dois_cpfs_na_identidade_fica_pendente(self):
        self.criar_com_cnh("26 - DOIS CPFS",
                           texto_cnh=CNH + " CPF 111.444.777-35")
        self.rodar(AstreaFalso(self.config, self.log))
        registro = self.registro("26 - DOIS CPFS")
        self.assertEqual(registro["status"], St.PENDENTE)
        self.assertIn("mais de um CPF", registro["dados_json"] or "")

    def test_sem_cnh_na_pasta_continua_pendente(self):
        self.criar_cliente("27 - SEM CNH", texto_contrato=SEM_CPF)
        self.rodar(AstreaFalso(self.config, self.log))
        self.assertEqual(self.registro("27 - SEM CNH")["status"], St.PENDENTE)


if __name__ == "__main__":
    unittest.main()
