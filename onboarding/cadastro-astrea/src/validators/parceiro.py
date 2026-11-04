#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Casos que são do PARCEIRO — não entram na automação do Astrea.

Decisão dela (02/10/2026): contrato cujo detalhamento do objeto é "adicional
de insalubridade e reflexos" é tocado pelo escritório parceiro. Ninguém é
cadastrado no Astrea e nenhum caso é aberto. O contrato continua sendo
baixado do Autentique e arquivado na pasta do cliente, com onboarding — o
que muda é só o Astrea.

A conferência é pelo OBJETO (cláusula 1ª), não pelo tipo de ação: é o objeto
que ela usou para descrever esses casos, e o tipo de ação do contrato de
honorários desses clientes pode vir escrito de várias formas.

Para incluir outro assunto do parceiro no futuro, acrescente um termo em
ASSUNTOS — a comparação ignora acento e maiúscula.
"""

import unicodedata

ASSUNTOS = (
    "insalubridade",
)


def _simples(texto: str) -> str:
    cru = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in cru if unicodedata.category(c) != "Mn")


def e_do_parceiro(objeto: str) -> bool:
    """O objeto do contrato é de um assunto que o parceiro cuida?"""
    alvo = _simples(objeto)
    return any(assunto in alvo for assunto in ASSUNTOS)


def motivo(objeto: str) -> str:
    achados = [a for a in ASSUNTOS if a in _simples(objeto)]
    return ("CASO DO PARCEIRO (%s) — não cadastra no Astrea nem abre caso."
            % ", ".join(achados))
