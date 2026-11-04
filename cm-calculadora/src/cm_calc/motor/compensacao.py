"""Compensação entre o crédito do consumidor e o saldo devedor revisado.

Só se compensam valores posicionados na MESMA data-base. Valores em datas
distintas precisam ser atualizados antes (``atualizacao.atualizar`` para o
crédito; ``evolucao.evoluir_saldo(data_final=...)`` para o saldo).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from .auditoria import Memoria, Origem
from .controle import ControleUtilizacao
from .numeros import ZERO


class Posicao(BaseModel):
    model_config = ConfigDict(frozen=True)

    descricao: str
    valor: Decimal
    data_base: date
    id: str | None = None
    """Obrigatório quando houver ``ControleUtilizacao`` (evita compensar o mesmo crédito duas vezes)."""


class ResultadoCompensacao(BaseModel):
    model_config = ConfigDict(frozen=True)

    data_base: date
    credito_consumidor: Decimal
    saldo_devedor: Decimal
    saldo_a_favor_consumidor: Decimal
    saldo_a_favor_credor: Decimal


def compensar(
    creditos: list[Posicao],
    debitos: list[Posicao],
    origem_titulo: Origem,
    memoria: Memoria,
    controle: ControleUtilizacao | None = None,
) -> ResultadoCompensacao:
    datas = {p.data_base for p in creditos + debitos}
    if len(datas) != 1:
        raise ValueError(
            "compensação exige valores na mesma data-base; encontradas: "
            + ", ".join(sorted(d.strftime("%d/%m/%Y") for d in datas))
        )
    if any(p.valor < 0 for p in creditos + debitos):
        raise ValueError("valores negativos na compensação: informe créditos e débitos separadamente")
    data_base = datas.pop()
    if controle is not None:
        for p in creditos + debitos:
            controle.usar(p.id, f"compensação em {data_base:%d/%m/%Y}")
    c = sum((p.valor for p in creditos), ZERO)
    d = sum((p.valor for p in debitos), ZERO)
    liquido = c - d
    res = ResultadoCompensacao(
        data_base=data_base, credito_consumidor=c, saldo_devedor=d,
        saldo_a_favor_consumidor=max(liquido, ZERO), saldo_a_favor_credor=max(-liquido, ZERO),
    )
    memoria.registrar(
        "compensacao",
        f"Compensação em {data_base:%d/%m/%Y}",
        "líquido = Σ créditos do consumidor − Σ saldo devedor revisado",
        {"creditos": {p.descricao: p.valor for p in creditos},
         "debitos": {p.descricao: p.valor for p in debitos}},
        {"a_favor_consumidor": res.saldo_a_favor_consumidor, "a_favor_credor": res.saldo_a_favor_credor},
        [origem_titulo], data_base,
    )
    return res
