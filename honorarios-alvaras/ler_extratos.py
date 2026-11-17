#!/usr/bin/env python3
"""Lê extratos bancários (OFX, CSV, XLSX ou PDF) e separa os CRÉDITOS de terceiros.

Contas do escritório: Santander, C6, Mercado Pago e Sicredi — PJ e PF.
O banco sai do próprio arquivo (OFX: BANKID; PDF/CSV: cabeçalho) ou do nome do
arquivo/pasta; PJ/PF sai do nome do titular (SOCIEDADE/CNPJ = PJ) ou do nome do
arquivo/pasta ("PJ", "PF"). Nada é enviado para fora do computador.

Categorias do crédito:
  Judicial        depósito judicial, alvará, TJ, Banco do Brasil/Caixa (contas judiciais)
  Banco réu       PIX/TED vindo de banco/financeira (pagamento voluntário de sucumbência)
  Plataforma      ASAAS, Conta Azul etc. (parcelas de honorários contratuais)
  Pessoa          PIX/TED de pessoa física (pode ser cliente pagando contratual)
  Parceiro        PIX do parceiro Israel Correia ("ISRAEL C S S") — receita, mas não de processo
  Pessoal         informado como pessoal (ex.: Rota 82) — fora das receitas
  Extrajudicial   cliente extrajudicial (honorário sem processo)
  Processo        recebimento de processo informado pela Caroline
  Interna         transferência entre as contas da própria Caroline / escritório
  Rendimento      rendimento, resgate, aplicação, estorno
"""
import csv
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "painel-financeiro"))
import gerar_relatorios as gr  # noqa: E402

BANCOS = {"033": "Santander", "336": "C6", "323": "Mercado Pago", "748": "Sicredi"}
NOMES_BANCO = [("SANTANDER", "Santander"), ("C6", "C6"), ("MERCADO ?PAGO", "Mercado Pago"),
               ("SICREDI", "Sicredi")]

# senhas de PDF exportado (C6 usa os 6 primeiros dígitos do CNPJ/CPF do titular)
SENHAS_PDF = ["581736", "086084"]
# contas cujo OFX não traz o titular (conferido pelos gastos/cabeçalhos em 06/11/2026)
CONTAS_CONHECIDAS = {("Sicredi", "152899"): "PF",      # a outra conta Sicredi é a PJ
                     ("C6", "39383032"): "PF",
                     ("C6", "353975893"): "PJ",
                     ("Santander", "010624437"): "PF"}
R_CNJ = re.compile(r"\d{7}-?\d{2}\.?\d{4}\.?[1-9]\.?\d{2}\.?\d{4}")
R_PARCEIRO = re.compile(r"ISRAEL C S S|ISRAEL CORREIA")
R_INTERNA = re.compile(r"CAROLINE (NEIVA|MACEDO|I ADVOC)|CHRISTOFANO|CM ADVOGAD|MACEDO SOCIEDADE|"
                       r"TRANSF\w* ENTRE CONTAS|MESMA TITULARIDADE|APLICACAO|RESGATE")
R_RENDIMENTO = re.compile(r"RENDIMENTO|RESGATE|CDB|RDB|APLICACAO|ESTORNO|DEVOLUC|CASHBACK|JUROS S/? ?SALDO|"
                          r"REMUNERACAO|POUPANCA")
R_JUDICIAL = re.compile(r"JUDICI|TJAL|TRIBUNAL|ALVARA|LEVANTAMENTO|SISCONDJ|DEP\.? ?JUD|"
                        r"BANCO DO BRASIL|\bBCO DO BRASIL|\bBB\b|CAIXA ECON|\bCEF\b|PODER JUDICI|"
                        r"DEPOSITOS JUDICIAIS|JUSTICA")
R_PLATAFORMA = re.compile(r"ASAAS|PJBANK|CONTA AZUL|PAGUEVELOZ|IUGU|PAGSEGURO|STONE|CIELO|GETNET|EFI |GERENCIANET|"
                          r"VINDI|MERCADO ?PAGO|PICPAY")
