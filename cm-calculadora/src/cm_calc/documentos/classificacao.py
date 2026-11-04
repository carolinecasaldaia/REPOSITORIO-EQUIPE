"""Classificação de documentos por regras locais (palavras-chave com pesos).

Cada tipo tem marcadores de CABEÇALHO (fortes, procurados no início da
página) e marcadores de CORPO (fracos). A pontuação e os indícios ficam
registrados para conferência. Abaixo do limiar mínimo, o documento fica
como "não classificado" — nunca é forçado num tipo.
"""

from __future__ import annotations

import re

from .modelos import TipoDocumento as T
from .texto import normalizar

CABECALHO = {
    T.CONTRATO: [r"cedula de credito bancario", r"contrato de financiamento", r"contrato de abertura de credito",
                 r"quadro resumo", r"alienacao fiduciaria em garantia"],
    T.SENTENCA: [r"\bsentenca\b"],
    T.ACORDAO: [r"\bacordao\b", r"\bementa\b"],
    T.EMBARGOS_DECISAO: [r"embargos de declaracao"],
    T.DECISAO: [r"\bdecisao\b", r"\bdespacho\b", r"decisao monocratica"],
    T.PETICAO_INICIAL: [r"excelentissim[oa]", r"peticao inicial"],
    T.CONTESTACAO: [r"\bcontestacao\b"],
    T.RECURSO: [r"razoes de (apelacao|recurso)", r"recurso de apelacao", r"razoes recursais"],
    T.COMPROVANTE: [r"comprovante de pagamento", r"\brecibo\b", r"comprovante de transacao", r"autenticacao mecanica"],
    T.LAUDO: [r"\blaudo\b", r"parecer tecnico", r"parecer pericial"],
    T.CERTIDAO: [r"\bcertidao\b", r"certifico"],
}

CORPO = {
    T.CONTRATO: [r"emitente", r"credor", r"taxa de juros", r"\biof\b", r"parcelas?", r"custo efetivo total"],
    T.SENTENCA: [r"julgo (parcialmente )?(im)?procedente", r"relatorio", r"fundamento", r"publique-se",
                 r"resolvo o merito", r"art\.? 487"],
    T.ACORDAO: [r"acordam", r"relator", r"(dar|nego|negar|dou) (parcial )?provimento", r"camara", r"turma",
                r"votacao unanime|por unanimidade"],
    T.EMBARGOS_DECISAO: [r"(acolho|rejeito|conheco)[^.]{0,60}embargos", r"omissao|contradicao|obscuridade",
                         r"art\.? 1\.?022"],
    T.DECISAO: [r"defiro|indefiro", r"intime-se", r"cumpra-se"],
    T.PETICAO_INICIAL: [r"vem.{0,40}propor", r"dos pedidos", r"requer", r"da a causa o valor", r"dos fatos"],
    T.CONTESTACAO: [r"apresentar contestacao", r"preliminar", r"improcedencia (dos|do) pedidos?"],
    T.RECURSO: [r"reforma da sentenca", r"apelante", r"pede provimento"],
    T.COMPROVANTE: [r"valor pago", r"data do pagamento", r"autenticacao", r"pagamento efetuado"],
    T.LAUDO: [r"perito", r"quesitos", r"apendice|ap0\d"],
    T.CERTIDAO: [r"transitou em julgado|transito em julgado", r"escriv|servidor"],
}

LIMIAR = 3.0
PESO_CABECALHO = 4.0
PESO_CORPO = 1.0


def pontuar(texto: str) -> dict[T, tuple[float, list[str]]]:
    norm = normalizar(texto)
    topo = norm[:500]
    out: dict[T, tuple[float, list[str]]] = {}
    for tipo in CABECALHO:
        pts, ind = 0.0, []
        for pad in CABECALHO[tipo]:
            if re.search(pad, topo):
                pts += PESO_CABECALHO
                ind.append(f"cabeçalho: {pad}")
        for pad in CORPO[tipo]:
            if re.search(pad, norm):
                pts += PESO_CORPO
                ind.append(f"corpo: {pad}")
        out[tipo] = (pts, ind)
    return out


def classificar(texto: str) -> tuple[T, float, list[str]]:
    """Tipo, confiança (0–1) e indícios. Desempates registrados como indício."""
    pts = pontuar(texto)
    norm = normalizar(texto)
    # Ajustes de precedência que palavras-chave isoladas não resolvem:
    # 'embargos de declaração' numa petição não é decisão; decisão exige verbo decisório.
    if pts[T.EMBARGOS_DECISAO][0] and not re.search(r"(acolho|rejeito|conheco|acolhe-se|rejeita-se)", norm):
        pts[T.EMBARGOS_DECISAO] = (0.0, pts[T.EMBARGOS_DECISAO][1] + ["sem verbo decisório: descartado"])
    if pts[T.EMBARGOS_DECISAO][0] >= LIMIAR:
        # o cabeçalho 'acórdão'/'decisão' de quem julga embargos não deve vencer
        for t in (T.ACORDAO, T.DECISAO, T.SENTENCA):
            pts[t] = (pts[t][0] - PESO_CABECALHO, pts[t][1])
    if pts[T.SENTENCA][0] >= LIMIAR and pts[T.DECISAO][0] > 0:
        pts[T.DECISAO] = (pts[T.DECISAO][0] - PESO_CABECALHO, pts[T.DECISAO][1])

    ordem = sorted(pts.items(), key=lambda kv: kv[1][0], reverse=True)
    (tipo, (p1, ind)), (_, (p2, _)) = ordem[0], ordem[1]
    if p1 < LIMIAR:
        return T.DESCONHECIDO, 0.0, [f"pontuação máxima {p1} abaixo do limiar {LIMIAR}"]
    confianca = min(1.0, (p1 - max(p2, 0)) / (p1 + 1e-9) + 0.3)
    if p1 - p2 < 2:
        ind = ind + [f"margem pequena sobre o 2º colocado ({ordem[1][0].value}: {p2})"]
    return tipo, round(confianca, 2), ind


def inicia_documento(texto_pagina: str) -> bool:
    """A página parece abrir um novo documento (marcador forte no topo)."""
    topo = normalizar(texto_pagina)[:300]
    return any(re.search(p, topo) for pads in CABECALHO.values() for p in pads)


def embargos_contra_acordao(texto: str) -> bool:
    return bool(re.search(r"\bacordao\b|turma|camara|relator", normalizar(texto)))
