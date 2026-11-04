"""Recálculo do financiamento conforme o título judicial (base do AP02).

O que muda no contrato revisado vem SOMENTE dos parâmetros informados:
- taxa remuneratória revisada (e/ou regime e convenção de capitalização);
- itens excluídos do valor financiado (tarifas, seguros, IOF reflexo...),
  cada um com sua origem no título;
- tratamento das parcelas reforçadas (precisa ser declarado).

Nada é excluído ou alterado por presunção.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .auditoria import Memoria, Origem, TipoRessalva
from .financiamento import ParcelaPrevista, calcular_parcela_regular
from .numeros import UM, ZERO, PoliticaArredondamento, arredondar, arredondar_prestacao
from .taxas import Taxa


class ItemExcluido(BaseModel):
    """Tarifa, seguro ou serviço declarado ilegal/abusivo no título."""

    model_config = ConfigDict(frozen=True)

    descricao: str
    valor: Decimal
    financiado: bool
    """True: integrou o valor financiado (sai da base do AP02).
    False: foi pago à parte (vira indébito com a data do pagamento)."""
    data_pagamento: date | None = None
    origem_titulo: Origem


class TratamentoReforcadas(str, Enum):
    MANTER_VALOR = "manter_valor"
    """Reforçadas mantêm o valor nominal; só as regulares são recalculadas."""
    PROPORCIONAL = "proporcional"
    """Todas as parcelas (regulares e reforçadas) reduzidas na mesma proporção."""


class ParametrosRevisao(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    taxa_revisada: Taxa
    origem_taxa: Origem
    itens_excluidos: list[ItemExcluido] = Field(default_factory=list)
    tratamento_reforcadas: TratamentoReforcadas | None = None


class ResultadoRevisao(BaseModel):
    model_config = ConfigDict(frozen=True)

    valor_financiado_revisado: Decimal
    excluidos_financiados: Decimal
    parcelas_revisadas: dict[int, Decimal]
    """número da parcela -> valor revisado"""
    parcela_regular_revisada: Decimal


def recalcular_contrato(
    valor_financiado_original: Decimal,
    data_liberacao: date,
    parcelas: list[ParcelaPrevista],
    parcela_regular_original: Decimal,
    params: ParametrosRevisao,
    politica: PoliticaArredondamento,
    memoria: Memoria,
) -> ResultadoRevisao:
    tem_reforcadas = any(p.valor_fixo is not None for p in parcelas)
    if tem_reforcadas and params.tratamento_reforcadas is None:
        raise ValueError(
            "contrato com parcelas reforçadas: informe tratamento_reforcadas "
            "(manter_valor ou proporcional) — critério não pode ser presumido"
        )
    for item in params.itens_excluidos:
        if not item.financiado and item.data_pagamento is None:
            raise ValueError(f"item pago à parte sem data de pagamento: {item.descricao}")

    excl_fin = sum((i.valor for i in params.itens_excluidos if i.financiado), ZERO)
    vf_rev = valor_financiado_original - excl_fin
    memoria.registrar(
        "AP02",
        "Valor financiado revisado (exclusão de itens declarados indevidos e financiados)",
        "VF_rev = VF − Σ itens excluídos financiados",
        {"VF": valor_financiado_original,
         "itens": [f"{i.descricao}: {i.valor}" for i in params.itens_excluidos if i.financiado]},
        vf_rev,
        [i.origem_titulo for i in params.itens_excluidos if i.financiado],
    )
    if excl_fin > ZERO:
        memoria.ressalvar(
            TipoRessalva.PENDENCIA,
            "Confirmar se o título determina também a exclusão do IOF incidente sobre os itens "
            "excluídos (IOF reflexo). Só é excluído se informado como item.",
        )

    taxa = params.taxa_revisada
    if params.tratamento_reforcadas is TratamentoReforcadas.PROPORCIONAL:
        def original(p: ParcelaPrevista) -> Decimal:
            return p.valor_fixo if p.valor_fixo is not None else parcela_regular_original

        vp_original = sum((original(p) / taxa.fator(data_liberacao, p.vencimento) for p in parcelas), ZERO)
        k = vf_rev / vp_original
        revisadas = {p.numero: arredondar_prestacao(original(p) * k, politica) for p in parcelas}
        regular = arredondar_prestacao(parcela_regular_original * k, politica)
        memoria.registrar(
            "AP02", "Parcelas revisadas — redução proporcional (inclui reforçadas)",
            "k = VF_rev / Σ P_original/F(lib,v); P_rev = P_original × k",
            {"VF_rev": vf_rev, "Σ P_original/F": vp_original, "taxa": taxa.descricao(),
             "arredondamento": politica.descricao()},
            {"k": k, "parcela_regular_revisada": regular},
            [params.origem_taxa],
        )
        if k > UM:
            memoria.ressalvar(TipoRessalva.ALERTA,
                              "AP02: parcelas revisadas MAIORES que as originais (k > 1). Conferir parâmetros.")
    else:
        r = calcular_parcela_regular(vf_rev, data_liberacao, parcelas, taxa, politica, memoria,
                                     [params.origem_taxa], etapa="AP02")
        regular = r.parcela_regular
        revisadas = {p.numero: (p.valor_fixo if p.valor_fixo is not None else regular) for p in parcelas}
        if regular > parcela_regular_original:
            memoria.ressalvar(TipoRessalva.ALERTA,
                              "AP02: parcela revisada MAIOR que a original. Conferir parâmetros.")

    return ResultadoRevisao(
        valor_financiado_revisado=vf_rev,
        excluidos_financiados=excl_fin,
        parcelas_revisadas=revisadas,
        parcela_regular_revisada=regular,
    )