R_BANCO_REU = re.compile(r"AYMORE|ITAU|BRADESCO|SANTANDER|SAFRA|OMNI|PAN\b|BV\b|VOTORANTIM|VOLKSWAGEN|"
                         r"TOYOTA|HONDA|YAMAHA|\bRCI\b|\bGM\b|CHEVROLET|FIAT|STELLANTIS|BMW|MERCEDES|"
                         r"CREFISA|HAPPY|DAYCOVAL|SICOOB|BANRISUL|INTER\b|FINANC|CREDITO|LEASING|"
                         r"\bS\.A\b|\bS/A\b|\bS\.A\.|\bS A$|ARRENDAMENTO|SECURITIZ|CONSORCIO|ADMINISTRADORA")


def _num_br(s):
    s = str(s).strip().replace("R$", "").replace(" ", "")
    neg = s.startswith("-") or s.endswith("-") or s.startswith("(")
    s = s.strip("-()+")
    if re.search(r",\d{1,2}$", s):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    v = float(s)
    return -v if neg else v


def _data(s):
    s = str(s).strip()
    for f in ("%Y%m%d", "%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%Y"):
        try:
            return datetime.datetime.strptime(s[:len(datetime.date.today().strftime(f))], f).date()
        except ValueError:
            continue
    return None


def banco_e_tipo(caminho, texto_cab=""):
    ref = gr.norm_texto(" ".join(caminho.parts[-3:]) + " " + texto_cab)
    banco = next((b for pad, b in NOMES_BANCO if re.search(pad, ref)), "?")
    tipo = "?"
    if re.search(r"\bPJ\b|SOCIEDADE|CNPJ|EMPRESA|LTDA|\bME\b", ref):
        tipo = "PJ"
    if re.search(r"\bPF\b|PESSOA FISICA|\bCPF\b", ref) and "SOCIEDADE" not in ref:
        tipo = "PF"
    return banco, tipo


# ─────────────────────────────── leitores ─────────────────────────────────

def ler_ofx(p):
    raw = p.read_bytes()
    try:
        t = raw.decode("utf-8")             # C6 exporta em UTF-8
    except UnicodeDecodeError:
        t = raw.decode("latin-1", "ignore")
    bankid = (re.search(r"<BANKID>\s*(\d+)", t) or [None, ""])[1]
    org = (re.search(r"<ORG>\s*([^<\r\n]+)", t) or [None, ""])[1]
    banco, tipo = banco_e_tipo(p, org)
    if banco == "?" and bankid.lstrip("0").zfill(3) in BANCOS:
        banco = BANCOS[bankid.lstrip("0").zfill(3)]
    if tipo == "?":
        acct = (re.search(r"<ACCTID>\s*(\d+)", t) or [None, ""])[1]
        tipo = next((tp for (bc, fim), tp in CONTAS_CONHECIDAS.items() if bc == banco and acct.endswith(fim)),
                    "PJ" if banco == "Sicredi" else "?")
    out = []
    for b in re.findall(r"<STMTTRN>(.*?)</STMTTRN>", t, re.S):
        def g(k):
            m = re.search("<" + k + r">([^<\r\n]*)", b)
            return m.group(1).strip() if m else ""
        try:
            v = _num_br(g("TRNAMT"))
        except ValueError:
            continue
        desc = " ".join((g("NAME") + " " + g("MEMO")).split())
        if not desc and banco == "C6" and v > 0:
            desc = "(sem descrição no OFX do C6 — provável resgate de aplicação)"
        out.append({"data": _data(g("DTPOSTED")[:8]), "valor": v,
                    "descricao": desc,
                    "doc": g("FITID") or g("CHECKNUM"), "banco": banco, "conta": tipo})
    return out


def ler_csv(p):
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "latin-1"):
        try:
            t = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        dial = csv.Sniffer().sniff(t[:5000], delimiters=";,\t")
    except csv.Error:
        dial = csv.excel
    linhas = list(csv.reader(t.splitlines(), dial))
    return _tabela(p, linhas, t[:2000])


def ler_xlsx(p):
    import openpyxl
    wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        linhas = [[("" if c is None else c) for c in r] for r in ws.iter_rows(values_only=True)]
        cab = " ".join(str(c) for r in linhas[:15] for c in r)
        out += _tabela(p, linhas, cab)
    return out


