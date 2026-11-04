#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Painel comercial: traz o histórico da planilha "DADOS CONTRATOS - CONSOLIDADO
2023-2026.csv" (A - COMERCIAL) para o painel, um documento por mês na coleção
"historico" (cada um com a lista de contratos do mês dentro).

    python3 importar_consolidado.py

Só importa os meses ANTERIORES a junho/2026. De junho em diante o painel já
tem fonte própria e conferida (planilhas mensais de junho e julho, pastas com
OK de agosto em diante), e a consolidada não é usada para não contar em dobro.

Os números vêm como estão na planilha consolidada: nada é estimado aqui.
"""

import csv
import json
import re
import unicodedata
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PLANILHA = AQUI.parent.parent / "DADOS CONTRATOS - CONSOLIDADO 2023-2026.csv"
ATE = "2026-06"            # exclusivo
MESES = ("Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro")


def slug(texto):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-").lower()[:80]


def num(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s.replace(",", ".")) if s.count(",") == 1 and "." not in s else float(s)
    except ValueError:
        return None


def data_iso(s):
    """'2023-09-15' -> '15.09.2023' (formato que o painel lê)."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", (s or "").strip())
    return "%s.%s.%s" % (m.group(3), m.group(2), m.group(1)) if m else None


def tipo(servico):
    s = (servico or "").lower()
    if "busca" in s:
        return "BUSCA E APREENSÃO"
    if "revisional" in s:
        return "REVISIONAL VEICULAR"
    return (servico or "").strip().upper() or None


def forma(pagamento):
    p = (pagamento or "").lower()
    if "cart" in p:
        return "Cartão"
    if "pix" in p:
        return "PIX"
    if "boleto" in p:
        return "Boleto"
    return None


def main():
    texto = PLANILHA.read_text(encoding="utf-8-sig")
    blocos = texto.split("\n\n")
    contratos = list(csv.DictReader(blocos[0].strip().splitlines(), delimiter=";"))

    resumo = {}
    for b in blocos[1:]:
        if b.strip().startswith("RESUMO MENSAL"):
            for r in csv.DictReader(b.strip().splitlines()[1:], delimiter=";"):
                resumo[r["Mês"]] = r

    por_mes = {}
    for c in contratos:
        mes = (c.get("Mês de fechamento") or "").strip()
        if not re.match(r"\d{4}-\d{2}$", mes) or mes >= ATE:
            continue
        banco = (c.get("Banco / Processo") or "").strip()
        uf = (c.get("UF") or "").strip()
        qtd = num(c.get("Qtd parcelas"))
        obs = []
        if (c.get("Divergência") or "").strip():
            obs.append("Divergência na planilha: " + c["Divergência"].strip())
        por_mes.setdefault(mes, []).append({
            "mes": mes, "cliente": c["Cliente"].strip().upper(), "pasta": "",
            "tipo_acao": tipo(c.get("Serviço")),
            "banco_adverso": None if not banco or banco.lower().startswith("proc") else banco,
            "uf": uf if re.match(r"^[A-Z]{2}$", uf) else None, "cidade": None,
            "valor_total": num(c.get("Total honorários (R$)")),
            "entrada": num(c.get("Entrada (R$)")), "entrada_data": data_iso(c.get("Vencimento da entrada")),
            "entrada_partes": [], "entrada_paga_asaas": None, "entrada_pagamentos": [],
            "parcelas_qtd": int(qtd) if qtd is not None else None,
            "parcelas_valor": num(c.get("Valor da parcela (R$)")),
            "parcelas_inicio": data_iso(c.get("1ª parcela")), "parcelas_fim": data_iso(c.get("Última parcela")),
            "forma_parcelas": forma(c.get("Pagamento")),
            "astrea": None, "marcado_ok": True, "previa": False, "outro_mes": False,
            "ajuste": "", "obs": " ".join(obs),
        })

    saida = AQUI / "dados" / "historico"
    saida.mkdir(parents=True, exist_ok=True)
    for f in saida.glob("*.json"):
        f.unlink()
    # Meses sem contrato mas com caixa (só parcelas) também entram no resumo,
    # para a evolução não pular o mês; ficam com a lista vazia.
    meses = sorted(set(por_mes) | {m for m in resumo if m < ATE})
    for mes in meses:
        linhas = por_mes.get(mes, [])
        usados = set()
        for l in linhas:
            base = "%s__%s" % (mes, slug(l["cliente"]))
            l["id"], n = base, 2
            while l["id"] in usados:
                l["id"], n = "%s-%d" % (base, n), n + 1
            usados.add(l["id"])
        r = resumo.get(mes, {})
        doc = {
            "mes": mes, "rotulo": "%s/%s" % (MESES[int(mes[5:]) - 1], mes[:4]),
            "fonte": "planilha consolidada 2023-2026", "previa": False,
            "caixa": num(r.get("Entradas do mês (R$)")),
            "faturamento": num(r.get("Faturamento do mês (R$)")),
            "conciliado": "", "contratos": len(linhas), "linhas": linhas,
        }
        (saida / (mes + ".json")).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    print("%d meses, %d contratos em %s" % (len(meses), sum(len(v) for v in por_mes.values()), saida))


if __name__ == "__main__":
    main()
