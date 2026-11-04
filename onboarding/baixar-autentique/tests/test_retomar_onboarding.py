#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Onboardings pendentes tentados de novo a cada rodada.

Pedido dela em 18/09/2026: os documentos da Gisleine chegaram dois dias depois
do contrato, e o onboarding ficou parado esperando o banco — nada tentava de
novo. A regra que não pode quebrar: NUNCA gerar um segundo onboarding.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import onboarding, pastas, servico  # noqa: E402


class EstadoFalso(object):
    def __init__(self, documentos):
        self.documentos = documentos

    def anotar(self, doc_id, **campos):
        self.documentos.setdefault(doc_id, {}).update(campos)


class LogMudo(object):
    def info(self, *a, **k): pass
    def ok(self, *a, **k): pass
    def aviso(self, *a, **k): pass


class Config(object):
    gerar_onboarding = True
    timeout_onboarding_s = 5


@pytest.fixture
def raiz(tmp_path):
    (tmp_path / "SETEMBRO 2026").mkdir()
    return tmp_path


def _cliente(raiz, nome, com_onboarding=False):
    pasta = raiz / "SETEMBRO 2026" / nome
    (pasta / "ONBOARDING").mkdir(parents=True)
    if com_onboarding:
        (pasta / "ONBOARDING" / "onboarding_x.pdf").write_bytes(b"%PDF-1.4")
    return pasta


@pytest.fixture
def geracoes(monkeypatch):
    feitas = []

    def gerar(pasta, config, timeout=0):
        feitas.append(Path(pasta).name)
        (Path(pasta) / "ONBOARDING" / "onboarding_novo.pdf").write_bytes(b"%PDF-1.4")
        return {"situacao": "gerado", "arquivo": None, "motivo": "Onboarding gerado."}
    monkeypatch.setattr(onboarding, "gerar", gerar)
    return feitas


def _rodar(raiz, documentos, somente_conferir=False):
    estado = EstadoFalso(documentos)
    retomados = servico.retomar_onboardings(Config(), estado, LogMudo(),
                                            pastas.varrer(raiz), somente_conferir)
    return estado, retomados


def test_gera_o_que_estava_esperando_o_banco(raiz, geracoes):
    pasta = _cliente(raiz, "GISLEINE PEREIRA JARDIM")
    estado, retomados = _rodar(raiz, {"d1": {"onboarding": "pendente", "cliente": "GISLEINE PEREIRA JARDIM",
                                             "pasta": str(pasta)}})
    assert geracoes == ["GISLEINE PEREIRA JARDIM"]
    assert retomados == ["GISLEINE PEREIRA JARDIM"]
    assert estado.documentos["d1"]["onboarding"] == "gerado"


def test_onboarding_feito_a_mao_nao_e_refeito(raiz, geracoes):
    """A maioria dos 14 pendentes de 18/09 já tinha sido resolvida à mão."""
    pasta = _cliente(raiz, "JOICE LEVANDOWSKI", com_onboarding=True)
    estado, retomados = _rodar(raiz, {"d1": {"onboarding": "pendente", "cliente": "JOICE LEVANDOWSKI",
                                             "pasta": str(pasta)}})
    assert geracoes == []
    assert retomados == []
    assert estado.documentos["d1"]["onboarding"] == "ja_existia", "para de tentar"


def test_pasta_renomeada_para_ok_e_encontrada_pelo_nome(raiz, geracoes):
    """Ela põe '01 - OK -' no nome quando manda para o jurídico."""
    _cliente(raiz, "01 - OK - RAFAEL WAGNER ALBINO MANGABEIRA")
    velho = str(raiz / "SETEMBRO 2026" / "RAFAEL WAGNER ALBINO MANGABEIRA")     # não existe mais
    estado, _ = _rodar(raiz, {"d1": {"onboarding": "pendente",
                                     "cliente": "RAFAEL WAGNER ALBINO MANGABEIRA", "pasta": velho}})
    assert geracoes == ["01 - OK - RAFAEL WAGNER ALBINO MANGABEIRA"]
    assert estado.documentos["d1"]["pasta"].endswith("01 - OK - RAFAEL WAGNER ALBINO MANGABEIRA")


def test_duas_pastas_parecidas_nao_escolhe(raiz, geracoes):
    """A Sofia virou duas pastas: na dúvida, não mexe."""
    _cliente(raiz, "SOFIA EVANGELISTA ARRUDA DE OLIVEIRA - CONTRATO 1")
    _cliente(raiz, "SOFIA EVANGELISTA ARRUDA DE OLIVEIRA - CONTRATO 2")
    velho = str(raiz / "SETEMBRO 2026" / "SOFIA EVANGELISTA ARRUDA DE OLIVEIRA")
    estado, _ = _rodar(raiz, {"d1": {"onboarding": "pendente",
                                     "cliente": "SOFIA EVANGELISTA ARRUDA DE OLIVEIRA", "pasta": velho}})
    assert geracoes == []
    assert estado.documentos["d1"]["onboarding"] == "pendente"


def test_so_conferir_nao_gera_nem_grava(raiz, geracoes):
    pasta = _cliente(raiz, "WELLINGTA DE SOUSA SILVA FERREIRA")
    estado, _ = _rodar(raiz, {"d1": {"onboarding": "pendente", "cliente": "WELLINGTA",
                                     "pasta": str(pasta)}}, somente_conferir=True)
    assert geracoes == []
    assert estado.documentos["d1"]["onboarding"] == "pendente"


def test_quem_nao_esta_pendente_nao_e_tocado(raiz, geracoes):
    pasta = _cliente(raiz, "EDIELSON PEREIRA DE OLIVEIRA")
    estado, _ = _rodar(raiz, {"d1": {"onboarding": "gerado", "cliente": "EDIELSON",
                                     "pasta": str(pasta)}})
    assert geracoes == []