def _tabela(p, linhas, cab_txt):
    """Acha a linha de cabeçalho (data / descrição / valor) e lê as linhas."""
    banco, tipo = banco_e_tipo(p, cab_txt)
    for i, r in enumerate(linhas[:40]):
        rot = [gr.norm_texto(c) for c in r]
        c_data = next((j for j, c in enumerate(rot) if re.match(r"DATA( DE)?( LANCAMENTO| DA TRANSACAO| MOVIMENTO)?$|"
                                                                  r"RELEASE_DATE|DATE", c)), None)
        c_valor = next((j for j, c in enumerate(rot) if re.match(r"VALOR|TRANSACTION_NET_AMOUNT|AMOUNT|"
                                                                   r"ENTRADA|CREDITO", c)), None)
        c_desc = next((j for j, c in enumerate(rot) if re.match(r"DESCRI|HISTORICO|LANCAMENTO|TRANSACTION_TYPE|"
                                                                  r"DETALHE|TITULO", c)), None)
        if c_data is None or c_valor is None:
            continue
        c_saida = next((j for j, c in enumerate(rot) if re.match(r"SAIDA|DEBITO", c)), None)
        extras = [j for j, c in enumerate(rot) if re.match(r"(NOME|ORIGEM|DESTINO|CONTRAPARTE|PAGADOR|"
                                                           r"REFERENCE|DESCRICAO)", c) and j != c_desc]
        out = []
        for r in linhas[i + 1:]:
            if len(r) <= max(c_data, c_valor):
                continue
            d = r[c_data]
            d = d.date() if isinstance(d, datetime.datetime) else d if isinstance(d, datetime.date) else _data(d)
            if not d:
                continue
            try:
                v = r[c_valor] if isinstance(r[c_valor], (int, float)) else _num_br(r[c_valor])
            except ValueError:
                continue
            if c_saida is not None and not v and r[c_saida]:
                try:
                    v = -abs(_num_br(r[c_saida]))
                except ValueError:
                    pass
            desc = " ".join(str(r[j]) for j in ([c_desc] if c_desc is not None else []) + extras
                            if j < len(r) and r[j])
            out.append({"data": d, "valor": float(v), "descricao": " ".join(desc.split()),
                        "doc": "", "banco": banco, "conta": tipo})
        return out
    return []


R_DIN = r"-?\(?(?:R\$\s?)?[\d]{1,3}(?:\.\d{3})*,\d{2}\)?-?"
R_FIM_VALORES = re.compile(r"(?:\s+(%s))+\s*$" % R_DIN)
R_DATA_INI = re.compile(r"^(\d\d/\d\d(?:/\d{2,4})?)\b\s*")
R_LIXO_PDF = re.compile(r"SALDO|P[aá]gina|Data\s+Hist|Data\s+Descri|Ag[eê]ncia|Per[ií]odo|Cr[eé]ditos\s+D[eé]bitos|"
                        r"Extrato_|BALP_|EXTRATO CONSOLIDADO|^[A-ZÇ]+ ?/ ?20\d\d$|^\w+/20\d\d$", re.I)


R_CABECA = re.compile(r"^(PIX|PAGAMENTO|RECEBIMENTO|TRANSFER|RENDIMENTO|DINHEIRO|LIBERACAO|COMPRA|DEBITO|"
                      r"REEMBOLSO|DEVOLUC|ENVIO|COBRANCA|TARIFA|ESTORNO|INGRESSO|SAQUE|DEPOSITO|TED|DOC|"
                      r"LIQUIDACAO|CREDITO|INTEGRALIZACAO|RESGATE|APLICACAO|BOLETO)")


def _linhas_com_valor(linhas, rx_mov, sinal):
    """Layouts em que a descrição se espalha por linhas acima e abaixo da linha do valor
    (Sicredi, Mercado Pago). Linha que começa com o tipo da operação abre o próximo
    lançamento; as demais continuam o anterior."""
    itens = []
    for l in linhas:
        m = rx_mov.match(l)
        if m:
            d = _data(m.group("d").replace("-", "/"))
            try:
                v = _num_br(m.group("v"))
            except ValueError:
                continue
            if sinal and m.group("s") == "-":
                v = -abs(v)
            itens.append(["mov", d, v, m.group("t").strip(), []])
        else:
            itens.append(["txt", l])
    for k, it in enumerate(itens):
        if it[0] != "txt":
            continue
        ant = next((x for x in reversed(itens[:k]) if x[0] == "mov"), None)
        prox = next((x for x in itens[k + 1:] if x[0] == "mov"), None)
        if prox is not None and (R_CABECA.match(gr.norm_texto(it[1])) or ant is None):
            prox[4].append(("a", it[1]))
        elif ant is not None:
            ant[4].append(("d", it[1]))
    out = []
    for it in itens:
        if it[0] == "mov":
            antes = [t for k, t in it[4] if k == "a"]
            depois = [t for k, t in it[4] if k == "d"][:2]
            out.append((it[1], it[2], " ".join(" ".join(antes + [it[3]] + depois).split())))
    return out


