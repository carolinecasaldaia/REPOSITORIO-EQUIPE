"""Demonstrativo de diferenças pago × devido (base do AP03).

Para cada pagamento efetivo:
    devido   = parcela revisada + encargos revisados (zerados no que a mora
               foi descaracterizada pelo título)
    pago     = parcela paga + encargos pagos
    diferença = pago − devido

Diferença positiva  -> indébito: simples/dobro (``indebito``) e atualização
                       (``atualizacao``) até a data-base.
Diferença negativa  -> valor pago a menor: listado à parte, SEM atualização
                       automática (critério depende do título — pendência).

Itens declarados indevidos e pagos fora do financiamento (tarifas/seguros à
vista) entram como indébito pela data do pagamento.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from .atualizacao import Fase, ParametrosAtualizacao, SerieMensal, atualizar, atualizar_por_fases
from .auditoria import Memoria, Origem, TipoRessalva
from .encargos import Descaracterizacao, ParametrosEncargos, calcular_encargos
from .indebito import RegraRestituicao, valor_a_restituir
from .numeros import ZERO, PoliticaArredondamento, arredondar_se_parcela
from .revisao import ItemExcluido, ResultadoRevisao
from .taxas import Taxa


class PagamentoEfetivo(BaseModel):
    model_config = ConfigDict(frozen=True)

    numero_parcela: int
    vencimento: date
    data_pagamento: date
    valor_parcela_pago: Decimal
    encargos_pagos: Decimal = ZERO
    antecipada_com_desconto: bool = False
    """Paga antes do vencimento com desconto concedido pelo credor: o devido revisado é trazido a valor
    presente na data do pagamento pela taxa revisada (exige ``taxa_desconto`` no demonstrativo)."""
    origem: Origem


class LinhaDiferenca(BaseModel):
    model_config = ConfigDict(frozen=True)

    descricao: str
    data_pagamento: date
    pago: Decimal
    devido: Decimal
    diferenca: Decimal
    a_restituir: Decimal
    corrigido: Decimal
    juros: Decimal
    atualizado: Decimal


class ResultadoDiferencas(BaseModel):
    model_config = ConfigDict(frozen=True)

    data_base: date
    linhas: list[LinhaDiferenca]
    pagos_a_menor: list[LinhaDiferenca]
    total_pago: Decimal
    total_devido: Decimal
    total_diferenca_nominal: Decimal
    total_a_restituir_nominal: Decimal
    total_atualizado: Decimal


def demonstrativo_diferencas(
    pagamentos: list[PagamentoEfetivo],
    revisao: ResultadoRevisao,
    regra: RegraRestituicao,
    atualizacao: ParametrosAtualizacao | None,
    series: dict[str, SerieMensal],
    data_base: date,
    politica: PoliticaArredondamento,
    memoria: Memoria,
    encargos: ParametrosEncargos | None = None,
    descaracterizacao: Descaracterizacao | None = None,
    itens_avulsos: list[ItemExcluido] | None = None,
    fases: list[Fase] | None = None,
    taxa_desconto: Taxa | None = None,
) -> ResultadoDiferencas:
    """``fases``: atualização em etapas consolidadas (ex.: INPC + mora até a citação; depois só Selic),
    quando o título determinar — substitui ``atualizacao`` (que pode ser None). A data final da última fase
    deve ser a data-base."""
    if fases is not None and fases[-1].fim != data_base:
        raise ValueError("a última fase da atualização deve terminar na data-base")
    if fases is None and atualizacao is None:
        raise ValueError("informe os critérios de atualização (atualizacao ou fases)")
    linhas: list[LinhaDiferenca] = []
    a_menor: list[LinhaDiferenca] = []
    total_pago = total_devido = ZERO

    for pg in sorted(pagamentos, key=lambda p: (p.data_pagamento, p.numero_parcela)):
        if pg.numero_parcela not in revisao.parcelas_revisadas:
            raise ValueError(f"parcela {pg.numero_parcela} não existe no cronograma revisado")
        devido_parcela = revisao.parcelas_revisadas[pg.numero_parcela]
        if pg.antecipada_com_desconto:
            if taxa_desconto is None:
                raise ValueError(f"parcela {pg.numero_parcela}: antecipada com desconto exige taxa_desconto")
            if pg.data_pagamento >= pg.vencimento:
                raise ValueError(f"parcela {pg.numero_parcela}: marcada como antecipada, mas paga no/após o vencimento")
            nominal = devido_parcela
            devido_parcela = arredondar_se_parcela(
                nominal / taxa_desconto.fator(pg.data_pagamento, pg.vencimento), politica)
            memoria.registrar(
                "AP03-antecipacao", f"Parcela {pg.numero_parcela} antecipada: devido revisado a valor presente",
                "devido = parcela revisada / F(data do pagamento, vencimento)",
                {"parcela_revisada": nominal, "pagamento": pg.data_pagamento.isoformat(),
                 "vencimento": pg.vencimento.isoformat(), "taxa": taxa_desconto.descricao()},
                devido_parcela, [pg.origem], pg.data_pagamento)
        devido_enc = ZERO
        if pg.data_pagamento > pg.vencimento:
            if encargos is None:
                if pg.encargos_pagos > ZERO:
                    raise ValueError(
                        f"parcela {pg.numero_parcela}: há encargos pagos, mas não foram informados os "
                        "parâmetros de encargos devidos (contrato/título)"
                    )
            else:
                devido_enc = sum(calcular_encargos(
                    devido_parcela, pg.vencimento, pg.data_pagamento, encargos, politica,
                    descaracterizacao, memoria, etapa="AP03-encargos").values(), ZERO)
        pago = pg.valor_parcela_pago + pg.encargos_pagos
        devido = devido_parcela + devido_enc
        total_pago += pago
        total_devido += devido
        dif = pago - devido
        desc = f"Parcela {pg.numero_parcela}"
        if dif < ZERO:
            a_menor.append(LinhaDiferenca(
                descricao=desc, data_pagamento=pg.data_pagamento, pago=pago, devido=devido,
                diferenca=dif, a_restituir=ZERO, corrigido=ZERO, juros=ZERO, atualizado=ZERO))
            continue
        linhas.append(_linha_indebito(desc, pg.data_pagamento, pago, devido, regra, atualizacao,
                                      series, data_base, politica, memoria, fases))

    for item in itens_avulsos or []:
        if item.financiado:
            raise ValueError(f"{item.descricao}: item financiado é tratado na revisão (AP02), não como avulso")
        total_pago += item.valor
        linhas.append(_linha_indebito(item.descricao, item.data_pagamento, item.valor, ZERO, regra,
                                      atualizacao, series, data_base, politica, memoria, fases))

    if a_menor:
        memoria.ressalvar(
            TipoRessalva.PENDENCIA,
            f"AP03: {len(a_menor)} pagamento(s) abaixo do valor revisado devido. Listados sem atualização; "
            "definir com a advogada o critério de atualização/compensação conforme o título.",
        )

    res = ResultadoDiferencas(
        data_base=data_base,
        linhas=linhas,
        pagos_a_menor=a_menor,
        total_pago=total_pago,
        total_devido=total_devido,
        total_diferenca_nominal=total_pago - total_devido,
        total_a_restituir_nominal=sum((l.a_restituir for l in linhas), ZERO),
        total_atualizado=sum((l.atualizado for l in linhas), ZERO),
    )
    memoria.registrar(
        "AP03", "Totais do demonstrativo de diferenças",
        "Σ pago − Σ devido = Σ diferenças positivas + Σ diferenças negativas",
        {"pagamentos": len(pagamentos), "itens_avulsos": len(itens_avulsos or []),
         "regra": regra.modalidade.value},
        {"total_pago": res.total_pago, "total_devido": res.total_devido,
         "diferenca_nominal": res.total_diferenca_nominal,
         "a_restituir_nominal": res.total_a_restituir_nominal,
         "total_atualizado": res.total_atualizado},
        [regra.origem_titulo], data_base,
    )
    return res


def _linha_indebito(desc: str, data_pag: date, pago: Decimal, devido: Decimal,
                    regra: RegraRestituicao, atualizacao: ParametrosAtualizacao,
                    series: dict[str, SerieMensal], data_base: date,
                    politica: PoliticaArredondamento, memoria: Memoria,
                    fases: list[Fase] | None = None) -> LinhaDiferenca:
    dif = pago - devido
    restituir = valor_a_restituir(dif, data_pag, regra, memoria, desc)
    if fases is None:
        at = atualizar(restituir, data_pag, data_base, atualizacao, series, politica, memoria, desc)
        return LinhaDiferenca(
            descricao=desc, data_pagamento=data_pag, pago=pago, devido=devido, diferenca=dif,
            a_restituir=restituir, corrigido=at.valor_corrigido, juros=at.juros, atualizado=at.total,
        )
    # pagamento posterior ao fim de uma fase (ex.: pago após a citação): começa na fase vigente
    vigentes = [f for f in fases if f.fim > data_pag] or fases[-1:]
    rf = atualizar_por_fases(restituir, min(data_pag, vigentes[0].fim), vigentes, series, politica, memoria, desc)
    f1 = rf.fases[0]
    return LinhaDiferenca(
        descricao=desc, data_pagamento=data_pag, pago=pago, devido=devido, diferenca=dif,
        a_restituir=restituir, corrigido=f1.valor_corrigido, juros=rf.total - f1.valor_corrigido,
        atualizado=rf.total,
    )
