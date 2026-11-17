#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dashboard Comercial Consolidado: regera a página
"A - REVISIONAL/A - COMERCIAL/DASHBOARD COMERCIAL - CONSOLIDADO 2023-2026.html"
a partir da base do Painel Comercial (painel-comercial-dados.json, que o robô
horário mantém em dia).

    /usr/bin/python3 gerar_consolidado.py

Até maio/2026 a base traz o histórico da planilha consolidada (contratos
assinados); de junho/2026 em diante, as fontes próprias do painel (planilhas
mensais e pastas com OK). Faturamento é o PREVISTO no contrato (entrada +
parcelas), não o recebido.
"""

import calendar
import html
import json
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DOC = next((p for p in AQUI.parents if p.name.startswith("Documentos Escrit")), None)
if DOC is None:   # rodando da cópia do repositório: usa o Drive
    DOC = next(Path.home().glob("Library/CloudStorage/GoogleDrive-*/Meu Drive/Documentos Escrit*"))
BASE = DOC / "EMPRESA" / "FINANCEIRO" / "PAINEL COMERCIAL" / "painel-comercial-dados.json"
SAIDA = DOC / "A - REVISIONAL" / "A - COMERCIAL" / "DASHBOARD COMERCIAL - CONSOLIDADO 2023-2026.html"

MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
MINUSC = {"de", "da", "do", "dos", "das", "e"}


# ---------- utilidades ----------
def brl(v, casas=2):
    s = f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return "R$ " + s


def rot(ym):
    a, m = ym
    return f"{MESES[m - 1]}/{a % 100:02d}"


def ym_de(s):
    """'26.06.2026' ou '2026-06' -> (2026, 6, dia)"""
    s = (s or "").strip()
    if len(s) >= 9 and s[2] == "." and s[5] == ".":
        d, m, a = s.split(".")[:3]
        return int(a[:4]), int(m), int(d)
    if len(s) >= 7 and s[4] == "-":
        return int(s[:4]), int(s[5:7]), 1
    return None


def soma_mes(ym, n):
    a, m = ym
    t = a * 12 + (m - 1) + n
    return t // 12, t % 12 + 1


def nome(s):
    out = []
    for i, p in enumerate((s or "").split()):
        p = p.lower()
        out.append(p if (i and p in MINUSC) else p[:1].upper() + p[1:])
    return " ".join(out)


def servico(t):
    t = (t or "").upper()
    if "REVISIONAL" in t:
        return "Revisional"
    if "BUSCA" in t:
        return "Busca e Apreensão"
    if "FRAUDE" in t:
        return "Fraude bancária"
    if "EXIB" in t:
        return "Exibição de Documentos"
    if "EXECU" in t:
        return "Defesa em execução"
    if "CÍVEL" in t or "CIVEL" in t:
        return "Cível"
    return "Não identificado"


def e(s):
    return html.escape(str(s))


# ---------- cálculo ----------
def calcular(dados, hoje):
    todos = dados["contratos"]
    contratos = [c for c in todos if not c.get("outro_mes")]
    venc = defaultdict(lambda: [0.0, 0.0])        # (a,m) -> [entradas, parcelas]
    realizado = 0.0
    a_receber = 0.0
    sem_crono = []
    sem_valor = []
    fim_max = None

    def lanca(ym, dia, valor, idx):
        nonlocal realizado, a_receber, fim_max
        venc[ym][idx] += valor
        ultimo = calendar.monthrange(*ym)[1]
        d = date(ym[0], ym[1], min(dia or 1, ultimo))
        if d <= hoje:
            realizado += valor
        else:
            a_receber += valor
        fim_max = ym if fim_max is None or ym > fim_max else fim_max

    for c in todos:
        mes = ym_de(c["mes"])
        mes_ym = (mes[0], mes[1])
        entrada = c.get("entrada") or 0
        partes = c.get("entrada_partes") or []
        qtd = c.get("parcelas_qtd") or 0
        pv = c.get("parcelas_valor") or 0
        if partes:
            for p in partes:
                d = ym_de(p.get("data")) or mes
                lanca((d[0], d[1]), d[2], p.get("valor") or 0, 0)
        elif entrada:
            d = ym_de(c.get("entrada_data")) or mes
            # entrada vale no mês do contrato (é assim que o painel conta)
            lanca(mes_ym, d[2] if (d[0], d[1]) == mes_ym else 1, entrada, 0)
        if qtd and pv:
            ini = ym_de(c.get("parcelas_inicio"))
            ini_ym, dia = ((ini[0], ini[1]), ini[2]) if ini else (soma_mes(mes_ym, 1), 10)
            for i in range(qtd):
                lanca(soma_mes(ini_ym, i), dia, pv, 1)
        if c.get("outro_mes"):
            continue
        if not entrada and not partes and not (qtd and pv):
            if c.get("valor_total"):
                sem_crono.append(c)
                lanca(mes_ym, 1, c["valor_total"], 0)
        if not c.get("valor_total"):
            sem_valor.append(c)

    # entradas pagas em partes lançadas como outro_mes, ligadas ao contrato pelo cliente
    extra = defaultdict(float)
    for c in todos:
        if c.get("outro_mes"):
            extra[c["cliente"]] += c.get("entrada") or 0
    diverg = []
    for c in contratos:
        vt = c.get("valor_total")
        if not vt:
            continue
        partes = c.get("entrada_partes") or []
        ent = sum(p.get("valor") or 0 for p in partes) if partes else (c.get("entrada") or 0)
        ent += extra.get(c["cliente"], 0)
        soma = ent + (c.get("parcelas_qtd") or 0) * (c.get("parcelas_valor") or 0)
        if soma and abs(vt - soma) > 1:
            diverg.append((c, vt, soma))
    diverg.sort(key=lambda x: -abs(x[1] - x[2]))

    return dict(contratos=contratos, venc=venc, realizado=realizado, a_receber=a_receber,
                sem_crono=sem_crono, sem_valor=sem_valor, diverg=diverg, fim_max=fim_max)


# ---------- HTML ----------
def colunas_fat(meses, venc, hoje_ym, escala):
    cols, ticks, vals = [], [], []
    for ym in meses:
        ent, par = venc.get(ym, (0, 0))
        fut = " fut" if ym > hoje_ym else ""
        cols.append(f'<div class="col"><div class="cbar ent{fut}" style="height:{ent / escala * 100:.1f}%"></div>'
                    f'<div class="cbar par{fut}" style="height:{par / escala * 100:.1f}%"></div></div>')
        ticks.append(f'<div class="ctick">{rot(ym)}</div>')
        t = (ent + par) / 1000
        vals.append(f'<div class="cv">{t:.1f}</div>' if t >= 0.05 else '<div class="cv"></div>')
    return "\n".join(cols), "\n".join(ticks), "\n".join(vals)


def hbars(linhas):
    """linhas: [(nome, fração 0-1, cor, texto)]"""
    return "\n".join(
        f'<div class="hrow"><div class="hname">{e(n)}</div><div class="htrack"><div class="hfill" '
        f'style="width:{f * 100:.1f}%;background:var({cor})"></div></div><div class="hval">{e(t)}</div></div>'
        for n, f, cor, t in linhas)


def gerar(dados, hoje):
    r = calcular(dados, hoje)
    cs = r["contratos"]
    venc = r["venc"]
    hoje_ym = (hoje.year, hoje.month)
    com_valor = [c for c in cs if c.get("valor_total")]
    hon_total = sum(c["valor_total"] for c in com_valor)
    ticket = hon_total / len(com_valor)
    n = len(cs)
    clientes = len({c["cliente"].strip().upper() for c in cs})
    meses_ct = sorted({ym_de(c["mes"])[:2] for c in cs})
    ini, fim_ct = meses_ct[0], meses_ct[-1]

    # eixo do faturamento: do 1º contrato ao último vencimento
    meses_fat = []
    ym = ini
    while ym <= r["fim_max"]:
        meses_fat.append(ym)
        ym = soma_mes(ym, 1)
    escala = max(sum(venc.get(m, (0, 0))) for m in meses_fat)
    c_fat, t_fat, v_fat = colunas_fat(meses_fat, venc, hoje_ym, escala)

    # honorários por mês de fechamento
    por_mes = defaultdict(lambda: [0, 0.0])
    for c in cs:
        k = ym_de(c["mes"])[:2]
        por_mes[k][0] += 1
        por_mes[k][1] += c.get("valor_total") or 0
    esc_h = max(v[1] for v in por_mes.values())
    c_hon = "\n".join(f'<div class="col"><div class="cbar hon" style="height:{por_mes[m][1] / esc_h * 100:.1f}%"></div></div>'
                      for m in meses_ct)
    t_hon = "\n".join(f'<div class="ctick">{rot(m)}</div>' for m in meses_ct)
    v_hon = "\n".join(f'<div class="cv">{por_mes[m][0]}</div>' for m in meses_ct)

    # por ano
    anos = sorted({m[0] for m in meses_ct} | {m[0] for m in meses_fat if sum(venc.get(m, (0, 0)))})
    linhas_ano, fat_total = [], 0.0
    por_ano_ct = Counter()
    for a in anos:
        ct = [c for c in cs if c["mes"].startswith(str(a))]
        cv = [c for c in ct if c.get("valor_total")]
        hon = sum(c["valor_total"] for c in cv)
        fat = sum(sum(v) for k, v in venc.items() if k[0] == a)
        fat_total += fat
        por_ano_ct[a] = len(ct)
        tk = brl(hon / len(cv)) if cv else "—"
        linhas_ano.append(f"<tr><td>{a}</td><td class='num'>{len(ct)}</td><td class='num'>{brl(hon)}</td>"
                          f"<td class='num'>{tk}</td><td class='num'>{brl(fat)}</td></tr>")

    # mês a mês
    linhas_mes = []
    for m in meses_ct:
        qt, hon = por_mes[m]
        cv = [c for c in cs if ym_de(c["mes"])[:2] == m and c.get("valor_total")]
        ent, par = venc.get(m, (0, 0))
        tk = brl(hon / len(cv)) if cv else "—"
        linhas_mes.append(f"<tr><td>{rot(m)}</td><td class='num'>{qt}</td><td class='num'>{brl(hon)}</td>"
                          f"<td class='num'>{tk}</td><td class='num'>{brl(ent)}</td><td class='num'>{brl(par)}</td>"
                          f"<td class='num'>{brl(ent + par)}</td></tr>")

    # serviços
    serv = defaultdict(lambda: [0, 0.0])
    for c in cs:
        s = servico(c.get("tipo_acao"))
        serv[s][0] += 1
        serv[s][1] += c.get("valor_total") or 0
    serv_ord = sorted(serv.items(), key=lambda kv: (-kv[1][1], -kv[1][0]))
    mx = serv_ord[0][1][1]
    cor_s = {"Revisional": "--series-1", "Busca e Apreensão": "--series-2"}
    h_serv = hbars([(s, v[1] / mx, cor_s.get(s, "--series-3"), f"{brl(v[1], 0)} · {v[0]} contr.") for s, v in serv_ord])

    # estados
    ufs = Counter((c.get("uf") or "").strip().upper() or "Não identificada" for c in cs)
    top_uf = ufs.most_common(10)
    h_uf = hbars([(u, q / top_uf[0][1], "--series-1", f"{q} contratos") for u, q in top_uf])
    sem_uf = ufs.get("Não identificada", 0)

    # maiores contratos
    top = sorted(com_valor, key=lambda c: -c["valor_total"])[:15]
    h_top = hbars([(nome(c["cliente"])[:30], c["valor_total"] / top[0]["valor_total"],
                    cor_s.get(servico(c.get("tipo_acao")), "--series-3"), brl(c["valor_total"])) for c in top])

    rev = serv.get("Revisional", [0])[0]
    bus = serv.get("Busca e Apreensão", [0])[0]
    ano_atual = hoje.year
    cap_anos = " · ".join(f"{a}: {por_ano_ct[a]}" for a in anos if por_ano_ct[a])
    ult_venc = rot(r["fim_max"])

    div_li = "\n".join(
        f"<li><strong>{e(nome(c['cliente']))}</strong> — contrato diz {brl(vt)}, mas entrada + parcelas somam "
        f"{brl(s)} ({'+' if s > vt else '−'}{brl(abs(s - vt))[3:]})</li>" for c, vt, s in r["diverg"][:8])
    sc_total = sum(c["valor_total"] for c in r["sem_crono"])
    sem_valor_txt = ", ".join(sorted({nome(c["cliente"]) for c in r["sem_valor"]}))

    corpo = f"""<body>
