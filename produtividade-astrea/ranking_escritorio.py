"""
Ranking do escritório: todas as atividades do ano no Astrea, por pessoa.

Complementa o coletar.py (que olha só os concluídos de 4 pessoas). Este lê o
ANO INTEIRO, de TODAS as pessoas (inclusive quem já saiu), todos os tipos
(prazo, tarefa, audiência, evento) e todos os status, e grava:

    RELATÓRIOS/atividades_escritorio_AAAA.csv  (uma linha por atividade; abre no Excel)
    RELATÓRIOS/publicacoes_escritorio_AAAA.csv (uma linha por publicação recebida)
    ranking-escritorio-dados.json              (só totais, sem nome de cliente;
                                                é o que a página "Ranking do
                                                Escritório" lê pelo Google Drive)

O .json é regravado no mesmo lugar para o Drive manter o mesmo ID: é por esse
ID que a página o encontra. Não renomeie nem mova.

Roda depois do coletar.py, pelo ~/.produtividade-astrea/rodar.sh (12:10 e 20:10).
Mesma consulta que a Agenda do Astrea faz, com a sessão da automação. Nada é
gravado no Astrea.

Publicações (desde 06/11/2026): lê as publicações tratadas, descartadas e não
tratadas (mesma consulta da tela Publicações). O Astrea guarda quem tratou e o
DIA (sem horário). Duplicidade = mesmo processo com a mesma data de
divulgação recebido mais de uma vez (em geral o diário do tribunal + o DJEN).
Se essa parte falhar, o ranking de atividades sai assim mesmo e a página
continua com os números de publicações da rodada anterior.

Uso:
    python3 ranking_escritorio.py            # rodada normal
    python3 ranking_escritorio.py 2025       # outro ano
"""
import csv
import hashlib
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import coletar as base  # noqa: E402  (sessão, espera do perfil, log)

SAIDA_JSON = AQUI / "ranking-escritorio-dados.json"
TIPOS = {"DEADLINE": "Prazo", "TASK": "Tarefa", "HEARING": "Audiência", "EVENT": "Evento"}
STATUS = {"DONE": "Concluída", "IN_PROGRESS": "A concluir", "CANCELED": "Cancelada"}
STATUS_PUB = {"ASSIGNED": "Tratada", "REJECTED": "Descartada", "RECEIVED": "Não tratada"}
DUPLICIDADE = {"D": "mesmo processo e dia em outro diário", "I": "cópia idêntica no mesmo diário",
               "M": "mesmo processo e dia no mesmo diário, texto diferente"}


def log(texto):
    base.log("[ranking] " + texto)


def dia(a):
    s = str(a.get("dateStart") or "").replace("-", "")[:8]
    return date(int(s[:4]), int(s[4:6]), int(s[6:8])) if len(s) == 8 else None


def concluida_em(a):
    return datetime.fromtimestamp(a["completedAt"] / 1000) if a.get("completedAt") else None


