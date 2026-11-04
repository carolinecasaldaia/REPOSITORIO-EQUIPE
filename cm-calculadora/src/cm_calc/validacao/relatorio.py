"""Relatório comparativo da validação: Markdown (leitura) e XLSX (conferência linha a linha)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from ..motor.numeros import brl
from .comparacao import ResultadoValidacao
from .modelos import ROTULO_COLUNA, Classe, Parecer

COR = {Classe.IDENTICO: "E6F4EA", Classe.CENTAVO: "EEF3FB", Classe.ACUMULADO: "FFF6DB", Classe.DIVERGENTE: "FBE3E3",
       Classe.SEM_PERITA: "F2F2F2"}


def _v(x) -> str:
    return "" if x is None else brl(x) if isinstance(x, Decimal) else str(x)


def resumo_classes(rv: ResultadoValidacao) -> dict[str, Counter]:
    out: dict[str, Counter] = {}
    for c in rv.comparacoes:
        out.setdefault(c.apendice, Counter())[c.classe] += 1
    return out


def markdown(rv: ResultadoValidacao, parecer: Parecer, caso: str) -> str:
    L = [f"# Validação pericial — {caso}", "",
         f"Gerado em {datetime.now():%d/%m/%Y %H:%M}. Parecer: `{parecer.arquivo}` (SHA-256 {parecer.sha256[:16]}…).",
         "Documento técnico interno. As divergências apontadas exigem análise da advogada e, se for o caso, do assistente técnico.", "",
         "## Metodologia da reconstrução", "",
         f"- Motor CM, parâmetros da ficha do caso: {rv.principal.descricao}.",
         "- Os resultados da perita não foram usados como entrada; servem apenas de comparação.",
         f"- Prestação pela Price com a taxa contratual: {_v(rv.principal.prestacao_price_contrato)} "
         f"(prestação contratada na ficha: {_v(rv.principal.parcela_regular_original)}).", ""]
    if parecer.metodologia:
        L += ["## Metodologia declarada no parecer (indícios localizados no texto)", ""]
        vistos = set()
        for m in parecer.metodologia:
            chave = (m.tema, m.descricao)
            if chave in vistos:
                continue
            vistos.add(chave)
            L.append(f"- **{m.tema}** — “{m.descricao}” (p. {m.pagina})")
        L.append("")
    L += ["## Resumo por apêndice", "", "| Apêndice | Idêntico | Centavo | Acumulado | Divergente |", "|---|---|---|---|---|"]
    for ap, c in sorted(resumo_classes(rv).items()):
        L.append(f"| {ap} | {c[Classe.IDENTICO]} | {c[Classe.CENTAVO]} | {c[Classe.ACUMULADO]} | {c[Classe.DIVERGENTE]} |")
    L += ["", "## Totais", "", "| Item | Perita | Motor | Diferença | % | Metodologia |", "|---|---|---|---|---|---|"]
    for t in rv.totais:
        L.append(f"| {t['item']} | {_v(t['perita'])} | {_v(t['motor'])} | {_v(t['diferenca'])} | "
                 f"{'' if t['diferenca_pct'] is None else str(t['diferenca_pct']) + '%'} | {t['metodologia']} |")
    L += ["", "## Consistência interna do parecer (independente do motor)", ""]
    L += [f"- {i.apendice}{' parcela ' + str(i.numero) if i.numero else ''}: {i.descricao}" for i in rv.inconsistencias] or \
         ["- Nenhuma inconsistência aritmética interna encontrada."]
    L += ["", "## Cenários de diagnóstico (aderência ao parecer)", ""]
    for ap, lista in rv.cenarios.items():
        if not lista:
            continue
        L += [f"### {ap}", "", "| Cenário | Erro máximo | Erro total | Linhas idênticas | Reproduz? |", "|---|---|---|---|---|"]
        for c in lista[:6]:
            L.append(f"| {c.nome} | {_v(c.erro_maximo)} | {_v(c.erro_absoluto_total)} | {c.linhas_identicas}/{c.linhas} | "
                     f"{'sim' if c.reproduz else 'não'} |")
        L.append("")
    div = [c for c in rv.comparacoes if c.classe is Classe.DIVERGENTE]
    L += [f"## Divergências ({len(div)})", "", "| Apêndice | Nº | Coluna | Perita | Motor | Diferença | % | Justificativa técnica |",
          "|---|---|---|---|---|---|---|---|"]
    for c in div[:200]:
        L.append(f"| {c.apendice} | {c.numero or ''} | {ROTULO_COLUNA.get(c.coluna, c.coluna)} | {_v(c.perita)} | {_v(c.motor)} | "
                 f"{_v(c.diferenca)} | {'' if c.diferenca_pct is None else str(c.diferenca_pct) + '%'} | {c.justificativa} |")
    if len(div) > 200:
        L.append(f"\n… {len(div) - 200} divergências adicionais na planilha.")
    if rv.principal.memoria.ressalvas or rv.principal.avisos or parecer.avisos:
        L += ["", "## Ressalvas e avisos", ""]
        L += [f"- {r.tipo.value}: {r.texto}" for r in rv.principal.memoria.ressalvas]
        L += [f"- aviso: {a}" for a in rv.principal.avisos + parecer.avisos]
    return "\n".join(L) + "\n"


def planilha(rv: ResultadoValidacao, destino: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Totais"
    negrito = Font(bold=True)
    ws.append(["Item", "Perita", "Motor", "Diferença", "Diferença %", "Metodologia"])
    for t in rv.totais:
        ws.append([t["item"], t["perita"], t["motor"], t["diferenca"], t["diferenca_pct"], t["metodologia"]])
    for ap in ("AP01", "AP02", "AP03"):
        comps = [c for c in rv.comparacoes if c.apendice == ap]
        if not comps:
            continue
        w = wb.create_sheet(ap)
        w.append(["Nº", "Data", "Coluna", "Perita", "Motor", "Diferença", "Diferença %", "Classificação", "Justificativa técnica"])
        for c in comps:
            w.append([c.numero, c.data, ROTULO_COLUNA.get(c.coluna, c.coluna), c.perita, c.motor, c.diferenca,
                      c.diferenca_pct, c.classe.value, c.justificativa])
            for cel in w[w.max_row][:8]:
                cel.fill = PatternFill("solid", fgColor=COR[c.classe])
    w = wb.create_sheet("Inconsistências perita")
    w.append(["Apêndice", "Nº", "Descrição"])
    for i in rv.inconsistencias:
        w.append([i.apendice, i.numero, i.descricao])
    w = wb.create_sheet("Cenários")
    w.append(["Apêndice", "Cenário", "Erro máximo", "Erro total", "Linhas idênticas", "Linhas", "Reproduz"])
    for ap, lista in rv.cenarios.items():
        for c in lista:
            w.append([ap, c.nome, c.erro_maximo, c.erro_absoluto_total, c.linhas_identicas, c.linhas, "sim" if c.reproduz else "não"])
    for folha in wb.worksheets:
        for cel in folha[1]:
            cel.font = negrito
        folha.freeze_panes = "A2"
        for col in folha.columns:
            folha.column_dimensions[col[0].column_letter].width = 16
    if "AP01" in wb.sheetnames:
        for nome in ("AP01", "AP02", "AP03"):
            if nome in wb.sheetnames:
                wb[nome].column_dimensions["I"].width = 90
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino
