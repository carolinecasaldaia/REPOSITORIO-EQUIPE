#!/usr/bin/env python3
"""Relatórios mensais aos clientes — um PDF por cliente, a partir da RODAGEM.

De onde vem cada coisa:

  QUEM RECEBE  — a RODAGEM PROCESSUAL (uma aba por estado). Cliente novo lançado
                 na rodagem entra sozinho no relatório do mês seguinte; não existe
                 outra lista para manter.
  O QUE HOUVE  — o DJEN (API Comunica do CNJ), consultado pelas OABs da Dra.
                 Caroline. Uma consulta por OAB traz todas as intimações do mês,
                 de qualquer tribunal, com o texto integral. D+1, sem captcha.
  TELEFONE     — CONTATOS DOS CLIENTES.xlsx, que a automação mantém: acrescenta os
                 clientes novos e puxa o telefone do Cadastro Astrea quando existe.

Por que não o DataJud: em 30/09/2026 ele devolveu 429 em 1 de cada 3 consultas
e levou 4 minutos para 15 processos, além de ter 2 semanas a 2 meses de atraso.
Rotina mensal de dois cliques não pode depender dele.

Casamento publicação → cliente: primeiro pelo número do processo; se não bater
(recurso no Tribunal nasce com número novo), pelo nome completo do cliente entre
as partes. O casamento por nome sempre pede conferência.

Nada vai para o cliente sem passar pela Eduarda: sentença, acórdão, liminar,
audiência, custas e tudo que o classificador não reconhece saem marcados como
CONFERIR na planilha de controle.
"""
import argparse
import datetime
import hashlib
import html
import json
import re
import sqlite3
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PASTA = Path(__file__).resolve().parent
RODAGEM_DIR = PASTA.parent
TIMBRE = PASTA / "timbre"
CONTATOS = PASTA / "CONTATOS DOS CLIENTES.xlsx"
ASTREA_DB = Path.home() / ".cadastro-astrea" / "controle.sqlite3"

# OABs da Dra. Caroline (procuração-modelo do GERADOR CONTRATOS).
OABS = [("15766", "AL"), ("528725", "SP"), ("70091", "PE")]
DJEN = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
DJEN_PAUSA = 7          # 10/min é o ritmo que o RADAR B&A mediu como seguro
WHATSAPP_ESCRITORIO = "(82) 99604-7676"     # WhatsApp do jurídico

MARROM = "#6C3813"
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]

CNJ = re.compile(r"\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}")


# ─────────────────────────── utilidades ────────────────────────────

def digitos(s):
    return re.sub(r"\D", "", str(s or ""))


def sem_acento(s):
    t = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in t if not unicodedata.combining(c))


def norm(s):
    """Maiúsculo, sem acento, só letras e espaços — para comparar nomes."""
    t = sem_acento(s).upper()
    return " ".join(re.sub(r"[^A-Z ]", " ", t).split())


def norm_texto(s):
    return " ".join(sem_acento(s).upper().split())


def limpar_html(t):
    t = re.sub(r"(?is)<style.*?</style>", " ", t or "")
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"body\{[^}]*\}|#div\w+\{[^}]*\}", " ", t)
    return " ".join(t.split())


_MINUSCULAS = {"da", "de", "do", "das", "dos", "e", "a", "o", "em"}


def nome_bonito(s):
    palavras = " ".join(str(s or "").replace("\t", " ").split()).lower().split()
    out = []
    for i, p in enumerate(palavras):
        if i and p in _MINUSCULAS:
            out.append(p)
        elif p in ("s/a", "s.a", "s.a.", "sa"):
            out.append("S/A")
        else:
            out.append(p[:1].upper() + p[1:])
    return " ".join(out)


def cpf_valido(s):
    d = digitos(s)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if (soma * 10 % 11) % 10 != int(d[n]):
            return False
    return True


def formatar_cnj(d):
    d = digitos(d)
    if len(d) != 20:
        return d
    return "%s-%s.%s.%s.%s.%s" % (d[:7], d[7:9], d[9:13], d[13], d[14:16], d[16:])


