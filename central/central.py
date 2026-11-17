#!/usr/bin/env python3
"""Central do Escritório — Caroline Macedo Advocacia.

Um só lugar para abrir os painéis, os geradores, os robôs e acompanhar as rotinas.
Roda só neste Mac (http://127.0.0.1:8500) e só com a biblioteca padrão do Python.

A central NÃO altera nenhuma automação: os painéis e geradores são lidos de onde já
estão no Drive, e os robôs são abertos exatamente como pelo atalho da Área de Trabalho.
"""
from __future__ import annotations

import datetime
import json
import os
import plistlib
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlparse

PORTA = int(os.environ.get("CENTRAL_PORTA", "8500"))
HOST = "127.0.0.1"
AQUI = Path(__file__).resolve().parent
CASA = Path.home()
DRIVE = CASA / "Library/CloudStorage/GoogleDrive-contato@carolinemacedoadv.com/Meu Drive/Documentos Escritório "
TOKEN = secrets.token_urlsafe(24)  # só a página aberta por esta central consegue acionar robôs

# --------------------------------------------------------------------------------------
# Catálogo. Para incluir algo novo, basta acrescentar uma linha aqui.
# --------------------------------------------------------------------------------------
PAINEIS = [
    # id, nome, descrição, caminho, frequência esperada de atualização (dias)
    # Painel Financeiro e Painel Comercial leem os dados do claude.ai: ficam em ONLINE.
    ("previsao", "Previsão de Recebimentos", "Asaas — atualiza todo dia às 7h", DRIVE / "EMPRESA/CLAUDE/PREVISÃO RECEBIMENTOS ASAAS/Dashboard Previsão Asaas.html", 1),
    ("prazos", "Dashboard de Prazos", "Astrea — 9h, 12h10 e 20h10", DRIVE / "EMPRESA/CLAUDE/PRODUTIVIDADE - PRAZOS ASTREA/Dashboard de Prazos.html", 1),
    ("consolidado", "Comercial Consolidado", "Histórico 2023–2026", DRIVE / "A - REVISIONAL/A - COMERCIAL/DASHBOARD COMERCIAL - CONSOLIDADO 2023-2026.html", 0),
]

GERADORES = [
    ("contratos", "Gerar Contratos", "Contrato, procuração e declarações", DRIVE / "A - REVISIONAL/A - COMERCIAL/GERADOR CONTRATOS/gerador_contratos.html"),
    ("peticao", "Petição Revisional", "Gera a inicial revisional", DRIVE / "A - REVISIONAL/A - DOCUMENTOS/GERADOR PETIÇÃO REVISIONAL/gerador_peticao.html"),
    ("calc-revisional", "Calculadora Revisional", "Simulação comercial", DRIVE / "A - REVISIONAL/A - COMERCIAL/CALCULADORA REVISIONAL/calculadora_revisional.html"),
    ("onboarding", "Gerador de Onboarding", "Boas-vindas do cliente", DRIVE / "EMPRESA/ONBORDING/GERADOR DE ONBOARDING/files/gerador_onboarding.html"),
    ("pdf", "Gerador de PDF", "Documentos em PDF", DRIVE / "A - REVISIONAL/A - COMERCIAL/ONBOARDING/gerador_pdf.html"),
]

