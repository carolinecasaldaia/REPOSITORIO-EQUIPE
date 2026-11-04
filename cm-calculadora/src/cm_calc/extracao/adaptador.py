"""Quadro APROVADO -> objetos do motor matemático.

Recusa qualquer quadro com bloqueios. Usa somente valores confirmados
(``valor_vigente``/``detalhes_vigentes``) e leva a origem documental de cada
parâmetro para a memória de cálculo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from ..documentos.modelos import Fonte
from ..documentos.texto import valor_br
from ..motor.auditoria import Memoria, Origem
from ..motor.datas import vencimentos_mensais
from ..motor.encargos import Componente, Descaracterizacao
from ..motor.financiamento import ParcelaPrevista
from ..motor.honorarios import BaseHonorarios, ParametrosHonorarios
from ..motor.indebito import Modalidade, RegraRestituicao
from ..motor.numeros import ModoArredondamento, PoliticaArredondamento, pct
from ..motor.revisao import ItemExcluido, ParametrosRevisao, ResultadoRevisao, recalcular_contrato
from ..motor.taxas import ConvencaoTempo, Regime, Taxa
from ..motor.evolucao import OrdemImputacao
from .aprovacao import bloqueios
from .catalogo import id_item
from .modelos import Parametro, QuadroParametros, StatusParametro as S


class QuadroBloqueado(RuntimeError):
    def __init__(self, pendencias: list[str]):
        super().__init__("cálculo definitivo bloqueado:\n- " + "\n- ".join(pendencias))
        self.pendencias = pendencias


@dataclass
class EntradaMotor:
    politica: PoliticaArredondamento
    ordem: OrdemImputacao
    data_liberacao: date
    valor_financiado: Decimal
    parcelas: list[ParcelaPrevista]
    parcela_original: Decimal
    taxa_contratual: Taxa
    revisao: ParametrosRevisao
    regra_restituicao: RegraRestituicao | None
    descaracterizacao: Descaracterizacao | None
    honorarios: ParametrosHonorarios | None
    origens: dict[str, Origem] = field(default_factory=dict)


def origem_de(p: Parametro) -> Origem:
    if not p.fontes:
        return Origem(documento=f"Definido pela advogada ({p.confirmado_por})", localizacao=p.id)
    f: Fonte = p.fontes[0]
    loc = f"p. {f.pagina}" + (f" ({f.referencia_pje})" if f.referencia_pje else "")
    return Origem(documento=f"{f.tipo_documento.value} — {f.arquivo}", localizacao=loc, trecho=f.trecho)


def _p(q: QuadroParametros, pid: str) -> Parametro | None:
    p = q.parametros.get(pid)
    return p if p is not None and p.status is S.CONFIRMADO else None


def _exigir(q: QuadroParametros, pid: str) -> Parametro:
    p = _p(q, pid)
    if p is None:
        raise QuadroBloqueado([f"{pid} não confirmado"])
    return p


def _politica(s: str) -> PoliticaArredondamento:
    return PoliticaArredondamento.de_texto(s)


def _percent(s: str) -> Decimal:
    return pct(s.replace("%", "").strip())


def montar_entrada(q: QuadroParametros) -> EntradaMotor:
    pend = bloqueios(q)
    if pend:
        raise QuadroBloqueado(pend)

    politica = _politica(_exigir(q, "calculo.arredondamento").valor_vigente())
    convencao = ConvencaoTempo(_exigir(q, "calculo.convencao_tempo").valor_vigente())
    ordem = OrdemImputacao(_exigir(q, "calculo.ordem_imputacao").valor_vigente())
    lib = date.fromisoformat(_exigir(q, "contrato.data_liberacao").valor_vigente())
    vf = Decimal(_exigir(q, "contrato.valor_financiado").valor_vigente())
    n = int(_exigir(q, "contrato.n_parcelas").valor_vigente())
    primeiro = date.fromisoformat(_exigir(q, "contrato.primeiro_vencimento").valor_vigente())
    pmt = Decimal(_exigir(q, "contrato.valor_parcela").valor_vigente())
    p_tm = _exigir(q, "contrato.taxa_mensal")
    p_ta = _p(q, "contrato.taxa_anual")
    taxa_orig = Taxa(mensal=Decimal(p_tm.valor_vigente()), regime=Regime.COMPOSTO, convencao=convencao,
                     anual=Decimal(p_ta.valor_vigente()) if p_ta else None)
    origens = {pid: origem_de(p) for pid, p in q.parametros.items() if p.status is S.CONFIRMADO}
    parcelas = [ParcelaPrevista(numero=k + 1, vencimento=d) for k, d in enumerate(vencimentos_mensais(primeiro, n))]

    # Taxa e regime revisados
    taxa_rev, origem_taxa = taxa_orig, origens["contrato.taxa_mensal"]
    jr = _p(q, "titulo.juros_remuneratorios")
    regime_rev = Regime.COMPOSTO
    cap = _p(q, "titulo.capitalizacao")
    if cap and cap.valor_vigente() == "afastada":
        det = cap.detalhes_vigentes()
        if "regime_revisado" not in det:
            raise QuadroBloqueado(["titulo.capitalizacao: informe 'regime_revisado' (simples/composto) ao confirmar"])
        regime_rev = Regime(det["regime_revisado"])
    if jr and jr.valor_vigente() == "revisados":
        det = jr.detalhes_vigentes()
        if "taxa_mensal" not in det:
            raise QuadroBloqueado(["titulo.juros_remuneratorios: informe a taxa mensal revisada ao confirmar"])
        taxa_rev = Taxa(mensal=_percent(det["taxa_mensal"]), regime=regime_rev, convencao=convencao)
        origem_taxa = origens["titulo.juros_remuneratorios"]
    elif regime_rev is not Regime.COMPOSTO:
        taxa_rev = Taxa(mensal=taxa_orig.mensal, regime=regime_rev, convencao=convencao)
        origem_taxa = origens["titulo.capitalizacao"]

    # Exclusões: o item precisa estar confirmado na composição (valor e forma)
    excluidos: list[ItemExcluido] = []
    for pid, p in q.parametros.items():
        if not pid.startswith("titulo.exclusao:") or p.status is not S.CONFIRMADO:
            continue
        if not p.valor_vigente().startswith("excluída"):
            continue
        item_pid = f"contrato.item:{id_item(p.detalhes_vigentes().get('item', ''))}"
        item = _p(q, item_pid)
        if item is None:
            raise QuadroBloqueado([f"{pid}: item {item_pid} não confirmado na composição do contrato"])
        forma = item.detalhes_vigentes().get("forma")
        if forma not in ("financiado", "à vista"):
            raise QuadroBloqueado([f"{item_pid}: forma de pagamento não confirmada"])
        data_pg = item.detalhes_vigentes().get("data_pagamento")
        if forma == "à vista" and not data_pg:
            raise QuadroBloqueado([f"{item_pid}: item pago à vista sem 'data_pagamento' confirmada (não é presumida)"])
        excluidos.append(ItemExcluido(
            descricao=item.descricao.replace("Item: ", ""), valor=Decimal(item.valor_vigente()),
            financiado=forma == "financiado",
            data_pagamento=date.fromisoformat(data_pg) if data_pg else None,
            origem_titulo=origens[pid]))

    revisao = ParametrosRevisao(taxa_revisada=taxa_rev, origem_taxa=origem_taxa, itens_excluidos=excluidos)

    regra = None
    if rp := _p(q, "titulo.repeticao"):
        v, det = rp.valor_vigente(), rp.detalhes_vigentes()
        mapa = {"simples": Modalidade.SIMPLES, "em dobro": Modalidade.DOBRO,
                "dobro a partir de data": Modalidade.DOBRO_A_PARTIR_DE}
        if v not in mapa:
            raise QuadroBloqueado([f"titulo.repeticao: '{v}' — confirme como simples, em dobro ou dobro a partir de data"])
        corte = date.fromisoformat(det["data_corte"]) if mapa[v] is Modalidade.DOBRO_A_PARTIR_DE else None
        regra = RegraRestituicao(modalidade=mapa[v], data_corte=corte, origem_titulo=origens["titulo.repeticao"])

    desc = None
    if mo := _p(q, "titulo.mora"):
        if mo.valor_vigente() == "descaracterizada":
            comps = [c for c in mo.detalhes_vigentes().get("componentes", "").split(",") if c]
            desc = Descaracterizacao(componentes_afastados=frozenset(Componente(c) for c in comps),
                                     origem_titulo=origens["titulo.mora"])

    hon = None
    if h := _p(q, "titulo.honorarios"):
        det = h.detalhes_vigentes()
        bases = {"valor da condenacao": BaseHonorarios.CONDENACAO, "valor atualizado da condenacao": BaseHonorarios.CONDENACAO,
                 "proveito economico": BaseHonorarios.PROVEITO_ECONOMICO,
                 "valor da causa": BaseHonorarios.VALOR_CAUSA_ATUALIZADO,
                 "valor atualizado da causa": BaseHonorarios.VALOR_CAUSA_ATUALIZADO}
        if "valor_fixo" in det:
            hon = ParametrosHonorarios(base=BaseHonorarios.VALOR_FIXO, valor_fixo=valor_br(det["valor_fixo"]),
                                       devedor=det.get("devedor", "[INFORMAÇÃO PENDENTE]"), origem_titulo=origens["titulo.honorarios"])
        else:
            hon = ParametrosHonorarios(base=bases[det["base"]], percentual=_percent(det["percentual"]),
                                       cota_devedor=Decimal(det.get("cota_devedor", "1")),
                                       devedor=det.get("devedor", "[INFORMAÇÃO PENDENTE]"),
                                       origem_titulo=origens["titulo.honorarios"])

    return EntradaMotor(politica=politica, ordem=ordem, data_liberacao=lib, valor_financiado=vf, parcelas=parcelas,
                        parcela_original=pmt, taxa_contratual=taxa_orig, revisao=revisao, regra_restituicao=regra,
                        descaracterizacao=desc, honorarios=hon, origens=origens)


def executar_revisao(e: EntradaMotor) -> tuple[ResultadoRevisao, Memoria]:
    mem = Memoria()
    r = recalcular_contrato(e.valor_financiado, e.data_liberacao, e.parcelas, e.parcela_original, e.revisao,
                            e.politica, mem)
    return r, mem
