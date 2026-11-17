#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gerencia as campanhas do Meta (Facebook / Instagram) do escritório.

Consultar (não muda nada):
    python3 executar.py testar                      # confere o token
    python3 executar.py contas                      # contas de anúncios e páginas
    python3 executar.py campanhas [--todas]
    python3 executar.py conjuntos [--campanha ID] [--todas]
    python3 executar.py anuncios  [--campanha ID | --conjunto ID] [--todas]
    python3 executar.py desempenho [--periodo last_7d] [--nivel campaign|adset|ad]
                                   [--desde 2026-10-01 --ate 2026-10-31] [--diario]

Alterar (pede confirmação; --sim pula a pergunta; tudo fica em ~/.meta-ads/historico.log):
    python3 executar.py pausar ID [ID ...]          # campanha, conjunto ou anúncio
    python3 executar.py ativar ID [ID ...]
    python3 executar.py orcamento ID --diario 80    # em reais (ou --total 1500)
    python3 executar.py renomear ID "Novo nome"
    python3 executar.py duplicar ID                 # a cópia nasce PAUSADA
    python3 executar.py criar-campanha --nome "..." --objetivo OUTCOME_LEADS [--diario 50]
                                                    # nasce PAUSADA
    python3 executar.py chave                       # troca o token (janela oculta)
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

from src.meta import ARQUIVO_ENV, HISTORICO, ErroMeta, Meta, gravar_no_env, mascarar  # noqa: E402

STATUS_ATIVOS = ["ACTIVE", "PAUSED", "IN_PROCESS", "WITH_ISSUES", "PENDING_REVIEW",
                 "DISAPPROVED", "PREAPPROVED", "PENDING_BILLING_INFO", "CAMPAIGN_PAUSED",
                 "ADSET_PAUSED"]
OBJETIVOS = ["OUTCOME_LEADS", "OUTCOME_ENGAGEMENT", "OUTCOME_TRAFFIC", "OUTCOME_AWARENESS",
             "OUTCOME_SALES", "OUTCOME_APP_PROMOTION"]
# Ações que contam como "resultado" para um escritório (lead e conversa no WhatsApp/Direct)
RESULTADOS = {
    "lead": "leads",
    "onsite_conversion.lead_grouped": "leads (form.)",
    "onsite_conversion.messaging_conversation_started_7d": "conversas",
    "link_click": "cliques no link",
}


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------

def reais(centavos):
    if centavos in (None, ""):
        return "-"
    return "R$ " + f"{int(centavos) / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def reais_float(valor):
    return reais(round(float(valor) * 100)) if valor not in (None, "") else "-"


def tabela(linhas, colunas):
    if not linhas:
        print("  (nada encontrado)")
        return
    larg = {c: max(len(c), *(len(str(l.get(c, ""))) for l in linhas)) for c in colunas}
    print("  " + "  ".join(c.ljust(larg[c]) for c in colunas))
    print("  " + "  ".join("-" * larg[c] for c in colunas))
    for l in linhas:
        print("  " + "  ".join(str(l.get(c, "")).ljust(larg[c]) for c in colunas))


def confirmar(args, mensagem):
    print(mensagem)
    if args.sim:
        return True
    if not sys.stdin.isatty():
        print("[!] Sem terminal para confirmar. Repita com --sim se tiver certeza.")
        return False
    return input("Confirma? (s/N) ").strip().lower() in ("s", "sim")


def filtro_status(args):
    return {} if args.todas else {"effective_status": STATUS_ATIVOS}


def orcamento_txt(item):
    if item.get("daily_budget"):
        return reais(item["daily_budget"]) + "/dia"
    if item.get("lifetime_budget"):
        return reais(item["lifetime_budget"]) + " total"
    return "-"


def descrever(meta, id_):
    """Descobre se o ID é campanha, conjunto ou anúncio, e o nome."""
    # A Marketing API não diz o tipo; descobrimos pelo campo que só aquele tipo tem.
    for tipo, campo in (("anúncio", "adset_id"), ("conjunto", "campaign_id"), ("campanha", "objective")):
        try:
            item = meta.get(id_, fields=f"name,effective_status,{campo}")
        except ErroMeta as e:
            if "nonexisting field" in str(e):
                continue
            raise
        return tipo, item.get("name", "?"), item.get("effective_status", "?")
    raise ErroMeta(f"{id_} não é campanha, conjunto nem anúncio.")


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------

def cmd_testar(meta, args):
    eu = meta.get("me", fields="id,name")
    info = meta.get("debug_token", input_token=meta.token).get("data", {})
    print(f"Token {mascarar(meta.token)} válido: {info.get('is_valid')}")
    print(f"  Usuário: {eu.get('name')} ({info.get('type')}) — app {info.get('application')}")
    print(f"  Expira: {'nunca' if not info.get('expires_at') else info.get('expires_at')}")
    falta = {"ads_management", "ads_read"} - set(info.get("scopes", []))
    print("  Permissões de anúncios: " + ("OK" if not falta else "FALTANDO " + ", ".join(falta)))
    print(f"  Conta padrão: {meta.conta_padrao or '(nenhuma)'}  —  API {meta.versao}")


def cmd_contas(meta, args):
    contas = meta.todos("me/adaccounts", fields="id,name,account_status,currency,amount_spent,"
                                                "balance,spend_cap,timezone_name")
    situacao = {1: "ativa", 2: "desativada", 3: "pendência de pagamento", 7: "em análise",
                9: "período de carência", 101: "fechada"}
    print("Contas de anúncios:")
    tabela([{"id": c["id"], "nome": c["name"], "situação": situacao.get(c["account_status"],
             c["account_status"]), "gasto total": reais(c.get("amount_spent")),
             "fuso": c.get("timezone_name"),
             "padrão": "*" if c["id"] == meta.conta_padrao else ""}
            for c in contas], ["id", "nome", "situação", "gasto total", "fuso", "padrão"])
    print("\nPáginas:")
    tabela([{"id": p["id"], "nome": p["name"]} for p in meta.todos("me/accounts", fields="id,name")],
           ["id", "nome"])


def cmd_campanhas(meta, args):
    itens = meta.todos(f"{meta.conta(args.conta)}/campaigns", **filtro_status(args),
                       fields="id,name,objective,effective_status,daily_budget,lifetime_budget,"
                              "start_time,stop_time")
    tabela([{"id": c["id"], "nome": c["name"], "status": c["effective_status"],
             "objetivo": c.get("objective", "").replace("OUTCOME_", ""),
             "orçamento": orcamento_txt(c)} for c in itens],
           ["id", "nome", "status", "objetivo", "orçamento"])


def cmd_conjuntos(meta, args):
    origem = args.campanha or meta.conta(args.conta)
    itens = meta.todos(f"{origem}/adsets", **filtro_status(args),
                       fields="id,name,effective_status,daily_budget,lifetime_budget,"
                              "optimization_goal,campaign{name}")
    tabela([{"id": a["id"], "nome": a["name"], "status": a["effective_status"],
             "campanha": a.get("campaign", {}).get("name", ""),
             "otimiza p/": a.get("optimization_goal", ""), "orçamento": orcamento_txt(a)}
            for a in itens], ["id", "nome", "status", "campanha", "otimiza p/", "orçamento"])


def cmd_anuncios(meta, args):
    origem = args.conjunto or args.campanha or meta.conta(args.conta)
    itens = meta.todos(f"{origem}/ads", **filtro_status(args),
                       fields="id,name,effective_status,adset{name},creative{id,title,body}")
    tabela([{"id": a["id"], "nome": a["name"], "status": a["effective_status"],
             "conjunto": a.get("adset", {}).get("name", ""),
             "criativo": a.get("creative", {}).get("id", "")} for a in itens],
           ["id", "nome", "status", "conjunto", "criativo"])