def coletar_ano(ano):
    sys.path.insert(0, str(base.CADASTRO))
    from src.astrea.navegador import AdaptadorNavegador
    from src.config.settings import get_config
    from src.logs.logger import Log

    base.esperar_perfil()
    registro = Log(base.CASA / "logs", True, datetime.now().strftime("%Y%m%d-%H%M%S"))
    adaptador = AdaptadorNavegador(get_config(recarregar=True), registro, somente_leitura=True)
    token, usuarios = {}, {}

    def ao_pedir(req):
        if req.url.startswith(base.API) and "authorization" in req.headers:
            token["v"] = req.headers["authorization"]

    def ao_responder(r):
        # A Agenda carrega a lista completa de usuários (ativos e inativos).
        if "getAllUsers" in r.url:
            try:
                for u in r.json().get("users", []):
                    usuarios[str(u["id"])] = {"nome": (u.get("name") or "").strip(),
                                              "ativo": u.get("status") == "ACTIVE"}
            except Exception:
                pass

    adaptador.conectar()
    try:
        pg = adaptador.pagina
        pg.on("request", ao_pedir)
        pg.on("response", ao_responder)
        for rota in ("#/main/workspace", "#/main/calendar", "#/main/contacts", "#/main/calendar"):
            if "v" in token and usuarios:
                break
            pg.goto("https://astrea.net.br/" + rota, wait_until="domcontentloaded",
                    timeout=60000)
            if rota == "#/main/calendar":
                pg.reload(wait_until="domcontentloaded", timeout=60000)
            for _ in range(25):
                if "v" in token and usuarios:
                    break
                pg.wait_for_timeout(1000)
        if "v" not in token:
            raise RuntimeError("Não consegui a credencial da sessão do Astrea.")
        if not usuarios:
            raise RuntimeError("A Agenda não trouxe a lista de usuários.")
        cab = {"authorization": token["v"], "content-type": "application/json"}
        ids = list(usuarios)

        vistos = {}
        d = date(ano, 1, 1)
        while d.year == ano:
            ate = base.mes_seguinte(d) - timedelta(days=1)
            corpo = {"from": d.strftime("%Y%m%d"), "to": ate.strftime("%Y%m%d"),
                     "userId": base.USUARIO_CLAUDE,
                     "cursors": {"deadlineCursor": "", "eventCursor": "",
                                 "hearingCursor": "", "taskCursor": ""},
                     "query": {"cases": [], "customers": [], "tasks": [],
                               "appointments": [], "deadlines": [], "hearings": [],
                               "appointmentSelected": True, "deadlineSelected": True,
                               "hearingSelected": True, "taskSelected": True,
                               "status": "ALL",
                               "userFilter": {"selected": ids, "type": "CF_ALL",
                                              "users": [{"checked": True, "userId": i}
                                                        for i in ids]},
                               "dateFilterPeriod": "MANUAL", "userId": base.USUARIO_CLAUDE}}
            r = pg.request.post(base.API + "/calendar-pro/complete", headers=cab,
                                data=json.dumps(corpo), timeout=120000)
            if r.status != 200:
                raise RuntimeError("Astrea respondeu %s em %s." % (r.status, d))
            b = r.json()
            atividades = b.get("activities", [])
            if b.get("count") is not None and b["count"] != len(atividades):
                log("ATENÇÃO: %s veio %d de %s itens (lista cortada)."
                    % (d.strftime("%m/%Y"), len(atividades), b["count"]))
            for a in atividades:
                vistos[str(a["id"])] = a
            d = base.mes_seguinte(d)

        publicacoes = None
        try:
            publicacoes = coletar_publicacoes(pg, cab, ano)
        except Exception as erro:
            log("publicações não vieram (%s); mantenho as da rodada anterior." % erro)
    finally:
        adaptador.encerrar()
    return list(vistos.values()), usuarios, publicacoes


