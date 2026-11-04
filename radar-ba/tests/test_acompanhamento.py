"""Acompanhamento dos processos de B&A conhecidos — sem tocar a rede."""
import datetime

import pytest

from src.servicos import acompanhamento
from src.servicos.classificador_movimentos import (LIMINAR_DEFERIDA,
                                                   MANDADO_EXPEDIDO)

HOJE = datetime.date(2026, 8, 18)
CLIENTE = {"id": "c1", "nome": "Fulano de Tal",
           "processos_busca": ["0740433-63.2026.8.02.0001"]}


class DjenFalso:
    def __init__(self, itens):
        self.itens = itens
        self.consultas = []

    def _consultar(self, **kw):
        self.consultas.append(kw)
        return {"items": self.itens}


def publicacao(texto, data="2026-08-17"):
    return {"siglaTribunal": "TJAL", "data_disponibilizacao": data,
            "nomeOrgao": "1ª Vara Cível", "texto": texto}


@pytest.fixture(autouse=True)
def historico_isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(acompanhamento, "EVENTOS_VISTOS", tmp_path / "eventos.json")


def test_detecta_liminar_deferida():
    djen = DjenFalso([publicacao("concedo liminarmente a BUSCA E APREENSÃO do veículo")])
    novidades, erros = acompanhamento.acompanhar([CLIENTE], djen, hoje=HOJE)
    assert erros == []
    assert [n["evento"] for n, _ in novidades] == [LIMINAR_DEFERIDA]
    assert novidades[0][0]["urgente"] is True


def test_consulta_pelo_numero_do_processo():
    """É por número que se acha a publicação dirigida só ao advogado do banco."""
    djen = DjenFalso([])
    acompanhamento.acompanhar([CLIENTE], djen, hoje=HOJE)
    assert djen.consultas[0]["numeroProcesso"] == "07404336320268020001"


def test_nao_repete_o_mesmo_evento():
    djen = DjenFalso([publicacao("Expeça-se mandado de busca e apreensão")])
    primeira, _ = acompanhamento.acompanhar([CLIENTE], djen, hoje=HOJE)
    segunda, _ = acompanhamento.acompanhar([CLIENTE], djen, hoje=HOJE)
    assert len(primeira) == 1 and segunda == []


def test_mesmo_evento_em_data_nova_nao_avisa_de_novo():
    """Uma liminar deferida é mencionada em cada despacho seguinte.

    O histórico registra cada menção, mas o aviso sai uma vez só — senão um
    processo antigo dispara o mesmo alerta a cada publicação. Medido na carga
    real: 352 menções correspondiam a 288 fatos distintos.
    """
    djen = DjenFalso([publicacao("Expeça-se mandado", data="2026-08-17")])
    primeira, _ = acompanhamento.acompanhar([CLIENTE], djen, hoje=HOJE)
    djen.itens = [publicacao("Expeça-se mandado", data="2026-08-18")]
    segunda, _ = acompanhamento.acompanhar([CLIENTE], djen, hoje=HOJE)
    assert len(primeira) == 1
    assert segunda == []
    # ...mas a segunda menção fica registrada no histórico
    historico = acompanhamento._carregar()
    assert len(historico) == 2


def test_eventos_diferentes_no_mesmo_processo_avisam_cada_um():
    djen = DjenFalso([publicacao("DEFIRO a liminar de busca e apreensão. Expeça-se mandado.")])
    novidades, _ = acompanhamento.acompanhar([CLIENTE], djen, hoje=HOJE)
    assert {n["evento"] for n, _ in novidades} == {LIMINAR_DEFERIDA, MANDADO_EXPEDIDO}


def test_numero_repetido_e_consultado_uma_vez_so():
    a = {"id": "c1", "nome": "A", "processos_busca": ["0740433-63.2026.8.02.0001"]}
    b = {"id": "c2", "nome": "B", "processos_busca": ["0740433-63.2026.8.02.0001"]}
    assert len(acompanhamento.processos_a_acompanhar([a, b])) == 1


def test_cliente_sem_processo_de_busca_e_ignorado():
    assert acompanhamento.processos_a_acompanhar([{"id": "c9", "nome": "X"}]) == []


def test_publicacao_sem_evento_nao_gera_novidade():
    djen = DjenFalso([publicacao("Nada consta nos autos")])
    novidades, _ = acompanhamento.acompanhar([CLIENTE], djen, hoje=HOJE)
    assert novidades == []


def test_falha_de_consulta_vira_erro_e_nao_derruba():
    from src.util.http import FalhaConsulta

    class Quebrado:
        def _consultar(self, **kw):
            raise FalhaConsulta("indisponível")

    novidades, erros = acompanhamento.acompanhar([CLIENTE], Quebrado(), hoje=HOJE)
    assert novidades == [] and len(erros) == 1
