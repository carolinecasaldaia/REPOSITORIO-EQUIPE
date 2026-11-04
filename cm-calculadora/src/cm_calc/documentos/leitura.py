"""Importação de arquivos: PDF (avulso ou processo completo), planilhas e texto.

- PDF: texto extraído localmente (PyMuPDF). Página sem camada de texto é
  sinalizada como "OCR necessário" — o OCR (Tesseract) não está instalado e
  não é executado automaticamente.
- Processo completo: segmentado pelos marcadores (sumário) do PDF quando
  existirem; senão, pelos cabeçalhos detectados em cada página.
- Planilhas: CSV e XLSX, com cabeçalhos normalizados.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from .classificacao import classificar, embargos_contra_acordao, inicia_documento
from .modelos import Documento, Pagina, TipoDocumento
from .texto import datas_no_texto, normalizar

RE_PJE = re.compile(r"Num\.\s*(\d{5,})\s*-\s*P[áa]g\.\s*(\d+)")


class ResultadoLeitura:
    def __init__(self) -> None:
        self.documentos: list[Documento] = []
        self.avisos: list[str] = []


def sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def ler_arquivo(caminho: Path) -> ResultadoLeitura:
    dados = caminho.read_bytes()
    ext = caminho.suffix.lower()
    if ext == ".pdf":
        return ler_pdf(dados, caminho.name)
    if ext in (".csv", ".xlsx"):
        return ler_planilha(dados, caminho.name, ext)
    if ext == ".txt":
        r = ResultadoLeitura()
        texto = dados.decode("utf-8")
        r.documentos.append(_documento(f"{caminho.name}#1", caminho.name, sha256(dados),
                                       [Pagina(numero=1, texto=texto)]))
        return r
    raise ValueError(f"formato não suportado: {ext} (aceitos: .pdf, .csv, .xlsx, .txt)")


def ler_pdf(dados: bytes, nome: str) -> ResultadoLeitura:
    import pymupdf

    r = ResultadoLeitura()
    h = sha256(dados)
    with pymupdf.open(stream=dados, filetype="pdf") as pdf:
        paginas = []
        for i, pg in enumerate(pdf, start=1):
            texto = pg.get_text("text")
            m = RE_PJE.search(texto)
            paginas.append(Pagina(numero=i, texto=texto,
                                  referencia_pje=f"Num. {m.group(1)} - Pág. {m.group(2)}" if m else None))
        toc = pdf.get_toc()

    sem_texto = [p.numero for p in paginas if not p.tem_texto]
    if sem_texto:
        r.avisos.append(f"{nome}: página(s) {_faixas(sem_texto)} sem texto (digitalizadas?). "
                        "OCR necessário — conferência manual dessas páginas.")

    for k, grupo in enumerate(_segmentar(paginas, toc), start=1):
        r.documentos.append(_documento(f"{nome}#{k}", nome, h, grupo))
    return r


def _segmentar(paginas: list[Pagina], toc: list) -> list[list[Pagina]]:
    if toc:
        inicios = sorted({max(1, e[2]) for e in toc if e[0] == 1})
        if inicios and inicios[0] != 1:
            inicios.insert(0, 1)
        limites = inicios + [len(paginas) + 1]
        return [paginas[a - 1:b - 1] for a, b in zip(limites, limites[1:]) if paginas[a - 1:b - 1]]
    grupos: list[list[Pagina]] = []
    for p in paginas:
        if not grupos or (p.tem_texto and inicia_documento(p.texto)):
            grupos.append([p])
        else:
            grupos[-1].append(p)
    return grupos


def _documento(id_: str, arquivo: str, h: str, paginas: list[Pagina], tipo_forcado: TipoDocumento | None = None) -> Documento:
    texto = "\n".join(p.texto for p in paginas)
    if tipo_forcado:
        tipo, conf, ind = tipo_forcado, 1.0, ["formato do arquivo"]
    else:
        tipo, conf, ind = classificar(texto)
    datas = datas_no_texto(texto)
    data = None
    if datas:
        # decisões: data da assinatura (última); demais: primeira data relevante
        from .modelos import DECISORIOS
        data = datas[-1][1] if tipo in DECISORIOS else datas[0][1]
    return Documento(id=id_, arquivo=arquivo, sha256=h, tipo=tipo, paginas=paginas, confianca=conf,
                     indicios=ind, data=data,
                     instancia_superior=tipo is TipoDocumento.EMBARGOS_DECISAO and embargos_contra_acordao(texto))


def _faixas(nums: list[int]) -> str:
    return ", ".join(str(n) for n in nums)


# --- Planilhas -----------------------------------------------------------------------

def _celula(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, float):
        # fronteira de entrada: número de planilha vira texto decimal exato da célula
        return str(Decimal(repr(v)))
    return str(v).strip()


def ler_planilha(dados: bytes, nome: str, ext: str) -> ResultadoLeitura:
    r = ResultadoLeitura()
    if ext == ".csv":
        texto = dados.decode("utf-8-sig")
        dialeto = csv.Sniffer().sniff(texto.splitlines()[0], delimiters=";,\t")
        linhas = [[c.strip() for c in l] for l in csv.reader(io.StringIO(texto), dialeto)]
    else:
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(dados), data_only=True, read_only=True)
        ws = wb.worksheets[0]
        linhas = [[_celula(c) for c in row] for row in ws.iter_rows(values_only=True)]
        if any(isinstance(c, float) for row in ws.iter_rows(values_only=True) for c in row):
            r.avisos.append(f"{nome}: células numéricas convertidas a partir do valor gravado no Excel; conferir centavos.")
    linhas = [l for l in linhas if any(c for c in l)]
    if not linhas:
        r.avisos.append(f"{nome}: planilha vazia")
        return r
    cab = [normalizar(c) for c in linhas[0]]
    tabela = [dict(zip(cab, l)) for l in linhas[1:]]
    texto = "\n".join(";".join(l) for l in linhas)
    doc = _documento(f"{nome}#1", nome, sha256(dados), [Pagina(numero=1, texto=texto)], TipoDocumento.PLANILHA)
    doc.tabela = tabela
    r.documentos.append(doc)
    return r