def coletar_publicacoes(pg, cab, ano):
    """Mesma consulta da tela Publicações, status por status, da mais nova para a mais antiga."""
    limite = "%d-07-01" % (ano - 1)   # tratadas neste ano quase sempre foram divulgadas há pouco
    todas = []
    for status in ("ASSIGNED", "REJECTED", "RECEIVED"):
        pagina = 0
        while True:
            corpo = {"order": "-releaseDate", "cursor": "", "page": pagina, "limit": 100,
                     "caseId": None, "caseTitle": None, "fromDate": None, "toDate": None,
                     "endCreateDate": None, "customerId": None, "dateFilter": None,
                     "clippingTypeFilter": None, "subpoenaStatusFilter": None,
                     "caseStatusFilter": None, "status": status, "clippingSearchName": None,
                     "state": None, "userId": base.USUARIO_CLAUDE, "caseResponsibleId": None,
                     "dateToShow": "CLIPPING_DATE"}
            r = pg.request.post(base.API + "/clipping-service/query", headers=cab,
                                data=json.dumps(corpo), timeout=120000)
            if r.status != 200:
                raise RuntimeError("Astrea respondeu %s nas publicações (%s)." % (r.status, status))
            lote = r.json().get("clippings", [])
            for c in lote:
                texto = " ".join(re.sub(r"<[^>]+>", " ", c.get("clippingMatter") or "").split())
                todas.append({
                    "status": c.get("status") or status,
                    "divulgada": c.get("releaseDate") or "",
                    "publicada": c.get("clippingDate") or "",
                    "tratada_em": c.get("assignedDate") or "",
                    "quem": str(c.get("whoAssigned") or c.get("whoReject") or ""),
                    "processo": c.get("lawsuitNumber") or c.get("clippingLawsuitNumber") or "",
                    "caso": c.get("caseTitle") or "",
                    "responsavel": c.get("caseResponsibleName") or "",
                    "diario": c.get("courtGazzete") or "",
                    "orgao": c.get("courtFormatted") or "",
                    "chave": c.get("hashKey") or "",
                    "texto": hashlib.md5(texto.encode("utf-8")).hexdigest(),
                    "trecho": resumo_texto(texto) if (c.get("status") or status) == "REJECTED" else "",
                    "motivo": c.get("discardReason") or "",
                    "id": c.get("id") or 0,
                })
            if len(lote) < 100 or (lote and (lote[-1].get("releaseDate") or "") < limite) or pagina > 400:
                break
            pagina += 1
    if not todas:
        raise RuntimeError("a consulta de publicações voltou vazia")
    return todas


def resumo_texto(t):
    """Trecho legível: pula o cabeçalho padrão do DJEN e vai ao conteúdo."""
    t = re.sub(r"\{\\?SrAdvogado\}", " ", t or "")
    i = t.find("Conteúdo:")
    if i >= 0:
        t = t[i + 9:]
    t = re.sub(r"^\s*Sr\. Advogado,?\s*", "", t)
    return " ".join(t.split())[:220]


