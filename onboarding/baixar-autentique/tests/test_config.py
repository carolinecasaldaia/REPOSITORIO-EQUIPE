#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnóstico de acesso à pasta dos clientes.

Existe por causa de 17/08/2026: a primeira rodada automática morreu com
"Operation not permitted" no Google Drive e a mensagem que aparecia era
"pasta não encontrada, ajuste PASTA_CLIENTES" — que manda consertar a coisa
errada. Bloqueio de privacidade e pasta inexistente não podem se confundir.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config as C  # noqa: E402


def config_de(tmp_path, monkeypatch):
    monkeypatch.setenv("PASTA_CLIENTES", str(tmp_path))
    monkeypatch.setenv("AUTENTIQUE_TOKEN", "chave-de-teste")
    return C.get_config(recarregar=True)


def test_pasta_acessivel_nao_reclama(tmp_path, monkeypatch):
    assert config_de(tmp_path, monkeypatch).acesso_a_pasta_clientes() == ""


def test_bloqueio_do_macos_ensina_o_caminho_da_liberacao(tmp_path, monkeypatch):
    cfg = config_de(tmp_path, monkeypatch)

    def negar(_caminho):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "listdir", negar)
    recado = cfg.acesso_a_pasta_clientes()

    assert "Acesso Total ao Disco" in recado
    assert C.BINARIO_PYTHON_REAL in recado, "tem que dizer QUAL arquivo liberar"
    assert "atalho" in recado, "e que pelo atalho continua funcionando"
    assert cfg.problemas(), "bloqueio impede a rodada"


def test_pasta_que_nao_existe_continua_com_a_mensagem_certa(tmp_path, monkeypatch):
    monkeypatch.setenv("PASTA_CLIENTES", str(tmp_path / "nao-existe"))
    monkeypatch.setenv("AUTENTIQUE_TOKEN", "chave-de-teste")
    recado = C.get_config(recarregar=True).acesso_a_pasta_clientes()

    assert "não foi encontrada" in recado
    assert "Google Drive está aberto" in recado
    assert "Acesso Total ao Disco" not in recado
