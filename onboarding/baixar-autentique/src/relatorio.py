#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Relatório em HTML do que a automação fez — é por onde a Caroline acompanha.

Fica em `BAIXAR AUTENTIQUE/RELATÓRIOS/CONTRATOS BAIXADOS - AUTENTIQUE.html`
(dentro do Drive, para abrir de qualquer máquina), com filtro por situação e
busca por nome. Página única, sem internet, sem biblioteca externa.
"""

import html
import json
from datetime import datetime
from pathlib import Path

NOME_ARQUIVO = "CONTRATOS BAIXADOS - AUTENTIQUE.html"

ROTULOS_ONBOARDING = {
    "gerado": ("onboarding gerado", "ok"),
    "ja_existia": ("onboarding já existia", "neutro"),
    "pendente": ("onboarding pendente", "aviso"),
    "erro": ("onboarding com erro", "erro"),
}

ROTULOS = {
    "baixado": ("Baixado", "ok"),
    "pendente": ("Precisa de você", "aviso"),
    "erro": ("Erro", "erro"),
    "ignorado": ("Não é onboarding", "neutro"),
    "historico": ("Histórico (antes da automação)", "neutro"),
}


def _data_br(texto: str) -> str:
    if not texto:
        return "—"
    bruto = texto.strip().replace("Z", "+00:00")
    try:
        quando = datetime.fromisoformat(bruto)
    except ValueError:
        return texto
    if quando.tzinfo is not None:
        quando = quando.astimezone()
    return quando.strftime("%d/%m/%Y %H:%M")


def _linhas(estado):
    linhas = []
    for doc_id, registro in estado.documentos.items():
        situacao = registro.get("situacao", "?")
        rotulo, classe = ROTULOS.get(situacao, (situacao, "neutro"))
        arquivos = registro.get("arquivos") or []
        onb, onb_classe = ROTULOS_ONBOARDING.get(registro.get("onboarding", ""), ("", ""))
        linhas.append({
            "onboarding": onb,
            "onboarding_classe": onb_classe,
            "id": doc_id,
            "nome": registro.get("nome") or "(sem nome)",
            "cliente": registro.get("cliente") or "",
            "assinado_em": registro.get("assinado_em") or "",
            "quando": registro.get("quando") or "",
            "situacao": situacao,
            "rotulo": rotulo,
            "classe": classe,
            "pasta": registro.get("pasta") or "",
            "motivo": registro.get("motivo") or "",
            "arquivos": [Path(a).name for a in arquivos],
        })
    # Mais recente primeiro; pendências e erros sobem para o topo.
    prioridade = {"pendente": 0, "erro": 0, "baixado": 1, "ignorado": 2, "historico": 3}
    linhas.sort(key=lambda l: (prioridade.get(l["situacao"], 9),
                               l["assinado_em"] or l["quando"]), reverse=False)
    linhas.sort(key=lambda l: prioridade.get(l["situacao"], 9))
    return linhas


def gerar(estado, config, resumo_rodada=None, destino=None) -> Path:
    destino = Path(destino) if destino else Path(config.pasta_relatorios) / NOME_ARQUIVO
    destino.parent.mkdir(parents=True, exist_ok=True)

    linhas = _linhas(estado)
    contagem = estado.contagem()
    resumo_rodada = resumo_rodada or {}

    cartoes = [
        ("Baixados", contagem.get("baixado", 0), "ok"),
        ("Precisam de você", contagem.get("pendente", 0) + contagem.get("erro", 0), "aviso"),
        ("Não eram onboarding", contagem.get("ignorado", 0), "neutro"),
        ("Histórico", contagem.get("historico", 0), "neutro"),
    ]

    aviso = ""
    if resumo_rodada.get("primeira_vez"):
        aviso = ("Primeira rodada: os documentos que já estavam assinados foram "
                 "marcados como histórico e <b>não</b> foram baixados. A partir de "
                 "agora, todo contrato novo assinado por todas as partes cai "
                 "sozinho na pasta do cliente. Para trazer os antigos, use a opção "
                 "<b>“Baixar contratos assinados anteriores”</b> no atalho.")
    elif contagem.get("pendente") or contagem.get("erro"):
        aviso = ("Tem documento esperando por você na lista abaixo. O PDF ficou "
                 "guardado em <code>~/.baixar-autentique/quarentena</code> — nada "
                 "se perdeu.")

    dados = json.dumps(linhas, ensure_ascii=False)
    destino.write_text(MODELO.format(
        gerado_em=datetime.now().strftime("%d/%m/%Y às %H:%M"),
        ultima_rodada=_data_br(estado.dados.get("ultima_rodada", "")),
        ligada_em=_data_br(estado.dados.get("ligada_em", "")),
        pasta_clientes=html.escape(str(config.pasta_clientes)),
        cartoes="\n".join(
            '<div class="cartao {classe}"><span class="numero">{n}</span>'
            '<span class="rotulo">{r}</span></div>'.format(classe=c, n=n, r=html.escape(r))
            for r, n, c in cartoes),
        aviso=('<div class="aviso">%s</div>' % aviso) if aviso else "",
        dados=dados,
    ), encoding="utf-8")
    return destino


MODELO = """<!doctype html>
<html lang="pt-BR">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Contratos baixados do Autentique</title>
<style>
  :root {{
    --fundo: #f6f7f9; --papel: #fff; --texto: #1c1e21; --suave: #6b7280;
    --linha: #e5e7eb; --ok: #157347; --ok-fundo: #e8f5ee; --aviso: #a15c00;
    --aviso-fundo: #fdf3e2; --erro: #b42318; --erro-fundo: #fdeceb;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --fundo: #14161a; --papel: #1c1f24; --texto: #e8eaed; --suave: #9aa1ab;
      --linha: #2c3038; --ok: #4ade80; --ok-fundo: #16281f; --aviso: #fbbf24;
      --aviso-fundo: #2a2113; --erro: #f87171; --erro-fundo: #2a1717;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 24px; background: var(--fundo); color: var(--texto);
         font: 15px/1.5 -apple-system, "Helvetica Neue", Arial, sans-serif; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .sub {{ color: var(--suave); font-size: 13px; margin-bottom: 20px; }}
  .cartoes {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 18px; }}
  .cartao {{ background: var(--papel); border: 1px solid var(--linha); border-radius: 10px;
             padding: 14px 18px; min-width: 150px; }}
  .cartao .numero {{ display: block; font-size: 26px; font-weight: 600; }}
  .cartao .rotulo {{ color: var(--suave); font-size: 13px; }}
  .cartao.ok .numero {{ color: var(--ok); }}
  .cartao.aviso .numero {{ color: var(--aviso); }}
  .aviso {{ background: var(--aviso-fundo); border: 1px solid var(--linha);
            border-left: 4px solid var(--aviso); border-radius: 8px;
            padding: 12px 16px; margin-bottom: 18px; }}
  .controles {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: 14px; }}
  button {{ font: inherit; padding: 7px 14px; border-radius: 999px; cursor: pointer;
            border: 1px solid var(--linha); background: var(--papel); color: var(--texto); }}
  button[aria-pressed="true"] {{ background: var(--texto); color: var(--papel); border-color: var(--texto); }}
  input[type=search] {{ font: inherit; padding: 7px 12px; border-radius: 8px; flex: 1; min-width: 200px;
                        border: 1px solid var(--linha); background: var(--papel); color: var(--texto); }}
  table {{ width: 100%; border-collapse: collapse; background: var(--papel);
           border: 1px solid var(--linha); border-radius: 10px; overflow: hidden; }}
  th, td {{ text-align: left; padding: 11px 14px; border-bottom: 1px solid var(--linha);
            vertical-align: top; font-size: 14px; }}
  th {{ font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: var(--suave); }}
  tr:last-child td {{ border-bottom: 0; }}
  .selo {{ display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 12px; white-space: nowrap; }}
  .selo.ok {{ background: var(--ok-fundo); color: var(--ok); }}
  .selo.aviso {{ background: var(--aviso-fundo); color: var(--aviso); }}
  .selo.erro {{ background: var(--erro-fundo); color: var(--erro); }}
  .selo.neutro {{ background: var(--fundo); color: var(--suave); }}
  .motivo {{ color: var(--suave); font-size: 13px; }}
  .arquivos {{ color: var(--suave); font-size: 12px; margin-top: 4px; }}
  .vazio {{ padding: 28px; text-align: center; color: var(--suave); }}
  footer {{ margin-top: 22px; color: var(--suave); font-size: 12px; }}
  code {{ background: var(--fundo); padding: 1px 5px; border-radius: 4px; }}
