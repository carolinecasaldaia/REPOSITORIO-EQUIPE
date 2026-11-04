#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extração da qualificação do contrato de honorários.

Os textos abaixo reproduzem, com CPFs fictícios válidos, as variações reais
encontradas nas pastas de 2026: com e sem RG, com e sem complemento, com
Cliente Responsável, com os espaços intrusos que o extrator de PDF produz.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.extractors import contrato_ho as C   # noqa: E402

CABECALHO = (
    "CONTRATO DE PRESTAÇÃO DE SERVIÇOS ADVOCATÍCIOS Pelo presente Instrumento "
    "Particular que entre si fazem, de um lado, como Advogada Contratada, "
    "CAROLINE MACEDO SOCIEDADE INDIVIDUAL DE ADVOCACIA, pessoa jurídica de "
    "direito privado com CNPJ sob o nº 58.173.643/0001-17, inscrita na OAB/AL, "
    "sob o nº 2400582, com endereço profissional na Rua Dr. Luís Pontes de "
    "Miranda, nº 36, Centro – Maceió – AL, CEP: 57.020-140 e do outro lado, ")

RODAPE = (" Cláusula 1ª. Advogada contratada obriga-se, diante de mandato "
          "judicial que lhe foi outorgado, para realizar o ingresso da Ação "
          "Revisional em desfavor do Banco Santander, referente ao contrato de "
          "financiamento do veículo HONDA/XRE 300, placa ABC1D23, a prestar "
          "seus serviços jurídicos profissionais.")

COMPLETO = (
    "como Cliente Contratante ANDERSON LOPES DA SILVA, brasileiro, casado, "
    "vigilante, portador do RG n°: 99001053514 SSP/ AL inscrito no CPF de nº "
    "529.982.247-25, residente e domiciliado na Rua Bom Jesus, 27 A – Benedito "
    "Bentes – Maceió/AL – CEP: 57084-818, endereço eletrônico: "
    "anderson@gmail.com e contato telefônico (82) 99188-6196 mediante as "
    "cláusulas e condições seguintes.")

COM_COMPLEMENTO = (
    "como Cliente Contratante EDGARD JOSE SANTOS BARROS OLIVEIRA , brasileiro, "
    "convivente em união estável, aeronauta, portador do RG sob o nº "
    "2001005012877 SSP/AL, inscrito no CPF de nº 529.982.247-25, residente e "
    "domiciliado na Rua Vista do Atlântico, nº 105, QD B – Jacarecica – "
    "Maceió/AL – CEP: 57038 -637, endereço eletrônico edgard@hotmail.com e "
    "contato telefônico (82) 99179 -7759, mediante as cláusulas e condições "
    "seguintes.")

SEM_RG_COM_RESPONSAVEL = (
    "como Cliente Contratante ERICA DA SILVA SANTOS, brasileira, união estável, "
    "vendedora, inscrita no CPF de nº 529.982.247-25, residente e domiciliada na "
    "Rua Dr Cleantho De Moura Rizzo, nº 122 – QD F casa 28 – Cidade "
    "Universitária – Maceió/AL – CEP: 57073-161, endereço eletrônico : "
    "erica@gmail.com e contato telefônico ( 82) 99185-5820, e como cliente "
    "responsável: LUCAS SILVA DE CASTRO, brasileiro, união estável, motorista, "
    "inscrito no CPF de n° 1 11.444.777-35, residente e domiciliado na Rua Dr "
    "Cleantho De Moura Rizzo, nº 122 – QD F casa 28 – Cidade Universitária – "
    "Maceió/AL – CEP: 57073-161, endereço eletrônico: lucas@gmail.com e contato "
    "telefônico: (82) 99644-9858 mediante as cláusulas e condições seguintes.")

CPF_INVALIDO = COMPLETO.replace("529.982.247-25", "529.982.247-26")
SEM_CPF = COMPLETO.replace("inscrito no CPF de nº 529.982.247-25, ", "")