def cmd_desempenho(meta, args):
    params = {"level": args.nivel,
              "fields": "campaign_name,adset_name,ad_name,spend,impressions,reach,frequency,"
                        "clicks,ctr,cpc,cpm,actions,cost_per_action_type"}
    if args.desde:
        params["time_range"] = {"since": args.desde, "until": args.ate or args.desde}
    else:
        params["date_preset"] = args.periodo
    if args.diario:
        params["time_increment"] = 1
    origem = args.id or meta.conta(args.conta)
    linhas = meta.todos(f"{origem}/insights", **params)

    nome_col = {"campaign": "campaign_name", "adset": "adset_name", "ad": "ad_name",
                "account": "campaign_name"}[args.nivel]
    saida, total_gasto, total_res = [], 0.0, {}
    for l in linhas:
        acoes = {a["action_type"]: int(float(a["value"])) for a in l.get("actions", [])}
        custos = {a["action_type"]: float(a["value"]) for a in l.get("cost_per_action_type", [])}
        res = [(rotulo, acoes[t], custos.get(t)) for t, rotulo in RESULTADOS.items()
               if t in acoes and t != "link_click"]
        gasto = float(l.get("spend", 0))
        total_gasto += gasto
        for rotulo, qtd, _ in res:
            total_res[rotulo] = total_res.get(rotulo, 0) + qtd
        saida.append({
            "dia": l.get("date_start", "") if args.diario else "",
            "nome": l.get(nome_col) or "(conta)",
            "gasto": reais_float(gasto),
            "impressões": f"{int(l.get('impressions', 0)):,}".replace(",", "."),
            "alcance": f"{int(l.get('reach', 0)):,}".replace(",", "."),
            "freq.": f"{float(l.get('frequency', 0)):.2f}",
            "CTR": f"{float(l.get('ctr', 0)):.2f}%",
            "CPC": reais_float(l.get("cpc")),
            "CPM": reais_float(l.get("cpm")),
            "resultados": "; ".join(f"{q} {r} ({reais_float(c)} cada)" for r, q, c in res) or "-",
        })
    if args.json:
        print(json.dumps(linhas, ensure_ascii=False, indent=1))
        return
    colunas = (["dia"] if args.diario else []) + ["nome", "gasto", "impressões", "alcance",
                                                  "freq.", "CTR", "CPC", "CPM", "resultados"]
    periodo = f"{args.desde} a {args.ate or args.desde}" if args.desde else args.periodo
    print(f"Desempenho ({periodo}, por {args.nivel}):")
    tabela(saida, colunas)
    resumo = "; ".join(f"{q} {r} ({reais_float(total_gasto / q)} cada)" for r, q in total_res.items())
    print(f"\n  TOTAL: {reais_float(total_gasto)} gastos" + (f" — {resumo}" if resumo else ""))


# ---------------------------------------------------------------------------
# Alterações
# ---------------------------------------------------------------------------

def _mudar_status(meta, args, status):
    alvos = [(id_, *descrever(meta, id_)) for id_ in args.ids]
    verbo = "PAUSAR" if status == "PAUSED" else "ATIVAR"
    lista = "\n".join(f"  - {t} {n} ({i}) — hoje: {s}" for i, t, n, s in alvos)
    if not confirmar(args, f"Vou {verbo}:\n{lista}"):
        return print("Nada foi alterado.")
    for id_, tipo, nome, _ in alvos:
        meta.post(id_, status=status)
        print(f"  OK: {tipo} {nome} -> {status}")
    if status == "ACTIVE":
        print("  Obs.: um anúncio só roda se a campanha e o conjunto dele também estiverem ativos.")


def cmd_pausar(meta, args):
    _mudar_status(meta, args, "PAUSED")


def cmd_ativar(meta, args):
    _mudar_status(meta, args, "ACTIVE")


def cmd_orcamento(meta, args):
    if (args.diario is None) == (args.total is None):
        raise ErroMeta("Informe --diario OU --total (em reais).")
    tipo, nome, _ = descrever(meta, args.id)
    if tipo not in ("campanha", "conjunto"):
        raise ErroMeta("Orçamento só existe em campanha ou conjunto.")
    atual = meta.get(args.id, fields="daily_budget,lifetime_budget")
    campo = "daily_budget" if args.diario is not None else "lifetime_budget"
    valor = round((args.diario if args.diario is not None else args.total) * 100)
    if not atual.get(campo):
        raise ErroMeta(f"Este {tipo} não usa orçamento {'diário' if campo == 'daily_budget' else 'total'} "
                       f"(hoje: {orcamento_txt(atual)}). Pode ser que o orçamento esteja no outro nível "
                       "(campanha x conjunto).")
    if not confirmar(args, f"Orçamento do {tipo} {nome}: {orcamento_txt(atual)} -> {reais(valor)}"):
        return print("Nada foi alterado.")
    meta.post(args.id, **{campo: valor})
    print("  OK.")


def cmd_renomear(meta, args):
    tipo, nome, _ = descrever(meta, args.id)
    if not confirmar(args, f"Renomear {tipo} \"{nome}\" -> \"{args.nome}\""):
        return print("Nada foi alterado.")
    meta.post(args.id, name=args.nome)
    print("  OK.")


