"""Prevenção de alerta duplicado (item 11) e ciclo de monitoramento (item 10)."""
import datetime

import pytest

from src.provedores.djen.cliente import ProvedorDJEN
from src.servicos import monitor
from src.servicos.alertas import CanalConsole
from src.servicos.prioridade import CRITICO

HOJE = datetime.date(2026, 8, 18)


def item(**kw):
    base = {
        "id": 1, "siglaTribunal": "TJSP", "codigoClasse": 81,
        "nomeClasse": "BUSCA E APREENSÃO EM ALIENAÇÃO FIDUCIÁRIA",
        "nomeOrgao": "1ª Vara Cível", "numeroprocessocommascara": "4000116-76.2026.8.26.0405",
        "data_disponibilizacao": "2026-08-17", "tipoComunicacao": "Citação",
        "destinatarios": [{"nome": "FULANO DE TAL SILVA", "polo": "P"},
                          {"nome": "ITAU UNIBANCO HOLDING S.A.", "polo": "A"}],
    }
    base.update(kw)
    return base


class DjenFalso(ProvedorDJEN):
    """Provedor com resposta fixa — o ciclo é testado sem tocar a rede."""

    def __init__(self, itens):
        self.itens = itens
        self.consultas = 0

    def buscar_por_nome(self, nome, dias=7, tribunal=None, cliente_id=None,
                        limite_nome=0.85, usar_prefixo=True):
        self.consultas += 1
        achados = []
        for it in self.itens:
            r = self.converter(it, nome_cliente=nome, cliente_id=cliente_id,
                               limite_nome=limite_nome)
            if r is not None:
                achados.append(r)
        return achados

    def varrer(self, data_inicio, data_fim, tribunal=None, max_paginas=400):
        for it in self.itens:
            yield it


CLIENTE = {"id": "c1", "nome": "Fulano de Tal Silva", "cpf_mascara": "***.***.***-35"}
OUTRO = {"id": "c2", "nome": "Fulano de Tal Silva", "cpf_mascara": "***.***.***-99"}


@pytest.fixture(autouse=True)
def estado_isolado(tmp_path, monkeypatch):
    """Cada teste começa com histórico limpo, fora de ~/.radar-ba."""
    monkeypatch.setattr(monitor, "VISTOS", tmp_path / "vistos.json")


def test_primeira_deteccao_gera_alerta():
    canal = CanalConsole(saida=_nulo())
    ex = monitor.executar([CLIENTE], DjenFalso([item()]), canal=canal, hoje=HOJE)
    assert ex.novos == 1
    assert ex.alertas_criticos == 1
    assert len(canal.entregues) == 1


def test_segunda_execucao_nao_repete_o_alerta():
    djen = DjenFalso([item()])
    monitor.executar([CLIENTE], djen, canal=CanalConsole(saida=_nulo()), hoje=HOJE)
    canal = CanalConsole(saida=_nulo())
    ex = monitor.executar([CLIENTE], djen, canal=canal, hoje=HOJE)
    assert ex.processos_encontrados == 1     # continua acompanhando
    assert ex.novos == 0                     # mas não alerta de novo
    assert canal.entregues == []


def test_mesmo_processo_para_cliente_diferente_gera_alerta_proprio():
    djen = DjenFalso([item()])
    monitor.executar([CLIENTE], djen, canal=CanalConsole(saida=_nulo()), hoje=HOJE)
    ex = monitor.executar([OUTRO], djen, canal=CanalConsole(saida=_nulo()), hoje=HOJE)
    assert ex.novos == 1


def test_historico_guarda_a_data_da_primeira_deteccao():
    djen = DjenFalso([item()])
    monitor.executar([CLIENTE], djen, canal=CanalConsole(saida=_nulo()), hoje=HOJE)
    monitor.executar([CLIENTE], djen, canal=CanalConsole(saida=_nulo()),
                     hoje=HOJE + datetime.timedelta(days=3))
    vistos = monitor._carregar_vistos()
    registro = list(vistos.values())[0]
    assert registro["primeiro_detectado_em"] == "2026-08-18"
    assert registro["ultima_checagem"] == "2026-08-21"


def test_processo_criminal_nunca_vira_alerta():
    ex = monitor.executar([CLIENTE], DjenFalso([item(codigoClasse=309)]),
                          canal=CanalConsole(saida=_nulo()), hoje=HOJE)
    assert ex.novos == 0


def test_modo_varredura_encontra_o_mesmo_que_o_modo_nome():
    a = monitor.executar([CLIENTE], DjenFalso([item()]), modo="nome",
                         canal=CanalConsole(saida=_nulo()), hoje=HOJE)
    monitor.VISTOS.unlink(missing_ok=True)
    b = monitor.executar([CLIENTE], DjenFalso([item()]), modo="varredura",
                         canal=CanalConsole(saida=_nulo()), hoje=HOJE)
    assert a.novos == b.novos == 1


def test_modo_nome_faz_uma_consulta_por_cliente():
    djen = DjenFalso([item()])
    monitor.executar([CLIENTE, OUTRO], djen, modo="nome",
                     canal=CanalConsole(saida=_nulo()), hoje=HOJE)
    assert djen.consultas == 2


def test_relatorio_traz_os_numeros_da_execucao():
    from src.servicos import relatorio
    ex = monitor.executar([CLIENTE], DjenFalso([item()]),
                          canal=CanalConsole(saida=_nulo()), hoje=HOJE)
    texto = relatorio.montar_texto(ex)
    assert "RADAR DE BUSCA E APREENSÃO" in texto
    assert "Novas buscas e apreensões: 1" in texto
    assert "Alertas críticos:          1" in texto


def test_relatorio_nunca_contem_cpf():
    from src.servicos import relatorio
    ex = monitor.executar([CLIENTE], DjenFalso([item()]),
                          canal=CanalConsole(saida=_nulo()), hoje=HOJE)
    dados = ex.para_dict()
    assert "cpf" not in repr(dados).lower() or "cpf_mascara" in repr(dados)
    texto = relatorio.montar_texto(ex)
    assert "11144477735" not in texto


def _nulo():
    import io
    return io.StringIO()
