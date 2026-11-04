"""Composição do financiamento, exclusão de cobranças e CET.

Composição
----------
    valor financiado = valor liberado + Σ itens financiados (IOF, tarifas, seguros...)
    itens à vista    = pagos pelo consumidor fora do financiamento (com data)

Exclusões determinadas pelo título
----------------------------------
Cada item excluído tem UM destino, nunca dois:
- financiado -> sai do valor financiado do AP02 (devolução ocorre pela
  redução das parcelas, inclusive dos juros que incidiam sobre ele);
- à vista    -> indébito avulso na data do pagamento.
O ``ControleUtilizacao`` recusa a segunda utilização do mesmo item.

CET
---
Metodologia de referência: Resolução CMN nº 3.517/2007 (CONFERIR NO TEXTO
OFICIAL antes de uso em peça). Taxa anual que satisfaz:

    FC0 = Σ FCj / (1 + CET)^((dj − d0) / 365)

FC0 = valor liberado ao cliente líquido das despesas pagas à vista no ato;
FCj = pagamentos do cliente (parcelas e demais saídas posteriores).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from .auditoria import Memoria, Origem, TipoRessalva
from .controle import ControleUtilizacao
from .numeros import UM, ZERO, D, potencia
from .revisao import ItemExcluido


class TipoItem(str, Enum):
    IOF = "IOF"
    TARIFA = "tarifa"
    SEGURO = "seguro"
    SERVICO = "serviço"
    OUTRO = "outro"


class FormaPagamento(str, Enum):
    FINANCIADO = "financiado"
    A_VISTA = "à vista"


class ItemCusto(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    tipo: TipoItem
    descricao: str
    valor: Decimal
    forma: FormaPagamento
    data_pagamento: date | None = None
    origem: Origem

    @model_validator(mode="after")
    def _data(self):
        if self.valor < 0:
            raise ValueError(f"{self.id}: valor negativo")
        if self.forma is FormaPagamento.A_VISTA and self.data_pagamento is None:
            raise ValueError(f"{self.id}: item pago à vista exige data de pagamento")
        return self


class Composicao(BaseModel):
    model_config = ConfigDict(frozen=True)

    data_liberacao: date
    valor_liberado: Decimal
    """Crédito efetivamente entregue (ao consumidor ou ao vendedor por conta dele)."""
    itens: list[ItemCusto]
    valor_financiado_declarado: Decimal | None = None
    cet_anual_declarado: Decimal | None = None
    origem: Origem

    @model_validator(mode="after")
    def _ids_unicos(self):
        ids = [i.id for i in self.itens]
        if len(ids) != len(set(ids)):
            raise ValueError("identificadores de itens repetidos na composição")
        return self

    @property
    def total_financiado_itens(self) -> Decimal:
        return sum((i.valor for i in self.itens if i.forma is FormaPagamento.FINANCIADO), ZERO)

    @property
    def total_a_vista(self) -> Decimal:
        return sum((i.valor for i in self.itens if i.forma is FormaPagamento.A_VISTA), ZERO)

    @property
    def valor_financiado(self) -> Decimal:
        return self.valor_liberado + self.total_financiado_itens

    def item(self, id_item: str) -> ItemCusto:
        for i in self.itens:
            if i.id == id_item:
                return i
        raise KeyError(f"item '{id_item}' não consta da composição do contrato")

    def conferir(self, memoria: Memoria) -> Decimal:
        """Registra a composição e acusa divergência com o valor declarado no contrato."""
        por_tipo: dict[str, Decimal] = {}
        for i in self.itens:
            chave = f"{i.tipo.value} ({i.forma.value})"
            por_tipo[chave] = por_tipo.get(chave, ZERO) + i.valor
        memoria.registrar(
            "composicao", "Composição do financiamento",
            "VF = valor liberado + Σ itens financiados; itens à vista em separado",
            {"valor_liberado": self.valor_liberado, "por_tipo": por_tipo},
            {"valor_financiado": self.valor_financiado, "total_a_vista": self.total_a_vista},
            [self.origem] + [i.origem for i in self.itens],
            self.data_liberacao,
        )
        if self.valor_financiado_declarado is not None:
            dif = self.valor_financiado_declarado - self.valor_financiado
            if dif != ZERO:
                memoria.ressalvar(
                    TipoRessalva.DIVERGENCIA,
                    f"composicao: valor financiado declarado ({self.valor_financiado_declarado}) difere da soma "
                    f"dos componentes ({self.valor_financiado}) em {dif}. Há componente não identificado ou erro "
                    "de extração.",
                )
        return self.valor_financiado


class Exclusao(BaseModel):
    """Comando do título que declara uma cobrança indevida."""

    model_config = ConfigDict(frozen=True)

    id_item: str
    origem_titulo: Origem


class ResultadoExclusoes(BaseModel):
    model_config = ConfigDict(frozen=True)

    valor_financiado_original: Decimal
    valor_financiado_revisado: Decimal
    excluidos_financiados: list[ItemExcluido]
    indebitos_a_vista: list[ItemExcluido]


def aplicar_exclusoes(
    composicao: Composicao,
    exclusoes: list[Exclusao],
    controle: ControleUtilizacao,
    memoria: Memoria,
) -> ResultadoExclusoes:
    financiados: list[ItemExcluido] = []
    a_vista: list[ItemExcluido] = []
    for ex in exclusoes:
        item = composicao.item(ex.id_item)
        if item.forma is FormaPagamento.FINANCIADO:
            controle.usar(item.id, "exclusão do valor financiado (AP02)")
            financiados.append(ItemExcluido(descricao=item.descricao, valor=item.valor, financiado=True,
                                            origem_titulo=ex.origem_titulo))
        else:
            controle.usar(item.id, "indébito de item pago à vista (AP03)")
            a_vista.append(ItemExcluido(descricao=item.descricao, valor=item.valor, financiado=False,
                                        data_pagamento=item.data_pagamento, origem_titulo=ex.origem_titulo))

    excl = sum((i.valor for i in financiados), ZERO)
    res = ResultadoExclusoes(
        valor_financiado_original=composicao.valor_financiado,
        valor_financiado_revisado=composicao.valor_financiado - excl,
        excluidos_financiados=financiados,
        indebitos_a_vista=a_vista,
    )
    memoria.registrar(
        "composicao", "Exclusão das cobranças declaradas indevidas no título",
        "VF_rev = VF − Σ excluídos financiados; excluídos à vista -> indébito avulso",
        {"financiados": [f"{i.descricao}: {i.valor}" for i in financiados],
         "a_vista": [f"{i.descricao}: {i.valor} em {i.data_pagamento}" for i in a_vista]},
        {"VF_original": res.valor_financiado_original, "VF_revisado": res.valor_financiado_revisado},
        [e.origem_titulo for e in exclusoes],
    )
    if financiados:
        memoria.ressalvar(
            TipoRessalva.PREMISSA,
            "Itens financiados excluídos são devolvidos pela redução das parcelas no AP02 (inclusive os juros "
            "que incidiam sobre eles) e por isso NÃO são lançados de novo como indébito avulso.",
        )
    ids_excluidos = {e.id_item for e in exclusoes}
    iof_mantido = [i for i in composicao.itens if i.tipo is TipoItem.IOF and i.id not in ids_excluidos]
    if financiados and iof_mantido:
        memoria.ressalvar(
            TipoRessalva.PENDENCIA,
            "IOF mantido integralmente, embora parte da base tributável tenha sido excluída. Confirmar se o título "
            "determina a exclusão do IOF reflexo; se sim, informar o valor como item próprio.",
        )
    return res


# --- CET --------------------------------------------------------------------------


class ResultadoCET(BaseModel):
    model_config = ConfigDict(frozen=True)

    fc0: Decimal
    anual: Decimal
    mensal_equivalente: Decimal
    residuo: Decimal


def _vpl(taxa: Decimal, d0: date, fluxos: list[tuple[date, Decimal]]) -> Decimal:
    return sum((v / potencia(UM + taxa, D((d - d0).days) / D(365)) for d, v in fluxos), ZERO)


def fluxo_cet(composicao: Composicao, parcelas: list[tuple[date, Decimal]]) -> tuple[Decimal, list[tuple[date, Decimal]]]:
    """FC0 e fluxos posteriores a partir da composição e do cronograma."""
    fc0 = composicao.valor_liberado
    saidas = list(parcelas)
    for i in composicao.itens:
        if i.forma is FormaPagamento.A_VISTA:
            if i.data_pagamento <= composicao.data_liberacao:
                fc0 -= i.valor
            else:
                saidas.append((i.data_pagamento, i.valor))
    return fc0, sorted(saidas)


def calcular_cet(
    data_liberacao: date,
    fc0: Decimal,
    fluxos: list[tuple[date, Decimal]],
    memoria: Memoria | None = None,
    etapa: str = "CET",
    cet_declarado: Decimal | None = None,
    tolerancia_declarado: Decimal = D("0.0001"),
    origem: list[Origem | str] | None = None,
) -> ResultadoCET:
    """Resolve o CET anual por bisseção (função estritamente decrescente na taxa)."""
    if fc0 <= 0:
        raise ValueError("FC0 deve ser positivo (valor liberado líquido)")
    if not fluxos or any(v < 0 for _, v in fluxos) or any(d < data_liberacao for d, _ in fluxos):
        raise ValueError("fluxos inválidos para o CET")
    if sum((v for _, v in fluxos), ZERO) < fc0:
        raise ValueError("pagamentos totais menores que o valor liberado: CET negativo, conferir dados")

    lo, hi = D("-0.99"), D(1)
    while _vpl(hi, data_liberacao, fluxos) > fc0:
        hi *= 2
        if hi > D(10000):
            raise ValueError("CET acima de 1.000.000% a.a.: conferir dados")
    for _ in range(200):
        meio = (lo + hi) / 2
        if _vpl(meio, data_liberacao, fluxos) > fc0:
            lo = meio
        else:
            hi = meio
        if hi - lo < D("1e-24"):
            break
    anual = (lo + hi) / 2
    res = ResultadoCET(
        fc0=fc0, anual=anual,
        mensal_equivalente=potencia(UM + anual, D(1) / D(12)) - UM,
        residuo=_vpl(anual, data_liberacao, fluxos) - fc0,
    )
    if memoria is not None:
        memoria.registrar(
            etapa, "Custo Efetivo Total (taxa anual, dias corridos/365)",
            "FC0 = Σ FCj / (1+CET)^((dj−d0)/365) — Res. CMN 3.517/2007 (conferir texto oficial)",
            {"FC0": fc0, "n_fluxos": len(fluxos), "total_pago": sum((v for _, v in fluxos), ZERO)},
            {"CET_anual": anual, "CET_mensal_equivalente": res.mensal_equivalente, "residuo": res.residuo},
            origem,
        )
        if cet_declarado is not None and abs(anual - cet_declarado) > tolerancia_declarado:
            memoria.ressalvar(
                TipoRessalva.DIVERGENCIA,
                f"{etapa}: CET calculado ({(anual * 100).quantize(D('0.01'))}% a.a.) difere do declarado no "
                f"contrato ({(cet_declarado * 100).quantize(D('0.01'))}% a.a.). Verificar fluxos e componentes.",
            )
    return res