def cmd_duplicar(meta, args):
    """
    Copia peça por peça (campanha -> conjuntos -> anúncios), porque a API só aceita
    cópia "profunda" de menos de 3 objetos por vez. Um anúncio que falhar não
    interrompe os demais; no fim sai a lista do que não foi copiado.
    --destino ID continua dentro de uma cópia que já existe (não recria o topo).
    """
    tipo, nome, _ = descrever(meta, args.id)
    if not confirmar(args, f"Duplicar {tipo} \"{nome}\" (com tudo que tem dentro), cópia PAUSADA"
                           + (f", dentro de {args.destino}" if args.destino else "")):
        return print("Nada foi alterado.")
    renomear = {"rename_strategy": "ONLY_TOP_LEVEL_RENAME", "rename_suffix": " — Cópia"}
    falhas = []

    def copiar_anuncios(conjunto_origem, conjunto_novo):
        # Não usa /copies: com o app em modo de desenvolvimento o Meta recusa, porque
        # a cópia geraria um post novo. Criar o anúncio reaproveitando o MESMO
        # criativo (mesmo post, com curtidas e comentários) funciona.
        for ad in meta.todos(f"{conjunto_origem}/ads",
                             fields="id,name,account_id,creative{id},tracking_specs,conversion_domain"):
            try:
                params = {"name": ad["name"], "adset_id": conjunto_novo, "status": "PAUSED",
                          "creative": {"creative_id": ad["creative"]["id"]}}
                for campo in ("tracking_specs", "conversion_domain"):
                    if ad.get(campo):
                        params[campo] = ad[campo]
                r = meta.post(f"act_{ad['account_id']}/ads", **params)
                print(f"      anúncio {ad['name']} -> {r.get('id')}")
            except ErroMeta as e:
                falhas.append((ad["name"], ad["id"], str(e)))
                print(f"      [!] anúncio {ad['name']}: {e}")

    def copiar_conjunto(conjunto, campanha_nova=None):
        params = {"deep_copy": "false", "status_option": "PAUSED"}
        if campanha_nova:
            params["campaign_id"] = campanha_nova
        else:
            params["rename_options"] = renomear
        try:
            novo = meta.post(f"{conjunto['id']}/copies", **params)["copied_adset_id"]
        except ErroMeta as e:
            if "atribuição" not in str(e) and "attribution" not in str(e):
                raise
            novo = recriar_conjunto(conjunto["id"], campanha_nova)
        print(f"    conjunto {conjunto['name']} -> {novo}")
        copiar_anuncios(conjunto["id"], novo)

    def recriar_conjunto(origem, campanha_nova):
        """Conjunto antigo com janela de atribuição que o Meta não aceita mais em
        conjunto novo: cria do zero com as mesmas configurações e janela de 1 dia."""
        campos = ("name,account_id,campaign_id,optimization_goal,billing_event,bid_strategy,"
                  "bid_amount,daily_budget,lifetime_budget,targeting,promoted_object,"
                  "destination_type,end_time,pacing_type")
        o = meta.get(origem, fields=campos)
        params = {k: v for k, v in o.items()
                  if k not in ("id", "account_id", "campaign_id", "end_time") and v not in (None, "")}
        params.update(campaign_id=campanha_nova or o["campaign_id"], status="PAUSED",
                      attribution_spec=[{"event_type": "CLICK_THROUGH", "window_days": 1}])
        if not campanha_nova:
            params["name"] = o["name"] + " — Cópia"
        print(f"    (janela de atribuição antiga em {o['name']}: recriando com 1 dia após o clique)")
        return meta.post(f"act_{o['account_id']}/adsets", **params)["id"]

    if tipo == "anúncio":
        r = meta.post(f"{args.id}/copies", status_option="PAUSED", rename_options=renomear)
        print(f"  OK: cópia criada -> {r.get('copied_ad_id')}")
        return
    if tipo == "conjunto":
        copiar_conjunto({"id": args.id, "name": nome}, args.destino)
    else:
        nova = args.destino
        if not nova:
            nova = meta.post(f"{args.id}/copies", deep_copy="false", status_option="PAUSED",
                             rename_options=renomear)["copied_campaign_id"]
        print(f"  campanha {nome} -> {nova}")
        for conjunto in meta.todos(f"{args.id}/adsets", fields="id,name"):
            copiar_conjunto(conjunto, nova)
    print(f"  Pronto. {len(falhas)} anúncio(s) não copiado(s)." if falhas else "  Pronto, tudo copiado.")


