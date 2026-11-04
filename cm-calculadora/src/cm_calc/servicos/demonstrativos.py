"""Resultados em tabelas (listas de linhas), prontas para tela e para a exportação
em Excel/PDF (Fase 6). Só formatação: nenhum cálculo novo aqui.
"""

from __future__ import annotations

from decimal import Decimal

from ..motor.evolucao import ResultadoEvolucao
from ..motor.numeros import brl
from .liquidacao import ResultadoExecucao


def _d(v: Decimal | None) -> str:
    return "" if v is None else brl(v)


def linhas_evolucao(r: ResultadoEvolucao) -> list[dict[str, str]]:
    return [{"Parcela": str(l.numero_parcela or ""), "Data": l.data.strftime("%d/%m/%Y"),
             "Saldo anterior": _d(l.saldo_anterior), "Juros": _d(l.juros_periodo), "Pagamento": _d(l.pagamento),
             "Amortização": _d(l.amortizacao), "Saldo": _d(l.saldo), "Excedente": _d(l.excedente) if l.excedente else ""}
            for l in r.linhas]


def comparativo_saldos(r: ResultadoExecucao) -> list[dict]:
    rev = {l.numero_parcela: l for l in r.ap02.linhas}
    out = []
    for l in r.ap01.linhas:
        l2 = rev.get(l.numero_parcela)
        out.append({"Parcela": l.numero_parcela, "Saldo original": float(l.saldo),   # float só para o gráfico
                    "Saldo revisado": float(l2.saldo) if l2 else None})
    return out


def linhas_diferencas(r: ResultadoExecucao) -> list[dict[str, str]]:
    if r.ap03 is None:
        return []
    rows = [{"Item": l.descricao, "Pago em": l.data_pagamento.strftime("%d/%m/%Y"), "Pago": _d(l.pago),
             "Devido (revisado)": _d(l.devido), "Diferença": _d(l.diferenca), "A restituir": _d(l.a_restituir),
             "Corrigido": _d(l.corrigido), "Juros": _d(l.juros), "Atualizado": _d(l.atualizado)}
            for l in r.ap03.linhas]
    rows += [{"Item": f"{l.descricao} (pago a menor)", "Pago em": l.data_pagamento.strftime("%d/%m/%Y"), "Pago": _d(l.pago),
              "Devido (revisado)": _d(l.devido), "Diferença": _d(l.diferenca), "A restituir": "", "Corrigido": "",
              "Juros": "", "Atualizado": ""} for l in r.ap03.pagos_a_menor]
    return rows


def resumo(r: ResultadoExecucao) -> list[tuple[str, str]]:
    itens = [
        ("Tipo de cálculo", r.tipo.value),
        ("Data-base", r.data_base.strftime("%d/%m/%Y")),
        ("Parcela original", _d(r.parcela_original)),
        ("Parcela revisada", _d(r.revisao.parcela_regular_revisada)),
        ("Valor financiado revisado", _d(r.revisao.valor_financiado_revisado)),
    ]
    if r.ap03:
        itens += [("Total pago (AP03)", _d(r.ap03.total_pago)), ("Total devido revisado (AP03)", _d(r.ap03.total_devido)),
                  ("Indébito a restituir (nominal)", _d(r.ap03.total_a_restituir_nominal)),
                  ("Indébito atualizado", _d(r.ap03.total_atualizado))]
    if r.honorarios is not None:
        itens.append(("Honorários", _d(r.honorarios)))
    if r.compensacao:
        itens += [("Compensação — a favor do consumidor", _d(r.compensacao.saldo_a_favor_consumidor)),
                  ("Compensação — a favor do credor", _d(r.compensacao.saldo_a_favor_credor))]
    if r.venda:
        itens += [("Saldo revisado na alienação", _d(r.venda.saldo_devedor_revisado)),
                  ("Valor da venda", _d(r.venda.valor_venda)),
                  ("Despesas consideradas", _d(r.venda.despesas_consideradas)),
                  ("Créditos do consumidor compensados", _d(r.venda.creditos_consumidor)),
                  ("Saldo remanescente (consumidor deve)", _d(r.venda.saldo_remanescente_consumidor)),
                  ("Valor a restituir ao consumidor", _d(r.venda.valor_a_restituir_consumidor))]
    return itens


def linhas_ressalvas(r: ResultadoExecucao) -> list[dict[str, str]]:
    return [{"Tipo": x.tipo.value, "Ressalva": x.texto} for x in r.memoria.ressalvas]


def linhas_memoria(r: ResultadoExecucao) -> list[dict[str, str]]:
    return [{"Etapa": p.etapa, "Descrição": p.descricao, "Fórmula": p.formula,
             "Entradas": "; ".join(f"{k}={v}" for k, v in p.entradas.items()),
             "Resultado": str(p.resultado), "Origem": " | ".join(p.origem)} for p in r.memoria.passos]
