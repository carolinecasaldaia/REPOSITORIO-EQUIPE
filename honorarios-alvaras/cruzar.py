#!/usr/bin/env python3
"""Cruza os alvarás/pagamentos achados nos autos com os créditos dos extratos.

Uso:  ~/.honorarios-alvaras/venv/bin/python cruzar.py ["<pasta dos extratos>"] [--desde 2025-01-01]
      sem pasta, lê Drive/Documentos Escritório /EMPRESA/FINANCEIRO/PAINEL FINANCEIRO/EXTRATOS

Regras (cada crédito casa com no máximo um processo):
  1. VALOR   crédito a até 1% (mín. R$ 50) de um valor citado no ato  → "Confirmado"
             a até 8% (correção monetária/juros entre a conta e o alvará) → "Provável"
     janela: de 5 dias antes (20, se o crédito vem do TJ) a 120 dias depois do ato.
     Créditos de plataforma (Pjbank etc.) não casam por valor: são parcelas de contrato.
     PIX do parceiro (Israel) não casa com processo.
  2. NOME    PIX/TED de pessoa cujo nome bate com o do cliente (também abreviado,
             ex.: "ISRAEL C S S" = Israel Correia Souza da Silva) → contratual "Provável"
  3. DATA    crédito Judicial sem valor que bata, com UM único alvará expedido/levantado
             nos 60 dias anteriores → "Conferir"
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import levantar_alvaras as L  # noqa: E402
import ler_extratos as X  # noqa: E402

gr = L.gr
ETAPAS_DINHEIRO = ("extinto_pago", "levantado", "expedido", "determinado", "deposito", "sisbajud_pos", "pedido")
FORA = ("Interna", "Rendimento", "Parceiro", "Pessoal", "Extrajudicial")
_PREP = {"DA", "DE", "DO", "DAS", "DOS", "E"}


def _tokens(nome):
    return [t for t in gr.norm(nome).split() if t not in _PREP]


def nome_bate(cliente, desc):
    """'ISRAEL C S S 0765...' x 'Israel Correia Souza da Silva'; 'JOSE R FERREIRA' etc."""
    cli = _tokens(cliente)
    if len(cli) < 2:
        return False
    d = _tokens(re.sub(r"PIX|TED|DOC|RECEBID[OA]|AGENDAD[OA]|ENVIAD[OA]|TRANSF\w*|INTERNET BANKING|\d+", " ", gr.norm_texto(desc)))
    if not d or d[0] != cli[0]:
        return False
    resto_d, resto_c = d[1:], cli[1:]
    if len(resto_d) < 2 and not (resto_d and len(resto_d[0]) > 3 and resto_d[0] in resto_c):
        return False
    # cada pedaço do extrato precisa bater, EM ORDEM, com um pedaço do nome do cliente:
    # palavra igual, inicial, ou (só o último, cortado pelo banco) começo da palavra.
    # O 2º nome não pode ser pulado: "JOSE CICERO DOS SANTOS" ≠ José Severino dos Santos.
    j = 0
    for k, t in enumerate(resto_d):
        ultimo = k == len(resto_d) - 1
        if ultimo and t == "D":          # "... Nascimento d" = "de" cortado
            break
        achou = False
        while j < len(resto_c):
            c = resto_c[j]
            j += 1
            if t == c or (len(t) == 1 and c[0] == t) or (ultimo and len(t) >= 2 and c.startswith(t)):
                achou = True
                break
            if k == 0:
                return False
        if not achou:
            return False
    return True


def cruzar(procs, eventos, creditos):
    por_num = {p["num"]: p for p in procs}
    usados, casamentos = set(), {}      # num -> lista de (credito, regra, nivel)
    candidatos = []
    for ci, c in enumerate(creditos):
        if c["categoria"] in FORA or c.get("regra_manual", {}).get("processo"):
            continue
        for num, evs in eventos.items():
            for e in evs:
                if e["etapa"] not in ETAPAS_DINHEIRO or not e["valores"]:
                    continue
                dias = (c["data"] - datetime.date.fromisoformat(e["data"])).days
                # o Diário costuma publicar depois que o TJ já pagou: para crédito judicial
                # aceita até 20 dias ANTES da publicação
                if not (-20 if c["categoria"] == "Judicial" else -5) <= dias <= 120:
                    continue
                # PIX de pessoa com valor igual é coincidência fácil (R$ 500, R$ 1.000…):
                # só entra depois do casamento por nome e como "Conferir".
                if c["categoria"] == "Plataforma":   # boletos/parcelas de contrato (Pjbank etc.)
                    continue
                pessoa = c["categoria"] == "Pessoa"
                for v in e["valores"]:
                    dif = abs(v - c["valor"])
                    if dif <= max(50, 0.01 * v):
                        # crédito ANTES da publicação do ato: pode ser de outro alvará com valor parecido
                        # (caso Givaldo x Jonas, 22/10/2026) → só "Provável"
                        antes = dias < 0
                        candidatos.append((3 if pessoa else (2 if antes else 1), dif, ci, num,
                                           "Valor igual ao do ato de %s (%s)%s" %
                                           (gr.data_br(e["data"]), L.ROTULO[e["etapa"]],
                                            ", publicado depois do crédito" if antes else ""),
                                           "Conferir" if pessoa else ("Provável" if antes else "Confirmado")))
                    elif dif <= 0.08 * v and not pessoa:
                        candidatos.append((2, dif, ci, num, "Valor próximo (%.1f%%) ao do ato de %s" %
                                           (100 * dif / v, gr.data_br(e["data"])), "Provável"))
    # regra manual (pagadores.json) com processo definido: vence tudo
    for ci, c in enumerate(creditos):
        r = c.get("regra_manual") or {}
        if r.get("processo") in por_num:
            candidatos.append((-2, 0, ci, r["processo"], "Informado pela Caroline: " + r.get("nota", ""),
                               "Confirmado"))
    # número do processo escrito na descrição do crédito (RPV/alvará da Justiça Federal etc.)
    for ci, c in enumerate(creditos):
        dig = re.sub(r"\D", "", c["descricao"])
        for p in procs:
            if len(p["num"]) == 20 and p["num"] in dig:
                candidatos.append((-1, 0, ci, p["num"], "Número do processo na descrição do crédito", "Confirmado"))
    for ci, c in enumerate(creditos):
        if c["categoria"] not in ("Pessoa", "Plataforma") or c.get("regra_manual"):
            continue
        for p in procs:
            if p["cliente"] and nome_bate(p["cliente"], c["descricao"]):
                candidatos.append((0, 0, ci, p["num"], "PIX/TED do próprio cliente (contratual?)", "Provável"))
    candidatos.sort()
    for pri, dif, ci, num, regra, nivel in candidatos:
        if ci in usados:
            continue
        usados.add(ci)
        casamentos.setdefault(num, []).append((creditos[ci], regra, nivel))
    # regra 3: judicial sem par, um único alvará na janela
    for ci, c in enumerate(creditos):
        if ci in usados or c["categoria"] != "Judicial":
            continue
        janela = [num for num, evs in eventos.items()
                  if any(e["etapa"] in ("expedido", "levantado", "extinto_pago") and
                         0 <= (c["data"] - datetime.date.fromisoformat(e["data"])).days <= 60 for e in evs)
                  and num not in casamentos]
        if len(janela) == 1:
            usados.add(ci)
            casamentos.setdefault(janela[0], []).append((c, "Único alvará expedido nos 60 dias anteriores",
                                                         "Conferir"))
    return casamentos, usados


FIN = Path.home() / ("Library/CloudStorage/GoogleDrive-contato@carolinemacedoadv.com/Meu Drive/"
                      "Documentos Escritório /EMPRESA/FINANCEIRO/PAINEL FINANCEIRO/dados")
TIPOS = {"E": "Entrada", "H": "Parcela de honorários", "X": "Pix avulso/parceiro"}
ACOES = {"BA": "Busca e Apreensão", "RV": "Revisional", "SE": "Superendividamento", "CV": "Cível", "PA": "Parceiro"}
FORMAS = {"B": "Boleto", "P": "Pix", "C": "Cartão", "L": "Perda/acordo", "O": "Outro"}


def ler_plataformas(desde):
    """Recebidos do Asaas e da Conta Azul, já juntados pelo Painel Financeiro (dados/financeiro_<mes>.json).
    Fica de fora o que já está nos extratos: Astrea/PJBank (= 'Pjbank' no Santander PJ) e, na Conta Azul,
    os lançamentos que são PIX de banco (forma 'O') ou do parceiro ('X')."""
    out, vistos = [], set()
    for f in sorted(FIN.glob("financeiro_*.json")):
        for l in json.loads(f.read_text(encoding="utf-8")).get("linhas", []):
            p = l.split("|")
            if len(p) < 11 or "r" not in p[9] or l in vistos or p[0] not in ("AS", "CA"):
                continue
            if p[0] == "CA" and (p[3] == "X" or p[5] == "O"):
                continue
            vistos.add(l)
            d = datetime.date.fromisoformat(p[8]) if p[8] else None
            if not d or d < desde:
                continue
            out.append({"data": d, "origem": p[0], "cliente": p[1], "valor": int(p[2]) / 100,
                        "tipo": TIPOS.get(p[3], p[3]), "acao": ACOES.get(p[4], ""),
                        "forma": FORMAS.get(p[5], p[5]), "parcela": p[10]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta", nargs="?", default=str(FIN.parent / "EXTRATOS"),
                    help="pasta dos extratos (padrão: EMPRESA/FINANCEIRO/PAINEL FINANCEIRO/EXTRATOS)")
    ap.add_argument("--desde", default="2025-01-01")
    a = ap.parse_args()
    desde = datetime.date.fromisoformat(a.desde)
    procs, eventos, _, _ = L.analisar(desde)
    creditos, arquivos, ignorados = X.ler_pasta(a.pasta)
    creditos = [c for c in creditos if c["data"] >= desde]
    casamentos, usados = cruzar(procs, eventos, creditos)
    destino = L.gerar_planilha(procs, eventos, desde, casamentos=casamentos, creditos=creditos,
                               usados=usados, arquivos=arquivos, ignorados=ignorados,
                               plataformas=ler_plataformas(desde))
    print("Planilha:", destino)
    print("Extratos lidos:", json.dumps(arquivos, ensure_ascii=False, indent=1))
    if ignorados:
        print("Ignorados:", ignorados)
    print("Créditos de terceiros: %d | casados: %d | processos com crédito: %d" % (
        sum(1 for c in creditos if c["categoria"] not in ("Interna", "Rendimento")), len(usados), len(casamentos)))


if __name__ == "__main__":
    main()
