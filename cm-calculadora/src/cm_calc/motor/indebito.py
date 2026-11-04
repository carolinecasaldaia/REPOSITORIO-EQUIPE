"""Repetição do indébito: simples ou em dobro, conforme o título.

A modalidade nunca é presumida. O título pode determinar:
- SIMPLES para tudo;
- DOBRO para tudo;
- DOBRO_A_PARTIR_DE uma data de corte (pagamentos anteriores, simples).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from .auditoria import Memoria, Origem
from .numeros import UM, D


class Modalidade(str, Enum):
    SIMPLES = "simples"
    DOBRO = "dobro"
    DOBRO_A_PARTIR_DE = "dobro_a_partir_de"


class RegraRestituicao(BaseModel):
    model_config = ConfigDict(frozen=True)

    modalidade: Modalidade
    data_corte: date | None = None
    """Pagamentos nesta data ou depois são restituídos em dobro."""
    origem_titulo: Origem

    @model_validator(mode="after")
    def _corte(self):
        if self.modalidade is Modalidade.DOBRO_A_PARTIR_DE and self.data_corte is None:
            raise ValueError("modalidade dobro_a_partir_de exige data_corte")
        if self.modalidade is not Modalidade.DOBRO_A_PARTIR_DE and self.data_corte is not None:
            raise ValueError("data_corte só se aplica à modalidade dobro_a_partir_de")
        return self

    def multiplicador(self, data_pagamento: date) -> Decimal:
        if self.modalidade is Modalidade.SIMPLES:
            return UM
        if self.modalidade is Modalidade.DOBRO:
            return D(2)
        return D(2) if data_pagamento >= self.data_corte else UM


def valor_a_restituir(
    valor_indevido: Decimal,
    data_pagamento: date,
    regra: RegraRestituicao,
    memoria: Memoria | None = None,
    descricao: str = "",
) -> Decimal:
    if valor_indevido < 0:
        raise ValueError("valor indevido negativo: não há indébito a restituir")
    m = regra.multiplicador(data_pagamento)
    total = valor_indevido * m
    if memoria is not None:
        memoria.registrar(
            "restituicao",
            f"Indébito {descricao} pago em {data_pagamento:%d/%m/%Y}".strip(),
            "R = valor indevido × multiplicador (1 simples; 2 dobro)",
            {"valor_indevido": valor_indevido, "modalidade": regra.modalidade.value,
             "data_corte": regra.data_corte.isoformat() if regra.data_corte else None,
             "multiplicador": m},
            total, [regra.origem_titulo], data_pagamento,
        )
    return total