R_SICREDI_MOV = re.compile(r"^(?P<d>\d\d/\d\d/\d{4})\s*(?P<t>.*?)\s*(?P<s>[+-])\s?R\$\s?(?P<v>[\d.]+,\d{2})$")
R_MP_MOV = re.compile(r"^(?P<d>\d\d-\d\d-\d{4})\s*(?P<t>.*?)\s*\d{8,}\s+R\$\s?(?P<v>-?[\d.]+,\d{2})\s+R\$\s?-?[\d.]+,\d{2}$")


def _pdf_especial(txt):
    """Sicredi e Mercado Pago (PDF). Devolve (banco, [(data, valor, desc)]) ou None."""
    if re.search(r"Cooperativa:\s*\d+", txt[:3000]):
        corpo = txt
        i = corpo.find("Movimentações de")
        if i > 0:                        # pula "Lançamentos futuros"
            corpo = corpo[i:]
        linhas = [l.strip() for l in corpo.splitlines()
                  if l.strip() and not re.match(r"(Saldo|Movimenta|Data Descri|Momento|Período|Titular|"
                                                r"Lançamento|Ouvidoria|SAC|\d+/\d+$)", l.strip(), re.I)]
        return "Sicredi", _linhas_com_valor(linhas, R_SICREDI_MOV, True)
    if "DETALHE DOS MOVIMENTOS" in txt[:3000] and re.search(r"ID da opera|IIDD", txt[:3000]):
        corpo = txt[txt.find("DETALHE DOS MOVIMENTOS"):]
        linhas = [l.strip() for l in corpo.splitlines()
                  if l.strip() and not re.match(r"(DETALHE|DDaattaa|Data\s|\d+/\d+$|Mercado Pago|"
                                                r"Data de gera|Você tem|Ouvidoria|Encontre)", l.strip(), re.I)]
        return "Mercado Pago", _linhas_com_valor(linhas, R_MP_MOV, False)
    if "C6 Bank" in txt and re.search(r"Agência:\s*1\s*•\s*Conta:", txt[:800]):
        meses = {m: i for i, m in enumerate(["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
                                              "agosto", "setembro", "outubro", "novembro", "dezembro"], 1)}
        out, ano = [], None
        for l in txt.splitlines():
            l = l.strip()
            mh = re.match(r"(\w+) (20\d\d) \(", l)
            if mh and mh.group(1).lower() in meses:
                ano = mh.group(2)
                continue
            mm = re.match(r"^(\d\d/\d\d) \d\d/\d\d (.*?)\s+(-?)R\$ ([\d.]+,\d{2})$", l)
            if mm and ano:
                v = _num_br(mm.group(4))
                out.append((_data(mm.group(1) + "/" + ano), -v if mm.group(3) else v, mm.group(2)))
        return "C6", out
    return None


def _tipo_titular(txt):
    """Pelo documento do titular no cabeçalho (antes dos lançamentos, que citam a SOCIEDADE)."""
    cab = re.split(r"Movimenta|DETALHE DOS MOVIMENTOS|Lançamentos", txt[:1500])[0]
    if re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|CNPJ:\s*\d{14}\b", cab):
        return "PJ"
    if re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}|CNPJ:\s*\d{11}\b|CPF:\s*\d{11}\b", cab):
        return "PF"
    return "?"


