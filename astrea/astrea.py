#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Astrea — integração geral (biblioteca + comando) para qualquer automação ou agente do escritório.

O Astrea não tem API pública. Usa a API interna do próprio site com a sessão da conta "Claude",
no perfil do Chrome da automação de cadastro (~/.cadastro-astrea/chrome-perfil). Espera o perfil
ficar livre se outra rotina estiver usando.

    PY=~/.cadastro-astrea/venv/bin/python
    $PY astrea.py <comando> [opções]          (a resposta sai em JSON; --saida ARQ grava em arquivo)

CONSULTAS (nada é gravado no Astrea)
    casos [--texto T] [--processos] [--etiqueta NOME]   casos ativos (filtra por título/cliente/nº)
    caso NUM|ID                                         detalhe do caso/processo (partes, vara, link do TJ)
    andamentos NUM|ID [--desde DD/MM/AAAA] [--tipo tj|pub|todos]
    tarefas NUM|ID                                      tarefas do caso (abertas e concluídas)
    agenda --de DD/MM/AAAA --ate DD/MM/AAAA [--pessoa NOME] [--status ALL|DONE|IN_PROGRESS]
                                                        prazos, tarefas, audiências e eventos
    publicacoes [--status RECEIVED|ASSIGNED|REJECTED] [--desde DD/MM/AAAA] [--processo NUM]
    contatos TEXTO                                      busca por nome/CPF/CNPJ
    contato ID
    casos-do-contato ID
    usuarios                                            pessoas do escritório (id, nome, ativo)
    etiquetas                                           etiquetas existentes (id, nome)

GRAVAÇÕES (sem --gravar só mostra o que faria)
    criar-tarefa NUM|ID --titulo T --para NOME [--vence DD/MM/AAAA | --vence +2u] [--comentario TEXTO]
                 [--prioridade baixa|media|alta] [--gravar]       (+2u = 2 dias úteis; +3 = 3 dias corridos)
    comentar TAREFA_ID --texto TEXTO [--gravar]
    concluir TAREFA_ID [--gravar]
    reabrir TAREFA_ID [--gravar]
    responsavel TAREFA_ID --para NOME [--gravar]
    etiqueta por|tirar NUM|ID --nome NOME [--gravar]

Travas: toda gravação precisa de --gravar (criar-tarefa confere lendo de novo). criar-tarefa não
duplica (tarefa ABERTA com o mesmo título no caso = não cria). Nada aqui protocola peça, apaga
caso/contato/tarefa ou mexe em financeiro. NUM aceita o nº do processo com ou sem pontuação.

Uso como biblioteca:
    sys.path.insert(0, "<repo>/astrea"); from astrea import Astrea
    with Astrea() as a: a.casos(); a.andamentos(id); a.criar_tarefa(...)

