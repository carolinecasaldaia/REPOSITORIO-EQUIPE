"""Comandos judiciais: dispositivo × fundamentação × alegações.

Regras de natureza:
- Comando no DISPOSITIVO de decisão (sentença, acórdão, embargos, decisão)
  -> ``Natureza.RECONHECIDO`` — candidato a parâmetro de liquidação.
- Mesma regra aplicada à FUNDAMENTAÇÃO -> ``Natureza.FUNDAMENTACAO`` —
  apenas sinaliza tema que talvez falte no dispositivo.
- Petição inicial, contestação, razões de recurso -> ``Natureza.ALEGADO`` —
  NUNCA vira parâmetro; serve para listar alegações não reconhecidas.

As regras são heurísticas de texto: cada comando sai com o trecho literal e
a página, e precisa ser conferido pela advogada antes de qualquer cálculo.
"""

from __future__ import annotations

import re

from ..documentos.modelos import ALEGACOES, DECISORIOS, Documento, Natureza, TipoDocumento, fonte_de
from ..documentos.texto import RE_DATA_NUM, RE_PERCENT, RE_VALOR, data_num, dividir_clausulas, normalizar
from .catalogo import itens_no_texto
from .modelos import Comando, Tema

INICIO_DISPOSITIVO = (r"(ante|diante|pelo|em face|por todo) (o )?exposto|isto posto|posto isso|"
                      r"em razao do exposto|\bdispositivo\b|\bacordam\b")
FIM_DISPOSITIVO = r"publique-se|p\.\s?r\.\s?i\.?|registre-se|sala das sessoes"
NEGACAO = (r"improceden|indefir|\bmant(er|enho|enha|ida|ido|idas|idos|em)\b|manutencao|\blegalidade d|\be legal\b|\bsao legais\b|"
           r"nao (ha|houve|se verifica|restou) (abusividade|ilegalidade)|rejeit|afast\w* a alegacao|nego\b|negar\b|"
           r"desacolh|nao acolh|inexist\w* abusividade|valida a cobranca|regular a cobranca")
VERBO_EXCLUSAO = r"ilegal|abusiv|nul[ao]|nulidade|indevid|exclu|afast|decot|restitu|devolu|repeti|exclusao"
RV = RE_VALOR.replace("R\\$", "r\\$")
INDICES = r"(inpc|ipca-e|ipca|igp-m|igpm|igp-di|selic|tabela pratica[^,;.]{0,30}|indice[s]? (oficial|da corregedoria)[^,;.]{0,40}|taxa legal)"
TERMO = (r"(?:a partir|a contar|desde|contad[oa]s?)\s+(?:da data\s+)?"
         r"((?:d[oae]s?|de cada|cada|a|o)\s+.{3,70}?)(?=\s+e\s+(?:juros|correcao|honorarios)|[,;]|\.\s|\.$|$)")


def localizar_dispositivo(doc: Documento) -> list[tuple[int, int]]:
    """Trechos (início, fim) do dispositivo. Vazio se não identificado."""
    norm = normalizar(doc.texto).replace("\n", " ")   # mesmo comprimento: posições preservadas
    marcas = list(re.finditer(INICIO_DISPOSITIVO, norm))
    if not marcas:
        j = list(re.finditer(r"\bjulgo\b|\bacolho\b|\brejeito\b|(dou|nego|negar|dar) (parcial )?provimento", norm))
        if not j:
            return []
        marcas = [j[0]]
    trechos = []
    if doc.tipo is TipoDocumento.ACORDAO:
        # acórdão: a frase do 'acordam' e a conclusão do voto ('ante o exposto ...')
        candidatos = [m for m in marcas if m.group(0) == "acordam"][:1] + [m for m in marcas if m.group(0) != "acordam"][-1:]
    else:
        candidatos = [marcas[-1]]
    for m in candidatos:
        f = re.search(FIM_DISPOSITIVO, norm[m.end():])
        fim = m.end() + f.start() if f else len(norm)
        if m.group(0) == "acordam":
            ponto = norm.find(".", m.end())
            fim = min(fim, ponto + 1 if ponto != -1 else fim)
        trechos.append((m.start(), fim))
    return sorted(trechos)


