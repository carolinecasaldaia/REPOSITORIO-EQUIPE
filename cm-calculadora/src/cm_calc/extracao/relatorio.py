"""Quadro de parâmetros em Markdown, para conferência (a interface vem na Fase 4)."""

from __future__ import annotations

from .aprovacao import bloqueios
from .modelos import QuadroParametros, StatusParametro as S

ICONE = {S.CONFIRMADO: "✅", S.EXTRAIDO: "🔎", S.CONFLITANTE: "⚠️", S.INSUFICIENTE: "⚠️", S.AUSENTE: "❌",
         S.REJEITADO: "⛔", S.INFORMATIVO: "ℹ️"}


def _cel(s) -> str:
    return str(s or "").replace("|", "/").replace("\n", " ")


def quadro_markdown(q: QuadroParametros) -> str:
    L = [f"# Quadro de parâmetros — caso {q.caso_id}",
         f"Gerado em {q.gerado_em:%d/%m/%Y %H:%M} · extrator {q.versao_extrator} · **documento interno, sujeito a conferência**", ""]
    pend = bloqueios(q)
    L += [f"**Situação:** {'pronto para o cálculo' if not pend else f'{len(pend)} pendência(s) impedem o cálculo definitivo'}", ""]

    L += ["## Documentos", "", "| Arquivo | Páginas | Tipo | Data | Confiança |", "|---|---|---|---|---|"]
    for d in q.documentos:
        L.append(f"| {_cel(d.arquivo)} | {d.paginas} | {d.tipo.value} | {d.data or ''} | {d.confianca} |")

    grupos: dict[str, list] = {}
    for p in q.parametros.values():
        grupos.setdefault(p.grupo, []).append(p)
    for g in ("contrato", "composição", "título judicial", "cálculo"):
        if g not in grupos:
            continue
        L += ["", f"## Parâmetros — {g}", "", "| | Parâmetro | Valor | Detalhes | Fonte | Observações |", "|---|---|---|---|---|---|"]
        for p in grupos[g]:
            val = p.valor_confirmado or p.exibicao or p.valor or ""
            if p.status is S.CONFLITANTE:
                val = " / ".join(f"{a.exibicao} ({a.fonte.referencia()})" for a in p.alternativas)
            det = ", ".join(f"{k}: {v}" for k, v in p.detalhes_vigentes().items() if v)
            fonte = "; ".join(f.referencia() for f in p.fontes[:2])
            L.append(f"| {ICONE[p.status]} | {_cel(p.descricao)} | {_cel(val)} | {_cel(det)} | {_cel(fonte)} | "
                     f"{_cel('; '.join(p.observacoes))} |")

    L += ["", f"## Pagamentos ({q.pagamentos_status.value})", "", "| Parcela | Vencimento | Pagamento | Valor | Encargos | Fonte |", "|---|---|---|---|---|---|"]
    for pg in q.pagamentos:
        L.append(f"| {pg.parcela or '?'} | {pg.vencimento or ''} | {pg.data_pagamento or '?'} | {pg.valor or '?'} | "
                 f"{pg.encargos or ''} | {_cel(pg.fonte.referencia())} |")

    if q.modificacoes:
        L += ["", "## Modificações do título por decisões posteriores", ""]
        L += [f"- {m.descricao}" for m in q.modificacoes]
    if q.alegacoes:
        L += ["", "## Alegações das partes NÃO reconhecidas no título (fora do cálculo)", ""]
        L += [f"- {a.tema.value} ({a.chave}) — {a.fonte.referencia()}" for a in q.alegacoes]

    L += ["", "## Ocorrências", "", "| Tipo | Bloqueia | Descrição | Ciência |", "|---|---|---|---|"]
    for o in q.ocorrencias:
        L.append(f"| {o.tipo.value} | {'sim' if o.bloqueia else 'não'} | {_cel(o.texto)} | {o.ciencia_por or ''} |")
    if pend:
        L += ["", "## Pendências para o cálculo definitivo", ""] + [f"- {x}" for x in pend]
    return "\n".join(L) + "\n"
