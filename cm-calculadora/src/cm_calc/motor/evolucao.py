"""Evolução do saldo devedor (conta gráfica) — base dos apêndices AP01 e AP02.

Modelo de saldo em duas contas:
- ``capital``         : principal ainda não amortizado;
- ``juros_pendentes`` : juros vencidos e não pagos.

Entre dois eventos, os juros do intervalo são:
- regime COMPOSTO: (capital + juros_pendentes) × (F − 1)  → juros sobre juros;
- regime SIMPLES : capital × (F − 1)                      → sem capitalização.

Cada pagamento é imputado na ordem declarada (``OrdemImputacao``). Não há
ordem padrão: o caso precisa informar (contrato, título ou decisão da advogada).
Pagamento acima do saldo gera ``excedente`` — candidato a restituição, que
NÃO rende a taxa do contrato; sua atualização segue critérios próprios.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict

from .auditoria import Memoria, Origem, TipoRessalva
from .financiamento import ParcelaPrevista
from .numeros import UM, ZERO, PoliticaArredondamento, arredondar, arredondar_se_parcela
from .taxas import Regime, Taxa


class OrdemImputacao(str, Enum):
    JUROS_PRIMEIRO = "juros_primeiro"
    CAPITAL_PRIMEIRO = "capital_primeiro"


class Evento(BaseModel):
    model_config = ConfigDict(frozen=True)

    data: date
    valor: Decimal
    descricao: str = "pagamento"
    numero_parcela: int | None = None


class LinhaEvolucao(BaseModel):
    model_config = ConfigDict(frozen=True)

    data: date
    descricao: str
    numero_parcela: int | None
    fator: Decimal
    saldo_anterior: Decimal
    juros_periodo: Decimal
    pagamento: Decimal
    juros_pagos: Decimal
    amortizacao: Decimal
    excedente: Decimal
    capital: Decimal
    juros_pendentes: Decimal

    @property
    def saldo(self) -> Decimal:
        return self.capital + self.juros_pendentes


class ResultadoEvolucao(BaseModel):
    model_config = ConfigDict(frozen=True)

    linhas: list[LinhaEvolucao]
    saldo_final: Decimal
    total_pago: Decimal
    total_juros: Decimal
    total_amortizado: Decimal
    total_excedente: Decimal

    def conciliacao(self, valor_inicial: Decimal) -> dict[str, Decimal]:
        """Identidades que precisam fechar (diferença zero):
        1) pago = juros pagos + amortização + excedente
        2) inicial + juros − juros pagos − amortização = saldo final
        """
        juros_pagos = sum((l.juros_pagos for l in self.linhas), ZERO)
        return {
            "pagamentos": self.total_pago - (juros_pagos + self.total_amortizado + self.total_excedente),
            "saldo": valor_inicial + self.total_juros - juros_pagos - self.total_amortizado - self.saldo_final,
        }


def evoluir_saldo(
    valor_inicial: Decimal,
    data_inicio: date,
    eventos: list[Evento],
    taxa: Taxa,
    politica: PoliticaArredondamento,
    ordem: OrdemImputacao,
    memoria: Memoria | None = None,
    etapa: str = "evolucao",
    origem: list[Origem | str] | None = None,
    data_final: date | None = None,
) -> ResultadoEvolucao:
    eventos = sorted(eventos, key=lambda e: e.data)
    if eventos and eventos[0].data < data_inicio:
        raise ValueError("evento anterior à data inicial")

    capital, pendentes = valor_inicial, ZERO
    ultima = data_inicio
    linhas: list[LinhaEvolucao] = []

    def acumular(ate: date) -> tuple[Decimal, Decimal]:
        f = taxa.fator(ultima, ate)
        base = capital + pendentes if taxa.regime is Regime.COMPOSTO else capital
        return f, arredondar_se_parcela(base * (f - UM), politica)

    for ev in eventos:
        f, juros = acumular(ev.data)
        saldo_ant = capital + pendentes
        pendentes += juros
        restante = ev.valor
        j_pagos = amort = ZERO
        for destino in _ordem(ordem):
            if destino == "juros":
                j_pagos = min(restante, pendentes)
                pendentes -= j_pagos
                restante -= j_pagos
            else:
                amort = min(restante, capital)
                capital -= amort
                restante -= amort
        excedente = restante
        if memoria is not None and ev.valor < juros and taxa.regime is Regime.COMPOSTO:
            memoria.ressalvar(
                TipoRessalva.ALERTA,
                f"{etapa}: pagamento de {ev.data:%d/%m/%Y} menor que os juros do período "
                "(amortização negativa — juros não pagos passam a integrar a base).",
            )
        linhas.append(LinhaEvolucao(
            data=ev.data, descricao=ev.descricao, numero_parcela=ev.numero_parcela,
            fator=f, saldo_anterior=saldo_ant, juros_periodo=juros, pagamento=ev.valor,
            juros_pagos=j_pagos, amortizacao=amort, excedente=excedente,
            capital=capital, juros_pendentes=pendentes,
        ))
        ultima = ev.data

    if data_final is not None and data_final > ultima:
        f, juros = acumular(data_final)
        saldo_ant = capital + pendentes
        pendentes += juros
        linhas.append(LinhaEvolucao(
            data=data_final, descricao="posição na data-base", numero_parcela=None,
            fator=f, saldo_anterior=saldo_ant, juros_periodo=juros, pagamento=ZERO,
            juros_pagos=ZERO, amortizacao=ZERO, excedente=ZERO,
            capital=capital, juros_pendentes=pendentes,
        ))

    res = ResultadoEvolucao(
        linhas=linhas,
        saldo_final=capital + pendentes,
        total_pago=sum((l.pagamento for l in linhas), ZERO),
        total_juros=sum((l.juros_periodo for l in linhas), ZERO),
        total_amortizado=sum((l.amortizacao for l in linhas), ZERO),
        total_excedente=sum((l.excedente for l in linhas), ZERO),
    )
    if memoria is not None:
        memoria.registrar(
            etapa,
            "Evolução do saldo devedor (conta gráfica)",
            "juros = base × (F(intervalo) − 1); base = capital + juros pendentes (composto) "
            "ou capital (simples); pagamento imputado na ordem declarada",
            {
                "valor_inicial": valor_inicial,
                "data_inicio": data_inicio.isoformat(),
                "eventos": len(eventos),
                "taxa": taxa.descricao(),
                "ordem_imputacao": ordem.value,
                "arredondamento": politica.descricao(),
            },
            {
                "saldo_final": res.saldo_final,
                "total_pago": res.total_pago,
                "total_juros": res.total_juros,
                "total_amortizado": res.total_amortizado,
                "total_excedente": res.total_excedente,
            },
            origem,
        )
        if taxa.regime is Regime.SIMPLES and res.linhas and res.linhas[-1].juros_pendentes > ZERO:
            memoria.ressalvar(
                TipoRessalva.PREMISSA,
                f"{etapa}: regime simples — juros vencidos e não pagos ficam em conta separada, "
                "sem incidência de novos juros.",
            )
        if res.total_excedente > ZERO:
            memoria.ressalvar(
                TipoRessalva.PREMISSA,
                f"{etapa}: pagamentos excedentes ao saldo ({res.total_excedente}) foram segregados "
                "e não rendem a taxa contratual; atualização conforme critérios do título.",
            )
    return res


def cronograma_como_eventos(parcelas: list[ParcelaPrevista], valor_regular: Decimal) -> list[Evento]:
    return [
        Evento(data=p.vencimento, valor=p.valor_fixo if p.valor_fixo is not None else valor_regular,
               descricao="parcela prevista", numero_parcela=p.numero)
        for p in parcelas
    ]


def tabela_contratual(
    valor_financiado: Decimal,
    data_liberacao: date,
    parcelas: list[ParcelaPrevista],
    valor_regular: Decimal,
    taxa: Taxa,
    politica: PoliticaArredondamento,
    memoria: Memoria | None = None,
    etapa: str = "tabela_contratual",
    origem: list[Origem | str] | None = None,
) -> ResultadoEvolucao:
    """Tabela de amortização teórica (todas as parcelas pagas no vencimento).

    O resíduo final (efeito do arredondamento da parcela) NÃO é absorvido na
    última parcela: é exibido como divergência para que a equipe decida.
    """
    res = evoluir_saldo(
        valor_financiado, data_liberacao, cronograma_como_eventos(parcelas, valor_regular),
        taxa, politica, OrdemImputacao.JUROS_PRIMEIRO, memoria, etapa, origem,
    )
    residuo = res.saldo_final - res.total_excedente
    if memoria is not None and arredondar(residuo, politica) != ZERO:
        memoria.ressalvar(
            TipoRessalva.DIVERGENCIA,
            f"{etapa}: resíduo de {residuo} após a última parcela (arredondamento da prestação). "
            "Não absorvido automaticamente.",
        )
    return res


def _ordem(ordem: OrdemImputacao) -> tuple[str, str]:
    return ("juros", "capital") if ordem is OrdemImputacao.JUROS_PRIMEIRO else ("capital", "juros")