def extrair_comandos(doc: Documento) -> list[Comando]:
    if doc.tipo not in DECISORIOS | ALEGACOES:
        return []
    texto = doc.texto
    if doc.tipo in ALEGACOES:
        return _comandos_em(doc, [(0, len(texto))], Natureza.ALEGADO)
    disp = localizar_dispositivo(doc)
    comandos = _comandos_em(doc, disp, Natureza.RECONHECIDO) if disp else []
    fora = _complemento(disp, len(texto))
    comandos += _comandos_em(doc, fora, Natureza.FUNDAMENTACAO)
    return comandos


def _complemento(trechos: list[tuple[int, int]], n: int) -> list[tuple[int, int]]:
    out, pos = [], 0
    for a, b in trechos:
        if a > pos:
            out.append((pos, a))
        pos = max(pos, b)
    if pos < n:
        out.append((pos, n))
    return out


def _comandos_em(doc: Documento, trechos: list[tuple[int, int]], natureza: Natureza) -> list[Comando]:
    texto = doc.texto
    norm = normalizar(texto)
    out: list[Comando] = []
    for a, b in trechos:
        for ca, cb in dividir_clausulas(texto[a:b]):
            ini, fim = a + ca, a + cb
            # quebras de linha/espaços repetidos não podem impedir o reconhecimento
            out.extend(_regras(doc, re.sub(r"\s+", " ", norm[ini:fim]), ini, fim, natureza))
    return out


def _cmd(doc, tema, chave, efeito, ini, fim, natureza, detalhes=None, lacunas=None) -> Comando:
    return Comando(tema=tema, chave=chave, efeito=efeito, detalhes=detalhes or {}, natureza=natureza,
                   fonte=fonte_de(doc, ini, fim, margem=0), documento_tipo=doc.tipo, documento_data=doc.data,
                   lacunas=lacunas or [])


