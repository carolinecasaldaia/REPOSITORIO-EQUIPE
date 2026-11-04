"""Leitura do parecer: tabelas dos apêndices, indícios de metodologia e checagem de anonimização.

Tabelas em PDF: as palavras de cada página são agrupadas em linhas (pela
posição vertical) e em células (pelos espaços horizontais). A linha de
cabeçalho define as colunas pela posição; cada valor numérico é atribuído à
coluna cujo cabeçalho está mais próximo na horizontal. Linhas de dados
começam por um número de parcela ou por uma data. Linhas "Total" viram os
totais declarados.

Planilhas (XLSX/CSV) do parecer seguem o mesmo mapeamento de cabeçalhos,
com uma aba (ou arquivo) por apêndice.
"""

from __future__ import annotations

import hashlib
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ..documentos.texto import RE_DATA_NUM, data_num, normalizar
from ..privacidade.pseudonimizacao import Pseudonimizador, residuos
from .modelos import IndicioMetodologia, LinhaPericial, Parecer, TabelaPericial

RE_APENDICE = re.compile(r"\b(?:ap|apendice|anexo)\s*[-–nº°o.]*\s*0?([123])\b")
# Título de apêndice: só quando a linha COMEÇA pelo marcador. Menções no meio do texto
# ("conforme o Apêndice AP02") não abrem nova tabela.
RE_TITULO_APENDICE = re.compile(r"^\s*(?:apendice\s+(?:ap\s*)?|ap\s*|anexo\s+(?:ap\s*)?)[-–nº°o.]*\s*0?([123])\b")
CABECALHOS = [
    ("meses_mora", r"meses\s*(de\s*)?mora|^meses$|n[ºo°]?\s*meses"),
    ("juros_mora", r"juros\s*(de\s*)?mora|juros\s*morat|juros\s*legais|^mora$"),
    ("saldo_anterior", r"saldo\s*(inicial|anterior|devedor\s*inicial|ant)"),
    ("saldo", r"saldo\s*(final|atual|devedor\s*final|apos)|^saldo(\s*devedor)?$"),
    ("amortizacao", r"amortiz"),
    ("juros", r"^juros|juros\s*(remunerat|do\s*periodo|do\s*mes|contratuais)"),
    ("prestacao", r"presta|valor\s*da\s*parcela|^parcela\s*contratual"),
    ("pago", r"pago|pagamento\s*efetu"),
    ("devido", r"devid|^correto|valor\s*correto|^revisad"),
    ("diferenca", r"diferen|^dif\.?$"),
    ("restituir", r"restitu|repeti|indebito|dobro"),
    ("fator", r"fator|indice|coef"),
    ("corrigido", r"corrigid|corrigido|correcao|atualiz\w*\s*monet"),
    ("subtotal", r"subtotal"),
    ("total", r"total|atualizado"),
    ("data", r"venc|^data|dt\.?\s*pag|pagamento\s*em|data\s*pag"),
    ("numero", r"^n[ºo°]?\.?$|^parc\.?$|^parcela$|^item$|^#$|^n[ºo°]?\s*parc"),
]
METODOLOGIA = [
    ("capitalização", r"capitaliza\w*\s+(diaria|mensal|anual)"),
    ("capitalização", r"(sem|afastad\w*|exclu\w*)\s+(a\s+)?capitaliza"),
    ("sistema de amortização", r"tabela price|sistema frances|\bsac\b|metodo (de )?gauss|juros simples|juros compostos"),
    ("base de dias", r"(base|ano)\s*(de\s*)?(360|365)\s*dias|dias corridos|ano comercial|ano civil"),
    ("taxa", r"taxa media (de mercado)?|bacen|banco central|serie \d{4,5}"),
    ("correção monetária", r"\b(inpc|ipca-e|ipca|igp-m|igpm|tr\b|selic|tabela pratica[^.;\n]{0,40})"),
    ("juros de mora", r"juros (de mora|moratorios|legais)[^.;\n]{0,60}"),
    ("restituição", r"(em dobro|forma simples|repeticao do indebito)[^.;\n]{0,60}"),
    ("arredondamento", r"arredond\w*[^.;\n]{0,60}|trunc\w*[^.;\n]{0,40}"),
    ("pro rata", r"pro[ -]rata( die)?"),
    ("data-base", r"data[- ]base[^.;\n]{0,40}|atualizad\w* ate [^.;\n]{0,30}"),
]


