"""Estruturas da validação pericial."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

COLUNAS = ("numero", "data", "saldo_anterior", "juros", "amortizacao", "prestacao", "saldo", "pago", "devido",
           "diferenca", "restituir", "fator", "corrigido", "meses_mora", "juros_mora", "subtotal", "total")

ROTULO_COLUNA = {
    "numero": "Nº", "data": "Data", "saldo_anterior": "Saldo anterior", "juros": "Juros", "amortizacao": "Amortização",
    "prestacao": "Prestação", "saldo": "Saldo", "pago": "Valor pago", "devido": "Valor devido", "diferenca": "Diferença",
    "restituir": "A restituir", "fator": "Fator de correção", "corrigido": "Valor corrigido", "meses_mora": "Meses de mora",
    "juros_mora": "Juros de mora", "subtotal": "Subtotal",
    "total": "Total atualizado",
}


class LinhaPericial(BaseModel):
    numero: int | None = None
    data: date | None = None
    valores: dict[str, Decimal] = Field(default_factory=dict)
    pagina: int | None = None
    texto: str = ""


class TabelaPericial(BaseModel):
    apendice: str
    """AP01, AP02 ou AP03."""
    colunas: list[str]
    linhas: list[LinhaPericial]
    totais: dict[str, Decimal] = Field(default_factory=dict)
    origem: str
    avisos: list[str] = Field(default_factory=list)


class IndicioMetodologia(BaseModel):
    tema: str
    descricao: str
    pagina: int
    trecho: str


class Parecer(BaseModel):
    arquivo: str
    sha256: str
    tabelas: dict[str, TabelaPericial]
    metodologia: list[IndicioMetodologia]
    avisos: list[str] = Field(default_factory=list)


class Classe(str, Enum):
    IDENTICO = "idêntico"
    CENTAVO = "arredondamento (até R$ 0,01)"
    ACUMULADO = "arredondamento acumulado"
    DIVERGENTE = "divergente"
    SEM_PERITA = "sem valor no parecer"


class Comparacao(BaseModel):
    apendice: str
    numero: int | None
    data: date | None
    coluna: str
    perita: Decimal | None
    motor: Decimal | None
    diferenca: Decimal | None
    diferenca_pct: Decimal | None
    classe: Classe
    justificativa: str


class Cenario(BaseModel):
    nome: str
    descricao: str
    erro_absoluto_total: Decimal
    erro_maximo: Decimal
    linhas_identicas: int
    linhas: int
    reproduz: bool


class Inconsistencia(BaseModel):
    apendice: str
    numero: int | None
    descricao: str
