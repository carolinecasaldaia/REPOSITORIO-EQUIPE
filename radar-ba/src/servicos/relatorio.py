"""Relatório de cada execução (item 16) e trilha de auditoria (item 17)."""
import datetime
import json

from src.config import ajustes
from src.servicos.prioridade import EMOJI
from src.util.http import AUDITORIA


def montar_texto(execucao, tribunais_com_erro=None):
    d = execucao.para_dict()
    tribunais_com_erro = tribunais_com_erro or []
    linhas = [
        "RADAR DE BUSCA E APREENSÃO",
        "=" * 58,
        "Data:                      %s" % datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "Modo de varredura:         %s" % d["modo"],
        "Clientes monitorados:      %d" % d["clientes_verificados"],
        "Consultas realizadas:      %d" % d["auditoria"]["consultas"],
        "Processos encontrados:     %d" % d["processos_encontrados"],
        "Novas buscas e apreensões: %d" % d["novos"],
        "Alertas críticos:          %d" % d["alertas_criticos"],
        "Tribunais alcançados:      %s" % (", ".join(d["tribunais"]) or "—"),
        "Tribunais indisponíveis:   %s" % (", ".join(tribunais_com_erro) or "nenhum"),
        "Erros:                     %d" % (len(d["erros"]) + d["auditoria"]["erros"]),
        "Duração:                   %.1fs" % d["duracao_s"],
    ]
    if execucao.itens:
        linhas += ["", "Novos processos por prioridade:"]
        for r, c, prioridade, motivo in execucao.itens:
            linhas.append("  %s %-10s %-26s %-7s %s" % (
                EMOJI.get(prioridade, " "), prioridade, r.numero_processo,
                r.tribunal, (c.get("nome") or r.reu or "")[:34]))
    if d["erros"]:
        linhas += ["", "Erros registrados:"] + ["  - %s" % e for e in d["erros"][:20]]
    return "\n".join(linhas)


def salvar(execucao, tribunais_com_erro=None):
    """Grava relatório .txt e auditoria .json em RELATÓRIOS/."""
    pasta = ajustes.PASTA_RELATORIOS
    pasta.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.datetime.now().strftime("%Y%m%d-%H%M")

    txt = pasta / ("radar-%s.txt" % carimbo)
    txt.write_text(montar_texto(execucao, tribunais_com_erro), encoding="utf-8")

    dados = execucao.para_dict()
    dados["processos"] = [{
        "numero": r.numero_processo, "tribunal": r.tribunal,
        "classe": r.classe_nome, "banco": r.banco_normalizado,
        "orgao": r.orgao_julgador, "publicacao": r.data_publicacao,
        "distribuicao": r.data_distribuicao, "prioridade": p,
        "status": r.status_casamento, "confianca": r.confianca,
        "cliente_id": c.get("id"),          # nunca o CPF
    } for r, c, p, _ in execucao.itens]
    dados["auditoria_detalhada"] = AUDITORIA.registros[-500:]

    js = pasta / ("radar-%s.json" % carimbo)
    js.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    return txt, js
