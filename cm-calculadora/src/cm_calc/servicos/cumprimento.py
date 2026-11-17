"""Cumprimento / liquidação de sentença revisional a partir de uma FICHA (JSON) — sem perito.

A ficha traz só ENTRADAS, cada critério com a sua origem (documento, folha e trecho literal do
dispositivo). Nenhum critério jurídico tem padrão: o que faltar é recusado (ValueError) e vira
pendência para a advogada. Este módulo não calcula nada por conta própria: só monta os parâmetros
e chama o motor.

Saídas: AP01 (contrato como cobrado), AP02 (contrato revisado pelo título), AP03 (pago × devido,
restituição simples/dobro e atualização, inclusive em fases — ex.: INPC + mora até a citação,
depois só Selic), verbas autorizadas (dano moral, dano material, multa…), honorários e total.

Formato da ficha: ver docs/CUMPRIMENTO.md.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..motor.atualizacao import (Acumulacao, ContagemJuros, ConvencaoCompetencias, CriterioCorrecao, CriterioJuros,
                                 Fase, ParametrosAtualizacao, SerieMensal, TipoJuros, atualizar_por_fases)
from ..motor.auditoria import Memoria, Origem
from ..motor.diferencas import PagamentoEfetivo, ResultadoDiferencas, demonstrativo_diferencas
from ..motor.encargos import Componente, ContagemAtraso, Descaracterizacao, ParametrosEncargos
from ..motor.evolucao import ResultadoEvolucao, tabela_contratual
from ..motor.financiamento import ParcelaPrevista
from ..motor.honorarios import BaseHonorarios, ParametrosHonorarios, calcular_honorarios
from ..motor.indebito import Modalidade, RegraRestituicao
from ..motor.numeros import ZERO, PoliticaArredondamento, arredondar
from ..motor.revisao import ItemExcluido, ParametrosRevisao, ResultadoRevisao, TratamentoReforcadas, recalcular_contrato
from ..motor.taxas import ConvencaoTempo, Regime, Taxa
from ..motor.verbas import VerbaAutorizada, calcular_verba

INICIO_REMOTO = date(1900, 1, 1)


def _d(v) -> date:
    if isinstance(v, date):
        return v
    return datetime.strptime(str(v).strip(), "%d/%m/%Y").date()


def _pct(v) -> Decimal:
    """'1,40' ou 1.40 (percentual) -> 0.014."""
    return Decimal(str(v).replace(",", ".")) / 100


def _dec(v) -> Decimal:
    return Decimal(str(v).replace(",", "."))


class Fonte(BaseModel):
    model_config = ConfigDict(extra="forbid")
    documento: str
    localizacao: str | None = None
    trecho: str | None = None

    def origem(self) -> Origem:
        return Origem(documento=self.documento, localizacao=self.localizacao, trecho=self.trecho)


class FonteTitulo(Fonte):
    """Critério do título: trecho literal obrigatório."""

    @model_validator(mode="after")
    def _trecho(self):
        if not (self.trecho and self.trecho.strip()):
            raise ValueError(f"{self.documento}: critério do título sem trecho literal do dispositivo")
        return self


class ParcelaFicha(BaseModel):
    numero: int
    vencimento: str
    valor_fixo: str | None = None
    """Só para reforçadas/intermediárias; vazio = regular."""


class Contrato(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data_liberacao: str
    valor_financiado: str
    taxa_mensal: str
    taxa_anual: str | None = None
    regime: Literal["composto", "simples"]
    convencao: Literal["meses_civis", "meses_30", "dias_base_360", "dias_base_365"]
    parcela_regular: str
    parcelas: list[ParcelaFicha]
    fonte: Fonte


class ItemExcluidoFicha(BaseModel):
    descricao: str
    valor: str
    financiado: bool
    data_pagamento: str | None = None
    fonte: FonteTitulo


class Revisao(BaseModel):
    model_config = ConfigDict(extra="forbid")
    taxa_mensal: str
    """Taxa fixada no título (ex.: média BACEN da modalidade no mês da contratação)."""
    taxa_anual: str | None = None
    regime: Literal["composto", "simples"]
    convencao: Literal["meses_civis", "meses_30", "dias_base_360", "dias_base_365"]
    tratamento_reforcadas: Literal["manter_valor", "proporcional"] | None = None
    itens_excluidos: list[ItemExcluidoFicha] = Field(default_factory=list)
    fonte: FonteTitulo


class Restituicao(BaseModel):
    modalidade: Literal["simples", "dobro", "dobro_a_partir_de"]
    data_corte: str | None = None
    fonte: FonteTitulo


class PagamentoFicha(BaseModel):
    numero: int
    data: str
    valor: str
    """Valor efetivamente pago, INCLUINDO encargos de atraso, se houver."""
    encargos: str = "0"
    antecipada_com_desconto: bool = False
    fonte: Fonte


class EncargosContrato(BaseModel):
    multa: str | None = None
    juros_mora_mensal: str | None = None
    contagem: Literal["dias_30", "meses_civis"]
    fonte: Fonte


class DescaracterizacaoFicha(BaseModel):
    componentes_afastados: list[Literal["multa", "juros_mora", "juros_remuneratorios_mora", "comissao_permanencia"]]
    desde: str | None = None
    ate: str | None = None
    fonte: FonteTitulo


class JurosFase(BaseModel):
    tipo: Literal["percentual_fixo", "serie", "serie_menos_serie"]
    percentual_mensal: str | None = None
    inicio: str | None = None
    """Termo inicial (ex.: vencimento da 1ª parcela). Vazio = início da fase."""
    contagem: Literal["dias_30", "meses_civis"] | None = None
    serie: str | None = None
    serie_deduzir: str | None = None
    """serie_menos_serie: ex. juros legais do art. 406 do CC (Lei 14.905/24) = SELIC − IPCA."""
    piso_zero: bool | None = None
    """serie_menos_serie: mês com resultado negativo vale zero (art. 406, §3º, CC)."""


class FaseFicha(BaseModel):
    fim: str
    """Data (DD/MM/AAAA) ou 'data_base'."""
    descricao: str
    correcao: str | None
    """Série de correção (ex.: INPC) ou null (sem correção — ex.: fase da Selic)."""
    juros: JurosFase | None = None
    incluir_mes_inicial: bool
    incluir_mes_final: bool
    acumulacao_juros: Literal["soma", "produto"]
    juros_desde_antes_do_valor: bool = False


class Atualizacao(BaseModel):
    fases: list[FaseFicha]
    fonte: FonteTitulo


class VerbaFicha(BaseModel):
    descricao: str
    valor_fixo: str | None = None
    percentual: str | None = None
    valor_base: str | None = None
    descricao_base: str | None = None
    data_base_verba: str
    """Data a partir da qual a verba é atualizada (ex.: data do arbitramento — Súmula 362 —, do evento…)."""
    atualizacao: Atualizacao | None = None
    fonte: FonteTitulo


class HonorariosFicha(BaseModel):
    base: Literal["valor da condenação", "proveito econômico", "valor atualizado da causa", "valor fixo"]
    percentual: str | None = None
    valor_fixo: str | None = None
    valor_base: str | None = None
    """Só quando a base não é a condenação apurada aqui (ex.: valor atualizado da causa)."""
    cota_devedor: str = "1"
    devedor: str
    fonte: FonteTitulo


class Ficha(BaseModel):
    model_config = ConfigDict(extra="forbid")
    caso: str
    responsavel: str
    data_base: str
    arredondamento: str
    contrato: Contrato | None = None
    """Vazio só quando não há revisão (ex.: cumprimento apenas de honorários ou de verba fixa)."""
    revisao: Revisao | None = None
    restituicao: Restituicao | None = None
    pagamentos: list[PagamentoFicha] = Field(default_factory=list)
    encargos_contrato: EncargosContrato | None = None
    descaracterizacao: DescaracterizacaoFicha | None = None
    atualizacao: Atualizacao | None = None
    verbas: list[VerbaFicha] = Field(default_factory=list)
    honorarios: HonorariosFicha | None = None

    @field_validator("responsavel")
    @classmethod
    def _resp(cls, v):
        if not v.strip():
            raise ValueError("informe a responsável pelo cálculo")
        return v

    @model_validator(mode="after")
    def _coerencia(self):
        if self.revisao and not self.contrato:
            raise ValueError("revisão exige os dados do contrato")
        if not self.contrato and not (self.verbas or self.honorarios):
            raise ValueError("nada a calcular: informe contrato/revisão, verbas ou honorários")
        if self.pagamentos and (not self.revisao or not self.restituicao or not self.atualizacao):
            raise ValueError("há pagamentos: preencha revisao, restituicao e atualizacao (AP03)")
        return self


class Resultado(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    ficha: Ficha
    executado_em: datetime
    parcela_original: Decimal | None = None
    ap01: ResultadoEvolucao | None = None
    revisao: ResultadoRevisao | None = None
    ap02: ResultadoEvolucao | None = None
    ap03: ResultadoDiferencas | None = None
    verbas: list[tuple[str, Decimal, Decimal]] = Field(default_factory=list)
    """(descrição, valor original, valor atualizado)"""
    condenacao: Decimal
    honorarios: Decimal | None = None
    total: Decimal
    memoria: Memoria


def _taxa(mensal: str, anual: str | None, regime: str, conv: str) -> Taxa:
    return Taxa(_pct(mensal), Regime(regime), ConvencaoTempo(conv), _pct(anual) if anual else None)


def _fases(at: Atualizacao, data_base: date) -> list[Fase]:
    origem = at.fonte.origem()
    fases, inicio = [], INICIO_REMOTO
    for f in at.fases:
        fim = data_base if f.fim == "data_base" else _d(f.fim)
        juros = []
        if f.juros:
            j = f.juros
            ini = _d(j.inicio) if j.inicio else inicio
            if j.tipo == "percentual_fixo":
                if not (j.percentual_mensal and j.contagem):
                    raise ValueError(f"fase '{f.descricao}': juros fixos exigem percentual_mensal e contagem")
                juros.append(CriterioJuros(inicio=ini, fim=fim, tipo=TipoJuros.PERCENTUAL_FIXO,
                                           percentual_mensal=_pct(j.percentual_mensal),
                                           contagem=ContagemJuros(j.contagem), origem=origem))
            else:
                if not j.serie:
                    raise ValueError(f"fase '{f.descricao}': juros por série exigem o nome da série")
                juros.append(CriterioJuros(inicio=ini, fim=fim, tipo=TipoJuros(j.tipo), serie=j.serie,
                                           serie_deduzir=j.serie_deduzir, piso_zero=j.piso_zero, origem=origem))
        params = ParametrosAtualizacao(
            correcao=[CriterioCorrecao(inicio=INICIO_REMOTO, fim=fim, serie=f.correcao, origem=origem)],
            juros=juros,
            competencias=ConvencaoCompetencias(incluir_mes_inicial=f.incluir_mes_inicial,
                                               incluir_mes_final=f.incluir_mes_final),
            acumulacao_juros=Acumulacao(f.acumulacao_juros),
            juros_desde_antes_do_valor=f.juros_desde_antes_do_valor,
            origem_juros_antes_do_valor=origem if f.juros_desde_antes_do_valor else None)
        fases.append(Fase(fim=fim, descricao=f.descricao, parametros=params, origem=origem))
        inicio = fim
    if fases[-1].fim != data_base:
        raise ValueError("a última fase da atualização deve terminar na data-base ('data_base')")
    return fases


def calcular(ficha: Ficha, series: dict[str, SerieMensal]) -> Resultado:
    pol = PoliticaArredondamento.de_texto(ficha.arredondamento)
    data_base = _d(ficha.data_base)
    mem = Memoria()
    res: dict = dict(ficha=ficha, executado_em=datetime.now().replace(microsecond=0), memoria=mem)
    c = ficha.contrato
    if c:
        lib, vf = _d(c.data_liberacao), _dec(c.valor_financiado)
        parcelas = [ParcelaPrevista(numero=p.numero, vencimento=_d(p.vencimento),
                                    valor_fixo=_dec(p.valor_fixo) if p.valor_fixo else None) for p in c.parcelas]
        regular = _dec(c.parcela_regular)
        taxa_c = _taxa(c.taxa_mensal, c.taxa_anual, c.regime, c.convencao)
        res["parcela_original"] = regular
        res["ap01"] = tabela_contratual(vf, lib, parcelas, regular, taxa_c, pol, mem, "AP01", [c.fonte.origem()])
    condenacao = ZERO

    if ficha.revisao:
        r = ficha.revisao
        taxa_r = _taxa(r.taxa_mensal, r.taxa_anual, r.regime, r.convencao)
        itens = [ItemExcluido(descricao=i.descricao, valor=_dec(i.valor), financiado=i.financiado,
                              data_pagamento=_d(i.data_pagamento) if i.data_pagamento else None,
                              origem_titulo=i.fonte.origem()) for i in r.itens_excluidos]
        params = ParametrosRevisao(taxa_revisada=taxa_r, origem_taxa=r.fonte.origem(), itens_excluidos=itens,
                                   tratamento_reforcadas=TratamentoReforcadas(r.tratamento_reforcadas)
                                   if r.tratamento_reforcadas else None)
        rev = recalcular_contrato(vf, lib, parcelas, regular, params, pol, mem)
        ap02 = tabela_contratual(rev.valor_financiado_revisado, lib, parcelas, rev.parcela_regular_revisada, taxa_r,
                                 pol, mem, "AP02", [r.fonte.origem()])
        res.update(revisao=rev, ap02=ap02)
    if ficha.revisao and ficha.pagamentos:
        r, rev = ficha.revisao, res["revisao"]
        taxa_r = _taxa(r.taxa_mensal, r.taxa_anual, r.regime, r.convencao)
        itens = [i for i in params.itens_excluidos]
        venc = {p.numero: p.vencimento for p in parcelas}
        pags = []
        for p in ficha.pagamentos:
            if p.numero not in venc:
                raise ValueError(f"pagamento da parcela {p.numero} fora do cronograma")
            enc = _dec(p.encargos)
            pags.append(PagamentoEfetivo(numero_parcela=p.numero, vencimento=venc[p.numero], data_pagamento=_d(p.data),
                                         valor_parcela_pago=_dec(p.valor) - enc, encargos_pagos=enc,
                                         antecipada_com_desconto=p.antecipada_com_desconto, origem=p.fonte.origem()))
        rs = ficha.restituicao
        regra = RegraRestituicao(modalidade=Modalidade(rs.modalidade),
                                 data_corte=_d(rs.data_corte) if rs.data_corte else None,
                                 origem_titulo=rs.fonte.origem())
        enc = None
        if ficha.encargos_contrato:
            e = ficha.encargos_contrato
            enc = ParametrosEncargos(multa=_pct(e.multa) if e.multa else None,
                                     juros_mora_mensal=_pct(e.juros_mora_mensal) if e.juros_mora_mensal else None,
                                     contagem=ContagemAtraso(e.contagem), origem=e.fonte.origem())
        desc = None
        if ficha.descaracterizacao:
            dc = ficha.descaracterizacao
            desc = Descaracterizacao(componentes_afastados=frozenset(Componente(x) for x in dc.componentes_afastados),
                                     desde=_d(dc.desde) if dc.desde else None, ate=_d(dc.ate) if dc.ate else None,
                                     origem_titulo=dc.fonte.origem())
        avulsos = [i for i in itens if not i.financiado]
        ap03 = demonstrativo_diferencas(pags, rev, regra, None, series, data_base, pol, mem, enc, desc, avulsos,
                                        fases=_fases(ficha.atualizacao, data_base), taxa_desconto=taxa_r)
        res["ap03"] = ap03
        condenacao += ap03.total_atualizado

    verbas = []
    for v in ficha.verbas:
        db = _d(v.data_base_verba)
        verba = VerbaAutorizada(descricao=v.descricao, data_base=db,
                                valor_fixo=_dec(v.valor_fixo) if v.valor_fixo else None,
                                percentual=_pct(v.percentual) if v.percentual else None,
                                valor_base=_dec(v.valor_base) if v.valor_base else None,
                                descricao_base=v.descricao_base, origem_titulo=v.fonte.origem())
        original = calcular_verba(verba, pol, mem)
        atual = original
        if v.atualizacao:
            atual = atualizar_por_fases(original, db, _fases(v.atualizacao, data_base), series, pol, mem,
                                        v.descricao).total
        verbas.append((v.descricao, original, atual))
        condenacao += atual
    res["verbas"] = verbas

    hon = None
    if ficha.honorarios:
        h = ficha.honorarios
        ph = ParametrosHonorarios(base=BaseHonorarios(h.base), percentual=_pct(h.percentual) if h.percentual else None,
                                  valor_fixo=_dec(h.valor_fixo) if h.valor_fixo else None,
                                  cota_devedor=_dec(h.cota_devedor), devedor=h.devedor, origem_titulo=h.fonte.origem())
        if h.base == "valor da condenação":
            base, rot = condenacao, "condenação apurada nesta memória"
        elif h.base == "valor fixo":
            base, rot = None, ""
        else:
            if not h.valor_base:
                raise ValueError(f"honorários sobre {h.base}: informe valor_base (já atualizado)")
            base, rot = _dec(h.valor_base), h.base
        hon = calcular_honorarios(ph, base, pol, mem, rot)
    total = arredondar(condenacao + (hon or ZERO), pol)
    return Resultado(**res, condenacao=arredondar(condenacao, pol), honorarios=hon, total=total)


def carregar_ficha(arq: Path) -> Ficha:
    return Ficha.model_validate(json.loads(arq.read_text(encoding="utf-8")))


def carregar_series_csv(pasta: Path) -> dict[str, SerieMensal]:
    """indices/<NOME>.csv (competência;variação %) + <NOME>.fonte.txt. SELIC* embute correção."""
    from .indices import serie_de_csv
    out = {}
    for csv in sorted(pasta.glob("*.csv")):
        fonte = csv.with_suffix(".fonte.txt")
        if not fonte.exists():
            raise ValueError(f"{csv.name}: falta {fonte.name} com a fonte oficial da série")
        s = serie_de_csv(csv.stem.upper(), csv.read_bytes(), fonte.read_text(encoding="utf-8").strip(),
                         embute_correcao=csv.stem.upper().startswith("SELIC"))
        out[s.nome] = s
    return out


# --- saída ---------------------------------------------------------------------------------------

def _brl(v: Decimal) -> str:
    s = f"{v:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def planilha(r: Resultado, destino: Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    neg, fundo = Font(bold=True), PatternFill("solid", fgColor="DDE4EE")

    def aba(nome, cab, linhas):
        ws = wb.create_sheet(nome)
        ws.append(cab)
        for c in ws[1]:
            c.font, c.fill = neg, fundo
        for l in linhas:
            ws.append([float(x) if isinstance(x, Decimal) else x for x in l])
        for i, _ in enumerate(cab):
            ws.column_dimensions[chr(65 + i)].width = 18
        return ws

    ws = wb.active
    ws.title = "Resumo"
    for l in resumo_linhas(r):
        ws.append(l)
    ws.column_dimensions["A"].width = 60
    ws.column_dimensions["B"].width = 22

    def evolucao(nome, ev):
        aba(nome, ["Nº", "Data", "Prestação", "Juros", "Amortização", "Saldo"],
            [[l.numero_parcela, l.data.strftime("%d/%m/%Y"), l.pagamento, l.juros_periodo, l.amortizacao, l.saldo]
             for l in ev.linhas])
    if r.ap01:
        evolucao("AP01", r.ap01)
    if r.ap02:
        evolucao("AP02", r.ap02)
    if r.ap03:
        aba("AP03", ["Descrição", "Pagamento", "Pago", "Devido", "Diferença", "A restituir", "Corrigido",
                     "Juros/Selic", "Atualizado"],
            [[l.descricao, l.data_pagamento.strftime("%d/%m/%Y"), l.pago, l.devido, l.diferenca, l.a_restituir,
              l.corrigido, l.juros, l.atualizado] for l in r.ap03.linhas]
            + [["Pagas a menor (sem atualização — ver ressalvas)", "", "", "", "", "", "", "", ""]]
            + [[l.descricao, l.data_pagamento.strftime("%d/%m/%Y"), l.pago, l.devido, l.diferenca, 0, 0, 0, 0]
               for l in r.ap03.pagos_a_menor])
    if r.verbas:
        aba("Verbas", ["Verba", "Valor original", "Valor atualizado"], [list(v) for v in r.verbas])
    aba("Memória", ["Etapa", "Descrição", "Fórmula", "Resultado", "Origem"],
        [[p.etapa, p.descricao, p.formula, str(p.resultado), "; ".join(p.origem)] for p in r.memoria.passos])
    aba("Ressalvas", ["Ressalva"], [[x] for x in ressalvas_agrupadas(r)])
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino


def resumo_linhas(r: Resultado) -> list[list]:
    f = r.ficha
    L = [["MEMÓRIA DE CÁLCULO — CUMPRIMENTO DE SENTENÇA", ""], ["Caso", f.caso],
         ["Data-base", f.data_base], ["Elaborado por", f.responsavel],
         ["Gerado em", r.executado_em.strftime("%d/%m/%Y %H:%M")], ["", ""]]
    if r.parcela_original is not None:
        L.append(["Prestação regular cobrada", _brl(r.parcela_original)])
    if r.revisao:
        L += [["Prestação regular revisada (título)", _brl(r.revisao.parcela_regular_revisada)],
              ["Valor financiado revisado", _brl(r.revisao.valor_financiado_revisado)]]
    if r.ap03:
        L += [["Total pago", _brl(r.ap03.total_pago)], ["Total devido (revisado)", _brl(r.ap03.total_devido)],
              ["Indébito nominal a restituir", _brl(r.ap03.total_a_restituir_nominal)],
              ["Indébito atualizado (AP03)", _brl(r.ap03.total_atualizado)]]
    for d, o, a in r.verbas:
        L.append([f"{d} (original {_brl(o)})", _brl(a)])
    L.append(["CONDENAÇÃO ATUALIZADA", _brl(r.condenacao)])
    if r.honorarios is not None:
        L.append([f"Honorários de sucumbência ({f.honorarios.base})", _brl(r.honorarios)])
    L += [["TOTAL DEVIDO (sem multa e honorários do art. 523, §1º, CPC)", _brl(r.total)], ["", ""],
          ["Critérios e fontes", ""]]
    for v in f.verbas:
        L.append([v.descricao, f"{v.fonte.documento}, {v.fonte.localizacao or ''} — {v.fonte.trecho or ''}".strip(" ,—")])
        if v.atualizacao:
            fa = v.atualizacao.fonte
            L.append([f"Atualização — {v.descricao}", f"{fa.documento}, {fa.localizacao or ''} — {fa.trecho or ''}".strip(" ,—")])
    for nome, fonte in (("Contrato", f.contrato.fonte if f.contrato else None), ("Revisão", f.revisao.fonte if f.revisao else None),
                        ("Restituição", f.restituicao.fonte if f.restituicao else None),
                        ("Atualização", f.atualizacao.fonte if f.atualizacao else None),
                        ("Honorários", f.honorarios.fonte if f.honorarios else None)):
        if fonte:
            L.append([nome, f"{fonte.documento}, {fonte.localizacao or ''} — {fonte.trecho or ''}".strip(" ,—")])
    return L


def markdown(r: Resultado) -> str:
    L = ["# " + resumo_linhas(r)[0][0], ""]
    L += [f"- **{a}**: {b}" for a, b in resumo_linhas(r)[1:] if a]
    if r.memoria.ressalvas:
        L += ["", "## Ressalvas", ""] + [f"- {x}" for x in ressalvas_agrupadas(r)]
    return "\n".join(L) + "\n"


def ressalvas_agrupadas(r: Resultado) -> list[str]:
    """Ressalvas repetidas por parcela (mesmo texto, só mudam nº e datas) viram uma linha com a contagem."""
    import re
    grupos: dict[tuple[str, str], list[str]] = {}
    for x in r.memoria.ressalvas:
        chave = re.sub(r"\d{2}/\d{2}/\d{4}", "DD/MM/AAAA", re.sub(r"Parcela \d+", "Parcela N", x.texto))
        grupos.setdefault((x.tipo.value, chave), []).append(x.texto)
    out = []
    for (tipo, chave), textos in grupos.items():
        out.append(f"[{tipo}] {textos[0]}" if len(textos) == 1 else f"[{tipo}] ({len(textos)} parcelas) {chave}")
    return out
