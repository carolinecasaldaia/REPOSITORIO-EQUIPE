#!/usr/bin/env python3
"""Lê no Astrea o histórico dos processos fora do TJAL — SOMENTE LEITURA, PELA TELA.

Por que existe: PJe, eproc e Projudi (PE, BA, MG, GO, RS, SC, SP novo...) não têm
consulta pública sem captcha, e o Diário (DJEN) só traz o que gera intimação. O
Astrea captura sozinho os andamentos desses tribunais. Caso real (01/10/2026): o
relatório do Diego dizia "o banco vai responder à defesa", mas o Astrea mostrava
o processo concluso para julgamento desde 18/08.

Como lê: igual a uma pessoa, com a conta "Claude" (a mesma do Cadastro Astrea),
no perfil de navegador ~/.cadastro-astrea/chrome-perfil, onde a sessão já está
aberta. Busca o nº na barra do topo, abre o caso e lê a aba "Histórico". Não usa
token nem API, não digita senha (se a sessão caiu, avisa e para) e não clica em
nada que altere o caso. Decisão da Caroline, 01/10/2026.

Trava: ~/.cadastro-astrea/execucao.lock, a mesma do cadastro automático.

Diligências (--diligencias): para cada caso, abre Atividades → "N CONCLUÍDAS",
clica nas tarefas de diligência (DILIGENCIAR, LIGAR NO TRIBUNAL, BALCÃO...) e lê
a aba Comentários, onde a equipe anota data, hora, com quem falou e a resposta.
Sai o texto do painel; quem decide o que vai ao cliente é o gerar_relatorios.py.

Uso:  <python do Cadastro Astrea> ler_astrea.py entrada.json saida.json [--diligencias]
      entrada = lista de números (20 dígitos)
      saída   = {numero: {"achou": bool, "itens": [[aaaa-mm-dd, texto], ...]}}
"""
import fcntl
import json
import re
import sys
import time
from pathlib import Path

CASA = Path.home() / ".cadastro-astrea"

# Cada item da aba Histórico é um bloco com a data (dd/mm/aaaa) e o texto.
# Sobe a partir do elemento da data até o primeiro ancestral que tenha mais texto.
_LER = """() => {
  const re = /^\\d\\d\\/\\d\\d\\/\\d{4}$/;
  const itens = [];
  document.querySelectorAll('*').forEach(e => {
    if (!e.offsetParent || e.children.length) return;
    const t = (e.innerText || '').trim();
    if (!re.test(t)) return;
    let bloco = e.parentElement;
    for (let k = 0; k < 4 && bloco; k++) {
      if ((bloco.innerText || '').trim().length > t.length + 3) break;
      bloco = bloco.parentElement;
    }
    itens.push([t, (bloco ? bloco.innerText : '').trim().slice(0, 4000)]);
  });
  return itens;
}"""


def fmt(n):
    return "%s-%s.%s.%s.%s.%s" % (n[:7], n[7:9], n[9:13], n[13], n[14:16], n[16:])


def pegar_trava(espera_max=900):
    fh = open(CASA / "execucao.lock", "w")
    inicio = time.time()
    while True:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fh
        except OSError:
            if time.time() - inicio > espera_max:
                raise SystemExit("ASTREA_OCUPADO: o cadastro automático não liberou o Astrea em 15 min")
            print("   o cadastro automático está usando o Astrea; aguardando...", flush=True)
            time.sleep(30)


def ler_um(pg, num):
    campo = pg.locator('input[ng-model="filtertext"]').first
    campo.click()
    campo.fill("")
    campo.fill(num)
    sug = pg.locator("ul.suggest-list li a.matching", has_text=num).first
    try:
        sug.wait_for(state="visible", timeout=8000)
    except Exception:
        return {"achou": False, "itens": []}
    sug.click()
    pg.get_by_text("Histórico", exact=True).first.wait_for(timeout=15000)
    pg.wait_for_timeout(1500)
    pg.get_by_text("Histórico", exact=True).first.click()
    pg.wait_for_timeout(3500)
    itens = []
    for data, texto in pg.evaluate(_LER):
        d, m, a = data.split("/")
        corpo = texto.replace(data, "", 1).strip()
        itens.append(["%s-%s-%s" % (a, m, d), corpo])
    return {"achou": True, "itens": itens}


