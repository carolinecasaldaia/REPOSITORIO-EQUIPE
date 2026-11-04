"""Montagem do quadro de parâmetros judiciais e das verificações de consistência.

O quadro é a ponte entre a leitura documental e o motor: nada vai ao motor
sem passar por ele e sem a confirmação da advogada (``aprovacao``).
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from ..documentos.modelos import ALEGACOES, DECISORIOS, Documento, Fonte, Natureza, TipoDocumento
from ..documentos.texto import normalizar
from .catalogo import ITENS, id_item
from .consolidacao import consolidar
from .contrato import extrair_contrato
from .decisoes import extrair_comandos
from .modelos import (
    Achado, Alternativa, Comando, Ocorrencia, Parametro, PagamentoExtraido, QuadroParametros,
    ResumoDocumento, StatusParametro as S, TipoOcorrencia as O,
)
from .pagamentos import cruzar_pagamentos, extrair_comprovante, extrair_planilha

VERSAO_EXTRATOR = "0.4.0"

CAMPOS_CONTRATO: dict[str, tuple[str, bool]] = {
    "contrato.numero": ("Número do contrato", False),
    "contrato.data_liberacao": ("Data de emissão/liberação", True),
    "contrato.valor_liberado": ("Valor liberado", False),
    "contrato.valor_financiado": ("Valor total financiado", True),
    "contrato.taxa_mensal": ("Taxa de juros mensal", True),
    "contrato.taxa_anual": ("Taxa de juros anual", False),
    "contrato.cet_mensal": ("CET mensal", False),
    "contrato.cet_anual": ("CET anual", False),
    "contrato.n_parcelas": ("Quantidade de parcelas", True),
    "contrato.valor_parcela": ("Valor da parcela", True),
    "contrato.primeiro_vencimento": ("Vencimento da 1ª parcela", True),
    "contrato.capitalizacao": ("Capitalização pactuada", False),
    "contrato.multa_moratoria": ("Multa moratória", False),
    "contrato.juros_moratorios": ("Juros moratórios contratuais", False),
    "contrato.comissao_permanencia": ("Comissão de permanência", False),
    "contrato.valor_bem": ("Valor do bem", False),
    "contrato.entrada": ("Entrada", False),
}

CAMPOS_CALCULO: dict[str, tuple[str, str]] = {
    "calculo.convencao_tempo": ("Convenção de tempo da capitalização",
                                "meses_civis | meses_30 | dias_base_360 | dias_base_365"),
    "calculo.arredondamento": ("Política de arredondamento", "ex.: '2;HALF_UP;por_parcela'"),
    "calculo.ordem_imputacao": ("Ordem de imputação dos pagamentos", "juros_primeiro | capital_primeiro"),
}

TITULO_DESCRICAO = {
    "resultado": "Resultado do julgamento", "resultado_recurso": "Resultado do recurso",
    "juros_remuneratorios": "Juros remuneratórios", "capitalizacao": "Capitalização",
    "mora": "Mora", "repeticao": "Repetição do indébito", "compensacao": "Compensação",
    "correcao": "Correção monetária", "juros_mora": "Juros de mora", "honorarios": "Honorários advocatícios",
    "multa_dl911": "Multa art. 3º, §6º, DL 911/1969", "perdas_danos": "Perdas e danos",
    "restituicao_veiculo": "Restituição do veículo",
}
EFEITOS_FAVORAVEIS = {"revisados", "afastada", "excluída (ilegal/abusiva)", "descaracterizada", "em dobro",
                      "simples", "dobro a partir de data", "simples e dobro", "determinada", "deferida", "deferidas"}


def montar_quadro(caso_id: str, documentos: list[Documento], avisos_leitura: list[str]) -> QuadroParametros:
    ocorr: list[Ocorrencia] = []
    params: dict[str, Parametro] = {}

    # --- Contrato ------------------------------------------------------------------
    achados: list[Achado] = []
    for d in documentos:
        if d.tipo is TipoDocumento.CONTRATO or d.tipo in ALEGACOES:
            achados += extrair_contrato(d)
    contratuais = [a for a in achados if a.natureza is Natureza.CONTRATUAL]
    alegados = [a for a in achados if a.natureza is Natureza.ALEGADO]

    campos = dict(CAMPOS_CONTRATO)
    for a in contratuais:
        if a.campo.startswith("contrato.item:") and a.campo not in campos:
            campos[a.campo] = (f"Item: {a.detalhes.get('item')}", False)
    for campo, (desc, obrig) in campos.items():
        doc_vals = [a for a in contratuais if a.campo == campo]
        p = _parametro_de_achados(campo, "contrato", desc, obrig, doc_vals)
        if p is None:
            continue
        for a in alegados:
            if a.campo == campo:
                p.alternativas.append(Alternativa(valor=a.valor, exibicao=a.exibicao, natureza=a.natureza, fonte=a.fonte))
                if p.valor is not None and a.valor != p.valor:
                    ocorr.append(Ocorrencia(
                        id=f"alegacao-diverge-{campo}-{len(ocorr)}", tipo=O.CONTRADICAO, bloqueia=False,
                        texto=f"{desc}: {a.fonte.tipo_documento.value} indica {a.exibicao}, o contrato indica "
                              f"{p.exibicao}. Prevalece o documento contratual; conferir.", fontes=[a.fonte] + p.fontes))
        if campo.startswith("contrato.item:"):
            p.grupo = "composição"
            if p.status is S.EXTRAIDO and not p.detalhes.get("forma"):
                p.status = S.INSUFICIENTE
                p.observacoes.append("forma de pagamento (financiado / à vista) não identificada no contrato")
        params[campo] = p

    for campo, (desc, ajuda) in CAMPOS_CALCULO.items():
        params[campo] = Parametro(id=campo, grupo="cálculo", descricao=desc, obrigatorio=True, status=S.AUSENTE,
                                  observacoes=[f"definição técnica da advogada/equipe: {ajuda}"])

    ocorr += _verificar_contrato(params)

    # --- Pagamentos ------------------------------------------------------------------
    pagamentos: list[PagamentoExtraido] = []
    for d in documentos:
        if d.tipo is TipoDocumento.COMPROVANTE:
            pagamentos.append(extrair_comprovante(d))
        elif d.tipo is TipoDocumento.PLANILHA:
            ps, av = extrair_planilha(d)
            pagamentos += ps
            avisos_leitura = avisos_leitura + av
    ocorr += cruzar_pagamentos(pagamentos)

    # --- Comandos judiciais ------------------------------------------------------------
    comandos: list[Comando] = []
    for d in documentos:
        comandos += extrair_comandos(d)
    superior = {d.id: d.instancia_superior for d in documentos}
    vigentes, modificacoes, oc = consolidar(comandos, superior)
    ocorr += oc
    chaves_vigentes = {c.chave: c for c in vigentes}

    n_emb = 0
    for c in vigentes:
        if c.chave in ("resultado_recurso", "resultado_embargos"):
            n_emb += c.chave == "resultado_embargos"
            pid = f"titulo.{c.chave}" + (f"_{n_emb}" if c.chave == "resultado_embargos" else "")
            params[pid] = Parametro(
                id=pid, grupo="título judicial", obrigatorio=False, status=S.INFORMATIVO, valor=c.efeito,
                exibicao=c.efeito, fontes=[c.fonte],
                descricao="Resultado do recurso" if c.chave == "resultado_recurso" else "Resultado dos embargos de declaração",
                observacoes=[f"{c.documento_tipo.value} de {c.documento_data or 'data não identificada'}"])
            continue
        pid = f"titulo.{c.chave}"
        desc = TITULO_DESCRICAO.get(c.chave) or f"Exclusão: {c.detalhes.get('item', c.chave)}"
        params[pid] = Parametro(
            id=pid, grupo="título judicial", descricao=desc, obrigatorio=True,
            status=S.INSUFICIENTE if c.lacunas else S.EXTRAIDO, valor=c.efeito, exibicao=c.efeito,
            detalhes=c.detalhes, fontes=[c.fonte],
            observacoes=[f"definir: {l}" for l in c.lacunas]
                        + [f"origem: dispositivo de {c.documento_tipo.value}"],
        )
        if c.chave.startswith("exclusao:") and c.efeito.startswith("excluída"):
            item = id_item(c.detalhes.get("item", ""))
            if f"contrato.item:{item}" not in params:
                params[pid].status = S.INSUFICIENTE
                params[pid].observacoes.append("valor e forma de pagamento do item não localizados no contrato")
    if "resultado" not in chaves_vigentes:
        params["titulo.resultado"] = Parametro(id="titulo.resultado", grupo="título judicial",
                                               descricao="Resultado do julgamento", obrigatorio=True, status=S.AUSENTE,
                                               observacoes=["dispositivo da sentença não localizado"])
    gera_credito = any(c.efeito in EFEITOS_FAVORAVEIS for c in vigentes
                       if c.chave.startswith("exclusao:") or c.chave in ("juros_remuneratorios", "capitalizacao", "mora"))
    if gera_credito:
        for chave in ("repeticao", "correcao", "juros_mora"):
            if chave not in chaves_vigentes:
                params[f"titulo.{chave}"] = Parametro(
                    id=f"titulo.{chave}", grupo="título judicial", descricao=TITULO_DESCRICAO[chave], obrigatorio=True,
                    status=S.AUSENTE,
                    observacoes=["o título reconhece cobrança indevida, mas não foi localizado comando sobre este "
                                 "ponto no dispositivo — confirmar (omissão? fixado em outra decisão?)"])

    # Fundamentação sem dispositivo e alegações não reconhecidas
    for c in comandos:
        if c.natureza is Natureza.FUNDAMENTACAO and c.chave not in chaves_vigentes and c.tema.value != "resultado":
            ocorr.append(Ocorrencia(
                id=f"fund-{c.chave}-{c.fonte.documento_id}", tipo=O.FUNDAMENTACAO_SEM_DISPOSITIVO, bloqueia=False,
                texto=f"'{c.tema.value}' ({c.efeito}) aparece na fundamentação de {c.documento_tipo.value}, "
                      "sem comando correspondente no dispositivo. Verificar se integra o título.",
                fontes=[c.fonte]))
    alegacoes = []
    for c in comandos:
        if c.natureza is not Natureza.ALEGADO:
            continue
        vig = chaves_vigentes.get(c.chave)
        if vig is None or vig.efeito not in EFEITOS_FAVORAVEIS:
            alegacoes.append(c)
            ocorr.append(Ocorrencia(
                id=f"alegacao-{c.chave}-{c.fonte.documento_id}", tipo=O.ALEGACAO_NAO_RECONHECIDA, bloqueia=False,
                texto=f"Alegado em {c.documento_tipo.value}: '{c.tema.value}' ({c.chave}). "
                      + ("Sem reconhecimento no título — não entra no cálculo." if vig is None
                         else f"No título: '{vig.efeito}' — não entra no cálculo."),
                fontes=[c.fonte]))

    ocorr += _documentos_ausentes(documentos, pagamentos)
    for av in avisos_leitura:
        ocorr.append(Ocorrencia(id=f"leitura-{len(ocorr)}", tipo=O.OCR if "OCR" in av else O.INFORMACAO,
                                bloqueia="OCR" in av, texto=av))
    for d in documentos:
        if d.tipo is TipoDocumento.DESCONHECIDO or d.confianca < 0.5:
            ocorr.append(Ocorrencia(
                id=f"classif-{d.id}", tipo=O.CLASSIFICACAO, bloqueia=True,
                texto=f"{d.arquivo} (p. {d.paginas[0].numero}–{d.paginas[-1].numero}): classificado como "
                      f"'{d.tipo.value}' com confiança {d.confianca}. Conferir. Indícios: {'; '.join(d.indicios[:4])}"))

    return QuadroParametros(
        caso_id=caso_id, gerado_em=datetime.now().replace(microsecond=0), versao_extrator=VERSAO_EXTRATOR,
        documentos=[ResumoDocumento(id=d.id, arquivo=d.arquivo, tipo=d.tipo,
                                    paginas=f"{d.paginas[0].numero}–{d.paginas[-1].numero}", data=d.data,
                                    confianca=d.confianca, sha256=d.sha256) for d in documentos],
        parametros=params,
        pagamentos=_consolidar_pagamentos(pagamentos),
        pagamentos_status=S.EXTRAIDO if pagamentos else S.AUSENTE,
        comandos_vigentes=vigentes, modificacoes=modificacoes, alegacoes=alegacoes,
        ocorrencias=_unicas(ocorr), avisos_leitura=avisos_leitura,
    )


def _parametro_de_achados(campo, grupo, desc, obrig, achados: list[Achado]) -> Parametro | None:
    if not achados:
        if not obrig:
            return None
        return Parametro(id=campo, grupo=grupo, descricao=desc, obrigatorio=True, status=S.AUSENTE,
                         observacoes=["não localizado nos documentos"])
    distintos: dict[str, Achado] = {}
    for a in achados:
        distintos.setdefault(a.valor, a)
    primeiro = achados[0]
    p = Parametro(id=campo, grupo=grupo, descricao=desc, obrigatorio=obrig, status=S.EXTRAIDO,
                  valor=primeiro.valor, exibicao=primeiro.exibicao, detalhes=primeiro.detalhes,
                  fontes=[a.fonte for a in achados if a.valor == primeiro.valor])
    if len(distintos) > 1:
        p.status, p.valor, p.exibicao = S.CONFLITANTE, None, None
        p.alternativas = [Alternativa(valor=a.valor, exibicao=a.exibicao, natureza=a.natureza, fonte=a.fonte)
                          for a in distintos.values()]
        p.observacoes.append("valores diferentes no(s) documento(s) contratual(is): escolher o correto")
    elif campo.startswith("contrato.item:"):
        formas = {a.detalhes.get("forma", "") for a in achados} - {""}
        if len(formas) > 1:
            p.status = S.CONFLITANTE
            p.observacoes.append(f"forma de pagamento contraditória: {', '.join(sorted(formas))}")
        elif formas:
            p.detalhes = {**primeiro.detalhes, "forma": formas.pop()}
    return p


def _num(params, pid) -> Decimal | None:
    p = params.get(pid)
    return Decimal(p.valor) if p and p.status is S.EXTRAIDO and p.valor else None


def _verificar_contrato(params: dict[str, Parametro]) -> list[Ocorrencia]:
    from ..motor.financiamento import parcela_price
    from ..motor.taxas import Regime, mensal_para_anual

    out: list[Ocorrencia] = []
    vf, lib = _num(params, "contrato.valor_financiado"), _num(params, "contrato.valor_liberado")
    itens = [p for k, p in params.items() if k.startswith("contrato.item:")]
    if vf is not None and lib is not None and itens and all(p.status is S.EXTRAIDO for p in itens):
        fin = sum((Decimal(p.valor) for p in itens if p.detalhes.get("forma") == "financiado"), Decimal(0))
        if lib + fin != vf:
            out.append(Ocorrencia(
                id="composicao-nao-fecha", tipo=O.CONTRADICAO, bloqueia=True,
                texto=f"Valor financiado ({vf}) ≠ valor liberado ({lib}) + itens financiados identificados ({fin}). "
                      f"Diferença de {vf - lib - fin}: componente não identificado ou valor lido incorretamente.",
                fontes=params["contrato.valor_financiado"].fontes))
    im, n, pmt = _num(params, "contrato.taxa_mensal"), _num(params, "contrato.n_parcelas"), _num(params, "contrato.valor_parcela")
    if vf is not None and im is not None and n is not None and pmt is not None:
        calc = parcela_price(vf, im, int(n)).quantize(Decimal("0.01"))
        if abs(calc - pmt) > Decimal("1.00"):
            out.append(Ocorrencia(
                id="parcela-diverge-price", tipo=O.DIVERGENCIA, bloqueia=False,
                texto=f"Parcela contratada ({pmt}) difere da Price mensal com os dados lidos ({calc}). Pode indicar "
                      "capitalização diária, data de liberação distinta, carência ou custo não identificado.",
                fontes=params["contrato.valor_parcela"].fontes))
    ia = _num(params, "contrato.taxa_anual")
    if im is not None and ia is not None:
        equiv = mensal_para_anual(im, Regime.COMPOSTO)
        if abs(equiv - ia) <= Decimal("0.0005"):
            txt = "Taxa anual equivale à capitalização mensal da taxa mensal (taxas equivalentes)."
        elif abs(im * 12 - ia) <= Decimal("0.0005"):
            txt = "Taxa anual é o duodécuplo da mensal (taxas proporcionais, sem capitalização aparente)."
        else:
            txt = f"Taxa anual ({ia}) não é equivalente nem proporcional à mensal ({im}). Verificar periodicidade da capitalização."
        out.append(Ocorrencia(id="taxas-relacao", tipo=O.INFORMACAO, bloqueia=False, texto=txt,
                              fontes=params["contrato.taxa_anual"].fontes))
    return out


def _consolidar_pagamentos(pags: list[PagamentoExtraido]) -> list[PagamentoExtraido]:
    """Uma linha por parcela, preferindo comprovante; sem número de parcela, mantém todos."""
    por: dict[int, PagamentoExtraido] = {}
    sem: list[PagamentoExtraido] = []
    for p in pags:
        if p.parcela is None:
            sem.append(p)
            continue
        atual = por.get(p.parcela)
        if atual is None or (p.fonte.tipo_documento is TipoDocumento.COMPROVANTE
                             and atual.fonte.tipo_documento is not TipoDocumento.COMPROVANTE):
            por[p.parcela] = p
    return [por[k] for k in sorted(por)] + sem


def _documentos_ausentes(docs: list[Documento], pags: list[PagamentoExtraido]) -> list[Ocorrencia]:
    tipos = {d.tipo for d in docs}
    out = []

    def falta(id_, txt, bloqueia=True):
        out.append(Ocorrencia(id=f"ausente-{id_}", tipo=O.DOCUMENTO_AUSENTE, bloqueia=bloqueia, texto=txt))

    if TipoDocumento.CONTRATO not in tipos:
        falta("contrato", "Contrato não localizado entre os documentos.")
    if TipoDocumento.SENTENCA not in tipos:
        falta("sentenca", "Sentença não localizada.")
    if not pags:
        falta("pagamentos", "Nenhum comprovante ou planilha de pagamentos localizado.")
    textos = {d.id: normalizar(d.texto) for d in docs}
    outros = lambda tipo: [t for i, t in textos.items() if next(d for d in docs if d.id == i).tipo is not tipo]  # noqa: E731
    if TipoDocumento.ACORDAO not in tipos and any(re.search(r"apelacao|recurso inominado|turma recursal", t)
                                                  for t in outros(TipoDocumento.PETICAO_INICIAL)):
        falta("acordao", "Há menção a recurso (apelação), mas nenhum acórdão foi localizado.")
    if TipoDocumento.EMBARGOS_DECISAO not in tipos and any(re.search(r"(opostos?|opos|interpost\w*) (os )?embargos de declaracao", t)
                                                           for t in textos.values()):
        falta("embargos", "Há menção a embargos de declaração opostos, mas a decisão que os julgou não foi localizada.")
    if not any(re.search(r"transit\w* em julgado|transito em julgado", t) for t in textos.values()):
        falta("transito", "Trânsito em julgado não comprovado nos documentos (cumprimento provisório?).", bloqueia=False)
    return out


def _unicas(ocorr: list[Ocorrencia]) -> list[Ocorrencia]:
    vistos, out = set(), []
    for o in ocorr:
        if o.id in vistos:
            continue
        vistos.add(o.id)
        out.append(o)
    return out