# Segundo cliente, com CPF válido diferente — para testar duas pessoas
# distintas na mesma rodada sem cair na regra de duplicidade.
OUTRO_CLIENTE = (COMPLETO
                 .replace("ANDERSON LOPES DA SILVA", "MARIA APARECIDA DOS SANTOS")
                 .replace("529.982.247-25", "111.444.777-35")
                 .replace("anderson@gmail.com", "maria@gmail.com"))


def texto(miolo):
    return CABECALHO + miolo + RODAPE


class TestQualificacao(unittest.TestCase):

    def bloco(self, miolo):
        return C._recortar(texto(miolo), C._INICIO_CONTRATANTE)

    def test_contrato_completo(self):
        pessoa = C.parse_bloco(self.bloco(COMPLETO), "contratante", "teste.pdf")
        self.assertEqual(pessoa.nome.valor, "ANDERSON LOPES DA SILVA")
        self.assertEqual(pessoa.nacionalidade.valor, "Brasileiro")
        self.assertEqual(pessoa.estado_civil.valor, "Casado(a)")
        self.assertEqual(pessoa.profissao.valor, "vigilante")
        self.assertEqual(pessoa.rg.valor, "99001053514")
        self.assertEqual(pessoa.orgao_expedidor.valor, "SSP/AL")
        self.assertEqual(pessoa.cpf.valor, "529.982.247-25")
        self.assertTrue(pessoa.cpf.valido)
        self.assertEqual(pessoa.logradouro.valor, "Rua Bom Jesus")
        self.assertEqual(pessoa.numero.valor, "27 A")
        self.assertEqual(pessoa.bairro.valor, "Benedito Bentes")
        self.assertEqual(pessoa.cidade.valor, "Maceió")
        self.assertEqual(pessoa.uf.valor, "AL")
        self.assertEqual(pessoa.cep.valor, "57084-818")
        self.assertEqual(pessoa.email.valor, "anderson@gmail.com")
        self.assertEqual(pessoa.telefone.valor, "+55 82 99188-6196")

    def test_endereco_com_complemento_e_cep_com_espaco(self):
        pessoa = C.parse_bloco(self.bloco(COM_COMPLEMENTO), "contratante", "t.pdf")
        self.assertEqual(pessoa.numero.valor, "105")
        self.assertEqual(pessoa.complemento.valor, "QD B")
        self.assertEqual(pessoa.bairro.valor, "Jacarecica")
        self.assertEqual(pessoa.cep.valor, "57038-637")
        self.assertEqual(pessoa.estado_civil.valor, "União estável")
        self.assertEqual(pessoa.telefone.valor, "+55 82 99179-7759")

    def test_sem_rg_marca_campo_vazio_sem_inventar(self):
        pessoa = C.parse_bloco(self.bloco(SEM_RG_COM_RESPONSAVEL), "contratante",
                               "t.pdf")
        self.assertEqual(pessoa.rg.valor, "")
        self.assertFalse(pessoa.rg.valido)
        self.assertIn("não consta", pessoa.rg.motivo)
        self.assertEqual(pessoa.complemento.valor, "QD F casa 28")
        self.assertEqual(pessoa.bairro.valor, "Cidade Universitária")

    def test_nao_confunde_contratante_com_responsavel(self):
        pessoa = C.parse_bloco(self.bloco(SEM_RG_COM_RESPONSAVEL), "contratante",
                               "t.pdf")
        self.assertEqual(pessoa.nome.valor, "ERICA DA SILVA SANTOS")
        self.assertEqual(pessoa.email.valor, "erica@gmail.com")
        self.assertNotIn("LUCAS", pessoa.nome.valor)

    def test_nao_confunde_com_o_cnpj_do_escritorio(self):
        pessoa = C.parse_bloco(self.bloco(COMPLETO), "contratante", "t.pdf")
        self.assertEqual(pessoa.cnpj.valor, "")

    def test_cpf_invalido_marca_invalido_e_nao_conta_confianca(self):
        pessoa = C.parse_bloco(self.bloco(CPF_INVALIDO), "contratante", "t.pdf")
        self.assertFalse(pessoa.cpf.valido)
        self.assertEqual(pessoa.cpf.confianca, 0.0)
        self.assertIn("dígito verificador", pessoa.cpf.motivo)


