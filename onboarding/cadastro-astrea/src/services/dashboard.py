#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dashboard financeiro dos casos abertos por esta automação (decisão dela,
23/09/2026): entrada paga, ação, estado, valor total do contrato e
parcelamento, mês a mês. É PÁGINA LOCAL — não uma página hospedada — porque
só assim a atualização de hora em hora funciona de verdade, pela mesma
automação que já roda no Mac, sem depender de ninguém estar presente para
empurrar dado nenhum (ver conversa de 23/09/2026 sobre a limitação real do
Artifact hospedado).

Só entra cliente cujo caso foi aberto por ESTA automação (status_caso
começando com "CASO ABERTO") — que, por sua vez, só existe para pasta vista
a partir do corte de 23/09/2026 (ver `config.data_corte_novos_casos`). Nada
do backlog antigo aparece aqui.

Dado financeiro nunca é estimado: o valor total do contrato e o
parcelamento vêm de reler a Cláusula 2ª do contrato assinado (ver
`src/extractors/contrato_ho.py`) a cada geração — não de um número
guardado que possa ficar desatualizado. O que não bate no padrão esperado
aparece como "—", nunca como um chute.
"""

import html
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

MESES_PT = ("janeiro", "fevereiro", "março", "abril", "maio", "junho",
           "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")


def _mes_rotulo(chave_mes: str) -> str:
    """'2026-09' -> 'Setembro de 2026'."""
    try:
        ano, mes = chave_mes.split("-")
        nome = MESES_PT[int(mes) - 1]
        return "%s de %s" % (nome.capitalize(), ano)
    except (ValueError, IndexError):
        return chave_mes


def _moeda(valor) -> str:
    if valor is None:
        return "—"
    texto = "%.2f" % valor
    inteiro, centavos = texto.split(".")
    inteiro_formatado = ""
    while len(inteiro) > 3:
        inteiro_formatado = "." + inteiro[-3:] + inteiro_formatado
        inteiro = inteiro[:-3]
    return "R$ %s%s,%s" % (inteiro, inteiro_formatado, centavos)


def _coletar_linha(config, log, registro):
    """
    Uma linha do dashboard: relê o contrato (fresco, nunca do dados_json
    guardado) e confere a entrada no Asaas. Erro num cliente vira uma linha
    com "—" nos campos que faltaram, e nunca derruba o resto do dashboard.
    """
    from src import asaas
    from src.extractors import contrato_ho

    linha = {
        "cliente": registro["nome_cliente"] or "",
        "cpf_cnpj": registro["cpf_cnpj"] or "",
        "quando": (registro["atualizado_em"] or "")[:16].replace("T", " "),
        "tipo_acao": None, "banco_adverso": None, "estado": None,
        "valor_total": None, "entrada_valor": None, "entrada_data": None,
        "parcelas_qtd": None, "parcelas_valor": None,
        "observacao": "",
    }

    try:
        pdfs = list(Path(registro["caminho"]).rglob("Contrato HO Assinado.pdf"))
        if not pdfs:
            linha["observacao"] = "Contrato assinado não encontrado na pasta."
            return linha
        resultado = contrato_ho.extrair(pdfs[0])
        dados = json.loads(registro["dados_json"] or "{}")
        bruto_tipo = (dados.get("tipo_acao") or {}).get("valor")
        from src.astrea import casos as C
        linha["tipo_acao"] = C.tipo_do_contrato(bruto_tipo) or bruto_tipo or None
        linha["banco_adverso"] = (dados.get("banco_adverso") or {}).get("valor") or None
        # A ficha grava o contratante em "pessoa" (não "contratante").
        contratante = (dados.get("pessoa") or dados.get("contratante") or {})
        linha["estado"] = (contratante.get("uf") or {}).get("valor") or None

        if resultado.valor_total_honorarios.valido:
            linha["valor_total"] = resultado.valor_total_honorarios.valor
        if resultado.entrada_valor.valido:
            linha["entrada_valor"] = resultado.entrada_valor.valor
        if resultado.entrada_data.valido:
            linha["entrada_data"] = resultado.entrada_data.valor
        if resultado.parcelas_qtd.valido:
            linha["parcelas_qtd"] = resultado.parcelas_qtd.valor
        if resultado.parcelas_valor.valido:
            linha["parcelas_valor"] = resultado.parcelas_valor.valor
    except Exception as erro:
        linha["observacao"] = "Falha ao reler o contrato: %s" % str(erro)[:120]
        log.alerta("Dashboard: falha ao reler contrato de %s: %s"
                  % (linha["cliente"], erro))

    # Valor de entrada REALMENTE PAGO vem do Asaas, não do contrato (o
    # contrato diz o combinado; o Asaas diz o que entrou de fato).
    try:
        if config.asaas_api_key and linha["cpf_cnpj"]:
            cobranca = asaas.entrada_paga(linha["cpf_cnpj"], config.asaas_api_key,
                                          config.asaas_texto_entrada)
            if cobranca:
                linha["entrada_valor"] = cobranca.get("value", linha["entrada_valor"])
    except asaas.ErroAsaas as erro:
        log.alerta("Dashboard: não consegui confirmar a entrada de %s no Asaas: %s"
                  % (linha["cliente"], erro))

    return linha


def coletar(config, log):
    """
    Devolve {mes: [linhas]} para todo cliente cujo caso foi aberto por esta
    automação (status_caso começando com "CASO ABERTO"), agrupado pelo mês
    em que o caso foi aberto.
    """
    from src.database.controle import Controle

    banco = Controle(config.banco)
    try:
        # Mesmo corte de `_clientes_aguardando_caso` (executar.py), e pelo
        # mesmo motivo: alguns clientes do backlog anterior a 23/09/2026 já
        # ficaram com status_caso "CASO ABERTO" gravado ANTES desta trava
        # existir (e alguns, corrigidos manualmente depois) — sem o filtro
        # por `visto_em`, eles apareceriam aqui de novo.
        linhas_banco = banco._conn.execute(
            "select nome_cliente, cpf_cnpj, caminho, dados_json, atualizado_em"
            " from processamentos where status_caso like 'CASO ABERTO%'"
            "   and visto_em >= ?"
            " order by atualizado_em", (config.data_corte_novos_casos,)).fetchall()
    finally:
        banco.fechar()

    por_mes = defaultdict(list)
    for registro in linhas_banco:
        mes = (registro["atualizado_em"] or "")[:7] or "sem-data"
        por_mes[mes].append(_coletar_linha(config, log, registro))
    return dict(por_mes)


def _resumo_do_mes(linhas):
    entradas = [l["entrada_valor"] for l in linhas if l["entrada_valor"] is not None]
    totais = [l["valor_total"] for l in linhas if l["valor_total"] is not None]
    por_acao = defaultdict(int)
    por_estado = defaultdict(int)
    for l in linhas:
        por_acao[l["tipo_acao"] or "Não identificada"] += 1
        por_estado[l["estado"] or "—"] += 1
    return {
        "total_clientes": len(linhas),
        "soma_entradas": sum(entradas) if entradas else None,
        "ticket_medio_entrada": (sum(entradas) / len(entradas)) if entradas else None,
        "soma_contratos": sum(totais) if totais else None,
        "ticket_medio_contrato": (sum(totais) / len(totais)) if totais else None,
        "por_acao": sorted(por_acao.items(), key=lambda kv: -kv[1]),
        "por_estado": sorted(por_estado.items(), key=lambda kv: -kv[1]),
    }


def _cabecalho(titulo):
    return """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s</title>
