#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Achar (e criar) a pasta do cliente."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import pastas  # noqa: E402


def montar(raiz, estrutura):
    """estrutura: {'AGOSTO 2026': ['01 - OK - FULANO', ...]}"""
    for mes, clientes in estrutura.items():
        for cliente in clientes:
            (Path(raiz) / mes / cliente).mkdir(parents=True, exist_ok=True)
    return pastas.varrer(raiz)


# --- limpeza de nome -------------------------------------------------------

def test_tira_numero_marcacao_e_estado_do_nome_da_pasta():
    assert pastas.nome_provavel_do_cliente("01 - OK - ANDESON LOPES DA SILVA") == "ANDESON LOPES DA SILVA"
    assert pastas.nome_provavel_do_cliente("6 - INDICACAO ISRAEL - JOAO WARLLEX - AGUARDANDO DOC") == "JOAO WARLLEX"
    assert pastas.nome_provavel_do_cliente("DAISY AQUINO MENDES - RIO GRANDE DO SUL") == "DAISY AQUINO MENDES"


def test_nomes_tirados_do_titulo_do_envelope():
    assert pastas.nomes_do_documento("CONTRATO - PROCURAÇÃO - DECLARAÇÃO - ANDERSON") == ["ANDERSON"]
    assert pastas.nomes_do_documento("CONTRATO DE HONORÁRIOS") == []


# --- semelhança ------------------------------------------------------------

def test_erro_de_digitacao_na_pasta_nao_impede_o_casamento():
    """A pasta diz ANDESON, o contrato diz ANDERSON — é a mesma pessoa."""
    assert pastas.pontuacao("ANDERSON LOPES DA SILVA", "ANDESON LOPES DA SILVA") > 0.9


def test_nome_abreviado_casa_com_o_completo():
    assert pastas.pontuacao("MARIA PEDROSA", "MARIA PEDROSA DE MORAIS BARROS") > 0.9


def test_pessoas_diferentes_nao_casam():
    assert pastas.pontuacao("MARIA PEDROSA DE MORAIS", "LUCIANA DUARTE DE OLIVEIRA") < 0.6


# --- busca -----------------------------------------------------------------

def test_acha_a_pasta_do_cliente_pelo_nome_do_signatario(tmp_path):
    candidatas = montar(tmp_path, {"AGOSTO 2026": ["01 - OK - ANDESON LOPES DA SILVA",
                                                   "LUCIANA DUARTE DE OLIVEIRA"]})
    achado = pastas.localizar(candidatas, ["Anderson Lopes da Silva"], 0.88)
    assert achado.achou
    assert achado.pasta.nome_pasta == "01 - OK - ANDESON LOPES DA SILVA"


def test_cliente_sem_pasta_nao_e_empurrado_para_a_pasta_de_outro(tmp_path):
    candidatas = montar(tmp_path, {"AGOSTO 2026": ["LUCIANA DUARTE DE OLIVEIRA"]})
    achado = pastas.localizar(candidatas, ["Roberto Araujo de Oliveira"], 0.88)
    assert not achado.achou
    assert achado.situacao == "nao_achou"


def test_duas_pastas_parecidas_viram_pendencia_em_vez_de_chute(tmp_path):
    candidatas = montar(tmp_path, {"AGOSTO 2026": ["MARIA SANTOS SILVA", "MARIA SANTOS SILVEIRA"]})
    achado = pastas.localizar(candidatas, ["Maria Santos Silva"], 0.88)
    if achado.achou:
        # casamento exato vence o parecido — é o desejado
        assert achado.pasta.nome_pasta == "MARIA SANTOS SILVA"
    else:
        assert achado.situacao == "ambiguo"


def test_mesmo_cliente_em_dois_meses_escolhe_o_mes_mais_recente(tmp_path):
    candidatas = montar(tmp_path, {"JULHO 2026": ["15 - ANDESON LOPES DA SILVA"],
                                   "AGOSTO 2026": ["01 - OK - ANDESON LOPES DA SILVA"]})
    achado = pastas.localizar(candidatas, ["Anderson Lopes da Silva"], 0.88)
    assert achado.achou
    assert achado.pasta.mes == "AGOSTO 2026"


def test_sem_nome_de_signatario_nao_tenta_adivinhar(tmp_path):
    candidatas = montar(tmp_path, {"AGOSTO 2026": ["FULANO DE TAL"]})
    assert not pastas.localizar(candidatas, [], 0.88).achou


# --- criação ---------------------------------------------------------------

def test_cria_pasta_do_mes_com_as_cinco_subpastas(tmp_path):
    destino = pastas.criar_pasta_cliente(tmp_path, "Fulano de Tal Souza",
                                         datetime(2026, 8, 17))
    assert destino == tmp_path / "AGOSTO 2026" / "FULANO DE TAL SOUZA"
    for subpasta in ("CONTRATO HO", "DOC CLIENTE", "DOC ESCRITÓRIO", "ONBOARDING", "PETIÇÕES"):
        assert (destino / subpasta).is_dir()


def test_reaproveita_a_pasta_do_mes_que_ja_existe(tmp_path):
    (tmp_path / "AGOSTO 2026").mkdir()
    destino = pastas.criar_pasta_cliente(tmp_path, "Outro Cliente", datetime(2026, 8, 17))
    assert destino.parent == tmp_path / "AGOSTO 2026"
    assert len(list(tmp_path.iterdir())) == 1


def test_nome_com_barra_nao_cria_subpasta_indevida(tmp_path):
    destino = pastas.criar_pasta_cliente(tmp_path, "Fulano / Beltrano", datetime(2026, 8, 17))
    assert destino.parent.name == "AGOSTO 2026"
    assert "/" not in destino.name


def test_duas_pastas_do_mesmo_cliente_no_mesmo_mes_sao_ambiguas(tmp_path):
    """
    Envelope com dois contratos vira "<NOME> - CONTRATO 1" e "- CONTRATO 2".
    O nome do cliente é o mesmo nas duas; escolher uma seria chute.
    """
    from src import pastas
    for sufixo in ("CONTRATO 1", "CONTRATO 2"):
        (tmp_path / "SETEMBRO 2026" / ("SOFIA EVANGELISTA ARRUDA DE OLIVEIRA - %s" % sufixo)).mkdir(parents=True)
    achado = pastas.localizar(pastas.varrer(tmp_path), ["SOFIA EVANGELISTA ARRUDA DE OLIVEIRA"])
    assert achado.situacao == "ambiguo"


def test_mesmo_cliente_em_meses_diferentes_fica_com_o_mais_recente(tmp_path):
    """O caso que a regra antiga protegia continua valendo."""
    from src import pastas
    (tmp_path / "JULHO 2026" / "15 - ANDESON LOPES DA SILVA").mkdir(parents=True)
    (tmp_path / "AGOSTO 2026" / "01 - OK - ANDESON LOPES DA SILVA").mkdir(parents=True)
    achado = pastas.localizar(pastas.varrer(tmp_path), ["ANDESON LOPES DA SILVA"])
    assert achado.achou
    assert achado.pasta.mes == "AGOSTO 2026"