def _num(s: str) -> Decimal | None:
    t = s.strip().replace("R$", "").replace(" ", "").replace("%", "")
    neg = t.startswith("(") and t.endswith(")") or t.startswith("-")
    t = t.strip("()-")
    if not re.fullmatch(r"\d{1,3}(\.\d{3})*(,\d+)?|\d+(,\d+)?|\d+\.\d+", t):
        return None
    try:
        v = Decimal(t.replace(".", "").replace(",", ".")) if "," in t or re.fullmatch(r"\d{1,3}(\.\d{3})+", t) else Decimal(t)
    except InvalidOperation:
        return None
    return -v if neg else v


def _data(s: str) -> date | None:
    m = re.fullmatch(RE_DATA_NUM, s.strip())
    return data_num(*m.groups()) if m else None


def _coluna(texto_cabecalho: str) -> str | None:
    n = normalizar(" ".join(texto_cabecalho.split()))
    n = re.sub(r"\(\s*(r\$|%)\s*\)|\br\$", "", n).strip(" .:-")      # "Saldo Devedor (R$)" -> "saldo devedor"
    for nome, pad in CABECALHOS:
        if re.search(pad, n):
            return nome
    return None


def titulo_apendice(linha: str) -> str | None:
    m = RE_TITULO_APENDICE.match(normalizar(linha))
    return f"AP0{m.group(1)}" if m else None


# --- PDF -------------------------------------------------------------------------------------

def _linhas_da_pagina(pagina) -> list[dict]:
    """Linhas da página: {'y', 'celulas': [(x0, x1, texto)], 'palavras': [(x0, x1, texto)]}."""
    palavras = pagina.get_text("words")   # x0, y0, x1, y1, texto, bloco, linha, nº
    por_y: dict[int, list] = {}
    for x0, y0, x1, y1, txt, *_ in palavras:
        chave = round((y0 + y1) / 2 / 3)    # tolerância vertical de ~3 pt
        por_y.setdefault(chave, []).append((x0, x1, txt, (y0 + y1) / 2))
    linhas = []
    for _, ws in sorted(por_y.items()):
        ws.sort()
        celulas: list[list] = []
        for x0, x1, txt, _y in ws:
            if celulas and x0 - celulas[-1][1] < 6:      # mesma célula
                celulas[-1][1] = x1
                celulas[-1][2] += " " + txt
            else:
                celulas.append([x0, x1, txt])
        linhas.append({"y": sum(w[3] for w in ws) / len(ws), "celulas": [tuple(c) for c in celulas],
                       "palavras": [(w[0], w[1], w[2]) for w in ws]})
    return linhas


def _grupos_cabecalho(linhas: list[dict], i: int) -> list[tuple[float, float, str]]:
    """Colunas do cabeçalho a partir das PALAVRAS (não das células): separa por espaço > 4 pt
    (ex.: 'Fator INPC' | 'Corrigida (R$)') e junta rótulos em duas linhas que se sobrepõem
    na horizontal (ex.: 'Meses' / 'Mora'). Devolve (x0, x1, coluna)."""
    y = linhas[i]["y"]
    faixa = [l for l in linhas if abs(l["y"] - y) <= 7 and not any(_num(c[2]) or _data(c[2]) for c in l["celulas"])]
    grupos: list[list] = []
    for l in faixa:
        atual: list | None = None
        for x0, x1, t in l["palavras"]:
            if atual is not None and x0 - atual[1] <= 4:
                atual[1], atual[2] = x1, atual[2] + " " + t
            else:
                atual = [x0, x1, t, l["y"]]
                grupos.append(atual)
    grupos.sort(key=lambda g: (g[0], g[3]))
    fundidos: list[list] = []
    for g in grupos:                       # rótulo quebrado em linhas: mesmo intervalo horizontal
        alvo = next((f for f in fundidos if min(f[1], g[1]) - max(f[0], g[0]) > 0.5 * min(g[1] - g[0], f[1] - f[0])
                     and abs(f[3] - g[3]) > 1), None)
        if alvo:
            alvo[0], alvo[1] = min(alvo[0], g[0]), max(alvo[1], g[1])
            alvo[2] = (alvo[2] + " " + g[2]) if alvo[3] < g[3] else (g[2] + " " + alvo[2])
        else:
            fundidos.append(list(g))
    return [(f[0], f[1], col) for f in fundidos if (col := _coluna(f[2]))]