<div class="viz-root">
<div class="wrap">

<header class="page">
  <div class="eyebrow">Caroline Macedo Advocacia — Carteira A - REVISIONAL</div>
  <h1>Dashboard Comercial Consolidado · {rot(ini)} a {rot(fim_ct)}</h1>
  <p class="sub">{n} contratos de honorários de {clientes} clientes. Base do Painel Comercial, atualizada em
     {e(dados.get('gerado_em', '').replace('T', ' às '))}; esta página foi gerada em {hoje.strftime('%d/%m/%Y')}.</p>
</header>

<section>
  <div class="tiles">
    <div class="tile"><div class="lbl">Honorários contratados</div><div class="val">{brl(hon_total, 0)}</div>
      <div class="cap">Soma dos {len(com_valor)} contratos com valor</div></div>
    <div class="tile"><div class="lbl">Faturamento realizado</div><div class="val">{brl(r['realizado'], 0)}</div>
      <div class="cap">Vencido até {hoje.strftime('%d/%m/%Y')} (entradas + parcelas)</div></div>
    <div class="tile"><div class="lbl">A receber</div><div class="val">{brl(r['a_receber'], 0)}</div>
      <div class="cap">Vencimentos até {ult_venc}</div></div>
    <div class="tile"><div class="lbl">Ticket médio geral</div><div class="val">{brl(ticket)}</div>
      <div class="cap">Honorários ÷ {len(com_valor)} contratos</div></div>
    <div class="tile"><div class="lbl">Contratos em {ano_atual}</div><div class="val">{por_ano_ct[ano_atual]}</div>
      <div class="cap">{cap_anos}</div></div>
    <div class="tile"><div class="lbl">Mix de serviços</div><div class="val">{rev} / {bus}</div>
      <div class="cap">{rev} revisional · {bus} busca e apreensão</div></div>
  </div>
