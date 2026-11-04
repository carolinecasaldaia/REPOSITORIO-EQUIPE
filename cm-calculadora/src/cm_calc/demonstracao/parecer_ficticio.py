"""Parecer pericial FICTÍCIO, calculado de forma INDEPENDENTE do motor (não importa cm_calc.motor).

Metodologia simulada da "perita":
- AP01: capitalização DIÁRIA pela taxa anual, base 365, TRUNCAMENTO por parcela
        (a ficha declara meses civis — o validador deve diagnosticar);
- AP02: capitalização mensal (meses civis), arredondamento meio-para-cima, com um ERRO
        DE DIGITAÇÃO proposital nos juros da parcela 7 (+ R$ 10,00, saldo correto);
- AP03: correção incluindo o mês da data-base (a ficha diz que não inclui), dobro a partir
        de 01/04/2023, juros de 1% a.m. (dias/30) desde 15/03/2024, data-base 10/10/2024.
"""

from __future__ import annotations

import decimal
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from fractions import Fraction
from pathlib import Path

CTX = decimal.Context(prec=40)
C2 = Decimal("0.01")

LIB = date(2023, 1, 10)
VF = Decimal("30000.00")
I_C = Decimal("0.025")                 # contrato: 2,5% a.m.
IA_C = Decimal("0.344889")             # 34,4889% a.a. (declarada no contrato fictício)
I_R = Decimal("0.015")                 # título: 1,5% a.m.
EXCLUIDO = Decimal("1000.00")          # tarifa financiada excluída
REFORCO_N, REFORCO_V = 6, Decimal("4000.00")
DATA_BASE = date(2024, 10, 10)
CORTE = date(2023, 4, 1)
JUROS_INI = date(2024, 3, 15)
ATRASO = {3: (15, Decimal("50.00"))}   # parcela: (dias de atraso, encargos pagos)
INDICE = {f"{a:04d}-{m:02d}": Decimal(v) for a, m, v in
          [(2023, m, ("0.0030", "0.0045", "0.0021", "0.0038")[m % 4]) for m in range(1, 13)]
          + [(2024, m, ("0.0042", "0.0019", "0.0033", "0.0027")[m % 4]) for m in range(1, 13)]}


def vencimentos() -> list[date]:
    out = []
    for k in range(12):
        m = LIB.month + 1 + k
        a = LIB.year + (m - 1) // 12
        out.append(date(a, (m - 1) % 12 + 1, 10))
    return out


def _price_com_reforco(vf: Decimal, i: Decimal) -> Decimal:
    """R tal que VF = Σ R·v^k (k≠6) + 4000·v^6, períodos mensais inteiros — aritmética racional."""
    fi = Fraction(str(i))
    v = 1 / (1 + fi)
    soma = sum(v ** k for k in range(1, 13) if k != REFORCO_N)
    r = (Fraction(str(vf)) - Fraction(str(REFORCO_V)) * v ** REFORCO_N) / soma
    return (Decimal(r.numerator) / Decimal(r.denominator)).quantize(C2, ROUND_HALF_UP)


P_CONTRATO = _price_com_reforco(VF, I_C)
P_REVISADA = _price_com_reforco(VF - EXCLUIDO, I_R)


def parcelas_contrato() -> list[tuple[int, date, Decimal, str]]:
    return [(k, d, REFORCO_V if k == REFORCO_N else P_CONTRATO, "reforçada" if k == REFORCO_N else "regular")
            for k, d in enumerate(vencimentos(), start=1)]


def ap01() -> list[dict]:
    linhas, saldo, ant = [], VF, LIB
    for n, d, p, _ in parcelas_contrato():
        dias = (d - ant).days
        fator = CTX.power(1 + IA_C, Decimal(dias) / Decimal(365))
        juros = (saldo * (fator - 1)).quantize(C2, ROUND_DOWN)
        novo = saldo + juros - p
        linhas.append(dict(n=n, d=d, ant=saldo, juros=juros, prest=p, amort=p - juros, saldo=novo))
        saldo, ant = novo, d
    return linhas


def ap02() -> list[dict]:
    linhas, saldo = [], VF - EXCLUIDO
    for n, d, _, _ in parcelas_contrato():
        p = REFORCO_V if n == REFORCO_N else P_REVISADA
        juros = (saldo * I_R).quantize(C2, ROUND_HALF_UP)
        novo = saldo + juros - p
        juros_impresso = juros + Decimal("10.00") if n == 7 else juros      # erro de digitação proposital
        linhas.append(dict(n=n, d=d, ant=saldo, juros=juros_impresso, prest=p, amort=p - juros_impresso, saldo=novo))
        saldo = novo
    return linhas


