"""Comparação parecer × motor, consistência interna do parecer e cenários de diagnóstico.

Classificação de cada valor:
- idêntico            : diferença zero;
- arredondamento      : |diferença| ≤ R$ 0,01;
- arredondamento acumulado: em colunas de saldo/valores acumulados, |diferença|
                        ≤ R$ 0,01 × nº de períodos já decorridos;
- divergente          : acima disso — recebe justificativa técnica diagnóstica.

A justificativa distingue o que foi COMPROVADO (um cenário alternativo
reproduz o parecer) do que é HIPÓTESE (indício numérico) e do que NÃO foi
explicado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from ..motor.evolucao import ResultadoEvolucao
from ..motor.numeros import UM, ZERO, D, ModoArredondamento, PoliticaArredondamento, potencia
from ..motor.taxas import ConvencaoTempo, Regime
from .ficha import FichaCaso
from .modelos import Cenario, Classe, Comparacao, Inconsistencia, LinhaPericial, Parecer, TabelaPericial
from .reconstrucao import Reconstrucao, reconstruir

CENT = D("0.01")
ACUMULAM = {"saldo", "saldo_anterior", "corrigido", "total"}
MAPA_EVOLUCAO = {"saldo_anterior": "saldo_anterior", "juros": "juros_periodo", "amortizacao": "amortizacao",
                 "prestacao": "pagamento", "saldo": "saldo"}
MAPA_AP03 = {"pago": "pago", "devido": "devido", "diferenca": "diferenca", "restituir": "a_restituir",
             "corrigido": "corrigido", "juros_mora": "juros", "total": "atualizado"}


def valor_motor_evolucao(lm, col: str) -> Decimal:
    """Valor do motor na convenção usual dos pareceres: o pagamento acima da dívida aparece como saldo
    negativo e integra a amortização (o motor o segrega como 'excedente'; o cálculo é o mesmo)."""
    if col == "saldo":
        return lm.saldo - lm.excedente
    if col == "amortizacao":
        return lm.amortizacao + lm.excedente
    return getattr(lm, MAPA_EVOLUCAO[col])


def _classe(col: str, d: Decimal, ordem: int) -> Classe:
    a = abs(d)
    if a == 0:
        return Classe.IDENTICO
    if a <= CENT:
        return Classe.CENTAVO
    if col in ACUMULAM and a <= CENT * max(ordem, 1):
        return Classe.ACUMULADO
    return Classe.DIVERGENTE


def _pct(d: Decimal, base: Decimal | None) -> Decimal | None:
    return None if not base else (d / base * 100).quantize(D("0.0001"))


# --- Consistência interna do parecer -----------------------------------------------------------

def consistencia_interna(t: TabelaPericial) -> list[Inconsistencia]:
    out: list[Inconsistencia] = []

    def inc(n, txt):
        out.append(Inconsistencia(apendice=t.apendice, numero=n, descricao=txt))

    anterior: LinhaPericial | None = None
    for l in t.linhas:
        v = l.valores
        if t.apendice in ("AP01", "AP02"):
            if {"saldo_anterior", "juros", "prestacao", "saldo"} <= v.keys():
                esp = v["saldo_anterior"] + v["juros"] - v["prestacao"]
                if abs(esp - v["saldo"]) > CENT:
                    inc(l.numero, f"saldo anterior + juros − prestação = {esp}, mas a tabela indica saldo {v['saldo']}")
            if {"juros", "prestacao", "amortizacao"} <= v.keys() and abs(v["prestacao"] - v["juros"] - v["amortizacao"]) > CENT:
                inc(l.numero, f"prestação − juros = {v['prestacao'] - v['juros']}, mas a amortização indicada é {v['amortizacao']}")
            if anterior and "saldo" in anterior.valores and "saldo_anterior" in v \
                    and abs(anterior.valores["saldo"] - v["saldo_anterior"]) > CENT:
                inc(l.numero, f"saldo anterior ({v['saldo_anterior']}) ≠ saldo final da linha anterior ({anterior.valores['saldo']})")
        else:
            if {"pago", "devido", "diferenca"} <= v.keys() and abs(v["pago"] - v["devido"] - v["diferenca"]) > CENT:
                inc(l.numero, f"pago − devido = {v['pago'] - v['devido']}, mas a diferença indicada é {v['diferenca']}")
            if {"corrigido", "juros_mora", "total"} <= v.keys() and abs(v["corrigido"] + v["juros_mora"] - v["total"]) > CENT:
                inc(l.numero, f"corrigido + juros = {v['corrigido'] + v['juros_mora']}, mas o total indicado é {v['total']}")
            if {"diferenca", "restituir"} <= v.keys() and v["diferenca"] and \
                    v["restituir"] not in (v["diferenca"], 2 * v["diferenca"]):
                inc(l.numero, f"valor a restituir ({v['restituir']}) não é a diferença nem o dobro dela ({v['diferenca']})")
        anterior = l
    for col, total in t.totais.items():
        soma = sum((l.valores[col] for l in t.linhas if col in l.valores), ZERO)
        if abs(soma - total) > CENT:
            inc(None, f"total declarado de '{col}' ({total}) ≠ soma das linhas ({soma})")
    return out


# --- Comparação linha a linha ----------------------------------------------------------------------

def _linhas_motor_evolucao(r: ResultadoEvolucao) -> tuple[dict[int, object], dict[date, object]]:
    por_n = {l.numero_parcela: l for l in r.linhas if l.numero_parcela is not None}
    por_d = {l.data: l for l in r.linhas if l.numero_parcela is None}
    return por_n, por_d


def comparar_evolucao(t: TabelaPericial, r: ResultadoEvolucao, ficha: FichaCaso | None = None) -> list[Comparacao]:
    por_n, por_d = _linhas_motor_evolucao(r)
    out = []
    datas = {}
    ant_data = ficha.data("data_liberacao") if ficha else None
    for ordem, lp in enumerate(t.linhas, start=1):
        lm = por_n.get(lp.numero) if lp.numero is not None else por_d.get(lp.data)
        for col in ("saldo_anterior", "juros", "amortizacao", "prestacao", "saldo"):
            vp = lp.valores.get(col)
            vm = valor_motor_evolucao(lm, col) if lm is not None else None
            if vp is None and vm is None:
                continue
            out.append(_comparacao(t.apendice, lp, col, vp, vm, ordem,
                                   _justificar_evolucao(col, lp, lm, ant_data, ficha, t.apendice)))
        ant_data = lp.data or ant_data
    return out


def comparar_ap03(t: TabelaPericial, r, ficha: FichaCaso | None = None, series=None) -> list[Comparacao]:
    por_n = {}
    for l in r.linhas:
        m = re.match(r"Parcela (\d+)", l.descricao)
        if m:
            por_n[int(m.group(1))] = l
    out = []
    for ordem, lp in enumerate(t.linhas, start=1):
        lm = por_n.get(lp.numero)
        for col, attr in MAPA_AP03.items():
            vp = lp.valores.get(col)
            vm = getattr(lm, attr) if lm is not None else None
            if vp is None and vm is None:
                continue
            out.append(_comparacao("AP03", lp, col, vp, vm, ordem, _justificar_ap03(col, lp, lm, ficha, series)))
    return out


def _comparacao(ap, lp: LinhaPericial, col, vp, vm, ordem, justificar) -> Comparacao:
    if vp is None:
        return Comparacao(apendice=ap, numero=lp.numero, data=lp.data, coluna=col, perita=None, motor=vm,
                          diferenca=None, diferenca_pct=None, classe=Classe.SEM_PERITA, justificativa="")
    if vm is None:
        return Comparacao(apendice=ap, numero=lp.numero, data=lp.data, coluna=col, perita=vp, motor=None, diferenca=None,
                          diferenca_pct=None, classe=Classe.DIVERGENTE,
                          justificativa="linha/coluna sem correspondente na reconstrução (parcela ou data não encontrada)")
    d = vm - vp
    classe = _classe(col, d, ordem)
    just = {Classe.IDENTICO: "", Classe.CENTAVO: "diferença de centavo compatível com arredondamento por parcela",
            Classe.ACUMULADO: "acúmulo de diferenças de centavo de períodos anteriores (arredondamento)"}.get(classe)
    if just is None:
        just = justificar() if callable(justificar) else justificar
    return Comparacao(apendice=ap, numero=lp.numero, data=lp.data, coluna=col, perita=vp, motor=vm, diferenca=d,
                      diferenca_pct=_pct(d, vp), classe=classe, justificativa=just)


def _justificar_evolucao(col, lp: LinhaPericial, lm, ant_data, ficha, ap):
    def f() -> str:
        partes = []
        v = lp.valores
        if lm is not None and "saldo_anterior" in v and abs(lm.saldo_anterior - v["saldo_anterior"]) > CENT:
            partes.append(f"diferença herdada: saldo anterior perita {v['saldo_anterior']} × motor {lm.saldo_anterior}")
        if col in ("juros", "amortizacao", "saldo") and "juros" in v and v.get("saldo_anterior"):
            ip = v["juros"] / v["saldo_anterior"]
            im = (lm.juros_periodo / lm.saldo_anterior) if lm is not None and lm.saldo_anterior else None
            dias = (lp.data - ant_data).days if lp.data and ant_data else None
            txt = f"taxa efetiva do período na perita {(ip * 100).quantize(D('0.0001'))}%"
            if im is not None:
                txt += f" × motor {(im * 100).quantize(D('0.0001'))}%"
            if dias:
                txt += f" ({dias} dias)"
            if ficha and dias:
                chave = "taxa_mensal_contrato" if ap == "AP01" else "taxa_mensal_revisada"
                i = ficha.percentual(chave)
                if i:
                    mensal_fixo, pro_rata = i, potencia(UM + i, D(dias) / D(30)) - UM
                    if abs(ip - mensal_fixo) < D("0.000005"):
                        txt += "; compatível com período mensal fixo (meses civis)"
                    elif abs(ip - pro_rata) < D("0.000005"):
                        txt += "; compatível com capitalização proporcional aos dias corridos (dias/30)"
                    else:
                        ia = ficha.percentual("taxa_anual_contrato" if ap == "AP01" else "taxa_anual_revisada")
                        for base in (365, 360):
                            if ia and abs(ip - (potencia(UM + ia, D(dias) / D(base)) - UM)) < D("0.000005"):
                                txt += f"; compatível com capitalização diária pela taxa anual, base {base}"
                                break
            partes.append(txt)
        if col == "prestacao" and lm is not None:
            partes.append("valor da prestação diverge: verificar a taxa/parcela adotada no recálculo")
        return "; ".join(partes) or "não explicada pelos diagnósticos automáticos — requer análise"
    return f


def _alternativas_correcao(lp: LinhaPericial, ficha: FichaCaso, series) -> str | None:
    """Testa índices disponíveis e regras de inclusão de meses; diz qual reproduz o valor corrigido da perita."""
    from ..motor.atualizacao import Acumulacao, ConvencaoCompetencias, CriterioCorrecao, ParametrosAtualizacao, atualizar
    from ..motor.auditoria import Origem
    base, alvo = lp.valores.get("restituir") or lp.valores.get("diferenca"), lp.valores.get("corrigido")
    if not (base and alvo and lp.data and series):
        return None
    pol = PoliticaArredondamento(casas=2, modo=ModoArredondamento.MEIO_PARA_CIMA, arredondar_cada_parcela=True)
    o = Origem(documento="diagnóstico")
    declarado = (ficha.texto("indice_correcao"), ficha.sim("incluir_mes_inicial"), ficha.sim("incluir_mes_final"))
    for nome in sorted(series):
        for ini in (True, False):
            for fim in (True, False):
                p = ParametrosAtualizacao(correcao=[CriterioCorrecao(inicio=date(1900, 1, 1), fim=date(2100, 1, 1), serie=nome, origem=o)],
                                          juros=[], competencias=ConvencaoCompetencias(incluir_mes_inicial=ini, incluir_mes_final=fim),
                                          acumulacao_juros=Acumulacao.SOMA)
                try:
                    v = atualizar(base, lp.data, ficha.data("data_base"), p, series, pol).valor_corrigido
                except ValueError:
                    continue
                if abs(v - alvo) <= CENT and (nome, ini, fim) != declarado:
                    sn = lambda b: "sim" if b else "não"  # noqa: E731
                    return (f"COMPROVADO: o valor corrigido da perita é reproduzido com o índice {nome}, mês inicial={sn(ini)}, "
                            f"mês da data-base={sn(fim)} (a ficha declara {declarado[0]}, {sn(declarado[1])}, {sn(declarado[2])})")
    return "nenhuma combinação de índice carregado e regra de meses reproduz o valor corrigido da perita"


def _justificar_ap03(col, lp: LinhaPericial, lm, ficha=None, series=None):
    def f() -> str:
        v = lp.valores
        partes = []
        if lm is None:
            return "parcela sem correspondente na reconstrução"
        if col in ("devido", "diferenca", "restituir") and "devido" in v and abs(v["devido"] - lm.devido) > CENT:
            partes.append(f"valor devido revisado perita {v['devido']} × motor {lm.devido} (efeito do AP02)")
        if col == "restituir" and "diferenca" in v and v.get("restituir"):
            mult = v["restituir"] / v["diferenca"] if v["diferenca"] else None
            if mult is not None:
                partes.append(f"perita aplicou multiplicador {mult.quantize(D('0.01'))} (1 = simples; 2 = dobro)")
        if col in ("corrigido", "total") and v.get("corrigido") and v.get("restituir") and lm.a_restituir:
            fp = v["corrigido"] / v["restituir"]
            fm = lm.corrigido / lm.a_restituir
            partes.append(f"fator de correção perita {fp.quantize(D('0.000001'))} × motor {fm.quantize(D('0.000001'))}")
            if ficha is not None:
                alt = _alternativas_correcao(lp, ficha, series)
                if alt:
                    partes.append(alt)
        if col in ("juros_mora", "total") and v.get("juros_mora") and v.get("corrigido") and lm.corrigido:
            pp, pm = v["juros_mora"] / v["corrigido"], lm.juros / lm.corrigido
            if abs(pp - pm) < D("0.0001"):
                partes.append(f"mesmo percentual de juros ({(pp * 100).quantize(D('0.01'))}%): diferença herdada do valor corrigido")
            else:
                partes.append(f"percentual de juros perita {(pp * 100).quantize(D('0.01'))}% × motor "
                              f"{(pm * 100).quantize(D('0.01'))}% (termo inicial, contagem ou taxa)")
        return "; ".join(partes) or "não explicada pelos diagnósticos automáticos — requer análise"
    return f


# --- Cenários de diagnóstico ---------------------------------------------------------------------

def _celulas(t: TabelaPericial, r: ResultadoEvolucao) -> dict[tuple, tuple[Decimal, Decimal]]:
    """(nº ou data, coluna) -> (perita, motor) para todas as colunas comparáveis."""
    por_n, por_d = _linhas_motor_evolucao(r)
    out = {}
    for lp in t.linhas:
        lm = por_n.get(lp.numero) if lp.numero is not None else por_d.get(lp.data)
        if lm is None:
            continue
        for col in MAPA_EVOLUCAO:
            if col in lp.valores:
                out[(lp.numero if lp.numero is not None else lp.data, col)] = (lp.valores[col], valor_motor_evolucao(lm, col))
    return out


def cenarios(ficha: FichaCaso, parecer: Parecer, series) -> tuple[dict[str, list[Cenario]], dict[tuple, dict]]:
    """Recalcula AP01/AP02 com convenções e arredondamentos alternativos e mede a aderência ao parecer.

    Retorna o ranking por apêndice e, por cenário, o valor do motor em cada célula (para comprovar
    divergências célula a célula)."""
    politicas = {
        "centavo HALF_UP por parcela": PoliticaArredondamento(casas=2, modo=ModoArredondamento.MEIO_PARA_CIMA, arredondar_cada_parcela=True),
        "centavo HALF_EVEN por parcela": PoliticaArredondamento(casas=2, modo=ModoArredondamento.MEIO_PARA_PAR, arredondar_cada_parcela=True),
        "truncamento por parcela": PoliticaArredondamento(casas=2, modo=ModoArredondamento.TRUNCAR, arredondar_cada_parcela=True),
        "sem arredondamento intermediário": PoliticaArredondamento(casas=2, modo=ModoArredondamento.MEIO_PARA_CIMA, arredondar_cada_parcela=False),
    }
    ranking: dict[str, list[Cenario]] = {"AP01": [], "AP02": []}
    celulas: dict[tuple, dict] = {}
    for conv in ConvencaoTempo:
        for regime in (Regime.COMPOSTO, Regime.SIMPLES):
            for nome_pol, pol in politicas.items():
                try:
                    r = reconstruir(ficha, series, convencao_contrato=conv, convencao_revisada=conv, regime_revisado=regime,
                                    politica=pol, com_ap03=False)
                except (ValueError, ArithmeticError):
                    continue
                for ap, res in (("AP01", r.ap01), ("AP02", r.ap02)):
                    if ap not in parecer.tabelas or (ap == "AP01" and regime is Regime.SIMPLES):
                        continue
                    cel = _celulas(parecer.tabelas[ap], res)
                    if not cel:
                        continue
                    difs = [abs(m - p) for p, m in cel.values()]
                    nome = f"{conv.value}" + (f", {regime.value}" if ap == "AP02" else "") + f", {nome_pol}"
                    celulas[(ap, nome)] = {k: m for k, (p, m) in cel.items()}
                    ranking[ap].append(Cenario(nome=nome, descricao=nome, erro_absoluto_total=sum(difs, ZERO),
                                               erro_maximo=max(difs), linhas_identicas=sum(1 for d in difs if d <= CENT),
                                               linhas=len(difs), reproduz=max(difs) <= CENT))
    for ap in ranking:
        ranking[ap].sort(key=lambda c: (-c.linhas_identicas, c.erro_absoluto_total))
    return ranking, celulas


@dataclass
class ResultadoValidacao:
    principal: Reconstrucao
    comparacoes: list[Comparacao]
    inconsistencias: list[Inconsistencia]
    cenarios: dict[str, list[Cenario]]
    totais: list[dict] = field(default_factory=list)


def validar(ficha: FichaCaso, parecer: Parecer, series) -> ResultadoValidacao:
    r = reconstruir(ficha, series)
    comps: list[Comparacao] = []
    if "AP01" in parecer.tabelas:
        comps += comparar_evolucao(parecer.tabelas["AP01"], r.ap01, ficha)
    if "AP02" in parecer.tabelas:
        comps += comparar_evolucao(parecer.tabelas["AP02"], r.ap02, ficha)
    if "AP03" in parecer.tabelas and r.ap03 is not None:
        comps += comparar_ap03(parecer.tabelas["AP03"], r.ap03, ficha, series)
    inc = [i for t in parecer.tabelas.values() for i in consistencia_interna(t)]
    ranking, celulas = cenarios(ficha, parecer, series)
    inc_linhas = {(i.apendice, i.numero) for i in inc if i.numero is not None}
    for c in comps:
        if c.classe is not Classe.DIVERGENTE:
            continue
        prefixo = ""
        if (c.apendice, c.numero) in inc_linhas:
            prefixo = "INCONSISTÊNCIA INTERNA DO PARECER nesta linha (ver seção própria) — possível erro material. "
        if c.apendice in ranking:
            chave = (c.numero if c.numero is not None else c.data, c.coluna)
            for cen in ranking[c.apendice]:          # do mais aderente ao menos aderente
                v = celulas.get((c.apendice, cen.nome), {}).get(chave)
                if v is not None and abs(v - c.perita) <= CENT:
                    prefixo += (f"COMPROVADO: reproduzido pelo cenário '{cen.nome}' "
                                f"({cen.linhas_identicas}/{cen.linhas} valores do apêndice reproduzidos). ")
                    break
            else:
                prefixo += "NÃO REPRODUZIDO por nenhum cenário testado. "
        c.justificativa = prefixo + c.justificativa
    return ResultadoValidacao(principal=r, comparacoes=comps, inconsistencias=inc, cenarios=ranking,
                              totais=_totais(parecer, r))


def _totais(parecer: Parecer, r: Reconstrucao) -> list[dict]:
    linhas = []

    def add(item, perita, motor, metodo):
        d = None if perita is None or motor is None else motor - perita
        linhas.append({"item": item, "perita": perita, "motor": motor, "diferenca": d,
                       "diferenca_pct": _pct(d, perita) if d is not None else None, "metodologia": metodo})

    def soma(ap, col):
        t = parecer.tabelas.get(ap)
        if not t:
            return None
        if col in t.totais:
            return t.totais[col]
        vals = [l.valores[col] for l in t.linhas if col in l.valores]
        return sum(vals, ZERO) if vals else None

    add("AP01 — total de juros", soma("AP01", "juros"), r.ap01.total_juros, "evolução original (motor)")
    add("AP02 — total de juros", soma("AP02", "juros"), r.ap02.total_juros, "evolução revisada (motor)")
    add("AP02 — prestação regular revisada", next((l.valores.get("prestacao") for l in parecer.tabelas["AP02"].linhas
                                                   if "prestacao" in l.valores), None) if "AP02" in parecer.tabelas else None,
        r.revisao.parcela_regular_revisada, "equivalência financeira na liberação")
    if r.ap03 is not None:
        add("AP03 — restituição nominal", soma("AP03", "restituir") or soma("AP03", "diferenca"),
            r.ap03.total_a_restituir_nominal, "pago − devido, × multiplicador do título")
        add("AP03 — total atualizado", soma("AP03", "total"), r.ap03.total_atualizado, "correção + juros de mora")
    return linhas