def ler_pdf(p):
    """Melhor esforço para PDF (prefira OFX). Regras medidas no Santander:
    - a data pode vir só na 1ª linha do dia (consolidado) ou em toda linha (extrato PJ);
    - débito termina em '-' (consolidado) ou começa com '-' (extrato PJ);
    - com 2 valores no fim, o último é o saldo;
    - o nome da contraparte fica na linha de cima (quando a linha do valor não tem texto)
      ou na linha de baixo (quando tem)."""
    import pdfplumber
    txt = None
    for senha in [""] + SENHAS_PDF:
        try:
            with pdfplumber.open(p, password=senha) as pdf:
                txt = "\n".join((pg.extract_text() or "") for pg in pdf.pages)
            break
        except Exception:
            continue
    if txt is None:
        raise ValueError("PDF com senha desconhecida")
    esp = _pdf_especial(txt)
    if esp:
        banco, movs = esp
        tipo = banco_e_tipo(p)[1]
        if tipo == "?":
            tipo = _tipo_titular(txt)
        return [{"data": d, "valor": v, "descricao": t, "doc": "", "banco": banco, "conta": tipo}
                for d, v, t in movs if d]
    banco, tipo = banco_e_tipo(p, txt[:3000])
    m_tp = re.search(r"Extrato_(PF|PJ)", txt)          # rodapé do Santander: Extrato_PF_A4_Inteligente
    if m_tp:
        tipo = m_tp.group(1)
    m_ct = re.search(r"Conta(?: Corrente)?:?\s*\n?\s*(?:\d{4}\s+)?([\d.\-]{6,})", txt[:3000])
    if m_ct:
        dig = re.sub(r"\D", "", m_ct.group(1))
        tipo = next((tp for (bc, fim), tp in CONTAS_CONHECIDAS.items()
                     if bc == banco and fim in dig), tipo)
    # o ano vem do título ("janeiro/2025"); a 1ª data do texto pode ser de outro ano
    m_ano = re.search(r"(?:janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|"
                      r"dezembro)/(20\d\d)", txt[:3000], re.I)
    ano_cab = m_ano.group(1) if m_ano else \
        (re.search(r"\d\d/\d\d/(20\d\d)", txt) or [None, str(datetime.date.today().year)])[1]
    for corte in ("Saldos por Per", "Comprovantes de Pagamento"):   # tabelas/anexos que repetem valores
        i = txt.find(corte)
        if i > 0:
            txt = txt[:i]
    linhas = [l.strip() for l in txt.splitlines() if l.strip() and not R_LIXO_PDF.search(l.strip())]
    itens, data_atual = [], None        # itens: ("mov", data, valor, texto) | ("txt", texto)
    for l in linhas:
        md = R_DATA_INI.match(l)
        resto = l[md.end():] if md else l
        if md:
            d = md.group(1)
            if len(d) == 5:
                d += "/" + ano_cab
            data_atual = _data(d) or data_atual
        mv = R_FIM_VALORES.search(" " + resto)
        if mv and data_atual:
            toks = re.findall(R_DIN, mv.group(0))
            bruto = toks[-2] if len(toks) >= 2 else toks[-1]
            try:
                v = _num_br(bruto)
            except ValueError:
                continue
            texto = (" " + resto)[:mv.start()].strip()
            texto = re.sub(r"\s+(-|\d{5,})$", "", texto).strip(" -")
            itens.append(["mov", data_atual, v, texto, []])
        else:
            itens.append(["txt", resto])
    # distribui as linhas de texto soltas
    for k, it in enumerate(itens):
        if it[0] != "txt":
            continue
        ant = next((x for x in reversed(itens[:k]) if x[0] == "mov"), None)
        prox = itens[k + 1] if k + 1 < len(itens) else None
        if prox and prox[0] == "mov" and not prox[3]:
            prox[4].insert(0, it[1])            # linha de cima de um valor sem texto
        elif ant is not None:
            ant[4].append(it[1])
    out = []
    for it in itens:
        if it[0] != "mov":
            continue
        desc = " ".join(([it[3]] if it[3] else []) + it[4][:2])
        out.append({"data": it[1], "valor": it[2], "descricao": " ".join(desc.split()), "doc": "",
                    "banco": banco, "conta": tipo})
    return out


LEITORES = {".ofx": ler_ofx, ".csv": ler_csv, ".xlsx": ler_xlsx, ".xls": None, ".pdf": ler_pdf}


