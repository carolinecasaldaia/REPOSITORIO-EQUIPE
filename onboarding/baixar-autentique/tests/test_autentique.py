#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regras de leitura da API do Autentique."""

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import autentique  # noqa: E402


def assinatura(nome, email, assinou=None, recusou=None):
    return {
        "public_id": nome.lower(),
        "name": nome,
        "email": email,
        "action": {"name": "SIGN"},
        "user": {"id": "1", "name": nome, "email": email},
        "signed": {"created_at": assinou} if assinou else None,
        "rejected": {"created_at": recusou} if recusou else None,
    }


def documento(assinaturas, **extra):
    dados = {
        "id": "abc123",
        "name": "CONTRATO - PROCURACAO - DECLARACAO - FULANO",
        "created_at": "2026-08-10T12:00:00.000000Z",
        "files": {"original": "https://x/o.pdf",
                  "signed": "https://painel.autentique.com.br/documentos/abc123/assinado.pdf"},
        "signatures": assinaturas,
    }
    dados.update(extra)
    return dados


# --- todas_assinaram -------------------------------------------------------

def test_documento_com_todas_as_partes_assinadas_esta_pronto():
    doc = documento([
        assinatura("Fulano de Tal", "fulano@gmail.com", "2026-08-12T10:00:00.000000Z"),
        assinatura("Caroline Macedo", "contato@carolinemacedoadv.com", "2026-08-12T11:00:00.000000Z"),
    ])
    assert autentique.todas_assinaram(doc) is True


def test_falta_uma_assinatura_entao_nao_baixa():
    doc = documento([
        assinatura("Fulano de Tal", "fulano@gmail.com", "2026-08-12T10:00:00.000000Z"),
        assinatura("Caroline Macedo", "contato@carolinemacedoadv.com"),
    ])
    assert autentique.todas_assinaram(doc) is False
    assert autentique.resumo_assinaturas(doc)["faltam"] == ["Caroline Macedo"]


def test_documento_recusado_nunca_e_considerado_pronto():
    doc = documento([
        assinatura("Fulano", "fulano@gmail.com", "2026-08-12T10:00:00.000000Z"),
        assinatura("Beltrano", "beltrano@gmail.com", recusou="2026-08-12T11:00:00.000000Z"),
    ])
    assert autentique.todas_assinaram(doc) is False


def test_documento_sem_signatarios_nao_e_pronto():
    assert autentique.todas_assinaram(documento([])) is False


def test_contagem_do_autentique_manda_quando_vem_na_resposta():
    """
    A lista pode estar defasada quando um signatário foi adicionado agora.
    Se o Autentique diz que são 3 partes e só 2 assinaram, não está pronto.
    """
    doc = documento(
        [assinatura("Fulano", "f@gmail.com", "2026-08-12T10:00:00.000000Z"),
         assinatura("Caroline", "contato@carolinemacedoadv.com", "2026-08-12T11:00:00.000000Z")],
        signatures_count=3, signed_count=2, rejected_count=0)
    assert autentique.todas_assinaram(doc) is False


def test_arquivo_assinado_sozinho_nao_prova_conclusao():
    """
    `files.signed` é um link fixo do painel: existe mesmo sem ninguém assinar.
    Se ele fosse o critério, contrato pela metade cairia na pasta do cliente.
    """
    doc = documento([assinatura("Fulano", "f@gmail.com")])
    assert doc["files"]["signed"]
    assert autentique.todas_assinaram(doc) is False


# --- datas e signatários ---------------------------------------------------

def test_data_de_conclusao_e_a_da_ultima_assinatura():
    doc = documento([
        assinatura("Fulano", "f@gmail.com", "2026-08-12T10:00:00.000000Z"),
        assinatura("Caroline", "contato@carolinemacedoadv.com", "2026-08-13T09:30:00.000000Z"),
    ])
    assert autentique.quando_ficou_pronto(doc) == "2026-08-13T09:30:00.000000Z"


def test_data_do_autentique_vira_datetime_com_fuso():
    quando = autentique.para_datetime("2026-08-13T09:30:00.000000Z")
    assert (quando.year, quando.month, quando.day, quando.hour) == (2026, 8, 13, 9)
    assert autentique.para_datetime("") is None


def test_signatario_do_escritorio_nao_e_confundido_com_cliente():
    doc = documento([
        assinatura("Caroline Macedo", "contato@carolinemacedoadv.com", "2026-08-12T09:00:00.000000Z"),
        assinatura("Anderson Lopes da Silva", "anderson@gmail.com", "2026-08-12T10:00:00.000000Z"),
    ])
    eh_escritorio = lambda email: email.endswith("@carolinemacedoadv.com")  # noqa: E731
    assert autentique.signatarios_clientes(doc, eh_escritorio) == ["Anderson Lopes da Silva"]


# --- transporte ------------------------------------------------------------

class RespostaFalsa(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def abridor_falso(paginas):
    """Simula o urlopen: devolve as páginas na ordem, e depois vazio."""
    chamadas = {"n": 0}

    def abrir(pedido, timeout=None):
        indice = chamadas["n"]
        chamadas["n"] += 1
        conteudo = paginas[indice] if indice < len(paginas) else {"data": {"documents": {"total": 0, "data": []}}}
        return RespostaFalsa(json.dumps(conteudo).encode("utf-8"))

    abrir.chamadas = chamadas
    return abrir


def test_listar_junta_as_paginas_e_para_quando_acaba():
    pagina1 = {"data": {"documents": {"total": 61,
                                      "data": [documento([], id="d%d" % i) for i in range(60)]}}}
    pagina2 = {"data": {"documents": {"total": 61, "data": [documento([], id="d60")]}}}
    api = autentique.Autentique("chave", abridor=abridor_falso([pagina1, pagina2]), pausa_s=0)
    assert len(api.listar(max_paginas=5, limite=60)) == 61


def test_prontos_filtra_o_que_ainda_falta_assinar():
    pronto = documento([assinatura("A", "a@gmail.com", "2026-08-12T10:00:00.000000Z")], id="pronto")
    meio = documento([assinatura("B", "b@gmail.com")], id="meio")
    pagina = {"data": {"documents": {"total": 2, "data": [pronto, meio]}}}
    api = autentique.Autentique("chave", abridor=abridor_falso([pagina]), pausa_s=0)
    assert [d["id"] for d in api.prontos(max_paginas=1, limite=60)] == ["pronto"]


def test_erro_do_graphql_vira_mensagem_em_portugues():
    pagina = {"errors": [{"message": "Unauthenticated."}]}
    api = autentique.Autentique("chave-ruim", abridor=abridor_falso([pagina]), pausa_s=0)
    with pytest.raises(autentique.ChaveInvalida):
        api.listar(max_paginas=1)


def test_download_recusa_conteudo_que_nao_e_pdf(tmp_path):
    def abrir(pedido, timeout=None):
        return RespostaFalsa(b"<html>faca login</html>")

    api = autentique.Autentique("chave", abridor=abrir, pausa_s=0)
    with pytest.raises(autentique.ErroAutentique):
        api.baixar_pdf("https://painel.autentique.com.br/x/assinado.pdf", tmp_path / "a.pdf")


def test_download_grava_o_pdf(tmp_path):
    def abrir(pedido, timeout=None):
        return RespostaFalsa(b"%PDF-1.4 conteudo")

    api = autentique.Autentique("chave", abridor=abrir, pausa_s=0)
    destino = tmp_path / "a.pdf"
    assert api.baixar_pdf("https://painel.autentique.com.br/x/assinado.pdf", destino) > 0
    assert destino.read_bytes().startswith(b"%PDF")
