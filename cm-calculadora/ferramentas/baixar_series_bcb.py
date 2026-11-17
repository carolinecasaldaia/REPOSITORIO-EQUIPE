"""Baixa séries mensais oficiais do Banco Central (SGS) e grava no formato da calculadora.

Fica FORA de src/cm_calc de propósito: o motor e os serviços não acessam a rede. Este utilitário só
baixa dados públicos (nenhum dado de cliente sai do computador) e grava, para cada série:
    <PASTA>/<NOME>.csv        competência;variação % (vírgula decimal)
    <PASTA>/<NOME>.fonte.txt  órgão, código SGS, URL e data/hora da consulta

uso: python ferramentas/baixar_series_bcb.py PASTA NOME=CODIGO [NOME=CODIGO ...] [--desde DD/MM/AAAA]
ex.: python ferramentas/baixar_series_bcb.py ~/caso/indices INPC=188 SELIC=4390 --desde 01/01/2019

Códigos usuais (confira o nome da série em https://www3.bcb.gov.br/sgspub antes do primeiro uso):
    INPC 188 · IPCA 433 · IGPM 189 · SELIC (acumulada no mês) 4390
    Taxa média BACEN (regra do escritório, financiamento de bens, mês da assinatura do contrato):
    mensal 25471 · anual 20749 — baixar em pasta separada dos índices de correção.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={ini}&dataFinal={fim}"


def baixar(codigo: int, desde: str, ate: str) -> list[dict]:
    url = URL.format(codigo=codigo, ini=desde, fim=ate)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        dados = json.loads(r.read().decode("utf-8"))
    if not isinstance(dados, list) or not dados:
        raise SystemExit(f"série {codigo}: resposta vazia ou inválida")
    return dados


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    pasta = Path(argv[0]).expanduser()
    desde = "01/01/2015"
    pares = []
    it = iter(argv[1:])
    for a in it:
        if a == "--desde":
            desde = next(it)
        else:
            nome, cod = a.split("=")
            pares.append((nome.upper(), int(cod)))
    ate = date.today().strftime("%d/%m/%Y")
    pasta.mkdir(parents=True, exist_ok=True)
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    for nome, cod in pares:
        dados = baixar(cod, desde, ate)
        linhas = [f"{r['data'][6:10]}-{r['data'][3:5]};{str(r['valor']).replace('.', ',')}" for r in dados]
        (pasta / f"{nome}.csv").write_text("\n".join(linhas) + "\n", encoding="utf-8")
        (pasta / f"{nome}.fonte.txt").write_text(
            f"Banco Central do Brasil — SGS série {cod} ({nome}); {URL.format(codigo=cod, ini=desde, fim=ate)}; "
            f"consultado em {agora}", encoding="utf-8")
        print(f"{nome} (SGS {cod}): {len(dados)} meses, {dados[0]['data'][3:]} a {dados[-1]['data'][3:]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