def ler_parecer_pdf(dados: bytes, nome: str) -> Parecer:
    import pymupdf

    tabelas: dict[str, TabelaPericial] = {}
    metodologia: list[IndicioMetodologia] = []
    avisos: list[str] = []
    atual: str | None = None
    cab: list[tuple[float, float, str]] = []     # (x0, x1, coluna)
    with pymupdf.open(stream=dados, filetype="pdf") as pdf:
        for npag, pg in enumerate(pdf, start=1):
            texto = pg.get_text("text")
            if len(texto.strip()) < 20:
                avisos.append(f"página {npag} sem texto (digitalizada?): não lida")
                continue
            metodologia += _metodologia(texto, npag)
            linhas = _linhas_da_pagina(pg)
            ja_cabecalho: set[int] = set()
            for i, linha in enumerate(linhas):
                celulas = linha["celulas"]
                linha_txt = " ".join(c[2] for c in celulas)
                if (ap := titulo_apendice(linha_txt)) and len(celulas) <= 3:
                    atual = ap
                    cab = []
                    continue
                if atual is None or i in ja_cabecalho:
                    continue
                mapeadas = [_coluna(c[2]) for c in celulas]
                if sum(1 for col in mapeadas if col) >= 3 and not any(_num(c[2]) for c in celulas):
                    cab = _grupos_cabecalho(linhas, i)
                    ja_cabecalho |= {j for j, l in enumerate(linhas) if abs(l["y"] - linha["y"]) <= 7}
                    tab = tabelas.setdefault(atual, TabelaPericial(apendice=atual, colunas=[], linhas=[], origem=f"{nome} (PDF)"))
                    for _, _, col in cab:
                        if col not in tab.colunas:
                            tab.colunas.append(col)
                    continue
                if not cab:
                    continue
                _linha_de_dados(tabelas[atual], celulas, cab, npag)
    for t in tabelas.values():
        if not t.linhas:
            t.avisos.append("cabeçalho encontrado, mas nenhuma linha de dados reconhecida")
    if not tabelas:
        avisos.append("nenhuma tabela de apêndice (AP01/AP02/AP03) reconhecida no PDF — use a planilha do parecer")
    return Parecer(arquivo=nome, sha256=hashlib.sha256(dados).hexdigest(), tabelas=tabelas,
                   metodologia=metodologia, avisos=avisos)


def _coluna_do_valor(x0: float, x1: float, cab: list[tuple[float, float, str]]) -> str | None:
    """Coluna do valor: maior sobreposição horizontal com o cabeçalho; sem sobreposição, a coluna
    cuja borda direita está mais próxima (números costumam ser alinhados à direita)."""
    melhor, sobre = None, 0.0
    for c0, c1, col in cab:
        s = min(x1, c1) - max(x0, c0)
        if s > sobre:
            melhor, sobre = col, s
    if melhor:
        return melhor
    return min(cab, key=lambda c: min(abs(c[1] - x1), abs((c[0] + c[1]) / 2 - (x0 + x1) / 2)))[2] if cab else None


def _linha_de_dados(tab: TabelaPericial, celulas, cab, npag: int) -> None:
    primeiro = normalizar(celulas[0][2])
    eh_total = primeiro.startswith("total")
    valores: dict[str, Decimal] = {}
    numero = None
    data = None
    for x0, x1, txt in celulas:
        col = _coluna_do_valor(x0, x1, cab)
        if col is None:
            continue
        if (d := _data(txt)) is not None:
            data = d
            continue
        v = _num(txt)
        if v is None:
            continue
        if col == "numero" and v == v.to_integral_value() and numero is None:
            numero = int(v)
        elif col not in ("numero", "data"):
            valores[col] = v
    if eh_total:
        tab.totais.update(valores)
    elif valores and (numero is not None or data is not None):
        tab.linhas.append(LinhaPericial(numero=numero, data=data, valores=valores, pagina=npag,
                                        texto=" | ".join(c[2] for c in celulas)))


