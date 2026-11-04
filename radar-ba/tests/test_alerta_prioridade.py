"""Prioridade (item 12) e montagem do alerta (item 13)."""
import datetime

import pytest

from src.provedores.base import CONFIRMADO, POSSIVEL, ResultadoProcesso
from src.servicos.alertas import CanalConsole, montar_texto
from src.servicos.prioridade import (ALTO, ATENCAO, CRITICO, INFORMATIVO,
                                     classificar_prioridade)

HOJE = datetime.date(2026, 8, 18)


@pytest.mark.parametrize("data,esperado", [
    ("2026-08-18", CRITICO),      # hoje
    ("2026-08-12", CRITICO),      # 6 dias
    ("2026-08-11", CRITICO),      # 7 dias — limite
    ("2026-08-10", ALTO),         # 8 dias
    ("2026-07-19", ALTO),         # 30 dias — limite
    ("2026-07-18", ATENCAO),      # 31 dias
])
def test_regua_de_prioridade(data, esperado):
    p, _ = classificar_prioridade(data_distribuicao=data, hoje=HOJE)
    assert p == esperado


def test_processo_encerrado_e_informativo():
    p, _ = classificar_prioridade(data_distribuicao="2026-08-18",
                                  encerrado=True, hoje=HOJE)
    assert p == INFORMATIVO


def test_sem_distribuicao_usa_publicacao_e_diz_isso():
    p, motivo = classificar_prioridade(data_publicacao="2026-08-17", hoje=HOJE)
    assert p == CRITICO
    assert "diário" in motivo


def test_sem_data_nenhuma_vai_para_conferencia():
    p, _ = classificar_prioridade(hoje=HOJE)
    assert p == ATENCAO


def _resultado(**kw):
    base = dict(numero_processo="4000116-76.2026.8.26.0405", tribunal="TJSP",
                classe_nome="BUSCA E APREENSÃO EM ALIENAÇÃO FIDUCIÁRIA",
                banco_normalizado="BANCO ITAÚ", autor="ITAU UNIBANCO HOLDING S.A.",
                reu="FULANO DE TAL", data_publicacao="2026-08-17",
                fonte="DJEN", status_casamento=POSSIVEL, confianca=0.99,
                motivo="classe 81")
    base.update(kw)
    return ResultadoProcesso(**base)


def test_alerta_traz_os_campos_pedidos():
    texto = montar_texto(_resultado(),
                         {"nome": "Fulano de Tal", "cpf_mascara": "***.***.***-35"},
                         CRITICO, "distribuído há 1 dia")
    for campo in ("Cliente:", "CPF:", "Banco:", "Processo:", "Tribunal:",
                  "Vara:", "Classe:", "Prioridade:", "Fonte:"):
        assert campo in texto


def test_alerta_nunca_mostra_cpf_completo():
    texto = montar_texto(_resultado(), {"nome": "F", "cpf_mascara": "***.***.***-35"},
                         CRITICO, "")
    assert "11144477735" not in texto and "111.444.777-35" not in texto
    assert "***.***.***-35" in texto


def test_possible_match_carrega_aviso_de_conferencia():
    texto = montar_texto(_resultado(status_casamento=POSSIVEL), {}, CRITICO, "")
    assert "IDENTIDADE NÃO CONFIRMADA" in texto


def test_confirmed_match_nao_carrega_o_aviso():
    texto = montar_texto(_resultado(status_casamento=CONFIRMADO), {}, CRITICO, "")
    assert "IDENTIDADE NÃO CONFIRMADA" not in texto


def test_canal_console_registra_o_envio():
    import io
    canal = CanalConsole(saida=io.StringIO())
    assert canal.enviar("teste") is True
    assert canal.entregues == ["teste"]
