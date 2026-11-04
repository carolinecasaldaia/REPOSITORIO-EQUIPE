"""Pagamentos: comprovantes (PDF/texto) e planilhas (CSV/XLSX).

Cruzamento: a mesma parcela em fontes diferentes com valor ou data distintos
gera contradição; parcela repetida na mesma fonte também.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from ..documentos.modelos import Documento, Fonte, fonte_de
from ..documentos.texto import RE_DATA_NUM, RE_VALOR, data_num, normalizar, valor_br
from .modelos import Ocorrencia, PagamentoExtraido, TipoOcorrencia

RV = RE_VALOR.replace("R\\$", "r\\$")


def _data_apos(norm: str, rotulo: str) -> tuple[date | None, int, int]:
    m = re.search(rotulo + r"[^\d\n]{0,25}" + RE_DATA_NUM, norm)
    if not m:
        return None, -1, -1
    return data_num(*m.groups()[-3:]), m.start(), m.end()


def extrair_comprovante(doc: Documento) -> PagamentoExtraido:
    texto, norm = doc.texto, normalizar(doc.texto)
    lacunas = []
    m = re.search(r"parcela\s*(?:n[ºo°]\.?\s*)?[:\-]?\s*(\d{1,3})(?:\s*(?:/|de)\s*\d{1,3})?", norm)
    parcela = int(m.group(1)) if m else None
    venc, *_ = _data_apos(norm, r"vencimento")
    pag, a, b = _data_apos(norm, r"(data (do|de|da) (pagamento|transacao|operacao)|pago em|pagamento em)")
    v = re.search(r"(valor (total )?pago|total pago|valor do pagamento|valor cobrado)[^\n]{0,25}?" + RV, norm)
    e = re.search(r"(encargos|multa e juros|acrescimos)[^\n]{0,25}?" + RV, norm)
    for nome, val in (("número da parcela", parcela), ("data do pagamento", pag), ("valor pago", v)):
        if val is None:
            lacunas.append(nome)
    pos = v.start() if v else (a if a >= 0 else 0)
    return PagamentoExtraido(
        parcela=parcela, vencimento=venc, data_pagamento=pag,
        valor=str(valor_br(v.groups()[-1])) if v else None,
        encargos=str(valor_br(e.groups()[-1])) if e else None,
        fonte=fonte_de(doc, pos, (v.end() if v else pos + 40)), lacunas=lacunas,
    )


def _num(s: str) -> Decimal | None:
    s = (s or "").replace("R$", "").strip()
    if not s:
        return None
    try:
        return valor_br(s) if "," in s else Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _data_celula(s: str) -> date | None:
    m = re.search(RE_DATA_NUM, s or "")
    if m:
        return data_num(*m.groups())
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s or "")
    return data_num(m.group(3), m.group(2), m.group(1)) if m else None


def _coluna(cab: list[str], *regras: str) -> str | None:
    for r in regras:
        for c in cab:
            if re.search(r, c):
                return c
    return None


def extrair_planilha(doc: Documento) -> tuple[list[PagamentoExtraido], list[str]]:
    avisos: list[str] = []
    if not doc.tabela:
        return [], [f"{doc.arquivo}: planilha sem linhas"]
    cab = list(doc.tabela[0].keys())
    c_parc = _coluna(cab, r"parcela", r"^n[ºo°]?\.?$", r"numero")
    c_venc = _coluna(cab, r"venc")
    c_pag = _coluna(cab, r"data.*pag|pagamento.*data|^pagamento$|pago em|^data$")
    c_val = _coluna(cab, r"valor.*pago|pago$", r"^valor$", r"valor")
    c_enc = _coluna(cab, r"encargo|multa|acrescimo")
    faltando = [n for n, c in (("parcela", c_parc), ("data de pagamento", c_pag), ("valor", c_val)) if c is None]
    if faltando:
        avisos.append(f"{doc.arquivo}: colunas não identificadas: {', '.join(faltando)} (cabeçalho: {cab})")
    out = []
    for i, linha in enumerate(doc.tabela, start=2):
        lacunas = []
        try:
            parcela = int(Decimal(linha.get(c_parc, "") or "x")) if c_parc else None
        except InvalidOperation:
            parcela = None
        pag = _data_celula(linha.get(c_pag, "")) if c_pag else None
        val = _num(linha.get(c_val, "")) if c_val else None
        enc = _num(linha.get(c_enc, "")) if c_enc else None
        if parcela is None:
            lacunas.append("número da parcela")
        if pag is None:
            lacunas.append("data do pagamento")
        if val is None:
            lacunas.append("valor pago")
        fonte = Fonte(documento_id=doc.id, arquivo=doc.arquivo, tipo_documento=doc.tipo, pagina=1,
                      trecho=f"linha {i}: " + "; ".join(f"{k}={v}" for k, v in linha.items()))
        out.append(PagamentoExtraido(parcela=parcela, vencimento=_data_celula(linha.get(c_venc, "")) if c_venc else None,
                                     data_pagamento=pag, valor=str(val) if val is not None else None,
                                     encargos=str(enc) if enc is not None else None, fonte=fonte, lacunas=lacunas))
    return out, avisos


def cruzar_pagamentos(pagamentos: list[PagamentoExtraido]) -> list[Ocorrencia]:
    ocorr: list[Ocorrencia] = []
    por_parcela: dict[int, list[PagamentoExtraido]] = {}
    for p in pagamentos:
        if p.parcela is not None:
            por_parcela.setdefault(p.parcela, []).append(p)
        if p.lacunas:
            ocorr.append(Ocorrencia(
                id=f"pag-lacuna-{len(ocorr)}", tipo=TipoOcorrencia.INSUFICIENTE, bloqueia=True,
                texto=f"Pagamento sem {', '.join(p.lacunas)} ({p.fonte.referencia()}).", fontes=[p.fonte]))
    for n, lista in sorted(por_parcela.items()):
        if len(lista) < 2:
            continue
        mesma_fonte = {}
        for p in lista:
            mesma_fonte.setdefault(p.fonte.documento_id, []).append(p)
        for doc_id, ps in mesma_fonte.items():
            if len(ps) > 1:
                ocorr.append(Ocorrencia(
                    id=f"pag-dup-{n}-{doc_id}", tipo=TipoOcorrencia.CONTRADICAO, bloqueia=True,
                    texto=f"Parcela {n} aparece {len(ps)} vezes em {ps[0].fonte.arquivo} "
                          "(pagamento em duplicidade ou erro de digitação?).", fontes=[p.fonte for p in ps]))
        valores = {p.valor for p in lista if p.valor}
        datas = {p.data_pagamento for p in lista if p.data_pagamento}
        if len(valores) > 1 or len(datas) > 1:
            det = "; ".join(f"{p.fonte.arquivo}: {p.valor} em {p.data_pagamento}" for p in lista)
            ocorr.append(Ocorrencia(
                id=f"pag-contradicao-{n}", tipo=TipoOcorrencia.CONTRADICAO, bloqueia=True,
                texto=f"Parcela {n} com valores/datas diferentes entre as fontes: {det}.",
                fontes=[p.fonte for p in lista]))
    return ocorr
