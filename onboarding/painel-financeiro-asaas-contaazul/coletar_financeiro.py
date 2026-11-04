#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Painel financeiro (ASAAS + Conta Azul): recebido no mês e inadimplência.

    ~/.cadastro-astrea/venv/bin/python coletar_financeiro.py 2026-10

Gera `dados/financeiro_<mes>.json`, que a tarefa diária grava no banco do
Artifact "ASAAS Setembro 2026" (coleção `meses`, doc = mês).

De onde vem cada coisa (conferido em 05/10/2026 contra as telas):
  - ASAAS pela API (chave do Porta-chaves, via get_config). "Recebido no mês"
    usa creditDate (= filtro "Período de recebimento" da tela: 140 cobranças,
    R$ 60.662,54 em set/2026); "venceu no mês" usa dueDate (191, R$ 80.602,93).
    Valor = `value`, que já inclui juros quando pago em atraso.
  - Conta Azul: não tem API que funcione para ela. A tarefa puxa pelo Chrome
    (contaazul_extrair.js) e grava `dados/ca_<mes>.txt`, uma linha por
    lançamento. Lançamentos da conta financeira "ASAAS" são espelho do ASAAS e
    saem; parcelas zeradas por renegociação também.
  - Entrada: no ASAAS, a descrição começa com "ENTRADA". No Conta Azul não há
    padrão ("1/N" costuma ser a 1ª PARCELA), então a entrada é casada com os
    contratos do Painel Comercial (PAINEL COMERCIAL/dados/<mes>): mesmo
    cliente e valor igual à entrada ou a uma parte dela. Partes de contratos
    do mês anterior pagas neste mês também contam (Sidnei, set/2026).

Linha de saída: src|cliente|centavos|tipo|ação|forma|vencimento|situação|pago|conjuntos|parcela|fechamento
  fechamento: AAAA-MM em que o cliente fechou contrato (Painel Comercial), vazio se não achado
  tipo E entrada, H parcela de honorários, X Pix avulso/parceiro
  situação R recebida, V vencida, C cartão confirmado, P a vencer, L perda
  conjuntos: r = recebido no mês, v = venceu no mês