Mapa da API interna (descoberto em 09/11/2026): docs em LEIA-ME.md.
"""
import contextlib
import html
import json
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

DRIVE = (Path.home() / "Library" / "CloudStorage" / "GoogleDrive-contato@carolinemacedoadv.com"
         / "Meu Drive" / "Documentos Escritório ")
PRODUTIVIDADE = DRIVE / "EMPRESA" / "CLAUDE" / "PRODUTIVIDADE - PRAZOS ASTREA"

APP = "https://app.astrea.net.br"
API = APP + "/api/v2"
ENDP = APP + "/_ah/api"
USUARIO = "5487223873241088"     # conta Claude no Astrea
TENANT = "6406437268422656"
PRIORIDADE = {"baixa": 1, "media": 2, "média": 2, "alta": 3}
FERIADOS_FIXOS = {(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)}
TIPOS_AGENDA = {"DEADLINE": "Prazo", "TASK": "Tarefa", "HEARING": "Audiência", "EVENT": "Evento"}


# ------------------------------------------------------------------ utilidades

def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").upper()


def so_digitos(s):
    return re.sub(r"\D", "", str(s or ""))


def texto_limpo(s):
    s = re.sub(r"<br\s*/?>", "\n", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>|\{\\?SrAdvogado\}", "", s)
    return re.sub(r"[ \t]+", " ", html.unescape(s)).strip()


def data_br(s):
    return datetime.strptime(s, "%d/%m/%Y").date()


def dias_uteis_depois(d, n):
    """Pula sábado, domingo e feriados nacionais de data fixa (feriados móveis/locais: conferir)."""
    while n:
        d += timedelta(days=1)
        if d.weekday() < 5 and (d.month, d.day) not in FERIADOS_FIXOS:
            n -= 1
    return d


def vencimento(v):
    v = (v or "").strip()
    if not v:
        return date.today()
    m = re.fullmatch(r"\+(\d+)(u?)", v)
    if m:
        n = int(m.group(1))
        return dias_uteis_depois(date.today(), n) if m.group(2) else date.today() + timedelta(days=n)
    return data_br(v)


def log(t):
    print(datetime.now().strftime("%H:%M:%S"), t, file=sys.stderr, flush=True)


# ------------------------------------------------------------------ cliente

class Astrea:
    """Sessão da conta Claude. Use com `with Astrea() as a:`."""

    def __init__(self):
        sys.path.insert(0, str(PRODUTIVIDADE))
        import coletar as base   # espera do perfil + caminho da automação de cadastro
        self.base = base
        sys.path.insert(0, str(base.CADASTRO))
        from src.astrea.navegador import AdaptadorNavegador
        from src.config.settings import get_config
        from src.logs.logger import Log
        base.esperar_perfil()
        self.ad = AdaptadorNavegador(get_config(recarregar=True),
                                     Log(base.CASA / "logs", True, datetime.now().strftime("%Y%m%d-%H%M%S")),
                                     somente_leitura=True)
        self.token = None
        self._casos = None
        self._usuarios = None

    def __enter__(self):
        self.ad.conectar()
        pg = self.pg = self.ad.pagina

        def ao_pedir(req):
            if req.url.startswith(APP + "/") and "authorization" in req.headers:
                self.token = req.headers["authorization"]
        pg.on("request", ao_pedir)
        for rota in ("#/main/contacts", "#/main/workspace", "#/main/contacts"):
            pg.goto("https://astrea.net.br/" + rota, wait_until="domcontentloaded", timeout=60000)
            for _ in range(25):
                if self.token:
                    return self
                pg.wait_for_timeout(1000)
        raise RuntimeError("não consegui a credencial da sessão do Astrea")

    def __exit__(self, *a):
        try:
            self.ad.encerrar()
        except Exception:
            pass

    # --- HTTP
    def _req(self, metodo, url, corpo=None, ok=(200, 204)):
        if not url.startswith("http"):
            url = APP + url
        cab = {"authorization": self.token, "content-type": "application/json"}
        for tent in range(3):
            if metodo == "GET":
                r = self.pg.request.get(url, headers=cab, timeout=120000)
            else:
                r = self.pg.request.post(url, headers=cab, data=json.dumps(corpo if corpo is not None else {}),
                                         timeout=120000)
            if r.status in ok:
                try:
                    return r.json()
                except Exception:
                    return {}
            if r.status in (400, 403, 404):
                break
            time.sleep(3 * (tent + 1))
        raise RuntimeError("Astrea respondeu %s em %s: %s" % (r.status, url.split("?")[0], r.text()[:300]))

    def get(self, url):
        return self._req("GET", url)

    def post(self, url, corpo):
        return self._req("POST", url, corpo)

    # --- pessoas e etiquetas
    def usuarios(self):
        if self._usuarios is None:
            r = self.post("%s/users/v1/getAllUsers?tenantId=%s" % (ENDP, TENANT), {})
            self._usuarios = [{"id": str(u["id"]), "nome": (u.get("name") or "").strip(),
                               "ativo": u.get("status") == "ACTIVE"} for u in r.get("users", [])]
        return self._usuarios

    def usuario(self, nome):
        """Pessoa ATIVA cujo nome contém o texto (sem acento/maiúsculas). Precisa ser única."""
        alvo = sem_acento(nome)
        achados = [u for u in self.usuarios() if u["ativo"] and alvo in sem_acento(u["nome"])]
        if len(achados) != 1:
            raise ValueError("pessoa '%s': %s" % (nome, "não encontrada entre os ativos" if not achados
                             else "ambígua (" + ", ".join(u["nome"] for u in achados) + ")"))
        return achados[0]

    def etiquetas(self):
        return [{"id": str(t["id"]), "nome": t.get("label"), "ativa": t.get("active")}
                for t in self.get(ENDP + "/shared/v1/getAllTags").get("items", [])]

    def etiqueta_id(self, nome):
        alvo = sem_acento(nome)
        ex = [t for t in self.etiquetas() if sem_acento(t["nome"]) == alvo]
        if not ex:
            ex = [t for t in self.etiquetas() if alvo in sem_acento(t["nome"])]
        if len(ex) != 1:
            raise ValueError("etiqueta '%s': %s" % (nome, "não existe (crie à mão no Astrea)" if not ex
                             else "ambígua (" + ", ".join(t["nome"] for t in ex) + ")"))
        return ex[0]

    # --- casos
    def casos(self):
        """Todos os casos e processos ativos (resumo da lista do Astrea)."""
        if self._casos is None:
            todos, cur = [], ""
            for _ in range(200):
                r = self.post(API + "/case/query", {
                    "userId": int(USUARIO), "limit": 100, "queryCursor": cur, "currentOrder": "-lastMovement",
                    "queryDTO": {"contacts": [], "userId": int(USUARIO), "order": "-lastMovement",
                                 "onlyImportant": None, "notUpdated": None, "isFromContactScreen": False,
                                 "historiesMovement": None, "createddate": None, "shareddate": None,
                                 "endeddate": None, "users": [], "team": None}})
                todos += r.get("cases", [])
                cur = r.get("cursor") or ""
                if not cur or not r.get("cases"):
                    break
            self._casos = todos
        return self._casos

    def achar_caso(self, ref):
        """Por id do Astrea ou nº do processo (com ou sem pontuação)."""
        ref = str(ref).strip()
        dig = so_digitos(ref)
        for c in self.casos():
            if str(c["id"]) == ref:
                return c
        if len(dig) >= 15:
            ex = [c for c in self.casos() if so_digitos(c.get("number")) == dig]
            if ex:
                return ex[0]
        raise ValueError("caso/processo %s não encontrado entre os ativos" % ref)

    def casos_do_contato(self, contato_id):
        return self.post(API + "/case/query", {
            "userId": int(USUARIO), "limit": 100, "queryCursor": "", "currentOrder": "-lastMovement",
            "queryDTO": {"contacts": [str(contato_id)], "userId": int(USUARIO), "order": "-lastMovement",
                         "onlyImportant": None, "notUpdated": None, "isFromContactScreen": True,
                         "historiesMovement": None, "createddate": None, "shareddate": None,
                         "endeddate": None, "users": [], "team": None}}).get("cases", [])

    def detalhe(self, caso_id):
        return self.get("%s/folder/%s?userId=%s&withDetails=true" % (API, caso_id, USUARIO))

    def andamentos(self, caso_id, desde=None):
        """Andamentos do tribunal, publicações e históricos, do mais novo ao mais antigo."""
        saida, cur = [], ""
        for _ in range(50):
            r = self.get("%s/historical/%s/resume?limit=100&cursor=%s" % (API, caso_id, cur))
            pagina = r.get("historicals", [])
            for h in pagina:
                d = h["date"][:10]
                if desde and d < desde.isoformat():
                    return saida
                saida.append({"id": str(h["id"]), "data": d, "tipo": h["type"],
                              "texto": texto_limpo(h.get("description")),
                              "responsavel": h.get("responsibleName") or ""})
            cur = r.get("cursor") or ""
            if not cur or len(pagina) < 100:
                break
        return saida

    # --- contatos
    def contatos(self, texto):
        return self.post(API + "/contact/all", {
            "queryCursor": None, "limit": 30, "userId": USUARIO,
            "queryDTO": {"startsWith": [], "text": texto, "type": "", "order": "nameUpperCase",
                         "customerNotificationTypeFilter": "ALL",
                         "customerNotification": ["AUTOMATIC_HISTORIES", "CLIPPING"], "birthMonth": 0,
                         "selectedTagsIds": [], "state": "",
                         "customerNotificationArtificialIntelligenceFilter": "ALL"}}).get("contacts", [])

    def contato(self, contato_id):
        return self.get("%s/contact/%s" % (API, contato_id))

    # --- agenda e publicações
    def agenda(self, de, ate, pessoas=None, status="ALL"):
        ids = [u["id"] for u in self.usuarios()] if not pessoas else [self.usuario(p)["id"] for p in pessoas]
        vistos = {}
        d = de
        while d <= ate:
            fim = min(ate, (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1))
            r = self.post(API + "/calendar-pro/complete", {
                "from": d.strftime("%Y%m%d"), "to": fim.strftime("%Y%m%d"), "userId": USUARIO,
                "cursors": {"deadlineCursor": "", "eventCursor": "", "hearingCursor": "", "taskCursor": ""},
                "query": {"cases": [], "customers": [], "tasks": [], "appointments": [], "deadlines": [],
                          "hearings": [], "appointmentSelected": True, "deadlineSelected": True,
                          "hearingSelected": True, "taskSelected": True, "status": status,
                          "userFilter": {"selected": ids, "type": "CF_ALL",
                                         "users": [{"checked": True, "userId": i} for i in ids]},
                          "dateFilterPeriod": "MANUAL", "userId": USUARIO}})
            if r.get("count") is not None and r["count"] != len(r.get("activities", [])):
                log("ATENÇÃO: agenda de %s veio cortada (%d de %s)" % (d, len(r.get("activities", [])), r["count"]))
            for a in r.get("activities", []):
                vistos[(a.get("type"), a.get("id"))] = a
            d = fim + timedelta(days=1)
        nomes = {u["id"]: u["nome"] for u in self.usuarios()}
        saida = []
        for a in vistos.values():
            s = str(a.get("dateStart") or "").replace("-", "")[:8]
            saida.append({"id": str(a.get("id")), "tipo": TIPOS_AGENDA.get(a.get("type"), a.get("type")),
                          "titulo": (a.get("title") or "").strip(), "data": "%s-%s-%s" % (s[:4], s[4:6], s[6:8]),
                          "status": a.get("status"), "responsavel": nomes.get(str(a.get("responsibleId")), ""),
                          "caso": (a.get("caseTitle") or "").strip(), "processo": a.get("lawsuitNumber") or "",
                          "caso_id": str(a.get("customerCase") or "")})
        return sorted(saida, key=lambda x: (x["data"], x["responsavel"]))

    def publicacoes(self, status="RECEIVED", desde=None, processo=None, maximo=5000):
        saida, pagina = [], 0
        while len(saida) < maximo:
            lote = self.post(API + "/clipping-service/query", {
                "order": "-releaseDate", "cursor": "", "page": pagina, "limit": 100, "caseId": None,
                "caseTitle": None, "fromDate": None, "toDate": None, "endCreateDate": None, "customerId": None,
                "dateFilter": None, "clippingTypeFilter": None, "subpoenaStatusFilter": None,
                "caseStatusFilter": None, "status": status, "clippingSearchName": None, "state": None,
                "userId": USUARIO, "caseResponsibleId": None, "dateToShow": "CLIPPING_DATE"}).get("clippings", [])
            for c in lote:
                num = c.get("lawsuitNumber") or c.get("clippingLawsuitNumber") or ""
                if processo and so_digitos(num) != so_digitos(processo):
                    continue
                saida.append({"id": str(c.get("id")), "status": c.get("status") or status,
                              "divulgada": c.get("releaseDate") or "", "publicada": c.get("clippingDate") or "",
                              "processo": num, "caso": c.get("caseTitle") or "",
                              "responsavel": c.get("caseResponsibleName") or "", "diario": c.get("courtGazzete") or "",
                              "orgao": c.get("courtFormatted") or "", "texto": texto_limpo(c.get("clippingMatter"))})
            ultimo = (lote[-1].get("releaseDate") or "") if lote else ""
            if len(lote) < 100 or (desde and ultimo and ultimo[:10] < desde.isoformat()) or pagina > 400:
                break
            pagina += 1
        if desde:
            saida = [p for p in saida if (p["divulgada"] or "9")[:10] >= desde.isoformat()]
        return saida

    # --- tarefas
    def tarefas_do_caso(self, caso_id):
        r = self.post("%s/workspace/v1/getTasksByCase?caseId=%s&userId=%s" % (ENDP, caso_id, USUARIO), {})
        ex = lambda t, aberta: {"id": str(t["id"]), "titulo": t.get("description"), "aberta": aberta,
                                "vence": t.get("dueDateString") or (t.get("dueDate") or "")[:10],
                                "responsavel": t.get("responsibleName"), "versao": t.get("version"),
                                "status": t.get("status")}
        return ([ex(t, True) for t in r.get("activeTasks", [])] +
                [ex(t, False) for t in r.get("inactiveTasks", [])])

    def tarefa(self, tarefa_id):
        r = self.post(ENDP + "/workspace/v1/getTaskWithComments",
                      {"taskId": str(tarefa_id), "userId": USUARIO, "bringAllComments": True})
        return r

    def _lista_de_tarefas(self):
        itens = self.get("%s/workspace/v1/listTaskListsByUser?userId=%s" % (ENDP, USUARIO)).get("items") or []
        atual = [i for i in itens if i.get("current")] or itens
        if not atual:
            raise RuntimeError("conta Claude sem lista de tarefas no Astrea")
        return atual[0]["id"]

    def criar_tarefa(self, caso_id, titulo, responsavel_id, vence, prioridade=2):
        lista = self._lista_de_tarefas()
        t = self.post(ENDP + "/workspace/v1/saveTaskWithList", {
            "userId": USUARIO, "idUser": USUARIO, "idCurrentTaskList": lista, "responsibleId": responsavel_id,
            "rootCaseId": str(caso_id),
            "taskInfoDTO": {"caseId": str(caso_id), "description": titulo, "dueDate": vence.isoformat(),
                            "responsibleId": responsavel_id, "ownerId": USUARIO, "priority": prioridade,
                            "involved": [], "tagIds": [], "taskListIds": [lista], "done": False}})
        if not t.get("id"):
            raise RuntimeError("Astrea não devolveu o id da tarefa: %s" % json.dumps(t)[:300])
        return t

    def comentar(self, tarefa_id, texto):
        # Mesmo formato do comentário feito pela tela (type 0 = comentário de pessoa; o hash é
        # texto + instante em ms + id do usuário). Sem esses campos o Astrea responde 503.
        agora = datetime.utcnow()
        ms = int((agora - datetime(1970, 1, 1)).total_seconds() * 1000)
        return self.post(ENDP + "/workspace/v1/saveComment", {
            "taskId": str(tarefa_id), "userId": USUARIO, "userName": "Claude", "text": texto, "type": 0,
            "when": agora.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (ms % 1000),
            "commenthash": "%s%d%s" % (texto, ms, USUARIO), "mentions": [], "attachments": [], "driveFiles": []})

    def mudar_status(self, tarefa_id, versao, concluida):
        return self.get("%s/workspace/v1/changeTaskStatus?taskId=%s&taskVersion=%s&userId=%s&status=%s"
                        % (ENDP, tarefa_id, versao, USUARIO, "true" if concluida else "false"))

    def mudar_responsavel(self, tarefa_id, responsavel_id):
        return self.post(ENDP + "/workspace/v1/changeTaskResponsible",
                         {"taskId": str(tarefa_id), "userId": USUARIO, "responsibleId": responsavel_id})

    def etiqueta_caso(self, acao, caso_id, tag_id):
        return self.get("%s/folders/v1/%s?caseId=%s&tagId=%s&userId=%s"
                        % (ENDP, "addTagToCase" if acao == "por" else "removeTagFromCase", caso_id, tag_id, USUARIO))


# ------------------------------------------------------------------ comando

def resumo_caso(c):
    return {"id": str(c["id"]), "processo": c.get("number") or "", "titulo": c.get("title"),
            "pasta": c.get("file") or "", "cliente": c.get("customer"), "tipo": c.get("lawsuitType") or "",
            "vara": c.get("court") or "", "processo_judicial": c.get("type") == "CTE_LAWSUIT",
            "ultima_movimentacao": c.get("lastMovement"), "etiquetas": c.get("tagIds") or []}


def _opcao(argv, nome, padrao=None):
    return argv[argv.index(nome) + 1] if nome in argv and argv.index(nome) + 1 < len(argv) else padrao


def executar(argv):
    if not argv or argv[0] in ("-h", "--help", "ajuda"):
        return None
    cmd, op = argv[0], (lambda n, p=None: _opcao(argv, n, p))
    gravar = "--gravar" in argv
    arg1 = argv[1] if len(argv) > 1 and not argv[1].startswith("--") else None

    with Astrea() as a:
        if cmd == "casos":
            cs = [resumo_caso(c) for c in a.casos()]
            if "--processos" in argv:
                cs = [c for c in cs if c["processo_judicial"]]
            if op("--texto"):
                t, dig = sem_acento(op("--texto")), so_digitos(op("--texto"))
                cs = [c for c in cs if t in sem_acento(" ".join(str(c[k]) for k in ("titulo", "pasta", "cliente")))
                      or (len(dig) >= 7 and dig in so_digitos(c["processo"]))]
            if op("--etiqueta"):
                tid = a.etiqueta_id(op("--etiqueta"))["id"]
                cs = [c for c in cs if tid in c["etiquetas"]]
            return cs
        if cmd == "caso":
            c = a.achar_caso(arg1)
            d = a.detalhe(c["id"])
            nomes = {t["id"]: t["nome"] for t in a.etiquetas()}
            return dict(resumo_caso(c), detalhe=d, etiquetas_nomes=[nomes.get(t, t) for t in c.get("tagIds") or []],
                        link_astrea="https://astrea.net.br/#/main/folders/detail/%s" % c["id"])
        if cmd == "andamentos":
            c = a.achar_caso(arg1)
            hs = a.andamentos(c["id"], data_br(op("--desde")) if op("--desde") else None)
            tipo = op("--tipo", "todos")
            if tipo == "tj":
                hs = [h for h in hs if h["tipo"] == "AUTOMATIC_LAWSUIT"]
            elif tipo == "pub":
                hs = [h for h in hs if h["tipo"] == "CLIPPING"]
            return hs
        if cmd == "tarefas":
            return a.tarefas_do_caso(a.achar_caso(arg1)["id"])
        if cmd == "agenda":
            pessoas = [op("--pessoa")] if op("--pessoa") else None
            return a.agenda(data_br(op("--de")), data_br(op("--ate")), pessoas, op("--status", "ALL"))
        if cmd == "publicacoes":
            return a.publicacoes(op("--status", "RECEIVED"), data_br(op("--desde")) if op("--desde") else None,
                                 op("--processo"))
        if cmd == "contatos":
            return [{"id": str(c["id"]), "nome": c.get("name"), "classificacao": c.get("classificationName")}
                    for c in a.contatos(" ".join(x for x in argv[1:] if not x.startswith("--")))]
        if cmd == "contato":
            return a.contato(arg1)
        if cmd == "casos-do-contato":
            return [resumo_caso(c) for c in a.casos_do_contato(arg1)]
        if cmd == "usuarios":
            return a.usuarios()
        if cmd == "etiquetas":
            return a.etiquetas()

        # ---------------- gravações
        if cmd == "criar-tarefa":
            c = a.achar_caso(arg1)
            titulo = (op("--titulo") or "").strip()
            if not titulo or not op("--para"):
                raise ValueError("informe --titulo e --para")
            resp = a.usuario(op("--para"))
            venc = vencimento(op("--vence"))
            prio = PRIORIDADE[sem_acento(op("--prioridade", "media")).lower()]
            abertas = [t for t in a.tarefas_do_caso(c["id"])
                       if t["aberta"] and sem_acento(t["titulo"]) == sem_acento(titulo)]
            plano = {"caso": c.get("title"), "processo": c.get("number"), "titulo": titulo,
                     "responsavel": resp["nome"], "vence": venc.isoformat(), "prioridade": prio,
                     "comentario": op("--comentario")}
            if abertas:
                return dict(plano, resultado="JÁ EXISTE tarefa aberta com esse título (id %s); nada criado"
                            % abertas[0]["id"])
            if not gravar:
                return dict(plano, resultado="SIMULAÇÃO: nada gravado. Repita com --gravar.")
            t = a.criar_tarefa(c["id"], titulo, resp["id"], venc, prio)
            if op("--comentario"):
                a.comentar(t["id"], op("--comentario"))
            ok = [x for x in a.tarefas_do_caso(c["id"]) if x["id"] == str(t["id"])]
            return dict(plano, resultado="CRIADA", tarefa_id=str(t["id"]), conferencia=ok)
        if cmd == "comentar":
            if not op("--texto"):
                raise ValueError("informe --texto")
            if not gravar:
                return {"tarefa": arg1, "texto": op("--texto"), "resultado": "SIMULAÇÃO: nada gravado."}
            a.comentar(arg1, op("--texto"))
            return {"tarefa": arg1, "resultado": "COMENTADA"}
        if cmd in ("concluir", "reabrir"):
            t = a.tarefa(arg1)
            info = t.get("task") or t
            plano = {"tarefa": arg1, "titulo": info.get("description"), "acao": cmd}
            if not gravar:
                return dict(plano, resultado="SIMULAÇÃO: nada gravado.")
            a.mudar_status(arg1, info.get("version"), cmd == "concluir")
            return dict(plano, resultado="FEITO")
        if cmd == "responsavel":
            resp = a.usuario(op("--para"))
            if not gravar:
                return {"tarefa": arg1, "para": resp["nome"], "resultado": "SIMULAÇÃO: nada gravado."}
            a.mudar_responsavel(arg1, resp["id"])
            return {"tarefa": arg1, "para": resp["nome"], "resultado": "FEITO"}
        if cmd == "etiqueta":
            acao = arg1
            if acao not in ("por", "tirar") or len(argv) < 3:
                raise ValueError("uso: etiqueta por|tirar NUM|ID --nome NOME [--gravar]")
            c = a.achar_caso(argv[2])
            tag = a.etiqueta_id(op("--nome") or "")
            tem = tag["id"] in (c.get("tagIds") or [])
            plano = {"caso": c.get("title"), "processo": c.get("number"), "etiqueta": tag["nome"], "acao": acao}
            if (acao == "por") == tem:
                return dict(plano, resultado="nada a fazer (já %s)" % ("está" if tem else "não está"))
            if not gravar:
                return dict(plano, resultado="SIMULAÇÃO: nada gravado.")
            a.etiqueta_caso(acao, c["id"], tag["id"])
            return dict(plano, resultado="FEITO")
    raise ValueError("comando desconhecido: %s (veja: astrea.py ajuda)" % cmd)


def main(argv):
    try:
        # mensagens do navegador/automação vão para stderr; stdout fica só com o JSON
        with contextlib.redirect_stdout(sys.stderr):
            r = executar(argv)
    except ValueError as e:
        print("ERRO: %s" % e, file=sys.stderr)
        return 2
    if r is None:
        if not argv or argv[0] in ("-h", "--help", "ajuda"):
            print(__doc__)
        return 0
    texto = json.dumps(r, ensure_ascii=False, indent=1, default=str)
    saida = _opcao(argv, "--saida")
    if saida:
        Path(saida).expanduser().write_text(texto, encoding="utf-8")
        print("Gravado em %s (%s itens)" % (saida, len(r) if isinstance(r, list) else 1))
    else:
        print(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
