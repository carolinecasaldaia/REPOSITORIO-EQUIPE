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
ENDERECOS = DADOS / "enderecos_asaas.json"


# ------------------------------------------------ cidade e Estado de cada contrato
# Aba "Estados e municípios" (pedido de 05/11/2026). A cidade só vem do contrato
# assinado de ago/2026 em diante; antes disso, nem a planilha consolidada a tem.
# Para os demais, usa o endereço do cadastro do cliente no ASAAS, ligado pelo
# nome, e só quando o Estado do ASAAS bate com o do contrato (conferido em
# 05/11/2026: concorda com o contrato assinado em 43 de 50 casos).
def _n(s):
    import unicodedata, re
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z ]", " ", s)).strip()


def enderecos_asaas():
    """Nome, cidade e UF dos clientes do ASAAS; guardado em dados/ e renovado 1x por dia."""
    hoje = date.today().isoformat()
    cache = json.loads(ENDERECOS.read_text(encoding="utf-8")) if ENDERECOS.exists() else {}
    if cache.get("atualizado") == hoje:
        return cache["clientes"]
    try:
        sys.path.insert(0, str(AQUI.parent / "CADASTRO ASTREA"))
        from src import asaas
        from src.config.settings import get_config
        chave, off, clientes = get_config().asaas_api_key, 0, []
        while True:
            r = asaas._chamar("/customers", chave, {"limit": 100, "offset": off})
            clientes += [{"nome": c.get("name"), "cidade": c.get("cityName"), "uf": c.get("state")}
                         for c in r["data"] if not c.get("deleted") and c.get("cityName")]
            if not r.get("hasMore"):
                break
            off += 100
        ENDERECOS.write_text(json.dumps({"atualizado": hoje, "clientes": clientes}, ensure_ascii=False),
                             encoding="utf-8")
        return clientes
    except Exception:
        print("endereços do ASAAS não renovados; usando a última cópia\n%s" % traceback.format_exc())
        return cache.get("clientes", [])


def completar_local(contratos):
    clientes = enderecos_asaas()
    apel_f = AQUI.parent / "PAINEL FINANCEIRO" / "apelidos.json"
    apel = json.loads(apel_f.read_text(encoding="utf-8")) if apel_f.exists() else {}
    comercial_p_asaas = {_n(v): _n(k) for k, v in apel.items() if not k.startswith("_")}
    por_nome = {}
    for c in clientes:
        por_nome.setdefault(_n(c["nome"]), []).append(c)

    def achar(nome, uf):
        n = _n(nome)
        n = comercial_p_asaas.get(n, n)
        cand = por_nome.get(n)
        if not cand and len(n.split()) >= 3:
            ks = [k for k in por_nome if k.split()[:3] == n.split()[:3]]
            cand = por_nome[ks[0]] if len(ks) == 1 else None
        if not cand:
            return None
        locais = {(c["uf"], c["cidade"]) for c in cand if not uf or c["uf"] == uf}
        return locais.pop() if len(locais) == 1 else None

    for k in contratos:
        k["cidade_fonte"] = "contrato" if k.get("cidade") else None
        k["uf_fonte"] = "contrato" if k.get("uf") else None
        if k.get("cidade") and k.get("uf"):
            continue
        achado = achar(k.get("cliente"), k.get("uf"))
        if not achado:
            continue
        if not k.get("uf"):
            k["uf"], k["uf_fonte"] = achado[0], "asaas"
        if not k.get("cidade"):
            k["cidade"], k["cidade_fonte"] = achado[1], "asaas"

    # Mesma cidade escrita de jeitos diferentes ("Gravatai"/"Gravataí", "Arco Verde"/
    # "Arcoverde", "Distrito Federal"/"Brasília"): fica a grafia com acento mais usada.
    apelido = {"DISTRITOFEDERAL": "BRASILIA"}
    chave = lambda k: (k.get("uf"), apelido.get(_n(k["cidade"]).replace(" ", ""), _n(k["cidade"]).replace(" ", "")))
    grafias = {}
    import re
    for k in contratos:
        if k.get("cidade"):
            # "Manaus (ação) / Brasília-DF (domicílio)": vale o domicílio do cliente
            dom = re.search(r"([^/()]+?)\s*(?:-\s*[A-Z]{2})?\s*\(domic", k["cidade"])
            k["cidade"] = (dom.group(1) if dom else k["cidade"]).strip()
            grafias.setdefault(chave(k), []).append(k["cidade"])
    melhor = {ch: max(set(gs), key=lambda g: (_n(g) != g.upper() and g != _n(g).title(), gs.count(g), len(g)))
              for ch, gs in grafias.items()}
    for k in contratos:
        if k.get("cidade"):
            k["cidade"] = melhor[chave(k)]


