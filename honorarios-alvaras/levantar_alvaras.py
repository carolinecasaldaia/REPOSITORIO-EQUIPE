#!/usr/bin/env python3
"""Levantamento de alvarás e honorários (2025 em diante) — SOMENTE LEITURA.

Por que existe: a planilha Controle_Honorarios_e_Ganhos tem só o que foi anotado à
mão, e muitos recebimentos ficaram sem registro. Este script percorre TODOS os
processos do escritório e monta a trilha do dinheiro em cada um:

    cumprimento de sentença → Sisbajud / depósito do banco → alvará determinado
    → alvará expedido → levantado / extinto pelo pagamento

Fontes (nenhuma é alterada):
  - Lista de processos: RODAGEM PROCESSUAL 2026, PROCESSOS CÍVEIS, PROCESSOS PARA
    ACOMPANHAMENTO DIÁRIO, Controle_Honorarios v2 e o que aparecer no Diário.
  - e-SAJ do TJAL (consulta pública): processo principal + incidentes
    (cumprimento de sentença tem página própria).
  - Diário de Justiça Eletrônico Nacional (DJEN), pelas 3 OABs: todos os tribunais.
  - Astrea: cache da última rodada dos relatórios mensais (fora do TJAL).

O alvará do escritório é expedido separado do cliente (decisão da Caroline): o
que tem sinal de honorários/advogada vai como "Escritório"; o resto, "Conferir".

Uso:  <python com openpyxl> levantar_alvaras.py [coletar|analisar|tudo] [--desde 2025-01-01]
"""
import argparse
import datetime
import html
import http.cookiejar
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "painel-financeiro"))
import gerar_relatorios as gr  # noqa: E402  (reaproveita leitura da Rodagem, DJEN e normalizações)

DRIVE = Path.home() / "Library/CloudStorage/GoogleDrive-contato@carolinemacedoadv.com/Meu Drive/Documentos Escritório "
RODAGEM = DRIVE / "A - REVISIONAL" / "A - RODAGEM"
HONOR = DRIVE / "EMPRESA" / "HONORÁRIOS DE SUCUMBÊNCIA"
CONTROLE_V2 = HONOR / "HONORARIOS SUCUMBENCIA E CONTRATUAIS - BUSCA E APREENSÃO" / \
    "Controle_Honorarios_e_Ganhos_Caroline_Macedo_v2.xlsx"
SAIDA = HONOR / "LEVANTAMENTO ALVARÁS"
DADOS = SAIDA / "_dados"
ASTREA_CACHE = sorted((RODAGEM / "RELATÓRIOS MENSAIS").glob("*/_dados/astrea.json"))

ESAJ = "https://www2.tjal.jus.br"
TRIBUNAIS = {"02": "TJAL", "17": "TJPE", "26": "TJSP", "05": "TJBA", "13": "TJMG", "15": "TJPB",
             "18": "TJPI", "24": "TJSC", "03": "TJAP", "09": "TJGO", "06": "TJCE", "08": "TJES",
             "14": "TJPA", "12": "TJMS", "20": "TJRN", "21": "TJRS", "22": "TJRO", "04": "TJAM",
             "16": "TJPR", "10": "TJMA", "19": "TJRJ", "27": "TJTO", "25": "TJSE", "23": "TJRR",
             "01": "TJAC", "07": "TJDFT", "11": "TJMT"}


def tribunal(n):
    if len(n) != 20:
        return "?"
    if n[13] == "8":
        return TRIBUNAIS.get(n[14:16], "TJ-" + n[14:16])
    if n[13] == "5":
        return "TRT" + str(int(n[14:16]))
    if n[13] == "4":
        return "TRF" + str(int(n[14:16]))
    return "J" + n[13]


def salvar(nome, obj):
    DADOS.mkdir(parents=True, exist_ok=True)
    (DADOS / nome).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def carregar(nome, padrao=None):
    p = DADOS / nome
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else padrao


# ───────────────────────── universo de processos ─────────────────────────

def _add(univ, num, cliente, origem, fonte=None, extra=None):
    num = gr.digitos(num)
    if len(num) != 20:
        return
    p = univ.setdefault(num, {"clientes": [], "origens": [], "fontes": [], "extra": {}})
    if cliente and cliente not in p["clientes"]:
        p["clientes"].append(cliente)
    if origem not in p["origens"]:
        p["origens"].append(origem)
    if fonte and fonte not in p["fontes"]:
        p["fontes"].append(fonte)
    if extra:
        p["extra"].update(extra)


_TIPO_RODAGEM = {"revisional": "Revisional", "busca": "Busca e Apreensão", "precatoria": None,
                 "apenso": None, "outro": None}


def montar_universo():
    import openpyxl
    univ = {}
    for arq, origem, fixo in [(RODAGEM / "RODAGEM PROCESSUAL 2026.xlsx", "Rodagem 2026", None),
                              (RODAGEM / "PROCESSOS CÍVEIS.xlsx", "Processos Cíveis", "Cível")]:
        if not arq.exists():
            print("  ⚠ não achei", arq.name)
            continue
        clientes, _ = gr.ler_rodagem(arq)
        for cli in clientes.values():
            for num, info in cli["processos"].items():
                fonte = fixo or _TIPO_RODAGEM.get(info.get("tipo"))
                _add(univ, num, cli["nome"], origem, fonte,
                     {"aba": ", ".join(cli["abas"])} if cli["abas"] else None)
                if info.get("pai"):
                    _add(univ, info["pai"], cli["nome"], origem, fonte)

    # Acompanhamento diário: 1ª coluna = categoria (BUSCA E APREENSÃO, REVISIONAL...)
    arq = RODAGEM / "PROCESSOS PARA ACOMPANHAMENTO DIÁRIO 02012025.xlsx"
    if arq.exists():
        wb = openpyxl.load_workbook(arq, read_only=True, data_only=True)
        for ws in wb.worksheets:
            for r in ws.iter_rows(values_only=True):
                cel = [str(c) if c is not None else "" for c in r]
                nums = [n for c in cel for n in gr.CNJ.findall(c)]
                if not nums:
                    continue
                cat = gr.norm_texto(cel[0]) if cel and not gr.digitos(cel[0]) else ""
                nome = cel[1] if len(cel) > 1 and not gr.digitos(cel[1]) else ""
                fonte = ("Busca e Apreensão" if "BUSCA" in cat else "Revisional" if "REVIS" in cat
                         else cat.title() if cat else None)
                for n in nums:
                    _add(univ, n, gr.nome_bonito(nome) if nome else None, "Acompanhamento diário", fonte)
        wb.close()

    # Planilha de honorários v2
    if CONTROLE_V2.exists():
        wb = openpyxl.load_workbook(CONTROLE_V2, read_only=True, data_only=True)
        for aba, c_nome, c_num in [("Honorários", 1, 2), ("Recebidos", 1, 3), ("Base de Ganhos", 1, 2)]:
            if aba not in wb.sheetnames:
                continue
            for r in wb[aba].iter_rows(min_row=5, values_only=True):
                if len(r) > c_num and r[c_nome] and r[c_num]:
                    tipo = None
                    if aba == "Recebidos" and r[2]:
                        tipo = "Busca e Apreensão" if "BUSCA" in gr.norm_texto(r[2]) else str(r[2]).title()
                    _add(univ, r[c_num], gr.nome_bonito(r[c_nome]), "Controle v2 (%s)" % aba,
                         tipo or "Busca e Apreensão")
        wb.close()

    # Sentenças por banco (só para não deixar processo de fora)
    arq = RODAGEM / "SENTENÇAS POR BANCO 2026.xlsx"
    if arq.exists():
        wb = openpyxl.load_workbook(arq, read_only=True, data_only=True)
        for ws in wb.worksheets:
            for r in ws.iter_rows(values_only=True):
                for c in r:
                    for n in gr.CNJ.findall(str(c or "")):
                        _add(univ, n, None, "Sentenças por banco")
        wb.close()
    return univ


