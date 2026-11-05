#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Painel Comercial Contratos: gera o arquivo que o painel lê pelo Google Drive.

    ~/.cadastro-astrea/venv/bin/python gerar_dados_painel.py

Roda de hora em hora pegando carona no robô do Cadastro Astrea
(~/.cadastro-astrea/rodar.sh), que já tem permissão de ler o Drive. Desde
23/10/2026 é assim que o painel se atualiza: as tarefas agendadas do Claude
não conseguem gravar no banco do Artifact sem alguém aprovar na hora.

1. Recoleta o mês corrente e, nos primeiros 5 dias do mês, também o anterior
   (fechamento) — só de outubro/2026 em diante; meses anteriores já estão
   fechados e conferidos e não são mexidos.
2. Junta tudo (dados/AAAA-MM/, dados/mes_*.json e dados/historico/) em
   painel-comercial-dados.json, nesta pasta. O arquivo é regravado no mesmo
   lugar, para o Drive manter o mesmo ID — é por esse ID que o painel o acha.
"""

import json
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
DADOS = AQUI / "dados"
SAIDA = AQUI / "painel-comercial-dados.json"
PRIMEIRO_MES_AUTOMATICO = "2026-10"

# Campos que o painel usa; o resto (pagamentos detalhados, pasta) fica de fora
# para o arquivo continuar pequeno.
CAMPOS = ("id", "mes", "cliente", "tipo_acao", "banco_adverso", "uf", "cidade",
          "valor_total", "entrada", "entrada_data", "entrada_partes",
          "entrada_paga_asaas", "parcelas_qtd", "parcelas_valor",
          "parcelas_inicio", "parcelas_fim", "forma_parcelas", "previa",
          "outro_mes", "ajuste", "obs")


def meses_a_coletar(hoje):
    atual = "%d-%02d" % (hoje.year, hoje.month)
    ano, m = (hoje.year, hoje.month - 1) if hoje.month > 1 else (hoje.year - 1, 12)
    anterior = "%d-%02d" % (ano, m)
    alvo = [atual]
    if hoje.day <= 5:
        alvo.insert(0, anterior)
    return [m for m in alvo if m >= PRIMEIRO_MES_AUTOMATICO]


def coletar(meses):
    import coletar_mes
    for mes in meses:
        try:
            coletar_mes.coletar(mes)
        except SystemExit as aviso:            # pasta do mês ainda não existe
            print("%s: %s" % (mes, aviso))
        except Exception:
            print("%s: falhou\n%s" % (mes, traceback.format_exc()))


FINANCEIRO = AQUI.parent / "PAINEL FINANCEIRO" / "dados"


def recebimentos():
    """Parcelas de honorários recebidas em cada mês, separadas pelo vencimento.

    Pedido de 05/11/2026: ver de onde veio o total recebido de parcelas no mês.
    Lê os dados/financeiro_<mes>.json do Painel Financeiro (coleta diária do
    ASAAS e da Conta Azul) e usa o mesmo critério de "recebido no mês" de lá
    (conjunto "r"). Só parcelas (tipo H): entrada tem card próprio e Pix
    avulso/parceiro fica de fora.
    Entra no mês pela data de crédito; a classificação é pela data em que o
    cliente pagou, comparada com o vencimento:
      do_mes      paga em dia (no mês do vencimento)
      atrasadas   paga depois do mês do vencimento   (origem = mês do vencimento)
      adiantadas  paga antes do mês do vencimento    (origem = mês do vencimento)
    """
    saida = {}
    for f in sorted(FINANCEIRO.glob("financeiro_*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            mes = d["mes"]
            grupos = {g: {"v": 0, "n": 0, "origem": {}, "itens": []}
                      for g in ("do_mes", "atrasadas", "adiantadas")}
            for linha in d.get("linhas", []):
                c = linha.split("|")
                if len(c) < 10 or c[3] != "H" or "r" not in c[9]:
                    continue
                # Atraso é medido pelo dia em que o cliente pagou, não pelo crédito:
                # cartão pago no vencimento (15/09) cai na conta só em outubro e
                # não é dívida atrasada. Sem data de pagamento, vale o mês do crédito.
                venc, pagou = c[6][:7], (c[8] or "")[:7] or mes
                g = grupos["do_mes" if pagou == venc else "atrasadas" if pagou > venc else "adiantadas"]
                cent = int(c[2])
                g["v"] += cent
                g["n"] += 1
                g["origem"][venc] = g["origem"].get(venc, 0) + cent
                if g is not grupos["do_mes"]:
                    g["itens"].append([c[1], round(cent / 100, 2), c[6], c[8], c[0]])
            for g in grupos.values():
                g["v"] = round(g["v"] / 100, 2)
                g["origem"] = {k: round(v / 100, 2) for k, v in sorted(g["origem"].items())}
                g["itens"].sort(key=lambda x: (x[2], x[0]))
            grupos["atualizado_em"] = d.get("atualizado_em")
            saida[mes] = grupos
        except Exception:
            print("%s: recebimentos não lidos\n%s" % (f.name, traceback.format_exc()))
    return saida


def montar():
    contratos, meses = [], {}
    for f in sorted(DADOS.glob("mes_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        meses[d["mes"]] = d
    for pasta in sorted(p for p in DADOS.iterdir() if p.is_dir() and p.name[:2] == "20"):
        for f in sorted(pasta.glob("*.json")):
            l = json.loads(f.read_text(encoding="utf-8"))
            contratos.append({k: l.get(k) for k in CAMPOS})
    for f in sorted((DADOS / "historico").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        linhas = d.pop("linhas", [])
        meses.setdefault(d["mes"], d)
        contratos.extend({k: l.get(k) for k in CAMPOS} for l in linhas)
    return {"gerado_em": datetime.now().strftime("%Y-%m-%dT%H:%M"),
            "meses": meses, "contratos": contratos, "recebimentos": recebimentos()}


def main():
    coletar(meses_a_coletar(date.today()))
    dados = montar()
    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    # Regrava no mesmo arquivo (sem renomear) para o Drive manter o ID.
    with open(SAIDA, "w", encoding="utf-8") as f:
        f.write(texto)
    print("%s: %d contratos, %d meses, %d KB" % (
        dados["gerado_em"], len(dados["contratos"]), len(dados["meses"]), len(texto) // 1024))


if __name__ == "__main__":
    main()