</style>

<h1>Contratos baixados do Autentique</h1>
<div class="sub">
  Gerado em {gerado_em} &middot; última verificação: {ultima_rodada} &middot;
  automação ligada em {ligada_em}<br>
  Pasta dos clientes: <code>{pasta_clientes}</code>
</div>

<div class="cartoes">{cartoes}</div>
{aviso}

<div class="controles">
  <button data-filtro="todos" aria-pressed="true">Todos</button>
  <button data-filtro="baixado" aria-pressed="false">Baixados</button>
  <button data-filtro="pendente" aria-pressed="false">Precisam de você</button>
  <button data-filtro="erro" aria-pressed="false">Erros</button>
  <button data-filtro="ignorado" aria-pressed="false">Não é onboarding</button>
  <button data-filtro="historico" aria-pressed="false">Histórico</button>
  <input type="search" id="busca" placeholder="Buscar por cliente, documento ou pasta...">
</div>

<table>
  <thead>
    <tr><th>Documento</th><th>Cliente</th><th>Assinado em</th><th>Situação</th><th>Onde foi parar</th></tr>
  </thead>
  <tbody id="corpo"></tbody>
</table>
<div class="vazio" id="vazio" hidden>Nada por aqui com esse filtro.</div>

<footer>
  Automação “Baixar Contratos Assinados” &middot; escritório Caroline Macedo.
  Os PDFs que ficaram sem pasta estão em <code>~/.baixar-autentique/quarentena</code>.
