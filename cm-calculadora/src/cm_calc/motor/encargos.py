"""Encargos moratórios e efeitos da descaracterização da mora.

Este módulo calcula APENAS efeitos financeiros sobre encargos:
- encargos devidos por atraso conforme os parâmetros (contrato ou título);
- afastamento de componentes no período em que o título descaracterizou a mora.

Ele NÃO gera, por si, restituição do veículo, perdas e danos, multa ou
devolução integral de parcelas. Essas verbas só existem se o título as
determinar e são tratadas em ``verbas.py``, com citação obrigatória.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from .auditoria import Memoria, Origem, TipoRessalva
from .datas import dias_corridos, meses_civis_e_dias
from .numeros import UM, ZERO, D, PoliticaArredondamento, arredondar, potencia


class Componente(str, Enum):
    MULTA = "multa"
    JUROS_MORA = "juros_mora"
    JUROS_REMUNERATORIOS_MORA = "juros_remuneratorios_mora"
    COMISSAO_PERMANENCIA = "comissao_permanencia"


class ContagemAtraso(str, Enum):
    DIAS_30 = "dias_30"           # dias de atraso / 30
    MESES_CIVIS = "meses_civis"   # meses completos + dias/30


class ParametrosEncargos(BaseModel):
    """Encargos de inadimplência como pactuados (ou como fixados no título)."""

    model_config = ConfigDict(frozen=True)

    multa: Decimal | None = None                       # fração, ex. 0.02
    juros_mora_mensal: Decimal | None = None           # fração ao mês, juros simples
    juros_remuneratorios_mora_mensal: Decimal | None = None
    remuneratorios_compostos: bool | None = None
    comissao_permanencia_mensal: Decimal | None = None
    contagem: ContagemAtraso
    origem: Origem

    @model_validator(mode="after")
    def _regime_remuneratorios(self):
        if self.juros_remuneratorios_mora_mensal is not None and self.remuneratorios_compostos is None:
            raise ValueError("informe se os juros remuneratórios na mora são compostos ou simples")
        return self


class Descaracterizacao(BaseModel):
    """Comando do título que descaracteriza a mora.

    ``componentes_afastados`` lista exatamente o que o título afastou; o que
    não estiver listado continua devido (se pactuado).
    ``ate``: até quando a mora fica descaracterizada (None = sem termo final
    no título; gera pendência para confirmação).
    """

    model_config = ConfigDict(frozen=True)

    componentes_afastados: frozenset[Componente]
    desde: date | None = None
    ate: date | None = None
    origem_titulo: Origem

    def abrange(self, vencimento: date) -> bool:
        if self.desde and vencimento < self.desde:
            return False
        if self.ate and vencimento > self.ate:
            return False
        return True


def _tempo_atraso(venc: date, pag: date, contagem: ContagemAtraso) -> Decimal:
    if contagem is ContagemAtraso.DIAS_30:
        return D(dias_corridos(venc, pag)) / D(30)
    m, d = meses_civis_e_dias(venc, pag)
    return D(m) + D(d) / D(30)


def calcular_encargos(
    valor_parcela: Decimal,
    vencimento: date,
    pagamento: date,
    params: ParametrosEncargos,
    politica: PoliticaArredondamento,
    descaracterizacao: Descaracterizacao | None = None,
    memoria: Memoria | None = None,
    etapa: str = "encargos",
) -> dict[Componente, Decimal]:
    """Encargos devidos por atraso de uma parcela, já aplicada a descaracterização."""
    if pagamento <= vencimento:
        return {}
    t = _tempo_atraso(vencimento, pagamento, params.contagem)
    brutos: dict[Componente, Decimal] = {}
    if params.multa is not None:
        brutos[Componente.MULTA] = valor_parcela * params.multa
    if params.juros_mora_mensal is not None:
        brutos[Componente.JUROS_MORA] = valor_parcela * params.juros_mora_mensal * t
    if params.juros_remuneratorios_mora_mensal is not None:
        i = params.juros_remuneratorios_mora_mensal
        fator = potencia(UM + i, t) if params.remuneratorios_compostos else UM + i * t
        brutos[Componente.JUROS_REMUNERATORIOS_MORA] = valor_parcela * (fator - UM)
    if params.comissao_permanencia_mensal is not None:
        brutos[Componente.COMISSAO_PERMANENCIA] = valor_parcela * params.comissao_permanencia_mensal * t
        if memoria is not None and (params.multa or params.juros_mora_mensal or params.juros_remuneratorios_mora_mensal):
            memoria.ressalvar(
                TipoRessalva.ALERTA,
                f"{etapa}: comissão de permanência parametrizada junto com outros encargos moratórios. "
                "Verificar a cumulação à luz do título.",
            )

    afastar = (descaracterizacao.componentes_afastados
               if descaracterizacao and descaracterizacao.abrange(vencimento) else frozenset())
    devidos = {c: (ZERO if c in afastar else arredondar(v, politica)) for c, v in brutos.items()}

    if memoria is not None:
        memoria.registrar(
            etapa,
            f"Encargos de atraso — parcela vencida em {vencimento:%d/%m/%Y}, paga em {pagamento:%d/%m/%Y}",
            "multa = P×m; mora = P×j×t; remuneratórios = P×((1+i)^t − 1) ou P×i×t; "
            "componentes afastados pelo título = 0",
            {"parcela": valor_parcela, "t_meses": t, "afastados": sorted(c.value for c in afastar)},
            {c.value: v for c, v in devidos.items()},
            [params.origem] + ([descaracterizacao.origem_titulo] if afastar else []),
        )
    return devidos


def ressalvas_descaracterizacao(desc: Descaracterizacao, memoria: Memoria) -> None:
    memoria.ressalvar(
        TipoRessalva.PREMISSA,
        "Descaracterização da mora aplicada apenas aos encargos listados no título "
        f"({', '.join(sorted(c.value for c in desc.componentes_afastados))}). "
        "Restituição do veículo, perdas e danos, multas e devolução de parcelas NÃO decorrem "
        "automaticamente e só são calculadas se constarem expressamente do título.",
    )
    if desc.ate is None:
        memoria.ressalvar(
            TipoRessalva.PENDENCIA,
            "Título sem termo final da descaracterização da mora: confirmar com a advogada "
            "responsável se abrange todo o período.",
        )