</section>

<section>
  <h2>Faturamento mês a mês</h2>
  <p class="note">Tudo que vence no mês: entradas dos contratos fechados + parcelas dos contratos em curso.
     Valores em milhares de reais. As barras claras são vencimentos futuros já contratados.</p>
  <div class="legend">
    <span><i class="sw" style="background:var(--series-2)"></i>Entradas (contratos fechados no mês)</span>
    <span><i class="sw" style="background:var(--series-1)"></i>Parcelas de contratos anteriores</span>
    <span><i class="sw" style="background:var(--series-1);opacity:.42"></i>Ainda a vencer</span>
  </div>
  <div class="scroller">
    <div class="cols">{c_fat}</div>
    <div class="caxis">{t_fat}</div>
    <div class="cvals">{v_fat}</div>
  </div>
</section>

<section>
  <h2>Honorários contratados por mês de fechamento</h2>
  <p class="note">Valor total dos contratos assinados em cada mês. O número embaixo é a quantidade de contratos.</p>
  <div class="scroller">
    <div class="cols">{c_hon}</div>
    <div class="caxis">{t_hon}</div>
    <div class="cvals">{v_hon}</div>
  </div>
</section>

<section>
  <h2>Resumo por ano</h2>
  <div class="tblwrap"><table>
    <thead><tr><th>Ano</th><th class="num">Contratos</th><th class="num">Honorários contratados</th>
      <th class="num">Ticket médio</th><th class="num">Faturamento do ano</th></tr></thead>
    <tbody>{chr(10).join(linhas_ano)}</tbody>
    <tfoot><tr><td>Total</td><td class="num">{n}</td><td class="num">{brl(hon_total, 0)}</td>
      <td class="num">{brl(ticket)}</td><td class="num">{brl(fat_total, 0)}</td></tr></tfoot>
  </table></div>