</footer>

<script>
const DADOS = {dados};
let filtro = "todos";
let busca = "";

function dataBR(texto) {{
  if (!texto) return "—";
  const d = new Date(texto);
  if (isNaN(d)) return texto;
  return d.toLocaleString("pt-BR", {{ day: "2-digit", month: "2-digit", year: "numeric",
                                     hour: "2-digit", minute: "2-digit" }});
}}

function escapar(texto) {{
  return String(texto ?? "").replace(/[&<>"]/g, c => (
    {{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }}[c]));
}}

function desenhar() {{
  const alvo = busca.trim().toLowerCase();
  const linhas = DADOS.filter(l => (filtro === "todos" || l.situacao === filtro))
    .filter(l => !alvo || [l.nome, l.cliente, l.pasta, l.motivo].join(" ").toLowerCase().includes(alvo));

  document.getElementById("corpo").innerHTML = linhas.map(l => `
    <tr>
      <td>${{escapar(l.nome)}}</td>
      <td>${{escapar(l.cliente) || "—"}}</td>
      <td>${{dataBR(l.assinado_em)}}</td>
      <td><span class="selo ${{l.classe}}">${{escapar(l.rotulo)}}</span>
          ${{l.onboarding ? `<div style="margin-top:6px"><span class="selo ${{l.onboarding_classe}}">${{escapar(l.onboarding)}}</span></div>` : ""}}</td>
      <td>
        ${{l.pasta ? `<div>${{escapar(l.pasta)}}</div>` : ""}}
        ${{l.motivo ? `<div class="motivo">${{escapar(l.motivo)}}</div>` : ""}}
        ${{l.arquivos.length ? `<div class="arquivos">${{l.arquivos.map(escapar).join(" &middot; ")}}</div>` : ""}}
      </td>
    </tr>`).join("");
  document.getElementById("vazio").hidden = linhas.length > 0;
}}

document.querySelectorAll("button[data-filtro]").forEach(botao => {{
  botao.addEventListener("click", () => {{
    filtro = botao.dataset.filtro;
    document.querySelectorAll("button[data-filtro]").forEach(b =>
      b.setAttribute("aria-pressed", String(b === botao)));
    desenhar();
  }});
}});
document.getElementById("busca").addEventListener("input", e => {{
  busca = e.target.value; desenhar();
}});
desenhar();
</script>
</html>
"""
