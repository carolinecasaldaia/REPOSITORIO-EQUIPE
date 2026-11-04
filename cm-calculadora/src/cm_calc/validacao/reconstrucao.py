"""Reconstrução independente dos apêndices com o motor, a partir da ficha do caso.

Nenhum resultado da perita entra aqui. Os parâmetros de convenção, regime e
arredondamento podem ser sobrepostos SOMENTE para os cenários de diagnóstico
(``comparacao.cenarios``); o cálculo principal usa exatamente o que a ficha
declara.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from ..motor.atualizacao import (
    Acumulacao, ContagemJuros, ConvencaoCompetencias, CriterioCorrecao, CriterioJuros, ParametrosAtualizacao,
    SerieMensal, TipoJuros,
)
from ..motor.auditoria import Memoria, Origem, TipoRessalva
from ..motor.diferencas import PagamentoEfetivo, ResultadoDiferencas, demonstrativo_diferencas
from ..motor.encargos import ContagemAtraso, ParametrosEncargos
from ..motor.evolucao import Evento, OrdemImputacao, ResultadoEvolucao, evoluir_saldo
from ..motor.financiamento import ParcelaPrevista, calcular_parcela_regular
from ..motor.indebito import Modalidade, RegraRestituicao
from ..motor.numeros import ModoArredondamento, PoliticaArredondamento
from ..motor.revisao import ItemExcluido, ParametrosRevisao, ResultadoRevisao, TratamentoReforcadas, recalcular_contrato
from ..motor.taxas import ConvencaoTempo, Regime, Taxa
from .ficha import FichaCaso

INICIO, FIM = date(1900, 1, 1), date(2100, 1, 1)


@dataclass
class Reconstrucao:
    ap01: ResultadoEvolucao
    ap02: ResultadoEvolucao
    revisao: ResultadoRevisao
    ap03: ResultadoDiferencas | None
    memoria: Memoria
    parcela_regular_original: Decimal
    prestacao_price_contrato: Decimal
    descricao: str
    avisos: list[str] = field(default_factory=list)


def politica_de(texto: str) -> PoliticaArredondamento:
    return PoliticaArredondamento.de_texto(texto)


def _origem(f: FichaCaso, chave: str) -> Origem:
    return Origem(documento="Ficha do caso (validação)", localizacao=chave, trecho=f.fontes.get(chave) or None)


def _taxa(mensal: Decimal, anual: Decimal | None, regime: Regime, conv: ConvencaoTempo) -> Taxa:
    return Taxa(mensal=mensal, regime=regime, convencao=conv, anual=anual)


def reconstruir(
    f: FichaCaso,
    series: dict[str, SerieMensal],
    *,
    convencao_contrato: ConvencaoTempo | None = None,
    convencao_revisada: ConvencaoTempo | None = None,
    regime_revisado: Regime | None = None,
    politica: PoliticaArredondamento | None = None,
    com_ap03: bool = True,
) -> Reconstrucao:
    mem = Memoria()
    avisos: list[str] = []
    pol = politica or politica_de(f.texto("arredondamento"))
    conv_c = convencao_contrato or ConvencaoTempo(f.texto("convencao_contrato"))
    conv_r = convencao_revisada or ConvencaoTempo(f.texto("convencao_revisada"))
    reg_r = regime_revisado or Regime(f.texto("regime_revisado"))
    lib, vf = f.data("data_liberacao"), f.decimal("valor_financiado")

    regulares = [p for p in f.parcelas if p.tipo == "regular"]
    moda = Counter(p.valor for p in regulares).most_common(1)[0][0] if regulares else None
    previstas: list[ParcelaPrevista] = []
    for p in f.parcelas:
        if p.tipo == "extraordinária":
            continue
        fixo = None if (p.tipo == "regular" and p.valor == moda) else p.valor
        if p.tipo == "regular" and p.valor != moda:
            avisos.append(f"parcela {p.numero}: valor regular diferente das demais ({p.valor}); tratada como valor fixo")
        previstas.append(ParcelaPrevista(numero=p.numero, vencimento=p.vencimento, valor_fixo=fixo))
    previstas.sort(key=lambda x: x.vencimento)
    extra = [Evento(data=p.vencimento, valor=p.valor, descricao="pagamento extraordinário")
             for p in f.parcelas if p.tipo == "extraordinária"]
    if extra:
        mem.ressalvar(TipoRessalva.PREMISSA, "Pagamentos extraordinários lançados pelo valor efetivo na evolução original e "
                      "na revisada; as parcelas revisadas seguem o cronograma contratual.")

    taxa_c = _taxa(f.percentual("taxa_mensal_contrato"), f.percentual("taxa_anual_contrato"), Regime.COMPOSTO, conv_c)
    price = calcular_parcela_regular(vf, lib, previstas, taxa_c, pol, mem, [_origem(f, "taxa_mensal_contrato")],
                                     etapa="AP01-prestacao").parcela_regular

    # AP01 — evolução original com os valores contratados
    ev01 = [Evento(data=p.vencimento, valor=p.valor, numero_parcela=p.numero, descricao=p.tipo)
            for p in f.parcelas if p.tipo != "extraordinária"] + extra
    ap01 = evoluir_saldo(vf, lib, ev01, taxa_c, pol, OrdemImputacao.JUROS_PRIMEIRO, mem, "AP01",
                         [_origem(f, "valor_financiado"), _origem(f, "taxa_mensal_contrato")])

    # AP02 — recálculo conforme o título
    taxa_r = _taxa(f.percentual("taxa_mensal_revisada"), f.percentual("taxa_anual_revisada"), reg_r, conv_r)
    excl = f.decimal("valor_excluido_financiado") or Decimal(0)
    itens = [ItemExcluido(descricao="itens excluídos pelo título (ficha)", valor=excl, financiado=True,
                          origem_titulo=_origem(f, "valor_excluido_financiado"))] if excl else []
    trat = TratamentoReforcadas(f.texto("tratamento_reforcadas")) if f.texto("tratamento_reforcadas") else None
    rev = recalcular_contrato(vf, lib, previstas, moda or previstas[0].valor_fixo,
                              ParametrosRevisao(taxa_revisada=taxa_r, origem_taxa=_origem(f, "taxa_mensal_revisada"),
                                                itens_excluidos=itens, tratamento_reforcadas=trat), pol, mem)
    ev02 = [Evento(data=p.vencimento, valor=rev.parcelas_revisadas[p.numero], numero_parcela=p.numero, descricao="revisada")
            for p in previstas] + extra
    ap02 = evoluir_saldo(rev.valor_financiado_revisado, lib, ev02, taxa_r, pol, OrdemImputacao.JUROS_PRIMEIRO, mem, "AP02",
                         [_origem(f, "taxa_mensal_revisada")])

    ap03 = _ap03(f, series, rev, previstas, pol, mem) if com_ap03 and f.pagamentos else None
    desc = f"contrato: {conv_c.value}; revisão: {reg_r.value}/{conv_r.value}; arredondamento: {pol.descricao()}"
    return Reconstrucao(ap01=ap01, ap02=ap02, revisao=rev, ap03=ap03, memoria=mem,
                        parcela_regular_original=moda or Decimal(0), prestacao_price_contrato=price,
                        descricao=desc, avisos=avisos)


def parametros_atualizacao(f: FichaCaso) -> ParametrosAtualizacao:
    o = _origem(f, "indice_correcao")
    juros = []
    if f.percentual("juros_mora_mensal") is not None:
        juros.append(CriterioJuros(inicio=f.data("juros_mora_inicio"), fim=FIM, tipo=TipoJuros.PERCENTUAL_FIXO,
                                   percentual_mensal=f.percentual("juros_mora_mensal"),
                                   contagem=ContagemJuros(f.texto("juros_contagem")), origem=_origem(f, "juros_mora_mensal")))
    return ParametrosAtualizacao(
        correcao=[CriterioCorrecao(inicio=INICIO, fim=FIM, serie=f.texto("indice_correcao"), origem=o)],
        juros=juros,
        competencias=ConvencaoCompetencias(incluir_mes_inicial=f.sim("incluir_mes_inicial"),
                                           incluir_mes_final=f.sim("incluir_mes_final")),
        acumulacao_juros=Acumulacao(f.texto("acumulacao_juros") or "soma"))


def _ap03(f: FichaCaso, series, rev: ResultadoRevisao, previstas, pol, mem) -> ResultadoDiferencas:
    venc = {p.numero: p.vencimento for p in previstas}
    trata = f.texto("encargos_no_ap03") or "ignorar"
    pags = []
    for p in f.pagamentos:
        if p.numero not in venc:
            raise ValueError(f"pagamento da parcela {p.numero} sem correspondente na aba 'parcelas'")
        enc = p.encargos if trata == "excluir" else Decimal(0)
        pags.append(PagamentoEfetivo(numero_parcela=p.numero, vencimento=venc[p.numero], data_pagamento=p.data,
                                     valor_parcela_pago=p.valor - p.encargos, encargos_pagos=enc,
                                     origem=Origem(documento="Ficha do caso — aba pagamentos", localizacao=f"parcela {p.numero}")))
    mod = {"simples": Modalidade.SIMPLES, "dobro": Modalidade.DOBRO, "dobro_a_partir_de": Modalidade.DOBRO_A_PARTIR_DE}
    regra = RegraRestituicao(modalidade=mod[f.texto("modalidade_restituicao")],
                             data_corte=f.data("data_corte_dobro") if f.texto("modalidade_restituicao") == "dobro_a_partir_de" else None,
                             origem_titulo=_origem(f, "modalidade_restituicao"))
    # "excluir": nenhum encargo é devido (afastados pelo título) -> pagos integralmente restituídos
    encargos = ParametrosEncargos(contagem=ContagemAtraso.DIAS_30, origem=_origem(f, "encargos_no_ap03")) if trata == "excluir" else None
    return demonstrativo_diferencas(pags, rev, regra, parametros_atualizacao(f), series, f.data("data_base"), pol, mem,
                                    encargos=encargos)