</section>

<section>
  <h2>Mês a mês — contratos, honorários e ticket médio</h2>
  <p class="note">Só aparecem os meses com contrato fechado. “Faturamento” = entradas + parcelas vencendo no mês.</p>
  <div class="tblwrap"><table>
    <thead><tr><th>Mês</th><th class="num">Contratos</th><th class="num">Honorários contratados</th>
      <th class="num">Ticket médio</th><th class="num">Entradas</th><th class="num">Parcelas</th>
      <th class="num">Faturamento</th></tr></thead>
    <tbody>{chr(10).join(linhas_mes)}</tbody>
  </table></div>
</section>

<section class="grid2">
  <div>
    <h2>Serviços vendidos</h2>
    <p class="note">Honorários contratados por tipo de ação.</p>
    <div class="hbars">{h_serv}</div>
  </div>
  <div>
    <h2>Estados atendidos</h2>
    <p class="note">Top 10 por número de contratos.</p>
    <div class="hbars">{h_uf}</div>
  </div>
</section>

<section>
  <h2>15 maiores contratos</h2>
  <div class="legend">
    <span><i class="sw" style="background:var(--series-1)"></i>Revisional</span>
    <span><i class="sw" style="background:var(--series-2)"></i>Busca e apreensão</span>
  </div>
  <div class="hbars">{h_top}</div>