"""

import json
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
COMERCIAL = AQUI.parent / "PAINEL COMERCIAL"
sys.path.insert(0, str(AQUI.parent / "CADASTRO ASTREA"))

from src import asaas                                         # noqa: E402
from src.config.settings import get_config                    # noqa: E402

DADOS = AQUI / "dados"


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z ]+", " ", re.sub(r"\s+", " ", s)).split()


def mesmo_cliente(a, b):
    """Nome do lançamento x nome do contrato: tolera sufixos e corte em 36 letras."""
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    n = min(len(a), len(b), 3)
    return a[:n] == b[:n]


def limites(mes):
    ano, m = map(int, mes.split("-"))
    fim = date(ano + (m == 12), m % 12 + 1, 1).toordinal() - 1
    return "%s-01" % mes, date.fromordinal(fim).isoformat()


def anterior(mes):
    ano, m = map(int, mes.split("-"))
    return "%d-%02d" % (ano - (m == 1), 12 if m == 1 else m - 1)


# ---------------------------------------------------------------- ASAAS
def pagamentos(chave, filtro):
    off, saida = 0, []
    while True:
        r = asaas._chamar("/payments", chave, dict(filtro, limit=100, offset=off))
        saida += [p for p in r["data"] if not p.get("deleted")]
        if not r.get("hasMore"):
            return saida
        off += 100


def nomes_clientes(chave, ids):
    cache_f = DADOS / "clientes_asaas.json"
    cache = json.loads(cache_f.read_text(encoding="utf-8")) if cache_f.exists() else {}
    for i in ids:
        if i not in cache:
            cache[i] = asaas._chamar("/customers/" + i, chave).get("name", "?")
    cache_f.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return cache


def acao(desc):
    d = desc or ""
    return ("BA" if re.search(r"busca e apreens", d, re.I) else
            "SE" if re.search(r"superendiv", d, re.I) else
            "RV" if re.search(r"revisional", d, re.I) else "--")


def linhas_asaas(mes, hoje):
    chave = get_config().asaas_api_key
    ini, fim = limites(mes)
    venc = pagamentos(chave, {"dueDate[ge]": ini, "dueDate[le]": fim})
    rec = pagamentos(chave, {"creditDate[ge]": ini, "creditDate[le]": fim})
    todos = {}
    for k, lista in (("r", rec), ("v", venc)):
        for p in lista:
            todos.setdefault(p["id"], [p, ""])[1] += k
    nomes = nomes_clientes(chave, {p["customer"] for p, _ in todos.values()})
    saida = []
    for p, fl in todos.values():
        st = {"RECEIVED": "R", "RECEIVED_IN_CASH": "R", "CONFIRMED": "C",
              "OVERDUE": "V", "PENDING": "P"}.get(p["status"])
        if st is None:              # estornada, em análise, chargeback: fora da conta
            continue
        if st == "P" and p["dueDate"] < hoje:
            st = "V"
        desc = p.get("description") or ""
        tipo = ("E" if desc.strip().upper().startswith("ENTRADA") else
                "X" if "pix recebido" in desc.lower() else "H")
        forma = {"BOLETO": "B", "PIX": "P", "CREDIT_CARD": "C"}.get(p["billingType"], "B")
        pago = p.get("clientPaymentDate") or p.get("paymentDate") or ""
        saida.append(["AS", nomes.get(p["customer"], "?").strip(), round(p["value"] * 100), tipo,
                      acao(desc), forma, p["dueDate"], st, pago, fl, ""])
    return saida


# ---------------------------------------------------------------- Conta Azul
def contratos(mes):
    pasta = COMERCIAL / "dados" / mes
    if pasta.is_dir():
        return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(pasta.glob("*.json"))]
    # até mai/2026 os contratos vêm da planilha consolidada (PAINEL COMERCIAL/dados/historico)
    hist = COMERCIAL / "dados" / "historico" / ("%s.json" % mes)
    return json.loads(hist.read_text(encoding="utf-8")).get("linhas", []) if hist.exists() else []


def valores_entrada(c):
    """Partes da entrada (quando dividida) ou o valor cheio."""
    vals = [p["valor"] for p in (c.get("entrada_partes") or []) if p.get("valor")]
    return vals or ([c["entrada"]] if c.get("entrada") else [])


def linhas_conta_azul(mes, hoje, avisos):
    arq = DADOS / ("ca_%s.txt" % mes)
    if not arq.exists():
        avisos.append("Conta Azul não coletado para %s (falta %s)." % (mes, arq.name))
        return []
    coletado = datetime.fromtimestamp(arq.stat().st_mtime).date().isoformat()
    if coletado < hoje:     # o Chrome não respondeu hoje: vale a última coleta, com aviso
        avisos.append("Conta Azul da coleta de %s (o de hoje ainda não foi coletado pelo Chrome)."
                      % "/".join(reversed(coletado.split("-"))))
    do_mes, do_anterior = contratos(mes), contratos(anterior(mes))
    restam = {}          # partes de entrada ainda não casadas, por contrato
    saida = []
    for l in arq.read_text(encoding="utf-8").strip().splitlines():
        # nome|centavos|cat|forma|venc|status|pago|fl|conta|parc
        n, c, cat, forma, venc, st, pago, fl, conta, parc = l.split("|")
        c = int(c)
        if conta == "A" or (st == "Z"):       # espelho do ASAAS; parcela zerada por renegociação
            continue
        if cat == "--" and parc == "PX":      # avulso sem categoria: transferência, estorno, rendimento
            continue
        tipo = "X" if cat == "PA" else "H"
        if tipo == "H" and "r" in fl:
            for lista, outro in ((do_mes, False), (do_anterior, True)):
                for k in lista:
                    if outro and len(k.get("entrada_partes") or []) < 2:
                        continue
                    if not mesmo_cliente(n, k["cliente"]):
                        continue
                    vals = restam.setdefault(k["id"], valores_entrada(k))
                    achou = next((v for v in vals if abs(v * 100 - c) < 1), None)
                    if achou is not None:
                        tipo = "E"
                        vals.remove(achou)
                        break
                if tipo == "E":
                    break
        if st == "P" and venc < hoje:
            st = "V"
        saida.append(["CA", n, c, tipo, cat if cat in ("RV", "BA", "CV", "PA") else "--",
                      forma, venc, st, pago, fl, parc])
    return saida


def avista(c):
    """Contrato pago à vista: sem parcelas e entrada = total (decisão dela, 20/10/2026)."""
    return (not c.get("parcelas_qtd")) and c.get("entrada") and \
        abs((c.get("valor_total") or 0) - c["entrada"]) < 0.01


def marcar_avista(linhas, contratos_mes):
    """Pagamento à vista conta como ENTRADA, mesmo sem "ENTRADA" na descrição
    (Dione Ferreira Lucas, out/2026: R$ 4.948,19 pagos no ASAAS em 15/10).
    Vale o que o cliente pagou no mês, de qualquer sistema."""
    for c in filter(avista, contratos_mes):
        for l in linhas:
            if "r" in l[9] and l[3] == "H" and mesmo_cliente(l[1], c["cliente"]):
                l[3] = "E"


# ---------------------------------------------------------------- mês de fechamento
def mapa_fechamento():
    """Cliente -> meses em que fechou contrato, pelo Painel Comercial:
    histórico da consolidada (fev/2023 a mai/2026) + contratos de jun/2026 em diante."""
    mapa = []
    for f in sorted((COMERCIAL / "dados" / "historico").glob("*.json")):
        for c in json.loads(f.read_text(encoding="utf-8")).get("linhas", []):
            mapa.append((c["cliente"], c["mes"]))
    for pasta in sorted((COMERCIAL / "dados").glob("20??-??")):
        for f in pasta.glob("*.json"):
            c = json.loads(f.read_text(encoding="utf-8"))
            if not c.get("outro_mes"):
                mapa.append((c["cliente"], c["mes"]))
    return mapa


PARTICULAS = {"DE", "DA", "DO", "DAS", "DOS", "E"}


def mesma_pessoa(a, b):
    """Mais rígido que mesmo_cliente: sem "de/da/dos", os 3 primeiros nomes iguais
    (ou todos, quando o nome é mais curto)."""
    a = [x for x in norm(a) if x not in PARTICULAS]
    b = [x for x in norm(b) if x not in PARTICULAS]
    n = min(len(a), len(b), 3)
    return n >= 2 and a[:n] == b[:n]


def marcar_fechamento(linhas, mes, mapa=None):
    """Acrescenta a cada linha o mês de fechamento do contrato do cliente
    (pedido dela, 21/10/2026: "no mês de agosto, quanto dos contratos de julho
    representam"). Com mais de um contrato, vale o mais recente até o mês do
    pagamento. Sem contrato achado pelo nome, fica vazio."""
    mapa = mapa if mapa is not None else mapa_fechamento()
    arq = AQUI / "apelidos.json"
    apelidos = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    for l in linhas:
        ref = (l[8] or "")[:7] if l[7] == "R" and l[8] else mes
        quem = apelidos.get(l[1].strip(), l[1])
        meses = sorted({m for nome, m in mapa if mesma_pessoa(quem, nome)})
        antes = [m for m in meses if m <= ref]
        fech = antes[-1] if antes else (meses[0] if meses else "")
        if len(l) > 11:
            l[11] = fech
        else:
            l.append(fech)
    return linhas


# ---------------------------------------------------------------- saída
def coletar(mes):
    DADOS.mkdir(exist_ok=True)
    hoje = date.today().isoformat()
    avisos = []
    linhas = linhas_asaas(mes, hoje) + linhas_conta_azul(mes, hoje, avisos)
    k = contratos(mes)
    marcar_avista(linhas, k)
    marcar_fechamento(linhas, mes)
    resumo = json.loads((COMERCIAL / "dados" / ("mes_%s.json" % mes)).read_text(encoding="utf-8")) \
        if (COMERCIAL / "dados" / ("mes_%s.json" % mes)).exists() else {}
    doc = {
        "mes": mes,
        "atualizado_em": datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "linhas": ["|".join(str(x) for x in l) for l in linhas],
        "painel_entradas": round(sum(x.get("entrada") or 0 for x in k), 2),
        "painel_contratos": len([x for x in k if not x.get("outro_mes")]),
        "painel_previa": bool(resumo.get("previa")),
        "avisos": avisos,
    }
    destino = DADOS / ("financeiro_%s.json" % mes)
    destino.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    tot = lambda f: sum(l[2] for l in linhas if f(l)) / 100
    print("%s: %d linhas | recebido %.2f | venceu %.2f | em aberto %.2f | entradas %.2f (painel %.2f) | %s"
          % (mes, len(linhas), tot(lambda l: "r" in l[9]),
             tot(lambda l: "v" in l[9] and l[7] != "L"), tot(lambda l: "v" in l[9] and l[7] == "V"),
             tot(lambda l: "r" in l[9] and l[3] == "E"), doc["painel_entradas"], destino))
    for a in avisos:
        print("AVISO:", a)


def so_fechamento(arquivos):
    """Marca o mês de fechamento em documentos já coletados, sem recoletar."""
    mapa = mapa_fechamento()
    for arq in arquivos:
        doc = json.loads(Path(arq).read_text(encoding="utf-8"))
        linhas = [l.split("|") for l in doc["linhas"]]
        marcar_fechamento(linhas, doc["mes"], mapa)
        doc["linhas"] = ["|".join(l) for l in linhas]
        Path(arq).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        print(arq, sum(1 for l in linhas if l[11]), "de", len(linhas), "com contrato achado")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--fechamento"]:
        so_fechamento(sys.argv[2:])
        sys.exit()
    for m in sys.argv[1:] or [date.today().strftime("%Y-%m")]:
        coletar(m)