<style>
 :root { color-scheme: light dark; }
 body { font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
        margin: 0; padding: 28px; background: #fafafa; color: #1a1a1a; }
 h1 { font-size: 22px; margin: 0 0 4px; }
 .sub { color: #666; font-size: 13px; margin-bottom: 22px; }
 .barra-topo { display: flex; align-items: center; justify-content: space-between;
               flex-wrap: wrap; gap: 10px; margin-bottom: 6px; }
 button.atualizar { border: 1px solid #ccc; background: #fff; border-radius: 8px;
                    padding: 8px 14px; font-size: 13px; cursor: pointer; }
 button.atualizar:hover { background: #f0f0f0; }
 .abas { display: flex; gap: 6px; flex-wrap: wrap; margin: 18px 0 22px; }
 .aba { padding: 7px 14px; border-radius: 20px; font-size: 13px; cursor: pointer;
        background: #eee; color: #333; user-select: none; }
 .aba.ativa { background: #2b5fa8; color: #fff; }
 .mes { display: none; }
 .mes.ativo { display: block; }
 .cartoes { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 26px; }
 .cartao { border-radius: 10px; padding: 12px 16px; min-width: 150px;
           background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
 .cartao b { display: block; font-size: 22px; line-height: 1.2; }
 .cartao span { font-size: 12px; color: #666; }
 .duas-colunas { display: flex; gap: 18px; flex-wrap: wrap; margin-bottom: 26px; }
 .bloco { flex: 1; min-width: 260px; background: #fff; border-radius: 10px;
          padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
 .bloco h3 { font-size: 13px; text-transform: uppercase; letter-spacing: .03em;
             color: #555; margin: 0 0 12px; }
 .barra-linha { display: flex; align-items: center; gap: 8px; margin-bottom: 8px;
                font-size: 13px; }
 .barra-linha .rotulo { width: 150px; flex-shrink: 0; }
 .barra-linha .trilho { flex: 1; background: #eee; border-radius: 6px; height: 14px;
                        overflow: hidden; }
 .barra-linha .preenchido { background: #2b5fa8; height: 100%%; }
 .barra-linha .contagem { width: 28px; text-align: right; color: #555; }
 table { border-collapse: collapse; width: 100%%; background: #fff;
         border-radius: 10px; overflow: hidden; font-size: 13px;
         box-shadow: 0 1px 3px rgba(0,0,0,.08); }
 th, td { text-align: left; padding: 9px 12px; border-bottom: 1px solid #eee;
          vertical-align: top; }
 th { background: #f2f4f7; font-weight: 600; font-size: 12px;
      text-transform: uppercase; letter-spacing: .03em; color: #555; }
 tr:last-child td { border-bottom: none; }
 td.numero { text-align: right; font-variant-numeric: tabular-nums; }
 .obs { color: #a65c00; font-size: 12px; }
 .vazio { color: #666; background: #fff; padding: 18px; border-radius: 10px; }
 footer { margin-top: 34px; color: #888; font-size: 12px; }
 @media (prefers-color-scheme: dark) {
   body { background: #16181c; color: #e8e8e8; }
   .cartao, .bloco, table { background: #202329; box-shadow: none; }
   .cartao span { color: #999; }
   .bloco h3 { color: #bbb; }
   th { background: #262a31; color: #bbb; }
   th, td { border-color: #2e323a; }
   .aba { background: #2a2d33; color: #ddd; }
   .aba.ativa { background: #3a6fc4; }
   button.atualizar { background: #202329; color: #e8e8e8; border-color: #3a3e46; }
   .barra-linha .trilho { background: #2e323a; }
   .vazio { background: #202329; color: #aaa; }
 }
</style></head><body>""" % html.escape(titulo)


def _secao_mes(chave_mes: str, linhas: list, ativo: bool) -> str:
    resumo = _resumo_do_mes(linhas)
    partes = ['<div class="mes%s" id="mes-%s">' % (" ativo" if ativo else "", chave_mes)]

    partes.append('<div class="cartoes">')
    cartoes = [
        ("%d" % resumo["total_clientes"], "Casos abertos no mês"),
        (_moeda(resumo["soma_entradas"]), "Total de entradas pagas"),
        (_moeda(resumo["ticket_medio_entrada"]), "Ticket médio da entrada"),
        (_moeda(resumo["soma_contratos"]), "Soma dos contratos (total)"),
        (_moeda(resumo["ticket_medio_contrato"]), "Ticket médio do contrato"),
    ]
    for valor, rotulo in cartoes:
        partes.append('<div class="cartao"><b>%s</b><span>%s</span></div>'
                      % (html.escape(str(valor)), html.escape(rotulo)))
    partes.append("</div>")

    partes.append('<div class="duas-colunas">')
    for titulo, dados in (("Por ação", resumo["por_acao"]),
                         ("Por estado", resumo["por_estado"])):
        partes.append('<div class="bloco"><h3>%s</h3>' % html.escape(titulo))
        maximo = max((n for _, n in dados), default=1)
        for rotulo, contagem in dados:
            largura = int(100 * contagem / maximo) if maximo else 0
            partes.append(
                '<div class="barra-linha"><span class="rotulo">%s</span>'
                '<span class="trilho"><span class="preenchido" style="width:%d%%">'
                '</span></span><span class="contagem">%d</span></div>'
                % (html.escape(rotulo), largura, contagem))
        partes.append("</div>")
    partes.append("</div>")

    if linhas:
        partes.append(
            "<table><thead><tr><th>Cliente</th><th>Ação</th><th>Estado</th>"
            "<th>Aberto em</th><th>Valor total do contrato</th>"
            "<th>Entrada paga</th><th>Parcelas</th><th>Valor da parcela</th>"
            "</tr></thead><tbody>")
        for l in sorted(linhas, key=lambda x: x["cliente"]):
            obs = ('<br><span class="obs">%s</span>' % html.escape(l["observacao"])
                  if l["observacao"] else "")
            partes.append(
                "<tr><td>%s%s</td><td>%s</td><td>%s</td><td>%s</td>"
                "<td class='numero'>%s</td><td class='numero'>%s</td>"
                "<td class='numero'>%s</td><td class='numero'>%s</td></tr>"
                % (html.escape(l["cliente"]), obs,
                   html.escape(l["tipo_acao"] or "—"),
                   html.escape(l["estado"] or "—"),
                   html.escape(l["quando"] or "—"),
                   html.escape(_moeda(l["valor_total"])),
                   html.escape(_moeda(l["entrada_valor"])),
                   html.escape(str(l["parcelas_qtd"]) if l["parcelas_qtd"] is not None else "—"),
                   html.escape(_moeda(l["parcelas_valor"]))))
        partes.append("</tbody></table>")
    else:
        partes.append('<div class="vazio">Nenhum caso aberto por esta automação neste mês.</div>')

    partes.append("</div>")
    return "".join(partes)


def gerar(config, log, caminho=None) -> Path:
    """Gera o dashboard e devolve o caminho do arquivo."""
    config.pasta_relatorios.mkdir(parents=True, exist_ok=True)
    destino = Path(caminho) if caminho else \
        config.pasta_relatorios / "DASHBOARD FINANCEIRO - CADASTRO ASTREA.html"

    por_mes = coletar(config, log)
    meses_ordenados = sorted(por_mes.keys(), reverse=True)

    partes = [_cabecalho("Dashboard financeiro — Cadastro Astrea")]
    partes.append('<div class="barra-topo"><div>'
                  "<h1>Dashboard financeiro — casos abertos pela automação</h1>"
                  '<div class="sub">Atualizado em %s &middot; atualiza sozinho a '
                  "cada hora, junto com a rodada da automação. Só entra caso "
                  "aberto por ela (a partir de %s) — o histórico anterior não "
                  "aparece aqui.</div></div>"
                  '<button class="atualizar" onclick="location.reload()">'
                  "↻ Atualizar</button></div>"
                  % (datetime.now().strftime("%d/%m/%Y às %H:%M"),
                     config.data_corte_novos_casos))

    if not meses_ordenados:
        partes.append('<div class="vazio">Nenhum caso aberto por esta automação '
                      "ainda. Assim que o primeiro caso for aberto, este "
                      "dashboard passa a mostrar os números aqui.</div>")
    else:
        partes.append('<div class="abas">')
        for i, mes in enumerate(meses_ordenados):
            partes.append('<div class="aba%s" onclick="mostrarMes(\'%s\')" '
                          'id="aba-%s">%s</div>'
                          % (" ativa" if i == 0 else "", mes, mes,
                             html.escape(_mes_rotulo(mes))))
        partes.append("</div>")
        for i, mes in enumerate(meses_ordenados):
            partes.append(_secao_mes(mes, por_mes[mes], ativo=(i == 0)))

    partes.append("""
<script>
function mostrarMes(mes) {
  document.querySelectorAll('.mes').forEach(function (el) { el.classList.remove('ativo'); });
  document.querySelectorAll('.aba').forEach(function (el) { el.classList.remove('ativa'); });
  var secao = document.getElementById('mes-' + mes);
  var aba = document.getElementById('aba-' + mes);
  if (secao) secao.classList.add('ativo');
  if (aba) aba.classList.add('ativa');
}
</script>""")

    partes.append("<footer>Gerado pela automação de cadastro no Astrea. Valor "
                  "total do contrato e parcelamento lidos da Cláusula 2ª do "
                  "contrato assinado a cada atualização — nunca uma estimativa. "
                  "Entrada paga conferida direto no Asaas.</footer>")
    partes.append("</body></html>")

    destino.write_text("\n".join(partes), encoding="utf-8")
    return destino
