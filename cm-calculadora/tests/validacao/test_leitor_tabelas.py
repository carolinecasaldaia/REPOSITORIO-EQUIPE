"""Leitor de tabelas do parecer: layouts que falharam na VAL-001, reproduzidos com dados FICTÍCIOS."""

import pymupdf

from cm_calc.validacao.leitura_parecer import _coluna, ler_parecer_pdf, titulo_apendice


def _pagina(pdf, titulo, descricao, cabecalho, linhas, y0=60):
    """Escreve palavras em posições exatas (números alinhados à direita, como nos pareceres)."""
    pg = pdf.new_page(width=595, height=842)
    pg.insert_text((72, y0), titulo, fontsize=9)
    for k, t in enumerate(descricao):
        pg.insert_text((72, y0 + 14 + 11 * k), t, fontsize=8)
    y = y0 + 14 + 11 * len(descricao) + 18
    for x, txt, dy in cabecalho:
        pg.insert_text((x, y + dy), txt, fontsize=7)
    for i, valores in enumerate(linhas, start=1):
        for x_dir, txt in valores:
            larg = pymupdf.get_text_length(txt, fontsize=7)
            pg.insert_text((x_dir - larg, y + 14 * i), txt, fontsize=7)


def _pdf_ficticio(tmp_path):
    pdf = pymupdf.open()
    cab_evol = [(84, "Nº", 0), (131, "Data", 0), (191, "Prestação (R$)", 0), (282, "Juros (R$)", 0),
                (356, "Amortização (R$)", 0), (443, "Saldo Devedor (R$)", 0)]
    evol = [[(92, str(n)), (175, f"1{n}/02/2024"), (242, "1.000,00"), (318, "10,00"), (417, "990,00"),
             (510, f"{9 - n}.010,00")] for n in range(1, 6)]
    _pagina(pdf, "APÊNDICE AP02 — EVOLUÇÃO FICTÍCIA", ["Texto fictício."], cab_evol, evol)
    cab03 = [(82, "Nº", 0), (119, "Data", 0), (163, "Pago (R$)", 0), (211, "Correto (R$)", 0), (269, "Dif. (R$)", 0),
             (311, "Fator INPC", 0), (354, "Corrigida (R$)", 0), (414, "Meses", -4), (416, "Mora", 4),
             (449, "Mora (R$)", 0), (492, "Subtotal (R$)", 0)]
    ap03 = [[(100, str(n)), (147, f"1{n}/02/2024"), (206, "1.000,04"), (259, "1.000,00"), (307, "0,04"),
             (352, "1.2500"), (405, "0,05"), (444, "70"), (489, "0,04"), (539, "0,09")] for n in range(1, 6)]
    # a descrição do AP03 menciona outro apêndice no meio da frase (causa da mistura na VAL-001)
    _pagina(pdf, "APÊNDICE AP03 — DIFERENÇAS FICTÍCIAS",
            ["Comparação entre o pago e o valor correto (Apêndice AP02), com correção pelo INPC."], cab03, ap03)
    arq = tmp_path / "f.pdf"
    pdf.save(arq)
    return arq


def test_marcador_so_no_inicio_da_linha():
    assert titulo_apendice("APÊNDICE AP03 — DEMONSTRATIVO") == "AP03"
    assert titulo_apendice("AP01 — Evolução") == "AP01"
    assert titulo_apendice("capitalização mensal (Apêndice AP02), com correção") is None
    assert titulo_apendice("1 11/05/2019 1.104,78") is None


def test_nomes_de_coluna_com_unidade():
    assert _coluna("Saldo Devedor (R$)") == "saldo"
    assert _coluna("Correto (R$)") == "devido" and _coluna("Dif. (R$)") == "diferenca"
    assert _coluna("Meses Mora") == "meses_mora" and _coluna("Mora (R$)") == "juros_mora"
    assert _coluna("Subtotal (R$)") == "subtotal" and _coluna("Fator INPC") == "fator"


def test_tabelas_separadas_e_colunas_completas(tmp_path):
    p = ler_parecer_pdf(_pdf_ficticio(tmp_path).read_bytes(), "f.pdf")
    assert set(p.tabelas) == {"AP02", "AP03"}
    ap02, ap03 = p.tabelas["AP02"], p.tabelas["AP03"]
    assert [l.numero for l in ap02.linhas] == [1, 2, 3, 4, 5] and [l.numero for l in ap03.linhas] == [1, 2, 3, 4, 5]
    assert ap02.linhas[0].valores == {"prestacao": 1000, "juros": 10, "amortizacao": 990, "saldo": 8010}
    v = ap03.linhas[0].valores
    from decimal import Decimal as D
    assert (v["pago"], v["devido"], v["diferenca"], v["fator"], v["corrigido"], v["meses_mora"], v["juros_mora"],
            v["subtotal"]) == tuple(D(x) for x in ("1000.04", "1000", "0.04", "1.25", "0.05", "70", "0.04", "0.09"))
