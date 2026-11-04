#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Relatório de pendências, em HTML, dentro do Drive.

Como a automação roda sozinha em segundo plano, este arquivo é o ponto de
contato: abre no navegador com dois cliques e mostra o que precisa de gente.

O CPF sai mascarado (049.***.***-56) — o relatório fica numa pasta sincronizada
e não precisa carregar o número inteiro para você saber de quem se trata.
"""

import html
import json
from datetime import datetime
from pathlib import Path

from ..config.settings import mascarar_cpf
from ..database import controle as St
from ..database.controle import Controle

CORES = {
    St.CADASTRADO: ("#0f7b3f", "#e8f6ee"),
    St.JA_CADASTRADO: ("#4a5568", "#eef1f5"),
    St.PENDENTE: ("#a65c00", "#fdf3e3"),
    St.DIVERGENTE: ("#8a4b00", "#fbeee0"),
    St.ERRO: ("#a11", "#fdeaea"),
    St.SIMULADO: ("#2b5fa8", "#e9f0fb"),
    St.AGUARDANDO: ("#555", "#f2f2f2"),
    St.HISTORICO: ("#777", "#f7f7f7"),
}

PRECISAM_DE_GENTE = (St.PENDENTE, St.DIVERGENTE, St.ERRO)


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
 .cartoes { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 26px; }
 .cartao { border-radius: 10px; padding: 12px 16px; min-width: 128px; }
 .cartao b { display: block; font-size: 24px; line-height: 1.1; }
 .cartao span { font-size: 12px; }
 table { border-collapse: collapse; width: 100%%; background: #fff;
         border-radius: 10px; overflow: hidden; font-size: 13px;
         box-shadow: 0 1px 3px rgba(0,0,0,.08); }
 th, td { text-align: left; padding: 9px 12px; border-bottom: 1px solid #eee;
          vertical-align: top; }
 th { background: #f2f4f7; font-weight: 600; font-size: 12px;
      text-transform: uppercase; letter-spacing: .03em; color: #555; }
 tr:last-child td { border-bottom: none; }
 .tag { display: inline-block; padding: 2px 8px; border-radius: 20px;
        font-size: 11px; font-weight: 600; white-space: nowrap; }
 .motivo { color: #444; }
 .secao { margin: 34px 0 10px; font-size: 16px; }
 .vazio { color: #666; background: #fff; padding: 18px; border-radius: 10px; }
 .aviso { background: #fdeaea; border-left: 5px solid #a11; color: #5c1010;
          padding: 14px 18px; border-radius: 8px; margin-bottom: 22px;
          font-size: 14px; line-height: 1.5; }
 footer { margin-top: 34px; color: #888; font-size: 12px; }
 @media (prefers-color-scheme: dark) {
   body { background: #16181c; color: #e8e8e8; }
   table { background: #202329; box-shadow: none; }
   th { background: #262a31; color: #bbb; }
   th, td { border-color: #2e323a; }
   .vazio { background: #202329; color: #aaa; }
   .aviso { background: #3a1f1f; color: #ffd9d9; border-left-color: #d66; }
 }
</style></head><body>""" % html.escape(titulo)


def _tag(status):
    cor, fundo = CORES.get(status, ("#333", "#eee"))
    return '<span class="tag" style="color:%s;background:%s">%s</span>' % (
        cor, fundo, html.escape(status or ""))


def _caso_do_registro(registro) -> str:
    """
    Tipo de ação e banco adverso lidos do contrato.

    A automação não abre o caso no Astrea (escopo atual é só o contato), mas o
    dado já foi extraído — mostrar aqui evita ter que reabrir o contrato para
    abrir a pasta à mão.
    """
    if not registro["dados_json"]:
        return ""
    try:
        dados = json.loads(registro["dados_json"])
    except ValueError:
        return ""
    acao = (dados.get("tipo_acao") or {}).get("valor") or ""
    banco = (dados.get("banco_adverso") or {}).get("valor") or ""
    if acao and banco:
        return "%s — %s" % (acao, banco)
    return acao or banco or ""


def _detalhe_com_trava(registro) -> str:
    """
    Cliente já cadastrado cujo caso/cópia está barrado pela trava de
    documentação (25/09/2026): o status dele é CADASTRADO, então sem isto o
    motivo de o caso não andar ficaria invisível no relatório.
    """
    detalhe = registro["detalhe"] or ""
    status_caso = registro["status_caso"] or ""
    if "DOCUMENTAÇÃO INCOMPLETA" in status_caso:
        return ("%s — %s" % (status_caso, detalhe)) if detalhe else status_caso
    return detalhe


