"""Verbas adicionais autorizadas pelo título (perdas e danos, multas, restituição
do veículo convertida em valor, despesas).

Trava: toda verba exige citação literal do trecho do título que a determina.
Sem trecho, a verba é recusada — o motor não cria verbas por inferência.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, model_validator

from .auditoria import Memoria, Origem
from .numeros import PoliticaArredondamento, arredondar


class VerbaAutorizada(BaseModel):
    model_config = ConfigDict(frozen=True)

    descricao: str
    data_base: date
    valor_fixo: Decimal | None = None
    percentual: Decimal | None = None
    valor_base: Decimal | None = None
    descricao_base: str | None = None
    origem_titulo: Origem

    @model_validator(mode="after")
    def _exige_titulo(self):
        if not (self.origem_titulo.trecho and self.origem_titulo.trecho.strip()):
            raise ValueError(
                f"verba '{self.descricao}' sem trecho do título que a autorize: não pode ser calculada"
            )
        if (self.valor_fixo is None) == (self.percentual is None):
            raise ValueError("informe valor_fixo OU percentual (sobre valor_base)")
        if self.percentual is not None and self.valor_base is None:
            raise ValueError("verba percentual exige valor_base")
        return self


def calcular_verba(verba: VerbaAutorizada, politica: PoliticaArredondamento, memoria: Memoria) -> Decimal:
    if verba.valor_fixo is not None:
        valor, formula = verba.valor_fixo, "V = valor fixado no título"
    else:
        valor, formula = verba.valor_base * verba.percentual, "V = base × percentual"
    valor = arredondar(valor, politica)
    memoria.registrar(
        "verbas_adicionais", verba.descricao, formula,
        {"valor_fixo": verba.valor_fixo, "percentual": verba.percentual,
         "valor_base": verba.valor_base, "descricao_base": verba.descricao_base},
        valor, [verba.origem_titulo], verba.data_base,
    )
    return valor