# ───────────────────────────── e-SAJ (TJAL) ──────────────────────────────

def _txt(s):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s or "")).split())


def _campo(h, ident):
    m = re.search(r'id="%s"[^>]*>(.*?)</' % ident, h, re.S)
    return _txt(m.group(1)) if m else ""


def _movs(h):
    movs, vistos = [], set()
    for r in re.findall(r'<tr class="[^"]*containerMovimentacao[^"]*".*?</tr>', h, re.S):
        tds = [_txt(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
        if len(tds) < 2 or not re.match(r"\d\d/\d\d/\d{4}", tds[0]):
            continue
        k = (tds[0], tds[-1][:300])
        if k in vistos:
            continue
        vistos.add(k)
        movs.append([datetime.datetime.strptime(tds[0][:10], "%d/%m/%Y").date().isoformat(), tds[-1]])
    return movs


def _partes(h):
    m = re.search(r'id="tablePartesPrincipais"(.*?)</table>', h, re.S)
    if not m:
        return []
    out = []
    for tr in re.findall(r"<tr.*?</tr>", m.group(1), re.S):
        tds = [_txt(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(tds) >= 2:
            papel = tds[0].strip(" :")
            nome = re.split(r"\b(Advogad[oa]|Defensor|Repre)", tds[1])[0].strip()
            out.append([papel, nome])
    return out


def _abrir():
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    op.addheaders = [("User-Agent", "Mozilla/5.0")]
    op.open(ESAJ + "/cpopg/open.do", timeout=60).read()
    time.sleep(1.2)
    return op


def _pagina(h):
    return {"classe": _campo(h, "classeProcesso"), "assunto": _campo(h, "assuntoProcesso"),
            "vara": _campo(h, "varaProcesso"), "valor": _campo(h, "valorAcaoProcesso"),
            "situacao": _campo(h, "labelSituacaoProcesso"), "partes": _partes(h), "movs": _movs(h)}


def esaj_completo(n):
    op = _abrir()
    fmt = gr.formatar_cnj(n)
    q = urllib.parse.urlencode({
        "conversationId": "", "cbPesquisa": "NUMPROC", "dadosConsulta.tipoNuProcesso": "UNIFICADO",
        "numeroDigitoAnoUnificado": fmt[:15], "foroNumeroUnificado": n[16:],
        "dadosConsulta.valorConsultaNuUnificado": fmt, "dadosConsulta.valorConsulta": "",
        "dadosConsulta.localPesquisa.cdLocal": "-1"})
    h = op.open(ESAJ + "/cpopg/search.do?" + q, timeout=60).read().decode("utf-8", "ignore")
    if re.search(r"segredo de justi|senha do processo", h, re.I) and "Distribuição" not in h:
        return {"ok": True, "segredo": True, "movs": [], "incidentes": []}
    # A busca às vezes cai numa lista (processo com mais de um registro): abre o 1º.
    if "Distribuição" not in h:
        lk = re.search(r'href="(/cpopg/show\.do\?processo\.codigo=[^"]+)"', h)
        if lk:
            time.sleep(1)
            h = op.open(ESAJ + html.unescape(lk.group(1)), timeout=60).read().decode("utf-8", "ignore")
    reg = _pagina(h)
    reg["ok"] = bool(reg["movs"]) or "Distribuição" in h
    reg["segredo"] = False
    reg["incidentes"] = []
    i = h.find("Incidentes, ações incidentais")
    bloco = h[i:i + 20000] if i >= 0 else ""
    for href, rot in re.findall(r'<a class="incidente" href="([^"]+)"[^>]*>(.*?)</a>', bloco, re.S):
        time.sleep(1.2)
        try:
            hi = op.open(ESAJ + html.unescape(href), timeout=60).read().decode("utf-8", "ignore")
            inc = _pagina(hi)
            inc["rotulo"] = _txt(rot)
            reg["incidentes"].append(inc)
        except Exception as e:  # incidente sem resposta não derruba o principal
            reg["incidentes"].append({"rotulo": _txt(rot), "erro": str(e), "movs": []})
    return reg


def baixar_esaj(numeros):
    cache = carregar("esaj_completo.json", {})
    faltam = [n for n in numeros if not (cache.get(n) or {}).get("ok")]
    print("e-SAJ TJAL: %d processos (%d já em cache)" % (len(numeros), len(numeros) - len(faltam)), flush=True)

    def tentar(n):
        for t in range(3):
            try:
                r = esaj_completo(n)
                if r["ok"]:
                    return n, r
            except Exception:
                pass
            time.sleep(3 * (t + 1))
        return n, {"ok": False, "movs": [], "incidentes": []}

    feitos = 0
    with ThreadPoolExecutor(2) as ex:
        for n, r in ex.map(tentar, faltam):
            cache[n] = r
            feitos += 1
            if feitos % 25 == 0:
                print("   %d/%d" % (feitos, len(faltam)), flush=True)
                salvar("esaj_completo.json", cache)
    salvar("esaj_completo.json", cache)
    print("   falharam: %d" % sum(1 for n in numeros if not cache[n].get("ok")), flush=True)
    return cache


# ──────────────────────────────── DJEN ────────────────────────────────────

def baixar_djen(desde):
    cache = carregar("djen.json", {})
    hoje = datetime.date.today()
    ini = desde.replace(day=1)
    while ini <= hoje:
        fim = min((ini.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1), hoje)
        chave = ini.isoformat()[:7]
        # o mês corrente sempre baixa de novo; meses fechados ficam no cache
        if chave not in cache or fim >= hoje - datetime.timedelta(days=3):
            print("DJEN %s" % chave, flush=True)
            itens = gr.baixar_djen(ini, fim)
            cache[chave] = [{
                "numero": gr.digitos(it.get("numero_processo")), "data": it.get("data_disponibilizacao"),
                "tribunal": it.get("siglaTribunal"), "classe": it.get("nomeClasse"),
                "tipo": it.get("tipoComunicacao"), "orgao": it.get("nomeOrgao"),
                "link": it.get("link"),
                "partes": [d.get("nome") for d in (it.get("destinatarios") or [])],
                "texto": gr.limpar_html(it.get("texto"))[:12000]} for it in itens]
            salvar("djen.json", cache)
        ini = fim + datetime.timedelta(days=1)
    return cache


# ─────────────────────────────── análise ──────────────────────────────────

N = gr.norm_texto
R_EXPEDIDO = re.compile(
    r"EXPEDICAO DE ALVARA|ALVARA (ELETRONICO |JUDICIAL )?(DE LEVANTAMENTO )?(FOI )?(EXPEDIDO|ASSINADO|EMITIDO)|"
    r"EXPEDIDO (O )?ALVARA|EXPEDIDO ALVARA|ALVARA N[O.]? ?\d|EXPEDICAO DE OFICIO (DE |PARA )?TRANSFERENCIA|"
    r"OFICIO DE TRANSFERENCIA (EXPEDIDO|ENVIADO|ASSINADO)|SISCONDJ")
R_DETERMINADO = re.compile(
    r"EXPECA(M)?-SE (O |OS |A )?(COMPETENTE |RESPECTIVO |RESPECTIVOS |NECESSARIO )?ALVARA|"
    r"EXPEDICAO D[OE]S? (COMPETENTE )?ALVARA|EXPECA-SE OFICIO.{0,40}TRANSFER|"
    r"(DEFIRO|AUTORIZO|DETERMINO) (O |A )?(LEVANTAMENTO|LIBERACAO|TRANSFERENCIA) D[OAE]S? "
    r"(VALOR|QUANTIA|DEPOSITO|IMPORTANCIA|MONTANTE|HONORARIO|CREDITO)|LEVANTAMENTO EM FAVOR|"
    r"LIBERE-SE|LIBEREM-SE|TRANSFIRA-SE|TRANSFIRAM-SE|EXPEDICAO DE ALVARA EM FAVOR")
R_LEVANTADO = re.compile(
    r"ALVARA (CUMPRIDO|LEVANTADO|PAGO|LIQUIDADO)|LEVANTAMENTO (REALIZADO|EFETUADO|EFETIVADO)|"
    r"COMPROVANTE DE (LEVANTAMENTO|TRANSFERENCIA)|TRANSFERENCIA (REALIZADA|EFETIVADA|EFETUADA|CONCLUIDA)|"
    r"VALOR(ES)? (LEVANTADO|TRANSFERIDO|LIBERADO)S?")
R_EXTINTO_PAGO = re.compile(
    r"(EXTIN\w*|EXTINGO)[^.]{0,150}(PAGAMENTO|SATISFA|ADIMPLEMENTO|QUITACAO|924,? ?(INC(ISO)?\.? ?)?II\b)|"
    r"(PAGAMENTO|SATISFACAO DA OBRIGACAO|OBRIGACAO (FOI )?SATISFEITA)[^.]{0,120}(EXTIN\w*|EXTINGO)")
R_PEDIDO = re.compile(r"PEDIDO DE (EXPEDICAO DE )?ALVARA|REQUER\w* (A )?EXPEDICAO D[OE] ALVARA|"
                      r"PEDIDO DE LEVANTAMENTO|PEDIDO DE TRANSFERENCIA")
R_DEPOSITO = re.compile(
    r"(COMPROVANTE|GUIA) DE (PAGAMENTO|DEPOSITO)|JUNTADA DE (COMPROVANTE|GUIA)|"
    r"(EFETUOU|REALIZOU|COMPROVOU|INFORMOU|NOTICIOU)( O)? (PAGAMENTO|DEPOSITO)|DEPOSITOU|"
    r"DEPOSITO JUDICIAL (DO|DOS|DA|REALIZADO|EFETUADO|ACOSTADO)|VALOR(ES)? DEPOSITADO|QUANTIA DEPOSITADA|"
    r"PAGAMENTO (REALIZADO|EFETUADO|COMPROVADO)")
R_CONSIGNACAO = re.compile(r"QUANTUM CONTROVERSO|PARCELAS (VINCENDAS|PACTUADAS|DO CONTRATO)|PRESTACOES|"
                           r"CONSIGNA|VALOR INCONTROVERSO|PURGA")
R_SISBAJUD = re.compile(r"SISBAJUD|BACENJUD|BLOQUEIO (DE VALORES|ON ?-?LINE|ELETRONICO|DE ATIVOS)|PENHORA ON ?-?LINE")
R_SISB_POS = re.compile(r"(RESULTADO )?POSITIV|VALOR(ES)? BLOQUEAD|BLOQUEIO (PARCIAL|TOTAL|EFETIVADO|REALIZADO)|"
                        r"TRANSFERENCIA (DO|DOS) VALOR(ES)? BLOQUEADO")
R_SISB_NEG = re.compile(r"NEGATIV|INFRUTIFER|SEM SALDO|NAO (FORAM )?ENCONTRAD|INEXISTENCIA DE (SALDO|VALORES)")
R_CUMPRIMENTO = re.compile(r"EXECUCAO DE SENTENCA INICIADA|CUMPRIMENTO DE SENTENCA|ART\.? ?523")
R_HONOR = re.compile(r"HONORARI|ADVOGAD|PATRON|CAUSIDIC|CAROLINE|SOCIEDADE (INDIVIDUAL )?DE ADVOCACIA")
R_VALOR = re.compile(r"R\$\s*([\d]{1,3}(?:\.\d{3})*,\d{2})")
# Cabeçalho do Diário: "ADV: CAROLINE NEIVA CHRISTOFANO MACEDO (OAB 15766/AL), ..." — sai antes de analisar
R_LISTA_ADV = re.compile(r"\bADV(OGAD[OA]S?)?\s*:\s*|[A-Z][A-Z .'-]{5,80}\(OAB [^)]{2,20}\),?")
R_CHAVES = re.compile(r"ALVARA|LEVANTAMENT|TRANSFER|DEPOSIT|PAGAMENTO|SISBAJUD|BLOQUEI|EXTIN|SATISFA|"
                      r"LIBERE|LIBERAC")


def limpar_cabecalho(t):
    return R_LISTA_ADV.sub(" ", t)


def janela_honor(t, padrao):
    """Há sinal de honorários/advogada a até 300 caracteres do trecho que bateu?"""
    for m in padrao.finditer(t):
        if R_HONOR.search(t[max(0, m.start() - 300): m.end() + 300]):
            return True
    return False

ETAPAS = [  # (código, rótulo, peso para a situação do processo)
    ("extinto_pago", "Extinto pelo pagamento", 7),
    ("levantado", "Valor levantado/transferido", 6),
    ("expedido", "Alvará expedido", 5),
    ("determinado", "Alvará determinado", 4),
    ("pedido", "Alvará pedido (por nós)", 3),
    ("deposito", "Depósito/pagamento do devedor", 3),
    ("sisbajud_pos", "Sisbajud com bloqueio", 3),
    ("sisbajud", "Sisbajud pedido/sem resultado", 2),
    ("cumprimento", "Cumprimento de sentença", 1),
]
ROTULO = {c: r for c, r, _ in ETAPAS}
PESO = {c: p for c, _, p in ETAPAS}


def valores_perto(t, padrao):
    """Valores em R$ num raio de 400 caracteres do trecho que bateu."""
    vals = []
    for m in padrao.finditer(t):
        janela = t[max(0, m.start() - 400): m.end() + 400]
        for v in R_VALOR.findall(janela):
            f = float(v.replace(".", "").replace(",", "."))
            if 50 <= f <= 5_000_000 and f not in vals:
                vals.append(f)
    return vals


def classificar_evento(texto, no_cumprimento=False):
    """Texto de movimentação/publicação → lista de (etapa, valores)."""
    t = limpar_cabecalho(N(texto))
    out = []
    if R_EXTINTO_PAGO.search(t) and re.search(r"EXECU|CUMPRIMENTO", t):
        out.append(("extinto_pago", valores_perto(t, R_EXTINTO_PAGO)))
    if R_LEVANTADO.search(t):
        out.append(("levantado", valores_perto(t, R_LEVANTADO)))
    if R_PEDIDO.search(t):
        out.append(("pedido", valores_perto(t, R_PEDIDO)))
    elif R_EXPEDIDO.search(t):
        out.append(("expedido", valores_perto(t, R_EXPEDIDO)))
    elif R_DETERMINADO.search(t) and not re.search(r"LEVANTAMENTO D[AE]S? (RESTRIC|GRAVAME|BLOQUEIO DO VEICULO|RENAJUD)", t):
        out.append(("determinado", valores_perto(t, R_DETERMINADO)))
    if R_DEPOSITO.search(t) and not (R_CONSIGNACAO.search(t) and not no_cumprimento) and \
            (no_cumprimento or janela_honor(t, R_DEPOSITO) or re.search(r"CUMPRIMENTO (DEFINITIVO )?DE SENTENCA", t)):
        out.append(("deposito", valores_perto(t, R_DEPOSITO)))
    if R_SISBAJUD.search(t):
        if R_SISB_POS.search(t) and not R_SISB_NEG.search(t):
            out.append(("sisbajud_pos", valores_perto(t, R_SISBAJUD)))
        elif not re.search(r"DEFIRO,? DESDE JA,? A BUSCA DE VALORES", t) or R_SISB_NEG.search(t):
            out.append(("sisbajud", []))
    if not out and R_CUMPRIMENTO.search(t) and (no_cumprimento or "EXECUCAO DE SENTENCA INICIADA" in t
                                                 or "INTIMACAO" in t or "523" in t):
        out.append(("cumprimento", valores_perto(t, R_CUMPRIMENTO)))
    return out


def beneficiario(texto):
    t = limpar_cabecalho(N(texto))
    outro = re.search(r"EM FAVOR D[EOA]S? ([^,;]{3,80}ADVOGADOS[^,;]{0,40})", t)
    if outro and "CAROLINE" not in outro.group(1) and "MACEDO" not in outro.group(1):
        return "Outro escritório (conferir)"
    if janela_honor(t, R_CHAVES) or re.search(r"(INICIADO|INAUGURADO|PROMOVIDO|AJUIZADO) POR CAROLINE|"
                                               r"HONORARIOS (ADVOCATICIOS )?SUCUMBENCIAIS", t[:600]):
        return "Escritório (honorários)"
    if R_CONSIGNACAO.search(t) or re.search(r"EM FAVOR D[AO] (PARTE )?(AUTOR|REQUERENTE|DEMANDANTE|RE\b|REU)", t):
        return "Cliente (não é do escritório)"
    return "Conferir"


def fonte_de_custo(num, u, esaj, djen_classes, djen_cab=""):
    """Busca e Apreensão, Revisional, Cível, Trabalhista… Ordem: classe do processo,
    lista em que ele está (Rodagem/Cíveis/Acompanhamento), assunto, texto do Diário."""
    cls = N((esaj or {}).get("classe", "")) + " " + " ".join(N(c) for c in djen_classes)
    ass = N((esaj or {}).get("assunto", "")) + " " + N(djen_cab)
    fontes = u.get("fontes", []) if u else []
    if "BUSCA E APREENS" in cls:
        return "Busca e Apreensão"
    if "Cível" in fontes:
        return "Cível"
    if "Revisional" in fontes or "REVISION" in cls:
        return "Revisional"
    if "Busca e Apreensão" in fontes:
        return "Busca e Apreensão"
    if fontes:
        return fontes[0]
    if "TRABALH" in cls or tribunal(num).startswith("TRT"):
        return "Trabalhista"
    if re.search(r"EXECUCAO DE TITULO EXTRAJUDICIAL|MONITORIA", cls):
        return "Execução/Cobrança"
    if re.search(r"REVISAO|INTERPRETACAO|CONTRATOS BANCARIOS|CAPITALIZACAO|JUROS|TARIFA", ass):
        return "Revisional"
    if re.search(r"BUSCA E APREENS|ALIENACAO FIDUCIARIA", ass):
        return "Busca e Apreensão"
    if re.search(r"INVENTARIO|ARROLAMENTO|ALIMENTOS|DIVORCIO|GUARDA|FAMILIA|SUCESS", cls + " " + ass):
        return "Família/Sucessões"
    if re.search(r"JUIZADO|PROCEDIMENTO COMUM|INDENIZ|OBRIGACAO DE FAZER|CONSUMIDOR|DANO|CUMPRIMENTO",
                 cls + " " + ass):
        return "Cível"
    return "Conferir"


_BANCOS = gr._BANCO


def cliente_do_processo(u, esaj, djen_partes):
    if u and u.get("clientes"):
        return u["clientes"][0]
    for papel, nome in (esaj or {}).get("partes", []):
        if nome and not _BANCOS.search(N(nome)):
            return gr.nome_bonito(nome)
    for nome in djen_partes:
        if nome and not _BANCOS.search(N(nome)) and "CAROLINE" not in N(nome):
            return gr.nome_bonito(nome)
    return ""


def analisar(desde):
    univ = carregar("universo.json", {})
    esaj = carregar("esaj_completo.json", {})
    djen = carregar("djen.json", {})
    astrea = {}
    for p in ASTREA_CACHE:
        astrea.update(json.loads(p.read_text(encoding="utf-8")))
    d0 = desde.isoformat()

    eventos = {}      # num -> lista de eventos
    djen_info = {}    # num -> {classes, partes}

    def add(num, data, etapa, vals, fonte, texto, link=""):
        if not data or data < d0:
            return
        # Recurso no 2º grau (nº terminado em 0000): "extinto", "depósito", "pagamento" ali
        # falam de custas/preparo, não de honorários. Dinheiro se resolve no 1º grau.
        if num[16:] == "0000" and etapa not in ("expedido", "levantado"):
            return
        eventos.setdefault(num, []).append({
            "data": data, "etapa": etapa, "valores": vals, "fonte": fonte,
            "benef": beneficiario(texto), "link": link,
            "texto": " ".join(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", texto).split())[:1500]})

    for num, reg in esaj.items():
        for data, txt in reg.get("movs", []):
            no_cump = "CUMPRIMENTO" in N(txt[-80:]) or "SEQ.:" in N(txt)
            for et, vals in classificar_evento(txt, no_cump):
                add(num, data, et, vals, "e-SAJ", txt)
        for inc in reg.get("incidentes", []):
            cump = "CUMPRIMENTO" in N(inc.get("rotulo", "")) or "EXECU" in N(inc.get("rotulo", ""))
            for data, txt in inc.get("movs", []):
                for et, vals in classificar_evento(txt, cump):
                    add(num, data, et, vals, "e-SAJ (%s)" % inc.get("rotulo", "incidente"), txt)

    for mes, itens in djen.items():
        for it in itens:
            num = it["numero"]
            if len(num) != 20:
                continue
            inf = djen_info.setdefault(num, {"classes": set(), "partes": [], "tribunal": it.get("tribunal"),
                                             "cab": ""})
            if len(inf["cab"]) < 1500:
                inf["cab"] += " " + limpar_cabecalho(N(it["texto"][:500]))
            if it.get("classe"):
                inf["classes"].add(it["classe"])
            inf["partes"] += [p for p in it.get("partes", []) if p not in inf["partes"]]
            cump = "CUMPRIMENTO" in N(it.get("classe", "")) or "EXECU" in N(it.get("classe", ""))
            for et, vals in classificar_evento(it["texto"], cump):
                add(num, it["data"], et, vals, "Diário (%s)" % (it.get("tribunal") or ""), it["texto"],
                    it.get("link") or "")

    for num, reg in astrea.items():
        if not reg or not reg.get("achou"):
            continue
        for data, txt in reg.get("itens", []):
            t0 = N(txt.split("\n")[0])
            if re.match(r"(TAREFA|PRAZO|COMPROMISSO|LEMBRETE)", t0):
                continue
            for et, vals in classificar_evento(txt):
                add(num, data, et, vals, "Astrea", txt)

    # Dedup: o mesmo ato aparece no e-SAJ e no Diário (dias diferentes). Mantém o
    # primeiro de cada (etapa, valores) num intervalo de 15 dias.
    linhas = []
    for num, evs in eventos.items():
        evs.sort(key=lambda e: (e["data"], e["fonte"]))
        limpos = []
        for e in evs:
            dup = next((x for x in limpos if x["etapa"] == e["etapa"] and
                        (set(x["valores"]) == set(e["valores"]) or not e["valores"]) and
                        abs((datetime.date.fromisoformat(e["data"]) -
                             datetime.date.fromisoformat(x["data"])).days) <= 15), None)
            if dup:
                if e["fonte"] not in dup["fonte"]:
                    dup["fonte"] += " + " + e["fonte"]
                if e["link"] and not dup["link"]:
                    dup["link"] = e["link"]
                if dup["benef"] == "Conferir" and e["benef"] != "Conferir":
                    dup["benef"] = e["benef"]
                continue
            limpos.append(e)
        eventos[num] = limpos

    procs = []
    for num, evs in eventos.items():
        u = univ.get(num)
        reg = esaj.get(num)
        inf = djen_info.get(num, {"classes": set(), "partes": [], "tribunal": None, "cab": ""})
        top = max(evs, key=lambda e: (PESO[e["etapa"]], e["data"]))
        so_cliente = all(e["benef"].startswith("Cliente") for e in evs if e["etapa"] in
                         ("determinado", "expedido", "levantado"))
        tem_alvara = any(e["etapa"] in ("determinado", "expedido", "levantado") for e in evs)
        vals_alv = []
        for e in evs:
            if e["etapa"] in ("expedido", "levantado", "determinado", "deposito", "extinto_pago", "sisbajud_pos"):
                vals_alv += [v for v in e["valores"] if v not in vals_alv]
        benefs = {e["benef"] for e in evs}
        procs.append({
            "num": num, "cnj": gr.formatar_cnj(num), "tribunal": tribunal(num),
            "cliente": cliente_do_processo(u, reg, inf["partes"]),
            "fonte_custo": fonte_de_custo(num, u, reg, inf["classes"], inf["cab"]),
            "classe": (reg or {}).get("classe") or ", ".join(sorted(inf["classes"])),
            "vara": (reg or {}).get("vara", ""),
            "situacao": ROTULO[top["etapa"]], "peso": PESO[top["etapa"]], "data_situacao": top["data"],
            "primeiro": evs[0]["data"], "ultimo": evs[-1]["data"],
            "valores": vals_alv[:6],
            "beneficiario": ("Escritório (honorários)" if "Escritório (honorários)" in benefs else
                             "Cliente (não é do escritório)" if tem_alvara and so_cliente else "Conferir"),
            "na_lista": ", ".join(u["origens"]) if u else "— (só no Diário/e-SAJ)",
            "n_eventos": len(evs),
        })
    procs.sort(key=lambda p: (-p["peso"], p["data_situacao"]), reverse=False)
    procs.sort(key=lambda p: (-p["peso"], p["data_situacao"]))
    return procs, eventos, univ, esaj


# ───────────────────────────── planilha ───────────────────────────────────

def ler_controle_v2():
    import openpyxl
    out = {}
    if not CONTROLE_V2.exists():
        return out
    wb = openpyxl.load_workbook(CONTROLE_V2, read_only=True, data_only=True)
    for r in wb["Honorários"].iter_rows(min_row=5, values_only=True):
        if r[1] and r[2]:
            out.setdefault(gr.digitos(r[2]), {})["honor"] = {
                "situacao": r[16], "sucumb": r[8], "contrat": r[9], "data_pgto": r[11], "data_cred": r[12]}
    for r in wb["Recebidos"].iter_rows(min_row=5, values_only=True):
        if r[1] and r[3]:
            out.setdefault(gr.digitos(r[3]), {}).setdefault("receb", []).append(
                {"sucumb": r[8], "contrat": r[9], "data": r[12]})
    wb.close()
    return out


def _brl(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def gerar_planilha(procs, eventos, desde, casamentos=None, creditos=None, usados=None,
                   arquivos=None, ignorados=None, plataformas=None):
    casamentos = casamentos or {}
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    v2 = ler_controle_v2()
    MARROM, BEGE = "6C3813", "F4EDE4"
    cab_font = Font(bold=True, color="FFFFFF")
    cab_fill = PatternFill("solid", fgColor=MARROM)
    fino = Side(style="thin", color="D9CFC4")
    borda = Border(bottom=fino)
    cores = {"Extinto pelo pagamento": "D8EFD9", "Valor levantado/transferido": "D8EFD9",
             "Alvará expedido": "FFF2C7", "Alvará determinado": "FFF2C7",
             "Depósito/pagamento do devedor": "FCE3CF", "Sisbajud com bloqueio": "FCE3CF"}

    wb = openpyxl.Workbook()

    # ── Aba 1: processos
    ws = wb.active
    ws.title = "Alvarás por processo"
    ws["A1"] = "LEVANTAMENTO DE ALVARÁS E HONORÁRIOS — desde %s" % desde.strftime("%d/%m/%Y")
    ws["A1"].font = Font(bold=True, size=14, color=MARROM)
    ws["A2"] = ("Gerado em %s a partir do e-SAJ/TJAL, do Diário de Justiça (DJEN) e do Astrea. "
                "Colunas em amarelo-claro são para a equipe preencher. Situação = etapa mais avançada encontrada."
                % datetime.datetime.now().strftime("%d/%m/%Y %H:%M"))
    ws["A2"].font = Font(italic=True, color="666666")
    cols = ["Nº", "Cliente", "Processo", "Tribunal", "Fonte de custo", "Classe", "Vara",
            "Situação encontrada", "Data da situação", "Valores citados (R$)", "Beneficiário (pelo texto)",
            "Nº de atos", "Na planilha v2?", "Situação na v2", "Recebido na v2 (R$)",
            "Tipo de honorário", "Valor recebido (R$)", "Data do crédito", "Conta", "Conferido?", "Observações",
            "Está nas listas"]
    ws.append([])
    ws.append(cols)
    for c in range(1, len(cols) + 1):
        cel = ws.cell(row=4, column=c)
        cel.font, cel.fill = cab_font, cab_fill
        cel.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    ws.row_dimensions[4].height = 34
    manual = PatternFill("solid", fgColor="FFFBEA")
    for i, p in enumerate(procs, 1):
        x = v2.get(p["num"], {})
        hon = x.get("honor") or {}
        receb = sum((r.get("sucumb") or 0) + (r.get("contrat") or 0) for r in x.get("receb", [])
                    if isinstance(r.get("sucumb") or 0, (int, float)) and isinstance(r.get("contrat") or 0, (int, float)))
        cas = casamentos.get(p["num"], [])
        val_rec = sum(c["valor"] for c, _, _ in cas) or None
        data_rec = max((c["data"] for c, _, _ in cas), default=None)
        contas = ", ".join(sorted({"%s %s" % (c["banco"], c["conta"]) for c, _, _ in cas})) or None
        obs = " || ".join("%s: %s %s em %s, R$ %s — %s" % (nivel, c["banco"], c["conta"], c["data"].strftime("%d/%m/%Y"),
                                                         _brl(c["valor"]), regra) for c, regra, nivel in cas) or None
        ws.append([i, p["cliente"], p["cnj"], p["tribunal"], p["fonte_custo"], p["classe"], p["vara"],
                   p["situacao"], datetime.date.fromisoformat(p["data_situacao"]),
                   " | ".join(_brl(v) for v in p["valores"]),
                   p["beneficiario"], p["n_eventos"], "Sim" if x else "Não", hon.get("situacao") or "",
                   receb or None, None, val_rec, data_rec, contas, None, obs, p["na_lista"]])
        if cas:
            nivel = min((n for _, _, n in cas), key=["Confirmado", "Provável", "Conferir"].index)
            ws.cell(row=ws.max_row, column=17).fill = PatternFill(
                "solid", fgColor={"Confirmado": "C6E9C8", "Provável": "FFF2C7", "Conferir": "FCE3CF"}[nivel])
        r = ws.max_row
        ws.cell(row=r, column=9).number_format = "DD/MM/YYYY"
        ws.cell(row=r, column=15).number_format = '#,##0.00'
        ws.cell(row=r, column=17).number_format = '#,##0.00'
        ws.cell(row=r, column=18).number_format = "DD/MM/YYYY"
        if p["situacao"] in cores:
            ws.cell(row=r, column=8).fill = PatternFill("solid", fgColor=cores[p["situacao"]])
        for c in (16, 18, 19, 20, 21):
            ws.cell(row=r, column=c).fill = manual
        if not cas:
            ws.cell(row=r, column=17).fill = manual
        for c in range(1, len(cols) + 1):
            ws.cell(row=r, column=c).border = borda
            ws.cell(row=r, column=c).alignment = Alignment(vertical="top", wrap_text=c in (2, 6, 7, 10, 21, 22))
    larg = [5, 30, 27, 8, 18, 26, 22, 24, 12, 22, 22, 7, 9, 20, 13, 16, 14, 12, 18, 10, 30, 28]
    for c, w in enumerate(larg, 1):
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = "C5"
    ws.auto_filter.ref = "A4:%s%d" % (get_column_letter(len(cols)), ws.max_row)
    ult = max(ws.max_row, 5)
    for col, opts in [("P", '"Sucumbência,Contratual (êxito),Sucumbência + Contratual,Não é do escritório"'),
                      ("S", '"Santander PJ,Santander PF,C6 PJ,C6 PF,Mercado Pago PJ,Mercado Pago PF,'
                            'Sicredi PJ,Sicredi PF"'),
                      ("T", '"Sim,Não"')]:
        dv = DataValidation(type="list", formula1=opts, allow_blank=True)
        ws.add_data_validation(dv)
        dv.add("%s5:%s%d" % (col, col, ult + 200))

    # ── Aba 2: linha do tempo (todos os atos)
    w2 = wb.create_sheet("Linha do tempo")
    c2 = ["Processo", "Cliente", "Fonte de custo", "Data", "Etapa", "Valores citados (R$)", "Beneficiário",
          "Fonte", "Trecho", "Link"]
    w2.append(c2)
    for c in range(1, len(c2) + 1):
        w2.cell(row=1, column=c).font, w2.cell(row=1, column=c).fill = cab_font, cab_fill
    por_num = {p["num"]: p for p in procs}
    for p in procs:
        for e in eventos[p["num"]]:
            w2.append([p["cnj"], p["cliente"], p["fonte_custo"], datetime.date.fromisoformat(e["data"]),
                       ROTULO[e["etapa"]],
                       " | ".join(_brl(v) for v in e["valores"]),
                       e["benef"], e["fonte"], e["texto"][:1200], e["link"]])
            w2.cell(row=w2.max_row, column=4).number_format = "DD/MM/YYYY"
            w2.cell(row=w2.max_row, column=9).alignment = Alignment(wrap_text=True, vertical="top")
    for c, w in enumerate([27, 28, 18, 11, 24, 18, 22, 22, 90, 30], 1):
        w2.column_dimensions[get_column_letter(c)].width = w
    w2.freeze_panes = "B2"
    w2.auto_filter.ref = "A1:J%d" % w2.max_row

    # ── Abas dos extratos (quando o cruzamento rodou)
    if creditos is not None:
        dono = {}
        for num, lst in casamentos.items():
            for c, regra, nivel in lst:
                dono[id(c)] = (num, regra, nivel)
        por_num = {p["num"]: p for p in procs}
        w4 = wb.create_sheet("Créditos dos extratos")
        c4 = ["Data", "Banco", "Conta", "Valor (R$)", "Categoria", "Descrição no extrato", "Processo casado",
              "Cliente", "Fonte de custo", "Nível", "Regra", "Arquivo", "Possíveis processos (alvará 45 dias antes a 30 depois)"]

        def candidatos(c):
            out = []
            for n, evs in eventos.items():
                for e in evs:
                    d = (c["data"] - datetime.date.fromisoformat(e["data"])).days
                    if e["etapa"] in ("expedido", "levantado", "determinado", "extinto_pago") and -30 <= d <= 45:
                        p = por_num.get(n)
                        if p:
                            out.append("%s (%s, %s)" % (p["cliente"].split()[0] + " " + p["cliente"].split()[-1],
                                                        p["cnj"], gr.data_br(e["data"])))
                        break
            return "; ".join(sorted(set(out)))
        w4.append(c4)
        for c in range(1, len(c4) + 1):
            w4.cell(row=1, column=c).font, w4.cell(row=1, column=c).fill = cab_font, cab_fill
        cor_cat = {"Judicial": "FFF2C7", "Banco réu": "FCE3CF", "Pessoa": "FFFFFF", "Plataforma": "EAF1FB",
                   "Parceiro": "E8F5E9", "Processo": "FFF2C7", "Extrajudicial": "EDE7F6"}
        for c in creditos:
            if c["categoria"] in ("Interna", "Rendimento", "Pessoal"):
                continue
            num, regra, nivel = dono.get(id(c), (None, "", ""))
            if not regra and c.get("regra_manual"):
                regra, nivel = "Informado pela Caroline: " + c["regra_manual"].get("nota", ""), "Informado"
            p = por_num.get(num, {})
            w4.append([c["data"], c["banco"], c["conta"], c["valor"], c["categoria"], c["descricao"],
                       p.get("cnj", ""), p.get("cliente", ""), p.get("fonte_custo", ""), nivel or "Sem par",
                       regra, c["arquivo"], candidatos(c) if c["categoria"] == "Judicial" and not num else ""])
            r = w4.max_row
            w4.cell(row=r, column=1).number_format = "DD/MM/YYYY"
            w4.cell(row=r, column=4).number_format = "#,##0.00"
            w4.cell(row=r, column=5).fill = PatternFill("solid", fgColor=cor_cat.get(c["categoria"], "FFFFFF"))
        for c, w in enumerate([11, 13, 7, 13, 12, 50, 27, 28, 18, 11, 40, 30, 70], 1):
            w4.column_dimensions[get_column_letter(c)].width = w
        w4.freeze_panes = "A2"
        w4.auto_filter.ref = "A1:M%d" % w4.max_row

        w5 = wb.create_sheet("Extratos lidos")
        w5.append(["Arquivo", "Banco", "Conta", "De", "Até", "Lançamentos"])
        for c in range(1, 7):
            w5.cell(row=1, column=c).font, w5.cell(row=1, column=c).fill = cab_font, cab_fill
        for nome, inf in sorted((arquivos or {}).items()):
            w5.append([nome, inf["banco"], inf["conta"], inf["de"], inf["ate"], inf["lancamentos"]])
        for nome in ignorados or []:
            w5.append([nome, "NÃO LIDO"])
        w5.column_dimensions["A"].width = 60
        for col in "BCDEF":
            w5.column_dimensions[col].width = 14

    # ── Aba 3: resumo
    w3 = wb.create_sheet("Resumo", 0)
    w3["A1"] = "RESUMO — ALVARÁS E HONORÁRIOS desde %s" % desde.strftime("%d/%m/%Y")
    w3["A1"].font = Font(bold=True, size=14, color=MARROM)
    w3.append([])
    w3.append(["Situação encontrada", "Processos", "Busca e Apreensão", "Revisional", "Cível", "Outros"])
    for c in range(1, 7):
        w3.cell(row=3, column=c).font, w3.cell(row=3, column=c).fill = cab_font, cab_fill
    for cod, rot, _ in ETAPAS:
        ps = [p for p in procs if p["situacao"] == rot]
        def cnt(f):
            return sum(1 for p in ps if p["fonte_custo"].startswith(f))
        w3.append([rot, len(ps), cnt("Busca"), cnt("Revisional"), cnt("Cível"),
                   len(ps) - cnt("Busca") - cnt("Revisional") - cnt("Cível")])
    w3.append(["TOTAL", len(procs)])
    w3.cell(row=w3.max_row, column=1).font = Font(bold=True)
    w3.append([])
    w3.append(["Processos com alvará/pagamento e que NÃO estão na planilha v2:",
               sum(1 for p in procs if p["peso"] >= 3 and p["num"] not in v2)])
    w3.append(["Processos da v2 marcados como pagos/recebidos:", sum(1 for x in v2.values()
               if (x.get("honor") or {}).get("situacao") == "PAGO INTEGRAL" or x.get("receb"))])
    if creditos is not None:
        terc = [c for c in creditos if c["categoria"] not in ("Interna", "Rendimento", "Pessoal")]
        jud = [c for c in terc if c["categoria"] in ("Judicial", "Banco réu")]
        w3.append([])
        w3.append(["EXTRATOS"])
        w3.cell(row=w3.max_row, column=1).font = Font(bold=True, color=MARROM)
        w3.append(["Créditos de terceiros no período", len(terc), sum(c["valor"] for c in terc)])
        w3.append(["…dos quais judiciais ou de banco réu", len(jud), sum(c["valor"] for c in jud)])
        w3.append(["Créditos casados com um processo", len(usados or ()),
                   sum(c["valor"] for lst in casamentos.values() for c, _, _ in lst)])
        w3.append(["Créditos judiciais/banco réu SEM processo (conferir)",
                   sum(1 for c in jud if not any(c is x for l in casamentos.values() for x, _, _ in l)),
                   sum(c["valor"] for c in jud if not any(c is x for l in casamentos.values() for x, _, _ in l))])
        for r in range(w3.max_row - 3, w3.max_row + 1):
            w3.cell(row=r, column=3).number_format = "#,##0.00"
        anos = sorted({c["data"].year for c in terc})
        w3.append([])
        w3.append(["Créditos por categoria (R$)"] + [str(a) for a in anos])
        for c in range(1, len(anos) + 2):
            w3.cell(row=w3.max_row, column=c).font, w3.cell(row=w3.max_row, column=c).fill = cab_font, cab_fill
        for cat in ("Judicial", "Processo", "Banco réu", "Plataforma", "Extrajudicial", "Parceiro", "Pessoa",
                    "Não identificado"):
            w3.append([cat] + [sum(c["valor"] for c in terc if c["categoria"] == cat and c["data"].year == a)
                               for a in anos])
            for k in range(len(anos)):
                w3.cell(row=w3.max_row, column=k + 2).number_format = "#,##0.00"
        if plataformas:
            for rot, src in (("Asaas (parcelas e entradas)", "AS"), ("Conta Azul (boletos)", "CA")):
                w3.append([rot] + [sum(x["valor"] for x in plataformas if x["origem"] == src and
                                       x["data"].year == a) for a in anos])
                for k in range(len(anos)):
                    w3.cell(row=w3.max_row, column=k + 2).number_format = "#,##0.00"
            todas = [c for c in terc] + plataformas
            w3.append(["TOTAL RECEBIDO (extratos + plataformas)"] +
                      [sum(c["valor"] for c in todas if c["data"].year == a and
                           c.get("categoria") != "Não identificado") for a in anos])
            w3.cell(row=w3.max_row, column=1).font = Font(bold=True)
            for k in range(len(anos)):
                w3.cell(row=w3.max_row, column=k + 2).number_format = "#,##0.00"
                w3.cell(row=w3.max_row, column=k + 2).font = Font(bold=True)
            w3.append(["(sem os créditos não identificados; o Astrea/PJBank de 2025 já está em 'Plataforma', "
                       "pelo extrato do Santander PJ)"])
    if plataformas:
        w6 = wb.create_sheet("Asaas e Conta Azul")
        c6 = ["Data do pagamento", "Origem", "Cliente", "Valor (R$)", "Tipo", "Ação", "Forma", "Parcela"]
        w6.append(c6)
        for c in range(1, len(c6) + 1):
            w6.cell(row=1, column=c).font, w6.cell(row=1, column=c).fill = cab_font, cab_fill
        for x in sorted(plataformas, key=lambda x: x["data"]):
            w6.append([x["data"], {"AS": "Asaas", "CA": "Conta Azul"}[x["origem"]], x["cliente"], x["valor"],
                       x["tipo"], x["acao"], x["forma"], x["parcela"]])
            w6.cell(row=w6.max_row, column=1).number_format = "DD/MM/YYYY"
            w6.cell(row=w6.max_row, column=4).number_format = "#,##0.00"
        for c, w in enumerate([13, 11, 38, 12, 18, 16, 12, 9], 1):
            w6.column_dimensions[get_column_letter(c)].width = w
        w6.freeze_panes = "A2"
        w6.auto_filter.ref = "A1:H%d" % w6.max_row
    w3.append([])
    w3.append(["Como ler"])
    w3.cell(row=w3.max_row, column=1).font = Font(bold=True, color=MARROM)
    for t in [
        "• Situação = a etapa mais avançada achada nos autos desde %s." % desde.strftime("%d/%m/%Y"),
        "• 'Valores citados' são os R$ que aparecem perto da palavra alvará/levantamento/depósito no texto. "
        "Podem incluir o valor da causa ou da condenação: confira na Linha do tempo.",
        "• Beneficiário 'Escritório' = o texto fala em honorários, advogada ou sucumbência. "
        "'Cliente' = depósito de parcelas/consignação (não entra no caixa do escritório).",
        "• O cruzamento com os extratos (Santander, C6, Mercado Pago e Sicredi) preenche as colunas "
        "Valor recebido, Data do crédito e Conta.",
        "• Processos fora do TJAL dependem do Diário e do Astrea: atos sem publicação podem não aparecer.",
    ]:
        w3.append([t])
    w3.column_dimensions["A"].width = 70
    for c in "BCDEF":
        w3.column_dimensions[c].width = 16

    SAIDA.mkdir(parents=True, exist_ok=True)
    destino = SAIDA / ("ALVARÁS %d-%d - LEVANTAMENTO.xlsx" % (desde.year, datetime.date.today().year))
    wb.save(destino)
    return destino


# ─────────────────────────────── main ─────────────────────────────────────

def coletar(desde):
    print("1/3  Montando a lista de processos...", flush=True)
    univ = montar_universo()
    print("     %d processos nas listas" % len(univ), flush=True)
    print("2/3  Diário (DJEN) desde %s..." % desde, flush=True)
    djen = baixar_djen(desde)
    for itens in djen.values():
        for it in itens:
            _add(univ, it["numero"], None, "Diário")
    salvar("universo.json", univ)
    tjal = sorted(n for n in univ if gr.tem_esaj(n))
    print("3/3  e-SAJ: %d processos do TJAL (com incidentes)..." % len(tjal), flush=True)
    baixar_esaj(tjal)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("etapa", nargs="?", default="tudo", choices=["coletar", "analisar", "tudo"])
    ap.add_argument("--desde", default="2025-01-01")
    a = ap.parse_args()
    desde = datetime.date.fromisoformat(a.desde)
    if a.etapa in ("coletar", "tudo"):
        coletar(desde)
    if a.etapa in ("analisar", "tudo"):
        procs, eventos, _, _ = analisar(desde)
        destino = gerar_planilha(procs, eventos, desde)
        print("Planilha: %s  (%d processos com movimento de valores)" % (destino, len(procs)))


if __name__ == "__main__":
    main()
