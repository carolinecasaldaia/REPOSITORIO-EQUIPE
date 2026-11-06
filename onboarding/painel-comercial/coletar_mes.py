#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Painel comercial: lê a pasta de um mês em PREPARAÇÃO PARA INGRESSO e gera
um JSON por contrato fechado, pronto para o banco do painel (Artifact).

    ~/.cadastro-astrea/venv/bin/python coletar_mes.py 2026-09

Quem entra (decisão dela, 30/09/2026):
  - mês com a planilha "DADOS CONTRATOS - <MÊS>.csv" na pasta (junho e julho
    de 2026, feitos e conferidos antes): a planilha manda, nada é recalculado;
  - mês com pastas "NN - OK -": só elas;
  - mês sem nenhuma marca OK (antes de agosto/2026): toda pasta com
    "Contrato HO Assinado.pdf", marcada como prévia (não conferida);
  - mais os ajustes manuais de `ajustes.json` (incluir/excluir pasta, trocar
    a entrada de um cliente, linhas extras como parte de entrada de contrato
    de outro mês).

Números vêm do contrato (Cláusula 2ª, relida sempre) e a entrada paga, do
Asaas. Nunca estima: o que não bate no padrão fica null. CPF não sai daqui.
"""

import json
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
# Raiz "Documentos Escritório " (acento pode vir decomposto): os caminhos valem onde
# quer que esta pasta esteja (PAINEL COMERCIAL foi para EMPRESA/FINANCEIRO em 06/11/2026).
DOC = next(p for p in Path(__file__).resolve().parents if p.name.startswith("Documentos Escrit"))
ONBOARDING = DOC / "A - REVISIONAL" / "A - COMERCIAL" / "ONBOARDING"
CADASTRO = ONBOARDING / "CADASTRO ASTREA"
sys.path.insert(0, str(CADASTRO))

from pypdf import PdfReader                                   # noqa: E402
from src import asaas                                         # noqa: E402
from src.astrea import casos as C                             # noqa: E402
from src.config.settings import get_config                    # noqa: E402
from src.extractors import contrato_ho                        # noqa: E402

PREPARACAO = ONBOARDING.parent / "PREPARAÇÃO PARA INGRESSO"
MESES = ("JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO", "JULHO",
         "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO")
MARCA_OK = re.compile(r"^\d+\s*-\s*OK\s*-\s*")   # "01 - OK -", "1 - OK -", "12 - OK -"


def slug(texto):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-").lower()[:80]


def texto_pdf(pdf):
    t = re.sub(r"\s+", " ", " ".join(p.extract_text() or "" for p in PdfReader(pdf).pages))
    return re.sub(r"Assinado com Assinatura Eletr.*?Validador", "", t, flags=re.S)


def _valor(s):
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def partes_e_forma(texto):
    """Partes da entrada (quando dividida) e forma de pagamento das parcelas."""
    i = texto.find("Entrada no valor")
    fim = texto.find("O contratante fica ciente", i)
    trecho = texto[i:fim if fim > 0 else i + 900] if i >= 0 else ""
    corte = re.search(r"\d+\s*\([^)]*\)\s*parcelas|R\$\s*R\$", trecho[20:])
    bloco = trecho[:20 + corte.start()] if corte else trecho
    partes = [{"valor": _valor(v), "data": d.replace("/", ".")}
              for v, d in re.findall(r"R\$\s*([\d.,]+)\s*(?:\([^)]*\))?\s*na\s+data\s+de\s*"
                                     r"(\d{1,2}[./]\d{1,2}[./]\d{2,4})", bloco)]
    if len(partes) < 2:
        partes = []
    cartao = bool(re.search(r"CART[ÃA]O\s+DE\s+CR[ÉE]DITO", trecho, re.I))
    return partes, ("Cartão" if cartao else "Boleto")


def entradas_asaas(cpf, config):
    """Cobranças de ENTRADA pagas no Asaas: [{valor, data, forma}]."""
    if not (cpf and config.asaas_api_key):
        return []
    cid = asaas.buscar_cliente_por_cpf(cpf, config.asaas_api_key)
    if not cid:
        return []
    alvo = (config.asaas_texto_entrada or "ENTRADA").strip().upper()
    pagas, offset = [], 0
    while True:
        r = asaas._chamar("/payments", config.asaas_api_key,
                          {"customer": cid, "limit": 100, "offset": offset})
        for c in r.get("data") or []:
            if (c.get("description") or "").strip().upper().startswith(alvo) \
                    and c.get("status") in asaas.STATUS_PAGO:
                pagas.append({"valor": c.get("value"),
                              "data": c.get("paymentDate") or c.get("clientPaymentDate"),
                              "forma": c.get("billingType")})
        if not r.get("hasMore"):
            return sorted(pagas, key=lambda p: p["data"] or "")
        offset += 100


def _num(s):
    s = (s or "").strip()
    if not s:
        return None
    if "," in s:
        return _valor(s.replace("R$", "").strip())
    try:
        return float(s)
    except ValueError:
        return None


def _data_br(s):
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", s or "")
    return "%s.%s.%s" % m.groups() if m else None


def ler_planilha(caminho, mes):
    """Planilha "DADOS CONTRATOS" de um mês já conferido: [linhas], caixa."""
    import csv
    texto = caminho.read_text(encoding="utf-8-sig")
    blocos = texto.split("\nTOTAIS")
    linhas = []
    for c in csv.DictReader(blocos[0].strip().splitlines(), delimiter=";"):
        if not (c.get("Cliente") or "").strip():
            continue
        venc = c.get("Vencimento da entrada") or ""
        partes = [{"valor": _num(v), "data": _data_br(d)}
                  for d, v in re.findall(r"(\d{2}/\d{2}/\d{4})\s*\(([\d.,]+)\)", venc)]
        if c.get("Parcelas"):                            # "35x R$ 507,54" ou "1x R$ 563,35 + 14x R$ 413,35"
            grupos = [(int(q), _valor(v)) for q, v in re.findall(r"(\d+)x\s*R\$\s*([\d.,]+)", c["Parcelas"])]
            qtd = sum(q for q, _ in grupos) or None
            valor_p = grupos[-1][1] if grupos else None
        else:
            qtd = int(_num(c.get("Qtd parcelas")) or 0) or None
            valor_p = _num(c.get("Valor da parcela (R$)"))
        servico = (c.get("Serviço") or "").lower()
        banco_proc = c.get("Banco / Processo") or ""
        linhas.append({
            "mes": mes, "cliente": c["Cliente"].strip().upper(), "pasta": "",
            "tipo_acao": "BUSCA E APREENSÃO" if "busca" in servico else
                         ("REVISIONAL VEICULAR" if "revisional" in servico else c.get("Serviço")),
            "banco_adverso": None if banco_proc.lower().startswith("proc") else banco_proc,
            "uf": (c.get("UF") or "").strip() or None, "cidade": (c.get("Cidade") or "").strip() or None,
            "valor_total": _num(c.get("Total honorários (R$)")),
            "entrada": _num(c.get("Entrada (R$)")), "entrada_data": _data_br(venc),
            "entrada_partes": partes if len(partes) > 1 else [],
            "entrada_paga_asaas": None, "entrada_pagamentos": [],
            "parcelas_qtd": qtd, "parcelas_valor": valor_p,
            "parcelas_inicio": _data_br(c.get("1ª parcela")), "parcelas_fim": _data_br(c.get("Última parcela")),
            "forma_parcelas": "Cartão" if "cart" in (c.get("Pagamento das parcelas") or "").lower() else "Boleto",
            "astrea": None, "marcado_ok": True, "previa": False, "outro_mes": False,
            "ajuste": "", "obs": "",
        })
    caixa = None
    if len(blocos) > 1:
        achado = re.search(r"Faturamento[^;]*;\s*([\d.,]+)", blocos[1])
        caixa = _num(achado.group(1)) if achado else None
    return linhas, caixa


def pagamentos_asaas(cpf, config):
    """Toda cobrança PAGA do cliente no Asaas, qualquer descrição: [{valor, data, forma, descricao}]."""
    if not (cpf and config.asaas_api_key):
        return []
    cid = asaas.buscar_cliente_por_cpf(cpf, config.asaas_api_key)
    if not cid:
        return []
    pagas, offset = [], 0
    while True:
        r = asaas._chamar("/payments", config.asaas_api_key,
                          {"customer": cid, "limit": 100, "offset": offset})
        for c in r.get("data") or []:
            if c.get("status") in asaas.STATUS_PAGO:
                pagas.append({"valor": c.get("value"),
                              "data": c.get("paymentDate") or c.get("clientPaymentDate"),
                              "forma": c.get("billingType"),
                              "descricao": (c.get("description") or "")[:80]})
        if not r.get("hasMore"):
            return sorted(pagas, key=lambda p: p["data"] or "")
        offset += 100


def status_astrea(banco, nome):
    if banco is None:
        return "Sem registro"
    r = banco.execute("select status_caso from processamentos where nome_cliente = ? "
                      "or nome_pasta = ? order by atualizado_em desc", (nome, nome)).fetchone()
    s = (r[0] if r else "") or ""
    if s.startswith("CASO ABERTO"):
        return "Aberto"
    return "Fora do escopo" if "fora do escopo" in s else "Sem registro"


def contratos_da_pasta(pasta):
    """
    Todos os contratos de honorários assinados da pasta, sem repetir o mesmo
    contrato em arquivos diferentes (o envelope do Autentique e o "(2)" às
    vezes são cópia). Uma pasta pode ter dois contratos de verdade: Luiz
    Carlos Pedro, agosto/2026, revisional + defesa em execução.
    """
    vistos, saida = set(), []
    # O arquivo sem sufixo é sempre o 1º contrato; "(2)" e afins vêm depois.
    for pdf in sorted(pasta.rglob("Contrato HO Assinado*.pdf"),
                      key=lambda f: (f.name != "Contrato HO Assinado.pdf", f.name)):
        r = contrato_ho.extrair(pdf)
        v = lambda c: c.valor if c.valido else None
        chave = (v(r.valor_total_honorarios), v(r.entrada_valor), v(r.parcelas_qtd), v(r.parcelas_valor))
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append((pdf, r))
    return saida


def linha(pasta, mes, config, banco, previa, pdf=None, r=None):
    if r is None:
        pdf = next(pasta.rglob("Contrato HO Assinado.pdf"))
        r = contrato_ho.extrair(pdf)
    p = r.contratante
    v = lambda campo: campo.valor if campo is not None and campo.valido else None
    nome = (v(p.nome) if p else None) or MARCA_OK.sub("", pasta.name)
    cpf = ((v(p.cpf) or v(p.cnpj)) if p else None) or ""
    partes, forma = partes_e_forma(texto_pdf(pdf))
    pagas, obs = [], ""
    try:
        pagas = entradas_asaas(cpf, config)
    except Exception as erro:                       # Asaas fora não derruba o mês
        obs = "Asaas não respondeu: %s" % str(erro)[:80]
    entrada, qtd, valor_p = v(r.entrada_valor), v(r.parcelas_qtd), v(r.parcelas_valor)
    total = v(r.valor_total_honorarios)
    avista = ""
    if total is not None and entrada is None and qtd in (None, 1) and valor_p == total:
        entrada, qtd, valor_p, avista = total, 0, 0.0, "Pagamento à vista (parcela única = total)."
    elif total is not None and entrada == total and qtd is None:
        qtd, valor_p, avista = 0, 0.0, "Só entrada, sem parcelamento."
    if avista and not pagas and not obs:
        # À vista: a cobrança no Asaas costuma ter outra descrição (Dione,
        # outubro/2026: "AÇÃO DE BUSCA E APREENSÃO"). Sem parcelas, toda
        # cobrança paga é o pagamento do contrato.
        try:
            pagas = pagamentos_asaas(cpf, config)
        except Exception as erro:
            obs = "Asaas não respondeu: %s" % str(erro)[:80]
    return {
        "mes": mes, "cliente": nome, "pasta": pasta.name,
        "tipo_acao": C.tipo_do_contrato(v(r.tipo_acao)) or v(r.tipo_acao),
        "banco_adverso": v(r.banco_adverso),
        "uf": v(p.uf) if p else None, "cidade": v(p.cidade) if p else None,
        "valor_total": v(r.valor_total_honorarios),
        "entrada": entrada, "entrada_data": v(r.entrada_data),
        "entrada_partes": partes,
        "entrada_paga_asaas": round(sum(x["valor"] or 0 for x in pagas), 2) if pagas else None,
        "entrada_pagamentos": pagas,
        "parcelas_qtd": qtd, "parcelas_valor": valor_p,
        "parcelas_inicio": v(r.parcelas_inicio), "parcelas_fim": v(r.parcelas_fim),
        "forma_parcelas": forma,
        "astrea": status_astrea(banco, nome),
        "marcado_ok": bool(MARCA_OK.match(pasta.name)),
        "previa": previa, "outro_mes": False, "ajuste": "", "obs": (avista + " " + obs).strip(),
        "_cpf": cpf,
    }


def coletar(mes):
    ano, m = mes.split("-")
    pasta_mes = PREPARACAO / ("%s %s" % (MESES[int(m) - 1], ano))
    if not pasta_mes.is_dir():
        raise SystemExit("Pasta do mês não existe: %s" % pasta_mes)
    ajustes = json.loads((AQUI / "ajustes.json").read_text(encoding="utf-8")).get(mes, {}) \
        if (AQUI / "ajustes.json").exists() else {}
    config = get_config()
    try:
        banco = sqlite3.connect(config.banco)
    except Exception:
        banco = None

    pastas = [p for p in sorted(pasta_mes.iterdir())
              if p.is_dir() and next(p.rglob("Contrato HO Assinado.pdf"), None)]
    tem_ok = any(MARCA_OK.match(p.name) for p in pastas)
    # Agosto/2026 (decisão dela, 01/10/2026): vale toda pasta com contrato
    # assinado, com OK ou sem. De setembro em diante, só as com OK.
    todas = bool(ajustes.get("todas_as_pastas"))
    incluir = set(ajustes.get("incluir_pastas", []))
    excluir = set(ajustes.get("excluir_clientes", []))
    # De outubro/2026 em diante nunca vale a "prévia" (todo contrato da pasta):
    # mês sem nenhum OK ainda (começo de mês) entra só com quem já pagou.
    so_ok = tem_ok or mes >= "2026-10"
    escolhidas = [p for p in pastas if todas or (MARCA_OK.match(p.name) if so_ok else True)
                  or p.name in incluir]
    # De outubro/2026 em diante (decisão dela, 19/10/2026): entra também quem
    # já pagou no Asaas, mesmo com a pasta ainda sem OK (documentação
    # incompleta). Um mês pode desligar com "incluir_pagos": false em ajustes.json.
    pagos_sem_ok = set()
    if ajustes.get("incluir_pagos", mes >= "2026-10"):
        config_ = get_config()
        for p in pastas:
            if p in escolhidas:
                continue
            for _, r in contratos_da_pasta(p):
                c = r.contratante
                cpf = ((c.cpf.valor if c.cpf.valido else None) or (c.cnpj.valor if c.cnpj.valido else None)) if c else None
                try:
                    if pagamentos_asaas(cpf, config_):
                        escolhidas.append(p)
                        pagos_sem_ok.add(p.name)
                        break
                except Exception:
                    pass
    for caminho in ajustes.get("incluir_de_outros_meses", []):
        if (PREPARACAO / caminho).is_dir():
            escolhidas.append(PREPARACAO / caminho)
            incluir.add(Path(caminho).name)

    planilha = pasta_mes / ("DADOS CONTRATOS - %s %s.csv" % (MESES[int(m) - 1], ano))
    linhas, caixa, fonte = [], None, "contratos"
    if planilha.exists():
        linhas, caixa = ler_planilha(planilha, mes)
        escolhidas, fonte = [], "planilha do mês"
    for p in escolhidas:
        for n, (pdf, r) in enumerate(contratos_da_pasta(p)):
            novas = _montar(p, n, pdf, r, mes, config, banco, tem_ok, todas, ajustes, incluir, excluir)
            for l in novas:
                if p.name in pagos_sem_ok:
                    l["ajuste"] = l["ajuste"] or "pago no Asaas; pasta ainda sem OK (documentação incompleta)"
                    if l["entrada_paga_asaas"] is None:
                        # Pagamento à vista ou com descrição diferente de "ENTRADA".
                        todas_pagas = pagamentos_asaas(l.get("_cpf"), config)
                        if todas_pagas:
                            l["entrada_pagamentos"] = todas_pagas
                            l["entrada_paga_asaas"] = round(sum(x["valor"] or 0 for x in todas_pagas), 2)
            for l in novas:
                l.pop("_cpf", None)
            linhas.extend(novas)
    for extra in ajustes.get("extras", []):
        linhas.append(dict({"mes": mes, "previa": False, "marcado_ok": True,
                            "entrada_partes": [], "entrada_pagamentos": [], "obs": ""}, **extra))
    return _gravar(linhas, mes, m, ano, tem_ok, todas, fonte, caixa, ajustes)


def _montar(p, n, pdf, r, mes, config, banco, tem_ok, todas, ajustes, incluir, excluir):
    """Uma linha do painel para um contrato, com os ajustes manuais aplicados."""
    l = linha(p, mes, config, banco, previa=not (tem_ok or todas or mes >= "2026-10"), pdf=pdf, r=r)
    l["id"] = "%s__%s%s" % (mes, slug(l["cliente"]), "" if n == 0 else "-%d" % (n + 1))
    if l["cliente"] in excluir or MARCA_OK.sub("", p.name) in excluir:
        return []
    por_id = ajustes.get("por_id", {}).get(l["id"])
    if por_id:
        l.update({k: por_id[k] for k in por_id if k != "obs"})
        l["ajuste"] = por_id.get("obs", "ajuste manual")
    troca = ajustes.get("entrada", {}).get(l["cliente"])
    if troca:
        l.update({k: troca[k] for k in troca if k != "obs"})
        l["ajuste"] = troca.get("obs", "ajuste manual")
    if p.name in incluir:
        l["ajuste"] = l["ajuste"] or "incluído manualmente (pasta sem OK)"
    elif todas and not MARCA_OK.match(p.name):
        l["ajuste"] = l["ajuste"] or "pasta sem OK (em agosto valem todas)"
    return [l]


def _gravar(linhas, mes, m, ano, tem_ok, todas, fonte, caixa, ajustes):
    saida = AQUI / "dados" / mes
    saida.mkdir(parents=True, exist_ok=True)
    for f in saida.glob("*.json"):
        f.unlink()
    usados = set()
    for l in linhas:
        base = l.get("id") or "%s__%s" % (mes, slug(l["cliente"]))
        l["id"], n = base, 2
        while l["id"] in usados:          # mesmo cliente em duas pastas (Sofia, agosto/2026)
            l["id"], n = "%s-%d" % (base, n), n + 1
        usados.add(l["id"])
        (saida / (l["id"] + ".json")).write_text(json.dumps(l, ensure_ascii=False, indent=1),
                                                 encoding="utf-8")
    resumo = {"mes": mes, "rotulo": "%s/%s" % (MESES[int(m) - 1].capitalize(), ano),
              "previa": (not (tem_ok or todas or mes >= "2026-10")) and fonte == "contratos", "fonte": fonte, "caixa": caixa,
              "contratos": len([l for l in linhas if not l.get("outro_mes")]),
              "conciliado": ajustes.get("conciliado", ""),
              "gerado_em": datetime.now().strftime("%Y-%m-%dT%H:%M")}
    (AQUI / "dados" / ("mes_%s.json" % mes)).write_text(json.dumps(resumo, ensure_ascii=False, indent=1),
                                                       encoding="utf-8")
    print("%s: %d linhas em %s" % (mes, len(linhas), saida))
    return linhas


if __name__ == "__main__":
    if len(sys.argv) < 2:
        hoje = datetime.now()
        ano, m = (hoje.year, hoje.month - 1) if hoje.month > 1 else (hoje.year - 1, 12)
        alvo = "%d-%02d" % (ano, m)
    else:
        alvo = sys.argv[1]
    coletar(alvo)