def cmd_criar_campanha(meta, args):
    params = {"name": args.nome, "objective": args.objetivo, "status": "PAUSED",
              "special_ad_categories": args.categoria_especial or []}
    if args.diario:
        params["daily_budget"] = round(args.diario * 100)
        params["bid_strategy"] = "LOWEST_COST_WITHOUT_CAP"
    else:
        params["is_adset_budget_sharing_enabled"] = "false"
    conta = meta.conta(args.conta)
    if not confirmar(args, f"Criar campanha PAUSADA \"{args.nome}\" ({args.objetivo}) na conta {conta}"
                           + (f", {reais(params['daily_budget'])}/dia" if args.diario else
                              ", orçamento nos conjuntos")):
        return print("Nada foi alterado.")
    r = meta.post(f"{conta}/campaigns", **params)
    print(f"  OK: campanha criada -> {r.get('id')}  (pausada; crie os conjuntos e anúncios e ative)")


def cmd_chave(meta_ignorado, args):
    script = ('display dialog "Cole o token do Meta (System User):" default answer "" '
              'with hidden answer with title "Meta Ads" buttons {"Cancelar", "OK"} default button "OK"')
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    token = r.stdout.split("text returned:", 1)[1].strip() if r.returncode == 0 and \
        "text returned:" in r.stdout else ""
    if not token:
        return print("Cancelado; nada mudou.")
    Meta(token=token).get("me", fields="id")  # valida antes de gravar
    gravar_no_env("META_TOKEN", token)
    print(f"Token {mascarar(token)} guardado em {ARQUIVO_ENV}")


# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Meta Ads do escritório",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("testar")
    sub.add_parser("contas")
    sub.add_parser("chave")
    for nome in ("campanhas", "conjuntos", "anuncios"):
        s = sub.add_parser(nome)
        s.add_argument("--todas", action="store_true", help="inclui arquivadas/excluídas")
        if nome != "campanhas":
            s.add_argument("--campanha")
        if nome == "anuncios":
            s.add_argument("--conjunto")
    s = sub.add_parser("desempenho")
    s.add_argument("id", nargs="?", help="campanha/conjunto/anúncio (padrão: a conta inteira)")
    s.add_argument("--periodo", default="last_7d",
                   help="today, yesterday, last_7d, last_14d, last_30d, this_month, last_month, maximum")
    s.add_argument("--desde")
    s.add_argument("--ate")
    s.add_argument("--nivel", default="campaign", choices=["account", "campaign", "adset", "ad"])
    s.add_argument("--diario", action="store_true", help="uma linha por dia")
    s.add_argument("--json", action="store_true")

    for nome in ("pausar", "ativar"):
        s = sub.add_parser(nome)
        s.add_argument("ids", nargs="+")
    s = sub.add_parser("orcamento")
    s.add_argument("id")
    s.add_argument("--diario", type=float)
    s.add_argument("--total", type=float)
    s = sub.add_parser("renomear")
    s.add_argument("id")
    s.add_argument("nome")
    s = sub.add_parser("duplicar")
    s.add_argument("id")
    s.add_argument("--destino", help="campanha (ou conjunto) já copiada onde continuar")
    s = sub.add_parser("criar-campanha")
    s.add_argument("--nome", required=True)
    s.add_argument("--objetivo", required=True, choices=OBJETIVOS)
    s.add_argument("--diario", type=float, help="orçamento diário da campanha (CBO), em reais")
    s.add_argument("--categoria-especial", action="append",
                   choices=["FINANCIAL_PRODUCTS_SERVICES", "EMPLOYMENT", "HOUSING",
                            "ISSUES_ELECTIONS_POLITICS"])
    for s in sub.choices.values():
        s.add_argument("--sim", action="store_true", help="não pede confirmação")
        s.add_argument("--conta", help="conta de anúncios (act_...); padrão = META_CONTA do .env")

    args = p.parse_args()
    try:
        meta = None if args.cmd == "chave" else Meta()
        globals()["cmd_" + args.cmd.replace("-", "_")](meta, args)
    except ErroMeta as e:
        print(f"[!] {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