# --------------------------------------------- Pix do parceiro (Israel Correia)
# Contratos fechados pelo parceiro não entram no Painel Comercial, mas o valor cai
# direto nas contas do escritório por Pix ("ISRAEL C S S", pedido de 05/11/2026).
# Ele deposita no Santander PJ, no Sicredi PJ ou no Sicredi PF. O que está lançado
# na Conta Azul já vem na coleta; o resto vem dos extratos OFX que a equipe salva
# em PAINEL FINANCEIRO/EXTRATOS. "ISRAEL VITOR" é cliente, não o parceiro.
import re as _re
PARCEIRO = _re.compile(r"\bISRAEL\s+C(?:ORREIA)?\b(?!\w)|\bISRAEL\s+C\s+S\s+S\b", _re.I)
EXTRATOS = AQUI.parent / "PAINEL FINANCEIRO" / "EXTRATOS"
BANCOS = {"033": "Santander", "0033": "Santander", "748": "Sicredi", "0748": "Sicredi"}


MESES_PT = {m: i + 1 for i, m in enumerate(
    "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro".split())}
SICREDI_PF = "152899"        # conta PF do Sicredi (15289-9); a outra conta Sicredi é a PJ


def _cent(s):
    return round(float(s.replace(".", "").replace(",", ".")) * 100)


def _creditos_ofx(arq):
    txt = arq.read_bytes().decode("latin-1")
    banco = (_re.search(r"<BANKID>\s*(\d+)", txt) or [None, ""])[1]
    acct = (_re.search(r"<ACCTID>\s*(\d+)", txt) or [None, ""])[1]
    conta = BANCOS.get(banco, "Banco %s" % banco if banco else "Extrato")
    if conta == "Sicredi":
        conta += " PF" if acct.endswith(SICREDI_PF) else " PJ"
    out = []
    for t in _re.findall(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|</BANKTRANLIST>)", txt, _re.S | _re.I):
        campo = lambda n: (_re.search(r"<%s>\s*([^<\r\n]*)" % n, t, _re.I) or [None, ""])[1].strip()
        valor = float(campo("TRNAMT").replace(",", ".") or 0)
        if valor <= 0 or not PARCEIRO.search(campo("NAME") + " " + campo("MEMO")):
            continue
        d = campo("DTPOSTED")[:8]
        out.append(("%s-%s-%s" % (d[:4], d[4:6], d[6:8]), round(valor * 100), conta))
    return out


