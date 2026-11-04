#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF de mentira para os testes.

Monta um PDF de verdade (com camada de texto) sem depender de biblioteca de
geração — o que interessa é a primeira linha de cada página, que é o que o
separador usa para decidir onde cortar.
"""


def _escapar(texto: str) -> str:
    return texto.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def escrever_pdf(caminho, primeiras_linhas):
    """Cria um PDF com uma página por item de `primeiras_linhas`."""
    total = len(primeiras_linhas)
    objetos = []

    # 1: catálogo | 2: páginas | 3..: páginas, conteúdos e a fonte
    id_paginas = [3 + i * 2 for i in range(total)]
    id_conteudos = [4 + i * 2 for i in range(total)]
    id_fonte = 3 + total * 2

    objetos.append("<< /Type /Catalog /Pages 2 0 R >>")
    objetos.append("<< /Type /Pages /Kids [%s] /Count %d >>"
                   % (" ".join("%d 0 R" % i for i in id_paginas), total))

    for pagina in range(total):
        objetos.append(
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            "/Contents %d 0 R /Resources << /Font << /F1 %d 0 R >> >> >>"
            % (id_conteudos[pagina], id_fonte))
        fluxo = ("BT /F1 14 Tf 72 720 Td (%s) Tj ET"
                 % _escapar(primeiras_linhas[pagina]))
        objetos.append("<< /Length %d >>\nstream\n%s\nendstream" % (len(fluxo), fluxo))

    objetos.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                   "/Encoding /WinAnsiEncoding >>")

    corpo = b"%PDF-1.4\n"
    posicoes = []
    for numero, objeto in enumerate(objetos, start=1):
        posicoes.append(len(corpo))
        corpo += ("%d 0 obj\n%s\nendobj\n" % (numero, objeto)).encode("latin-1")

    inicio_xref = len(corpo)
    corpo += ("xref\n0 %d\n" % (len(objetos) + 1)).encode("latin-1")
    corpo += b"0000000000 65535 f \n"
    for posicao in posicoes:
        corpo += ("%010d 00000 n \n" % posicao).encode("latin-1")
    corpo += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
              % (len(objetos) + 1, inicio_xref)).encode("latin-1")

    with open(str(caminho), "wb") as arquivo:
        arquivo.write(corpo)
    return caminho


def envelope_de_onboarding(caminho, contratante="FULANO DE TAL SOUZA", responsavel=""):
    """
    Envelope igual ao que o Autentique devolve no onboarding.

    A segunda página repete a qualificação como ela sai no contrato de verdade
    ("...como Cliente Contratante NOME, brasileiro, ..."), que é de onde o nome
    do cliente é lido.
    """
    qualificacao = ("e do outro lado, como Cliente Contratante %s, brasileiro, "
                    "divorciado, motorista, portador do RG sob o n 1528220" % contratante)
    if responsavel:
        qualificacao += (" e, como Cliente Responsavel %s, brasileira, casada, "
                         "autonoma, portadora do RG" % responsavel)
    return escrever_pdf(caminho, [
        "CONTRATO DE PRESTACAO DE SERVICOS ADVOCATICIOS",
        qualificacao,
        "PROCURACAO",
        "DECLARACAO DE HIPOSSUFICIENCIA",
        "Identificador: 3f2a9 autentique.com.br assinaturas do documento",
    ])


def documento_qualquer(caminho):
    """Documento assinado que NÃO é do onboarding (não pode entrar na pasta)."""
    return escrever_pdf(caminho, [
        "TERMO DE ACORDO EXTRAJUDICIAL",
        "Identificador: 77bb1 autentique.com.br assinaturas do documento",
    ])
