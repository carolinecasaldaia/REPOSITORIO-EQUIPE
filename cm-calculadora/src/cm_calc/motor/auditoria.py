"""Trilha de auditoria: cada cálculo registra origem, fórmula, entradas e resultado.

O motor nunca devolve um número "solto": todo resultado relevante gera um
``Passo`` na ``Memoria``. A exportação (Fase 6) transforma a memória em
planilha e relatório.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Origem(BaseModel):
    """De onde veio um dado ou um critério."""

    model_config = ConfigDict(frozen=True)

    documento: str
    """Ex.: 'Contrato CCB nº ...', 'Sentença', 'Acórdão', 'Dados fictícios de teste'."""
    localizacao: str | None = None
    """Página, cláusula, item do dispositivo."""
    trecho: str | None = None
    """Transcrição literal do trecho, quando houver."""

    def __str__(self) -> str:
        partes = [self.documento]
        if self.localizacao:
            partes.append(self.localizacao)
        return ", ".join(partes)


FICTICIO = Origem(documento="Dados fictícios de teste")


class TipoRessalva(str, Enum):
    PENDENCIA = "pendência"          # falta dado ou decisão; o resultado depende dela
    DIVERGENCIA = "divergência"      # diferença entre fontes/cálculos
    ALERTA = "alerta"                # situação atípica (ex.: amortização negativa)
    PREMISSA = "premissa"            # critério técnico adotado e declarado


class Ressalva(BaseModel):
    model_config = ConfigDict(frozen=True)

    tipo: TipoRessalva
    texto: str
    referencia: str | None = None


class Passo(BaseModel):
    model_config = ConfigDict(frozen=True)

    etapa: str
    descricao: str
    formula: str
    entradas: dict[str, Any]
    resultado: Any
    origem: list[str] = Field(default_factory=list)
    data_referencia: date | None = None


class Memoria(BaseModel):
    """Memória de cálculo acumulada de uma execução."""

    passos: list[Passo] = Field(default_factory=list)
    ressalvas: list[Ressalva] = Field(default_factory=list)

    def registrar(
        self,
        etapa: str,
        descricao: str,
        formula: str,
        entradas: dict[str, Any],
        resultado: Any,
        origem: list[Origem | str] | None = None,
        data_referencia: date | None = None,
    ) -> Any:
        self.passos.append(
            Passo(
                etapa=etapa,
                descricao=descricao,
                formula=formula,
                entradas={k: _serializavel(v) for k, v in entradas.items()},
                resultado=_serializavel(resultado),
                origem=[str(o) for o in (origem or [])],
                data_referencia=data_referencia,
            )
        )
        return resultado

    def ressalvar(self, tipo: TipoRessalva, texto: str, referencia: str | None = None) -> None:
        r = Ressalva(tipo=tipo, texto=texto, referencia=referencia)
        if r not in self.ressalvas:
            self.ressalvas.append(r)

    def da_etapa(self, etapa: str) -> list[Passo]:
        return [p for p in self.passos if p.etapa == etapa]


def _serializavel(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (list, tuple)):
        return [_serializavel(x) for x in v]
    if isinstance(v, dict):
        return {k: _serializavel(x) for k, x in v.items()}
    if isinstance(v, Enum):
        return v.value
    return v