def data_br(iso):
    try:
        return datetime.date.fromisoformat(str(iso)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(iso)


def rotulo_mes(ano, mes):
    return "%s %d" % (MESES[mes - 1].upper(), ano)


# ─────────────────────────── RODAGEM ───────────────────────────────

def localizar_rodagem():
    """A planilha do ano mais recente (RODAGEM PROCESSUAL 2026.xlsx, 2027...)."""
    cands = [p for p in RODAGEM_DIR.glob("RODAGEM PROCESSUAL*.xlsx")
             if not p.name.startswith("~$")]
    if not cands:
        raise SystemExit("Não achei a RODAGEM PROCESSUAL em %s" % RODAGEM_DIR)
    return max(cands, key=lambda p: (re.findall(r"20\d\d", p.name) or ["0"])[-1])


def _rot(v):
    t = norm_texto(v).replace("º", "").replace("°", "").replace(".", " ")
    return " ".join(t.split())


def _sim(v):
    t = norm_texto(v)
    return bool(t) and t not in ("NAO", "N", "NONE", "0", "0.0")


def ler_rodagem(caminho):
    """Devolve {chave: cliente}. Chave = CPF (dígitos) ou, sem CPF, o nome."""
    import openpyxl
    wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    clientes = {}
    sem_processo = []
    for ws in wb.worksheets:
        linhas = list(ws.iter_rows(values_only=True))
        cab = None
        for i, r in enumerate(linhas[:30]):
            if any(_rot(c) == "NOME" for c in r):
                cab = i
                break
        if cab is None:
            continue
        rot = [_rot(c) for c in linhas[cab]]

        def col(*nomes):
            for n in nomes:
                if n in rot:
                    return rot.index(n)
            return None

        c_nome = col("NOME")
        c_cpf = col("CPF")
        c_proc = col("N PROCESSO", "NO PROCESSO")
        c_rev = col("REVISIONAL")
        c_busca = col("BUSCA")
        c_sec = col("N PROC BUSCA/ESPEC", "N PROC BUSCA ESPEC", "ESPECIFICIDADE")
        c_desp = col("DESPACHO")
        c_sit = col("SITUACAO")
        c_obs = col("OBSERVACAO")
        c_ent = col("DATA (ENTRADA)")

        for r in linhas[cab + 1:]:
            def v(j):
                return r[j] if j is not None and j < len(r) else None
            nome = " ".join(str(v(c_nome) or "").split())
            if not nome:
                continue
            # CPF: pela coluna; se não validar, procura na linha (abas com
            # cabeçalho desalinhado, como MARANHÃO e AMAPÁ).
            cpf = digitos(v(c_cpf)) if cpf_valido(v(c_cpf)) else ""
            if not cpf:
                for x in r:
                    if cpf_valido(x) and not CNJ.search(str(x)):
                        cpf = digitos(x)
                        break
            principal = CNJ.findall(str(v(c_proc) or ""))
            secundario = CNJ.findall(str(v(c_sec) or ""))
            if not principal and not secundario:
                # número pode estar em outra coluna quando o cabeçalho desalinha
                for x in r:
                    principal += CNJ.findall(str(x or ""))
            rev, busca = _sim(v(c_rev)), _sim(v(c_busca))

            chave = cpf or norm(nome)
            cli = clientes.get(chave)
            if cli is None:
                cli = clientes[chave] = {
                    "chave": chave, "nome": nome_bonito(nome), "cpf": cpf,
                    "abas": [], "processos": {}, "entrada": None,
                }
            if ws.title not in cli["abas"]:
                cli["abas"].append(ws.title)
            ent = v(c_ent)
            if isinstance(ent, datetime.datetime):
                cli["entrada"] = min(filter(None, [cli["entrada"], ent.date()]))
            info = {
                "despacho": norm_texto(v(c_desp)),
                "situacao": norm_texto(v(c_sit)),
                "observacao": " ".join(str(v(c_obs) or "").split()),
            }
            for n in principal:
                tipo = "revisional" if rev or not busca else "busca"
                cli["processos"].setdefault(digitos(n), dict(info, tipo=tipo, origem="rodagem"))
            # A coluna "Nº PROC. BUSCA/ESPEC." às vezes traz um rótulo antes do número:
            # "Carta precatória nº ..." (pedido a outra comarca, parte do MESMO processo) ou
            # "AP. ..." (processo apensado). Caso real da Gisele, 02/10/2026: a precatória
            # virou uma "segunda ação de busca" no relatório. Sem rótulo = a ação de busca.
            texto_sec = norm_texto(v(c_sec))
            pai = digitos(principal[0]) if principal else None
            for n in secundario:
                if re.search(r"PRECAT", texto_sec) and pai:
                    cli["processos"].setdefault(digitos(n), dict(info, tipo="precatoria", pai=pai,
                                                                 origem="rodagem"))
                elif re.search(r"\bAP\b|APENS", texto_sec):
                    cli["processos"].setdefault(digitos(n), {"tipo": "apenso", "origem": "rodagem",
                                                             "despacho": "", "situacao": "", "observacao": ""})
                else:
                    cli["processos"].setdefault(digitos(n), dict(info, tipo="busca" if busca else "outro",
                                                                 origem="rodagem"))
            if not cli["processos"]:
                sem_processo.append({"nome": cli["nome"], "aba": ws.title})
    wb.close()
    return clientes, sem_processo


# ─────────────────────────── DJEN ──────────────────────────────────

def _get_json(url, tentativas=7):
    espera = 15
    for t in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "relatorios-clientes/1.0"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            # 429 = excesso; 500 "sistema muito ocupado" = o DJEN pedindo calma
            if e.code not in (429, 500, 502, 503, 504) or t == tentativas - 1:
                raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if t == tentativas - 1:
                raise
        print("   o DJEN pediu uma pausa, aguardando %ds..." % espera, flush=True)
        time.sleep(espera)
        espera = min(espera * 2, 120)


def baixar_djen(inicio, fim):
    """Todas as comunicações do período para as OABs do escritório."""
    vistos = {}
    for oab, uf in OABS:
        pagina = 1
        while True:
            q = urllib.parse.urlencode({
                "numeroOab": oab, "ufOab": uf,
                "dataDisponibilizacaoInicio": inicio.isoformat(),
                "dataDisponibilizacaoFim": fim.isoformat(),
                "itensPorPagina": 100, "pagina": pagina,
            })
            d = _get_json(DJEN + "?" + q)
            itens = d.get("items") or []
            for it in itens:
                vistos[str(it.get("id"))] = it
            print("   OAB %s/%s — página %d: %d publicações" % (oab, uf, pagina, len(itens)),
                  flush=True)
            time.sleep(DJEN_PAUSA)
            if len(itens) < 100:
                break
            pagina += 1
    # a mesma decisão costuma sair em mais de uma OAB/tribunal: dedup pelo teor
    unicos = {}
    for it in vistos.values():
        k = (digitos(it.get("numero_processo")), it.get("data_disponibilizacao"),
             hashlib.md5(limpar_html(it.get("texto"))[:4000].encode()).hexdigest())
        unicos.setdefault(k, it)
    return list(unicos.values())


# ─────────────────────────── e-SAJ (TJAL) ──────────────────────────
# O DJEN só traz o que gera intimação. Contestação do banco, petições, conclusão ao
# juiz, mandados — nada disso sai no Diário. Caso real (01/10/2026): o relatório
# do Abraão dizia "sem publicação" num mês em que o banco juntou petição (22/09).
# A consulta pública de 1º grau do TJAL mostra a movimentação completa, sem login e
# sem captcha, e cobre ~80% da carteira.
#
# Armadilha medida: com 3 consultas simultâneas, metade volta como página de
# gateway SEM movimentações. Por isso: no máximo 2 em paralelo, sessão nova por
# processo, e página sem "Distribuição" conta como falha e é repetida.

ESAJ_BASES = {"02": "https://www2.tjal.jus.br"}     # TJSP: acervo já migrou para o eproc


def tem_esaj(numero):
    d = digitos(numero)
    return len(d) == 20 and d[13] == "8" and d[14:16] in ESAJ_BASES and d[16:] != "0000"


def _esaj_uma(numero):
    import http.cookiejar
    base = ESAJ_BASES[numero[14:16]]
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    op.addheaders = [("User-Agent", "Mozilla/5.0")]
    op.open(base + "/cpopg/open.do", timeout=60).read()
    time.sleep(1.2)
    fmt = formatar_cnj(numero)
    q = urllib.parse.urlencode({
        "conversationId": "", "cbPesquisa": "NUMPROC", "dadosConsulta.tipoNuProcesso": "UNIFICADO",
        "numeroDigitoAnoUnificado": fmt[:15], "foroNumeroUnificado": numero[16:],
        "dadosConsulta.valorConsultaNuUnificado": fmt, "dadosConsulta.valorConsulta": "",
        "dadosConsulta.localPesquisa.cdLocal": "-1"})
    h = op.open(base + "/cpopg/search.do?" + q, timeout=60).read().decode("utf-8", "ignore")
    if re.search(r"segredo de justi|senha do processo", h, re.I) and "Distribuição" not in h:
        return {"ok": True, "segredo": True, "movs": []}
    movs, vistos = [], set()
    for r in re.findall(r'<tr class="[^"]*containerMovimentacao[^"]*".*?</tr>', h, re.S):
        tds = [" ".join(html.unescape(re.sub("<[^>]+>", " ", x)).split())
               for x in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
        if len(tds) < 2 or not re.match(r"\d\d/\d\d/\d{4}", tds[0]):
            continue
        chave = (tds[0], tds[-1][:200])
        if chave in vistos:          # a página repete as últimas 5 na tabela completa
            continue
        vistos.add(chave)
        movs.append([datetime.datetime.strptime(tds[0][:10], "%d/%m/%Y").date().isoformat(), tds[-1]])
    ok = bool(movs) or "Distribuição" in h
    return {"ok": ok, "segredo": False, "movs": movs}


def baixar_esaj(numeros, cache_path, reconsultar):
    from concurrent.futures import ThreadPoolExecutor
    cache = {}
    if cache_path.exists() and not reconsultar:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    faltam = [n for n in numeros if not (cache.get(n) or {}).get("ok")]
    if not faltam:
        return cache
    print("   consultando %d processos no e-SAJ do TJAL (leva alguns minutos)..." % len(faltam), flush=True)

    def tentar(n):
        for t in range(3):
            try:
                r = _esaj_uma(n)
                if r["ok"]:
                    return n, r
            except Exception:
                pass
            time.sleep(3 * (t + 1))
        return n, {"ok": False, "segredo": False, "movs": []}

    feitos = 0
    with ThreadPoolExecutor(2) as ex:
        for n, r in ex.map(tentar, faltam):
            cache[n] = r
            feitos += 1
            if feitos % 50 == 0:
                print("   %d/%d" % (feitos, len(faltam)), flush=True)
                cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    falhas = sum(1 for n in numeros if not cache[n]["ok"])
    if falhas:
        print("   ⚠ %d processo(s) não responderam no e-SAJ — rode de novo (opção 1) para tentar só esses."
              % falhas)
    return cache


def traduzir_movimento(texto, tipo):
    """Movimentação do e-SAJ → (frase, motivo_conferir, eh_decisao) ou None (ignorar).

    eh_decisao=True: o teor também sai no DJEN; se houver publicação perto, a do
    DJEN prevalece (é o texto oficial e evita repetir o mesmo fato)."""
    t = norm_texto(texto)
    busca = tipo == "busca"

    if re.match(r"(ATO PUBLICADO|DISPONIBILIZACAO NO DIARIO|CERTIDAO|APENSADO|PROCESSO RECEBIDO|"
                r"RECEBIMENTO|DEVOLVIDO CJU|REALIZADO CALCULO|REMESSA A CJU|MANDADO RECEBIDO|"
                r"EXPEDICAO DE CERTIDAO|EVOLUIDA A CLASSE|DESAPENSADO)", t):
        return None
    tipo_pet = re.search(r"TIPO DA PETICAO: (.+?)(?: DATA:|$)", t)
    tipo_pet = tipo_pet.group(1) if tipo_pet else ""
    if t.startswith("JUNTADA"):
        if re.search(r"CONTRA ?RAZ", t):
            return ("Foram apresentadas as respostas ao recurso (contrarrazões).", None, False)
        if "COMUNICACAO DE DECISAO" in tipo_pet:
            return ("O Tribunal comunicou ao juiz uma decisão tomada no recurso.", None, False)
        if "CONTESTACAO" in tipo_pet:
            return (("Apresentamos a sua defesa (contestação) na ação do banco." if busca else
                     "O banco apresentou sua defesa (contestação) no processo."), None, False)
        if re.search(r"REPLICA|IMPUGNACAO", tipo_pet):
            return (("O banco respondeu à defesa que apresentamos." if busca else
                     "Apresentamos a nossa resposta à defesa do banco (réplica)."), None, False)
        if "MANIFESTACAO DO AUTOR" in tipo_pet or "MANIFESTACAO DO REU" in tipo_pet:
            autor = "MANIFESTACAO DO AUTOR" in tipo_pet
            quem = ("o banco" if autor else "nós") if busca else ("nós" if autor else "o banco")
            return (("Apresentamos uma manifestação no processo." if quem == "nós" else
                     "O banco apresentou uma manifestação no processo."), None, False)
        if t.startswith("JUNTADA DE RECURSO") or re.search(r"APELACAO|EMBARGOS|AGRAVO", tipo_pet):
            return ("Foi apresentado recurso no processo.", None, False)
        if t.startswith("JUNTADA DE PETICAO") or tipo_pet:
            return ("Foi juntada uma petição ao processo. Nossa equipe acompanha o conteúdo.", None, False)
        return None
    if t.startswith("CONCLUSO PARA SENTENCA"):
        return ("O processo está pronto para julgamento e foi enviado ao juiz para a sentença.", None, False)
    if t.startswith("CONCLUSO PARA DECISAO"):
        return ("O processo foi enviado ao juiz para decisão.", None, False)
    if t.startswith("CONCLUSO"):
        return ("O processo foi enviado ao juiz para dar andamento.", None, False)
    if t.startswith("DISTRIBUID"):
        return ("A ação foi distribuída, ou seja, registrada oficialmente na Justiça.", None, False)
    if t.startswith("REMETIDO RECURSO") or "REMESSA AO TRIBUNAL" in t[:80]:
        return ("O processo foi enviado ao Tribunal para o julgamento do recurso.", None, False)
    if t.startswith("COMUNICACAO DE JULGAMENTO DO RECURSO"):
        return ("Chegou ao processo a comunicação de que o Tribunal julgou um recurso ligado a ele. "
                "Nossa equipe vai explicar o resultado.", "JULGAMENTO DE RECURSO", False)
    if t.startswith("INFORMACAO DE CADASTRO DE ORIGINARIO"):
        return ("Foi registrado um recurso no Tribunal ligado a este processo.", None, False)
    if re.match(r"(PROCESSO ENCAMINHADO PARA REDISTRIBUICAO|PROCESSO TRANSFERIDO|REMESSA PARA O CEJUSC|"
                r"REDISTRIBU)", t):
        if re.search(r"CEJUSC|CJUS|CONCILIA", t):
            return ("O processo foi enviado ao setor de conciliação do Tribunal.", None, False)
        return ("O processo foi transferido para outra vara.", None, False)
    if t.startswith("CARTA EXPEDIDA") and "CITACAO" in t[:120]:
        return (("Foi expedida a carta de citação." if busca else
                 "Foi enviada a carta de citação ao banco, para que ele se defenda."), None, False)
    if t.startswith("MANDADO EXPEDIDO"):
        return (("Foi expedido mandado no processo (ordem cumprida por oficial de justiça)."),
                "MANDADO" if busca else None, False)
    if t.startswith("MANDADO DEVOLVIDO NAO CUMPRIDO"):
        return ("O oficial de justiça devolveu o mandado sem conseguir cumpri-lo.", None, False)
    if t.startswith("MANDADO DEVOLVIDO CUMPRIDO"):
        return ("O oficial de justiça cumpriu o mandado.", "MANDADO CUMPRIDO" if busca else None, False)
    if t.startswith("AUDIENCIA REALIZADA"):
        return ("Foi realizada a audiência.", None, False)
    if t.startswith("AUDIENCIA") and _achar_data(t):
        return ("Foi marcada audiência para %s." % _achar_data(t), "AUDIÊNCIA", False)
    if t.startswith("TRANSITADO EM JULGADO"):
        return ("A decisão do processo se tornou definitiva (trânsito em julgado).", "TRÂNSITO", False)
    if re.match(r"ARQUIVADO DEFINITIVAMENTE|BAIXA DEFINITIVA", t):
        return ("O processo foi arquivado.", "ARQUIVAMENTO", False)
    if t.startswith("RECURSO INTERPOSTO"):
        if "EMBARGOS DE DECLARACAO" in t:
            return ("Houve um pedido de esclarecimento sobre uma decisão (embargos de declaração), "
                    "que será analisado.", None, False)
        return ("Foi apresentado recurso no processo.", None, False)
    if re.match(r"(DECISAO|DESPACHO|SENTENCA|JULGAD|CONCEDIDA|NAO CONCEDIDA|INDEFERID|DEFERID|EMBARGOS|"
                r"HOMOLOGAD|EXTINT|ATO ORDINATORIO|PROFERIDO)", t):
        return ("", None, True)               # teor: classificado como publicação
    return None


# ─────────────────────────── Astrea (fora do TJAL) ─────────────────
# Andamentos de PJe/eproc/Projudi lidos pela tela do Astrea com a conta "Claude"
# (ler_astrea.py, rodado com o Python do Cadastro Astrea). Aqui só traduzimos.
#
# O histórico do Astrea mistura quatro coisas. Só duas vão ao cliente:
#   andamento do tribunal       -> traduzido como o e-SAJ
#   "Prazo concluído | X - Realizado" -> peça da equipe, SÓ se X estiver na lista
#   tarefas internas            -> NUNCA (há "COBRAR HONORÁRIOS" no meio)
#   publicações (clipping)      -> ignoradas: já vêm do DJEN com o texto oficial

ASTREA_PY = Path.home() / ".cadastro-astrea" / "venv" / "bin" / "python"

_EQUIPE = [
    (r"^REPLICA|IMPUGNACAO A CONTESTACAO", "Nossa equipe protocolou a réplica, que é a nossa resposta à defesa do banco."),
    (r"^CONTESTACAO|^DEFESA", "Nossa equipe protocolou a sua defesa (contestação)."),
    (r"^APELACAO", "Nossa equipe protocolou recurso de apelação contra a sentença."),
    (r"^AGRAVO", "Nossa equipe protocolou recurso (agravo) no Tribunal."),
    (r"^RECURSO ESPECIAL|^RESP\b", "Nossa equipe protocolou recurso especial, que vai ao Superior Tribunal de "
                                   "Justiça (STJ)."),
    (r"^EMBARGOS", "Nossa equipe protocolou embargos de declaração (pedido de esclarecimento de uma decisão)."),
    (r"^CONTRA ?-?R?RAZ", "Nossa equipe respondeu ao recurso do banco (contrarrazões)."),
    (r"PROVAS", "Nossa equipe se manifestou sobre as provas do processo."),
    (r"^EMENDA", "Nossa equipe fez o complemento pedido pelo juiz (emenda)."),
    (r"^JUNTA(R|DA) (DE )?DOCUMENT", "Nossa equipe juntou documentos ao processo."),
    (r"^MANIFESTACAO", "Nossa equipe apresentou uma manifestação no processo."),
    (r"(SOLICIT|REQUER)\w* (DE |A )?DOCUMENT", "Pedimos a você documentos necessários para o processo."),
    (r"(JUNTAR|COMPROVA\w*)[^|]{0,30}HIPOSSUFICI|DOCUMENTOS DE HIPO",
     "Nossa equipe juntou os documentos que comprovam o seu direito à justiça gratuita."),
    (r"^(PETICAO INICIAL|AJUIZAMENTO|PROTOCOLO DA INICIAL)", "Nossa equipe protocolou a ação."),
]


def _astrea_tribunal(texto):
    """Andamento do Astrea -> texto no formato que traduzir_movimento entende."""
    linhas = [l.strip() for l in texto.split("\n") if l.strip()]
    t = norm_texto(linhas[0]) if linhas else ""
    ev = re.search(r"\bEVENTO:\s*(.+?)(?: MOVIMENTADO POR|/|$)", norm_texto(texto))
    if t.startswith("SEQ") and ev:                  # Projudi: "Seq.: 66 / Evento: JUNTADA DE ..."
        t = ev.group(1).strip()
    if re.match(r"(ASSISTENCIA JUDICIARIA|JUSTICA GRATUITA|GRATUIDADE)", t):
        return "DECISAO " + norm_texto(texto)
    m = re.match(r"JUNTADA DE PETICAO DE (.+)", t)
    if m:
        return "JUNTADA DE PETICAO TIPO DA PETICAO: " + m.group(1)
    if re.match(r"CONCLUSOS? PARA (JULGAMENTO|SENTENCA)", t):
        return "CONCLUSO PARA SENTENCA"
    if re.match(r"CONCLUSOS? PARA DECIS", t):
        return "CONCLUSO PARA DECISAO"
    if re.match(r"CONCLUSOS?\b", t):
        return "CONCLUSO PARA DESPACHO"
    if re.search(r"EXPEDICAO DE CITACAO|CITACAO EXPEDIDA|EXPEDIDA A? ?CITACAO|CARTA DE CITACAO", t):
        return "CARTA EXPEDIDA CITACAO"
    if re.search(r"EXPEDICAO DE MANDADO|MANDADO EXPEDIDO", t):
        return "MANDADO EXPEDIDO"
    if t.startswith("MANDADO DEVOLVIDO"):
        return t
    if t.startswith("REMETIDOS OS AUTOS") and re.search(r"RECURSO|INSTANCIA SUPERIOR|TRIBUNAL", t):
        return "REMETIDO RECURSO"
    if re.match(r"BAIXA DEFINITIVA|ARQUIVADO", t):
        return "ARQUIVADO DEFINITIVAMENTE"
    if t.startswith("TRANSITADO"):
        return "TRANSITADO EM JULGADO"
    if "COMUNICACAO ELETRONICA RECEBIDA" in t and "JULGADO" in t:
        return "COMUNICACAO DE JULGAMENTO DO RECURSO"
    if t.startswith("AUDIENCIA") and re.search(r"DESIGNAD|REDESIGNAD|MARCAD", t):
        return t
    if re.match(r"(PROFERID|DECISAO|DESPACHO|SENTENCA|JULGAD|CONCEDID|NAO CONCEDID|INDEFERID|DEFERID|"
                r"HOMOLOGAD|EXTINT|EMBARGOS DE DECLARACAO)", t):
        return "DECISAO " + norm_texto(texto)
    return None


def converter_astrea(reg):
    """Registro do ler_astrea.py -> mesmo formato do e-SAJ, mais as peças da equipe."""
    if not reg or not reg.get("achou"):
        return {"ok": False, "fonte": "astrea", "achou": False, "movs": [], "equipe": []}
    movs, equipe = [], []
    for iso, texto in reg.get("itens", []):
        linhas = [l.strip() for l in texto.split("\n") if l.strip()]
        if not linhas:
            continue
        t0 = norm_texto(linhas[0])
        if t0.startswith(("PRAZO CONCLUIDO", "TAREFA CONCLUIDA")):
            m = re.search(r"\|\s*(.+?)\s*(?:-\s*REALIZADO|$)", t0)
            if t0.startswith("TAREFA CONCLUIDA") and not m and len(linhas) > 1:
                m = re.match(r"(.+)", norm_texto(linhas[1]))
            if m and re.search(r"HONORARI|PAGAMENTO|COBRA|FINANCEIR|BOLETO|ASAAS|CONTA AZUL|COMPROVANTE HO",
                               norm_texto(texto)):
                m = None                            # financeiro: nunca vai ao cliente
            if m:
                frase = next((f for padrao, f in _EQUIPE if re.search(padrao, m.group(1))), None)
                if frase:
                    equipe.append([iso, frase])
            continue
        if re.match(r"(TAREFA|PUBLICACAO|PRAZO|COMPROMISSO|EVENTO|LEMBRETE)", t0):
            continue                               # interno ou clipping
        convertido = _astrea_tribunal(texto)
        if convertido:
            movs.append([iso, convertido])
    return {"ok": True, "fonte": "astrea", "achou": True, "movs": movs, "equipe": equipe}


def baixar_astrea(numeros, dados, reconsultar):
    """Roda o ler_astrea.py com o Python do Cadastro Astrea. Falha não para o relatório."""
    import subprocess
    cache = dados / "astrea.json"
    if cache.exists() and not reconsultar:
        return json.loads(cache.read_text(encoding="utf-8"))
    if not ASTREA_PY.exists():
        print("   ⚠ Cadastro Astrea não instalado nesta máquina — processos fora do TJAL só pelo Diário.")
        return {}
    entrada = dados / "astrea_entrada.json"
    entrada.write_text(json.dumps(numeros), encoding="utf-8")
    print("   lendo %d processos no Astrea pela tela (cerca de 15 a 25 minutos)..." % len(numeros), flush=True)
    r = subprocess.run([str(ASTREA_PY), str(PASTA / "ler_astrea.py"), str(entrada), str(cache)])
    if r.returncode != 0 or not cache.exists():
        print("   ⚠ Não consegui ler o Astrea (sessão caída ou ocupado). Os processos fora do TJAL "
              "saem só com o Diário. Rode de novo depois.")
        return {}
    return json.loads(cache.read_text(encoding="utf-8"))


# ─────────────────────────── diligências (Astrea) ──────────────────
# Diligência = contato da equipe com a vara/cartório (presencial, balcão virtual,
# telefone, despacho com o juiz), registrada como TAREFA no Astrea. O que aconteceu
# fica nos COMENTÁRIOS da tarefa (pedido da Caroline, 01/10/2026). Os comentários
# misturam o relato com anotações internas — horário de funcionamento da vara,
# telefones —, que NUNCA vão ao cliente. Só entra o comentário que relata a
# diligência, reescrito em linguagem simples, e sempre marcado para conferir.

TAREFA_DILIGENCIA = re.compile(r"DILIG|LIGAR (NO|PARA)|BALC[AÃ]O|DESPACHAR|DESPACHO (COM|VIRTUAL)|CONTATO COM (A )?"
                               r"(VARA|CART|SECRETARIA)", re.I)

_COMENT = re.compile(r"(?P<autor>[^\n]+)\n(?P<data>\d\d/\d\d/\d{4}) às (?P<hora>\d\d:\d\d)\n+(?P<txt>.*?)"
                     r"(?=\n[^\n]+\n\d\d/\d\d/\d{4} às \d\d:\d\d|\n\s*COMENTAR|\Z)", re.S)

_JARGAO = [(r"(colocad[oa]|deixad[oa]|posto|feito|ficar)\s+concluso", "enviado ao juiz"),
           (r"(colocar|deixar|fazer)\s+concluso", "enviar ao juiz"),
           (r"concluso para decis[aã]o", "com o juiz para decisão"),
           (r"concluso para despacho", "com o juiz"),
           (r"concluso para senten[cç]a", "com o juiz para a sentença"),
           (r"\bconclusos?\b", "com o juiz"),
           (r"\bdespachar\b", "conversar com o juiz")]
# recado interno da equipe que às vezes vem no mesmo comentário: corta daqui em diante
_RECADO_INTERNO = re.compile(r"[,.;!]?\s*(remanejar|reagendar|acompanhar|lembrar|cobrar novamente|verificar|"
                             r"retornar|voltar a ligar|ligar novamente)\b.*$", re.I | re.S)
# só conta o que foi FEITO (não "DILIGENCIAR X", que é o plano da tarefa)
_FEITO = re.compile(r"DILIGENCIAD|DILIGENCIANDO|DILIGENCIA (PRESENCIAL )?REALIZAD|REALIZAD|INFORMOU|INFORMAD|"
                    r"INFORMARAM|ATENDID|DESPACHAD|DESPACHEI|FALEI|FALAMOS|LIGUEI|LIGAMOS|ENCAMINHAD")


def comentarios_da_tarefa(painel):
    """Texto do painel da tarefa -> [(data_iso, hora, autor, texto)]."""
    i = painel.find("Histórico de alterações")
    corpo = painel[i + len("Histórico de alterações"):] if i >= 0 else painel
    out = []
    for m in _COMENT.finditer(corpo):
        d, mth, a = m.group("data").split("/")
        out.append(("%s-%s-%s" % (a, mth, d), m.group("hora"), m.group("autor").strip(),
                    " ".join(m.group("txt").split())))
    return out


def relato_diligencia(texto):
    """Comentário -> frase para o cliente, ou None se não relatar uma diligência feita."""
    t = norm_texto(texto)
    if re.search(r"\(\d\d\)\s*\d{4,5}-?\d{4}|\b\d{4}-\d{4}\b", texto):
        return None                                   # telefone: anotação interna
    if re.match(r"(DISPONIBILIZACAO|PUBLICACAO|RELACAO|TEOR DO ATO|CERTIDAO)", t) or t.startswith("DILIGENCIAR"):
        return None                                   # publicação colada / plano da tarefa
    if not _FEITO.search(t):
        return None                                   # "07h30 às 13h30..." e afins
    if re.search(r"DESPACH\w*[^.]{0,30}(JUIZ|DR\b|DRA\b|DR\.)|\bDRA?\.?\s+\w+\s+DESPACH", t):
        com = "conversar diretamente com o juiz sobre o seu processo"
        canal = " pessoalmente" if "PRESENCIAL" in t else ""
        frase = "Nossa equipe foi%s ao fórum para %s." % (canal, com)
    else:
        canal = ("pessoalmente, na vara," if "PRESENCIAL" in t else
                 "pelo balcão virtual da vara" if "BALCAO" in t else
                 "por telefone com a vara" if re.search(r"LIGA|TELEFON", t) else "junto à vara")
        quem = " com o servidor responsável" if re.search(r"SERVIDOR|ASSESSOR|ANALISTA|CHEFE", t) else ""
        frase = "Nossa equipe fez uma diligência %s%s para cobrar o andamento do seu processo." % (canal, quem)
    m = re.search(r"(?:INFORMOU|INFORMAD[OA]|INFORMARAM|FICOU DE|DISSE|DISSERAM|RESPONDEU)\s*(?:QUE|DE)?\s*(.+)",
                  texto, re.I | re.S)
    if m:
        resposta = _RECADO_INTERNO.sub("", m.group(1)).strip().rstrip(".!, ")
        resposta = re.sub(r"(?i)^(me|nos|a nós)\s+(que\s+)?", "", resposta)
        resposta = re.sub(r"(?i)^contudo,?\s*", "", resposta)
        for padrao, novo in _JARGAO:
            resposta = re.sub(padrao, novo, resposta, flags=re.I)
        if re.match(r"(?i)(irá|ira|vai|iria|ficou|seria) ", resposta):
            resposta = "a vara " + resposta
        if resposta:
            frase += " Fomos informados de que %s." % (resposta[:1].lower() + resposta[1:])
    elif re.search(r"SENTENCA", t):
        frase += " Em seguida, o processo recebeu a sentença."
    return frase


def diligencias_do_mes(tarefas, inicio, fim):
    """[{titulo, painel}] -> [(data_iso, hora, frase)] das diligências relatadas no mês."""
    out = []
    for tarefa in (tarefas if isinstance(tarefas, list) else []):
        if not TAREFA_DILIGENCIA.search(tarefa.get("titulo", "")):
            continue
        for iso, hora, autor, texto in comentarios_da_tarefa(tarefa.get("painel", "")):
            d = datetime.date.fromisoformat(iso)
            if not (inicio <= d <= fim):
                continue
            frase = relato_diligencia(texto)
            if frase and any(o[0] == iso and o[4] == tarefa.get("titulo") for o in out):
                anterior = next(o for o in out if o[0] == iso and o[4] == tarefa.get("titulo"))
                if "Fomos informados" in frase and "Fomos informados" not in anterior[2]:
                    out.remove(anterior)
                else:
                    continue
            if frase:
                h = re.search(r"\b(\d{1,2})[h:](\d{2})\b", texto)
                out.append((iso, ("%sh%s" % (h.group(1).zfill(2), h.group(2))) if h else hora.replace(":", "h"),
                            frase, texto, tarefa.get("titulo")))
    return out


# ─────────────────────────── classificação ─────────────────────────
# Cada publicação vira UMA frase para o cliente. A ordem das regras importa:
# o texto costuma recapitular o histórico ("a decisão agravada indeferiu a
# tutela..."), então o que é mais decisivo e mais específico vem primeiro.

_MES_EXT = {m.upper().replace("Ç", "C"): i + 1 for i, m in enumerate(MESES)}


def _achar_data(t):
    """Primeira data futura-ou-recente citada no texto (dd/mm/aaaa ou por extenso)."""
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d\d)\b", t)
    if m:
        return "%02d/%02d/%s" % (int(m.group(1)), int(m.group(2)), m.group(3))
    meses = "|".join(_MES_EXT)
    # "DOS DIAS 29 DE SETEMBRO A 06 DE OUTUBRO DE 2026" -> vale o primeiro dia
    m = re.search(r"\b(\d{1,2})(?:º|O)? DE (%s)(?: A \d{1,2} DE (?:%s))? DE (20\d\d)" % (meses, meses), t)
    if m:
        return "%02d/%02d/%s" % (int(m.group(1)), _MES_EXT[m.group(2)], m.group(3))
    return None


def _achar_hora(t):
    m = re.search(r"\b(?:AS|A PARTIR DAS|COM INICIO AS)\s+(\d{1,2})[:H](\d{2})", t)
    return "%s:%s" % (m.group(1).zfill(2), m.group(2)) if m else None


_NEG = r"(INDEFIRO|INDEFERID[OA]|INDEFERI\b|NEGO\b|DENEGO|NAO CONCEDO|NAO CONCEDID[OA]|DEIXO DE CONCEDER)"
_POS = r"(DEFIRO|DEFERID[OA]\b|CONCEDO|CONCEDID[OA]|ANTECIPO)"
_MED = r"(TUTELA|LIMINAR|MEDIDA DE URGENCIA|EFEITO SUSPENSIVO|ANTECIPACAO)"
_ANTIGA = r"(OUTRORA|ANTERIORMENTE|JA (CONCEDID|DEFERID)|CONFIRMO A LIMINAR|DECISAO AGRAVADA|" \
          r"DECISAO RECORRIDA|QUE INDEFERIU|QUE DEFERIU)"
# Negativa sem a palavra "indefiro" — caso real (30/09/2026): "DEFIRO O PEDIDO DE AJG.
# OS REQUISITOS PARA A CONCESSAO DA TUTELA ... NAO SE ENCONTRAM PRESENTES".
_NEG_IMPLICITA = r"(REQUISITOS[^.]{0,80}NAO (SE )?(ENCONTRAM|ESTAO|FORAM)[^.]{0,20}(PRESENTES|PREENCHIDOS|" \
                 r"DEMONSTRADOS)|AUSENTES OS REQUISITOS|NAO VISLUMBRO[^.]{0,60}(PROBABILIDADE|URGENCIA|" \
                 r"REQUISITOS))"


def _liminar(t):
    """'parcial', 'neg', 'pos' ou None.

    Nas revisionais o comum é o deferimento PARCIAL ("DEFIRO PARCIALMENTE a tutela
    para autorizar o depósito [...] INDEFIRO os demais pedidos") — por isso ele é
    checado primeiro, e "indefiro os demais" não conta como negativa. Depois a
    negativa, antes da positiva (lição do RADAR B&A). A janela não atravessa ponto
    final: "DEFIRO a gratuidade. [...] a TUTELA" não é deferimento da tutela."""
    def recente(m):
        return not re.search(_ANTIGA, t[max(0, m.start() - 80):m.end()])

    for m in re.finditer(r"(DEFIRO|CONCEDO)\s+(EM PARTE|PARCIALMENTE)[^.]{0,80}?%s|%s[^.]{0,40}?"
                         r"(DEFERID[OA]|CONCEDID[OA]) (EM PARTE|PARCIALMENTE)" % (_MED, _MED), t):
        if recente(m):
            return "parcial"
    for m in re.finditer(r"%s[^.]{0,120}?%s|%s[^.]{0,60}?%s" % (_NEG, _MED, _MED, _NEG), t):
        if recente(m) and "DEMAIS" not in m.group(0):
            return "neg"
    if re.search(_NEG_IMPLICITA, t) and re.search(_MED, t):
        return "neg"
    for m in re.finditer(r"%s[^.]{0,120}?%s|%s[^.]{0,60}?%s" % (_POS, _MED, _MED, _POS), t):
        if recente(m):
            return "pos"
    # "DEFIRO O DEPOSITO DO VALOR INTEGRAL E DECIDO MANTER A POSSE" — é a tutela,
    # mesmo sem a palavra "tutela".
    if re.search(r"(DEFIRO|AUTORIZO)[^.]{0,30}DEPOSITO|DECIDO MANTER A POSSE", t):
        return "pos"
    return None


def _com_deposito(t):
    return bool(re.search(r"(AUTORIZ\w*|DEFIRO)[^.]{0,80}DEPOSIT", t))


def _audiencia(t):
    """(data, hora) de audiência efetivamente marcada, ou None.

    Só vale data dentro da mesma frase de AUDIENCIA — senão pegava a data da
    assinatura ("MACEIO, 01 DE SETEMBRO"). E "deixo de designar" não é audiência."""
    for m in re.finditer(r"AUDIENCIA[^.]{0,250}", t):
        frase = t[max(0, m.start() - 120):m.end()]
        if re.search(r"DEIXO (DE|PARA)|NAO DESIGN|NAO HAVERA|DEIXA DE SER|INCLUSAO DO FEITO NA PAUTA|"
                     r"POR NAO DESIGNAR|DISPENS", frase):
            continue
        if not re.search(r"DESIGN|REDESIGN|AGENDAD|MARCAD|REALIZAR-SE|DIA\b", frase):
            continue
        d = _achar_data(m.group(0))
        if d:
            return d, _achar_hora(m.group(0))
    return None


def _sinal_sentenca(t, tipo):
    """Leitura interna do dispositivo, só para a coluna CONFERIR (não vai ao cliente)."""
    if re.search(r"HOMOLOG[^.]{0,80}ACORDO", t):
        r = "acordo homologado"
    elif re.search(r"SEM (A )?RESOLUCAO D[OE] MERITO|JULGO EXTINT|EXTINGO O (PROCESSO|FEITO)", t) \
            and not re.search(r"PROCEDENTE", t):
        r = "extinto sem julgar o mérito"
    elif re.search(r"PARCIALMENTE PROCEDENTE|PROCEDENTES? EM PARTE|PROCEDENTE, EM PARTE", t):
        r = "parcialmente procedente"
    elif re.search(r"IMPROCEDENTE", t):
        r = "improcedente"
    elif re.search(r"PROCEDENTE", t):
        r = "procedente"
    else:
        return ""
    if tipo == "busca" and r in ("procedente", "parcialmente procedente"):
        r += " — DESFAVORÁVEL (cliente é réu)"
    elif tipo == "busca" and r == "improcedente":
        r += " — favorável (cliente é réu)"
    return r


_NOME_RECURSO = [("AGRAVO INTERNO", "agravo interno"), ("AGRAVO DE INSTRUMENTO", "agravo de instrumento"),
                 ("EMBARGOS DE DECLARACAO", "embargos de declaração"), ("APELACAO", "apelação"),
                 ("RECURSO ESPECIAL", "recurso especial"), ("RECURSO INOMINADO", "recurso inominado"),
                 ("AGRAVO", "agravo")]
_INCIDENTAL = r"AGRAVO INTERNO|EMBARGOS"


def nome_do_recurso(classe):
    c = norm_texto(classe)
    return next((nome for chave, nome in _NOME_RECURSO if chave in c), "recurso")


def quem_recorre(t, cliente):
    """'nosso', 'banco' ou None — pelo rótulo AGRAVANTE/APELANTE/EMBARGANTE do texto."""
    m = re.search(r"\b(AGRAVANTE|APELANTE|EMBARGANTE|RECORRENTE)S?(?:\(S\))?\s*:\s*(.{3,90}?)\s*"
                  r"(?: - |AGRAVAD|APELAD|EMBARGAD|RECORRID|ADVOGAD|RELATOR|$)", t)
    if not m:
        return None
    nome = norm(m.group(2))
    if cliente:
        c = norm(cliente).split()
        if len(c) >= 2 and nome.startswith(" ".join(c[:2])):
            return "nosso"
    if _BANCO.search(m.group(2)):
        return "banco"
    return None


def _trecho_dispositivo(t):
    m = re.search(r"ACORDAM|A UNANIMIDADE|POR UNANIMIDADE|POR MAIORIA|JULGARAM|DISPOSITIVO|ANTE O EXPOSTO|"
                  r"DIANTE DO EXPOSTO|ISTO POSTO|POSTO ISSO", t)
    return t[m.start():m.start() + 1200] if m else t[:2500]


def resultado_do_recurso(t):
    """O PRIMEIRO resultado que aparece no dispositivo — a ementa mais abaixo cita outros
    julgados ("agravo não conhecido") e não pode prevalecer (caso real de 30/09/2026)."""
    trecho = _trecho_dispositivo(t)
    if re.search(r"PREJUDICAD", trecho[:400]):
        return "prejudicado"
    padroes = [("nao_conhecido", r"NAO CONHEC"),
               ("parcial", r"PARCIAL PROVIMENTO|PROVIMENTO PARCIAL|PARCIALMENTE PROVID"),
               ("negado", r"NEGA(R|DO)?(-LHE)? PROVIMENTO|NEGO(-LHE)? PROVIMENTO|DESPROVI|IMPROVID|NAO PROVID"),
               ("provido", r"\bDA(R|DO)(-LHE)? PROVIMENTO|\bDOU(-LHE)? PROVIMENTO|\bPROVID[OA]\b")]
    melhor = None
    for nome, padrao in padroes:
        m = re.search(padrao, trecho)
        if m and (melhor is None or m.start() < melhor[1]):
            melhor = (nome, m.start())
    if melhor and melhor[0] == "provido" and re.match(r".{0,40}?(EM PARTE|PARCIAL)", trecho[melhor[1]:]):
        return "parcial"                     # "DAR-LHE PROVIMENTO EM PARTE"
    return melhor[0] if melhor else None


def resultado_dos_dois_recursos(t, tipo):
    """Quando autor e réu recorreram: {'nosso': res, 'banco': res}."""
    out = {}
    for m in re.finditer(r"(DAR PARCIAL|DAR|DOU|NEGAR|NEGO)[^.]{0,25}?PROVIMENTO (?:AO|A) (?:RECURSO|APELO|"
                         r"APELACAO) D[OA] (AUTORA?|REU|RE|REQUERID[OA]|DEMANDAD[OA])\b", _trecho_dispositivo(t)):
        v = m.group(1)
        res = "parcial" if "PARCIAL" in v else ("negado" if v.startswith("NEG") else "provido")
        autor = m.group(2).startswith("AUTOR")
        quem = ("nosso" if autor else "banco") if tipo != "busca" else ("banco" if autor else "nosso")
        out[quem] = res
    return out


_ASSUNTOS = [
    (r"GRATUIDADE|JUSTICA GRATUITA|\bAJG\b|ASSISTENCIA JUDICIARIA",
     "a justiça gratuita (não pagar as custas do processo)"),
    (r"DEPOSIT\w*[^.]{0,60}(PARCELA|PRESTAC|INCONTROVERS|INTEGRAL)", "o depósito das parcelas em juízo"),
    (r"(POSSE|MANUTENCAO|MANTENDO)[^.]{0,40}(VEICULO|BEM)", "você ficar com o veículo durante o processo"),
    (r"INSCRICAO[^.]{0,40}(ORGAOS|CADASTRO)|NEGATIVA\w*|ORGAOS DE PROTECAO|SERASA|\bSPC\b",
     "não ter o nome negativado"),
    (r"BUSCA E APREENSAO", "a busca e apreensão do veículo"),
    (r"JUROS|CAPITALIZACAO|TARIFA", "os juros e cobranças do contrato"),
]


def assunto_do_recurso(textos):
    achados = []
    for t in textos:
        for padrao, rotulo in _ASSUNTOS:
            if rotulo not in achados and re.search(padrao, t[:4000]):
                achados.append(rotulo)
    if not achados and any(re.search(r"TUTELA|LIMINAR", t[:4000]) for t in textos):
        achados.append("o pedido urgente (liminar)")
    return achados[:4]


def _qual_recurso(t, classe, cliente):
    quem = quem_recorre(t, cliente)
    nome = nome_do_recurso(classe)
    if quem == "nosso":
        return "o nosso recurso (%s)" % nome
    if quem == "banco":
        return "o recurso do banco (%s)" % nome
    return "o recurso (%s)" % nome


def classificar(pub, tipo, cliente=None):
    """Devolve (frase_para_o_cliente, motivo_para_conferir_ou_None)."""
    t = pub["texto_norm"]
    doc = norm_texto(pub["tipo_documento"])
    classe = norm_texto(pub["classe"])
    recurso = bool(re.search(r"AGRAVO|APELACAO|EMBARGOS|RECURSO", classe))
    orgao = pub["orgao"]

    if "SIGILOS" in t[:600]:
        return ("Houve uma movimentação no processo, que tramita em segredo de justiça. "
                "Nossa equipe acompanha o conteúdo.", None)

    if re.search(r"DISTRIBUID[OA] PARA", t):
        d = _achar_data(t)
        if recurso:
            return ("O recurso foi registrado no Tribunal e distribuído para %s%s."
                    % (orgao or "a câmara responsável", " em " + d if d else ""), None)
        return ("A ação foi registrada e distribuída para %s%s. É o início oficial do processo."
                % (orgao or "a vara responsável", " em " + d if d else ""), None)

    futuro = re.search(r"(CONCLUSOS|VOLTEM|RETORNEM|APOS)[^.]{0,40}PARA (A )?INCLUSAO", t)
    if "PROXIMOS JULGADOS" in doc or (not futuro and re.search(r"PAUTAD[OA]|INCLUSAO .{0,40}JULGAMENTO|"
                                                               r"INCLUID[OA] .{0,30}PAUTA", t)):
        if re.search(r"TORNO SEM EFEITO|RETIRAD[OA] DE PAUTA|ADIAD", t):
            return ("O julgamento do recurso que estava marcado foi adiado pelo Tribunal. "
                    "Uma nova data será definida.", None)
        qual = _qual_recurso(t, classe, cliente)
        if re.search(r"PECO (DIA PARA JULGAMENTO|INCLUSAO)|SOLICITO INCLUSAO", t):
            return ("O relator pediu para colocar %s na pauta de julgamento do Tribunal. "
                    "A data será divulgada pelo Tribunal." % qual, None)
        # a data vale só DEPOIS da menção à pauta (antes vêm datas de resoluções etc.)
        m = re.search(r"PAUTAD[OA]|INCLUSAO|INCLUID[OA]|PAUTA", t)
        resto = t[m.start():m.start() + 300] if m else t
        d, h = _achar_data(resto), _achar_hora(resto)
        if h and h.startswith("00:"):
            h = None                               # sessão virtual "a partir das 00:01"
        return ("%s entrou na pauta de julgamento do Tribunal%s%s."
                % (qual[:1].upper() + qual[1:], " do dia " + d if d else "", ", às " + h if h else ""), None)

    if re.search(r"FILA DE SENTENCA|CONCLUS[OA]S? (DOS AUTOS )?PARA (A )?SENTENCA|"
                 r"CONCLUSAO DOS AUTOS[^.]{0,60}SENTENCA|APTO PARA JULGAMENTO", t):
        return ("O processo está pronto para julgamento e foi enviado ao juiz para a sentença.", None)

    if "SENTENCA" in doc or re.search(
            r"- SENTENCA\b|\bJULG(O|A-SE|AD[OA])\b[^.]{0,60}\b(IM)?PROCEDENTE|\bJULGO PARCIALMENTE|JULGO EXTINT|"
            r"EXTINGO O (PROCESSO|FEITO)|JULGO O (PROCESSO|FEITO) EXTINTO|HOMOLOGO[^.]{0,80}ACORDO|"
            r"RESOLVO O (PROCESSO|MERITO)", t):
        if not recurso:
            sinal = _sinal_sentenca(t, tipo)
            return ("Foi publicada a sentença do processo, que é a decisão do juiz sobre o pedido. "
                    "Nossa equipe está analisando o resultado e os próximos passos e vai "
                    "falar com você.", "SENTENÇA" + (": " + sinal if sinal else ""))

    if re.search(r"ACORDAO|ACORDAM|RELATORIO E VOTO|VOTO PREVALECENTE", doc + " " + t[:3000]) \
            and recurso:
        quem, res = quem_recorre(t, cliente), resultado_do_recurso(t)
        nome = nome_do_recurso(classe)
        unan = ", por unanimidade," if "UNANIMIDADE" in t else ""
        if re.search(r"(SUPERIOR TRIBUNAL DE JUSTICA|\bSTJ\b)[^.]{0,30}NAO CONHECEU", t):
            return ("O Superior Tribunal de Justiça (STJ), em Brasília, não chegou a analisar o recurso. "
                    "Fica valendo a decisão do Tribunal de Justiça, e o processo volta para a vara de origem.",
                    "STJ: não conhecido")
        if res == "prejudicado":
            return ("O Tribunal considerou o recurso (%s) prejudicado: não foi preciso julgá-lo, porque a "
                    "situação do processo mudou. Nossa equipe explica os detalhes." % nome, "ACÓRDÃO: prejudicado")
        dois = resultado_dos_dois_recursos(t, tipo)
        if len(dois) == 2:
            txt_n = {"provido": "aceitou o nosso recurso", "parcial": "aceitou em parte o nosso recurso",
                     "negado": "não aceitou o nosso recurso"}[dois["nosso"]]
            txt_b = {"provido": "aceitou o do banco", "parcial": "aceitou em parte o do banco",
                     "negado": "rejeitou o do banco"}[dois["banco"]]
            return ("As duas partes recorreram. O Tribunal%s %s e %s. Nossa equipe vai explicar o que "
                    "muda para você." % (unan, txt_n, txt_b),
                    "ACÓRDÃO: nosso %s / banco %s" % (dois["nosso"], dois["banco"]))
        frases = {
            ("nosso", "provido"): "O Tribunal aceitou%s o nosso recurso (%s)." % (unan, nome),
            ("nosso", "parcial"): "O Tribunal aceitou em parte%s o nosso recurso (%s)." % (unan, nome),
            ("nosso", "negado"): "O Tribunal não aceitou%s o nosso recurso (%s). Nossa equipe vai avaliar "
                                 "os próximos passos." % (unan, nome),
            ("banco", "negado"): "O Tribunal rejeitou%s o recurso do banco (%s). A decisão que o banco "
                                 "queria mudar continua valendo." % (unan, nome),
            ("banco", "provido"): "O Tribunal aceitou%s o recurso do banco (%s). Nossa equipe vai avaliar "
                                  "os próximos passos e falar com você." % (unan, nome),
            ("banco", "parcial"): "O Tribunal aceitou em parte%s o recurso do banco (%s). Nossa equipe vai "
                                  "avaliar os próximos passos e falar com você." % (unan, nome),
        }
        if res == "nao_conhecido" and quem:
            return ("O Tribunal não chegou a analisar %s (%s), por uma questão formal."
                    % ("o nosso recurso" if quem == "nosso" else "o recurso do banco", nome),
                    "ACÓRDÃO: não conhecido")
        if (quem, res) in frases:
            return (frases[(quem, res)], "ACÓRDÃO: %s %s" % (res, "nosso" if quem == "nosso" else "do banco"))
        return ("O Tribunal julgou o recurso (%s). Nossa equipe está analisando a decisão e "
                "vai explicar o resultado para você." % nome, "ACÓRDÃO")

    lim = _liminar(t)
    if recurso and (lim or "DECISAO MONOCRATICA" in doc + t[:800] or "DECISAO LIMINAR" in t[:1500]):
        if lim == "pos":
            txt = "O Tribunal concedeu o pedido urgente feito no recurso."
        elif lim == "parcial":
            txt = "O Tribunal concedeu em parte o pedido urgente feito no recurso."
        elif lim == "neg":
            txt = "O Tribunal negou, por enquanto, o pedido urgente feito no recurso. O recurso continua."
        else:
            txt = "O desembargador responsável proferiu uma decisão no recurso."
        return (txt + " Nossa equipe está analisando os detalhes.", "DECISÃO NO RECURSO")

    aud = _audiencia(t)
    if aud:
        seg = t[t.find("AUDIENCIA"):t.find("AUDIENCIA") + 120]
        tipo_aud = "de conciliação " if re.search(r"CONCILIA|MEDIACAO", seg) else ""
        return ("Foi marcada audiência %spara %s%s. Vamos orientar você antes da data."
                % (tipo_aud, aud[0], ", às " + aud[1] if aud[1] else ""), "AUDIÊNCIA")

    if recurso:
        # Nos recursos, gratuidade/emenda/citação no texto falam da origem, não de
        # uma providência nova — não aplicar as regras de 1º grau.
        if re.search(r"EMBARGOS DE DECLARACAO", classe + " " + t[:1500]):
            return ("Houve um pedido de esclarecimento sobre uma decisão (embargos de declaração), "
                    "que será analisado pelo Tribunal.", None)
        if "DECISAO" in doc:
            return ("O desembargador responsável proferiu uma decisão no recurso. Nossa equipe "
                    "está analisando os detalhes.", "DECISÃO NO RECURSO")
        return ("O recurso teve andamento no Tribunal.", None)

    if tipo == "busca":
        if re.search(r"(EXPE[CÇ]A-SE|EXPEDICAO D[OE]|EXPEDID[OA]).{0,80}MANDADO|MANDADO.{0,60}EXPEDID", t):
            return ("Foi determinada a expedição do mandado de busca e apreensão do veículo. "
                    "Nossa equipe acompanha e atua na sua defesa.", "MANDADO")
        if lim in ("pos", "parcial") or re.search(r"(DEFIRO|CONCEDO).{0,40}LIMINARMENTE", t):
            return ("O juiz concedeu a liminar pedida pelo banco na ação de busca e apreensão. "
                    "Nossa equipe está atuando na sua defesa.", "LIMINAR (BUSCA)")
        if lim == "neg":
            return ("O juiz negou a liminar de busca e apreensão pedida pelo banco.", "LIMINAR (BUSCA)")
        if re.search(r"INTERESSE NO (PRO)?SSEGUIMENTO|INTERESSE NO PROSSEGUIMENTO", t):
            return ("O juiz perguntou ao banco se ainda tem interesse em continuar a ação.", None)
    else:
        if lim in ("pos", "parcial"):
            dep = _com_deposito(t)
            return ("O juiz concedeu %sa liminar (pedido urgente) que fizemos na ação%s. %s"
                    % ("em parte " if lim == "parcial" else "",
                       ", autorizando o depósito judicial das parcelas" if dep else "",
                       "Nossa equipe vai orientar você sobre como fazer os depósitos." if dep
                       else "Nossa equipe vai explicar o que isso muda na prática."),
                    "LIMINAR" + (" PARCIAL" if lim == "parcial" else "") + (" + DEPÓSITO" if dep else ""))
        if lim == "neg":
            return ("O juiz negou, neste momento, o pedido de liminar (medida urgente). Isso não é a "
                    "decisão final: o processo continua normalmente e avaliamos a possibilidade "
                    "de recurso.", "LIMINAR NEGADA")

    if re.search(r"\bALVARA\b|EXPE[CÇ]A-SE[^.]{0,60}TRANSFERENCIA|LEVANTAMENTO D[OE]S? (VALOR|DEPOSITO|QUANTIA)", t):
        return ("O juiz autorizou a liberação de valores depositados no processo (alvará).", "ALVARÁ")

    if re.search(r"DECLINIO DE COMPETENCIA|DECLINO DA COMPETENCIA|REMETAM-SE OS AUTOS AO JUIZO COMPETENTE|"
                 r"REDISTRIBUI", t):
        return ("O processo foi enviado para outra vara ou comarca, que passa a ser a responsável "
                "por ele.", "COMPETÊNCIA")

    if re.search(r"PASSARA A TRAMITAR ELETRONICAMENTE|MIGRAD[OA] PARA O (SISTEMA )?EPROC", t):
        return ("O processo passou para o novo sistema eletrônico do Tribunal. Nada muda para você.", None)

    if re.search(r"REMETAM-SE OS AUTOS AO CJUS|INCLUSAO DO FEITO NA PAUTA DE AUDIENCIAS", t):
        return ("O juiz mandou citar o banco e incluir o processo na pauta de audiências de "
                "conciliação. A data ainda será definida.", None)

    if re.search(r"CUSTAS FINAIS|COBRANCA DE CUSTAS", t):
        return ("O cartório emitiu cobrança de custas finais do processo. Nossa equipe vai "
                "orientar você.", "CUSTAS")

    if re.search(r"GRATUIDADE|JUSTICA GRATUITA|HIPOSSUFICIENCIA|\bAJG\b|ASSISTENCIA JUDICIARIA", t):
        _GRAT = r"(GRATUIDADE|JUSTICA GRATUITA|\bAJG\b|ASSISTENCIA JUDICIARIA)"
        if re.search(r"(INDEFIRO|INDEFERID[OA])[^.]{0,60}%s|%s[^.]{0,40}(INDEFIRO|INDEFERID|NAO CONCEDID)|"
                     r"RECONSIDERACAO NAO COMPORTA|INDEFIRO O PEDIDO DE RECONSIDERACAO" % (_GRAT, _GRAT), t):
            return ("O juiz negou, por ora, o pedido de justiça gratuita. Nossa equipe vai falar "
                    "com você sobre as custas e os próximos passos.", "GRATUIDADE NEGADA")
        if re.search(r"(DEFIRO|CONCEDO|DEFERID[OA]|CONCEDID[OA]|MANTENHO)[^.]{0,80}%s|"
                     r"%s[^.]{0,80}(DEFIRO|CONCEDO)" % (_GRAT, _GRAT), t) \
                and not re.search(r"SOB PENA DE INDEFERIMENTO", t):
            return ("O juiz concedeu a justiça gratuita: você não paga as custas do processo.", None)
        if re.search(r"APRESENT|COMPROV|JUNT|SOB PENA", t):
            return ("O juiz pediu documentos para confirmar o direito à justiça gratuita (sem "
                    "custas). Se precisarmos de algum documento seu, vamos entrar em contato.",
                    "DOCUMENTOS")

    if re.search(r"EMENDA|EMENDAR|RECOLHIMENTO D[AE]S? CUSTAS|GUIAS? DE (RECOLHIMENTO|CUSTAS)", t):
        return ("O juiz pediu um complemento na petição inicial. Nossa equipe já está "
                "cuidando disso.", "CUSTAS/EMENDA" if "CUSTAS" in t else None)

    if re.search(r"SUSPEN(SAO|DO|DA|DO O)\b.{0,60}(PROCESSO|FEITO)|(PROCESSO|FEITO).{0,40}SUSPENS", t):
        return ("O processo foi suspenso temporariamente por determinação do juiz.", "SUSPENSÃO")

    if re.search(r"ART\.? 523|CUMPRIR A OBRIGACAO DE PAGAR", t) or "CUMPRIMENTO DE SENTENCA" in classe:
        return ("O processo está na fase de cumprimento do que foi decidido: o juiz mandou "
                "a parte devedora pagar o valor em 15 dias.", "CUMPRIMENTO")

    if re.search(r"EMBARGOS DE DECLARACAO", t):
        return ("Houve um pedido de esclarecimento sobre uma decisão (embargos de declaração), "
                "que será analisado.", None)

    if re.search(r"CONTRARRAZOES|APELACAO", t):
        return ("Foi apresentado recurso de apelação. As partes estão apresentando suas "
                "respostas antes de o processo seguir para o Tribunal.", None)

    if re.search(r"RETORNO DOS (PRESENTES )?AUTOS|BAIXA DOS AUTOS|AUTOS RETORNARAM", t):
        return ("O processo voltou do Tribunal para a vara de origem e segue seu andamento.", None)

    if re.search(r"REPLICA|SOBRE A CONTESTACAO|IMPUGN\w* A CONTESTACAO", t):
        if tipo == "busca":
            return ("O banco foi chamado a responder à defesa que apresentamos.", None)
        return ("O banco apresentou sua defesa (contestação) e agora é a nossa vez de "
                "responder.", None)

    if re.search(r"ESPECIFI\w*.{0,60}PROVAS|OUTRAS PROVAS|PRODUCAO DE PROVAS|PROVAS QUE PRETEND", t):
        return ("O juiz perguntou se as partes querem produzir outras provas. É a etapa que "
                "antecede o julgamento.", None)

    if re.search(r"CONCILIACAO|AUTOCOMPOSICAO|POSSIBILIDADE DE ACORDO", t):
        return ("O juiz perguntou se existe possibilidade de acordo com o banco.", None)

    if re.search(r"DEVOLUCAO DO A\.?R\b|RETORNO DO A\.?R\b|AGUARDE-SE (A DEVOLUCAO|O RETORNO)", t):
        return ("O juiz está aguardando o comprovante dos Correios de que a citação foi entregue (o \"AR\").",
                None)

    if re.search(r"\bCITE-SE\b|CITACAO D[OA] (REU|RE\b|REQUERID|DEMANDAD|PARTE RE)", t):
        if tipo == "busca":
            return ("Foi determinada a citação, que é a comunicação oficial sobre a ação do banco.", None)
        return ("O juiz mandou citar o banco, ou seja, chamá-lo oficialmente para se defender.", None)

    if "ATO ORDINATORIO" in doc + t[:1500] or re.search(r"PROVIMENTO N", t[:1500]):
        return ("O cartório deu andamento de rotina ao processo.", None)

    if "DECISAO" in doc:
        return ("O juiz proferiu uma decisão no processo. Nossa equipe está analisando.", "DECISÃO")

    if "DESPACHO" in doc or re.search(r"\bINTIME-SE\b|\bDESPACHO\b|DE-SE VISTA|MANIFESTE-SE", t[:2500]):
        return ("O juiz deu andamento ao processo (despacho).", None)

    if re.search(r"\b(DEFIRO|INDEFIRO|DETERMINO)\b", t):
        return ("O juiz proferiu uma decisão no processo. Nossa equipe está analisando.", "DECISÃO")

    return ("Houve uma publicação oficial no processo.", "NÃO CLASSIFICADA")


# ─────────────────────────── fase atual (rodagem) ──────────────────

# Cada fase é um trio: (SITUAÇÃO ATUAL, O QUE ISSO QUER DIZER, PRÓXIMO PASSO).
# Pedido da Caroline (01/10/2026): o cliente é muito leigo — "réplica", "contestação"
# e "conclusos" não dizem nada para ele. A situação vem em frase direta e o segundo
# item explica, em linguagem de conversa, o que aquilo significa para ele.

_FASE_REV = {
    "INICIAL": ("Sua ação já foi entregue à Justiça e aguarda a primeira análise do juiz.",
                "O processo começou. O juiz vai ler o pedido e, estando tudo certo, mandar o banco "
                "se defender. Essa etapa costuma levar algumas semanas e não depende de nada da sua parte.",
                "O juiz analisa o pedido e manda chamar o banco para se defender."),
    "EMENDA": ("O juiz pediu um ajuste ou um documento a mais no nosso pedido.",
               "Isso é comum: o juiz só quer que algum ponto fique mais completo antes de seguir. "
               "Nossa equipe cuida disso. Se precisarmos de algum documento seu, vamos avisar.",
               "Feito o ajuste, o juiz analisa o pedido e manda chamar o banco."),
    "CONTESTACAO": ("O banco foi chamado para se defender no processo.",
                    "Em toda ação o banco recebe uma cópia do pedido e tem um prazo para responder. "
                    "É uma etapa obrigatória e não significa nada de ruim para você.",
                    "Quando o banco se defender, nós apresentamos a nossa resposta."),
    "REPLICA": ("O banco já apresentou a defesa dele. Agora é a nossa vez de responder.",
                "Essa resposta se chama \"réplica\". Nela rebatemos os argumentos do banco e reforçamos "
                "os seus direitos. É uma etapa normal de todo processo, e quem faz é a nossa equipe — "
                "você não precisa fazer nada.",
                "Depois da nossa resposta, o juiz decide se precisa de mais provas ou se já pode julgar."),
    "PROD PROVAS": ("O processo está na fase de provas.",
                    "O juiz quer saber se alguém precisa apresentar mais documentos ou fazer perícia "
                    "antes de decidir. Na maioria das ações revisionais, os documentos do contrato já bastam.",
                    "Terminada essa fase, o processo vai para o juiz dar a sentença."),
    "RECURSO": ("Há um recurso em andamento no Tribunal.",
                "Recurso é quando uma das partes pede ao Tribunal — que fica acima do juiz — para rever "
                "uma decisão. Quem julga são três desembargadores.",
                "O Tribunal julga o recurso."),
    "PROCEDENTE": ("O juiz deu ganho de causa a você (sentença favorável).",
                   "O juiz concordou com o nosso pedido. O banco ainda pode recorrer ao Tribunal, por "
                   "isso seguimos acompanhando até o fim.",
                   "Acompanhamos um eventual recurso do banco e o cumprimento da decisão."),
}
_FASE_BUSCA = {
    "INICIAL": ("O banco entrou com uma ação de busca e apreensão do veículo, que está no começo.",
                "É o processo em que o banco pede para retomar o veículo por causa de parcelas em atraso. "
                "Nossa equipe cuida da sua defesa nesse processo.",
                "Nossa equipe acompanha e atua na sua defesa."),
    "EMENDA": ("O juiz pediu ao banco para completar o pedido dele.",
               "O próprio banco precisa corrigir ou completar algo antes de o processo seguir. "
               "Por enquanto, não há nada que você precise fazer.",
               "Nossa equipe acompanha e atua na sua defesa."),
    "CONTESTACAO": ("Apresentamos a sua defesa na ação do banco.",
                    "A defesa (\"contestação\") é onde mostramos ao juiz os seus argumentos e os problemas "
                    "do contrato. Agora o banco pode responder.",
                    "O banco responde à defesa e o juiz decide os próximos passos."),
    "REPLICA": ("O banco está respondendo à defesa que apresentamos.",
                "Depois da nossa defesa, o banco tem o direito de se manifestar. É uma etapa normal.",
                "Em seguida, o juiz decide os próximos passos."),
    "PROD PROVAS": _FASE_REV["PROD PROVAS"],
    "RECURSO": _FASE_REV["RECURSO"],
}
_SIT_BUSCA = {
    "LIMINAR DEF": ("O juiz autorizou, por enquanto, a busca e apreensão do veículo pedida pelo banco.",
                    "\"Liminar\" é uma decisão provisória, tomada no começo do processo. Ela não é a "
                    "decisão final, e nossa equipe atua para defender você.",
                    "Nossa equipe acompanha e atua na sua defesa."),
    "MANDADO EXP": ("Foi emitida a ordem para o oficial de justiça buscar o veículo (mandado).",
                    "O mandado é o documento que autoriza o oficial de justiça a cumprir a decisão. "
                    "Se um oficial de justiça procurar você, fale com a nossa equipe na mesma hora.",
                    "Nossa equipe acompanha o cumprimento do mandado e atua na sua defesa."),
    "VEIC APREENDIDO": ("O veículo foi apreendido.",
                        "O processo continua e o caso ainda pode ser discutido. Nossa equipe segue na sua "
                        "defesa e vai orientar você sobre as opções.",
                        "Seguimos atuando na defesa e nos pedidos possíveis no processo."),
    "VEIC DEVOLVIDO": ("O veículo foi devolvido a você.",
                       "O processo continua até a decisão final, e seguimos acompanhando.",
                       "Seguimos acompanhando o processo até o final."),
    "ACORDO HOM": ("O acordo com o banco foi aprovado pelo juiz.",
                   "O juiz confirmou o acordo, que passa a valer como decisão. O importante agora é cumprir "
                   "o que foi combinado.",
                   "Acompanhamos o cumprimento do acordo."),
}
_PADRAO = ("Seu processo está em andamento.",
           "Não houve mudança de fase. O processo segue o ritmo normal da Justiça e nossa equipe acompanha.",
           "Seguimos acompanhando o processo e avisamos sobre qualquer novidade.")
_LIMINAR_NOSSA = ("O juiz concedeu a liminar (pedido urgente) que fizemos.",
                  "\"Liminar\" é uma decisão provisória que protege você enquanto o processo não termina. "
                  "Ela vale enquanto as condições fixadas pelo juiz forem cumpridas — por exemplo, fazer "
                  "os depósitos em dia.",
                  "O banco é chamado a se defender e o processo segue.")


def _chave_fase(v):
    return " ".join(re.sub(r"[^A-Z ]", " ", norm_texto(v)).split())


# O que aconteceu é mais novo que a coluna DESPACHO da rodagem, que costuma ficar
# para trás. O último evento que indica a fase prevalece.
_FASE_POR_EVENTO = [
    (r"^Foi publicada a sentença", ("O juiz deu a sentença, que é a decisão sobre o seu pedido.",
                                     "A sentença encerra a primeira etapa do processo. Nossa equipe vai explicar "
                                     "o resultado e o que pode ser feito a seguir. Ainda cabe recurso ao Tribunal, "
                                     "por qualquer das partes.",
                                     "Nossa equipe vai falar com você sobre o resultado e os próximos passos.")),
    (r"^O Tribunal (julgou|aceitou|rejeitou|não aceitou|não chegou)", (
        "O Tribunal já julgou o recurso.",
        "Os desembargadores analisaram o recurso e decidiram. O resultado está descrito logo acima.",
        "Nossa equipe avalia a decisão e os próximos passos.")),
    (r"^O processo está pronto para julgamento", (
        "O processo está pronto e aguarda a sentença do juiz.",
        "As etapas de discussão terminaram. Agora o juiz vai estudar o caso e decidir. O tempo depende "
        "da quantidade de processos da vara.",
        "O juiz dá a sentença.")),
    (r"pauta de julgamento|na pauta", (
        "O recurso está aguardando julgamento no Tribunal.",
        "O recurso já foi preparado e está marcado (ou prestes a ser marcado) para ser julgado pelos "
        "desembargadores.",
        "O Tribunal julga o recurso na sessão marcada.")),
    (r"^O juiz concedeu (em parte )?a liminar \(pedido urgente\)", _LIMINAR_NOSSA),
    (r"^O juiz negou, neste momento, o pedido de liminar", (
        "O juiz não concedeu, por enquanto, o pedido urgente (liminar).",
        "Isso não é a decisão final do processo. O pedido principal continua sendo analisado e nossa "
        "equipe avalia se cabe recurso ao Tribunal.",
        "O banco é chamado a se defender e o processo segue.")),
    (r"^Foi determinada a expedição do mandado", _SIT_BUSCA["MANDADO EXP"]),
    (r"^O juiz concedeu a liminar pedida pelo banco", _SIT_BUSCA["LIMINAR DEF"]),
    (r"^O banco apresentou sua defesa", _FASE_REV["REPLICA"]),
    (r"^O juiz perguntou se as partes querem produzir", _FASE_REV["PROD PROVAS"]),
    (r"^O juiz mandou citar o banco|^O juiz está aguardando o comprovante dos Correios", _FASE_REV["CONTESTACAO"]),
    (r"^A ação foi (registrada|distribuída)", _FASE_REV["INICIAL"]),
    (r"^O processo foi suspenso", ("O processo está suspenso por um tempo.",
                                   "O processo fica parado por um período, normalmente aguardando outro processo "
                                   "ou um prazo. Você não perde direitos por isso.",
                                   "Aguardamos o fim da suspensão para o processo seguir.")),
    (r"^Nossa equipe protocolou a réplica", (
        "Já respondemos à defesa do banco.",
        "Apresentamos a \"réplica\": rebatemos os argumentos do banco e reforçamos os seus direitos.",
        _FASE_REV["REPLICA"][2])),
    (r"^Nossa equipe protocolou a sua defesa", _FASE_BUSCA["CONTESTACAO"]),
    (r"^Apresentamos a nossa resposta à defesa", (
        "Já respondemos à defesa do banco.",
        "Apresentamos a \"réplica\": rebatemos os argumentos do banco e reforçamos os seus direitos.",
        _FASE_REV["REPLICA"][2])),
    (r"^Apresentamos a sua defesa \(contestação\)", _FASE_BUSCA["CONTESTACAO"]),
    (r"^O processo foi enviado ao juiz para decisão", (
        "O processo está com o juiz, aguardando uma decisão.",
        "O processo está na mesa do juiz para que ele decida alguma questão. É uma etapa de rotina.",
        "Aguardamos a decisão do juiz.")),
    (r"^O processo foi enviado ao juiz para dar andamento", (
        "O processo está com o juiz para o próximo passo.",
        "O processo foi enviado ao juiz para que ele dê andamento. É uma etapa de rotina.",
        "Aguardamos o próximo despacho do juiz.")),
    (r"^O processo foi enviado ao Tribunal|^Foi apresentado recurso", _FASE_REV["RECURSO"]),
    (r"^Foi enviada a carta de citação ao banco", _FASE_REV["CONTESTACAO"]),
    (r"^O processo foi enviado ao setor de conciliação", (
        "O processo está no setor de conciliação do Tribunal.",
        "É o setor que tenta um acordo entre as partes antes de o processo seguir.",
        "Aguardamos a citação do banco e a definição sobre a audiência de conciliação.")),
    (r"^O processo foi arquivado", ("O processo foi arquivado.",
                                    "O processo foi encerrado no sistema do Tribunal.",
                                    "Nossa equipe confere se resta alguma providência.")),
]


def fase_pelo_evento(eventos):
    for _, frase in reversed(eventos):
        for padrao, fase in _FASE_POR_EVENTO:
            if re.search(padrao, frase):
                return fase
    return None


def fase_atual(proc):
    desp, sit = _chave_fase(proc.get("despacho")), _chave_fase(proc.get("situacao"))
    if proc["tipo"] == "busca":
        if sit in _SIT_BUSCA:
            return _SIT_BUSCA[sit]
        return _FASE_BUSCA.get(desp, _PADRAO)
    if sit == "ACORDO HOM":
        return _SIT_BUSCA[sit]
    if sit == "LIMINAR DEF":
        return _LIMINAR_NOSSA
    return _FASE_REV.get(desp, _PADRAO)


# ─────────────────────────── casamento ─────────────────────────────

_BANCO = re.compile(r"BANCO|FINANC|CREDITO|LEASING|ARRENDAMENTO|S\.?/?A\b|AYMORE|ITAU|OMNI|SAFRA|"
                    r"SANTANDER|BRADESCO|CAIXA|UNIBANCO|COOPERA|FUNDO|HONDA|TOYOTA|YAMAHA|PAN\b|BV\b")


def preparar(it):
    dest = it.get("destinatarios") or []
    if isinstance(dest, str):
        dest = []
    texto = limpar_html(it.get("texto"))
    return {
        "id": str(it.get("id")),
        "numero": digitos(it.get("numero_processo")),
        "data": (it.get("data_disponibilizacao") or "")[:10],
        "tribunal": it.get("siglaTribunal") or "",
        "orgao": " ".join(str(it.get("nomeOrgao") or "").split()),
        "classe": it.get("nomeClasse") or "",
        "tipo_documento": it.get("tipoDocumento") or "",
        "texto": texto,
        "texto_norm": norm_texto(texto),
        "partes": [(d.get("nome") or "", d.get("polo") or "") for d in dest],
        "link": it.get("link") or "",
    }


def banco_da_publicacao(pub, nome_cliente):
    alvo = norm(nome_cliente)
    for nome, _ in pub["partes"]:
        if norm(nome) != alvo and _BANCO.search(norm_texto(nome)):
            return nome_bonito(nome)
    m = re.search(r"(?:RE[U]?|RÉ|AUTORA?|AGRAVAD[OA]|APELAD[OA]|REQUERID[OA])\s*:\s*([^-:]{4,90}?)"
                  r"\s+(?:-|ADVOGAD|RELATOR|$)", pub["texto"], re.I)
    if m and _BANCO.search(norm_texto(m.group(1))) and norm(m.group(1)) != alvo:
        return nome_bonito(m.group(1).strip(" .,"))
    return ""


def tipo_pela_classe(classe):
    c = norm_texto(classe)
    if "BUSCA E APREENS" in c:
        return "busca"
    if re.search(r"AGRAVO|APELACAO|EMBARGOS|RECURSO", c):
        return "recurso"
    if "CUMPRIMENTO" in c:
        return "cumprimento"
    return None


def casar(clientes, pubs):
    """Anexa cada publicação ao cliente. Devolve as que não casaram."""
    por_numero = {}
    for cli in clientes.values():
        for n in cli["processos"]:
            por_numero[n] = cli
    por_nome = {}
    for cli in clientes.values():
        por_nome.setdefault(norm(cli["nome"]), []).append(cli)

    fora = []
    for pub in pubs:
        cli = por_numero.get(pub["numero"])
        via_nome = False
        if cli is None:
            achados = set()
            partes = {norm(n) for n, _ in pub["partes"]}
            cabeca = norm(pub["texto"][:2500])
            for nome, lista in por_nome.items():
                if len(lista) != 1:
                    continue                       # homônimo na carteira: não arrisca
                if nome in partes or (len(nome.split()) >= 3 and len(nome) >= 15
                                      and (" %s " % nome) in (" %s " % cabeca)):
                    achados.add(nome)
            if len(achados) == 1:
                cli = por_nome[achados.pop()][0]
                via_nome = True
        if cli is None:
            fora.append(pub)
            continue
        proc = cli["processos"].get(pub["numero"])
        if proc is None:
            proc = cli["processos"][pub["numero"]] = {
                "tipo": tipo_pela_classe(pub["classe"]) or "outro", "origem": "djen",
                "despacho": "", "situacao": "", "observacao": "",
            }
        proc.setdefault("pubs", []).append(dict(pub, via_nome=via_nome))
    return fora


# ─────────────────────────── montagem do conteúdo ──────────────────

def montar(cli, rotulo, inicio=None, fim=None, esaj=None, dilig=None):
    """Transforma o cliente em blocos prontos para o PDF e para a planilha."""
    blocos, conferir, resumo = [], [], []
    procs = dict(cli["processos"])
    auxiliares = {}                                   # pai -> [precatórias]
    for n, p in list(procs.items()):
        if p.get("tipo") == "precatoria" and p.get("pai") in procs:
            procs[p["pai"]] = dict(procs[p["pai"]], pubs=procs[p["pai"]].get("pubs", []) + p.get("pubs", []))
            auxiliares.setdefault(p["pai"], []).append(n)
            del procs[n]
    for numero, proc in sorted(procs.items(),
                               key=lambda kv: (kv[1].get("origem") != "rodagem", kv[0])):
        pubs = sorted(proc.get("pubs", []), key=lambda p: p["data"])
        tipo_classe = tipo_pela_classe(pubs[-1]["classe"]) if pubs else None
        tipo = proc["tipo"]
        if tipo_classe in ("busca",) or (tipo == "outro" and tipo_classe):
            tipo = tipo_classe
        banco = next((b for b in (banco_da_publicacao(p, cli["nome"]) for p in pubs) if b), "")
        orgao = next((p["orgao"] for p in reversed(pubs) if p["orgao"]), "")
        tribunal = next((p["tribunal"] for p in pubs if p["tribunal"]), "")

        if tipo == "busca":
            titulo = "Ação de busca e apreensão" + (" movida por " + banco if banco else "") + " (sua defesa)"
        elif tipo == "recurso":
            titulo = "Recurso no Tribunal" + (" — processo contra " + banco if banco else "")
        elif tipo == "cumprimento":
            titulo = "Cumprimento de sentença" + (" contra " + banco if banco else "")
        elif tipo == "revisional":
            titulo = "Ação revisional" + (" contra " + banco if banco else "")
        elif tipo == "apenso":
            titulo = "Processo ligado à sua ação (apensado)"
        else:
            titulo = "Processo" + (" — " + banco if banco else "")

        tipo_leitura = "busca" if tipo == "busca" else "revisional"
        _REPLICA_BUSCA = ("Nossa equipe protocolou uma nova manifestação, rebatendo os argumentos do banco.")
        brutos = []                                   # (iso, frase, motivo, via_nome)
        for p in pubs:
            frase, motivo = classificar(p, tipo_leitura, cli["nome"])
            brutos.append((p["data"], frase, motivo, p.get("via_nome"), p["classe"]))

        # movimentação do e-SAJ: o que não sai no Diário (contestação, petições...)
        ultima_fora_do_mes = None
        historico = []                                # tudo que o e-SAJ mostra, para a fase
        reg = (esaj or {}).get(numero)
        for aux in auxiliares.get(numero, []):          # movimentação da carta precatória
            r_aux = (esaj or {}).get(aux)
            if r_aux and r_aux.get("ok"):
                reg = dict(reg or {"ok": True}, movs=(reg or {}).get("movs", []) + r_aux.get("movs", []),
                           equipe=(reg or {}).get("equipe", []) + r_aux.get("equipe", []))
        if reg is not None:
            if tem_esaj(numero):
                tribunal = tribunal or "TJAL"
            if reg.get("fonte") == "astrea":
                if not reg.get("achou"):
                    conferir.append("processo não está no Astrea — cadastrar (%s)" % formatar_cnj(numero))
                for iso, frase in reg.get("equipe", []):
                    d = datetime.date.fromisoformat(iso)
                    if tipo_leitura == "busca" and frase.startswith("Nossa equipe protocolou a réplica"):
                        frase = _REPLICA_BUSCA
                    if d <= fim:
                        historico.append((iso, frase))
                    if inicio <= d <= fim:
                        brutos.append((iso, frase, None, False, ""))
            elif not reg.get("ok"):
                conferir.append("e-SAJ não respondeu (%s)" % formatar_cnj(numero))
            if reg.get("segredo"):
                conferir.append("segredo de justiça no e-SAJ (%s)" % formatar_cnj(numero))
            datas_djen = [datetime.date.fromisoformat(p["data"]) for p in pubs if p["data"]]
            for iso, texto in sorted(reg.get("movs", [])):
                tr = traduzir_movimento(texto, tipo_leitura)
                if tr is None:
                    continue
                frase, motivo, eh_decisao = tr
                d = datetime.date.fromisoformat(iso)
                if eh_decisao:
                    # o teor sai no DJEN logo depois; se saiu, vale o texto oficial
                    if any(0 <= (dj - d).days <= 10 for dj in datas_djen):
                        continue
                    pseudo = {"texto_norm": norm_texto(texto), "tipo_documento": texto[:40],
                              "classe": "", "orgao": orgao}
                    frase, motivo = classificar(pseudo, tipo_leitura, cli["nome"])
                    if motivo == "NÃO CLASSIFICADA" or frase.startswith("O cartório deu andamento"):
                        continue
                if d <= fim:
                    historico.append((iso, frase))
                if inicio <= d <= fim:
                    brutos.append((iso, frase, motivo, False, ""))
                elif d < inicio:
                    ultima_fora_do_mes = (iso, frase)

        eventos, vistos = [], set()
        # no mesmo dia, "foi enviado ao juiz" vem ANTES do que o juiz decidiu
        def _ordem(iso, frase):
            return (iso, 0 if frase.startswith("O processo foi enviado ao juiz") else 1)
        for iso, frase, motivo, via_nome, _cl in sorted(brutos, key=lambda b: _ordem(b[0], b[1])):
            if (iso, frase) in vistos:
                continue
            vistos.add((iso, frase))
            eventos.append((data_br(iso), frase))
            if motivo:
                conferir.append("%s (%s)" % (motivo, formatar_cnj(numero)))
            if via_nome:
                conferir.append("vinculado pelo NOME (%s)" % formatar_cnj(numero))
            pass
        # A peça da equipe e a juntada que o tribunal registra são o MESMO fato: some a
        # juntada correspondente (só a do mesmo tipo — a contestação do banco fica).
        _MESMO_FATO = [
            (r"réplica|rebatendo os argumentos", r"Foi juntada uma petição|Apresentamos a nossa resposta|"
                                                r"O banco respondeu à defesa"),
            (r"sua defesa", r"Foi juntada uma petição|Apresentamos a sua defesa"),
            (r"recurso|embargos", r"Foi apresentado recurso|Foi juntada uma petição"),
            (r"contrarrazões", r"Foram apresentadas as respostas ao recurso|Foi juntada uma petição"),
            (r"documentos|manifestação|provas|complemento", r"Foi juntada uma petição|Apresentamos uma manifestação"),
        ]
        def _dt(d):
            return datetime.datetime.strptime(d, "%d/%m/%Y").date()
        remover = set()
        for i, (d, f) in enumerate(eventos):
            if not f.startswith("Nossa equipe"):
                continue
            alvo = next((j for k, j in _MESMO_FATO if re.search(k, f)), None)
            if not alvo:
                continue
            for j, (d2, f2) in enumerate(eventos):
                if j not in remover and re.match(alvo, f2) and abs((_dt(d2) - _dt(d)).days) <= 3:
                    remover.add(j)
                    break
        eventos = [e for j, e in enumerate(eventos) if j not in remover]
        # "enviado ao juiz" some quando o juiz já se manifestou no mesmo dia
        eventos = [(d, f) for d, f in eventos
                   if not (f.startswith("O processo foi enviado ao juiz")
                           and any(x[0] == d and x[1].startswith("O juiz") for x in eventos))]
        # "enviado ao juiz" repetido no mês vira uma linha só (a mais recente)
        eventos = [e for i, e in enumerate(eventos)
                   if not (e[1].startswith("O processo foi enviado ao juiz")
                           and any(x[1] == e[1] for x in eventos[i + 1:]))]

        resumo.extend("%s: %s" % (d[:5], f.split(".")[0]) for d, f in eventos)
        diligencias = [(data_br(iso)[:5], hora, frase)
                       for iso, hora, frase, _txt, _tit in diligencias_do_mes((dilig or {}).get(numero, []),
                                                                             inicio, fim)] if inicio else []
        for d, _h, _f in diligencias:
            conferir.append("DILIGÊNCIA %s — conferir o texto (%s)" % (d, formatar_cnj(numero)))
            resumo.append("%s: Diligência da equipe" % d)
        situacao, explica, proximo = fase_atual(dict(proc, tipo=tipo if tipo in ("busca",) else "revisional"))
        if tipo in ("recurso",):
            situacao, explica, proximo = _FASE_REV["RECURSO"]
        # a fase sai do último evento que a indica — no mês ou antes dele (e-SAJ)
        # julgamento de agravo interno/embargos não encerra o recurso principal
        linha_do_tempo = sorted(historico + [(iso, f) for iso, f, _, _, cl in brutos
                                             if not (re.search(_INCIDENTAL, norm_texto(cl))
                                                     and f.startswith("O Tribunal"))],
                                key=lambda x: _ordem(x[0], x[1]))
        pelo_evento = fase_pelo_evento(linha_do_tempo)
        if pelo_evento:
            situacao, explica, proximo = pelo_evento
            if situacao.startswith("O recurso está aguardando julgamento"):
                d = next((re.search(r"do dia (\d\d/\d\d/\d{4})", f).group(1)
                          for _, f in reversed(linha_do_tempo) if re.search(r"do dia \d\d/\d\d/\d{4}", f)), None)
                if d:
                    passou = datetime.datetime.strptime(d, "%d/%m/%Y").date() < datetime.date.today()
                    proximo = (("O julgamento estava marcado para %s. Avisaremos o resultado assim que "
                                "for publicado.") if passou else
                               "O recurso será julgado na sessão de %s. Avisaremos o resultado.") % d
        assunto = assunto_do_recurso([p["texto_norm"] for p in pubs]) if tipo == "recurso" else []
        if assunto:
            lista = assunto[0] if len(assunto) == 1 else ", ".join(assunto[:-1]) + " e " + assunto[-1]
            eventos = [(d, f.replace("A decisão que o banco queria mudar continua valendo.",
                                     "Continua valendo a decisão a seu favor sobre %s." % lista))
                       for d, f in eventos]
        # "o relator pediu para pautar X" some quando a pauta de X já saiu no mesmo mês
        eventos = [e for i, e in enumerate(eventos)
                   if not (e[1].startswith("O relator pediu para colocar ")
                           and any(x[1].lower().startswith(e[1][len("O relator pediu para colocar "):]
                                                          .split(" na pauta")[0].lower() + " entrou na pauta")
                                   for x in eventos[i + 1:]))]
        blocos.append({
            "titulo": titulo,
            "numero": formatar_cnj(numero),
            "local": ", ".join(x for x in (orgao, tribunal) if x),
            "situacao": situacao,
            "explica": explica,
            # só no TJAL (e-SAJ) vemos TODA a movimentação; nos demais, só o Diário
            "ve_tudo": bool(reg and reg.get("ok")),
            "assunto": assunto,
            "proximo": proximo,
            "eventos": eventos,
            "diligencias": diligencias,
            "ultima": ultima_fora_do_mes and (data_br(ultima_fora_do_mes[0]), ultima_fora_do_mes[1]),
            "links": [p["link"] for p in pubs if p.get("link")],
            "tem_rodagem": proc.get("origem") == "rodagem",
        })

    # Recurso sem publicação no mês só polui o relatório: fica só o que é da rodagem
    # ou o que teve novidade.
    blocos = [b for b in blocos if b["tem_rodagem"] or b["eventos"] or b["diligencias"]]
    return {
        "blocos": blocos,
        "novidade": any(b["eventos"] or b["diligencias"] for b in blocos),
        "conferir": list(dict.fromkeys(conferir)),
        "resumo": " | ".join(resumo) if resumo else "Sem movimentação no mês.",
        "links": [l for b in blocos for l in b["links"]][:3],
    }


# ─────────────────────────── contatos ──────────────────────────────

def telefones_astrea():
    """{cpf: telefone} do banco do Cadastro Astrea, quando existir nesta máquina."""
    if not ASTREA_DB.exists():
        return {}
    out = {}
    try:
        con = sqlite3.connect("file:%s?mode=ro" % ASTREA_DB, uri=True)
        for (dados,) in con.execute("select dados_json from processamentos where dados_json like '%telefone%'"):
            try:
                p = json.loads(dados).get("pessoa") or {}
                cpf = digitos((p.get("cpf") or {}).get("valor"))
                tel = digitos((p.get("telefone") or {}).get("valor"))
                if cpf and len(tel) >= 10:
                    out[cpf] = tel
            except (ValueError, AttributeError):
                continue
        con.close()
    except sqlite3.Error:
        return {}
    return out


LOTES = 20     # dias úteis de envio por mês: ~20 relatórios/dia (uma pessoa na controladoria)
_DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def _pascoa(ano):
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    return datetime.date(ano, mes, ((h + l - 7 * m + 114) % 31) + 1)


def feriados(ano):
    """Feriados nacionais (fixos + Carnaval, Sexta-feira Santa e Corpus Christi).
    Feriados de Alagoas/Maceió não entram — se cair num deles, envie no dia seguinte."""
    p = _pascoa(ano)
    fixos = [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)]
    return ({datetime.date(ano, m, d) for m, d in fixos} |
            {p - datetime.timedelta(days=48), p - datetime.timedelta(days=47),
             p - datetime.timedelta(days=2), p + datetime.timedelta(days=60)})