def _linha_pendencia(registro):
    dados = {}
    if registro["dados_json"]:
        try:
            dados = json.loads(registro["dados_json"])
        except ValueError:
            dados = {}

    nao_lidos = dados.get("nao_interpretados") or []
    extras = ""
    if nao_lidos:
        itens = "".join("<li>%s — %s</li>"
                        % (html.escape(n.get("arquivo", "")),
                           html.escape(n.get("motivo", "")))
                        for n in nao_lidos)
        extras = ("<details><summary>%d documento(s) não interpretado(s)</summary>"
                  "<ul>%s</ul></details>" % (len(nao_lidos), itens))

    observacoes = dados.get("observacoes") or []
    if observacoes:
        extras += "<details><summary>Observações</summary><ul>%s</ul></details>" % \
                  "".join("<li>%s</li>" % html.escape(o) for o in observacoes)

    return ("<tr><td>%s</td><td><b>%s</b><br><small>%s</small></td><td>%s</td>"
            "<td class='motivo'>%s%s</td><td>%s</td></tr>") % (
        _tag(registro["status"]),
        html.escape(registro["nome_cliente"] or registro["nome_pasta"] or ""),
        html.escape(registro["nome_pasta"] or ""),
        html.escape(mascarar_cpf(registro["cpf_cnpj"] or "")),
        html.escape(registro["detalhe"] or registro["erro"] or ""),
        extras,
        html.escape((registro["atualizado_em"] or "").replace("T", " ")[:16]))


def gerar(config, caminho=None) -> Path:
    """Escreve o relatório e devolve o caminho do arquivo."""
    config.pasta_relatorios.mkdir(parents=True, exist_ok=True)
    destino = Path(caminho) if caminho else \
        config.pasta_relatorios / "PENDÊNCIAS - CADASTRO ASTREA.html"

    with Controle(config.banco) as banco:
        contagens = dict(banco.contagem_por_status())
        precisam = banco.listar(status=list(PRECISAM_DE_GENTE), limite=500)
        recentes = banco.listar(status=[St.CADASTRADO, St.JA_CADASTRADO,
                                        St.SIMULADO], limite=60)
        sem_sessao = banco.marco("sem_sessao_desde") or ""

    partes = [_cabecalho("Pendências — Cadastro Astrea")]
    partes.append("<h1>Cadastro automático no Astrea</h1>")
    partes.append('<div class="sub">Atualizado em %s &middot; modo %s</div>'
                  % (datetime.now().strftime("%d/%m/%Y às %H:%M"),
                     "TESTE (nada é gravado no Astrea)" if config.test_mode
                     else "PRODUÇÃO"))

    if sem_sessao:
        partes.append(
            '<div class="aviso"><b>A automação está parada:</b> não conseguiu '
            'entrar no Astrea desde %s.<br>O Astrea aceita só uma sessão por '
            'conta, então a sessão dela cai quando você usa o sistema. '
            'Abra o atalho <b>Cadastro Astrea</b> e use <b>“Entrar no Astrea”</b> '
            '— a fila de clientes está intacta e continua de onde parou.</div>'
            % html.escape(sem_sessao.replace("T", " ")[:16]))

    partes.append('<div class="cartoes">')
    for status in (St.CADASTRADO, St.JA_CADASTRADO, St.PENDENTE, St.DIVERGENTE,
                   St.ERRO, St.SIMULADO, St.AGUARDANDO, St.HISTORICO):
        if status not in contagens:
            continue
        cor, fundo = CORES.get(status, ("#333", "#eee"))
        partes.append('<div class="cartao" style="background:%s;color:%s">'
                      '<b>%d</b><span>%s</span></div>'
                      % (fundo, cor, contagens[status], html.escape(status)))
    partes.append("</div>")

    partes.append('<div class="secao"><b>Precisam de você</b></div>')
    if precisam:
        partes.append("<table><thead><tr><th>Status</th><th>Cliente</th>"
                      "<th>CPF</th><th>O que houve</th><th>Quando</th></tr>"
                      "</thead><tbody>")
        partes.extend(_linha_pendencia(r) for r in precisam)
        partes.append("</tbody></table>")
    else:
        partes.append('<div class="vazio">Nada pendente. Todos os clientes '
                      'analisados foram resolvidos.</div>')

    partes.append('<div class="secao"><b>Últimos processados</b></div>')
    partes.append('<div class="sub">A coluna <b>Caso a abrir</b> traz o que foi '
                  'lido do contrato. Hoje a automação cadastra só o contato — '
                  'o caso é aberto por você no Astrea.</div>')
    if recentes:
        partes.append("<table><thead><tr><th>Status</th><th>Cliente</th>"
                      "<th>CPF</th><th>Caso a abrir</th><th>Detalhe</th>"
                      "<th>Quando</th></tr></thead><tbody>")
        for registro in recentes:
            partes.append(
                "<tr><td>%s</td><td>%s<br><small>%s</small></td><td>%s</td>"
                "<td>%s</td><td class='motivo'>%s</td><td>%s</td></tr>" % (
                    _tag(registro["status"]),
                    html.escape(registro["nome_cliente"] or ""),
                    html.escape(registro["nome_pasta"] or ""),
                    html.escape(mascarar_cpf(registro["cpf_cnpj"] or "")),
                    html.escape(_caso_do_registro(registro)),
                    html.escape(_detalhe_com_trava(registro)),
                    html.escape((registro["processado_em"] or "").replace("T", " ")[:16])))
        partes.append("</tbody></table>")
    else:
        partes.append('<div class="vazio">Ainda não há clientes processados.</div>')

    partes.append("<footer>Gerado pela automação de cadastro no Astrea. "
                  "CPF exibido parcialmente por segurança. "
                  "Log completo em ~/.cadastro-astrea/logs/.</footer>")
    partes.append("</body></html>")

    destino.write_text("\n".join(partes), encoding="utf-8")
    return destino
