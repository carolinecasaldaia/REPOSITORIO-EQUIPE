#!/usr/bin/env python3
"""Primeira etapa da rotina mensal: monta as listas de processos que o Astrea vai ler.

Grava em <MÊS ANO>/_dados/:
    astrea_entrada.json        processos FORA do TJAL (histórico do Astrea)
    diligencias_entrada.json   todos os processos da rodagem (tarefas de diligência)

Depois a rotina roda, com o Python do Cadastro Astrea:
    ler_astrea.py astrea_entrada.json astrea.json
    ler_astrea.py diligencias_entrada.json diligencias.json --diligencias
e só então gerar_relatorios.py, que aproveita esses arquivos.

Uso:  python preparar_listas.py [AAAA-MM]     (sem argumento: mês anterior)
Imprime o caminho da pasta _dados e o mês escolhido.
"""
import datetime
import json
import sys

import gerar_relatorios as g


def mes_anterior(hoje=None):
    hoje = hoje or datetime.date.today()
    d = hoje.replace(day=1) - datetime.timedelta(days=1)
    return d.year, d.month


def main():
    if len(sys.argv) > 1:
        ano, mes = map(int, sys.argv[1].split("-"))
    else:
        ano, mes = mes_anterior()
    dados = g.PASTA / g.rotulo_mes(ano, mes) / "_dados"
    dados.mkdir(parents=True, exist_ok=True)
    clientes, _ = g.ler_rodagem(g.localizar_rodagem())
    todos = sorted({n for c in clientes.values() for n in c["processos"] if len(n) == 20})
    fora_tjal = [n for n in todos if not g.tem_esaj(n)]
    (dados / "astrea_entrada.json").write_text(json.dumps(fora_tjal), encoding="utf-8")
    (dados / "diligencias_entrada.json").write_text(json.dumps(todos), encoding="utf-8")
    print("MES=%d-%02d" % (ano, mes))
    print("DADOS=%s" % dados)
    print("%d processos fora do TJAL, %d processos no total" % (len(fora_tjal), len(todos)))


if __name__ == "__main__":
    main()