def pagamentos() -> list[tuple[int, date, Decimal, Decimal]]:
    out = []
    for n, d, p, _ in parcelas_contrato()[:6]:
        atraso, enc = ATRASO.get(n, (0, Decimal(0)))
        out.append((n, date.fromordinal(d.toordinal() + atraso), p + enc, enc))
    return out


def ap03() -> list[dict]:
    linhas = []
    for n, dp, pago, enc in pagamentos():
        devido = REFORCO_V if n == REFORCO_N else P_REVISADA
        dif = pago - devido
        mult = 2 if dp >= CORTE else 1
        rest = dif * mult
        a, m = dp.year, dp.month
        fator = Decimal(1)
        while (a, m) <= (DATA_BASE.year, DATA_BASE.month):         # inclui o mês da data-base
            fator *= 1 + INDICE[f"{a:04d}-{m:02d}"]
            m += 1
            if m == 13:
                a, m = a + 1, 1
        corr = (rest * fator).quantize(C2, ROUND_HALF_UP)
        pct = Decimal("0.01") * Decimal((DATA_BASE - JUROS_INI).days) / Decimal(30)
        jm = (corr * pct).quantize(C2, ROUND_HALF_UP)
        linhas.append(dict(n=n, d=dp, pago=pago, devido=devido, dif=dif, rest=rest, corr=corr, jm=jm, total=corr + jm))
    return linhas


def br(v: Decimal) -> str:
    s = f"{v:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


TEXTO = """PARECER TÉCNICO-PERICIAL DE LIQUIDAÇÃO DE SENTENÇA (FICTÍCIO)
Autor: [NOME_1]   Réu: BANCO FICTÍCIO S.A.   Processo: [PROCESSO_1]
1. METODOLOGIA
Na evolução original (AP01), a perita reproduziu a capitalização diária dos juros, base 365 dias, com truncamento na segunda casa decimal.
No recálculo (AP02), aplicou-se a taxa de 1,5% a.m. fixada no título, com capitalização mensal (Tabela Price), excluída a tarifa financiada.
No AP03, a restituição ocorre em dobro para os pagamentos a partir de 01/04/2023, com correção monetária pelo INPC
e juros de mora de 1% ao mês desde a citação (15/03/2024). Data-base: 10/10/2024.
"""


def gerar_pdf(destino: Path, texto_extra: str = "") -> Path:
    import pymupdf

    pdf = pymupdf.open()
    pg = pdf.new_page()
    pg.insert_text((40, 60), TEXTO + texto_extra, fontsize=8.5)

    def tabela(titulo, cab, linhas, totais=None):
        pg = pdf.new_page(width=842, height=595)       # paisagem
        pg.insert_text((40, 40), titulo, fontsize=10)
        xs = [40 + i * 95 for i in range(len(cab))]
        for x, c in zip(xs, cab):
            pg.insert_text((x, 70), c, fontsize=8)
        y = 90
        for l in linhas + ([totais] if totais else []):
            for x, v in zip(xs, l):
                pg.insert_text((x, y), v, fontsize=8)
            y += 14

    a1 = ap01()
    tabela("AP01", ["Nº", "Vencimento", "Saldo Inicial", "Juros", "Amortização", "Prestação", "Saldo Final"],
           [[str(l["n"]), l["d"].strftime("%d/%m/%Y"), br(l["ant"]), br(l["juros"]), br(l["amort"]), br(l["prest"]),
             br(l["saldo"])] for l in a1],
           ["Total", "", "", br(sum(l["juros"] for l in a1)), "", br(sum(l["prest"] for l in a1)), ""])
    a2 = ap02()
    tabela("AP02", ["Nº", "Vencimento", "Saldo Inicial", "Juros", "Amortização", "Prestação", "Saldo Final"],
           [[str(l["n"]), l["d"].strftime("%d/%m/%Y"), br(l["ant"]), br(l["juros"]), br(l["amort"]), br(l["prest"]),
             br(l["saldo"])] for l in a2])
    a3 = ap03()
    tabela("AP03", ["Nº", "Data pagamento", "Valor pago", "Valor devido", "Diferença", "A restituir", "Valor corrigido",
                    "Juros de mora", "Total atualizado"],
           [[str(l["n"]), l["d"].strftime("%d/%m/%Y"), br(l["pago"]), br(l["devido"]), br(l["dif"]), br(l["rest"]),
             br(l["corr"]), br(l["jm"]), br(l["total"])] for l in a3],
           ["Total", "", "", "", "", br(sum(l["rest"] for l in a3)), "", "", br(sum(l["total"] for l in a3))])
    pdf.save(destino)
    return destino


