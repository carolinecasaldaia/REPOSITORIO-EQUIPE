#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aviso na tela do Mac.

O teste que interessa é o do acento: a primeira versão montava o script com
json.dumps e o AppleScript recusava `\\u00c1`, então o aviso morria calado
justamente nos nomes reais ("MARIA NIZETE ... ARAÚJO").
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import aviso  # noqa: E402


# --- escape ----------------------------------------------------------------

def test_acento_vai_inteiro_para_o_applescript():
    assert aviso.aspas("MARIA NIZETE ARAÚJO") == '"MARIA NIZETE ARAÚJO"'
    assert "\\u" not in aviso.aspas("Ação de Obrigação · Ç ã é")


def test_aspas_e_barra_sao_escapadas():
    assert aviso.aspas('Fulano "Beltrano"') == '"Fulano \\"Beltrano\\""'
    assert aviso.aspas("caminho\\pasta") == '"caminho\\\\pasta"'


def test_o_script_montado_e_aceito_pelo_applescript():
    """Compila o script de verdade (sem exibir nada) — pega erro de sintaxe."""
    script = 'display notification %s with title %s' % (
        aviso.aspas("Maria Nizete Araújo · onboarding gerado"),
        aviso.aspas("Contrato assinado arquivado"))
    conferido = subprocess.run(["osascript", "-e", "return 1", "-e", script[:0] or "return 1"],
                               capture_output=True, text=True)
    assert conferido.returncode == 0
    # e o script real compila:
    compilado = subprocess.run(["osacompile", "-o", "/dev/null", "-e", script],
                               capture_output=True, text=True)
    assert compilado.returncode == 0, compilado.stderr


# --- conteúdo da mensagem --------------------------------------------------

def evento(situacao, cliente, onboarding=""):
    return {"situacao": situacao, "cliente": cliente, "onboarding": onboarding}


def test_um_contrato_com_onboarding_pronto():
    titulo, mensagem = aviso.montar({
        "baixados": 1, "pendentes": 0, "erros": 0,
        "eventos": [evento("baixado", "Eber Roberto Almeida", "gerado")]})
    assert titulo == "Contrato assinado arquivado"
    assert "Eber Roberto Almeida" in mensagem
    assert "onboarding gerado" in mensagem


def test_avisa_quando_falta_o_banco_adverso():
    _titulo, mensagem = aviso.montar({
        "baixados": 1, "pendentes": 0, "erros": 0,
        "eventos": [evento("baixado", "Telma Cristiane", "pendente")]})
    assert "banco adverso" in mensagem


def test_documento_sem_pasta_tambem_gera_aviso():
    titulo, mensagem = aviso.montar({
        "baixados": 0, "pendentes": 1, "erros": 0,
        "eventos": [evento("pendente", "Fulano de Tal")]})
    assert titulo == "Documento assinado esperando você"
    assert "Fulano de Tal" in mensagem


def test_muitos_contratos_viram_resumo():
    eventos = [evento("baixado", "Cliente %d" % n, "gerado") for n in range(5)]
    titulo, mensagem = aviso.montar({"baixados": 5, "pendentes": 0, "erros": 0,
                                     "eventos": eventos})
    assert titulo == "5 contratos assinados arquivados"
    assert "e mais 2" in mensagem


def test_rodada_sem_novidade_nao_incomoda():
    assert aviso.montar({"baixados": 0, "pendentes": 0, "erros": 0, "eventos": []}) == (None, None)


def test_aviso_desligado_no_env_nao_notifica():
    class ConfigFalsa(object):
        avisar_na_tela = False

    resumo = {"baixados": 1, "pendentes": 0, "erros": 0,
              "eventos": [evento("baixado", "Fulano", "gerado")]}
    assert aviso.avisar_da_rodada(resumo, ConfigFalsa()) is False



def test_envelope_com_dois_contratos_aparece_na_notificacao():
    """
    Se ficar só no relatório, ninguém vê: no caso da Sofia (01/09/2026) o
    segundo contrato sumiria sem barulho nenhum.
    """
    titulo, mensagem = aviso.montar({
        "baixados": 1, "pendentes": 0, "erros": 0,
        "eventos": [{"situacao": "baixado", "cliente": "SOFIA EVANGELISTA",
                     "multicontrato": {"quantos": 2, "paginas": [1, 6],
                                       "objetos": ["", ""]}}],
    })
    assert titulo == "Envelope com mais de um contrato"
    assert "SOFIA EVANGELISTA" in mensagem
    assert "uma pasta por contrato" in mensagem


def test_rodada_normal_nao_ganha_o_alerta_de_dois_contratos():
    titulo, mensagem = aviso.montar({
        "baixados": 1, "pendentes": 0, "erros": 0,
        "eventos": [{"situacao": "baixado", "cliente": "JOICE LEVANDOWSKI"}],
    })
    assert "mais de um contrato" not in ((titulo or "") + (mensagem or ""))
