#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chamada do gerador de onboarding.

O gerador de verdade abre um Chrome invisível; aqui ele é trocado por um script
que se comporta igual nos três desfechos que importam: gerou, faltou campo
obrigatório (busca e apreensão sem banco) e quebrou.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import onboarding  # noqa: E402

GERADOR_QUE_GERA = '''import sys
from pathlib import Path
pasta = Path(sys.argv[1])
destino = pasta / "ONBOARDING"
destino.mkdir(parents=True, exist_ok=True)
(destino / "onboarding_fulano.pdf").write_bytes(b"%PDF-1.4 onboarding")
print("  onboarding_fulano.pdf")
'''

GERADOR_QUE_PEDE_BANCO = '''import sys
print("Falta preencher: Banco adverso. Rode sem argumentos para preencher na tela.",
      file=sys.stderr)
sys.exit(1)
'''

GERADOR_QUE_QUEBRA = '''import sys
print("não encontrei o Google Chrome", file=sys.stderr)
sys.exit(2)
'''


class ConfigFalsa(object):
    def __init__(self, gerador, python=None):
        self.gerador_onboarding = gerador
        self.python_onboarding = python or Path(sys.executable)


@pytest.fixture
def cliente(tmp_path):
    pasta = tmp_path / "AGOSTO 2026" / "FULANO DE TAL"
    for sub in ("CONTRATO HO", "ONBOARDING"):
        (pasta / sub).mkdir(parents=True)
    return pasta


def escrever_gerador(tmp_path, codigo):
    caminho = tmp_path / "gerador_falso.py"
    caminho.write_text(codigo, encoding="utf-8")
    return caminho


def test_gera_o_onboarding_na_subpasta_do_cliente(cliente, tmp_path):
    config = ConfigFalsa(escrever_gerador(tmp_path, GERADOR_QUE_GERA))

    feito = onboarding.gerar(cliente, config)

    assert feito["situacao"] == "gerado"
    assert feito["arquivo"].name == "onboarding_fulano.pdf"
    assert (cliente / "ONBOARDING" / "onboarding_fulano.pdf").exists()


def test_busca_e_apreensao_sem_banco_vira_recado_e_nao_erro(cliente, tmp_path):
    config = ConfigFalsa(escrever_gerador(tmp_path, GERADOR_QUE_PEDE_BANCO))

    feito = onboarding.gerar(cliente, config)

    assert feito["situacao"] == "pendente"
    assert "Banco adverso" in feito["motivo"]
    assert "Gerar Onboarding do Cliente" in feito["motivo"]


def test_falha_do_gerador_nao_derruba_a_rodada(cliente, tmp_path):
    config = ConfigFalsa(escrever_gerador(tmp_path, GERADOR_QUE_QUEBRA))

    feito = onboarding.gerar(cliente, config)

    assert feito["situacao"] == "erro"
    assert "Chrome" in feito["motivo"]


def test_onboarding_que_ja_existe_nao_e_gerado_de_novo(cliente, tmp_path):
    """Sem isso o gerador criaria um 'onboarding_fulano (2).pdf'."""
    (cliente / "ONBOARDING" / "onboarding_fulano.pdf").write_bytes(b"%PDF-1.4 antigo")
    config = ConfigFalsa(escrever_gerador(tmp_path, GERADOR_QUE_GERA))

    feito = onboarding.gerar(cliente, config)

    assert feito["situacao"] == "ja_existia"
    assert len(list((cliente / "ONBOARDING").glob("*.pdf"))) == 1


def test_ambiente_do_gerador_ausente_avisa_o_que_fazer(cliente, tmp_path):
    config = ConfigFalsa(escrever_gerador(tmp_path, GERADOR_QUE_GERA),
                         python=tmp_path / "nao-existe" / "python")

    feito = onboarding.gerar(cliente, config)

    assert feito["situacao"] == "erro"
    assert "Gerar Onboarding do Cliente" in feito["motivo"]