def preencher_ficha(destino_modelo: Path, **ajustes) -> None:
    """Preenche a ficha com ENTRADAS do caso fictício (contrato e título) — nenhum resultado da perita."""
    from openpyxl import load_workbook

    valores = {
        "data_liberacao": "10/01/2023", "valor_financiado": "30000,00", "taxa_mensal_contrato": "2,5",
        "taxa_anual_contrato": "34,4889", "convencao_contrato": "meses_civis", "taxa_mensal_revisada": "1,5",
        "regime_revisado": "composto", "convencao_revisada": "meses_civis", "valor_excluido_financiado": "1000,00",
        "tratamento_reforcadas": "manter_valor", "arredondamento": "2;HALF_UP;por_parcela",
        "modalidade_restituicao": "dobro_a_partir_de", "data_corte_dobro": "01/04/2023", "encargos_no_ap03": "excluir",
        "data_base": "10/10/2024", "indice_correcao": "INPC_FICT", "incluir_mes_inicial": "sim", "incluir_mes_final": "não",
        "juros_mora_mensal": "1", "juros_mora_inicio": "15/03/2024", "juros_contagem": "dias_30", "acumulacao_juros": "soma",
    }
    valores.update(ajustes)
    wb = load_workbook(destino_modelo)
    ws = wb["parametros"]
    for row in ws.iter_rows(min_row=2):
        chave = row[0].value
        if chave in valores and valores[chave] is not None:
            row[1].value = valores[chave]
            row[2].value = "documento fictício de teste"
    for n, d, p, tipo in parcelas_contrato():
        wb["parcelas"].append([n, d.strftime("%d/%m/%Y"), str(p).replace(".", ","), tipo])
    for n, d, pago, enc in pagamentos():
        wb["pagamentos"].append([n, d.strftime("%d/%m/%Y"), str(pago).replace(".", ","), str(enc).replace(".", ",")])
    wb.save(destino_modelo)


def csv_indice() -> str:
    return "competencia;variacao\n" + "\n".join(f"{k};{str(v * 100).replace('.', ',')}" for k, v in sorted(INDICE.items()))


CAPA_COM_DADOS_FICTICIOS = """PARECER TÉCNICO-PERICIAL (FICTÍCIO — MATERIAL DE TESTE)
Processo nº 0001234-56.2023.8.26.0000
Autor: JOANA EXEMPLO DA SILVA, brasileira, inscrita no CPF 123.456.789-09, residente na Rua das Flores, 100,
CEP 01000-000, telefone (11) 91234-5678, e-mail joana@exemplo.com. Veículo placa ABC1D23.
Cédula de Crédito Bancário nº 2023-000777.
Perita: Dra. Fulana Perita Teste, CORECON/SP nº 12.345
O valor financiado foi de R$ 30.000,00 à taxa de 2,5% a.m., com liberação em 10/01/2023.
Assinado eletronicamente por: FULANA PERITA TESTE - 10/10/2024
Num. 12345678 - Pág. 1   https://pje.exemplo.invalid/validacao?id=99887766
"""


def gerar_pdf_com_dados_ficticios(destino: Path) -> Path:
    """Parecer FICTÍCIO 'não anonimizado' (dados pessoais inventados) para treinar e testar a anonimização."""
    import pymupdf

    gerar_pdf(destino)
    pdf = pymupdf.open(destino)
    capa = pdf.new_page(pno=0)
    capa.insert_text((40, 60), CAPA_COM_DADOS_FICTICIOS, fontsize=8)
    capa.insert_text((40, 300), "CPF oculto 987.654.321-00", fontsize=8, render_mode=3)
    pdf.set_metadata({"author": "Fulana Perita Teste", "title": "Parecer Joana Exemplo (fictício)"})
    tmp = destino.with_suffix(".tmp.pdf")
    pdf.save(tmp)
    pdf.close()
    tmp.replace(destino)
    return destino