def dias_uteis(ano, mes):
    d = datetime.date(ano, mes, 1)
    out = []
    folgas = feriados(ano)
    while d.month == mes:
        if d.weekday() < 5 and d not in folgas:
            out.append(d)
        d += datetime.timedelta(days=1)
    return out


def data_do_lote(lote, ano_ref, mes_ref):
    """Lote 1..20 -> data de envio: o N-ésimo dia útil do mês SEGUINTE ao de referência."""
    ano, mes = (ano_ref + 1, 1) if mes_ref == 12 else (ano_ref, mes_ref + 1)
    dias = dias_uteis(ano, mes)
    return dias[min(lote, len(dias)) - 1]


 ASAAS_RELATORIOS = PASTA / "_entrada" / "asaas"
CONTRATOS_CSV = PASTA / "_entrada" / "DADOS CONTRATOS - CONSOLIDADO 2023-2026.csv"

def _ultimo(padrao):
    arqs = sorted(ASAAS_RELATORIOS.glob(padrao)) if ASAAS_RELATORIOS.exists() else []
    return arqs[-1] if arqs else None


_ESTADOS = ("ALAGOAS", "BAHIA", "PERNAMBUCO", "SERGIPE", "PARAIBA", "SAO PAULO", "MINAS GERAIS", "GOIAS",
            "MACEIO", "VEICULO APREENDIDO", "REVISIONAL", "BUSCA E APREENSAO")


