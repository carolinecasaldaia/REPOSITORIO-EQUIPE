#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Honorários recebidos pelo Financeiro do Astrea (boletos PJBank e baixas manuais).

    ~/.cadastro-astrea/venv/bin/python coletar_astrea.py 2025

Antes do ASAAS (ago/2025) as parcelas eram cobradas pelo Astrea. Pedido de
06/11/2026: incluir 2025 no "Total recebido no mês" do Painel Comercial.

Lê, só consultando, a mesma lista da tela Financeiro > Lançamentos
(api/v2/entry/query/list), com a sessão da conta "Claude" do Cadastro Astrea.
Grava dados/at_<mes>.txt no mesmo formato dos arquivos da Conta Azul
(nome|centavos|cat|forma|vencimento|situação|pago|conjuntos|conta|parcela),
um arquivo por mês de PAGAMENTO, e o coletar_financeiro.py junta como fonte "AT".

Só entram receitas pagas (ENTRY_IN, DONE). Os lançamentos "em aberto" de 2025
no Astrea (535 em 06/11/2026) foram migrados para o ASAAS e nunca baixados lá,
então não servem para inadimplência. Valor = valor pago pelo cliente (com
multa/juros, antes da tarifa do boleto), como no ASAAS.
"""

import calendar
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DADOS = AQUI / "dados"
PRODUTIVIDADE = (AQUI.parents[3] / "EMPRESA" / "CLAUDE" / "PRODUTIVIDADE - PRAZOS ASTREA")
sys.path.insert(0, str(PRODUTIVIDADE))
import coletar as base  # noqa: E402  (sessão do Astrea, espera do perfil)

LISTA = base.API + "/entry/query/list"


def baixar(ano):
    sys.path.insert(0, str(base.CADASTRO))
    from src.astrea.navegador import AdaptadorNavegador
    from src.config.settings import get_config
    from src.logs.logger import Log

    base.esperar_perfil()
    registro = Log(base.CASA / "logs", True, datetime.now().strftime("%Y%m%d-%H%M%S"))
    adaptador = AdaptadorNavegador(get_config(recarregar=True), registro, somente_leitura=True)
    cap = {}

    def ao_pedir(r):
        if "entry/query/list" in r.url and "corpo" not in cap:
            cap["corpo"] = json.loads(r.post_data)
            cap["cab"] = {k: v for k, v in r.headers.items()
                          if k.lower() in ("authorization", "content-type")}

    adaptador.conectar()
    lancamentos = {}
    try:
        pg = adaptador.pagina
        pg.on("request", ao_pedir)
        pg.goto("https://astrea.net.br/#/main/financial/entries",
                wait_until="domcontentloaded", timeout=60000)
        for _ in range(30):
            if "corpo" in cap:
                break
            pg.wait_for_timeout(1000)
        if "corpo" not in cap:
            raise RuntimeError("A tela de Lançamentos do Astrea não carregou.")
        # A lista filtra pelo vencimento: busca de jul do ano anterior a mar do
        # seguinte para pegar o que foi pago no ano com vencimento fora dele.
        meses = [(a, m) for a in (ano - 1, ano, ano + 1) for m in range(1, 13)
                 if (ano - 1, 7) <= (a, m) <= (ano + 1, 3)]
        for a, m in meses:
            corpo = dict(cap["corpo"], dayBegin=1, monthBegin=m, yearBegin=a,
                         dayEnd=calendar.monthrange(a, m)[1], monthEnd=m, yearEnd=a)
            r = pg.request.post(LISTA, headers=cap["cab"], data=json.dumps(corpo), timeout=120000)
            if r.status != 200:
                raise RuntimeError("Astrea respondeu %s em %02d/%d." % (r.status, m, a))
            for dia in r.json():
                for e in dia.get("entries", []):
                    lancamentos[e["id"]] = e
    finally:
        adaptador.encerrar()
    return list(lancamentos.values())


def linha(e, mes):
    nome = (e.get("customerName") or e.get("caseCustomerName") or e.get("description") or "?")
    valor = e.get("originalAmountPaid") or e.get("amountPaid") or e.get("amount") or 0
    entrada = (e.get("description") or "").strip().upper().startswith("ENTRADA")
    fl = "r" + ("v" if e["dueDate"][:7] == mes else "")
    return "|".join([
        " ".join(nome.split())[:40], str(round(valor * 100)),
        "CV" if e.get("costCenter") == "Civil" else "--",
        "B" if e.get("bankSlipProvider") else "O",
        e["dueDate"], "R", e["paymentDate"], fl, "C",
        "EN" if entrada else (e.get("order") or "U")])


def main():
    ano = int(sys.argv[1]) if len(sys.argv) > 1 else datetime.now().year - 1
    por_mes = defaultdict(list)
    for e in baixar(ano):
        if e.get("type") == "ENTRY_IN" and e.get("status") == "DONE" \
                and str(e.get("paymentDate", "")).startswith(str(ano)):
            mes = e["paymentDate"][:7]
            por_mes[mes].append(linha(e, mes))
    DADOS.mkdir(exist_ok=True)
    for m in range(1, 13):
        mes = "%d-%02d" % (ano, m)
        linhas = sorted(por_mes.get(mes, []))
        (DADOS / ("at_%s.txt" % mes)).write_text("\n".join(linhas) + ("\n" if linhas else ""),
                                                 encoding="utf-8")
        print("%s: %d recebimentos, R$ %.2f" % (mes, len(linhas),
                                               sum(int(l.split("|")[1]) for l in linhas) / 100))


if __name__ == "__main__":
    main()
