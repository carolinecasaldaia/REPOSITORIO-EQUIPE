#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cumprimento de sentença <-> Astrea (sessão da conta Claude no perfil do Chrome da automação).

    PY=~/.cadastro-astrea/venv/bin/python
    $PY cumprimento.py triagem [--tudo]
    $PY cumprimento.py caso 0725012-67.2025.8.02.0001 [--pasta ~/CM-Calculos-Dados/cumprimento/<CASO>]
    $PY cumprimento.py registrar 0725012-67.2025.8.02.0001 --peticao ARQ.docx [--memoria ARQ.xlsx] [--gravar]

triagem    Lê os andamentos de todos os processos ativos e lista os que têm TRÂNSITO EM JULGADO e ainda
           não têm cumprimento (sem a etiqueta "CUMPRIMENTO DE SENTENÇA - HO SUCUMBENCIA" e sem
           andamento de cumprimento/mudança de classe). Cada caso vem classificado (polo do cliente,
           resultado detectado), mas a decisão é da Dra. Caroline. Só consulta.
           Guarda os andamentos em cache e só relê os processos com movimentação nova (--tudo relê todos).
           Saída: ~/CM-Calculos-Dados/cumprimento/_astrea/triagem-AAAAMMDD.csv (abre no Excel) e .json.
caso       Dados do processo (nº, vara, link do TJ, cliente e polo, parte contrária, valor da causa) e os
           andamentos-chave (sentença, acórdão, trânsito, citação/AR/mandado, contestação, cumprimento)
           para montar a ficha. Grava <pasta>/astrea/caso.json e andamentos.md. Só consulta.
           Os andamentos são PISTAS: datas e dispositivo se confirmam nos autos (regra do agente).
registrar  Quando a petição está pronta: cria a tarefa "REVISAR E PROTOCOLAR CUMPRIMENTO DE SENTENÇA"
           para a Luysa (vencimento em 2 dias úteis), comenta com os caminhos dos arquivos e põe a
           etiqueta "CUMPRIMENTO DE SENTENÇA - HO SUCUMBENCIA" no processo. SEM --gravar só mostra o que
           faria. Não duplica: se já houver tarefa aberta com o mesmo título no caso, não cria outra.
           Nunca protocola nada.

