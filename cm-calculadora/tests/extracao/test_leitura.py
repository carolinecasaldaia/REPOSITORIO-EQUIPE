"""Importação, classificação e segmentação de documentos fictícios."""

from datetime import date

import pytest
from openpyxl import Workbook

from cm_calc.documentos.classificacao import classificar
from cm_calc.documentos.leitura import ler_arquivo
from cm_calc.documentos.modelos import TipoDocumento as T
from tests.fixtures import documentos_ficticios as F


@pytest.mark.parametrize("chave,tipo", [
    ("contrato", T.CONTRATO), ("peticao", T.PETICAO_INICIAL), ("sentenca", T.SENTENCA),
    ("embargos", T.EMBARGOS_DECISAO), ("acordao", T.ACORDAO), ("certidao", T.CERTIDAO),
    ("comp1", T.COMPROVANTE), ("planilha", T.PLANILHA),
])
def test_classificacao_de_cada_documento(arquivos, chave, tipo):
    r = ler_arquivo(arquivos[chave])
    assert [d.tipo for d in r.documentos] == [tipo]


def test_datas_das_decisoes_sao_as_de_assinatura(documentos):
    docs, _ = documentos
    por_tipo = {d.tipo: d for d in docs}
    assert por_tipo[T.SENTENCA].data == date(2024, 3, 10)
    assert por_tipo[T.ACORDAO].data == date(2024, 8, 20)
    assert por_tipo[T.EMBARGOS_DECISAO].instancia_superior is False


def test_texto_sem_marcadores_nao_e_forcado():
    tipo, conf, ind = classificar("Lista de compras: pão, leite e café.")
    assert tipo is T.DESCONHECIDO and conf == 0.0


def test_peticao_que_cita_embargos_nao_vira_decisao():
    tipo, _, _ = classificar("EMBARGOS DE DECLARAÇÃO\nO embargante requer o suprimento da omissão apontada.")
    assert tipo is not T.EMBARGOS_DECISAO


@pytest.mark.parametrize("com_sumario", [True, False])
def test_processo_completo_segmentado(tmp_path, com_sumario):
    partes = [("Inicial", F.PETICAO), ("Contrato", F.CONTRATO), ("Sentença", F.SENTENCA),
              ("Embargos", F.EMBARGOS), ("Acórdão", F.ACORDAO), ("Certidão", F.CERTIDAO)]
    pdf = F.gerar_pdf(tmp_path / "processo.pdf", partes, com_sumario=com_sumario, rodape_pje=99887766)
    r = ler_arquivo(pdf)
    assert [d.tipo for d in r.documentos] == [T.PETICAO_INICIAL, T.CONTRATO, T.SENTENCA, T.EMBARGOS_DECISAO,
                                              T.ACORDAO, T.CERTIDAO]
    sentenca = r.documentos[2]
    assert sentenca.paginas[0].numero == 3                      # página no arquivo do processo
    assert sentenca.paginas[0].referencia_pje == "Num. 99887766 - Pág. 3"
    assert len({d.sha256 for d in r.documentos}) == 1           # mesmo arquivo de origem


def test_documento_de_varias_paginas_fica_inteiro(tmp_path):
    pdf = F.gerar_pdf(tmp_path / "s.pdf", [("Sentença", F.SENTENCA)], linhas_por_pagina=8)
    r = ler_arquivo(pdf)
    assert len(r.documentos) == 1 and len(r.documentos[0].paginas) >= 3
    assert r.documentos[0].tipo is T.SENTENCA


def test_pagina_digitalizada_gera_aviso_de_ocr(tmp_path):
    pdf = F.gerar_pdf(tmp_path / "c.pdf", [("Contrato", F.CONTRATO)], pagina_digitalizada=True)
    r = ler_arquivo(pdf)
    assert any("OCR necessário" in a and "2" in a for a in r.avisos)


def test_planilha_xlsx_com_numeros_e_datas(tmp_path):
    from datetime import datetime
    wb = Workbook()
    ws = wb.active
    ws.append(["Nº", "Vencimento", "Pago em", "Valor", "Multa/Juros"])
    ws.append([1, datetime(2023, 2, 5), datetime(2023, 2, 7), 2163.06, 3.12])
    arq = tmp_path / "p.xlsx"
    wb.save(arq)
    r = ler_arquivo(arq)
    d = r.documentos[0]
    assert d.tipo is T.PLANILHA
    linha = d.tabela[0]
    assert linha["valor"] == "2163.06" and linha["pago em"] == "07/02/2023"
    assert any("conferir centavos" in a for a in r.avisos)


def test_formato_nao_suportado(tmp_path):
    arq = tmp_path / "x.docx"
    arq.write_bytes(b"x")
    with pytest.raises(ValueError, match="não suportado"):
        ler_arquivo(arq)
