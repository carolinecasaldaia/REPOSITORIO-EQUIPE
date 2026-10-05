#!/usr/bin/env python3
"""Prepara os dados do PAINEL DE ENVIOS (página publicada no claude.ai).

Lê a planilha CONTROLE DE ENVIO do mês e os PDFs gerados por gerar_relatorios.py e
monta, numa pasta de saída:
    painel.html          a página (copiada de PAINEL/painel.html)
    dados.json           um registro por cliente: dia de envio, vencimento,
                         financeiro (interno), itens a conferir, resumo, PDF...
    pdf/<id>.pdf         os relatórios, com nome neutro (sem nome nem CPF na URL)

O que a equipe muda no painel (o check de ENVIADO, quem marcou e quando, e as
anotações) NÃO fica aqui: fica no banco de dados do próprio painel, que sobrevive
a cada atualização mensal. O CPF não vai para o painel.

Uso:  python gerar_painel.py 2026-09 <pasta de saída>
"""
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

import gerar_relatorios as g

PASTA = Path(__file__).resolve().parent


def montar(ano, mes, saida):
    rotulo = g.rotulo_mes(ano, mes)
    pasta_mes = PASTA / rotulo
    controle = pasta_mes / ("CONTROLE DE ENVIO - %s.xlsx" % rotulo)
    import openpyxl
    ws = openpyxl.load_workbook(controle, data_only=True)["CLIENTES"]
    cab = [c.value for c in ws[1]]
    saida = Path(saida)
    (saida / "pdf").mkdir(parents=True, exist_ok=True)
    for velho in (saida / "pdf").glob("*.pdf"):
        velho.unlink()
    pdfs = {p.name: p for p in (pasta_mes / "RELATÓRIOS (PDF)").rglob("*.pdf")}

    clientes, dias = [], {}
    for linha in ws.iter_rows(min_row=2):
        r = dict(zip(cab, linha))
        v = {k: (c.value if c.value is not None else "") for k, c in r.items()}
        if not v.get("CLIENTE"):
            continue
        ident = hashlib.sha1(("%s|%s" % (rotulo, v["CHAVE"])).encode()).hexdigest()[:12]
        nome_pdf = "%s - %s.pdf" % (g.nome_arquivo(v["CLIENTE"]), rotulo)
        origem = pdfs.get(nome_pdf)
        if origem:
            shutil.copyfile(origem, saida / "pdf" / (ident + ".pdf"))
        m = re.match(r"(\d+) - (\d\d)/(\d\d) \((\w+)\)", str(v["DIA DE ENVIO"]))
        n, dd, mm, sem = int(m.group(1)), m.group(2), m.group(3), m.group(4)
        ano_env = ano + 1 if mes == 12 else ano
        dias[n] = {"n": n, "data": "%d-%s-%s" % (ano_env, mm, dd), "rotulo": "%s/%s" % (dd, mm), "semana": sem}
        whatsapp = linha[cab.index("WHATSAPP")].hyperlink
        fin = str(v["FINANCEIRO (INTERNO)"])
        clientes.append({
            "id": ident,
            "dia": n,
            "nome": v["CLIENTE"],
            "telefone": str(v["TELEFONE"] or ""),
            "whatsapp": whatsapp.target if whatsapp else "",
            "vencimento": str(v["VENCIMENTO DA PARCELA"] or ""),
            "financeiro": fin,
            "atraso": fin.startswith("EM ATRASO"),
            "verificar": fin.startswith("VERIFICAR"),
            "novidade": str(v["NOVIDADE NO MÊS?"]).upper() == "SIM",
            "conferir": [c.strip() for c in str(v["CONFERIR ANTES DE ENVIAR"] or "").split(";") if c.strip()],
            "resumo": [x.strip() for x in str(v["RESUMO DO MÊS"] or "").split("|") if x.strip()],
            "processos": [p for p in str(v["PROCESSOS"] or "").split("\n") if p],
            "pdf": ("pdf/%s.pdf" % ident) if origem else "",
            "pdf_nome": nome_pdf,
        })
    dados = {
        "mes": "%d-%02d" % (ano, mes),
        "rotulo": "%s/%d" % (g.MESES[mes - 1], ano),
        "gerado_em": g.datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "dias": [dias[k] for k in sorted(dias)],
        "clientes": clientes,
    }
    (saida / "dados.json").write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    shutil.copyfile(PASTA / "PAINEL" / "painel.html", saida / "painel.html")
    # O Artifact aceita até 255 arquivos por publicação: lote 1 = dados + 250 PDFs, lote 2 = o resto
    pdfs_pub = sorted("pdf/" + p.name for p in (saida / "pdf").glob("*.pdf"))
    lotes = [["dados.json"] + pdfs_pub[:250]] + [pdfs_pub[i:i + 250] for i in range(250, len(pdfs_pub), 250)]
    for i, lote in enumerate(lotes, 1):
        (saida / ("lote%d.json" % i)).write_text(json.dumps(lote), encoding="utf-8")
    print("PAINEL_OK %d clientes, %d PDFs, %d dias, %d lote(s) de publicação -> %s"
          % (len(clientes), sum(1 for c in clientes if c["pdf"]), len(dias), len(lotes), saida))


if __name__ == "__main__":
    a, m = map(int, sys.argv[1].split("-"))
    montar(a, m, sys.argv[2])