ONLINE = [
    ("Painel Financeiro", "ASAAS + Conta Azul", "https://claude.ai/code/artifact/805c59c0-1021-4c20-90e9-80369d6365ad"),
    ("Ranking do Escritório", "Produtividade por pessoa", "https://claude.ai/code/artifact/f7316780-6902-4741-b27d-9fe305ba681b"),
    ("Inadimplência no Astrea", "Etiquetas postas e tiradas", "https://claude.ai/code/artifact/586bc7da-dd8d-4129-b137-543bd9274687"),
    ("Alvarás Recebidos", "Levantamento 2025+", "https://claude.ai/code/artifact/55f71c1b-718c-4af9-8338-e317486d77db"),
    ("Painel Comercial", "Contratos e recebimentos por mês", "https://claude.ai/code/artifact/f00267ca-0e58-49e1-bda7-762db67b893a"),
    ("Cadastros no Astrea", "Clientes cadastrados pelo robô", "https://claude.ai/code/artifact/c579b9de-9d85-4aca-a18d-9cbe562abd49"),
    ("Envios de Relatórios", "Relatórios mensais enviados", "https://claude.ai/code/artifact/f769fdfb-3ed3-4ff0-84a9-c864c86d395d"),
    ("Banco de Teses CM", "Teses do escritório", "https://claude.ai/code/artifact/94dcfc18-c962-4db5-b662-f0711f3d2cde"),
    ("Sentenças por Banco", "Carteira revisional", "https://claude.ai/code/artifact/8a837150-6097-493c-9eed-7e2e1609b0c0"),
]

_ONB = DRIVE / "A - REVISIONAL/A - COMERCIAL/ONBOARDING"
ROBOS = [
    ("baixar", "Baixar Contratos Assinados", "Autentique → Drive", _ONB / "BAIXAR AUTENTIQUE/Baixar Contratos Assinados.command"),
    ("separar", "Separar Documentos", "Separa os PDFs do Autentique", _ONB / "SEPARADOR AUTENTIQUE/Separar Documentos.command"),
    ("cadastro", "Cadastrar no Astrea", "Clientes e casos novos", _ONB / "CADASTRO ASTREA/Cadastrar Clientes.command"),
    ("gerar-onb", "Gerar Onboarding", "Onboarding do cliente", _ONB / "GERADOR ONBOARDING/Gerar Onboarding.command"),
    ("relatorios-mes", "Relatórios do Mês", "Gera os relatórios da rodagem", DRIVE / "A - REVISIONAL/A - RODAGEM/RELATÓRIOS MENSAIS/Relatórios do Mês.command"),
    ("radar", "Radar B&A", "Monitoramento nos tribunais", DRIVE / "MAPEAMENTO TJS/radar-ba/RADAR B&A.command"),
    ("anonimizar", "CM · Anonimizar parecer", "Validação pericial, passo 1", CASA / "Desktop/CM - 1 Anonimizar parecer.command"),
    ("liberar", "CM · Liberar parecer", "Validação pericial, passo 2", CASA / "Desktop/CM - 2 Liberar parecer anonimizado.command"),
]

ROTINAS = [
    # rótulo do LaunchAgent, nome, pasta de logs
    ("com.carolinemacedo.previsao-asaas", "Previsão Asaas", CASA / ".previsao-asaas/logs"),
    ("com.carolinemacedo.produtividade-astrea", "Produtividade Astrea", CASA / ".produtividade-astrea/logs"),
    ("com.carolinemacedo.baixar-autentique", "Baixar Autentique", CASA / ".baixar-autentique/logs"),
    ("com.carolinemacedo.cadastro-astrea", "Cadastro Astrea", CASA / ".cadastro-astrea/logs"),
    ("com.carolinemacedo.tarja-prova-social", "Tarja Prova Social", CASA / ".tarja-prova-social/logs"),
    ("com.carolinemacedo.manter-acordado", "Manter Mac acordado", CASA / ".cadastro-astrea/logs"),
]

CALCULADORA = CASA / "cm-calculadora"
SISTEMAS = [
    ("cm-real", "Calculadora Judicial", "Casos reais", 8501, CALCULADORA / "iniciar.sh"),
    ("cm-demo", "Calculadora Judicial · demo", "Casos fictícios", 8502, CALCULADORA / "iniciar-demo.sh"),
]

ARQUIVOS = {i[0]: i[3] for i in PAINEIS + GERADORES}
EXECUTAVEIS = {i[0]: i[3] for i in ROBOS}
EXECUTAVEIS.update({s[0]: s[4] for s in SISTEMAS})