def categoria(desc):
    t = gr.norm_texto(desc)
    if R_RENDIMENTO.search(t):
        return "Rendimento"
    if R_CNJ.search(t):                  # número de processo na descrição (RPV/alvará)
        return "Judicial"
    if "PROVAVEL RESGATE" in t:
        return "Rendimento"
    if R_PARCEIRO.search(t):
        return "Parceiro"
    if R_INTERNA.search(t):
        return "Interna"
    if R_JUDICIAL.search(t):
        return "Judicial"
    if R_PLATAFORMA.search(t):
        return "Plataforma"
    if R_BANCO_REU.search(re.sub(r"PIX (RECEBIDO|ENVIADO)|TED (RECEBIDA|ENVIADA)|TRANSF\w*", "", t)):
        return "Banco réu"
    return "Pessoa"


def pagadores():
    """Regras manuais (pagadores.json): quem é parceiro, pessoal, extrajudicial ou de qual processo."""
    f = AQUI / "pagadores.json"
    return json.loads(f.read_text(encoding="utf-8")).get("regras", []) if f.exists() else []


def ler_pasta(pasta):
    todos, por_arquivo, ignorados = [], {}, []
    for p in sorted(Path(pasta).rglob("*")):
        if not p.is_file() or p.name.startswith(("~$", ".")):
            continue
        f = LEITORES.get(p.suffix.lower())
        if not f:
            ignorados.append(p.name)
            continue
        try:
            movs = f(p)
        except Exception as e:
            ignorados.append("%s (erro: %s)" % (p.name, e))
            continue
        por_arquivo[str(p.relative_to(pasta))] = {"lancamentos": len(movs),
                                                 "banco": movs[0]["banco"] if movs else "?",
                                                 "conta": movs[0]["conta"] if movs else "?",
                                                 "de": str(min((m["data"] for m in movs if m["data"]), default="")),
                                                 "ate": str(max((m["data"] for m in movs if m["data"]), default=""))}
        for m in movs:
            m["arquivo"] = p.name
            todos.append(m)
    # dedup (mesmo extrato exportado em OFX e PDF, em layouts diferentes ou com períodos sobrepostos):
    # para cada (conta, dia, valor) fica o MAIOR número de ocorrências visto num único arquivo —
    # dois PIX iguais no mesmo dia do mesmo arquivo continuam sendo dois.
    from collections import Counter, defaultdict
    por_arq = defaultdict(Counter)
    for m in todos:
        por_arq[m["arquivo"]][(m["banco"], m["conta"], str(m["data"]), round(m["valor"], 2))] += 1
    limite = Counter()
    for cnt in por_arq.values():
        for k, n in cnt.items():
            limite[k] = max(limite[k], n)
    usados_k, unicos = Counter(), []
    for m in sorted(todos, key=lambda m: (m["arquivo"].lower().endswith(".pdf"), -len(m["descricao"]),
                                          str(m["data"]))):
        k = (m["banco"], m["conta"], str(m["data"]), round(m["valor"], 2))
        if usados_k[k] >= limite[k]:
            continue
        usados_k[k] += 1
        unicos.append(m)
    regras = pagadores()
    creditos = []
    for m in unicos:
        if m["valor"] > 0 and m["data"]:
            m["categoria"] = categoria(m["descricao"])
            nd = gr.norm_texto(m["descricao"])
            for r in regras:
                if ("padrao" not in r or re.search(r["padrao"], nd)) and \
                        ("data" not in r or r["data"] == str(m["data"])) and \
                        ("valor" not in r or abs(r["valor"] - m["valor"]) < 0.01):
                    m["categoria"] = r.get("categoria", m["categoria"])
                    m["regra_manual"] = r
                    break
            m.pop("_pend", None)
            creditos.append(m)
    creditos.sort(key=lambda m: m["data"])
    return creditos, por_arquivo, ignorados


if __name__ == "__main__":
    cr, arqs, ign = ler_pasta(sys.argv[1])
    print(json.dumps(arqs, ensure_ascii=False, indent=1))
    if ign:
        print("ignorados:", ign)
    from collections import Counter
    print(Counter(c["categoria"] for c in cr))
    for c in cr:
        if c["categoria"] not in ("Rendimento", "Interna"):
            print(c["data"], c["banco"], c["conta"], "%.2f" % c["valor"], c["categoria"], c["descricao"][:70])
