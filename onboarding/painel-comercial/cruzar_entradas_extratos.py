#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Entradas de contrato pagas por Pix direto na conta (sem passar por ASAAS,
Conta Azul ou Astrea). Pedido de 06/11/2026: em 2025 quase nenhuma entrada
foi lançada em sistema; o dinheiro caiu por Pix no Santander PJ.

    ~/.honorarios-alvaras/venv/bin/python cruzar_entradas_extratos.py

Lê todos os créditos dos extratos de PAINEL FINANCEIRO/EXTRATOS com o leitor
do Levantamento de Alvarás (repo automacoes-claude/honorarios-alvaras) e casa
cada entrada combinada nos contratos (ou cada parte dela) com um crédito:
  - mesmo cliente: 1º nome igual e mais 2 nomes iguais (tolera Sousa/Souza e o
    corte do nome no extrato); Pix pago por parente/terceiro NÃO entra;
  - mesmo valor, ao centavo;
  - data até 20 dias antes ou depois da data combinada da entrada (sem data:
    de 15 dias antes do mês do contrato até 75 dias depois).
Cada crédito casa uma vez só. Grava dados/entradas_extrato.json; o
gerar_dados_painel.py soma no grupo "entradas" o que ainda não estiver
recebido por sistema (mesmo cliente e valor, até 5 dias).

Só roda de novo quando a pasta EXTRATOS muda (o rodar.sh chama toda hora).
"""
import json
import re
import sys
import unicodedata
from datetime import date, timedelta
from difflib import SequenceMatcher
from pathlib import Path

AQUI = Path(__file__).resolve().parent
EXTRATOS = AQUI.parent / "PAINEL FINANCEIRO" / "EXTRATOS"
SAIDA = AQUI / "dados" / "entradas_extrato.json"
DADOS_PAINEL = AQUI / "painel-comercial-dados.json"
LEITOR = Path.home() / "AUTOMACOES" / "automacoes-claude" / "honorarios-alvaras"

STOP = {"DE", "DA", "DO", "DOS", "DAS", "E", "PIX", "RECEBIDO", "RECEBIDA", "TED",
        "TRANSF", "RECEBIMENTO", "DOC"}


def tokens(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    return [t for t in re.sub(r"[^A-Z ]+", " ", s).split() if t not in STOP]


def mesmo_cliente(cliente, descricao):
    c, d = tokens(cliente), tokens(descricao)
    if len(c) < 2 or not d or c[0] not in d:
        return False
    i = d.index(c[0])
    resto = d[i:i + 6]

    def igual(t, x):
        return (x == t or (len(t) >= 4 and SequenceMatcher(None, t, x).ratio() >= 0.8)
                or (len(x) >= 3 and t.startswith(x) and x == resto[-1]))   # nome cortado
    acertos = sum(1 for t in c[1:] if any(igual(t, x) for x in resto[1:]))
    return acertos >= min(2, len(c) - 1)


def data_br(s):
    m = re.match(r"(\d{2})[./](\d{2})[./](\d{4})", s or "")
    return date(int(m[3]), int(m[2]), int(m[1])) if m else None


def assinatura():
    return sorted("%s|%d|%d" % (p.relative_to(EXTRATOS), p.stat().st_size, int(p.stat().st_mtime))
                  for p in EXTRATOS.rglob("*") if p.is_file())


def main():
    try:
        antes = json.loads(SAIDA.read_text(encoding="utf-8"))
    except Exception:
        antes = {}
    contratos = json.loads(DADOS_PAINEL.read_text(encoding="utf-8"))["contratos"]
    chave = assinatura() + sorted("%s|%s|%s" % (k["id"], k.get("entrada"), k.get("entrada_data"))
                                  for k in contratos)
    if antes.get("assinatura") == chave and "--forcar" not in sys.argv:
        print("Extratos e contratos sem mudança; nada a fazer.")
        return
    sys.path.insert(0, str(LEITOR))
    import ler_extratos
    creditos, _, _ = ler_extratos.ler_pasta(EXTRATOS)
    cred = [c for c in creditos if c["categoria"] in ("Pessoa", "Não identificado", "Extrajudicial")]
    for c in cred:
        c["d"] = c["data"] if isinstance(c["data"], date) else date.fromisoformat(str(c["data"])[:10])
        c["cent"] = round(c["valor"] * 100)
    usados, achados = set(), []
    for k in contratos:
        partes = [(p["valor"], data_br(p.get("data"))) for p in (k.get("entrada_partes") or [])
                  if p.get("valor")]
        if not partes and k.get("entrada"):
            partes = [(k["entrada"], data_br(k.get("entrada_data")))]
        a, m = map(int, k["mes"].split("-"))
        inicio = date(a, m, 1) - timedelta(days=15)
        for valor, d0 in partes:
            alvo = round(valor * 100)
            de, ate = ((d0 - timedelta(days=20), d0 + timedelta(days=20)) if d0
                       else (inicio, inicio + timedelta(days=90)))
            cand = [i for i, c in enumerate(cred) if i not in usados and c["cent"] == alvo
                    and de <= c["d"] <= ate and mesmo_cliente(k["cliente"], c["descricao"])]
            if not cand:
                continue
            i = min(cand, key=lambda i: abs((cred[i]["d"] - (d0 or cred[i]["d"])).days))
            usados.add(i)
            c = cred[i]
            achados.append({"contrato": k["id"], "mes_contrato": k["mes"], "cliente": k["cliente"],
                            "data": c["d"].isoformat(), "centavos": alvo,
                            "conta": "%s %s" % (c["banco"], c["conta"])})
    achados.sort(key=lambda x: x["data"])
    SAIDA.parent.mkdir(exist_ok=True)
    SAIDA.write_text(json.dumps({"assinatura": chave, "entradas": achados}, ensure_ascii=False),
                     encoding="utf-8")
    print("%d entradas achadas nos extratos (R$ %.2f)."
          % (len(achados), sum(x["centavos"] for x in achados) / 100))


if __name__ == "__main__":
    main()
