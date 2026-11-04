"""Honorários advocatícios e despesas, conforme o título.

A base de cálculo (condenação, proveito econômico, valor da causa atualizado
ou valor fixo) é uma escolha do título: o motor recebe o VALOR da base já
identificado e registrado, e nunca decide sozinho qual montante é "a condenação".
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from .auditoria import Memoria, Origem
from .numeros import UM, ZERO, PoliticaArredondamento, arredondar


class BaseHonorarios(str, Enum):
    CONDENACAO = "valor da condenação"
    PROVEITO_ECONOMICO = "proveito econômico"
    VALOR_CAUSA_ATUALIZADO = "valor atualizado da causa"
    VALOR_FIXO = "valor fixo"


class ParametrosHonorarios(BaseModel):
    model_config = ConfigDict(frozen=True)

    base: BaseHonorarios
    percentual: Decimal | None = None
    valor_fixo: Decimal | None = None
    cota_devedor: Decimal = UM
    """Fração a cargo da parte devedora (sucumbência recíproca: ex. 0.70)."""
    devedor: str
    origem_titulo: Origem

    @model_validator(mode="after")
    def _coerencia(self):
        if self.base is BaseHonorarios.VALOR_FIXO:
            if self.valor_fixo is None or self.percentual is not None:
                raise ValueError("honorários em valor fixo exigem valor_fixo e não aceitam percentual")
        elif self.percentual is None:
            raise ValueError("honorários sobre base exigem percentual")
        if not (ZERO < self.cota_devedor <= UM):
            raise ValueError("cota_devedor deve estar entre 0 e 1")
        return self


def calcular_honorarios(
    params: ParametrosHonorarios,
    valor_base: Decimal | None,
    politica: PoliticaArredondamento,
    memoria: Memoria,
    descricao_base: str = "",
) -> Decimal:
    if params.base is BaseHonorarios.VALOR_FIXO:
        bruto = params.valor_fixo
        formula = "H = valor fixo × cota"
    else:
        if valor_base is None:
            raise ValueError(f"informe o valor da base ({params.base.value})")
        bruto = valor_base * params.percentual
        formula = "H = base × percentual × cota"
    total = arredondar(bruto * params.cota_devedor, politica)
    memoria.registrar(
        "honorarios",
        f"Honorários a cargo de {params.devedor} — base: {params.base.value}",
        formula,
        {"base": params.base.value, "valor_base": valor_base, "descricao_base": descricao_base,
         "percentual": params.percentual, "valor_fixo": params.valor_fixo, "cota": params.cota_devedor},
        total, [params.origem_titulo],
    )
    return total
