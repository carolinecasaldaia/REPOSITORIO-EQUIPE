"""Consolidação do título: decisões posteriores modificam as anteriores por tema.

Ordem: sentença -> embargos contra a sentença -> acórdão -> embargos contra
o acórdão -> decisões posteriores. Havendo data em todas as decisões, a data
desempata dentro da mesma posição.

Por tema (``Comando.chave``), prevalece o comando da decisão mais recente que
tratou daquele tema; o anterior fica registrado como modificado. Recurso
desprovido / embargos rejeitados sem comandos próprios = sentença mantida.

Situações que exigem leitura humana (geram ocorrência bloqueante):
- recurso provido/parcialmente provido sem capítulo identificado;
- reforma do resultado (ex.: procedente -> improcedente);
- comandos contraditórios no mesmo dispositivo.
"""

from __future__ import annotations

from datetime import date

from ..documentos.modelos import Natureza, TipoDocumento
from .modelos import Comando, Modificacao, Ocorrencia, TipoOcorrencia

POSICAO = {
    TipoDocumento.SENTENCA: 1,
    TipoDocumento.EMBARGOS_DECISAO: 2,   # +2 se contra acórdão (ver _posicao)
    TipoDocumento.ACORDAO: 3,
    TipoDocumento.DECISAO: 5,
}


def _posicao(c: Comando, superior: dict[str, bool]) -> tuple[int, date]:
    p = POSICAO.get(c.documento_tipo, 9)
    if c.documento_tipo is TipoDocumento.EMBARGOS_DECISAO and superior.get(c.fonte.documento_id):
        p = 4
    return p, c.documento_data or date.min


def consolidar(comandos: list[Comando], superior: dict[str, bool]) -> tuple[list[Comando], list[Modificacao], list[Ocorrencia]]:
    reconhecidos = [c for c in comandos if c.natureza is Natureza.RECONHECIDO]
    por_doc: dict[str, list[Comando]] = {}
    for c in reconhecidos:
        por_doc.setdefault(c.fonte.documento_id, []).append(c)
    ordem_docs = sorted(por_doc, key=lambda d: _posicao(por_doc[d][0], superior))

    vigentes: dict[str, Comando] = {}
    modificacoes: list[Modificacao] = []
    ocorr: list[Ocorrencia] = []

    for doc_id in ordem_docs:
        cmds = por_doc[doc_id]
        tipo = cmds[0].documento_tipo
        proprios = [c for c in cmds if c.chave not in ("resultado_recurso", "resultado_embargos")]
        proprios = _unir_mesmo_dispositivo(proprios)

        # contradição dentro do mesmo dispositivo
        por_chave: dict[str, set[str]] = {}
        for c in proprios:
            por_chave.setdefault(c.chave, set()).add(c.efeito)
        for chave, efeitos in por_chave.items():
            if len(efeitos) > 1 and chave != "honorarios":
                ocorr.append(Ocorrencia(
                    id=f"contradicao-{doc_id}-{chave}", tipo=TipoOcorrencia.CONTRADICAO, bloqueia=True,
                    texto=f"{tipo.value}: comandos divergentes para '{chave}' no mesmo dispositivo ({', '.join(sorted(efeitos))}).",
                    fontes=[c.fonte for c in proprios if c.chave == chave]))

        rec = next((c for c in cmds if c.chave == "resultado_recurso"), None)
        if rec and rec.efeito != "negado provimento" and not proprios:
            ocorr.append(Ocorrencia(
                id=f"provimento-sem-capitulo-{doc_id}", tipo=TipoOcorrencia.INSUFICIENTE, bloqueia=True,
                texto=f"{tipo.value}: recurso com '{rec.efeito}', mas sem capítulos identificados no dispositivo. "
                      "Verificar quais pontos da sentença foram reformados.", fontes=[rec.fonte]))

        for c in proprios:
            anterior = vigentes.get(c.chave)
            if c.chave == "honorarios" and c.efeito == "majorados" and anterior is not None:
                novo = c.model_copy(update={"detalhes": {**anterior.detalhes, **c.detalhes},
                                            "lacunas": [l for l in c.lacunas if "base" not in l or "base" not in anterior.detalhes]})
                c = novo
            if anterior is not None and (anterior.efeito != c.efeito or anterior.detalhes != c.detalhes):
                modificacoes.append(Modificacao(
                    chave=c.chave, anterior=anterior, posterior=c,
                    descricao=f"{c.tema.value}: {anterior.documento_tipo.value} ({anterior.fonte.referencia()}) "
                              f"'{anterior.efeito}' -> {c.documento_tipo.value} ({c.fonte.referencia()}) '{c.efeito}'"))
                if c.chave == "resultado":
                    ocorr.append(Ocorrencia(
                        id=f"reforma-resultado-{doc_id}", tipo=TipoOcorrencia.MODIFICACAO, bloqueia=True,
                        texto=f"Resultado do julgamento alterado ('{anterior.efeito}' -> '{c.efeito}'). "
                              "Revisar todos os capítulos da decisão anterior.", fontes=[anterior.fonte, c.fonte]))
            vigentes[c.chave] = c
        if rec:
            vigentes["resultado_recurso"] = rec
        emb = next((c for c in cmds if c.chave == "resultado_embargos"), None)
        if emb:
            vigentes[f"resultado_embargos:{doc_id}"] = emb

    for m in modificacoes:
        ocorr.append(Ocorrencia(id=f"mod-{m.chave}-{m.posterior.fonte.documento_id}", tipo=TipoOcorrencia.MODIFICACAO,
                                bloqueia=False, texto=m.descricao, fontes=[m.posterior.fonte]))
    return list(vigentes.values()), modificacoes, ocorr


def _unir_mesmo_dispositivo(cmds: list[Comando]) -> list[Comando]:
    """Cláusulas do mesmo dispositivo sobre o mesmo tema e efeito viram um comando
    (detalhes somados; lacuna só permanece se nenhuma cláusula a supriu).
    Efeitos diferentes são mantidos separados (contradição)."""
    unidos: dict[tuple[str, str], Comando] = {}
    for c in cmds:
        k = (c.chave, c.efeito)
        if k not in unidos:
            unidos[k] = c
            continue
        a = unidos[k]
        det = {**c.detalhes, **a.detalhes}
        lac = [l for l in a.lacunas if l in c.lacunas]
        unidos[k] = a.model_copy(update={"detalhes": det, "lacunas": lac})
    return list(unidos.values())
