"""Execução dos cálculos a partir do quadro APROVADO.

Tipos de cálculo:
- RECALCULO : AP01 (evolução original) × AP02 (evolução revisada).
- LIQUIDACAO: AP01, AP02, AP03 (diferenças com restituição e atualização),
              honorários e, se marcado, compensação com o saldo revisado.
- VENDA     : busca e apreensão — AP01, AP02, saldo revisado na alienação e
              apuração após a venda (com crédito do AP03 na data da venda,
              se o título autorizar a compensação).

Tudo o que não vem do quadro (data-base, critérios de atualização, dados da
venda) é informado na tela, com responsável e justificativa, e fica gravado
junto do resultado. Nenhuma fórmula aqui: só chamadas ao motor.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .. import __version__
from ..extracao.adaptador import EntradaMotor, QuadroBloqueado, montar_entrada
from ..extracao.aprovacao import bloqueios
from ..extracao.modelos import QuadroParametros, StatusParametro as S
from ..motor.atualizacao import (
    Acumulacao, ContagemJuros, ConvencaoCompetencias, CriterioCorrecao, CriterioJuros, ParametrosAtualizacao,
    SerieMensal, TipoJuros,
)
from ..motor.auditoria import Memoria, Origem, TipoRessalva
from ..motor.compensacao import Posicao, ResultadoCompensacao, compensar
from ..motor.controle import ControleUtilizacao
from ..motor.datas import competencias_entre
from ..motor.diferencas import PagamentoEfetivo, ResultadoDiferencas, demonstrativo_diferencas
from ..motor.encargos import ContagemAtraso, ParametrosEncargos
from ..motor.evolucao import Evento, ResultadoEvolucao, evoluir_saldo, tabela_contratual
from ..motor.honorarios import calcular_honorarios
from ..motor.numeros import ZERO, arredondar
from ..motor.revisao import ResultadoRevisao, recalcular_contrato
from ..motor.veiculo import ComandoVenda, Despesa, ResultadoVenda, VendaVeiculo, apurar_saldo_pos_venda, posicao_saldo_revisado

INICIO_REMOTO, FIM_REMOTO = date(1900, 1, 1), date(2100, 1, 1)


class TipoCalculo(str, Enum):
    RECALCULO = "Recálculo do contrato (AP01 × AP02)"
    LIQUIDACAO = "Liquidação revisional (AP01, AP02, AP03 e honorários)"
    VENDA = "Busca e apreensão — saldo após a venda do veículo"


class CriteriosAtualizacao(BaseModel):
    """Critérios do título para atualizar o indébito, confirmados na tela."""

    serie_correcao: str | None
    """Nome da série carregada; None = sem correção monetária."""
    incluir_mes_inicial: bool
    incluir_mes_final: bool
    juros_taxa_mensal: Decimal | None
    """Fração (0.01 = 1% a.m.). None = sem juros de mora."""
    juros_inicio: date | None
    juros_contagem: ContagemJuros
    acumulacao: Acumulacao
    contagem_atraso: ContagemAtraso
    justificativa: str
    """Trecho do título / decisão da advogada que fundamenta os critérios."""


class DespesaVenda(BaseModel):
    descricao: str
    valor: Decimal
    data: date
    comprovada: bool


class DadosVenda(BaseModel):
    data_alienacao: date
    valor_venda: Decimal
    venda_comprovada: bool
    despesas: list[DespesaVenda] = Field(default_factory=list)
    abater_despesas: bool
    compensar_creditos: bool
    trecho_titulo: str


class OpcoesCalculo(BaseModel):
    tipo: TipoCalculo
    data_base: date
    responsavel: str
    criterios: CriteriosAtualizacao | None = None
    honorarios_sobre_ap03: bool = True
    valor_base_honorarios: Decimal | None = None
    compensar_saldo_revisado: bool = False
    venda: DadosVenda | None = None


class ResultadoExecucao(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    tipo: TipoCalculo
    executado_em: datetime
    executado_por: str
    data_base: date
    hash_quadro: str
    versao: str
    opcoes: OpcoesCalculo
    parcela_original: Decimal
    revisao: ResultadoRevisao
    ap01: ResultadoEvolucao
    ap02: ResultadoEvolucao
    ap03: ResultadoDiferencas | None = None
    honorarios: Decimal | None = None
    compensacao: ResultadoCompensacao | None = None
    saldo_alienacao: Posicao | None = None
    venda: ResultadoVenda | None = None
    memoria: Memoria


def hash_quadro(q: QuadroParametros) -> str:
    return hashlib.sha256(q.model_dump_json().encode()).hexdigest()[:16]


def pendencias_calculo(q: QuadroParametros, op: OpcoesCalculo, series: dict[str, SerieMensal]) -> list[str]:
    pend = list(bloqueios(q))
    if not op.responsavel.strip():
        pend.append("informe a responsável pela execução")
    if op.tipo is TipoCalculo.RECALCULO:
        return pend

    pags = [p for p in q.pagamentos if p.data_pagamento]
    ultimo = max((p.data_pagamento for p in pags), default=None)
    data_ref = op.venda.data_alienacao if (op.tipo is TipoCalculo.VENDA and op.venda) else op.data_base
    if ultimo and data_ref < ultimo:
        pend.append(f"data-base ({data_ref:%d/%m/%Y}) anterior ao último pagamento ({ultimo:%d/%m/%Y})")
    if any(p.parcela is None for p in q.pagamentos):
        pend.append("há pagamento sem número de parcela")
    if any(p.valor is None or p.data_pagamento is None for p in q.pagamentos):
        pend.append("há pagamento sem valor ou sem data (a ciência da ocorrência não supre o dado)")
    if any(p.encargos for p in q.pagamentos):
        conf = [q.parametros.get(k) for k in ("contrato.multa_moratoria", "contrato.juros_moratorios")]
        if not any(p is not None and p.status is S.CONFIRMADO for p in conf):
            pend.append("há encargos pagos: confirme a multa e/ou os juros moratórios do contrato")

    if op.tipo is TipoCalculo.VENDA:
        if op.venda is None:
            pend.append("informe os dados da venda do veículo")
        elif not op.venda.trecho_titulo.strip():
            pend.append("informe o trecho do título que fundamenta a apuração após a venda")

    precisa_ap03 = op.tipo is TipoCalculo.LIQUIDACAO or (op.venda is not None and op.venda.compensar_creditos)
    if precisa_ap03:
        rep = q.parametros.get("titulo.repeticao")
        if rep is None or rep.status is not S.CONFIRMADO:
            pend.append("repetição do indébito (titulo.repeticao) não confirmada")
        c = op.criterios
        if c is None:
            pend.append("defina os critérios de correção monetária e juros")
        else:
            if not c.justificativa.strip():
                pend.append("critérios de atualização sem fundamentação (trecho do título)")
            if c.juros_taxa_mensal is not None and c.juros_inicio is None:
                pend.append("informe o termo inicial dos juros de mora (data)")
            if c.serie_correcao:
                s = series.get(c.serie_correcao)
                if s is None:
                    pend.append(f"série {c.serie_correcao} não carregada")
                else:
                    primeiro = min((p.data_pagamento for p in pags), default=data_ref)
                    faltam = [f"{a:04d}-{m:02d}" for a, m in competencias_entre((primeiro.year, primeiro.month),
                                                                                (data_ref.year, data_ref.month))
                              if f"{a:04d}-{m:02d}" not in s.valores]
                    if faltam:
                        pend.append(f"série {s.nome} sem valores para {', '.join(faltam[:6])}"
                                    + ("…" if len(faltam) > 6 else ""))
    if op.tipo is TipoCalculo.LIQUIDACAO and "titulo.honorarios" in q.parametros:
        if not op.honorarios_sobre_ap03 and op.valor_base_honorarios is None:
            pend.append("informe o valor da base dos honorários")
    return pend


def _origem_tela(op: OpcoesCalculo, texto: str) -> Origem:
    return Origem(documento=f"Definido na tela de cálculo por {op.responsavel}", trecho=texto)


def _parametros_atualizacao(c: CriteriosAtualizacao, origem: Origem) -> ParametrosAtualizacao:
    correcao = [CriterioCorrecao(inicio=INICIO_REMOTO, fim=FIM_REMOTO, serie=c.serie_correcao, origem=origem)]
    juros = []
    if c.juros_taxa_mensal is not None:
        juros.append(CriterioJuros(inicio=c.juros_inicio, fim=FIM_REMOTO, tipo=TipoJuros.PERCENTUAL_FIXO,
                                   percentual_mensal=c.juros_taxa_mensal, contagem=c.juros_contagem, origem=origem))
    return ParametrosAtualizacao(
        correcao=correcao, juros=juros, acumulacao_juros=c.acumulacao,
        competencias=ConvencaoCompetencias(incluir_mes_inicial=c.incluir_mes_inicial, incluir_mes_final=c.incluir_mes_final))


def _pagamentos(q: QuadroParametros, e: EntradaMotor) -> list[PagamentoEfetivo]:
    venc = {p.numero: p.vencimento for p in e.parcelas}
    out = []
    for p in q.pagamentos:
        if p.parcela not in venc:
            raise QuadroBloqueado([f"pagamento da parcela {p.parcela} não consta do cronograma"])
        encargos = Decimal(p.encargos) if p.encargos else ZERO
        origem = Origem(documento=f"{p.fonte.tipo_documento.value} — {p.fonte.arquivo}", localizacao=f"p. {p.fonte.pagina}",
                        trecho=p.fonte.trecho)
        out.append(PagamentoEfetivo(numero_parcela=p.parcela, vencimento=venc[p.parcela], data_pagamento=p.data_pagamento,
                                    valor_parcela_pago=Decimal(p.valor) - encargos, encargos_pagos=encargos, origem=origem))
    return out


def _encargos(q: QuadroParametros, e: EntradaMotor, c: CriteriosAtualizacao) -> ParametrosEncargos | None:
    multa, juros = q.parametros.get("contrato.multa_moratoria"), q.parametros.get("contrato.juros_moratorios")
    conf = [p for p in (multa, juros) if p is not None and p.status is S.CONFIRMADO]
    if not conf:
        return None
    return ParametrosEncargos(
        multa=Decimal(multa.valor_vigente()) if multa in conf else None,
        juros_mora_mensal=Decimal(juros.valor_vigente()) if juros in conf else None,
        contagem=c.contagem_atraso, origem=e.origens.get("contrato.multa_moratoria") or e.origens["contrato.juros_moratorios"])


def _ap03(q, e, rev, op, series, data_base, mem) -> ResultadoDiferencas:
    c = op.criterios
    atual = _parametros_atualizacao(c, _origem_tela(op, c.justificativa))
    avulsos = [i for i in e.revisao.itens_excluidos if not i.financiado]
    return demonstrativo_diferencas(_pagamentos(q, e), rev, e.regra_restituicao, atual, series, data_base, e.politica,
                                    mem, _encargos(q, e, c), e.descaracterizacao, avulsos)


def _eventos_revisados(q, rev: ResultadoRevisao, ate: date) -> list[Evento]:
    return [Evento(data=p.data_pagamento, valor=rev.parcelas_revisadas[p.parcela], numero_parcela=p.parcela,
                   descricao="parcela revisada (paga)")
            for p in q.pagamentos if p.data_pagamento and p.data_pagamento <= ate]


def executar(q: QuadroParametros, op: OpcoesCalculo, series: dict[str, SerieMensal]) -> ResultadoExecucao:
    pend = pendencias_calculo(q, op, series)
    if pend:
        raise QuadroBloqueado(pend)
    e = montar_entrada(q)
    mem = Memoria()
    o = e.origens
    ap01 = tabela_contratual(e.valor_financiado, e.data_liberacao, e.parcelas, e.parcela_original, e.taxa_contratual,
                             e.politica, mem, "AP01", [o["contrato.valor_financiado"], o["contrato.taxa_mensal"]])
    rev = recalcular_contrato(e.valor_financiado, e.data_liberacao, e.parcelas, e.parcela_original, e.revisao,
                              e.politica, mem)
    ap02 = tabela_contratual(rev.valor_financiado_revisado, e.data_liberacao, e.parcelas, rev.parcela_regular_revisada,
                             e.revisao.taxa_revisada, e.politica, mem, "AP02", [e.revisao.origem_taxa])
    if e.descaracterizacao:
        from ..motor.encargos import ressalvas_descaracterizacao
        ressalvas_descaracterizacao(e.descaracterizacao, mem)

    res = dict(tipo=op.tipo, executado_em=datetime.now().replace(microsecond=0), executado_por=op.responsavel.strip(),
               data_base=op.data_base, hash_quadro=hash_quadro(q), versao=__version__, opcoes=op,
               parcela_original=e.parcela_original, revisao=rev, ap01=ap01, ap02=ap02)
    controle = ControleUtilizacao()

    if op.tipo is TipoCalculo.LIQUIDACAO:
        ap03 = _ap03(q, e, rev, op, series, op.data_base, mem)
        res["ap03"] = ap03
        if e.honorarios is not None:
            base = ap03.total_atualizado if op.honorarios_sobre_ap03 else op.valor_base_honorarios
            if op.honorarios_sobre_ap03:
                mem.ressalvar(TipoRessalva.PREMISSA, "Honorários calculados sobre o total atualizado do AP03 "
                              "(escolha registrada na tela de cálculo; conferir com a base fixada no título).")
            res["honorarios"] = calcular_honorarios(e.honorarios, base, e.politica, mem,
                                                    "total do AP03" if op.honorarios_sobre_ap03 else "valor informado")
        if op.compensar_saldo_revisado:
            saldo = evoluir_saldo(rev.valor_financiado_revisado, e.data_liberacao, _eventos_revisados(q, rev, op.data_base),
                                  e.revisao.taxa_revisada, e.politica, e.ordem, mem, "saldo_revisado",
                                  [e.revisao.origem_taxa], op.data_base)
            mem.ressalvar(TipoRessalva.PENDENCIA, "saldo_revisado: taxa revisada aplicada até a data-base, inclusive "
                          "após eventual inadimplemento. Confirmar o critério com a advogada.")
            res["compensacao"] = compensar(
                [Posicao(id="ap03", descricao="Indébito atualizado (AP03)", valor=ap03.total_atualizado, data_base=op.data_base)],
                [Posicao(id="saldo", descricao="Saldo devedor revisado", valor=arredondar(saldo.saldo_final, e.politica),
                         data_base=op.data_base)],
                o.get("titulo.compensacao") or _origem_tela(op, "compensação marcada na tela de cálculo"), mem, controle)

    if op.tipo is TipoCalculo.VENDA:
        v = op.venda
        origem_titulo = Origem(documento="Título judicial (trecho informado na tela)", trecho=v.trecho_titulo)
        saldo = posicao_saldo_revisado(rev.valor_financiado_revisado, e.data_liberacao,
                                       _eventos_revisados(q, rev, v.data_alienacao), e.revisao.taxa_revisada, e.politica,
                                       e.ordem, v.data_alienacao, mem, [e.revisao.origem_taxa])
        creditos = []
        if v.compensar_creditos:
            ap03 = _ap03(q, e, rev, op, series, v.data_alienacao, mem)
            res["ap03"] = ap03
            creditos = [Posicao(id="ap03", descricao="Indébito atualizado (AP03)", valor=ap03.total_atualizado,
                                data_base=v.data_alienacao)]
        despesas = [Despesa(id=f"despesa-{i}", descricao=d.descricao, valor=d.valor, data=d.data, comprovada=d.comprovada,
                            origem=_origem_tela(op, "despesa informada na tela"))
                    for i, d in enumerate(v.despesas, start=1)]
        res["saldo_alienacao"] = saldo
        res["venda"] = apurar_saldo_pos_venda(
            saldo, VendaVeiculo(data_alienacao=v.data_alienacao, valor_venda=v.valor_venda, comprovado=v.venda_comprovada,
                                origem=_origem_tela(op, "valor de venda informado na tela")),
            despesas, creditos,
            ComandoVenda(abater_despesas_comprovadas=v.abater_despesas, compensar_creditos_consumidor=v.compensar_creditos,
                         origem_titulo=origem_titulo),
            e.politica, mem, controle)

    return ResultadoExecucao(**res, memoria=mem)


def salvar_resultado(r: ResultadoExecucao, pasta: Path) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / f"resultado-{r.executado_em:%Y%m%d-%H%M%S}-{r.hash_quadro[:8]}.json"
    arq.write_text(r.model_dump_json(indent=1), encoding="utf-8")
    return arq


def listar_resultados(pasta: Path) -> list[Path]:
    return sorted(pasta.glob("resultado-*.json"), reverse=True) if pasta.exists() else []


def carregar_resultado(arq: Path) -> ResultadoExecucao:
    return ResultadoExecucao.model_validate_json(arq.read_text(encoding="utf-8"))