</section>

<section>
  <h2>Como ler estes números</h2>
  <div class="callout">
    <ul>
      <li><strong>Fonte:</strong> a base do Painel Comercial. Até mai/2026, o histórico da planilha consolidada
          (cláusula 2ª dos contratos assinados); de jun/2026 em diante, as planilhas mensais e as pastas com “OK”,
          com os ajustes já conferidos no painel.</li>
      <li><strong>Faturamento é o previsto em contrato</strong>, não o efetivamente recebido. Não desconta
          inadimplência, renúncia ou acordo antecipado.</li>
      <li><strong>Mês do contrato</strong> = o mês em que o painel conta o fechamento (o da entrada). Entrada paga
          em partes entra no mês de cada parte.</li>
      <li><strong>{len(r['diverg'])} contratos têm diferença</strong> entre o total declarado e entrada + parcelas.
          Vale o valor declarado; os maiores casos:</li>
    </ul>
    <ul>{div_li}</ul>
    <ul>
      <li><strong>{sem_uf} contratos sem UF</strong> identificada.</li>
      <li><strong>{len(r['sem_crono'])} contratos não trazem cronograma</strong> ({brl(sc_total, 0)} no total).
          Foram lançados integralmente no mês de fechamento.</li>
      <li><strong>{len(r['sem_valor'])} contratos ainda sem valor de honorários</strong> ({e(sem_valor_txt)}):
          contam na quantidade, mas não nos honorários nem no ticket médio; só a entrada paga entra no faturamento.</li>
    </ul>
  </div>
</section>

</div>
</div>
</body>
</html>
"""
    return corpo, dict(n=n, hon=hon_total, realizado=r["realizado"], a_receber=r["a_receber"],
                       ticket=ticket, ini=rot(ini), fim=rot(fim_ct))


def main():
    hoje = date.today()
    dados = json.loads(BASE.read_text(encoding="utf-8"))
    antigo = SAIDA.read_text(encoding="utf-8")
    cabeca = antigo[:antigo.index("<body>")]       # mantém o <head> e o estilo da página
    corpo, resumo = gerar(dados, hoje)
    backup = SAIDA.with_name(SAIDA.stem + f"_BACKUP_{hoje:%Y%m%d}.html")
    if not backup.exists():
        shutil.copy2(SAIDA, backup)
    SAIDA.write_text(cabeca + corpo, encoding="utf-8")
    print(json.dumps(resumo, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