def gerar_publicacoes(pubs, usuarios, ano):
    hoje = date.today()
    a = str(ano)

    def quem(uid):
        info = usuarios.get(uid)
        return nome_curto(info["nome"]) if info and info["nome"] else ("(sem registro)" if not uid else "Usuário " + uid[-4:])

    def dt(s):
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None

    # Duplicidade: mesmo processo + mesma data de divulgação (chave do próprio Astrea).
    grupos = defaultdict(list)
    for p in pubs:
        p["dup"] = ""
        if p["chave"] and p["divulgada"].startswith(a):
            grupos[p["chave"]].append(p)
    resumo_grupos = []
    for chave, g in grupos.items():
        if len(g) < 2:
            continue
        g.sort(key=lambda x: x["id"])
        textos, diarios = set(), set()
        for i, p in enumerate(g):
            if i:
                p["dup"] = "I" if p["texto"] in textos else ("D" if p["diario"] not in diarios else "M")
            textos.add(p["texto"]); diarios.add(p["diario"])
        resumo_grupos.append(g)

    tratadas = [p for p in pubs if p["status"] == "ASSIGNED" and p["tratada_em"].startswith(a)]
    descartadas = [p for p in pubs if p["status"] == "REJECTED" and p["divulgada"].startswith(a)]
    pendentes = [p for p in pubs if p["status"] == "RECEIVED"]

    # Planilha
    pasta = base.RELATORIOS
    pasta.mkdir(exist_ok=True)
    planilha = pasta / ("publicacoes_escritorio_%d.csv" % ano)
    tmp = planilha.with_suffix(".tmp")
    linhas = [p for p in pubs if p["divulgada"].startswith(a) or p["status"] == "RECEIVED"
              or (p["status"] == "ASSIGNED" and p["tratada_em"].startswith(a))]
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["divulgada em", "publicação em", "status", "tratada em", "tratada/descartada por",
                    "processo", "caso", "diário", "órgão", "responsável do caso", "duplicidade"])
        for p in sorted(linhas, key=lambda x: (x["divulgada"], x["processo"], x["id"])):
            w.writerow([p["divulgada"], p["publicada"], STATUS_PUB.get(p["status"], p["status"]),
                        p["tratada_em"], quem(p["quem"]) if p["quem"] else "", p["processo"], p["caso"],
                        p["diario"], p["orgao"], p["responsavel"], DUPLICIDADE.get(p["dup"], "")])
    tmp.replace(planilha)

    # Por pessoa
    pessoas = defaultdict(Counter)
    esperas = defaultdict(list)
    for p in tratadas:
        n = quem(p["quem"]); c = pessoas[n]
        c["tratadas"] += 1
        d = dt(p["tratada_em"])
        if d and d >= hoje - timedelta(days=6):
            c["ult7"] += 1
        if d and d >= hoje - timedelta(days=29):
            c["ult30"] += 1
        if p["dup"] in ("D", "I"):
            c["duplicadas"] += 1
        dv = dt(p["divulgada"])
        if d and dv:
            esperas[n].append((d - dv).days)
    for p in descartadas:
        pessoas[quem(p["quem"])]["descartadas"] += 1
    lista_p = []
    for n, c in pessoas.items():
        e = sorted(esperas[n])
        lista_p.append({"nome": n, "tratadas": c["tratadas"], "descartadas": c["descartadas"],
                        "ultimos_7_dias": c["ult7"], "ultimos_30_dias": c["ult30"],
                        "duplicadas_tratadas": c["duplicadas"],
                        "dias_ate_tratar_mediana": e[len(e) // 2] if e else None,
                        "tratadas_no_dia_seguinte_ou_antes": sum(1 for x in e if x <= 1)})
    lista_p.sort(key=lambda x: (-(x["tratadas"] + x["descartadas"]), x["nome"]))

    mensal = defaultdict(Counter)
    for p in tratadas:
        mensal[p["tratada_em"][:7]][quem(p["quem"])] += 1
    dup_mensal = defaultdict(Counter)
    pares = Counter()
    for g in resumo_grupos:
        for p in g[1:]:
            dup_mensal[p["divulgada"][:7]][p["dup"]] += 1
        pares[" + ".join(sorted(set(x["diario"] for x in g)))] += 1
    recentes = sorted(resumo_grupos, key=lambda g: (g[0]["divulgada"], g[0]["processo"]), reverse=True)[:150]

    def espera(p):
        d = dt(p["divulgada"])
        return (hoje - d).days if d else 0
    faixas = Counter()
    for p in pendentes:
        e = espera(p)
        faixas["até 1 dia" if e <= 1 else "2 a 3 dias" if e <= 3 else "4 a 7 dias" if e <= 7 else "mais de 7 dias"] += 1

    extras = [p for g in resumo_grupos for p in g[1:]]
    return {
        "gerado_em": datetime.now().isoformat(timespec="minutes"),
        "tratadas": len(tratadas), "descartadas": len(descartadas), "pendentes": len(pendentes),
        "pessoas": lista_p,
        "mensal": {m: dict(c) for m, c in sorted(mensal.items())},
        # [tratada em, quem, divulgada em, processo, diário, duplicidade D/I/M]
        "tratadas_lista": sorted([p["tratada_em"], quem(p["quem"]), p["divulgada"], p["processo"],
                                  p["diario"], p["dup"]] for p in tratadas),
        # [divulgada, quem descartou, processo, diário, órgão, trecho, motivo, duplicidade]
        "descartadas_lista": sorted(([p["divulgada"], quem(p["quem"]), p["processo"], p["diario"], p["orgao"],
                                     resumo_texto(p["trecho"]), p["motivo"], p["dup"]] for p in descartadas), reverse=True),
        "pendentes_faixas": dict(faixas),
        "pendentes_mais_antiga": min((p["divulgada"] for p in pendentes if p["divulgada"]), default=""),
        "pendentes_lista": sorted([p["divulgada"], p["processo"], p["diario"], nome_curto(p["responsavel"]) if p["responsavel"] else "",
                                   p["dup"]] for p in pendentes)[:200],
        "duplicidade": {
            "grupos": len(resumo_grupos), "extras": len(extras),
            "recebidas_no_ano": sum(1 for p in pubs if p["divulgada"].startswith(a)),
            "por_tipo": dict(Counter(p["dup"] for p in extras)),
            "mensal": {m: dict(c) for m, c in sorted(dup_mensal.items())},
            "diarios": pares.most_common(8),
            # [divulgada, processo, quantas, diários, quem tratou, status]
            "recentes": [[g[0]["divulgada"], g[0]["processo"] or "(sem número)", len(g),
                          ", ".join(sorted(set(x["diario"] for x in g))),
                          ", ".join(sorted(set(quem(x["quem"]) for x in g if x["quem"]))),
                          ", ".join(sorted(set(STATUS_PUB.get(x["status"], x["status"]) for x in g)))]
                         for g in recentes],
        },
    }


def nome_curto(nome):
    partes = nome.split()
    return " ".join(partes[:2]) if partes else "(sem responsável)"


def gerar(atividades, usuarios, ano, publicacoes=None):
    hoje = date.today()
    agora = datetime.now()
    pessoas = defaultdict(Counter)
    mensal = defaultdict(Counter)          # mês -> pessoa -> concluídas
    mensal_tipo = defaultdict(Counter)     # mês -> tipo -> concluídas
    titulos = defaultdict(Counter)         # pessoa -> título de prazo concluído
    linhas = []
    feitas = []                            # cada conclusão com dia e hora (filtro por dia na página)

    for a in atividades:
        d = dia(a)
        if not d or d.year != ano:
            continue
        uid = str(a.get("responsibleId") or "")
        info = usuarios.get(uid, {"nome": "", "ativo": False})
        pessoa = nome_curto(info["nome"]) if info["nome"] else "(sem responsável)"
        tipo, status = a.get("type"), a.get("status")
        fim = concluida_em(a)
        em_dia = ""
        p = pessoas[pessoa]
        p["movimentadas"] += 1
        if status == "DONE":
            p["concluidas"] += 1
            p["c_" + tipo] += 1
            mes = (fim.date() if fim else d).strftime("%Y-%m")
            mensal[mes][pessoa] += 1
            mensal_tipo[mes][TIPOS.get(tipo, tipo)] += 1
            if fim:
                if fim.date() >= hoje - timedelta(days=6):
                    p["ult7"] += 1
                if fim.date() >= hoje - timedelta(days=29):
                    p["ult30"] += 1
            if tipo == "DEADLINE":
                titulos[pessoa][" ".join((a.get("title") or "").upper().split())] += 1
                if fim:
                    em_dia = "sim" if fim.date() <= d else "não"
                    p["pz_em_dia" if em_dia == "sim" else "pz_depois"] += 1
            if fim:
                feitas.append([fim.isoformat(timespec="minutes"), pessoa, tipo[:1],
                               " ".join((a.get("title") or "").split())[:140],
                               {"sim": "s", "não": "n"}.get(em_dia, "")])
        elif status == "IN_PROGRESS":
            p["abertas"] += 1
            if d < hoje:
                p["atras_" + tipo] += 1
        else:
            p["canceladas"] += 1
        p["_ativo"] = 1 if info["ativo"] else 0

        linhas.append([d.isoformat(), TIPOS.get(tipo, tipo), STATUS.get(status, status),
                       (a.get("title") or "").strip(), info["nome"] or "(sem responsável)",
                       (a.get("completeLawsuit") or a.get("caseTitle") or "").strip(),
                       fim.isoformat(timespec="minutes") if fim else "", em_dia])

    if not linhas:
        raise RuntimeError("A consulta voltou vazia — não vou sobrescrever a planilha.")

    # Planilha (separador ; para o Excel em português)
    pasta = base.RELATORIOS
    pasta.mkdir(exist_ok=True)
    planilha = pasta / ("atividades_escritorio_%d.csv" % ano)
    tmp = planilha.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["data", "tipo", "status", "título", "responsável", "processo/caso",
                    "concluída em", "prazo concluído até a data"])
        w.writerows(sorted(linhas))
    tmp.replace(planilha)

    # Resumo para a página (sem cliente nem processo; títulos só na lista do dia)
    lista = []
    for nome, p in pessoas.items():
        lista.append({
            "nome": nome, "ativo": bool(p["_ativo"]),
            "movimentadas": p["movimentadas"], "concluidas": p["concluidas"],
            "prazos": p["c_DEADLINE"], "tarefas": p["c_TASK"],
            "audiencias": p["c_HEARING"], "eventos": p["c_EVENT"],
            "prazos_em_dia": p["pz_em_dia"], "prazos_depois": p["pz_depois"],
            "abertas": p["abertas"], "canceladas": p["canceladas"],
            "atrasadas_prazo": p["atras_DEADLINE"], "atrasadas_tarefa": p["atras_TASK"],
            "atrasadas_outras": p["atras_HEARING"] + p["atras_EVENT"],
            "ultimos_7_dias": p["ult7"], "ultimos_30_dias": p["ult30"],
            "prazos_mais_feitos": [[t, n] for t, n in titulos[nome].most_common(5)],
        })
    lista.sort(key=lambda x: (-x["concluidas"], x["nome"]))
    todos_titulos = Counter()
    for c in titulos.values():
        todos_titulos.update(c)
    dados = {
        "gerado_em": agora.isoformat(timespec="minutes"),
        "ano": ano,
        "pessoas": lista,
        "mensal": {m: dict(c) for m, c in sorted(mensal.items())},
        "mensal_tipo": {m: dict(c) for m, c in sorted(mensal_tipo.items())},
        "prazos_mais_feitos": [[t, n] for t, n in todos_titulos.most_common(15)],
        # [quando concluiu, pessoa, tipo D/T/H/E, título, prazo em dia s/n]
        "concluidas_lista": sorted(feitas),
    }
    if publicacoes:
        dados["publicacoes"] = gerar_publicacoes(publicacoes, usuarios, ano)
    else:
        try:
            antigo = json.loads(SAIDA_JSON.read_text(encoding="utf-8"))
            if antigo.get("ano") == ano and antigo.get("publicacoes"):
                dados["publicacoes"] = antigo["publicacoes"]
        except Exception:
            pass
    tmp = SAIDA_JSON.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    # Regrava por cima (não troca o arquivo) para o Drive manter o mesmo ID.
    SAIDA_JSON.write_text(tmp.read_text(encoding="utf-8"), encoding="utf-8")
    tmp.unlink()
    total = sum(x["movimentadas"] for x in lista)
    feitas = sum(x["concluidas"] for x in lista)
    log("ok: %d atividades em %d (%d concluídas), %d pessoas." % (total, ano, feitas, len(lista)))
    pb = dados.get("publicacoes")
    if pb and publicacoes:
        log("publicações: %d tratadas, %d descartadas, %d não tratadas, %d duplicadas."
            % (pb["tratadas"], pb["descartadas"], pb["pendentes"], pb["duplicidade"]["extras"]))


def main():
    ano = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else date.today().year
    (base.CASA / "logs").mkdir(parents=True, exist_ok=True)
    atividades, usuarios, publicacoes = coletar_ano(ano)
    gerar(atividades, usuarios, ano, publicacoes)


if __name__ == "__main__":
    try:
        main()
    except Exception as erro:
        log("FALHOU: %s" % erro)
        sys.exit(1)
