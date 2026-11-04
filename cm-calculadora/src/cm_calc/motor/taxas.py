"""Taxas de juros: equivalência, proporcionalidade e fator de capitalização.

Convenções (sempre declaradas pelo caso, nunca presumidas):

- Regime COMPOSTO: taxas equivalentes, ``(1+ia) = (1+im)^12``.
- Regime SIMPLES (linear): taxas proporcionais, ``ia = 12·im``.
- ``ConvencaoTempo`` define como um intervalo entre duas datas vira expoente:
    * MESES_30       : dias corridos / 30  (mês comercial)
    * MESES_CIVIS    : meses de calendário completos + dias restantes / 30
    * DIAS_BASE_360  : dias corridos; taxa diária a partir da anual com ano de 360 dias
    * DIAS_BASE_365  : idem, ano de 365 dias
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from .datas import dias_corridos, meses_civis_e_dias
from .numeros import UM, D, potencia


class Regime(str, Enum):
    COMPOSTO = "composto"
    SIMPLES = "simples"


class ConvencaoTempo(str, Enum):
    MESES_30 = "meses_30"
    MESES_CIVIS = "meses_civis"
    DIAS_BASE_360 = "dias_base_360"
    DIAS_BASE_365 = "dias_base_365"


def mensal_para_anual(im: Decimal, regime: Regime) -> Decimal:
    if regime is Regime.COMPOSTO:
        return potencia(UM + im, 12) - UM
    return im * 12


def anual_para_mensal(ia: Decimal, regime: Regime) -> Decimal:
    if regime is Regime.COMPOSTO:
        return potencia(UM + ia, D(1) / D(12)) - UM
    return ia / 12


def anual_para_diaria(ia: Decimal, base_dias: int, regime: Regime) -> Decimal:
    if regime is Regime.COMPOSTO:
        return potencia(UM + ia, D(1) / D(base_dias)) - UM
    return ia / base_dias


def mensal_para_diaria(im: Decimal, regime: Regime) -> Decimal:
    """Taxa diária a partir da mensal com mês de 30 dias."""
    if regime is Regime.COMPOSTO:
        return potencia(UM + im, D(1) / D(30)) - UM
    return im / 30


def expoente_tempo(inicio: date, fim: date, convencao: ConvencaoTempo) -> Decimal:
    """Duração do intervalo na unidade da taxa usada pela convenção.

    MESES_* -> em meses (taxa mensal). DIAS_* -> em dias (taxa diária).
    """
    if fim < inicio:
        raise ValueError(f"intervalo invertido: {inicio} > {fim}")
    if convencao is ConvencaoTempo.MESES_30:
        return D(dias_corridos(inicio, fim)) / D(30)
    if convencao is ConvencaoTempo.MESES_CIVIS:
        meses, dias = meses_civis_e_dias(inicio, fim)
        return D(meses) + D(dias) / D(30)
    return D(dias_corridos(inicio, fim))


class Taxa:
    """Taxa contratual ou judicial já na unidade compatível com a convenção."""

    def __init__(self, mensal: Decimal, regime: Regime, convencao: ConvencaoTempo,
                 anual: Decimal | None = None):
        self.mensal = mensal
        self.regime = regime
        self.convencao = convencao
        self.anual = anual if anual is not None else mensal_para_anual(mensal, regime)

    @property
    def por_unidade(self) -> Decimal:
        """Taxa na unidade de ``expoente_tempo`` (mensal ou diária)."""
        if self.convencao in (ConvencaoTempo.MESES_30, ConvencaoTempo.MESES_CIVIS):
            return self.mensal
        base = 360 if self.convencao is ConvencaoTempo.DIAS_BASE_360 else 365
        return anual_para_diaria(self.anual, base, self.regime)

    def fator(self, inicio: date, fim: date) -> Decimal:
        """Fator de acumulação do intervalo: composto (1+i)^t; simples 1+i·t."""
        t = expoente_tempo(inicio, fim, self.convencao)
        i = self.por_unidade
        if self.regime is Regime.COMPOSTO:
            return potencia(UM + i, t)
        return UM + i * t

    def descricao(self) -> str:
        return (f"{(self.mensal * 100).normalize()}% a.m. / {(self.anual * 100).quantize(D('0.0001'))}% a.a., "
                f"regime {self.regime.value}, convenção {self.convencao.value}")