def _nucleo(n):
    """Nome sem cidade/estado/anotação no fim e sem partículas — para comparar cobrança x rodagem."""
    n = norm(n)
    for e in _ESTADOS:
        n = re.sub(r"\b%s\b" % e, " ", n)
    n = re.sub(r"\b(ME|EPP|LTDA)\s*$", " ", n)
    return [t for t in n.split() if t not in ("DA", "DE", "DO", "DAS", "DOS", "E")]


def casar_nome(nome, candidatos):
    """Melhor candidato para `nome` (mesmo 1º nome e quase todo o resto igual), ou None."""
    import difflib
    a = _nucleo(nome)
    if not a:
        return None
    melhor, nota_m = None, 0.0
    for c in candidatos:
        b = _nucleo(c)
        if not b or b[0] != a[0]:
            continue
        if a == b or set(a) <= set(b) or set(b) <= set(a):
            nota = 0.99 if min(len(a), len(b)) >= 3 or a == b else 0.0
        else:
            nota = difflib.SequenceMatcher(None, " ".join(a), " ".join(b)).ratio()
        if nota > nota_m:
            melhor, nota_m = c, nota
    return melhor if nota_m >= 0.9 else None


def vencimentos(ano_envio, mes_envio):
    """{nome normalizado: data do vencimento no mês de envio}.

    Fonte 1: a coleta diária do ASAAS (previsao_*.csv), com as parcelas a vencer.
    Fonte 2 (clientes da Conta Azul, desde jun/2026): DADOS CONTRATOS — dia da 1ª
    parcela, se o parcelamento ainda não terminou."""
    import csv
    out = {}
    arq = _ultimo("previsao_*.csv")
    if arq:
        for l in csv.DictReader(open(arq, encoding="utf-8-sig"), delimiter=";"):
            try:
                d = datetime.date.fromisoformat(l["vencimento"])
            except ValueError:
                continue
            if (d.year, d.month) == (ano_envio, mes_envio):
                n = norm(l["cliente"])
                out[n] = min(out.get(n, d), d)
    if CONTRATOS_CSV.exists():
        for l in csv.DictReader(open(CONTRATOS_CSV, encoding="utf-8-sig"), delimiter=";"):
            n = norm(l.get("Cliente"))
            if n in out:
                continue
            try:
                primeira = datetime.date.fromisoformat((l.get("1ª parcela") or "")[:10])
            except ValueError:
                continue
            try:
                ultima = datetime.date.fromisoformat((l.get("Última parcela") or "")[:10])
            except ValueError:
                qtd = int(float(l.get("Qtd parcelas") or 0) or 0)
                m = primeira.month - 1 + max(qtd - 1, 0)
                ultima = datetime.date(primeira.year + m // 12, m % 12 + 1, 1)
            if (ultima.year, ultima.month) < (ano_envio, mes_envio) or \
                    (primeira.year, primeira.month) > (ano_envio, mes_envio):
                continue
            ult_dia = (datetime.date(ano_envio, mes_envio, 28) + datetime.timedelta(days=4)).replace(day=1) \
                - datetime.timedelta(days=1)
            out[n] = datetime.date(ano_envio, mes_envio, min(primeira.day, ult_dia.day))
    return out


def em_atraso():
    """{cpf ou nome normalizado: (qtd, vencimento mais antigo, total)} do ASAAS."""
    import csv
    arq = _ultimo("em_atraso_*.csv")
    out = {}
    if not arq:
        return out, None
    for l in csv.DictReader(open(arq, encoding="utf-8-sig"), delimiter=";"):
        valor = float((l.get("valor") or "0").replace(".", "").replace(",", ".") or 0)
        venc = l.get("vencimento") or ""
        for chave in filter(None, (digitos(l.get("cpf_cnpj")), norm(l.get("cliente")))):
            q, v, t = out.get(chave, (0, venc, 0.0))
            out[chave] = (q + 1, min(v, venc) if v else venc, t + valor)
    return out, arq.name


def distribuir_envio(clientes_ordem, venc, manual, ano_ref, mes_ref):
    """Dia de envio de cada cliente: ~3 dias úteis ANTES do vencimento da parcela,
    no máximo ~20 por dia. Sem parcela no mês: preenche os dias mais vazios.
    Dia digitado à mão em CONTATOS sempre vence."""
    ano, mes = (ano_ref + 1, 1) if mes_ref == 12 else (ano_ref, mes_ref + 1)
    dias = dias_uteis(ano, mes)[:LOTES]
    cap = -(-len(clientes_ordem) // len(dias)) + 2
    carga = {i: 0 for i in range(len(dias))}
    lote = {}
    for chave in clientes_ordem:                       # 1º: escolhas manuais
        if manual.get(chave) in range(1, len(dias) + 1):
            lote[chave] = manual[chave] - 1
            carga[lote[chave]] += 1
    com_venc = sorted((c for c in clientes_ordem if c not in lote and venc.get(c)), key=lambda c: venc[c])
    for chave in com_venc:                             # 2º: quem tem parcela no mês
        alvo = max([i for i, d in enumerate(dias) if (venc[chave] - d).days >= 3] or [0])
        ordem = list(range(alvo, -1, -1)) + list(range(alvo + 1, len(dias)))
        i = next((i for i in ordem if carga[i] < cap), min(carga, key=carga.get))
        lote[chave] = i
        carga[i] += 1
    for chave in clientes_ordem:                       # 3º: os demais, nos dias mais leves
        if chave not in lote:
            i = min(carga, key=lambda k: (carga[k], k))
            lote[chave] = i
            carga[i] += 1
    return {c: (i + 1, dias[i]) for c, i in lote.items()}


def atualizar_contatos(clientes):
    """Mantém a planilha de contatos: acrescenta clientes novos, nunca apaga nem
    sobrescreve o que a Eduarda digitou. Devolve {chave: telefone}."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    linhas = {}
    if CONTATOS.exists():
        wb = openpyxl.load_workbook(CONTATOS)
        ws = wb.active
        for r in ws.iter_rows(min_row=2, values_only=True):
            if not r or not (r[0] or r[1]):
                continue
            chave = digitos(r[0]) if cpf_valido(r[0]) else norm(r[1])
            lote = r[4] if len(r) > 4 else None
            try:
                lote = int(lote) if lote not in (None, "") else None
            except (TypeError, ValueError):
                lote = None
            linhas[chave] = [r[0] or "", r[1] or "", r[2] or "", r[3] or "", lote]
    astrea = telefones_astrea()
    novos = 0
    for cli in clientes.values():
        if cli["chave"] not in linhas:
            cpf_fmt = ("%s.%s.%s-%s" % (cli["cpf"][:3], cli["cpf"][3:6], cli["cpf"][6:9], cli["cpf"][9:])
                       if cli["cpf"] else "")
            linhas[cli["chave"]] = [cpf_fmt, cli["nome"], "", "", None]
            novos += 1
        reg = linhas[cli["chave"]]
        if not digitos(reg[2]) and cli["cpf"] in astrea:
            t = astrea[cli["cpf"]]
            reg[2] = "(%s) %s-%s" % (t[-11:-9], t[-9:-4], t[-4:]) if len(t) >= 11 else t
            reg[3] = reg[3] or "telefone puxado do Cadastro Astrea"

    # DIA DO ENVIO: vazio = automático (pelo vencimento da parcela). Número de 1 a 20
    # digitado pela Eduarda = aquele dia útil, sempre.

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CONTATOS"
    ws.append(["CPF", "CLIENTE", "TELEFONE (WHATSAPP)", "OBSERVAÇÃO",
               "DIA DO ENVIO (vazio = automático; 1 a %d = dia útil fixo)" % LOTES])
    for reg in sorted(linhas.values(), key=lambda r: norm(r[1])):
        ws.append(reg)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=MARROM[1:])
        c.alignment = Alignment(vertical="center")
    for col, w in zip("ABCDE", (17, 44, 22, 40, 22)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    try:
        wb.save(CONTATOS)
    except PermissionError:
        print("   ⚠ CONTATOS DOS CLIENTES.xlsx está aberta — feche para eu acrescentar os novos.")
    return {k: digitos(v[2]) for k, v in linhas.items()}, novos, {k: v[4] for k, v in linhas.items()}


# ─────────────────────────── PDF ───────────────────────────────────

def _fontes():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    base = Path("/System/Library/Fonts/Supplemental")
    try:
        pdfmetrics.registerFont(TTFont("Georgia", str(base / "Georgia.ttf")))
        pdfmetrics.registerFont(TTFont("Georgia-B", str(base / "Georgia Bold.ttf")))
        pdfmetrics.registerFont(TTFont("Arial", str(base / "Arial.ttf")))
        pdfmetrics.registerFont(TTFont("Arial-B", str(base / "Arial Bold.ttf")))
        pdfmetrics.registerFont(TTFont("Arial-I", str(base / "Arial Italic.ttf")))
        return "Georgia", "Georgia-B", "Arial", "Arial-B", "Arial-I"
    except Exception:
        return "Times-Roman", "Times-Bold", "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


def gerar_pdf(destino, cli, conteudo, ano, mes, nota):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, KeepTogether)

    SERIF, SERIF_B, SANS, SANS_B, SANS_I = _fontes()
    marrom = colors.HexColor(MARROM)
    bege = colors.HexColor("#F6F0EA")
    cinza = colors.HexColor("#5A4A3F")

    st = {
        "titulo": ParagraphStyle("t", fontName=SERIF_B, fontSize=15, leading=19, textColor=marrom),
        "sub": ParagraphStyle("s", fontName=SANS, fontSize=9.5, leading=13, textColor=cinza),
        "h": ParagraphStyle("h", fontName=SERIF_B, fontSize=11.5, leading=15, textColor=marrom),
        "meta": ParagraphStyle("m", fontName=SANS, fontSize=8.5, leading=11, textColor=cinza),
        "rot": ParagraphStyle("r", fontName=SANS_B, fontSize=9, leading=12, textColor=marrom),
        "p": ParagraphStyle("p", fontName=SANS, fontSize=10, leading=14, textColor=colors.HexColor("#2B211B")),
        "ev": ParagraphStyle("e", fontName=SANS, fontSize=10, leading=14, leftIndent=0,
                             textColor=colors.HexColor("#2B211B")),
        "nota": ParagraphStyle("n", fontName=SANS, fontSize=10, leading=14, textColor=colors.HexColor("#2B211B")),
        "rodape": ParagraphStyle("f", fontName=SANS_I, fontSize=7.5, leading=10, textColor=cinza),
    }
    mes_txt = MESES[mes - 1]

    def cabecalho_rodape(canvas, doc):
        canvas.saveState()
        w, h = A4
        logo = TIMBRE / "logo.png"
        if logo.exists():
            lw = 52 * mm
            canvas.drawImage(str(logo), 20 * mm, h - 12 * mm - lw * 190 / 596, width=lw,
                             height=lw * 190 / 596, mask="auto", preserveAspectRatio=True)
        canvas.setStrokeColor(marrom)
        canvas.setLineWidth(0.6)
        canvas.line(20 * mm, h - 33 * mm, w - 20 * mm, h - 33 * mm)
        rod = TIMBRE / "rodape.png"
        if rod.exists():
            rw = 120 * mm
            canvas.drawImage(str(rod), 20 * mm, 9 * mm, width=rw, height=rw * 65 / 1037,
                             mask="auto", preserveAspectRatio=True)
        canvas.setFont(SANS, 7.5)
        canvas.setFillColor(cinza)
        canvas.drawRightString(w - 20 * mm, 10.5 * mm, "Página %d" % doc.page)
        canvas.restoreState()

    doc = SimpleDocTemplate(str(destino), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=38 * mm, bottomMargin=22 * mm,
                            title="Relatório processual — %s/%d — %s" % (mes_txt, ano, cli["nome"]),
                            author="Caroline Macedo Advocacia & Consultoria")
    E = []
    E.append(Paragraph("Relatório do seu processo — %s de %d" % (mes_txt.capitalize(), ano), st["titulo"]))
    E.append(Spacer(1, 3))
    E.append(Paragraph("Cliente: <b>%s</b> &nbsp;·&nbsp; Emitido em %s"
                       % (html.escape(cli["nome"]), datetime.date.today().strftime("%d/%m/%Y")), st["sub"]))
    E.append(Spacer(1, 10))
    primeiro = cli["nome"].split()[0] if cli["nome"] else ""
    E.append(Paragraph(
        "Olá, %s! Este é o resumo mensal do andamento do seu processo, preparado pela nossa equipe "
        "com base nas publicações oficiais da Justiça." % html.escape(primeiro), st["p"]))
    E.append(Spacer(1, 10))

    for b in conteudo["blocos"]:
        corpo = [Paragraph(html.escape(b["titulo"]), st["h"]),
                 Paragraph("Processo nº %s%s" % (b["numero"], (" · " + html.escape(b["local"])) if b["local"] else ""),
                           st["meta"]),
                 Spacer(1, 6),
                 Paragraph("SITUAÇÃO ATUAL", st["rot"]),
                 Paragraph("<b>%s</b>" % html.escape(b["situacao"]), st["p"]),
                 Spacer(1, 6),
                 Paragraph("O QUE ISSO QUER DIZER", st["rot"]),
                 Paragraph(html.escape(b["explica"]), st["p"])]
        if b.get("assunto"):
            itens = b["assunto"]
            lista = itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]
            corpo += [Spacer(1, 6), Paragraph("SOBRE O QUE É O RECURSO", st["rot"]),
                      Paragraph(html.escape("Neste recurso se discute %s." % lista), st["p"])]
        corpo += [Spacer(1, 6), Paragraph("O QUE ACONTECEU EM %s" % mes_txt.upper(), st["rot"])]
        if b["eventos"]:
            for d, frase in b["eventos"]:
                corpo.append(Paragraph("<b>%s</b> — %s" % (d[:5], html.escape(frase)), st["ev"]))
        else:
            corpo.append(Paragraph(
                ("Não houve movimentação no processo neste mês. " if b.get("ve_tudo") else
                 "Não houve publicação oficial da Justiça sobre o processo neste mês. ") +
                "Isso é normal: a Justiça tem prazos próprios e há períodos em que o processo aguarda "
                "a vez de ser analisado. Nossa equipe acompanha o processo continuamente.", st["p"]))
            if b.get("ultima"):
                corpo.append(Paragraph("<i>Última movimentação, em %s: %s</i>"
                                       % (b["ultima"][0], html.escape(b["ultima"][1])), st["ev"]))
        if b.get("diligencias"):
            # pedido da Caroline (02/10/2026): o cliente leigo não sabe o que é diligência
            corpo += [Spacer(1, 6), Paragraph("DILIGÊNCIAS DA NOSSA EQUIPE", st["rot"]),
                      Paragraph("<i>Diligência é quando a nossa equipe procura diretamente a vara onde está o "
                                "seu processo — pessoalmente, por telefone ou pelo balcão virtual — para "
                                "acompanhar de perto, pedir informações e cobrar andamento. É um trabalho "
                                "a mais que fazemos para que o seu processo não fique parado.</i>", st["ev"]),
                      Spacer(1, 3)]
            for d, h, frase in b["diligencias"]:
                corpo.append(Paragraph("<b>%s, às %s</b> — %s" % (d, h, html.escape(frase)), st["ev"]))
        corpo += [Spacer(1, 6), Paragraph("PRÓXIMO PASSO", st["rot"]),
                  Paragraph(html.escape(b["proximo"]), st["p"])]
        caixa = Table([[corpo]], colWidths=[170 * mm])
        caixa.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bege),
            ("LINEBEFORE", (0, 0), (0, -1), 2.5, marrom),
            ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ]))
        E += [KeepTogether([caixa]), Spacer(1, 10)]

    if nota:
        E.append(KeepTogether([Paragraph("RECADO DA EQUIPE", st["rot"]),
                               Paragraph(html.escape(nota).replace("\n", "<br/>"), st["nota"]),
                               Spacer(1, 10)]))

    E.append(Paragraph(
        "Ficou com alguma dúvida? Fale com a gente pelo WhatsApp %s. Estamos à disposição."
        % WHATSAPP_ESCRITORIO, st["p"]))
    E.append(Spacer(1, 8))
    E.append(Paragraph(
        "Relatório informativo elaborado a partir do Diário de Justiça Eletrônico Nacional (DJEN/CNJ) "
        "e do acompanhamento interno do escritório. Não substitui a análise individual do advogado.",
        st["rodape"]))
    doc.build(E, onFirstPage=cabecalho_rodape, onLaterPages=cabecalho_rodape)


# ─────────────────────────── planilha de controle ──────────────────

COLS = ["Nº", "DIA DE ENVIO", "VENCIMENTO DA PARCELA", "CLIENTE", "CPF", "TELEFONE", "WHATSAPP",
        "FINANCEIRO (INTERNO)", "NOVIDADE NO MÊS?", "CONFERIR ANTES DE ENVIAR",
        "RESUMO DO MÊS", "PROCESSOS", "NOTA PARA O CLIENTE (sai no PDF)", "ENVIADO?", "DATA DO ENVIO",
        "VER PUBLICAÇÃO", "CHAVE"]


def ler_controle_anterior(caminho):
    """Notas, 'enviado' e data já digitados pela Eduarda — sobrevivem a cada nova geração."""
    if not caminho.exists():
        return {}
    import openpyxl
    wb = openpyxl.load_workbook(caminho)
    ws = wb["CLIENTES"] if "CLIENTES" in wb.sheetnames else wb.active
    cab = [c.value for c in ws[1]]
    ix = {n: cab.index(n) for n in cab if n}
    out = {}
    for r in ws.iter_rows(min_row=2, values_only=True):
        if "CHAVE" not in ix or not r[ix["CHAVE"]]:
            continue
        out[str(r[ix["CHAVE"]])] = {
            "nota": r[ix["NOTA PARA O CLIENTE (sai no PDF)"]] or "",
            "enviado": r[ix["ENVIADO?"]] or "",
            "data_envio": r[ix["DATA DO ENVIO"]] or "",
        }
    return out


def link_whatsapp(tel, nome, ano, mes):
    d = digitos(tel)
    if len(d) < 10:
        return ""
    if not d.startswith("55"):
        d = "55" + d
    msg = ("Olá, %s! Aqui é a Eduarda, do escritório Caroline Macedo Advocacia. "
           "Segue o relatório com o andamento do seu processo referente a %s/%d. "
           "Qualquer dúvida, estou à disposição." % (nome.split()[0], MESES[mes - 1], ano))
    return "https://wa.me/%s?text=%s" % (d, urllib.parse.quote(msg))


def salvar_controle(caminho, linhas, fora, sem_processo, ano, mes):
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.formatting.rule import FormulaRule

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CLIENTES"
    ws.append(COLS)
    for l in linhas:
        ws.append([l.get(c, "") for c in COLS])
    cab_fill = PatternFill("solid", fgColor=MARROM[1:])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = cab_fill
        c.alignment = Alignment(wrap_text=True, vertical="center")
    def L(nome):
        return openpyxl.utils.get_column_letter(COLS.index(nome) + 1)
    larg = [5, 15, 12, 34, 15, 17, 16, 30, 11, 34, 70, 28, 40, 11, 13, 16, 4]
    for i, w in enumerate(larg):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i + 1)].width = w
    ws.column_dimensions[L("CHAVE")].hidden = True
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
        wa, pub = row[COLS.index("WHATSAPP")], row[COLS.index("VER PUBLICAÇÃO")]
        if wa.value:
            wa.hyperlink, wa.value, wa.font = wa.value, "Abrir conversa", Font(color="1155CC", underline="single")
        if pub.value:
            pub.hyperlink, pub.value, pub.font = pub.value, "Abrir", Font(color="1155CC", underline="single")
    dv = DataValidation(type="list", formula1='"SIM,NÃO"', allow_blank=True)
    ws.add_data_validation(dv)
    env, conf, ult_col = L("ENVIADO?"), L("CONFERIR ANTES DE ENVIAR"), L("VER PUBLICAÇÃO")
    dv.add("%s2:%s%d" % (env, env, max(2, ws.max_row)))
    ultima = max(2, ws.max_row)
    ws.conditional_formatting.add("A2:%s%d" % (ult_col, ultima), FormulaRule(
        formula=['$%s2="SIM"' % env], fill=PatternFill("solid", fgColor="E3F1E0")))
    ws.conditional_formatting.add("%s2:%s%d" % (conf, conf, ultima), FormulaRule(
        formula=['LEN($%s2)>0' % conf], fill=PatternFill("solid", fgColor="FCE8D5")))
    # dias alternados em faixas leves, para a Eduarda enxergar onde começa cada lote
    faixa = PatternFill("solid", fgColor="F6F0EA")
    for row in ws.iter_rows(min_row=2):
        dia = str(row[1].value or "")
        if dia[:2].isdigit() and int(dia[:2]) % 2 == 0:
            for c in row[:3]:
                c.fill = faixa
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = "A1:%s%d" % (ult_col, ultima)

    # Agenda: quantos relatórios e quantos itens para conferir em cada dia de envio
    wa = wb.create_sheet("AGENDA", 0)
    wa.append(["DIA DE ENVIO", "RELATÓRIOS", "COM ITEM PARA CONFERIR", "COM NOVIDADE", "JÁ ENVIADOS",
               "EM ATRASO COM O ESCRITÓRIO"])
    por_dia = {}
    for l in linhas:
        d = por_dia.setdefault(l["DIA DE ENVIO"], [0, 0, 0, 0, 0])
        d[0] += 1
        d[1] += 1 if l["CONFERIR ANTES DE ENVIAR"] else 0
        d[2] += 1 if l["NOVIDADE NO MÊS?"] == "SIM" else 0
        d[3] += 1 if str(l.get("ENVIADO?") or "").upper() == "SIM" else 0
        d[4] += 1 if str(l.get("FINANCEIRO (INTERNO)") or "").startswith("EM ATRASO") else 0
    for dia in sorted(por_dia):
        wa.append([dia] + por_dia[dia])
    for c in wa[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), cab_fill
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for col, w in zip("ABCDEF", (22, 13, 16, 14, 13, 16)):
        wa.column_dimensions[col].width = w
    wa.freeze_panes = "A2"
    # Quem está em atraso com o escritório — uso interno, nunca vai ao cliente
    wt = wb.create_sheet("EM ATRASO (INTERNO)", 1)
    wt.append(["DIA DE ENVIO", "CLIENTE", "TELEFONE", "SITUAÇÃO NO ASAAS"])
    for l in linhas:
        if str(l.get("FINANCEIRO (INTERNO)") or "").startswith(("EM ATRASO", "VERIFICAR")):
            wt.append([l["DIA DE ENVIO"], l["CLIENTE"], l["TELEFONE"], l["FINANCEIRO (INTERNO)"]])
    for c in wt[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), cab_fill
    for col, w in zip("ABCD", (18, 40, 17, 60)):
        wt.column_dimensions[col].width = w
    wt.freeze_panes = "A2"
    wb.active = 2

    # Uma linha por processo: são casos com publicação para a OAB do escritório que
    # não casaram com ninguém da rodagem — cliente a incluir, ou caso de outra área.
    ws2 = wb.create_sheet("FORA DA RODAGEM")
    ws2.append(["ÚLTIMA PUBLICAÇÃO", "PROCESSO", "TRIBUNAL", "CLASSE", "PARTES", "PUBLICAÇÕES NO MÊS",
                "TRECHO DA ÚLTIMA", "PUBLICAÇÃO"])
    grupos = {}
    for p in sorted(fora, key=lambda p: p["data"]):
        grupos.setdefault(p["numero"], []).append(p)
    for numero, ps in sorted(grupos.items(), key=lambda kv: kv[1][-1]["data"], reverse=True):
        ult = ps[-1]
        partes = "; ".join(dict.fromkeys(nome_bonito(n) for p in ps for n, _ in p["partes"]
                                         if "CAROLINE NEIVA" not in norm(n)))
        ws2.append([data_br(ult["data"]), formatar_cnj(numero), ult["tribunal"], nome_bonito(ult["classe"]),
                    partes, len(ps), ult["texto"][:300], ult["link"]])
    for c in ws2[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), cab_fill
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for col, w in zip("ABCDEFGH", (12, 27, 9, 28, 45, 12, 80, 14)):
        ws2.column_dimensions[col].width = w
    for row in ws2.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws2.freeze_panes = "A2"

    ws3 = wb.create_sheet("SEM Nº DE PROCESSO")
    ws3.append(["CLIENTE", "ABA DA RODAGEM"])
    for s in sem_processo:
        ws3.append([s["nome"], s["aba"]])
    for c in ws3[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), cab_fill
    ws3.column_dimensions["A"].width, ws3.column_dimensions["B"].width = 44, 22

    wb.save(caminho)


# ─────────────────────────── principal ─────────────────────────────

def mes_padrao(hoje=None):
    """Depois do dia 25, o relatório é do mês corrente; antes, do mês anterior."""
    hoje = hoje or datetime.date.today()
    if hoje.day >= 25:
        return hoje.year, hoje.month
    primeiro = hoje.replace(day=1) - datetime.timedelta(days=1)
    return primeiro.year, primeiro.month


def nome_arquivo(s):
    s = re.sub(r'[\\/:*?"<>|]', "", s)
    return " ".join(s.split())[:90]


def _reais(v):
    return ("%.2f" % v).replace(".", "X").replace(",", ".").replace("X", ",") if v < 1000 else \
        "{:,.2f}".format(v).replace(",", "X").replace(".", ",").replace("X", ".")


def nomes_no_asaas():
    """Todos os clientes com cobrança no ASAAS (a vencer, recebida ou projetada)."""
    import csv
    arq = _ultimo("previsao_*.csv")
    return {norm(l["cliente"]) for l in csv.DictReader(open(arq, encoding="utf-8-sig"), delimiter=";")} \
        if arq else set()


def contratos_por_nome():
    """{nome normalizado: linha mais recente do DADOS CONTRATOS}."""
    import csv
    out = {}
    if CONTRATOS_CSV.exists():
        for l in csv.DictReader(open(CONTRATOS_CSV, encoding="utf-8-sig"), delimiter=";"):
            out[norm(l.get("Cliente"))] = l
    return out


def todos_nomes_asaas():
    """Qualquer cliente que já apareceu numa coleta do ASAAS (previsão ou atraso)."""
    import csv
    nomes = set()
    if ASAAS_RELATORIOS.exists():
        for f in list(ASAAS_RELATORIOS.glob("previsao_*.csv")) + list(ASAAS_RELATORIOS.glob("em_atraso_*.csv")):
            for l in csv.DictReader(open(f, encoding="utf-8-sig"), delimiter=";"):
                nomes.add(norm(l.get("cliente")))
    return nomes


def parecido_no_asaas(nome, nomes_asaas):
    """Cadastro do ASAAS com grafia parecida (mesmo 1º nome, ~80% igual) — só para avisar."""
    import difflib
    a = _nucleo(nome)
    melhor, nota_m = None, 0.0
    for c in nomes_asaas:
        b = _nucleo(c)
        if not b or not a or b[0] != a[0]:
            continue
        nota = difflib.SequenceMatcher(None, " ".join(a), " ".join(b)).ratio()
        if nota > nota_m:
            melhor, nota_m = c, nota
    return melhor if nota_m >= 0.8 else None


def situacao_sem_asaas(nome, contratos, nomes_asaas, ano_env, mes_env):
    """Por que o cliente não tem cobrança no ASAAS — em vez de uma frase genérica.
    Começa com VERIFICAR quando algo não fecha e alguém precisa olhar."""
    k = norm(nome) if norm(nome) in contratos else casar_nome(nome, contratos)
    mesmo = norm(nome) if norm(nome) in nomes_asaas else casar_nome(nome, nomes_asaas)
    # já teve cobrança no ASAAS e hoje não tem nada a vencer nem vencido = pagou tudo lá
    if mesmo and not k:
        return "Sem parcela a vencer nem em atraso no ASAAS (provável contrato quitado)"
    parecido = None if mesmo else parecido_no_asaas(nome, nomes_asaas)
    aviso_par = " Há cadastro parecido no ASAAS: %s." % parecido if parecido else ""
    if not k:
        if parecido:
            return "VERIFICAR: não consta no DADOS CONTRATOS, mas há cadastro parecido no ASAAS (%s)" % parecido
        return "VERIFICAR: não consta no DADOS CONTRATOS nem no ASAAS"
    l = contratos[k]
    fech = (l.get("Mês de fechamento") or "")[:7]
    qtd = int(float(l.get("Qtd parcelas") or 0) or 0)
    if qtd == 0:
        return "Pagamento à vista (sem parcelas)"
    try:
        ultima = datetime.date.fromisoformat((l.get("Última parcela") or "")[:10])
    except ValueError:
        try:
            p1 = datetime.date.fromisoformat((l.get("1ª parcela") or "")[:10])
            m = p1.month - 1 + qtd - 1
            ultima = datetime.date(p1.year + m // 12, m % 12 + 1, 1)
        except ValueError:
            ultima = None
    if ultima and (ultima.year, ultima.month) < (ano_env, mes_env):
        return "Contrato quitado (última parcela %02d/%d)" % (ultima.month, ultima.year)
    if mesmo:
        return "Sem parcela a vencer nem em atraso no ASAAS (provável contrato quitado)"
    if fech >= "2026-06":
        return "Conta Azul: sem dados de pagamento (contrato de %s/%s)%s" % (fech[5:7], fech[:4], aviso_par)
    return ("VERIFICAR: contrato com parcelas em andamento, mas nenhuma cobrança no ASAAS%s"
            % (" — cadastro parecido: %s" % parecido if parecido else ""))


def _texto_atraso(reg, arq, no_asaas=True, sem_asaas=""):
    if not arq:
        return "lista de atrasos do ASAAS ainda não gerada"
    if not reg:
        return "em dia (ASAAS)" if no_asaas else (sem_asaas or "sem cobrança no ASAAS")
    qtd, desde, total = reg
    return "EM ATRASO: %d parcela%s desde %s (R$ %s)" % (qtd, "s" if qtd > 1 else "", data_br(desde),
                                                         _reais(total))


def executar(ano, mes, reconsultar=False):
    rotulo = rotulo_mes(ano, mes)
    saida = PASTA / rotulo
    pdfs = saida / "RELATÓRIOS (PDF)"
    dados = saida / "_dados"
    pdfs.mkdir(parents=True, exist_ok=True)
    dados.mkdir(exist_ok=True)
    controle = saida / ("CONTROLE DE ENVIO - %s.xlsx" % rotulo)

    rodagem = localizar_rodagem()
    print("\n1/5  Lendo a carteira: %s" % rodagem.name, flush=True)
    clientes, sem_processo = ler_rodagem(rodagem)
    print("     %d clientes na rodagem" % len(clientes))

    inicio = datetime.date(ano, mes, 1)
    fim = (inicio + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)
    fim = min(fim, datetime.date.today())
    cache = dados / "djen.json"
    if cache.exists() and not reconsultar:
        print("\n2/5  Usando as publicações já baixadas (%s)" % cache.name)
        brutos = json.loads(cache.read_text(encoding="utf-8"))
    else:
        print("\n2/5  Baixando as publicações de %s a %s no DJEN..." % (data_br(inicio), data_br(fim)),
              flush=True)
        brutos = baixar_djen(inicio, fim)
        cache.write_text(json.dumps(brutos, ensure_ascii=False), encoding="utf-8")
    pubs = [preparar(it) for it in brutos]
    fora = casar(clientes, pubs)
    print("     %d publicações · %d de clientes da rodagem · %d fora da rodagem"
          % (len(pubs), len(pubs) - len(fora), len(fora)))

    print("\n3/5  Movimentação no e-SAJ do TJAL (contestação, petições, conclusões...)", flush=True)
    numeros_esaj = sorted({n for c in clientes.values() for n in c["processos"] if tem_esaj(n)})
    esaj = baixar_esaj(numeros_esaj, dados / "esaj.json", reconsultar)
    print("     %d processos do TJAL consultados" % sum(1 for n in numeros_esaj if esaj.get(n, {}).get("ok")))

    print("\n     Andamentos dos demais tribunais pelo Astrea (PJe, eproc, Projudi)", flush=True)
    numeros_astrea = sorted({n for c in clientes.values() for n in c["processos"]
                             if len(n) == 20 and not tem_esaj(n)})
    astrea = baixar_astrea(numeros_astrea, dados, reconsultar)
    for n in numeros_astrea:
        if n in astrea:
            esaj[n] = converter_astrea(astrea[n])
    if astrea:
        print("     %d de %d encontrados no Astrea" % (sum(1 for n in numeros_astrea if astrea.get(n, {}).get("achou")),
                                                     sum(1 for n in numeros_astrea if n in astrea)))

    arq_dilig = dados / "diligencias.json"
    dilig = json.loads(arq_dilig.read_text(encoding="utf-8")) if arq_dilig.exists() else {}
    if dilig:
        print("     diligências lidas no Astrea: %d processos" % len(dilig))

    print("\n4/5  Atualizando a planilha de contatos...", flush=True)
    telefones, novos, lotes = atualizar_contatos(clientes)
    if novos:
        print("     %d cliente(s) novo(s) acrescentado(s) em CONTATOS DOS CLIENTES.xlsx" % novos)

    print("\n5/5  Gerando os relatórios...", flush=True)
    anterior = ler_controle_anterior(controle)
    for velho in pdfs.rglob("*.pdf"):
        velho.unlink()
    for pasta in sorted(pdfs.glob("*"), reverse=True):
        if pasta.is_dir() and not any(pasta.iterdir()):
            pasta.rmdir()
    ano_env, mes_env = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    venc_nome = vencimentos(ano_env, mes_env)
    venc = {}
    for c in clientes.values():
        chave_nome = norm(c["nome"]) if norm(c["nome"]) in venc_nome else casar_nome(c["nome"], venc_nome)
        venc[c["chave"]] = venc_nome.get(chave_nome) if chave_nome else None
    atraso, arq_atraso = em_atraso()
    asaas_nomes = nomes_no_asaas()
    contratos = contratos_por_nome()
    asaas_todos = todos_nomes_asaas()
    def _no_asaas(c):
        return norm(c["nome"]) in asaas_nomes or bool(casar_nome(c["nome"], asaas_nomes))
    nomes_atraso = [k for k in atraso if not k.isdigit()]
    def _atraso_de(c):
        if c["cpf"] and c["cpf"] in atraso:
            return atraso[c["cpf"]]
        k = norm(c["nome"]) if norm(c["nome"]) in atraso else casar_nome(c["nome"], nomes_atraso)
        return atraso.get(k) if k else None
    # A agenda do mês é CONGELADA na primeira geração: a atualização semanal do
    # financeiro não pode mudar ninguém de dia (quem paga adiantado perde o
    # "vencimento" no ASAAS). Escolha manual em CONTATOS e cliente novo ainda entram.
    arq_plano = dados / "plano_envio.json"
    congelado = json.loads(arq_plano.read_text(encoding="utf-8")) if arq_plano.exists() else {}
    manual = dict(lotes)
    for chave, n in congelado.items():
        if not manual.get(chave):
            manual[chave] = n
    plano = distribuir_envio([c["chave"] for c in sorted(clientes.values(), key=lambda c: norm(c["nome"]))],
                             venc, manual, ano, mes)
    arq_plano.write_text(json.dumps({k: v[0] for k, v in plano.items()}), encoding="utf-8")
    linhas = []
    for i, cli in enumerate(sorted(clientes.values(), key=lambda c: norm(c["nome"])), start=1):
        conteudo = montar(cli, rotulo, inicio, fim, esaj, dilig)
        if not conteudo["blocos"]:
            continue
        prev = anterior.get(cli["chave"], {})
        nota = str(prev.get("nota") or "").strip()
        lote, d_envio = plano[cli["chave"]]
        dia_txt = "%02d - %s (%s)" % (lote, d_envio.strftime("%d/%m"), _DIAS_SEMANA[d_envio.weekday()])
        pasta_dia = pdfs / ("DIA %02d - %s (%s)" % (lote, d_envio.strftime("%d-%m"), _DIAS_SEMANA[d_envio.weekday()]))
        pasta_dia.mkdir(exist_ok=True)
        gerar_pdf(pasta_dia / ("%s - %s.pdf" % (nome_arquivo(cli["nome"]), rotulo)), cli, conteudo,
                  ano, mes, nota)
        tel = telefones.get(cli["chave"], "")
        conferir = list(conteudo["conferir"])
        if not tel:
            conferir.append("sem telefone (preencher em CONTATOS)")
        linhas.append({
            "Nº": 0,
            "DIA DE ENVIO": dia_txt,
            "VENCIMENTO DA PARCELA": venc[cli["chave"]].strftime("%d/%m") if venc.get(cli["chave"]) else "",
            "FINANCEIRO (INTERNO)": _texto_atraso(
                _atraso_de(cli), arq_atraso, _no_asaas(cli),
                situacao_sem_asaas(cli["nome"], contratos, asaas_todos, ano_env, mes_env)
                if not _no_asaas(cli) else ""),
            "CLIENTE": cli["nome"],
            "CPF": cli["cpf"] and "%s.%s.%s-%s" % (cli["cpf"][:3], cli["cpf"][3:6], cli["cpf"][6:9], cli["cpf"][9:]),
            "TELEFONE": tel and ("(%s) %s-%s" % (tel[-11:-9], tel[-9:-4], tel[-4:]) if len(tel) >= 11 else tel),
            "WHATSAPP": link_whatsapp(tel, cli["nome"], ano, mes),
            "NOVIDADE NO MÊS?": "SIM" if conteudo["novidade"] else "não",
            "CONFERIR ANTES DE ENVIAR": "; ".join(c for c in conferir if not c.startswith("sem telefone")),
            "RESUMO DO MÊS": conteudo["resumo"],
            "PROCESSOS": "\n".join(b["numero"] for b in conteudo["blocos"]),
            "NOTA PARA O CLIENTE (sai no PDF)": nota,
            "ENVIADO?": prev.get("enviado", ""),
            "DATA DO ENVIO": prev.get("data_envio", ""),
            "VER PUBLICAÇÃO": conteudo["links"][0] if conteudo["links"] else "",
            "CHAVE": cli["chave"],
        })
        if len(linhas) % 50 == 0:
            print("     %d relatórios prontos..." % len(linhas), flush=True)

    linhas.sort(key=lambda l: (l["DIA DE ENVIO"], norm(l["CLIENTE"])))
    for i, l in enumerate(linhas, 1):
        l["Nº"] = i
    try:
        salvar_controle(controle, linhas, fora, sem_processo, ano, mes)
    except PermissionError:
        raise SystemExit("\n⚠ A planilha %s está aberta. Feche o Excel e rode de novo." % controle.name)

    com_nov = sum(1 for l in linhas if l["NOVIDADE NO MÊS?"] == "SIM")
    a_conferir = sum(1 for l in linhas if l["CONFERIR ANTES DE ENVIAR"])
    sem_tel = sum(1 for l in linhas if not l["TELEFONE"])
    print("\n" + "─" * 60)
    print("PRONTO — %s" % rotulo)
    print("  %d relatórios gerados (%d com novidade no mês, %d sem publicação)"
          % (len(linhas), com_nov, len(linhas) - com_nov))
    print("  %d para CONFERIR antes de enviar (coluna laranja)" % a_conferir)
    print("  %d sem telefone — preencher em CONTATOS DOS CLIENTES.xlsx" % sem_tel)
    print("  %d processos com publicação que NÃO estão na rodagem (aba FORA DA RODAGEM)"
          % len({p["numero"] for p in fora}))
    if sem_processo:
        print("  %d linha(s) da rodagem sem nº de processo (aba SEM Nº DE PROCESSO)" % len(sem_processo))
    qtd = {}
    for l in linhas:
        qtd[l["DIA DE ENVIO"]] = qtd.get(l["DIA DE ENVIO"], 0) + 1
    if qtd:
        print("  Envio dividido em %d dias úteis: de %d a %d relatórios por dia (aba AGENDA)"
              % (len(qtd), min(qtd.values()), max(qtd.values())))
    com_v = sum(1 for l in linhas if l["VENCIMENTO DA PARCELA"])
    print("  %d clientes com parcela no mês de envio: relatório sai ~3 dias úteis antes do vencimento" % com_v)
    if arq_atraso:
        print("  %d clientes EM ATRASO com o escritório (aba EM ATRASO — uso interno)"
              % sum(1 for l in linhas if l["FINANCEIRO (INTERNO)"].startswith("EM ATRASO")))
        print("  %d clientes com situação financeira a VERIFICAR (sem cobrança achada no ASAAS)"
              % sum(1 for l in linhas if l["FINANCEIRO (INTERNO)"].startswith("VERIFICAR")))
    else:
        print("  Lista de atrasos do ASAAS ainda não existe — sai na coleta das 7h do ASAAS")
    print("─" * 60)
    return saida, controle


def _ler_mes(texto, padrao):
    """Aceita 'setembro', 'setembro/2026', '09/2026', '9', '2026-09'."""
    t = norm(texto).lower()
    if not t and not digitos(texto):
        return padrao
    ano = padrao[0]
    m = re.search(r"(20\d\d)", texto)
    if m:
        ano = int(m.group(1))
    for i, nome in enumerate(MESES):
        if norm(nome).lower() in t:
            return ano, i + 1
    nums = [int(x) for x in re.findall(r"\d+", texto) if len(x) <= 2]
    if nums and 1 <= nums[0] <= 12:
        return ano, nums[0]
    return None


def interativo():
    print("=" * 60)
    print("  RELATÓRIOS MENSAIS AOS CLIENTES")
    print("  Caroline Macedo Advocacia & Consultoria")
    print("=" * 60)
    padrao = mes_padrao()
    while True:
        r = input("\nDe qual mês é o relatório? [Enter = %s/%d]: "
                  % (MESES[padrao[1] - 1], padrao[0])).strip()
        escolha = _ler_mes(r, padrao)
        if escolha:
            break
        print("Não entendi. Escreva o nome do mês (ex.: outubro) ou mm/aaaa.")
    ano, mes = escolha
    reconsultar = False
    cache = PASTA / rotulo_mes(ano, mes) / "_dados" / "djen.json"
    if cache.exists():
        print("\nOs relatórios de %s já foram gerados antes. O que você quer fazer?" % rotulo_mes(ano, mes))
        print("  1 - Refazer os PDFs com as NOTAS que você escreveu na planilha (rápido)")
        print("  2 - Buscar as publicações de novo no tribunal e refazer tudo")
        reconsultar = input("Escolha [Enter = 1]: ").strip() == "2"
    saida, controle = executar(ano, mes, reconsultar)
    import subprocess
    subprocess.run(["open", str(saida)])
    subprocess.run(["open", str(controle)])


def main():
    ap = argparse.ArgumentParser(description="Relatórios mensais aos clientes")
    ap.add_argument("--mes", help="aaaa-mm (padrão: mês de referência automático)")
    ap.add_argument("--reconsultar", action="store_true", help="baixa as publicações de novo")
    ap.add_argument("--interativo", action="store_true")
    a = ap.parse_args()
    if a.interativo:
        return interativo()
    if a.mes:
        ano, mes = map(int, a.mes.split("-"))
    else:
        ano, mes = mes_padrao()
    executar(ano, mes, a.reconsultar)


if __name__ == "__main__":
    main()
