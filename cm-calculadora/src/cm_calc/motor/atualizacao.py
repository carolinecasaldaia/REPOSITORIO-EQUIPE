"""Correção monetária e juros (moratórios ou legais) por períodos.

Fórmula geral (declarada no relatório):

    valor corrigido = valor × Π (1 + variação do índice no mês)
    juros           = valor corrigido × (Σ percentuais de juros)      [acumulação SOMA]
                    = valor corrigido × (Π (1 + percentual) − 1)       [acumulação PRODUTO]
    total           = valor corrigido + juros

Critérios que NÃO têm padrão e precisam vir do título/da advogada:
- índice de correção por período (ou nenhum);
- termo inicial dos juros, tipo e taxa por período;
- inclusão do mês inicial/final na correção (``ConvencaoCompetencias``);
- forma de acumulação dos juros.

Índices são recebidos como séries mensais (fração, ex. 0.0042 = 0,42%).
Mês sem valor na série interrompe o cálculo (``SerieIncompleta``): o motor
não estima nem interpola índices.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from .auditoria import Memoria, Origem, TipoRessalva
from .datas import competencias_entre, dias_corridos, meses_civis_e_dias
from .numeros import UM, ZERO, D, PoliticaArredondamento, arredondar

Competencia = tuple[int, int]


class SerieIncompleta(ValueError):
    pass


class CriterioInvalido(ValueError):
    pass


class SerieMensal(BaseModel):
    model_config = ConfigDict(frozen=True)

    nome: str
    valores: dict[str, Decimal]
    """'AAAA-MM' -> variação/taxa do mês, em fração."""
    fonte: str
    embute_correcao: bool = False
    """True para taxas que já incluem correção monetária (ex.: Selic)."""

    def valor(self, comp: Competencia) -> Decimal:
        chave = f"{comp[0]:04d}-{comp[1]:02d}"
        if chave not in self.valores:
            raise SerieIncompleta(f"série {self.nome} sem valor para {chave} (fonte: {self.fonte})")
        return self.valores[chave]


class ConvencaoCompetencias(BaseModel):
    model_config = ConfigDict(frozen=True)

    incluir_mes_inicial: bool
    incluir_mes_final: bool


class CriterioCorrecao(BaseModel):
    """Índice aplicável no intervalo [inicio, fim). ``serie=None``: sem correção."""

    model_config = ConfigDict(frozen=True)

    inicio: date
    fim: date
    serie: str | None
    origem: Origem


class TipoJuros(str, Enum):
    PERCENTUAL_FIXO = "percentual_fixo"          # ex.: 1% a.m.
    SERIE = "serie"                              # ex.: taxa mensal de série oficial
    SERIE_MENOS_SERIE = "serie_menos_serie"      # ex.: taxa A deduzida do índice B


class ContagemJuros(str, Enum):
    DIAS_30 = "dias_30"
    MESES_CIVIS = "meses_civis"


class CriterioJuros(BaseModel):
    """Juros no intervalo [inicio, fim)."""

    model_config = ConfigDict(frozen=True)

    inicio: date
    fim: date
    tipo: TipoJuros
    percentual_mensal: Decimal | None = None
    contagem: ContagemJuros | None = None
    serie: str | None = None
    serie_deduzir: str | None = None
    piso_zero: bool | None = None
    origem: Origem

    @model_validator(mode="after")
    def _coerencia(self):
        if self.fim <= self.inicio:
            raise ValueError("critério de juros com período vazio")
        if self.tipo is TipoJuros.PERCENTUAL_FIXO and (self.percentual_mensal is None or self.contagem is None):
            raise ValueError("percentual_fixo exige percentual_mensal e contagem")
        if self.tipo in (TipoJuros.SERIE, TipoJuros.SERIE_MENOS_SERIE) and self.serie is None:
            raise ValueError("juros por série exige o nome da série")
        if self.tipo is TipoJuros.SERIE_MENOS_SERIE and (self.serie_deduzir is None or self.piso_zero is None):
            raise ValueError("serie_menos_serie exige serie_deduzir e definição de piso_zero")
        return self


class Acumulacao(str, Enum):
    SOMA = "soma"           # juros simples: percentuais somados
    PRODUTO = "produto"     # juros compostos: fatores multiplicados


class ParametrosAtualizacao(BaseModel):
    model_config = ConfigDict(frozen=True)

    correcao: list[CriterioCorrecao]
    juros: list[CriterioJuros]
    competencias: ConvencaoCompetencias
    acumulacao_juros: Acumulacao
    juros_desde_antes_do_valor: bool = False
    """Juros contados desde o termo inicial do critério MESMO antes da data do valor (pagamento).
    Só quando o título determinar; exige ``origem_juros_antes_do_valor`` com o trecho."""
    origem_juros_antes_do_valor: Origem | None = None

    @model_validator(mode="after")
    def _juros_antes(self):
        if self.juros_desde_antes_do_valor:
            o = self.origem_juros_antes_do_valor
            if o is None or not (o.trecho and o.trecho.strip()):
                raise ValueError("juros anteriores à data do valor exigem o trecho do título que os determina")
        return self


class ResultadoAtualizacao(BaseModel):
    model_config = ConfigDict(frozen=True)

    valor_original: Decimal
    data_valor: date
    data_final: date
    fator_correcao: Decimal
    valor_corrigido: Decimal
    percentual_juros: Decimal
    juros: Decimal
    total: Decimal
    total_exato: Decimal | None = None
    """corrigido + juros sem arredondamento (base de consolidação em precisão integral)."""


class Fase(BaseModel):
    """Trecho da atualização com critérios próprios. Ao fim da fase, o total (corrigido + juros)
    é CONSOLIDADO e passa a ser a base da fase seguinte (ex.: INPC + mora até a citação; depois
    Selic sobre o subtotal). Usar só quando o título determinar a consolidação."""

    model_config = ConfigDict(frozen=True)

    fim: date
    descricao: str
    parametros: ParametrosAtualizacao
    origem: Origem


class ResultadoFases(BaseModel):
    model_config = ConfigDict(frozen=True)

    fases: list[ResultadoAtualizacao]
    total: Decimal
    total_exato: Decimal


def atualizar_por_fases(valor: Decimal, data_valor: date, fases: list[Fase], series: dict[str, "SerieMensal"],
                        politica: PoliticaArredondamento, memoria: Memoria | None = None,
                        rotulo: str = "") -> ResultadoFases:
    if not fases:
        raise CriterioInvalido("informe ao menos uma fase")
    if any(b.fim <= a.fim for a, b in zip(fases, fases[1:])):
        raise CriterioInvalido("fases fora de ordem cronológica")
    base, inicio, resultados = valor, data_valor, []
    for f in fases:
        r = atualizar(base, inicio, f.fim, f.parametros, series, politica, memoria, f"{rotulo} — {f.descricao}".strip(" —"))
        resultados.append(r)
        # consolidação: em precisão integral segue o valor exato; senão, o total arredondado da fase
        base = r.total_exato if not politica.arredondar_cada_parcela else r.total
        inicio = f.fim
    total = arredondar(base, politica)
    if memoria is not None:
        memoria.registrar(
            "atualizacao", f"Atualização em fases {rotulo}".strip(),
            "base(fase n+1) = corrigido(fase n) + juros(fase n)  — consolidação ao fim de cada fase",
            {"valor": valor, "fases": [f"{f.descricao} até {f.fim:%d/%m/%Y}" for f in fases],
             "arredondamento": politica.descricao()},
            {"total": total, "total_exato": base}, [f.origem for f in fases], fases[-1].fim)
    return ResultadoFases(fases=resultados, total=total, total_exato=base)


def _validar_cobertura(periodos: list[tuple[date, date]], inicio: date, fim: date, nome: str) -> None:
    periodos = sorted(periodos)
    if not periodos:
        raise CriterioInvalido(f"nenhum critério de {nome} informado")
    if periodos[0][0] > inicio or periodos[-1][1] < fim:
        raise CriterioInvalido(
            f"critérios de {nome} não cobrem {inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"
        )
    for (a1, b1), (a2, b2) in zip(periodos, periodos[1:]):
        if a2 != b1:
            raise CriterioInvalido(f"critérios de {nome} com lacuna ou sobreposição em {b1:%d/%m/%Y}")


def _competencias(inicio: date, fim: date, conv: ConvencaoCompetencias) -> list[Competencia]:
    comps = competencias_entre((inicio.year, inicio.month), (fim.year, fim.month))
    if comps and not conv.incluir_mes_inicial:
        comps = comps[1:]
    if comps and not conv.incluir_mes_final:
        comps = comps[:-1]
    return comps


def _data_representativa(comp: Competencia, piso: date) -> date:
    """Mês é atribuído ao critério vigente no seu 1º dia (ou na data inicial, se posterior)."""
    return max(date(comp[0], comp[1], 1), piso)


def _vigente(criterios, d: date):
    for c in criterios:
        if c.inicio <= d < c.fim:
            return c
    return criterios[-1] if d >= criterios[-1].fim else None


def atualizar(
    valor: Decimal,
    data_valor: date,
    data_final: date,
    params: ParametrosAtualizacao,
    series: dict[str, SerieMensal],
    politica: PoliticaArredondamento,
    memoria: Memoria | None = None,
    rotulo: str = "",
) -> ResultadoAtualizacao:
    if data_final < data_valor:
        raise CriterioInvalido("data final anterior à data do valor")

    # --- correção monetária -------------------------------------------------
    _validar_cobertura([(c.inicio, c.fim) for c in params.correcao], data_valor, data_final, "correção")
    correcao = sorted(params.correcao, key=lambda c: c.inicio)
    comps = _competencias(data_valor, data_final, params.competencias)
    fator = UM
    meses_corrigidos: list[str] = []
    criterio_correcao_mes: dict[Competencia, CriterioCorrecao] = {}
    for comp in comps:
        crit = _vigente(correcao, _data_representativa(comp, data_valor))
        criterio_correcao_mes[comp] = crit
        if crit is None or crit.serie is None:
            continue
        fator *= UM + _serie(series, crit.serie).valor(comp)
        meses_corrigidos.append(f"{comp[0]:04d}-{comp[1]:02d}:{crit.serie}")
    corrigido = valor * fator

    # --- juros ---------------------------------------------------------------
    juros_crit = sorted(params.juros, key=lambda c: c.inicio)
    pct_total = ZERO
    fator_juros = UM
    detalhes_juros: list[str] = []
    if juros_crit:
        # Por padrão, juros não correm antes da data do valor (pagamento). Só quando o TÍTULO determina
        # termo inicial anterior (ex.: "desde o vencimento da 1ª parcela" para todas), com o trecho citado.
        antes = params.juros_desde_antes_do_valor
        piso = juros_crit[0].inicio if antes else max(juros_crit[0].inicio, data_valor)
        _validar_cobertura([(c.inicio, c.fim) for c in juros_crit], piso, data_final, "juros")
        if memoria is not None and juros_crit[0].inicio < data_valor:
            if antes:
                memoria.ressalvar(TipoRessalva.PREMISSA,
                                  f"{rotulo}: juros contados desde {juros_crit[0].inicio:%d/%m/%Y}, ANTES da data do valor "
                                  f"({data_valor:%d/%m/%Y}), por determinação do título "
                                  f"({params.origem_juros_antes_do_valor}).")
            else:
                memoria.ressalvar(TipoRessalva.PREMISSA,
                                  f"{rotulo}: juros iniciados na data do valor ({data_valor:%d/%m/%Y}), "
                                  "posterior ao termo inicial do critério.")
        inicio_juros = piso
        # Critérios por série: cada competência pertence a um único critério
        # (o vigente no 1º dia do mês), evitando contar o mês de transição duas vezes.
        por_criterio: dict[int, list[Decimal]] = {id(c): [] for c in juros_crit}
        for comp in _competencias(inicio_juros, data_final, params.competencias):
            crit = _vigente(juros_crit, _data_representativa(comp, inicio_juros))
            if crit is None or crit.tipo is TipoJuros.PERCENTUAL_FIXO:
                continue
            por_criterio[id(crit)].append(
                _taxa_serie_mes(crit, comp, series, criterio_correcao_mes))
        for crit in juros_crit:
            a, b = max(crit.inicio, piso), min(crit.fim, data_final)
            if b <= a:
                continue
            if crit.tipo is TipoJuros.PERCENTUAL_FIXO:
                parcelas_pct = [_percentual_fixo(crit, a, b)]
            else:
                parcelas_pct = por_criterio[id(crit)]
            for p in parcelas_pct:
                pct_total += p
                fator_juros *= UM + p
            detalhes_juros.append(f"{a:%d/%m/%Y}–{b:%d/%m/%Y} {crit.tipo.value}: {sum(parcelas_pct, ZERO)}")

    if params.acumulacao_juros is Acumulacao.PRODUTO:
        pct_efetivo = fator_juros - UM
    else:
        pct_efetivo = pct_total
    juros = corrigido * pct_efetivo

    corrigido_r = arredondar(corrigido, politica)
    juros_r = arredondar(juros, politica)
    res = ResultadoAtualizacao(
        valor_original=valor, data_valor=data_valor, data_final=data_final,
        fator_correcao=fator, valor_corrigido=corrigido_r,
        percentual_juros=pct_efetivo, juros=juros_r, total=corrigido_r + juros_r,
        total_exato=corrigido + juros,
    )
    if memoria is not None:
        memoria.registrar(
            "atualizacao",
            f"Atualização {rotulo} de {data_valor:%d/%m/%Y} até {data_final:%d/%m/%Y}".replace("  ", " "),
            "corrigido = V × Π(1+índice); juros = corrigido × Σ% (soma) ou × (Π(1+%) − 1) (produto)",
            {"valor": valor, "meses_corrigidos": meses_corrigidos,
             "convencao_meses": params.competencias.model_dump(),
             "juros": detalhes_juros, "acumulacao": params.acumulacao_juros.value,
             "arredondamento": politica.descricao()},
            {"fator_correcao": fator, "corrigido": corrigido_r,
             "percentual_juros": pct_efetivo, "juros": juros_r, "total": res.total},
            [c.origem for c in params.correcao] + [c.origem for c in params.juros],
            data_final,
        )
    return res


def _serie(series: dict[str, SerieMensal], nome: str) -> SerieMensal:
    if nome not in series:
        raise SerieIncompleta(f"série {nome} não carregada")
    return series[nome]


def _percentual_fixo(crit: CriterioJuros, a: date, b: date) -> Decimal:
    if crit.contagem is ContagemJuros.DIAS_30:
        t = D(dias_corridos(a, b)) / D(30)
    else:
        m, d = meses_civis_e_dias(a, b)
        t = D(m) + D(d) / D(30)
    return crit.percentual_mensal * t


def _taxa_serie_mes(crit: CriterioJuros, comp: Competencia, series: dict[str, SerieMensal],
                    correcao_mes: dict[Competencia, CriterioCorrecao]) -> Decimal:
    principal = _serie(series, crit.serie)
    # Selic − IPCA (juros legais do art. 406 do CC) já desconta a correção: pode conviver com o IPCA.
    if principal.embute_correcao and crit.tipo is not TipoJuros.SERIE_MENOS_SERIE:
        cc = correcao_mes.get(comp)
        if cc is not None and cc.serie is not None:
            raise CriterioInvalido(
                f"{comp[0]:04d}-{comp[1]:02d}: série {principal.nome} já embute correção e "
                f"foi cumulada com o índice {cc.serie}. Ajuste os critérios."
            )
    v = principal.valor(comp)
    if crit.tipo is TipoJuros.SERIE_MENOS_SERIE:
        v = v - _serie(series, crit.serie_deduzir).valor(comp)
        if crit.piso_zero and v < ZERO:
            v = ZERO
    return v