class TestEnderecosReais(unittest.TestCase):
    """Formatos de endereço que apareceram de verdade nas pastas de 2026."""

    def separar(self, endereco):
        miolo = COMPLETO.replace(
            "Rua Bom Jesus, 27 A – Benedito Bentes – Maceió/AL – CEP: 57084-818",
            endereco)
        return C.parse_bloco(C._recortar(texto(miolo), C._INICIO_CONTRATANTE),
                             "contratante", "t.pdf")

    def test_uf_por_extenso_e_virgulas(self):
        p = self.separar("Rua Boa Vista, nº 63, Centro, Coqueiro Seco – "
                         "Alagoas - CEP: 57.100-000")
        self.assertEqual(p.uf.valor, "AL")
        self.assertEqual(p.cidade.valor, "Coqueiro Seco")
        self.assertEqual(p.bairro.valor, "Centro")
        self.assertEqual(p.logradouro.valor, "Rua Boa Vista")
        self.assertEqual(p.numero.valor, "63")

    def test_separado_so_por_virgula_e_uf_com_hifen(self):
        p = self.separar("Rua Sombra do Coco, 75, PQ R Jaqueline, "
                         "Gravatai - RS - CEP: 94180-100")
        self.assertEqual(p.uf.valor, "RS")
        self.assertEqual(p.cidade.valor, "Gravatai")
        self.assertEqual(p.bairro.valor, "PQ R Jaqueline")
        self.assertEqual(p.numero.valor, "75")

    def test_nome_de_rua_terminado_em_no_nao_vira_numero(self):
        # "Rua Tamarino Pimentel": o "no" de Tamarino já foi lido como "nº".
        p = self.separar("Rua Tamarino Pimentel, nº S/N – Vila Pimentel – "
                         "Amambai/MS – CEP: 79990-000")
        self.assertEqual(p.logradouro.valor, "Rua Tamarino Pimentel")
        self.assertEqual(p.numero.valor, "S/N")
        self.assertEqual(p.bairro.valor, "Vila Pimentel")
        self.assertEqual(p.cidade.valor, "Amambai")

    def test_numero_com_apartamento_no_mesmo_trecho(self):
        p = self.separar("Rua PAMPA, 482 AP 5, Sit Gaucho, "
                         "Gravatai - RS - CEP: 94030-320")
        self.assertEqual(p.logradouro.valor, "Rua PAMPA")
        self.assertEqual(p.numero.valor, "482")
        self.assertEqual(p.complemento.valor, "AP 5")

    def test_endereco_sem_numero_nao_inventa(self):
        p = self.separar("Avenida Roberto Santos, Terreo Esperança, "
                         "Ilhéus- BA - CEP: 45650-000")
        self.assertEqual(p.numero.valor, "")
        self.assertFalse(p.numero.valido)
        self.assertTrue(any("Número" in o for o in p.observacoes))

    def test_endereco_irreconhecivel_baixa_a_confianca(self):
        p = self.separar("um lugar qualquer sem cidade CEP: 57000-000")
        self.assertFalse(p.cidade.preenchido)
        self.assertLess(p.logradouro.confianca, 0.80)


