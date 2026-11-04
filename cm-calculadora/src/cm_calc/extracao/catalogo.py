"""Catálogo de cobranças acessórias (tarifas, seguros, serviços) e seus padrões.

Os padrões operam sobre texto normalizado (minúsculo, sem acentos). O
catálogo é o ponto de ajuste quando um contrato usar outra nomenclatura.
"""

from __future__ import annotations

import re

from ..motor.composicao import TipoItem

ITENS: dict[str, tuple[TipoItem, str]] = {
    "tarifa de cadastro": (TipoItem.TARIFA, r"tarifa de cadastro"),
    "tarifa de avaliacao do bem": (TipoItem.TARIFA, r"(tarifa de )?avaliacao (do bem|de bem|do veiculo)|tarifa de avaliacao"),
    "registro de contrato": (TipoItem.TARIFA, r"(tarifa de |despesa de |despesas com )?registro (do |de )?(contrato|gravame)"),
    "seguro prestamista": (TipoItem.SEGURO, r"seguro prestamista|seguro de protecao financeira|seguro de credito"),
    "servicos de terceiros": (TipoItem.SERVICO, r"servicos? de terceiros|servicos? prestados por terceiros"),
    "titulo de capitalizacao": (TipoItem.SERVICO, r"titulo de capitalizacao"),
    "tarifa de abertura de credito": (TipoItem.TARIFA, r"tarifa de abertura de credito|\btac\b"),
    "tarifa de emissao de carne": (TipoItem.TARIFA, r"tarifa de emissao de (carne|boleto)|\btec\b"),
    "iof": (TipoItem.IOF, r"\biof\b|imposto sobre operacoes financeiras"),
}


def itens_no_texto(norm: str) -> list[tuple[str, int, int]]:
    """(chave do item, início, fim) de cada menção no texto normalizado."""
    out = []
    for chave, (_, pad) in ITENS.items():
        for m in re.finditer(pad, norm):
            out.append((chave, m.start(), m.end()))
    return sorted(out, key=lambda x: x[1])


def id_item(chave: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", chave).strip("_")