def _metodologia(texto: str, npag: int) -> list[IndicioMetodologia]:
    # só texto corrido: células de tabela (linhas curtas ou com vários números) geram falsos indícios
    corrido = [l for l in texto.split("\n")
               if len(l.strip()) >= 25 and len(re.findall(r"\d[\d.,/]*", l)) < 5]
    texto = "\n".join(corrido)
    norm = normalizar(texto).replace("\n", " ")
    out = []
    for tema, pad in METODOLOGIA:
        for m in re.finditer(pad, norm):
            a, b = max(0, m.start() - 80), min(len(norm), m.end() + 80)
            out.append(IndicioMetodologia(tema=tema, descricao=m.group(0).strip(), pagina=npag,
                                          trecho=" ".join(texto.replace("\n", " ")[a:b].split())))
    return out


# --- Planilhas do parecer -------------------------------------------------------------------

def ler_tabela_planilha(apendice: str, linhas: list[list[str]], origem: str) -> TabelaPericial:
    if not linhas:
        raise ValueError(f"{apendice}: planilha vazia")
    cab = [_coluna(c or "") for c in linhas[0]]
    if sum(1 for c in cab if c) < 3:
        raise ValueError(f"{apendice}: cabeçalho não reconhecido ({linhas[0]})")
    tab = TabelaPericial(apendice=apendice, colunas=[c for c in cab if c], linhas=[], origem=origem)
    mapa = [(float(k), float(k) + 1, c) for k, c in enumerate(cab) if c]
    for i, l in enumerate(linhas[1:], start=2):
        # só colunas com cabeçalho reconhecido (evita atribuir célula órfã à coluna vizinha)
        celulas = [(float(k), float(k) + 1, str(v or "")) for k, v in enumerate(l) if k < len(cab) and cab[k]]
        if l and normalizar(str(l[0] or "")).startswith("total"):
            celulas.insert(0, (-2.0, -1.0, "Total"))
        _linha_de_dados(tab, celulas, mapa, i)
    return tab


def _celula(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, float):
        return str(Decimal(repr(v)))
    return str(v)


def ler_parecer_xlsx(dados: bytes, nome: str) -> dict[str, TabelaPericial]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(dados), data_only=True, read_only=True)
    out = {}
    for ws in wb.worksheets:
        m = RE_APENDICE.search(normalizar(ws.title))
        if not m:
            continue
        ap = f"AP0{m.group(1)}"
        linhas = [[_celula(c) for c in row] for row in ws.iter_rows(values_only=True)]
        linhas = [l for l in linhas if any(x.strip() for x in l)]
        # o cabeçalho é a primeira linha com 3+ colunas reconhecidas
        ini = next((i for i, l in enumerate(linhas) if sum(1 for c in l if _coluna(c)) >= 3), None)
        if ini is None:
            continue
        out[ap] = ler_tabela_planilha(ap, linhas[ini:], f"{nome} / aba {ws.title}")
    return out


def ler_parecer_csv(dados: bytes, nome: str) -> TabelaPericial:
    import csv
    m = RE_APENDICE.search(normalizar(Path(nome).stem))
    if not m:
        raise ValueError(f"{nome}: o nome do arquivo deve indicar o apêndice (ex.: AP01.csv)")
    texto = dados.decode("utf-8-sig")
    linhas = list(csv.reader(io.StringIO(texto), delimiter=";" if ";" in texto else ","))
    return ler_tabela_planilha(f"AP0{m.group(1)}", [l for l in linhas if any(x.strip() for x in l)], nome)


# --- Anonimização ------------------------------------------------------------------------------

def verificar_anonimizacao(texto: str) -> list[str]:
    """Indícios de dados pessoais remanescentes (tipos e quantidades — sem expor os dados)."""
    ps = Pseudonimizador()
    ps.descobrir_nomes(texto)
    achados = residuos(texto) + [f"NOME: {n[:2]}…" for n in ps.mapa]
    contagem: dict[str, int] = {}
    for a in achados:
        tipo = a.split(":")[0]
        if tipo in ("PROCESSO",):      # número de processo não identifica a pessoa por si; registrar como aviso
            continue
        contagem[tipo] = contagem.get(tipo, 0) + 1
    return [f"{t}: {n} ocorrência(s)" for t, n in sorted(contagem.items())]


def texto_pdf(dados: bytes) -> str:
    import pymupdf
    with pymupdf.open(stream=dados, filetype="pdf") as pdf:
        return "\n".join(p.get_text("text") for p in pdf)
