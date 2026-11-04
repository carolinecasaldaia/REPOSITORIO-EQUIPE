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
            "meses": meses, "contratos": contratos}


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
