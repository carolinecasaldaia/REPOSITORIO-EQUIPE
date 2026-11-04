"""Venda do veículo, saldo remanescente, multa do DL 911/1969 e perdas e danos (FIPE).

Nada aqui decorre da descaracterização da mora. Cada cálculo exige comando
expresso do título, com o trecho literal (``Origem.trecho``).

Saldo após a venda (todas as posições na data da alienação):

    resultado = saldo devedor revisado
              + despesas comprovadas (se o título mandar abatê-las)
              − valor da venda
              − créditos do consumidor (se o título mandar compensá-los aqui)

    resultado > 0 -> saldo remanescente a cargo do consumidor
    resultado < 0 -> valor a restituir ao consumidor

Multa do art. 3º, §6º, do DL 911/1969 (redação da Lei 10.931/2004 — CONFERIR
NO TEXTO OFICIAL): improcedência da busca e apreensão + bem já alienado ->
multa de 50% do valor originalmente financiado, atualizado. O §7º prevê que a
multa não exclui perdas e danos. O motor exige o percentual e a base vindos
do título e acusa divergência em relação ao texto legal; não os presume.

Perdas e danos pela FIPE: valor de referência informado manualmente, com
mês de referência e fonte (sem consulta automática), menos as deduções que
o título determinar.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, model_validator

from .atualizacao import ParametrosAtualizacao, SerieMensal, atualizar
from .auditoria import Memoria, Origem, TipoRessalva
from .compensacao import Posicao
from .controle import ControleUtilizacao
from .evolucao import Evento, OrdemImputacao, evoluir_saldo
from .numeros import ZERO, D, PoliticaArredondamento, arredondar
from .taxas import Taxa

PERCENTUAL_DL911 = D("0.50")


def _exigir_trecho(origem: Origem, verba: str) -> None:
    if not (origem.trecho and origem.trecho.strip()):
        raise ValueError(f"{verba}: sem trecho do título que a determine — não pode ser calculada")


# --- Venda e saldo remanescente -----------------------------------------------------

class VendaVeiculo(BaseModel):
    model_config = ConfigDict(frozen=True)

    data_alienacao: date
    valor_venda: Decimal
    comprovado: bool
    origem: Origem
    valor_fipe_referencia: Decimal | None = None
    origem_fipe: Origem | None = None

    @model_validator(mode="after")
    def _fipe(self):
        if self.valor_venda < 0:
            raise ValueError("valor de venda negativo")
        if self.valor_fipe_referencia is not None and self.origem_fipe is None:
            raise ValueError("valor FIPE exige origem (tabela, código e mês de referência)")
        return self


class Despesa(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    descricao: str
    valor: Decimal
    data: date
    comprovada: bool
    origem: Origem


class ComandoVenda(BaseModel):
    """O que o título determina para a apuração pós-venda."""

    model_config = ConfigDict(frozen=True)

    abater_despesas_comprovadas: bool
    compensar_creditos_consumidor: bool
    origem_titulo: Origem


class ResultadoVenda(BaseModel):
    model_config = ConfigDict(frozen=True)

    data_alienacao: date
    saldo_devedor_revisado: Decimal
    despesas_consideradas: Decimal
    despesas_desconsideradas: Decimal
    valor_venda: Decimal
    creditos_consumidor: Decimal
    saldo_remanescente_consumidor: Decimal
    """Quanto o consumidor ainda deve após a venda."""
    valor_a_restituir_consumidor: Decimal
    """Sobra da venda (e créditos) a favor do consumidor."""


def posicao_saldo_revisado(
    valor_financiado_revisado: Decimal,
    data_liberacao: date,
    pagamentos: list[Evento],
    taxa_revisada: Taxa,
    politica: PoliticaArredondamento,
    ordem: OrdemImputacao,
    data_alienacao: date,
    memoria: Memoria,
    origem: list[Origem | str],
) -> Posicao:
    """Saldo devedor revisado na data da alienação, considerados os pagamentos realizados."""
    if any(p.data > data_alienacao for p in pagamentos):
        raise ValueError("há pagamento posterior à alienação: tratar separadamente")
    r = evoluir_saldo(valor_financiado_revisado, data_liberacao, pagamentos, taxa_revisada, politica, ordem,
                      memoria, "saldo_na_alienacao", origem, data_alienacao)
    memoria.ressalvar(
        TipoRessalva.PENDENCIA,
        "saldo_na_alienacao: após o inadimplemento foi aplicada a taxa revisada até a data da venda. "
        "Confirmar com a advogada se o título determina outro critério para esse período.",
    )
    return Posicao(descricao="Saldo devedor revisado na alienação", valor=arredondar(r.saldo_final, politica),
                   data_base=data_alienacao, id="saldo_devedor_revisado")


def apurar_saldo_pos_venda(
    saldo_devedor: Posicao,
    venda: VendaVeiculo,
    despesas: list[Despesa],
    creditos: list[Posicao],
    comando: ComandoVenda,
    politica: PoliticaArredondamento,
    memoria: Memoria,
    controle: ControleUtilizacao | None = None,
) -> ResultadoVenda:
    d = venda.data_alienacao
    for p in [saldo_devedor] + creditos:
        if p.data_base != d:
            raise ValueError(
                f"'{p.descricao}' posicionado em {p.data_base:%d/%m/%Y}; a apuração exige a data da "
                f"alienação ({d:%d/%m/%Y}). Atualize antes."
            )

    if controle is not None:
        controle.usar(saldo_devedor.id, "saldo devedor apurado na venda do veículo")

    consideradas = desconsideradas = ZERO
    if comando.abater_despesas_comprovadas:
        for desp in despesas:
            if desp.comprovada:
                if controle is not None:
                    controle.usar(desp.id, "despesa abatida na apuração da venda")
                consideradas += desp.valor
            else:
                desconsideradas += desp.valor
                memoria.ressalvar(TipoRessalva.PENDENCIA,
                                  f"venda: despesa '{desp.descricao}' ({desp.valor}) sem comprovação — não abatida.")
    elif despesas:
        desconsideradas = sum((x.valor for x in despesas), ZERO)
        memoria.ressalvar(TipoRessalva.PREMISSA,
                          "venda: o título não autoriza abater despesas da venda; nenhuma foi considerada.")

    creditos_total = ZERO
    if comando.compensar_creditos_consumidor:
        for c in creditos:
            if controle is not None:
                controle.usar(c.id, "crédito compensado na apuração da venda")
            creditos_total += c.valor
    elif creditos:
        memoria.ressalvar(TipoRessalva.PREMISSA,
                          "venda: créditos do consumidor não compensados nesta apuração (não autorizado no título).")

    if not venda.comprovado:
        memoria.ressalvar(TipoRessalva.PENDENCIA,
                          f"venda: valor de venda ({venda.valor_venda}) sem comprovação documental.")
    if venda.valor_fipe_referencia:
        memoria.registrar(
            "venda", "Valor de venda em relação à referência FIPE (informativo, sem juízo de valor)",
            "proporção = valor de venda / valor FIPE",
            {"venda": venda.valor_venda, "fipe": venda.valor_fipe_referencia},
            venda.valor_venda / venda.valor_fipe_referencia, [venda.origem_fipe], d,
        )

    resultado = saldo_devedor.valor + consideradas - venda.valor_venda - creditos_total
    res = ResultadoVenda(
        data_alienacao=d,
        saldo_devedor_revisado=saldo_devedor.valor,
        despesas_consideradas=consideradas,
        despesas_desconsideradas=desconsideradas,
        valor_venda=venda.valor_venda,
        creditos_consumidor=creditos_total,
        saldo_remanescente_consumidor=arredondar(max(resultado, ZERO), politica),
        valor_a_restituir_consumidor=arredondar(max(-resultado, ZERO), politica),
    )
    memoria.registrar(
        "venda", f"Apuração após a venda do veículo em {d:%d/%m/%Y}",
        "resultado = saldo revisado + despesas comprovadas − venda − créditos do consumidor",
        {"saldo_revisado": saldo_devedor.valor, "despesas": consideradas, "venda": venda.valor_venda,
         "creditos": creditos_total, "abater_despesas": comando.abater_despesas_comprovadas,
         "compensar_creditos": comando.compensar_creditos_consumidor},
        {"saldo_remanescente_consumidor": res.saldo_remanescente_consumidor,
         "a_restituir_consumidor": res.valor_a_restituir_consumidor},
        [comando.origem_titulo, venda.origem] + [x.origem for x in despesas if x.comprovada], d,
    )
    return res


# --- Multa do DL 911/1969 ---------------------------------------------------------------

class MultaDL911(BaseModel):
    model_config = ConfigDict(frozen=True)

    percentual: Decimal
    valor_base: Decimal
    descricao_base: str
    data_valor_base: date
    improcedencia_busca_apreensao: bool
    bem_alienado: bool
    origem_titulo: Origem
    confirmacao_advogada: Origem | None = None
    """Exigida se o título determinar a multa fora das hipóteses do §6º."""


def calcular_multa_dl911(
    multa: MultaDL911,
    data_final: date,
    politica: PoliticaArredondamento,
    memoria: Memoria,
    atualizacao: ParametrosAtualizacao | None = None,
    series: dict[str, SerieMensal] | None = None,
) -> Decimal:
    _exigir_trecho(multa.origem_titulo, "multa do DL 911/1969")
    if not (multa.improcedencia_busca_apreensao and multa.bem_alienado) and multa.confirmacao_advogada is None:
        raise ValueError(
            "multa do art. 3º, §6º, do DL 911/1969 pressupõe improcedência da busca e apreensão e bem já "
            "alienado; registre confirmação da advogada responsável para prosseguir"
        )
    if multa.confirmacao_advogada is not None:
        memoria.ressalvar(TipoRessalva.ALERTA,
                          "multa DL 911: calculada fora das hipóteses do §6º por confirmação expressa da advogada.")
    if multa.percentual != PERCENTUAL_DL911:
        memoria.ressalvar(TipoRessalva.DIVERGENCIA,
                          f"multa DL 911: percentual do título ({multa.percentual}) difere dos 50% do §6º. "
                          "Prevaleceu o título; conferir.")
    memoria.ressalvar(TipoRessalva.PENDENCIA,
                      f"multa DL 911: confirmar que '{multa.descricao_base}' corresponde ao 'valor originalmente "
                      "financiado' (com ou sem IOF e tarifas financiadas) na interpretação do título.")

    if atualizacao is not None:
        base = atualizar(multa.valor_base, multa.data_valor_base, data_final, atualizacao, series or {}, politica,
                         memoria, "da base da multa DL 911").total
    else:
        base = multa.valor_base
        memoria.ressalvar(TipoRessalva.PENDENCIA,
                          "multa DL 911: base não atualizada — informar os critérios de atualização do título.")
    valor = arredondar(base * multa.percentual, politica)
    memoria.registrar(
        "multa_dl911", "Multa do art. 3º, §6º, do DL 911/1969",
        "M = base atualizada × percentual do título",
        {"base_original": multa.valor_base, "descricao_base": multa.descricao_base,
         "base_atualizada": base, "percentual": multa.percentual},
        valor, [multa.origem_titulo], data_final,
    )
    _ressalva_cumulacao(memoria)
    return valor


# --- Perdas e danos (FIPE) ---------------------------------------------------------------

class Deducao(BaseModel):
    model_config = ConfigDict(frozen=True)

    descricao: str
    valor: Decimal
    origem: Origem


class PerdasDanosFipe(BaseModel):
    model_config = ConfigDict(frozen=True)

    valor_fipe: Decimal
    mes_referencia_fipe: str
    codigo_fipe: str | None = None
    origem_fipe: Origem
    data_base: date
    """Data a partir da qual o valor é atualizado (definida no título)."""
    deducoes: list[Deducao] = []
    origem_titulo: Origem


def calcular_perdas_danos_fipe(
    pd: PerdasDanosFipe,
    data_final: date,
    politica: PoliticaArredondamento,
    memoria: Memoria,
    atualizacao: ParametrosAtualizacao | None = None,
    series: dict[str, SerieMensal] | None = None,
) -> Decimal:
    _exigir_trecho(pd.origem_titulo, "perdas e danos")
    deduz = sum((x.valor for x in pd.deducoes), ZERO)
    liquido = pd.valor_fipe - deduz
    if liquido < ZERO:
        memoria.ressalvar(TipoRessalva.ALERTA,
                          f"perdas e danos: deduções ({deduz}) superam o valor FIPE ({pd.valor_fipe}); resultado zerado.")
        liquido = ZERO
    memoria.registrar(
        "perdas_danos", f"Perdas e danos — FIPE {pd.mes_referencia_fipe}",
        "PD = valor FIPE − Σ deduções determinadas no título",
        {"fipe": pd.valor_fipe, "codigo_fipe": pd.codigo_fipe,
         "deducoes": {x.descricao: x.valor for x in pd.deducoes}},
        liquido, [pd.origem_titulo, pd.origem_fipe] + [x.origem for x in pd.deducoes], pd.data_base,
    )
    if atualizacao is not None and liquido > ZERO:
        valor = atualizar(liquido, pd.data_base, data_final, atualizacao, series or {}, politica, memoria,
                          "das perdas e danos").total
    else:
        valor = arredondar(liquido, politica)
        if atualizacao is None:
            memoria.ressalvar(TipoRessalva.PENDENCIA,
                              "perdas e danos: valor não atualizado — informar os critérios do título.")
    _ressalva_cumulacao(memoria)
    return valor


def _ressalva_cumulacao(memoria: Memoria) -> None:
    etapas = {p.etapa for p in memoria.passos}
    if {"multa_dl911", "perdas_danos"} <= etapas:
        memoria.ressalvar(TipoRessalva.PREMISSA,
                          "Multa do DL 911 e perdas e danos calculadas cumulativamente, conforme o título "
                          "(o §7º do art. 3º admite a cumulação; conferir a extensão no caso concreto).")
