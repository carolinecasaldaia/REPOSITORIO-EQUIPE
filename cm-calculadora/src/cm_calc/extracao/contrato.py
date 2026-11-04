"""Extração de dados contratuais (CCB / contrato de financiamento).

Estratégia: rótulo + valor na mesma linha ou na seguinte. Cada valor vira um
``Achado`` com página e trecho. Nada é completado por inferência: o que não
for localizado fica ausente no quadro.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..documentos.modelos import ALEGACOES, Documento, Natureza, TipoDocumento, fonte_de
from ..documentos.texto import RE_DATA_EXT, RE_DATA_NUM, RE_PERCENT, RE_VALOR, MESES, data_num, normalizar, percentual_br, valor_br
from .catalogo import ITENS, id_item
from .modelos import Achado

ROTULOS_VALOR = {
    "contrato.valor_liberado": r"valor (liquido )?(liberado|do credito liberado|entregue|liquido do credito)",
    "contrato.valor_financiado": r"valor (total )?(financiado|do financiamento|total do credito)",
    "contrato.valor_parcela": r"valor (da|de cada) (parcela|prestacao)",
    "contrato.valor_bem": r"valor (do bem|do veiculo)",
    "contrato.entrada": r"(valor da )?entrada\b",
}
ROTULOS_DATA = {
    "contrato.data_liberacao": r"data (de|da) (emissao|liberacao|contratacao)",
    "contrato.primeiro_vencimento": r"(vencimento da )?(1a|1ª|primeira) (parcela|prestacao)|primeiro vencimento",
}
RE_N_PARCELAS = [r"(quantidade|numero|n[ºo°]\.?) de (parcelas|prestacoes)\s*[:\-]?\s*(\d{1,3})",
                 r"(\d{1,3})\s*(parcelas|prestacoes) mensais"]
RE_CAPITALIZACAO = r"capitaliza\w*\s+(diaria|mensal|anual)"
RE_NUMERO = r"(cedula de credito bancario|contrato|ccb)[^\n]{0,25}?\bn[ºo°]?\.?\s*[:\-]?\s*([0-9][\w.\-/]{3,30})"
MENSAL = r"a\.?\s?m\.?|ao mes|mensal"
ANUAL = r"a\.?\s?a\.?|ao ano|anual"


def _linhas(texto: str) -> Iterator[tuple[int, str]]:
    pos = 0
    for linha in texto.split("\n"):
        yield pos, linha
        pos += len(linha) + 1


def _janela(norm: str, inicio: int, tamanho: int = 140) -> tuple[int, str]:
    """Do fim do rótulo até o fim da linha. Só avança para a linha seguinte se o
    restante da linha não tiver texto (rótulo isolado, valor embaixo) — evita
    capturar o valor de outro item listado na linha de baixo."""
    eol = norm.find("\n", inicio)
    eol = len(norm) if eol == -1 else eol
    resto = norm[inicio:eol]
    if re.search(r"[a-z0-9$]", resto):
        return inicio, resto[:tamanho]
    prox = norm.find("\n", eol + 1)
    prox = len(norm) if prox == -1 else prox
    return inicio, norm[inicio:min(prox, inicio + tamanho)]


def extrair_contrato(doc: Documento) -> list[Achado]:
    texto = doc.texto
    norm = normalizar(texto)
    natureza = Natureza.ALEGADO if doc.tipo in ALEGACOES else Natureza.CONTRATUAL
    achados: list[Achado] = []

    def add(campo, valor, exib, a, b, **det):
        achados.append(Achado(campo=campo, valor=valor, exibicao=exib, natureza=natureza,
                              fonte=fonte_de(doc, a, b), detalhes={k: str(v) for k, v in det.items()}))

    m = re.search(RE_NUMERO, norm)
    if m and doc.tipo is TipoDocumento.CONTRATO:
        add("contrato.numero", texto[m.start(2):m.end(2)], texto[m.start(2):m.end(2)], m.start(), m.end())

    for campo, rot in ROTULOS_VALOR.items():
        for r in re.finditer(rot, norm):
            ini, jan = _janela(norm, r.end())
            v = re.search(RE_VALOR.replace("R\\$", "r\\$"), jan)
            if v:
                s = v.group(1)
                add(campo, str(valor_br(s)), f"R$ {s}", r.start(), ini + v.end())

    for campo, rot in ROTULOS_DATA.items():
        for r in re.finditer(rot, norm):
            ini, jan = _janela(norm, r.end(), 80)
            d = _data(jan)
            if d:
                dt, fim = d
                add(campo, dt.isoformat(), dt.strftime("%d/%m/%Y"), r.start(), ini + fim)

    for pad in RE_N_PARCELAS:
        for r in re.finditer(pad, norm):
            n = next(g for g in r.groups()[::-1] if g and g.isdigit()) if pad == RE_N_PARCELAS[0] else r.group(1)
            add("contrato.n_parcelas", n, n, r.start(), r.end())

    # Taxas: linhas com 'juros'/'taxa' (excluídos mora, multa e CET) e linhas de CET
    for pos, linha in _linhas(norm):
        # só olha a linha seguinte se a do rótulo não tiver percentual (evita pegar o CET da linha de baixo)
        lin_ext = linha if "%" in linha else linha + " " + norm[pos + len(linha) + 1: pos + len(linha) + 80].split("\n")[0]
        e_cet = bool(re.search(r"custo efetivo total|\bcet\b", linha))
        e_juros = bool(re.search(r"juros|taxa", linha)) and not re.search(r"mora|multa|moratori|inadimpl", linha)
        if not (e_cet or e_juros):
            continue
        for p in re.finditer(RE_PERCENT + r"\s*(" + MENSAL + "|" + ANUAL + ")?", lin_ext):
            sufixo = p.group(2) or ""
            if not sufixo:
                sufixo = "anual" if re.search(r"anual|ao ano|a\.a", linha) else ("mensal" if re.search(r"mensal|ao mes|a\.m", linha) else "")
            periodo = "mensal" if re.match(MENSAL, sufixo) else ("anual" if re.match(ANUAL, sufixo) else None)
            if periodo is None:
                continue
            campo = ("contrato.cet_" if e_cet else "contrato.taxa_") + periodo
            frac = percentual_br(p.group(1))
            add(campo, str(frac), f"{p.group(1)}% {'a.m.' if periodo == 'mensal' else 'a.a.'}", pos + p.start(), pos + p.end())

    # Encargos de inadimplência
    for pos, linha in _linhas(norm):
        if re.search(r"multa", linha):
            p = re.search(RE_PERCENT, linha)
            if p:
                add("contrato.multa_moratoria", str(percentual_br(p.group(1))), f"{p.group(1)}%", pos + p.start(), pos + p.end())
        if re.search(r"juros (moratorios|de mora)", linha):
            p = re.search(RE_PERCENT + r"\s*(" + MENSAL + ")", linha)
            if p:
                add("contrato.juros_moratorios", str(percentual_br(p.group(1))), f"{p.group(1)}% a.m.", pos + p.start(), pos + p.end())
        if re.search(r"comissao de permanencia", linha):
            add("contrato.comissao_permanencia", "prevista", "prevista no contrato", pos, pos + len(linha))

    for r in re.finditer(RE_CAPITALIZACAO, norm):
        add("contrato.capitalizacao", r.group(1), f"capitalização {r.group(1)}", r.start(), r.end())

    achados.extend(_itens_de_custo(doc, norm, natureza))
    return achados


def _data(jan: str):
    m = re.search(RE_DATA_NUM, jan)
    if m:
        d = data_num(*m.groups())
        if d:
            return d, m.end()
    m = re.search(RE_DATA_EXT, jan)
    if m:
        d = data_num(m.group(1), str(MESES[m.group(2)]), m.group(3))
        if d:
            return d, m.end()
    return None


def _itens_de_custo(doc: Documento, norm: str, natureza: Natureza) -> list[Achado]:
    """Tarifas, seguros e IOF: valor e forma de pagamento (financiado / à vista / indefinida)."""
    out = []
    for chave, (tipo, pad) in ITENS.items():
        for r in re.finditer(pad, norm):
            ini, jan = _janela(norm, r.end(), 160)
            v = re.search(RE_VALOR.replace("R\\$", "r\\$"), jan)
            if not v:
                continue
            # forma de pagamento: só a(s) linha(s) do próprio item, nunca a vizinha
            linha_ini = norm.rfind("\n", 0, r.start()) + 1
            contexto = norm[linha_ini: ini + len(jan)]
            if re.search(r"a vista|pago diretamente|pago pelo (cliente|emitente)|nao financiad", contexto):
                forma = "à vista"
            elif re.search(r"financiad|incluso no financiamento|incluido no valor", contexto):
                forma = "financiado"
            else:
                forma = ""
            s = v.group(1)
            out.append(Achado(
                campo=f"contrato.item:{id_item(chave)}", valor=str(valor_br(s)), exibicao=f"R$ {s}",
                natureza=natureza, fonte=fonte_de(doc, r.start(), ini + v.end()),
                detalhes={"item": chave, "tipo": tipo.value, "forma": forma},
            ))
    return out