def _creditos_pdf(arq):
    """Extratos em PDF do Santander (consolidado PF/PJ), Sicredi e Mercado Pago."""
    from pypdf import PdfReader
    L = [l for p in PdfReader(str(arq)).pages for l in (p.extract_text() or "").splitlines()]
    topo = " ".join(L[:40])
    prox = lambda i: L[i + 1] if i + 1 < len(L) else ""
    out = []
    if "EXTRATO CONSOLIDADO INTELIGENTE" in topo:              # Santander
        m = _re.search(r"\b(%s)/(\d{4})" % "|".join(MESES_PT), topo)
        ano, mes = int(m[2]), MESES_PT[m[1]]
        conta = "Santander " + ("PJ" if "Extrato_PJ" in topo else "PF")
        dia = None               # o Santander só escreve a data no 1º lançamento do dia
        for i, l in enumerate(L):
            d = _re.match(r"\s*(\d{2})/(\d{2})\b", l)
            if d and int(d[2]) == mes:
                dia = int(d[1])
            if dia is None or not PARCEIRO.search(l) or "PIX RECEBIDO" not in (L[i - 1] + l).upper():
                continue
            v = _re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2})(-?)", prox(i))
            if v and v[2] != "-":                                # "500,00-" é débito
                out.append(("%04d-%02d-%02d" % (ano, mes, dia), _cent(v[1]), conta))
    elif "Cooperativa:" in topo and "Extrato de conta corrente" in topo:   # Sicredi
        conta = "Sicredi " + ("PJ" if _re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", topo) else "PF")
        data = None
        for i, l in enumerate(L):
            d = _re.fullmatch(r"\s*(\d{2})/(\d{2})/(\d{4})\s*", l)
            if d:
                data = "%s-%s-%s" % (d[3], d[2], d[1])
            if data and PARCEIRO.search(l) and "RECEBIMENTO" in l.upper():
                v = _re.search(r"([+-])\s*R\$\s*([\d\.]+,\d{2})", prox(i))
                if v and v[1] == "+":
                    out.append((data, _cent(v[2]), conta))
    elif "DETALHE DOS MOVIMENTOS" in " ".join(L[:80]):          # Mercado Pago
        for i, l in enumerate(L):
            if not (PARCEIRO.search(l) and "recebido" in l.lower()):
                continue
            d = _re.search(r"(\d{2})-(\d{2})-(\d{4})", L[i - 1] + " " + l)
            v = _re.search(r"R\$\s*(-?)\s*([\d\.]+,\d{2})", l + " " + prox(i))
            if d and v and not v[1]:
                out.append(("%s-%s-%s" % (d[3], d[2], d[1]), _cent(v[2]), "Mercado Pago"))
    return out


def pix_parceiro_extratos():
    """(data AAAA-MM-DD, centavos, conta) de cada crédito do parceiro nos extratos
    (.ofx ou .pdf) da pasta EXTRATOS. Débitos (Pix enviado a ele) ficam de fora.
    Extratos da mesma conta com períodos sobrepostos não duplicam: de cada
    (conta, data, valor) vale a maior quantidade vista num único arquivo."""
    from collections import Counter
    # Ler 46 PDFs leva ~20 s; cada arquivo só é relido se mudar (nome/tamanho/data).
    cache_arq = DADOS / "extratos_parceiro_cache.json"
    try:
        cache = json.loads(cache_arq.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    novo, maximo = {}, Counter()
    for arq in sorted(EXTRATOS.glob("**/*")) if EXTRATOS.is_dir() else []:
        tipo = arq.suffix.lower()
        if tipo not in (".ofx", ".pdf"):
            continue
        try:
            st = arq.stat()
            assinatura = "%s|%d|%d" % (arq.relative_to(EXTRATOS), st.st_size, int(st.st_mtime))
            if assinatura in cache:
                lista = [tuple(x) for x in cache[assinatura]]
            else:
                lista = _creditos_ofx(arq) if tipo == ".ofx" else _creditos_pdf(arq)
            novo[assinatura] = lista
            for k, n in Counter(lista).items():
                maximo[k] = max(maximo[k], n)
        except Exception:
            print("%s: extrato não lido\n%s" % (arq.name, traceback.format_exc()))
    if novo != cache:
        try:
            cache_arq.write_text(json.dumps(novo, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    return sorted(k for k, n in maximo.items() for _ in range(n))


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
    extrato = pix_parceiro_extratos()
    for f in sorted(FINANCEIRO.glob("financeiro_*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            mes = d["mes"]
            # entradas, parceiros e outros (Pix avulso) entram só no "Total recebido
            # no mês" (pedido de 05/11/2026); fonte = recebido por sistema.
            grupos = {g: {"v": 0, "n": 0, "origem": {}, "itens": []}
                      for g in ("do_mes", "atrasadas", "adiantadas", "entradas", "parceiros", "outros")}
            fonte = {"AS": 0, "CA": 0, "EXT": 0}
            vistos = set()          # (data, centavos) dos Pix do parceiro já contados
            for linha in d.get("linhas", []):
                c = linha.split("|")
                if len(c) < 10 or "r" not in c[9]:
                    continue
                fonte[c[0]] = fonte.get(c[0], 0) + int(c[2])
                if c[3] != "H":
                    parceiro = c[3] == "X" and PARCEIRO.search(c[1])
                    g = grupos["entradas" if c[3] == "E" else "parceiros" if parceiro else "outros"]
                    g["v"] += int(c[2])
                    g["n"] += 1
                    if parceiro:
                        vistos.add((c[8] or c[6], int(c[2]), len(vistos)))
                        g["itens"].append([c[8] or c[6], round(int(c[2]) / 100, 2), "Conta Azul"])
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
            # Pix do parceiro que só está no extrato do banco (conta fora da Conta
            # Azul, como a PF do Sicredi, ou ainda não conciliado lá).
            for data, cent, conta in extrato:
                if data[:7] != mes:
                    continue
                # já lançado na Conta Azul: mesmo valor, até 3 dias de diferença na data
                dup = next((v for v in vistos if v[1] == cent and abs(
                    (date.fromisoformat(v[0][:10]) - date.fromisoformat(data)).days) <= 3), None)
                if dup:
                    vistos.discard(dup)
                    continue
                g = grupos["parceiros"]
                g["v"] += cent
                g["n"] += 1
                g["itens"].append([data, round(cent / 100, 2), conta])
                fonte["EXT"] += cent
            for g in grupos.values():
                g["v"] = round(g["v"] / 100, 2)
                g["origem"] = {k: round(v / 100, 2) for k, v in sorted(g["origem"].items())}
                g["itens"].sort(key=lambda x: (x[0], str(x[2])) if len(x) == 3 else (x[2], x[0]))
            grupos["fonte"] = {k: round(v / 100, 2) for k, v in fonte.items()}
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
    try:
        completar_local(contratos)
    except Exception:
        print("cidade/UF pelo ASAAS falhou; segue só com o que veio dos contratos\n%s" % traceback.format_exc())
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