class TestExtracaoCompleta(unittest.TestCase):
    """Testa extrair(), trocando a leitura do PDF por texto controlado."""

    def setUp(self):
        self.original = C.texto_do_pdf

    def tearDown(self):
        C.texto_do_pdf = self.original

    def extrair(self, miolo):
        C.texto_do_pdf = lambda caminho, paginas=3: texto(miolo)
        return C.extrair(Path("contrato-ficticio.pdf"))

    def test_extrai_processo_e_veiculo(self):
        resultado = self.extrair(COMPLETO)
        self.assertTrue(resultado.legivel)
        self.assertEqual(resultado.tipo_acao.valor, "Ação Revisional")
        self.assertEqual(resultado.banco_adverso.valor, "Banco Santander")
        self.assertIn("HONDA", resultado.veiculo.valor)

    def test_detecta_corresponsavel(self):
        resultado = self.extrair(SEM_RG_COM_RESPONSAVEL)
        self.assertIsNotNone(resultado.responsavel)
        self.assertEqual(resultado.responsavel.nome.valor, "LUCAS SILVA DE CASTRO")
        self.assertTrue(any("Responsável" in o for o in resultado.observacoes))

    def test_sem_qualificacao_reporta_erro_em_vez_de_adivinhar(self):
        C.texto_do_pdf = lambda caminho, paginas=3: CABECALHO + RODAPE
        resultado = C.extrair(Path("x.pdf"))
        self.assertFalse(resultado.legivel)
        self.assertTrue(resultado.erros)
        self.assertIsNone(resultado.contratante)

    def test_pdf_sem_camada_de_texto_e_reportado(self):
        C.texto_do_pdf = lambda caminho, paginas=3: "QR-CODE SERPRO"
        resultado = C.extrair(Path("cnh.pdf"))
        self.assertFalse(resultado.legivel)
        self.assertIn("camada de texto", resultado.erros[0])

    def test_pdf_ilegivel_nao_derruba_a_extracao(self):
        def explodir(caminho, paginas=3):
            raise IOError("arquivo corrompido")
        C.texto_do_pdf = explodir
        resultado = C.extrair(Path("quebrado.pdf"))
        self.assertFalse(resultado.legivel)
        self.assertIn("corrompido", resultado.erros[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestPessoaJuridica(unittest.TestCase):
    """
    Contrato de empresa — o primeiro foi a Vektor Pharma (18/09/2026).

    Ficou pendente por "CPF não localizado": o extrator não lia "CNPJ de nº"
    nem endereço de empresa ("localizada na"), então a ficha parecia de pessoa
    física sem CPF.
    """

    TEXTO = ("como Cliente Contratante VEKTOR PHARMA IMPORTAÇÃO E EXPORTAÇÃO EM "
             "SOLUCOES DE SAUDE LTDA. , CNPJ de nº 40.420.219/0001-64, localizada "
             "na Rua General Clark, nº 1983 – Novo Progresso – Contagem - MG – "
             "CEP: 32.115-140 e endereço eletrônico diretoria@exemplo.com.br, "
             "telefone de contato (31) 99944-6040, mediante as cláusulas e "
             "condições seguintes: Cláusula 1ª. para realizar o ingresso da Ação "
             "de Obrigação de Fazer referente ao não pagamento das notas fiscais. "
             "Cláusula 2ª.")

    def _ler(self):
        from src.extractors import contrato_ho
        original = contrato_ho.texto_do_pdf
        contrato_ho.texto_do_pdf = lambda caminho, paginas=3: self.TEXTO
        try:
            return contrato_ho.extrair(Path("contrato.pdf"))
        finally:
            contrato_ho.texto_do_pdf = original

    def test_le_o_cnpj_escrito_com_de(self):
        self.assertEqual(self._ler().contratante.cnpj.valor, "40.420.219/0001-64")

    def test_le_o_endereco_de_empresa(self):
        pessoa = self._ler().contratante
        self.assertEqual(pessoa.cidade.valor, "Contagem")
        self.assertEqual(pessoa.uf.valor, "MG")
        self.assertEqual(pessoa.cep.valor, "32115-140")

    def test_obrigacao_de_fazer_sozinha_tem_tipo(self):
        self.assertEqual(self._ler().tipo_acao.valor, "Ação de Obrigação de Fazer")

    def test_obrigacao_de_fazer_vira_caso_civel(self):
        from src.astrea import casos
        self.assertEqual(casos.tipo_do_contrato(self._ler().tipo_acao.valor), "CÍVEL")


class TestTipoDeRevisional(unittest.TestCase):
    """
    Revisional de empréstimo e de cartão têm caso próprio no manual dela.

    Com uma exceção decidida por ela: empréstimo COM garantia de veículo é
    veicular (Nubia, 21/09/2026 — eu tinha aberto como empréstimo e errei).
    """

    def _tipo(self, clausula):
        from src.astrea import casos
        from src.extractors import contrato_ho
        resultado = contrato_ho.ResultadoContrato(Path("contrato.pdf"))
        contrato_ho._parse_processo(clausula, resultado, "contrato.pdf")
        return casos.tipo_do_contrato(resultado.tipo_acao.valor)

    def test_emprestimo_com_garantia_de_veiculo_e_veicular(self):
        """Decisão dela (21/09/2026): garantia de veículo manda — é veicular."""
        self.assertEqual(self._tipo(
            "para realizar o ingresso da Ação Revisional de Empréstimo com garantia "
            "de veículo em desfavor do Banco Creditas"), "REVISIONAL VEICULAR")

    def test_emprestimo_sem_veiculo_e_emprestimo(self):
        self.assertEqual(self._tipo(
            "para realizar o ingresso da Ação Revisional de Empréstimo consignado em "
            "desfavor do Banco Pan"), "REVISIONAL EMPRÉSTIMO")

    def test_cartao_de_credito(self):
        self.assertEqual(self._tipo(
            "para realizar o ingresso da Ação Revisional de Cartão de Crédito em "
            "desfavor do Banco Pan"), "REVISIONAL CARTÃO DE CRÉDITO")

    def test_financiamento_de_veiculo_continua_veicular(self):
        self.assertEqual(self._tipo(
            "para realizar o ingresso da Ação Revisional em desfavor do Banco BV, "
            "referente ao contrato de financiamento do veículo"), "REVISIONAL VEICULAR")


RODAPE_COM_HONORARIOS = (
    RODAPE +
    " Cláusula 2ª. Em remuneração, o cliente pagará à advogada a título de "
    "honorários advocatícios, a importância de R$ 10.000,00 (dez mil reais), "
    "sendo este cobrado da seguinte maneira: - Entrada no valor de R$ 1.000,00 "
    "(mil reais) na data de 10.01.2026; - 9 (nove) parcelas de R$ 1.000,00 "
    "(mil reais) com início em 10.02.2026 e a última em 10.10.2026. - A título "
    "de honorários advocatícios finais, pagará a importância correspondente a "
    "20% (vinte por cento) sob o ganho. Cláusula 3ª. Disposição qualquer, sem "
    "relevância para este teste.")

RODAPE_COM_HONORARIOS_UMA_PARCELA = (
    RODAPE +
    " Cláusula 2ª. Em remuneração, o cliente pagará à advogada a título de "
    "honorários advocatícios, a importância de R$ 2.000,00 (dois mil reais), "
    "sendo este cobrado da seguinte maneira: - Entrada no valor de R$ 1.000,00 "
    "(mil reais) na data de 10.01.2026; - R$ R$ 1.000,00 (mil reais) na data "
    "de 10.02.2026. Cláusula 3ª. Disposição qualquer, sem relevância para "
    "este teste.")


class TestHonorarios(unittest.TestCase):
    """
    Cláusula 2ª: valor total, entrada e parcelamento — usados no dashboard
    financeiro (decisão dela, 23/09/2026). Dado financeiro nunca se adivinha:
    o que não bate no padrão vira pendência, não estimativa.
    """

    def setUp(self):
        self.original = C.texto_do_pdf

    def tearDown(self):
        C.texto_do_pdf = self.original

    def _extrair(self, rodape):
        C.texto_do_pdf = lambda caminho, paginas=3: CABECALHO + COMPLETO + rodape
        return C.extrair(Path("contrato-ficticio.pdf"))

    def test_varias_parcelas(self):
        r = self._extrair(RODAPE_COM_HONORARIOS)
        self.assertEqual(r.valor_total_honorarios.valor, 10000.0)
        self.assertEqual(r.entrada_valor.valor, 1000.0)
        self.assertEqual(r.entrada_data.valor, "10.01.2026")
        self.assertEqual(r.parcelas_qtd.valor, 9)
        self.assertEqual(r.parcelas_valor.valor, 1000.0)
        self.assertEqual(r.parcelas_inicio.valor, "10.02.2026")
        self.assertEqual(r.parcelas_fim.valor, "10.10.2026")

    def test_uma_parcela_so_nao_usa_a_palavra_parcelas(self):
        """
        Quando só sobra uma parcela, o modelo do escritório não escreve
        "1 (uma) parcela" — vira uma linha solta com "R$ R$ ... na data de".
        """
        r = self._extrair(RODAPE_COM_HONORARIOS_UMA_PARCELA)
        self.assertEqual(r.valor_total_honorarios.valor, 2000.0)
        self.assertEqual(r.parcelas_qtd.valor, 1)
        self.assertEqual(r.parcelas_valor.valor, 1000.0)
        self.assertEqual(r.parcelas_inicio.valor, "10.02.2026")
        self.assertEqual(r.parcelas_fim.valor, "10.02.2026")

    def test_sem_clausula_2_vira_pendencia_sem_inventar(self):
        r = self._extrair("")   # RODAPE (só cláusula 1ª) sem cláusula 2ª
        for campo in (r.valor_total_honorarios, r.entrada_valor, r.entrada_data,
                     r.parcelas_qtd, r.parcelas_valor, r.parcelas_inicio, r.parcelas_fim):
            self.assertFalse(campo.valido)
            self.assertIn("cláusula 2ª", campo.motivo)



class TestEntradaDividida(unittest.TestCase):
    """Entrada "sendo; - R$ a na data X; - R$ b na data Y" (contratos de 30/09/2026)."""

    def test_entrada_dividida_em_duas_datas(self):
        texto = ("CLÁUSULA 2ª - Pelos serviços, a importância de R$ 7.689,20 (sete mil), "
                 "sendo este cobrado da seguinte maneira: - Entrada no valor de R$ 500,00 "
                 "(quinhentos reais) sendo; - R$ 250,00 (duzentos e cinquenta reais) na data "
                 "de 10/09/2026; - R$ 250,00 (duzentos e cinquenta reais) na data de "
                 "21/09/2026; - 15 (quinze) parcelas de R$ 479,28 (quatrocentos) com início "
                 "em 10.10.2026 e a última em 10.12.2027. CLÁUSULA 3ª - fim")
        r = C.ResultadoContrato(Path("x.pdf"))
        C._parse_honorarios(texto, r, "x.pdf")
        self.assertEqual(r.entrada_valor.valor, 500.0)
        self.assertTrue(r.entrada_data.valido)
        self.assertEqual(r.parcelas_qtd.valor, 15)
        self.assertEqual(r.parcelas_valor.valor, 479.28)

    def test_entrada_dividida_sem_ponto_e_virgula(self):
        """Partes separadas só por " - " (contrato do Sidnei, agosto/2026)."""
        texto = ("CLÁUSULA 2ª - a importância de R$ 5.218,52 (cinco mil), sendo este cobrado "
                 "da seguinte maneira: - Entrada no valor de R$ 500,00 (quinhentos reais) sendo; "
                 "- R$ 250,00 (duzentos e cinquenta reais) na data de 14/08/2026 - R$ 250,00 "
                 "(duzentos e cinquenta reais) na data de 17/08/2026 - 12 (doze) parcelas de "
                 "R$ 393,21 (trezentos) com início em 12.09.2026 e a última em 12.08.2027. "
                 "CLÁUSULA 3ª - fim")
        r = C.ResultadoContrato(Path("x.pdf"))
        C._parse_honorarios(texto, r, "x.pdf")
        self.assertEqual(r.entrada_valor.valor, 500.0)
        self.assertEqual(r.parcelas_qtd.valor, 12)
        self.assertEqual(r.parcelas_valor.valor, 393.21)