TIPOS = {".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8",
         ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".svg": "image/svg+xml", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".csv": "text/csv; charset=utf-8", ".txt": "text/plain; charset=utf-8"}


# --------------------------------------------------------------------------------------
# Estado
# --------------------------------------------------------------------------------------
def _mtime(p: Path):
    try:
        return p.stat().st_mtime
    except OSError:
        return None


def _porta_aberta(porta: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex((HOST, porta)) == 0


def _launchctl() -> dict:
    try:
        saida = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return {}
    estado = {}
    for linha in saida.splitlines()[1:]:
        partes = linha.split("\t")
        if len(partes) == 3:
            pid, codigo, rotulo = partes
            estado[rotulo] = {"pid": None if pid == "-" else pid, "codigo": codigo}
    return estado


def _horarios(rotulo: str) -> list:
    plist = CASA / "Library/LaunchAgents" / f"{rotulo}.plist"
    try:
        with plist.open("rb") as f:
            dados = plistlib.load(f)
    except Exception:
        return []
    cal = dados.get("StartCalendarInterval")
    if isinstance(cal, dict):
        cal = [cal]
    if not cal:
        intervalo = dados.get("StartInterval")
        return [f"a cada {intervalo // 60} min"] if intervalo else []
    return sorted({f"{c.get('Hour', 0):02d}:{c.get('Minute', 0):02d}" for c in cal})


def _ultimas_linhas(p: Path, n: int = 6) -> list:
    try:
        with p.open("rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4000))
            texto = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    return [l for l in texto.splitlines() if l.strip()][-n:]


def estado() -> dict:
    agora = time.time()
    lc = _launchctl()
    rotinas = []
    for rotulo, nome, logs in ROTINAS:
        info = lc.get(rotulo)
        arquivos = sorted(logs.glob("*"), key=lambda p: _mtime(p) or 0, reverse=True) if logs.is_dir() else []
        recente = arquivos[0] if arquivos else None
        erros = [p for p in arquivos if p.suffix == ".err"]
        rotinas.append({
            "nome": nome,
            "carregada": info is not None,
            "rodando": bool(info and info["pid"]),
            "codigo": info["codigo"] if info else None,
            "horarios": _horarios(rotulo),
            "ultimo_log": _mtime(recente) if recente else None,
            "log": _ultimas_linhas(recente) if recente else [],
            "erro": _ultimas_linhas(erros[0], 4) if erros and (_mtime(erros[0]) or 0) > agora - 3 * 86400 else [],
        })
    return {
        "agora": agora,
        "paineis": [{"id": i, "nome": n, "desc": d, "existe": p.exists(), "atualizado": _mtime(p), "freq": f}
                    for i, n, d, p, f in PAINEIS],
        "geradores": [{"id": i, "nome": n, "desc": d, "existe": p.exists()} for i, n, d, p in GERADORES],
        "online": [{"nome": n, "desc": d, "url": u} for n, d, u in ONLINE],
        "robos": [{"id": i, "nome": n, "desc": d, "existe": p.exists()} for i, n, d, p in ROBOS],
        "rotinas": rotinas,
        "sistemas": [{"id": i, "nome": n, "desc": d, "porta": porta, "ligado": _porta_aberta(porta),
                      "existe": script.exists()} for i, n, d, porta, script in SISTEMAS],
    }


# --------------------------------------------------------------------------------------
# Asaas (só leitura). A chave fica no Porta-chaves do Mac, a mesma da Previsão Asaas;
# para trocar: /usr/bin/python3 ~/.previsao-asaas/trocar-chave.py
# --------------------------------------------------------------------------------------
ASAAS_URL = "https://api.asaas.com/v3"
ASAAS_CACHE_SEG = 600
_asaas = {"dados": None, "quando": 0.0, "erro": None, "ocupado": False}
_asaas_trava = threading.Lock()


def _asaas_chave() -> str:
    r = subprocess.run(["security", "find-generic-password", "-s", "asaas-api", "-a", "previsao-asaas", "-w"],
                       capture_output=True, text=True)
    return r.stdout.strip()


def _asaas_get(chave: str, caminho: str, params: dict = None) -> dict:
    url = ASAAS_URL + caminho + ("?" + urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"access_token": chave, "User-Agent": "central-escritorio"})
    for tentativa in range(3):  # o Asaas às vezes demora; tenta de novo antes de desistir
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code < 500 and e.code != 429:
                raise
            erro = e
        except (urllib.error.URLError, OSError) as e:  # timeout, conexão caiu
            erro = e
        time.sleep(2 * (tentativa + 1))
    raise erro


def _asaas_somar(chave: str, params: dict, campo: str = "value", limite: int = 5000):
    """Soma o campo de todas as cobranças do filtro, página por página."""
    total, qtd, offset = 0.0, 0, 0
    while offset < limite:
        pagina = _asaas_get(chave, "/payments", dict(params, limit=100, offset=offset))
        for c in pagina.get("data", []):
            if c.get("deleted"):
                continue
            total += float(c.get(campo) or c.get("value") or 0)
            qtd += 1
        if not pagina.get("hasMore"):
            break
        offset += 100
    return round(total, 2), qtd


FAIXAS_ATRASO = [("ate30", "até 30 dias", 30), ("31a90", "31 a 90 dias", 90),
                 ("91a180", "91 a 180 dias", 180), ("mais180", "mais de 180 dias", None)]


def _asaas_vencidas(chave: str, limite: int = 10000) -> list:
    """Cobranças vencidas separadas pela idade do atraso (dias desde o vencimento)."""
    hoje = datetime.date.today()
    faixas = [{"id": i, "nome": n, "valor": 0.0, "qtd": 0} for i, n, _ in FAIXAS_ATRASO]
    offset = 0
    while offset < limite:
        pagina = _asaas_get(chave, "/payments", {"status": "OVERDUE", "limit": 100, "offset": offset})
        for c in pagina.get("data", []):
            if c.get("deleted") or not c.get("dueDate"):
                continue
            dias = (hoje - datetime.date.fromisoformat(c["dueDate"])).days
            k = _faixa(dias)
            faixas[k]["valor"] += float(c.get("value") or 0)
            faixas[k]["qtd"] += 1
        if not pagina.get("hasMore"):
            break
        offset += 100
    for f in faixas:
        f["valor"] = round(f["valor"], 2)
    return faixas


def _asaas_coletar():
    try:
        chave = _asaas_chave()
        if not chave:
            raise RuntimeError("Chave do Asaas não encontrada no Porta-chaves")
        hoje = time.localtime()
        dia = time.strftime("%Y-%m-%d", hoje)
        inicio_mes = time.strftime("%Y-%m-01", hoje)
        em30 = time.strftime("%Y-%m-%d", time.localtime(time.time() + 30 * 86400))
        recebido, n_rec = 0.0, 0
        for status in ("RECEIVED", "CONFIRMED", "RECEIVED_IN_CASH"):
            v, n = _asaas_somar(chave, {"status": status, "paymentDate[ge]": inicio_mes, "paymentDate[le]": dia}, "netValue")
            recebido, n_rec = recebido + v, n_rec + n
        a_receber, n_pend = _asaas_somar(chave, {"status": "PENDING", "dueDate[ge]": dia, "dueDate[le]": em30})
        atraso = _asaas_vencidas(chave)
        vencido, n_venc = round(sum(f["valor"] for f in atraso), 2), sum(f["qtd"] for f in atraso)
        saldo = _asaas_get(chave, "/finance/balance").get("balance")
        dados = {"saldo": saldo, "recebido_mes": round(recebido, 2), "n_recebido": n_rec,
                 "a_receber_30": a_receber, "n_a_receber": n_pend, "vencido": vencido, "n_vencido": n_venc,
                 "atraso": atraso}
        with _asaas_trava:
            _asaas.update(dados=dados, quando=time.time(), erro=None)
    except urllib.error.HTTPError as e:
        with _asaas_trava:
            _asaas["erro"] = "O Asaas recusou a chave (HTTP 401). Troque com trocar-chave.py" if e.code == 401 else f"Asaas respondeu HTTP {e.code}"
    except Exception as e:  # sem internet, etc.
        with _asaas_trava:
            _asaas["erro"] = f"Não consegui falar com o Asaas: {e}"
    finally:
        with _asaas_trava:
            _asaas["ocupado"] = False


def asaas(forcar: bool = False) -> dict:
    with _asaas_trava:
        velho = time.time() - _asaas["quando"] > ASAAS_CACHE_SEG
        if (velho or forcar) and not _asaas["ocupado"]:
            _asaas["ocupado"] = True
            threading.Thread(target=_asaas_coletar, daemon=True).start()
        return {"dados": _asaas["dados"], "quando": _asaas["quando"] or None,
                "erro": _asaas["erro"], "atualizando": _asaas["ocupado"]}


# --------------------------------------------------------------------------------------
# Conta Azul. Não há API que funcione para o escritório (OAuth nunca autorizou, ago/2026);
# a tarefa diária puxa pelo Chrome (contaazul_extrair.js) e grava os arquivos abaixo.
# A central só lê, com as mesmas regras do painel financeiro e das etiquetas.
# --------------------------------------------------------------------------------------
CA_DADOS = DRIVE / "EMPRESA/FINANCEIRO/PAINEL FINANCEIRO/dados"


def _faixa(dias: int) -> int:
    return next(i for i, (_, _, ate) in enumerate(FAIXAS_ATRASO) if ate is None or dias <= ate)


def conta_azul() -> dict:
    hoje = datetime.date.today()
    hoje_iso = hoje.isoformat()
    avisos = []
    # Vencidas: nome|centavos em aberto|vencimento|situação V/L|conta C/S|cat|parcela
    faixas = [{"id": i, "nome": n, "valor": 0.0, "qtd": 0} for i, n, _ in FAIXAS_ATRASO]
    venc_arq = CA_DADOS / "ca_vencidas.txt"
    coletado = _mtime(venc_arq)
    if coletado is None:
        return {"erro": "Ainda não há coleta do Conta Azul (falta ca_vencidas.txt no Drive)."}
    for linha in venc_arq.read_text(encoding="utf-8").strip().splitlines():
        p = linha.split("|")
        if len(p) < 7:
            continue
        _nome, c, venc, _st, conta, cat, parc = p[:7]
        if conta == "A" or cat == "PA" or (cat == "--" and parc == "PX") or int(c) <= 0 or venc >= hoje_iso:
            continue
        k = _faixa((hoje - datetime.date.fromisoformat(venc)).days)
        faixas[k]["valor"] += int(c) / 100
        faixas[k]["qtd"] += 1
    for f in faixas:
        f["valor"] = round(f["valor"], 2)
    # Mês: nome|centavos|cat|forma|venc|situação|pago|conjuntos|conta|parcela
    recebido = a_receber = 0.0
    n_rec = n_pend = 0
    mes_arq = CA_DADOS / f"ca_{hoje:%Y-%m}.txt"
    if mes_arq.exists():
        for linha in mes_arq.read_text(encoding="utf-8").strip().splitlines():
            p = linha.split("|")
            if len(p) < 10:
                continue
            _n, c, cat, _forma, venc, st, _pago, fl, conta, parc = p[:10]
            if conta == "A" or st == "Z" or (cat == "--" and parc == "PX"):
                continue
            if "r" in fl and st == "R":
                recebido += int(c) / 100
                n_rec += 1
            elif st == "P" and venc >= hoje_iso:
                a_receber += int(c) / 100
                n_pend += 1
    else:
        avisos.append(f"Falta a coleta do mês ({mes_arq.name}).")
    if datetime.date.fromtimestamp(coletado) < hoje:
        avisos.append("A coleta de hoje ainda não chegou; valem os números da última coleta.")
    return {
        "coletado": coletado, "avisos": avisos,
        "recebido_mes": round(recebido, 2), "n_recebido": n_rec,
        "a_receber_mes": round(a_receber, 2), "n_a_receber": n_pend,
        "vencido": round(sum(f["valor"] for f in faixas), 2), "n_vencido": sum(f["qtd"] for f in faixas),
        "atraso": faixas,
    }


# --------------------------------------------------------------------------------------
# Multichat360 (atendimentos no WhatsApp), só leitura. O token fica no Porta-chaves
# (serviço multichat360, conta token). Só usa as rotas de estatística (GET): a URL
# /v1/api/external/... da plataforma ENVIA mensagens e nunca é chamada aqui.
# A API trata endDate como "até 00h do dia", por isso pedimos sempre fim + 1 dia.
# --------------------------------------------------------------------------------------
MC_URL = "https://new4api.multichat360.com.br"
MC_CACHE_SEG = 600
_mc_cache: dict = {}
_mc_trava = threading.Lock()


def _mc_token() -> str:
    r = subprocess.run(["security", "find-generic-password", "-s", "multichat360", "-a", "token", "-w"],
                       capture_output=True, text=True)
    return r.stdout.strip()


def _mc_get(token: str, rota: str, inicio: datetime.date, fim: datetime.date):
    params = {"startDate": inicio.isoformat(), "endDate": (fim + datetime.timedelta(days=1)).isoformat()}
    req = urllib.request.Request(f"{MC_URL}{rota}?{urlencode(params)}",
                                 headers={"Authorization": f"Bearer {token}", "User-Agent": "central-escritorio"})
    for tentativa in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code < 500 and e.code != 429:
                raise
            erro = e
        except (urllib.error.URLError, OSError) as e:
            erro = e
        time.sleep(2 * (tentativa + 1))
    raise erro


def _minutos(t) -> float | None:
    """{"hours": 25, "minutes": 50} -> 1550. Vazio ou nulo -> None."""
    if not t:
        return None
    return t.get("days", 0) * 1440 + t.get("hours", 0) * 60 + t.get("minutes", 0) + t.get("seconds", 0) / 60


def _mc_coletar(inicio: datetime.date, fim: datetime.date) -> dict:
    token = _mc_token()
    if not token:
        raise RuntimeError("Token da Multichat não encontrado no Porta-chaves (serviço multichat360)")
    dias = (fim - inicio).days + 1
    ant_fim = inicio - datetime.timedelta(days=1)
    ant_ini = ant_fim - datetime.timedelta(days=dias - 1)
    pedidos = {
        "tempos": ("/statistics-tickets-times", inicio, fim),
        "anterior": ("/statistics-tickets-times", ant_ini, ant_fim),
        "detalhe": ("/statistics-tickets-per-users-detail", inicio, fim),
        "usuarios": ("/statistics-per-users", inicio, fim),
        "filas": ("/statistics-tickets-queue", inicio, fim),
        "dias": ("/statistics-tickets-evolution-by-period", inicio, fim),
    }
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as ex:
        fut = {k: ex.submit(_mc_get, token, *v) for k, v in pedidos.items()}
        r = {k: f.result() for k, f in fut.items()}

    def geral(lista):
        t = (lista or [{}])[0]
        return {"total": int(t.get("qtd_total_atendimentos") or 0),
                "receptivos": int(t.get("qtd_demanda_receptiva") or 0),
                "ativos": int(t.get("qtd_demanda_ativa") or 0),
                "pendentes": int(t.get("qtd_tickets_pendentes") or 0),
                "tma": _minutos(t.get("tma")), "tme": _minutos(t.get("tme")),
                "contatos_novos": int(t.get("new_contacts") or 0)}

    extremos = {u.get("email"): u for u in (r["usuarios"] or {}).get("users", [])}
    pessoas = []
    for u in r["detalhe"] or []:
        e = extremos.get(u.get("email"), {})
        pessoas.append({
            "nome": u.get("name") or "Sem atendente (aguardando na fila)",
            "sem_atendente": not u.get("name"),
            "total": int(u.get("qtd_por_usuario") or 0),
            "resolvidos": int(u.get("qtd_resolvidos") or 0),
            "em_atendimento": int(u.get("qtd_em_atendimento") or 0),
            "pendentes": int(u.get("qtd_pendentes") or 0),
            "tma": _minutos(u.get("tma")), "tme": _minutos(u.get("tme")),
            "menor": e.get("menor_tempo_por_usuario"), "maior": e.get("maior_tempo_por_usuario"),
        })
    pessoas.sort(key=lambda p: (p["sem_atendente"], -p["total"]))
    por_dia = {datetime.datetime.strptime(d["label"], "%d/%m/%Y").date().isoformat(): int(d["qtd"])
               for d in r["dias"] or [] if d.get("label")}
    return {
        "inicio": inicio.isoformat(), "fim": fim.isoformat(),
        "anterior_inicio": ant_ini.isoformat(), "anterior_fim": ant_fim.isoformat(),
        "geral": geral(r["tempos"]), "anterior": geral(r["anterior"]),
        "pessoas": pessoas,
        "filas": [{"nome": f.get("label"), "qtd": int(f.get("qtd") or 0)} for f in r["filas"] or []],
        "dias": [{"dia": (inicio + datetime.timedelta(days=i)).isoformat(),
                  "qtd": por_dia.get((inicio + datetime.timedelta(days=i)).isoformat(), 0)} for i in range(dias)],
    }


def multichat(inicio: str, fim: str, forcar: bool = False) -> dict:
    try:
        ini, fi = datetime.date.fromisoformat(inicio), datetime.date.fromisoformat(fim)
    except ValueError:
        return {"erro": "Período inválido"}
    if fi < ini or (fi - ini).days > 400:
        return {"erro": "Escolha um período de até 400 dias, com início antes do fim"}
    chave = (ini, fi)
    with _mc_trava:
        guardado = _mc_cache.get(chave)
    if guardado and not forcar and time.time() - guardado["quando"] < MC_CACHE_SEG:
        return guardado
    try:
        resp = {"dados": _mc_coletar(ini, fi), "quando": time.time(), "erro": None}
    except urllib.error.HTTPError as e:
        msg = ("A Multichat recusou o token. Grave o token certo com: "
               "/usr/bin/python3 central/trocar-token-multichat.py") if e.code in (401, 403) \
            else f"A Multichat respondeu HTTP {e.code}"
        return {"dados": guardado["dados"] if guardado else None, "quando": guardado["quando"] if guardado else None, "erro": msg}
    except Exception as e:
        return {"dados": guardado["dados"] if guardado else None, "quando": guardado["quando"] if guardado else None,
                "erro": f"Não consegui falar com a Multichat: {e}"}
    with _mc_trava:
        _mc_cache[chave] = resp
    return resp


# --------------------------------------------------------------------------------------
# Servidor
# --------------------------------------------------------------------------------------
class Central(BaseHTTPRequestHandler):
    server_version = "Central"

    def log_message(self, *args):  # silencioso no Terminal
        pass

    def _host_ok(self) -> bool:
        # Bloqueia páginas de fora que tentem falar com a central (DNS rebinding).
        return self.headers.get("Host", "") in {f"127.0.0.1:{PORTA}", f"localhost:{PORTA}"}

    def _responder(self, status, corpo: bytes, tipo="text/plain; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, obj, status=HTTPStatus.OK):
        self._responder(status, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def do_GET(self):
        if not self._host_ok():
            return self._responder(HTTPStatus.FORBIDDEN, b"Acesso negado")
        caminho = unquote(urlparse(self.path).path)
        if caminho in ("/", "/index.html"):
            pagina = (AQUI / "central.html").read_text(encoding="utf-8").replace("__TOKEN__", TOKEN)
            return self._responder(HTTPStatus.OK, pagina.encode(), TIPOS[".html"])
        if caminho == "/api/estado":
            return self._json(estado())
        if caminho == "/api/contaazul":
            try:
                return self._json(conta_azul())
            except Exception as e:
                return self._json({"erro": f"Não consegui ler a coleta do Conta Azul: {e}"})
        if caminho == "/api/asaas":
            forcar = parse_qs(urlparse(self.path).query).get("forcar") == ["1"]
            return self._json(asaas(forcar))
        if caminho == "/api/multichat":
            q = parse_qs(urlparse(self.path).query)
            hoje = datetime.date.today().isoformat()
            return self._json(multichat(q.get("inicio", [hoje])[0], q.get("fim", [hoje])[0], q.get("forcar") == ["1"]))
        if caminho in ("/marca/assinatura.png", "/marca/simbolo.png"):
            return self._responder(HTTPStatus.OK, (AQUI / caminho.lstrip("/")).read_bytes(), TIPOS[".png"])
        if caminho.startswith("/ver/"):
            return self._servir_arquivo(caminho[len("/ver/"):])
        self._responder(HTTPStatus.NOT_FOUND, b"Nao encontrado")

    def _servir_arquivo(self, resto: str):
        ident, _, sub = resto.partition("/")
        principal = ARQUIVOS.get(ident)
        if not principal:
            return self._responder(HTTPStatus.NOT_FOUND, b"Nao encontrado")
        if sub:
            # Arquivos ao lado do painel (ex.: dados.json e PDFs dos relatórios), sem sair da pasta.
            pasta = principal.parent.resolve()
            alvo = (pasta / sub).resolve()
            if pasta not in alvo.parents:
                return self._responder(HTTPStatus.FORBIDDEN, b"Acesso negado")
        else:
            alvo = principal
        if not alvo.is_file():
            return self._responder(HTTPStatus.NOT_FOUND, "Arquivo não encontrado no Drive".encode())
        self._responder(HTTPStatus.OK, alvo.read_bytes(), TIPOS.get(alvo.suffix.lower(), "application/octet-stream"))

    def do_POST(self):
        if not self._host_ok() or self.headers.get("X-Token") != TOKEN:
            return self._responder(HTTPStatus.FORBIDDEN, b"Acesso negado")
        caminho = urlparse(self.path).path
        if caminho.startswith("/abrir/"):
            ident = caminho[len("/abrir/"):]
            alvo = EXECUTAVEIS.get(ident)
            if not alvo or not alvo.exists():
                return self._json({"ok": False, "msg": "Não encontrei o arquivo"}, HTTPStatus.NOT_FOUND)
            # Mesmo efeito de dar dois cliques no atalho: abre no Terminal.
            subprocess.Popen(["open", "-a", "Terminal", str(alvo)])
            return self._json({"ok": True})
        if caminho == "/pasta":
            corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
            alvo = ARQUIVOS.get(corpo.get("id", "")) or EXECUTAVEIS.get(corpo.get("id", ""))
            if not alvo:
                return self._json({"ok": False}, HTTPStatus.NOT_FOUND)
            subprocess.Popen(["open", "-R", str(alvo)])  # mostra no Finder
            return self._json({"ok": True})
        self._responder(HTTPStatus.NOT_FOUND, b"Nao encontrado")


def main():
    if _porta_aberta(PORTA):
        print(f"A central já está aberta em http://127.0.0.1:{PORTA}")
        subprocess.Popen(["open", f"http://127.0.0.1:{PORTA}"])
        return
    servidor = ThreadingHTTPServer((HOST, PORTA), Central)
    url = f"http://127.0.0.1:{PORTA}"
    print(f"Central do Escritório em {url}  (feche esta janela para desligar)")
    asaas()  # já começa a buscar os números do Asaas
    if "--sem-navegador" not in sys.argv:
        subprocess.Popen(["open", url])
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