_TAREFAS = """() => {
  const out = [];
  document.querySelectorAll('*').forEach(e => {
    if (!e.offsetParent || e.children.length) return;
    if ((e.innerText || '').trim() !== 'TAREFA') return;
    let b = e.parentElement;
    for (let k = 0; k < 5 && b; k++) { if ((b.innerText || '').split('\\n').length > 3) break; b = b.parentElement; }
    out.push((b ? b.innerText : '').trim());
  });
  return out;
}"""
_DILIG = re.compile(r"DILIG|LIGAR (NO|PARA)|BALC[AÃ]O|DESPACHAR|DESPACHO (COM|VIRTUAL)|CONTATO COM", re.I)


def ler_diligencias(pg, num):
    """Abre o caso já selecionado pela busca e devolve [{titulo, painel}]."""
    pg.get_by_text("Atividades", exact=True).first.click()
    pg.wait_for_timeout(2500)
    botao = pg.get_by_text(re.compile(r"^\d+\s+CONCLU", re.I))
    if not botao.count():
        return []
    botao.first.click()
    pg.wait_for_timeout(3000)
    achadas = []
    for bloco in pg.evaluate(_TAREFAS):
        linhas = [l.strip() for l in bloco.split("\n") if l.strip()]
        titulo = linhas[1] if len(linhas) > 1 else ""
        if not _DILIG.search(titulo) or "comentário" not in bloco:
            continue
        try:
            pg.get_by_text(titulo, exact=True).first.click()
            pg.wait_for_timeout(3000)
            pg.get_by_text("Comentários", exact=True).last.click()
            pg.wait_for_timeout(2500)
            texto = pg.inner_text("body")
            i = texto.find("Tarefa concluída em")
            achadas.append({"titulo": titulo, "painel": texto[max(0, i - 900):][:6000] if i >= 0 else texto[-6000:]})
        except Exception:
            continue
    return achadas


def main():
    numeros = json.load(open(sys.argv[1]))
    saida = Path(sys.argv[2])
    so_diligencias = "--diligencias" in sys.argv
    from playwright.sync_api import sync_playwright

    trava = pegar_trava()
    resultado = {}
    with sync_playwright() as p:
        ctx = None
        for _ in range(6):                     # outra automação pode estar com o perfil aberto
            try:
                ctx = p.chromium.launch_persistent_context(
                    str(CASA / "chrome-perfil"), channel="chrome", headless=True, locale="pt-BR",
                    viewport={"width": 1440, "height": 1400})
                break
            except Exception:
                print("   perfil do Astrea em uso; tentando de novo em 30s...", flush=True)
                time.sleep(30)
        if ctx is None:
            raise SystemExit("ASTREA_OCUPADO: perfil do navegador em uso")
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto("https://astrea.net.br/#/main/workspace", wait_until="domcontentloaded")
        pg.wait_for_timeout(6000)
        if pg.locator("input[type=password]").count() or "/login" in pg.url:
            ctx.close()
            raise SystemExit("ASTREA_SEM_SESSAO: a sessão caiu — entre pelo atalho do Cadastro Astrea")

        for i, n in enumerate(numeros, 1):
            try:
                if so_diligencias:
                    achou = ler_um(pg, fmt(n))["achou"]
                    resultado[n] = ler_diligencias(pg, fmt(n)) if achou else []
                    # o painel da tarefa cobre a barra de busca: volta para a tela inicial
                    pg.goto("https://astrea.net.br/#/main/workspace", wait_until="domcontentloaded")
                    pg.wait_for_timeout(4000)
                    continue
                resultado[n] = ler_um(pg, fmt(n))
            except Exception as e:
                resultado[n] = [] if so_diligencias else {"achou": False, "itens": [], "erro": str(e)[:200]}
                pg.goto("https://astrea.net.br/#/main/workspace", wait_until="domcontentloaded")
                pg.wait_for_timeout(5000)
            if i % 10 == 0:
                print("   Astrea: %d/%d" % (i, len(numeros)), flush=True)
                saida.write_text(json.dumps(resultado, ensure_ascii=False), encoding="utf-8")
        ctx.close()
    saida.write_text(json.dumps(resultado, ensure_ascii=False), encoding="utf-8")
    trava.close()
    if so_diligencias:
        print("ASTREA_OK %d lidos, %d com diligência" % (len(resultado), sum(1 for r in resultado.values() if r)))
    else:
        print("ASTREA_OK %d lidos, %d encontrados" % (len(resultado), sum(r["achou"] for r in resultado.values())))


if __name__ == "__main__":
    main()
