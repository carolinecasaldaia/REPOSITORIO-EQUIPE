"""Cálculo da prestação: Price (mensal/diária), parcelas reforçadas, SAC, Gauss.

Princípio geral (equivalência financeira na data da liberação):

    VF = Σ_regulares  R / F(lib, v_k)  +  Σ_fixas  P_j / F(lib, v_j)

onde F é o fator de acumulação da ``Taxa`` (composto ou simples) segundo a
convenção de tempo declarada. Resolve-se R (valor da parcela regular):

    R = (VF − Σ_fixas P_j / F_j) / Σ_regulares 1 / F_k

Esse único modelo cobre:
- Price mensal clássica (vencimentos a cada mês civil, regime composto);
- capitalização diária (convenção DIAS_BASE_360/365);
- carência / primeiro vencimento fora do padrão;
- parcelas reforçadas, intermediárias ou balão (valores fixos conhecidos);
- juros simples com desconto racional por parcela (regime SIMPLES).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from .auditoria import Memoria, Origem
from .numeros import UM, ZERO, D, PoliticaArredondamento, arredondar, arredondar_prestacao, potencia
from .taxas import Taxa


class ParcelaPrevista(BaseModel):
    model_config = ConfigDict(frozen=True)

    numero: int
    vencimento: date
    valor_fixo: Decimal | None = None
    """Preenchido para parcela reforçada/intermediária/balão de valor conhecido."""


class ResultadoPrestacao(BaseModel):
    model_config = ConfigDict(frozen=True)

    parcela_regular_exata: Decimal
    parcela_regular: Decimal
    soma_fatores_regulares: Decimal
    valor_presente_fixas: Decimal


def coeficiente_price(i: Decimal, n: int) -> Decimal:
    """CF = i / (1 − (1+i)^−n). Para i = 0, CF = 1/n."""
    if n <= 0:
        raise ValueError("número de parcelas deve ser positivo")
    if i == ZERO:
        return UM / D(n)
    return i / (UM - potencia(UM + i, -n))


def parcela_price(valor_financiado: Decimal, i: Decimal, n: int) -> Decimal:
    return valor_financiado * coeficiente_price(i, n)


def parcela_gauss(valor_financiado: Decimal, i: Decimal, n: int) -> Decimal:
    """Método de Gauss (juros lineares): PMT = VF·(1 + i·n) / [n·(1 + i·(n−1)/2)].

    Uso somente se o título judicial determinar expressamente este método.
    """
    if n <= 0:
        raise ValueError("número de parcelas deve ser positivo")
    return valor_financiado * (UM + i * n) / (D(n) * (UM + i * D(n - 1) / D(2)))


def calcular_parcela_regular(
    valor_financiado: Decimal,
    data_liberacao: date,
    parcelas: list[ParcelaPrevista],
    taxa: Taxa,
    politica: PoliticaArredondamento,
    memoria: Memoria | None = None,
    origem: list[Origem | str] | None = None,
    etapa: str = "prestacao",
) -> ResultadoPrestacao:
    if not parcelas:
        raise ValueError("cronograma vazio")
    if any(p.vencimento < data_liberacao for p in parcelas):
        raise ValueError("há vencimento anterior à liberação")

    soma_fatores = ZERO
    vp_fixas = ZERO
    for p in parcelas:
        f = taxa.fator(data_liberacao, p.vencimento)
        if p.valor_fixo is None:
            soma_fatores += UM / f
        else:
            vp_fixas += p.valor_fixo / f
    if soma_fatores == ZERO:
        raise ValueError("não há parcelas regulares a determinar")

    exata = (valor_financiado - vp_fixas) / soma_fatores
    arred = arredondar_prestacao(exata, politica)
    res = ResultadoPrestacao(
        parcela_regular_exata=exata,
        parcela_regular=arred,
        soma_fatores_regulares=soma_fatores,
        valor_presente_fixas=vp_fixas,
    )
    if memoria is not None:
        memoria.registrar(
            etapa,
            "Parcela regular por equivalência na data da liberação",
            "R = (VF − Σ Pj/F(lib,vj)) / Σ 1/F(lib,vk)",
            {
                "VF": valor_financiado,
                "data_liberacao": data_liberacao.isoformat(),
                "n_parcelas": len(parcelas),
                "n_fixas": sum(1 for p in parcelas if p.valor_fixo is not None),
                "taxa": taxa.descricao(),
                "Σ1/F": soma_fatores,
                "VP_fixas": vp_fixas,
                "arredondamento": politica.descricao(),
            },
            {"exata": exata, "arredondada": arred},
            origem,
        )
    return res


def valor_presente(parcelas: list[tuple[date, Decimal]], data_base: date, taxa: Taxa) -> Decimal:
    """Σ valor / F(data_base, vencimento). Útil para conferir contratos."""
    return sum((v / taxa.fator(data_base, d) for d, v in parcelas), ZERO)


def cronograma_sac(valor_financiado: Decimal, i: Decimal, n: int,
                   politica: PoliticaArredondamento) -> list[dict[str, Decimal]]:
    """SAC com períodos mensais iguais: amortização constante, juros sobre saldo."""
    amort = arredondar(valor_financiado / n, politica)
    saldo = valor_financiado
    linhas = []
    for k in range(1, n + 1):
        juros = arredondar(saldo * i, politica)
        a = saldo if k == n else amort
        saldo = saldo - a
        linhas.append({"numero": D(k), "juros": juros, "amortizacao": a,
                       "parcela": juros + a, "saldo": saldo})
    return linhas