def _regras(doc: Documento, c: str, ini: int, fim: int, nat: Natureza) -> list[Comando]:
    out: list[Comando] = []
    neg = bool(re.search(NEGACAO, c))
    add = lambda *a, **k: out.append(_cmd(doc, *a, ini=ini, fim=fim, natureza=nat, **k))  # noqa: E731

    # Resultado do julgamento / do recurso / dos embargos
    if m := re.search(r"julg\w* (parcialmente )?(procedente|improcedente)s?", c):
        efeito = "improcedente" if m.group(2) == "improcedente" else ("parcialmente procedente" if m.group(1) else "procedente")
        add(Tema.RESULTADO, "resultado", efeito)
    if m := re.search(r"(dar|dou|deram|dado|nego|negar|negaram|negado) (parcial )?provimento", c):
        efeito = ("negado provimento" if m.group(1).startswith("neg")
                  else "dado parcial provimento" if m.group(2) else "dado provimento")
        add(Tema.RESULTADO, "resultado_recurso", efeito)
    if doc.tipo is TipoDocumento.EMBARGOS_DECISAO and (m := re.search(r"(acolho|acolher|rejeito|rejeitar)( em parte| parcialmente)?", c)):
        efeito = "rejeitados" if m.group(1).startswith("rejeit") else ("acolhidos em parte" if m.group(2) else "acolhidos")
        add(Tema.RESULTADO, "resultado_embargos", efeito)

    # Juros remuneratórios
    if re.search(r"juros remuneratorios|taxa de juros (remuneratorios|contratad|pactuad)", c):
        if re.search(r"limit|reduz|revis|readequ|substitu|aplica|adequa", c) and not re.search(r"mant\w+ (a taxa|os juros)", c):
            det, lac = {}, []
            if re.search(r"taxa media", c):
                det["criterio"] = "taxa média de mercado (BACEN)"
                lac.append("valor da taxa média (série BACEN, modalidade e mês da contratação)")
            elif p := re.search(RE_PERCENT + r"\s*(a\.?\s?m\.?|ao mes)", c):
                det["taxa_mensal"] = p.group(1)
            else:
                lac.append("taxa revisada não especificada")
            add(Tema.JUROS_REMUNERATORIOS, "juros_remuneratorios", "revisados", detalhes=det, lacunas=lac)
        elif neg:
            add(Tema.JUROS_REMUNERATORIOS, "juros_remuneratorios", "mantidos")

    # Capitalização
    if re.search(r"capitaliza", c):
        modal = re.findall(r"capitaliza\w*\s+(diaria|mensal|anual)", c)
        if re.search(r"afast|vedad|exclu|inadmit|ilegal|proib|nao (e )?(admitid|permitid)|decot", c):
            add(Tema.CAPITALIZACAO, "capitalizacao", "afastada", detalhes={"modalidades": ",".join(modal)},
                lacunas=[] if modal else ["periodicidade afastada não especificada"])
        elif neg or re.search(r"admit|permitid|legal|pactuad|valid", c):
            add(Tema.CAPITALIZACAO, "capitalizacao", "mantida", detalhes={"modalidades": ",".join(modal)})

    # Tarifas, seguros e demais cobranças
    if re.search(VERBO_EXCLUSAO, c) or neg:
        for chave in dict.fromkeys(k for k, _, _ in itens_no_texto(c)):
            if chave == "iof" and not re.search(r"iof (reflexo|proporcional|incidente)", c):
                continue
            if neg and not re.search(r"(declar|reconhec)\w* (a )?(ilegalidade|abusividade|nulidade)", c):
                add(Tema.EXCLUSAO, f"exclusao:{chave}", "mantida (legal)", detalhes={"item": chave})
            elif re.search(VERBO_EXCLUSAO, c):
                add(Tema.EXCLUSAO, f"exclusao:{chave}", "excluída (ilegal/abusiva)", detalhes={"item": chave})

    # Mora
    if re.search(r"descaracteriz\w*\s+(a\s+)?mora|afast\w* (a|os efeitos da) mora|inexist\w* (a )?mora", c):
        comps = [n for n, p in (("multa", r"\bmulta"), ("juros_mora", r"juros (de mora|moratorios)"),
                                 ("comissao_permanencia", r"comissao de permanencia")) if re.search(p, c)]
        add(Tema.MORA, "mora", "descaracterizada", detalhes={"componentes": ",".join(comps)},
            lacunas=[] if comps else ["encargos moratórios afastados não especificados"])
    elif re.search(r"(caracteriz|configur)\w* (a )?mora|mora (do|da) \w+ (caracterizad|configurad)", c):
        add(Tema.MORA, "mora", "caracterizada")

    # Repetição do indébito
    if re.search(r"restitu|repeti|devolu", c) and re.search(r"dobro|simples|indebito|valores pagos", c):
        if neg and not re.search(r"dobro|simples", c):
            add(Tema.REPETICAO, "repeticao", "negada")
        else:
            corte = re.search(r"(a partir de|apos|posteriores a)\s+" + RE_DATA_NUM, c)
            det = {}
            if "dobro" in c and corte:
                efeito = "dobro a partir de data"
                det["data_corte"] = data_num(*corte.groups()[-3:]).isoformat()
            elif "dobro" in c and "simples" in c:
                efeito = "simples e dobro"
            elif "dobro" in c:
                efeito = "em dobro"
            elif "simples" in c:
                efeito = "simples"
            else:
                efeito = "determinada"
            lac = []
            if efeito in ("simples e dobro", "determinada"):
                lac.append("modalidade (simples/dobro) e marco temporal não especificados")
            add(Tema.REPETICAO, "repeticao", efeito, detalhes=det, lacunas=lac)

    # Compensação
    if re.search(r"compensa", c):
        add(Tema.COMPENSACAO, "compensacao", "negada" if neg else "autorizada")

    # Correção monetária
    if re.search(r"correcao monetaria|corrigid|atualizacao monetaria", c):
        det, lac = {}, []
        if i := re.search(INDICES, c):
            det["indice"] = i.group(1).strip()
        else:
            lac.append("índice de correção")
        if t := re.search(r"(correcao monetaria|corrigid\w*|atualizacao monetaria)[^;]{0,120}?" + TERMO, c):
            det["termo_inicial"] = t.group(2).strip()
        else:
            lac.append("termo inicial da correção")
        add(Tema.CORRECAO, "correcao", "determinada", detalhes=det, lacunas=lac)

    # Juros de mora
    if re.search(r"juros (de mora|moratorios|legais)", c) and not re.search(r"(afast|exclu)\w*[^;]{0,30}juros (de mora|moratorios)", c):
        det, lac = {}, []
        if p := re.search(r"juros (?:de mora|moratorios|legais)[^;]{0,40}?" + RE_PERCENT + r"\s*(a\.?\s?m\.?|ao mes)", c):
            det["taxa_mensal"] = p.group(1)
        elif s := re.search(r"selic|taxa legal|art\.? 406", c):
            det["taxa"] = s.group(0)
        else:
            lac.append("taxa dos juros de mora")
        if t := re.search(r"juros (?:de mora|moratorios|legais)[^;]{0,120}?" + TERMO, c):
            det["termo_inicial"] = t.group(1).strip()
        else:
            lac.append("termo inicial dos juros de mora")
        add(Tema.JUROS_MORA, "juros_mora", "determinados", detalhes=det, lacunas=lac)

    # Honorários
    if re.search(r"honorarios", c):
        det, lac = {}, []
        efeito = "majorados" if re.search(r"major", c) else "fixados"
        if p := re.search(RE_PERCENT, c):
            det["percentual"] = p.group(1)
        elif v := re.search(RV, c):
            det["valor_fixo"] = v.group(1)
        else:
            lac.append("percentual ou valor dos honorários")
        if b := re.search(r"(valor (atualizado )?da condenacao|proveito economico|valor (atualizado )?da causa)", c):
            det["base"] = b.group(1)
        elif "percentual" in det:
            lac.append("base de cálculo dos honorários")
        if d := re.search(r"condeno (o|a|os|as) (re[u]?|requerid\w*|banco|instituicao financeira|autor\w*|parte autora|parte re|ambas as partes|apelante|apelad\w*)", c):
            det["devedor"] = d.group(2)
        if re.search(r"sucumbencia reciproca|proporcao|pro rata|ambas as partes", c):
            det["sucumbencia_reciproca"] = "sim"
            lac.append("cota de cada parte na sucumbência")
        add(Tema.HONORARIOS, "honorarios", efeito, detalhes=det, lacunas=lac)

    # Multa do DL 911/1969
    if re.search(r"art\w*\.?\s*3[ºo°]?,?\s*§\s*6|multa (prevista no|do) (decreto-lei|dl)\s*(n[ºo°]?\s*)?911|multa de (50|cinquenta)", c):
        add(Tema.MULTA_DL911, "multa_dl911", "indeferida" if neg else "deferida",
            lacunas=[] if neg else ["base ('valor originalmente financiado') e atualização"])

    # Perdas e danos
    if re.search(r"perdas e danos", c):
        det = {"base": "tabela fipe"} if "fipe" in c else {}
        add(Tema.PERDAS_DANOS, "perdas_danos", "indeferidas" if neg else "deferidas", detalhes=det,
            lacunas=[] if (neg or det) else ["critério de quantificação das perdas e danos"])

    # Restituição do veículo
    if re.search(r"(restitui|devolu|reintegra)\w*[^;]{0,50}(veiculo|bem|automovel)", c):
        add(Tema.RESTITUICAO_VEICULO, "restituicao_veiculo", "negada" if neg else "determinada")
    return out
