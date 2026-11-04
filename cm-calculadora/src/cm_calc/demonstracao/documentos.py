"""Documentos 100% FICTÍCIOS para testes da leitura documental.

Pessoas, CPF, placa, processo, banco e valores são inventados. O CPF
123.456.789-09 é um número de teste notório, não pertence a cliente.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pymupdf

CONTRATO = """CÉDULA DE CRÉDITO BANCÁRIO Nº 2023-000777
Credor: BANCO FICTÍCIO S.A., CNPJ 00.000.000/0001-91
Emitente: JOANA EXEMPLO DA SILVA, brasileira, solteira, inscrita no CPF 123.456.789-09,
residente na Rua das Flores Fictícias, 100, CEP 01000-000, telefone (11) 91234-5678,
e-mail joana.exemplo@exemplo.com
Veículo: placa ABC1D23, chassi 9BWZZZ377VT004251, RENAVAM 12345678901
QUADRO RESUMO
Data de emissão: 05/01/2023
Valor liberado: R$ 36.000,00
IOF (financiado): R$ 1.100,00
Tarifa de cadastro (financiada): R$ 900,00
Seguro prestamista (financiado): R$ 1.500,00
Registro de contrato (financiado): R$ 500,00
Tarifa de avaliação do bem (paga à vista): R$ 450,00
Valor total financiado: R$ 40.000,00
Taxa de juros: 2,20% a.m. e 29,84% a.a.
Custo Efetivo Total (CET): 2,61% a.m. e 36,22% a.a.
Quantidade de parcelas: 24
Valor da parcela: R$ 2.163,06
Vencimento da primeira parcela: 05/02/2023
Capitalização mensal dos juros, conforme pactuado.
ENCARGOS DE INADIMPLÊNCIA
Multa de 2% sobre o valor em atraso.
Juros moratórios de 1% a.m.
"""

PETICAO = """EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO DA VARA CÍVEL DA COMARCA FICTÍCIA
JOANA EXEMPLO DA SILVA, brasileira, solteira, inscrita no CPF 123.456.789-09, vem propor
AÇÃO REVISIONAL em face de BANCO FICTÍCIO S.A., pelos fundamentos a seguir.
DOS FATOS
A autora firmou contrato de financiamento com valor total financiado: R$ 41.000,00, em 24 parcelas.
DOS PEDIDOS
Requer:
a) a declaração de abusividade da tarifa de registro de contrato e da tarifa de cadastro;
b) a limitação dos juros remuneratórios à taxa média de mercado;
c) a repetição em dobro dos valores pagos indevidamente;
d) a descaracterização da mora.
Dá à causa o valor de R$ 10.000,00.
"""

SENTENCA = """PODER JUDICIÁRIO
SENTENÇA
Processo nº 0001234-56.2023.8.26.0000
Autor: JOANA EXEMPLO DA SILVA
Réu: BANCO FICTÍCIO S.A.
Vistos. Trata-se de ação revisional de contrato de financiamento de veículo, na qual a autora
sustenta a abusividade de encargos e tarifas. O réu apresentou contestação. É o relatório.
Fundamento e decido. A capitalização mensal é admitida, pois expressamente pactuada no contrato.
Quanto à compensação, é cabível com eventual saldo devedor da autora.
Ante o exposto, JULGO PARCIALMENTE PROCEDENTES os pedidos, com resolução do mérito (art. 487, I, do CPC), para:
a) limitar os juros remuneratórios à taxa média de mercado divulgada pelo BACEN para a modalidade, na data da contratação;
b) declarar a abusividade da tarifa de cadastro e do seguro prestamista, determinando sua exclusão;
c) descaracterizar a mora, afastando a multa e os juros de mora;
d) condenar o réu à restituição dos valores pagos a maior, em dobro, com correção monetária pelo INPC desde cada desembolso e juros de mora de 1% a.m. desde a citação;
e) manter a cobrança da tarifa de registro de contrato e da tarifa de avaliação do bem.
Condeno o réu ao pagamento das custas e dos honorários advocatícios, que fixo em 10% sobre o valor da condenação.
Publique-se. Registre-se. Intimem-se.
Comarca Fictícia, 10 de março de 2024.
Juiz de Direito Fictício
"""

EMBARGOS = """DECISÃO
Embargos de declaração opostos pelo réu em face da sentença.
Alega omissão quanto ao termo final da descaracterização da mora.
Não há omissão: a matéria foi enfrentada de forma suficiente.
Ante o exposto, conheço dos embargos e os REJEITO.
Comarca Fictícia, 25 de março de 2024.
"""

ACORDAO = """PODER JUDICIÁRIO
TRIBUNAL DE JUSTIÇA FICTÍCIO
ACÓRDÃO
Apelação Cível nº 0001234-56.2023.8.26.0000
Apelante: BANCO FICTÍCIO S.A.
Apelada: JOANA EXEMPLO DA SILVA
EMENTA: APELAÇÃO. AÇÃO REVISIONAL. REPETIÇÃO DO INDÉBITO. FORMA SIMPLES. Recurso parcialmente provido.
ACORDAM, em 99ª Câmara de Direito Privado do Tribunal de Justiça Fictício, por unanimidade, dar parcial provimento ao recurso, nos termos do voto do relator.
VOTO
Trata-se de apelação interposta pelo banco réu. Sustenta que a devolução deve ocorrer de forma simples, pois não demonstrada má-fé. Com razão.
Ante o exposto, dou parcial provimento ao recurso para determinar que a restituição dos valores pagos a maior ocorra na forma simples, mantida a sentença nos demais termos. Em razão do resultado, majoro os honorários advocatícios para 12% sobre o valor da condenação.
Sala das Sessões, 20 de agosto de 2024.
Desembargador Relator Fictício
"""

CERTIDAO = """CERTIDÃO
Certifico que o acórdão transitou em julgado em 30/09/2024.
Servidor Fictício
"""


def comprovante(parcela: int, venc: str, pag: str, valor: str, encargos: str | None = None) -> str:
    enc = f"Encargos: R$ {encargos}\n" if encargos else ""
    return (f"COMPROVANTE DE PAGAMENTO\nBanco Fictício S.A. - Financiamento de veículo\nContrato: 2023-000777\n"
            f"Parcela: {parcela:02d}/24\nVencimento: {venc}\nData do pagamento: {pag}\n{enc}"
            f"Valor pago: R$ {valor}\nAutenticação mecânica: 0000-FICT-{parcela:04d}\n")


PLANILHA_CSV = """Parcela;Vencimento;Data pagamento;Valor pago;Encargos
1;05/02/2023;05/02/2023;2.163,06;
2;05/03/2023;05/03/2023;2.163,60;
3;05/04/2023;05/04/2023;2.163,06;
4;05/05/2023;25/05/2023;2.252,46;89,40
5;05/06/2023;05/06/2023;2.163,06;
"""


def _paginas(texto: str, largura: int = 100, linhas_por_pagina: int = 55) -> list[str]:
    linhas: list[str] = []
    for par in texto.split("\n"):
        linhas += textwrap.wrap(par, largura) or [""]
    return ["\n".join(linhas[i:i + linhas_por_pagina]) for i in range(0, len(linhas), linhas_por_pagina)] or [""]


def gerar_pdf(destino: Path, partes: list[tuple[str, str]], com_sumario: bool = False, rodape_pje: int | None = None,
              pagina_digitalizada: bool = False, linhas_por_pagina: int = 55) -> Path:
    """``partes``: [(título, texto)]. Cada parte começa em nova página."""
    pdf = pymupdf.open()
    toc = []
    for titulo, texto in partes:
        toc.append([1, titulo, pdf.page_count + 1])
        for corpo in _paginas(texto, linhas_por_pagina=linhas_por_pagina):
            pg = pdf.new_page()
            pg.insert_text((40, 50), corpo, fontsize=8.5, fontname="helv")
            if rodape_pje:
                pg.insert_text((40, 820), f"Num. {rodape_pje} - Pág. {pdf.page_count}", fontsize=7)
    if pagina_digitalizada:
        pg = pdf.new_page()
        pg.draw_rect(pymupdf.Rect(40, 40, 400, 300), fill=(0.8, 0.8, 0.8))   # imagem sem camada de texto
    if com_sumario:
        pdf.set_toc(toc)
    pdf.save(destino)
    return destino


def gerar_caso_completo(pasta: Path) -> dict[str, Path]:
    """Arquivos avulsos de um caso fictício completo."""
    pasta.mkdir(parents=True, exist_ok=True)
    arqs = {
        "contrato": gerar_pdf(pasta / "contrato.pdf", [("Contrato", CONTRATO)]),
        "peticao": gerar_pdf(pasta / "inicial.pdf", [("Inicial", PETICAO)]),
        "sentenca": gerar_pdf(pasta / "sentenca.pdf", [("Sentença", SENTENCA)], rodape_pje=11111111),
        "embargos": gerar_pdf(pasta / "embargos.pdf", [("Embargos", EMBARGOS)]),
        "acordao": gerar_pdf(pasta / "acordao.pdf", [("Acórdão", ACORDAO)], rodape_pje=22222222),
        "certidao": gerar_pdf(pasta / "certidao.pdf", [("Certidão", CERTIDAO)]),
        "comp1": gerar_pdf(pasta / "comprovante-01.pdf", [("c", comprovante(1, "05/02/2023", "05/02/2023", "2.163,06"))]),
        "comp2": gerar_pdf(pasta / "comprovante-02.pdf", [("c", comprovante(2, "05/03/2023", "05/03/2023", "2.163,06"))]),
        "comp4": gerar_pdf(pasta / "comprovante-04.pdf",
                           [("c", comprovante(4, "05/05/2023", "25/05/2023", "2.252,46", "89,40"))]),
    }
    p = pasta / "pagamentos.csv"
    p.write_text(PLANILHA_CSV, encoding="utf-8")
    arqs["planilha"] = p
    return arqs