Regras da Dra. Caroline (09/11/2026): tarefa para a Luysa em 2 dias úteis; etiqueta existente
"CUMPRIMENTO DE SENTENÇA - HO SUCUMBENCIA"; triagem com todos os transitados, classificados; sob demanda.
"""
import csv
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from astrea import Astrea, dias_uteis_depois, so_digitos  # noqa: E402  (integração geral)

DADOS = Path.home() / "CM-Calculos-Dados" / "cumprimento"
CASA = DADOS / "_astrea"
CACHE = CASA / "cache-andamentos.json"

LUYSA = "5424480016072704"              # Luysa Thalyne de Jesus Rocha
TAG_CUMPRIMENTO = "6041961008529408"    # CUMPRIMENTO DE SENTENÇA - HO SUCUMBENCIA
TAG_EXECUCAO_HO = "6748896016007168"    # Execução de HO Sucumbenciais (também indica cumprimento)
TITULO_TAREFA = "REVISAR E PROTOCOLAR CUMPRIMENTO DE SENTENÇA"
DIAS_UTEIS = 2

TRANSITO = re.compile(r"^\s*(transitad[oa] em julgado|certid[ãa]o de tr[âa]nsito|tr[âa]nsito em julgado\s*$)", re.I)
TRANSITO_DATA = re.compile(r"transitad[oa] em julgado em (\d{2}/\d{2}/\d{4})", re.I)
CUMPRIMENTO = re.compile(r"cumprimento de senten[çc]a|evolu[íi]d[ao] a classe|altera[çc][ãa]o de classe"
                         r"|execu[çc][ãa]o de (t[íi]tulo judicial|senten[çc]a)", re.I)
PADROES_DECISAO = [  # (rótulo, padrão) — só pistas; quem decide é a advogada
    ("procedente", re.compile(r"julgo procedente|julgo procedentes", re.I)),
    ("parcialmente procedente", re.compile(r"julgo parcialmente procedente", re.I)),
    ("improcedente", re.compile(r"julgo improcedente", re.I)),
    ("extinto", re.compile(r"julgo extint|extin[çc][ãa]o do processo|extinto o processo|sem resolu[çc][ãa]o do m[ée]rito", re.I)),
    ("acordo/homologação", re.compile(r"homologo|homologado o acordo|homologa[çc][ãa]o de acordo", re.I)),
    ("recurso provido", re.compile(r"dar provimento|dou provimento|deram provimento|provimento ao recurso", re.I)),
    ("recurso não provido", re.compile(r"negar provimento|nego provimento|negaram provimento", re.I)),
]
CHAVE = [  # andamentos que interessam à ficha
    ("trânsito", TRANSITO),
    ("sentença", re.compile(r"julgo (parcialmente )?(im)?procedente|senten[çc]a|julgo extint", re.I)),
    ("acórdão", re.compile(r"ac[óo]rd[ãa]o|data do julgamento|provimento", re.I)),
    ("citação", re.compile(r"cita[çc][ãa]o|aviso de recebimento|\bAR\b|mandado .*cumprid|carta precat", re.I)),
    ("contestação", re.compile(r"contesta[çc][ãa]o", re.I)),
    ("cumprimento", CUMPRIMENTO),
    ("honorários/custas", re.compile(r"honor[áa]ri|custas finais|sucumb", re.I)),
]


def log(t):
    print(datetime.now().strftime("%H:%M:%S"), t, flush=True)


def ler(p, padrao):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def gravar_json(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


# ------------------------------------------------------------------ análise dos andamentos

def analisar(hs):
    """hs em ordem do mais novo para o mais antigo (como o Astrea devolve)."""
    proc = [h for h in hs if h["tipo"] == "AUTOMATIC_LAWSUIT"]
    trans = [h for h in proc if TRANSITO.search(h["texto"])]
    data_tr = ""
    for h in proc:
        m = TRANSITO_DATA.search(h["texto"])
        if m:
            data_tr = m.group(1)
            break
    cump = [h for h in proc if CUMPRIMENTO.search(h["texto"])]
    achados = []
    for rot, p in PADROES_DECISAO:
        if any(p.search(h["texto"]) for h in hs):
            achados.append(rot)
    return {"transito": bool(trans),
            "transito_andamento": trans[0]["data"] if trans else "",
            "transito_data": data_tr,
            "cumprimento_andamento": cump[0]["data"] if cump else "",
            "resultado_detectado": ", ".join(achados) or "não identificado"}


def polo(caso, detalhe):
    papel = ((detalhe or {}).get("customer") or {}).get("stakeholderRoleName") or ""
    if papel:
        return papel
    tit = caso.get("title") or ""
    cli = (caso.get("customer") or "").lower()
    if " x " in tit and cli:
        return "Autor" if tit.lower().startswith(cli[:15]) else "Réu"
    return ""


def parte_contraria(detalhe):
    return "; ".join(s["contactName"] for s in (detalhe or {}).get("stakeholders", [])
                     if s.get("roleType") == 1)


# ------------------------------------------------------------------ comandos

def cmd_triagem(tudo=False):
    cache = {} if tudo else ler(CACHE, {})
    hoje = date.today()
    with Astrea() as a:
        casos = [c for c in a.casos() if c.get("type") == "CTE_LAWSUIT" and c.get("active", True)]
        log("%d processos ativos" % len(casos))
        relidos = 0
        for i, c in enumerate(casos):
            ent = cache.get(c["id"])
            if ent and ent.get("ultimo_mov") == c.get("lastMovement"):
                continue
            hs = so_processo(a.andamentos(c["id"]))
            cache[c["id"]] = {"ultimo_mov": c.get("lastMovement"), "analise": analisar(hs)}
            relidos += 1
            if relidos % 100 == 0:
                log("  %d relidos (%d/%d)" % (relidos, i + 1, len(casos)))
                gravar_json(CACHE, cache)
        gravar_json(CACHE, cache)
        log("%d processos relidos (os demais sem movimentação nova)" % relidos)

        linhas = []
        for c in casos:
            an = cache[c["id"]]["analise"]
            if not an["transito"]:
                continue
            tags = set(c.get("tagIds") or [])
            ja = []
            if TAG_CUMPRIMENTO in tags:
                ja.append("etiqueta CUMPRIMENTO")
            if TAG_EXECUCAO_HO in tags:
                ja.append("etiqueta Execução de HO")
            if an["cumprimento_andamento"]:
                ja.append("andamento de cumprimento em " + an["cumprimento_andamento"])
            det = a.detalhe(c["id"])
            linhas.append({
                "situacao": "JÁ TEM CUMPRIMENTO" if ja else "SEM CUMPRIMENTO",
                "processo": c.get("number", ""), "cliente": c.get("customer", ""),
                "polo_cliente": polo(c, det), "parte_contraria": parte_contraria(det),
                "tipo": c.get("lawsuitType", ""), "vara": c.get("court", ""),
                "transito_em": an["transito_data"], "andamento_transito": an["transito_andamento"],
                "resultado_detectado": an["resultado_detectado"], "sinais_de_cumprimento": "; ".join(ja),
                "ultima_movimentacao": c.get("lastMovement", ""),
                "link_astrea": "https://astrea.net.br/#/main/folders/detail/%s" % c["id"],
                "link_tribunal": (det or {}).get("urlLawsuit", ""), "caso_id": c["id"]})
    sem = [l for l in linhas if l["situacao"] == "SEM CUMPRIMENTO"]
    sem.sort(key=lambda l: l["andamento_transito"], reverse=True)
    com = [l for l in linhas if l["situacao"] != "SEM CUMPRIMENTO"]
    linhas = sem + com
    base = CASA / ("triagem-%s" % hoje.strftime("%Y%m%d"))
    CASA.mkdir(parents=True, exist_ok=True)
    with open(str(base) + ".csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]) if linhas else ["processo"], delimiter=";")
        w.writeheader()
        w.writerows(linhas)
    gravar_json(str(base) + ".json", {"gerado_em": datetime.now().isoformat(timespec="seconds"),
                                      "linhas": linhas})
    print("\n%d com trânsito em julgado: %d SEM cumprimento, %d já com cumprimento."
          % (len(linhas), len(sem), len(com)))
    print("Lista: %s.csv" % base)
    print("Aviso: polo e resultado são pistas lidas dos andamentos; confirme nos autos.")


def achar_caso(a, numero):
    try:
        return a.achar_caso(numero)
    except ValueError as e:
        raise SystemExit(str(e))


def so_processo(hs):
    """Só andamentos do tribunal e publicações (tira tarefas, prazos e históricos internos)."""
    return [h for h in hs if h["tipo"] in ("AUTOMATIC_LAWSUIT", "CLIPPING")]


def cmd_caso(numero, pasta=None):
    with Astrea() as a:
        c = achar_caso(a, numero)
        det = a.detalhe(c["id"])
        hs = so_processo(a.andamentos(c["id"]))
    an = analisar(hs)
    chave = []
    for h in hs:
        rot = [r for r, p in CHAVE if p.search(h["texto"])]
        if rot:
            chave.append({"data": h["data"], "marcas": rot,
                          "origem": "tribunal" if h["tipo"] == "AUTOMATIC_LAWSUIT" else "publicação",
                          "texto": h["texto"][:1500]})
    caso = {
        "lido_em": datetime.now().isoformat(timespec="seconds"),
        "aviso": "Pistas do Astrea. Datas (citação, trânsito) e dispositivo se confirmam nos autos.",
        "caso_id": c["id"], "processo": c.get("number"), "titulo": c.get("title"),
        "cliente": c.get("customer"), "polo_cliente": polo(c, det), "parte_contraria": parte_contraria(det),
        "tipo": c.get("lawsuitType"), "vara": det.get("courtFormatted") or c.get("court"),
        "instancia_atual": det.get("currentInstanceNumber"), "link_tribunal": det.get("urlLawsuit"),
        "link_astrea": "https://astrea.net.br/#/main/folders/detail/%s" % c["id"],
        "valor_da_causa_astrea": det.get("demandAmount") or det.get("amount"),
        "responsavel_astrea": (det.get("responsible") or {}).get("name"),
        "etiquetas": c.get("tagIds") or [], "analise": an, "andamentos_chave": chave,
    }
    destino = Path(pasta).expanduser() if pasta else DADOS / so_digitos(numero)
    destino = destino / "astrea"
    gravar_json(destino / "caso.json", caso)
    md = ["# %s — %s" % (caso["processo"], caso["titulo"]), "",
          "- Cliente: %s (%s) · Parte contrária: %s" % (caso["cliente"], caso["polo_cliente"], caso["parte_contraria"]),
          "- Vara: %s · Tipo: %s" % (caso["vara"], caso["tipo"]),
          "- Trânsito: %s (andamento de %s) · Resultado detectado: %s"
          % (an["transito_data"] or "data não informada", an["transito_andamento"] or "—", an["resultado_detectado"]),
          "- Tribunal: %s" % caso["link_tribunal"], "", "> " + caso["aviso"], "",
          "## Todos os andamentos (mais novo primeiro)", ""]
    for h in hs:
        md.append("- **%s** [%s] %s" % (h["data"], "TJ" if h["tipo"] == "AUTOMATIC_LAWSUIT" else "pub",
                                        h["texto"].replace("\n", " ")[:900]))
    (destino / "andamentos.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({k: caso[k] for k in ("processo", "cliente", "polo_cliente", "parte_contraria", "vara",
                                           "tipo", "link_tribunal")}, ensure_ascii=False, indent=1))
    print("Trânsito: %s | resultado detectado: %s | %d andamentos-chave"
          % (an["transito_data"] or an["transito_andamento"] or "não achado", an["resultado_detectado"], len(chave)))
    print("Gravado: %s e %s" % (destino / "caso.json", destino / "andamentos.md"))


def cmd_registrar(numero, peticao, memoria=None, gravar_astrea=False):
    arquivos = [Path(p).expanduser() for p in (peticao, memoria) if p]
    faltando = [str(p) for p in arquivos if not p.is_file()]
    if faltando:
        raise SystemExit("Arquivo não encontrado: " + ", ".join(faltando))
    venc = dias_uteis_depois(date.today(), DIAS_UTEIS)
    comentario = ("Cumprimento de sentença calculado pelo Claude (agente macedo-liquidacao), PRONTO PARA "
                  "REVISÃO DA LUYSA / DRA. CAROLINE MACEDO. Não foi protocolado.\n"
                  + "\n".join("- " + str(p) for p in arquivos))
    with Astrea() as a:
        c = achar_caso(a, numero)
        tags = set(c.get("tagIds") or [])
        abertas = [t for t in a.tarefas_do_caso(c["id"])
                   if t["aberta"] and (t["titulo"] or "").strip().upper() == TITULO_TAREFA]
        print("Processo %s — %s" % (c.get("number"), c.get("title")))
        print("Tarefa: \"%s\" para Luysa, vencimento %s%s" % (TITULO_TAREFA, venc.strftime("%d/%m/%Y"),
              " — JÁ EXISTE aberta (id %s), não crio outra" % abertas[0]["id"] if abertas else ""))
        print("Comentário:\n" + comentario)
        print("Etiqueta CUMPRIMENTO DE SENTENÇA - HO SUCUMBENCIA: %s"
              % ("já está no caso" if TAG_CUMPRIMENTO in tags else "será posta"))
        if not gravar_astrea:
            print("\nSIMULAÇÃO: nada foi gravado no Astrea. Rode de novo com --gravar para gravar.")
            return
        if not abertas:
            t = a.criar_tarefa(c["id"], TITULO_TAREFA, LUYSA, venc, 2)
            a.comentar(t["id"], comentario)
            print("Tarefa criada (id %s)." % t["id"])
        if TAG_CUMPRIMENTO not in tags:
            a.etiqueta_caso("por", c["id"], TAG_CUMPRIMENTO)
            print("Etiqueta posta.")
        ok = [t for t in a.tarefas_do_caso(c["id"]) if t["aberta"] and (t["titulo"] or "").strip().upper() == TITULO_TAREFA]
        print("Conferência: %d tarefa(s) aberta(s) \"%s\" no caso; responsável: %s; vencimento: %s"
              % (len(ok), TITULO_TAREFA, ok[0]["responsavel"] if ok else "—", ok[0]["vence"] if ok else "—"))


def main(argv):
    if not argv or argv[0] not in ("triagem", "caso", "registrar"):
        print(__doc__)
        return 1
    op = lambda nome: argv[argv.index(nome) + 1] if nome in argv else None
    if argv[0] == "triagem":
        cmd_triagem(tudo="--tudo" in argv)
    elif argv[0] == "caso":
        cmd_caso(argv[1], op("--pasta"))
    else:
        if not op("--peticao"):
            raise SystemExit("Informe --peticao <arquivo da petição pronta>.")
        cmd_registrar(argv[1], op("--peticao"), op("--memoria"), "--gravar" in argv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
