"""Provedores, com mock — nenhum teste aqui toca a rede."""
import datetime
from pathlib import Path

import pytest

from src.provedores.base import (CONFIRMADO, POSSIVEL, REVISAO_MANUAL,
                                 ProvedorJudicial, ResultadoProcesso)
from src.provedores.datajud.cliente import (ProvedorDataJud, faixa_periodo,
                                            normalizar_data_ajuizamento,
                                            sigla_pelo_numero)
from src.provedores.djen.cliente import ProvedorDJEN
from src.provedores.esaj.cliente import ProvedorESAJ


class HttpFalso:
    """Dublê do cliente HTTP: devolve o que mandarmos, sem sair da máquina."""

    def __init__(self, resposta=None):
        self.resposta = resposta or {"items": []}
        self.chamadas = []

    def pedir_get(self, caminho, parametros=None, **kw):
        self.chamadas.append(dict(parametros or {}))
        return self.resposta

    def pedir(self, url, corpo=None, **kw):
        self.chamadas.append({"url": url, "corpo": corpo})
        return self.resposta


def item_djen(**kw):
    base = {
        "id": 1, "siglaTribunal": "TJSP", "codigoClasse": 81,
        "nomeClasse": "BUSCA E APREENSãO EM ALIENAçãO FIDUCIáRIA",
        "nomeOrgao": "1ª Vara Cível de Osasco",
        "numeroprocessocommascara": "4000116-76.2026.8.26.0405",
        "data_disponibilizacao": "2026-08-17", "tipoComunicacao": "Citação",
        "destinatarios": [{"nome": "FULANO DE TAL SILVA", "polo": "P"},
                          {"nome": "ITAU UNIBANCO HOLDING S.A.", "polo": "A"}],
    }
    base.update(kw)
    return base


# --- DJEN ---------------------------------------------------------------

def test_djen_converte_busca_e_apreensao_do_cliente():
    p = ProvedorDJEN(cliente_http=HttpFalso())
    r = p.converter(item_djen(), nome_cliente="FULANO DE TAL SILVA", cliente_id="c1")
    assert r is not None
    assert r.classe_codigo == 81
    assert r.banco_normalizado == "BANCO ITAÚ"
    assert r.reu == "FULANO DE TAL SILVA"
    assert r.status_casamento == POSSIVEL      # nome nunca confirma identidade


def test_djen_normaliza_a_caixa_da_classe():
    p = ProvedorDJEN(cliente_http=HttpFalso())
    r = p.converter(item_djen(), nome_cliente="FULANO DE TAL SILVA")
    assert r.classe_nome == "BUSCA E APREENSÃO EM ALIENAÇÃO FIDUCIÁRIA"


def test_djen_descarta_classe_criminal():
    p = ProvedorDJEN(cliente_http=HttpFalso())
    assert p.converter(item_djen(codigoClasse=309), nome_cliente="FULANO DE TAL SILVA") is None


def test_djen_descarta_quando_o_cliente_esta_no_polo_ativo():
    """Cliente autor não é vítima de busca e apreensão — é o caso do agravo."""
    item = item_djen(destinatarios=[{"nome": "FULANO DE TAL SILVA", "polo": "A"},
                                    {"nome": "ITAU UNIBANCO S.A.", "polo": "P"}])
    p = ProvedorDJEN(cliente_http=HttpFalso())
    assert p.converter(item, nome_cliente="FULANO DE TAL SILVA") is None


def test_djen_descarta_pessoa_diferente():
    p = ProvedorDJEN(cliente_http=HttpFalso())
    assert p.converter(item_djen(), nome_cliente="BELTRANO OUTRO NOME") is None


def test_djen_descarta_parametro_que_a_api_ignora():
    """codigoClasse não filtra nada no servidor: não pode ser enviado como se filtrasse."""
    http = HttpFalso()
    p = ProvedorDJEN(cliente_http=http)
    p._consultar(nomeParte="X", codigoClasse=81, inventado="y")
    enviados = http.chamadas[0]
    assert "nomeParte" in enviados
    assert "codigoClasse" not in enviados and "inventado" not in enviados


def test_djen_varredura_para_quando_a_pagina_vem_incompleta():
    http = HttpFalso({"items": [item_djen()]})
    p = ProvedorDJEN(cliente_http=http)
    itens = list(p.varrer("2026-08-17", "2026-08-17"))
    assert len(itens) == 1 and len(http.chamadas) == 1


# --- DataJud ------------------------------------------------------------

@pytest.mark.parametrize("bruto,esperado", [
    ("20260630235628", "2026-06-30"),
    ("2025-07-15T13:19:10", "2025-07-15"),
    ("40220915000000", None),        # lixo real encontrado no índice
    ("", None),
    (None, None),
])
def test_datajud_normaliza_os_dois_formatos_de_data(bruto, esperado):
    assert normalizar_data_ajuizamento(bruto) == esperado


def test_faixa_periodo_usa_numero_cru_e_nao_data():
    """A armadilha: o índice lê dataAjuizamento como epoch_millis.

    Com semântica de data o filtro casa errado em silêncio. O valor tem de ir
    como inteiro yyyyMMddHHmmss.
    """
    f = faixa_periodo(datetime.date(2026, 3, 1), datetime.date(2026, 3, 31))
    gte = f["range"]["dataAjuizamento"]["gte"]
    assert isinstance(gte, int)
    assert gte == 20260301000000


@pytest.mark.parametrize("numero,sigla", [
    ("4000116-76.2026.8.26.0405", "tjsp"),
    ("0701883-50.2026.8.02.0081", "tjal"),
    ("0000000-00.2026.8.17.0001", "tjpe"),
    ("0000000-00.2026.4.03.0001", ""),      # justiça federal: fora do escopo
    ("123", ""),
])
def test_descobre_o_tribunal_pelo_numero_cnj(numero, sigla):
    assert sigla_pelo_numero(numero) == sigla


def test_datajud_recusa_busca_por_cpf_de_forma_honesta():
    p = ProvedorDataJud(cliente_http=HttpFalso())
    r = p.buscar_por_cpf("11144477735")[0]
    assert r.status_casamento == REVISAO_MANUAL
    assert "não expõe partes" in r.motivo


# --- e-SAJ --------------------------------------------------------------

def test_esaj_nasce_desligado(monkeypatch):
    from src.config import ajustes
    monkeypatch.setattr(ajustes, "ESAJ_HABILITADO", False)
    r = ProvedorESAJ("TJAL").buscar_por_cpf("11144477735")[0]
    assert r.status_casamento == REVISAO_MANUAL
    assert "DESLIGADA" in r.motivo


def test_esaj_recusa_tribunal_sem_suporte():
    with pytest.raises(ValueError):
        ProvedorESAJ("TJPE")      # PJe com reCAPTCHA — não automatizamos


def test_esaj_le_a_listagem_real_do_tribunal():
    """Parser conferido contra HTML de verdade, salvo do TJAL."""
    amostra = Path(__file__).parent / "amostra_esaj_tjal.html"
    corpo = amostra.read_bytes().decode("utf-8", errors="replace")
    from src.provedores.esaj.cliente import _BLOCO, _NUMERO
    blocos = _BLOCO.findall(corpo)
    assert len(blocos) >= 20
    assert _NUMERO.search(blocos[0]).group(1).strip() == "0701883-50.2026.8.02.0081"


def test_esaj_filtra_o_que_nao_e_busca_e_apreensao():
    amostra = Path(__file__).parent / "amostra_esaj_tjal.html"
    corpo = amostra.read_bytes().decode("utf-8", errors="replace")
    # a amostra só tem Juizado Especial Cível — nada pode passar
    assert ProvedorESAJ("TJAL")._extrair(corpo) == []


# --- contrato comum -----------------------------------------------------

def test_provedor_sem_cpf_devolve_revisao_manual_por_padrao():
    class Qualquer(ProvedorJudicial):
        nome = "qualquer"

        def verificar_saude(self):
            return True

    assert Qualquer().buscar_por_cpf("11144477735")[0].status_casamento == REVISAO_MANUAL


def test_chave_de_deduplicacao_junta_processo_e_cliente():
    a = ResultadoProcesso(numero_processo="4000116-76.2026.8.26.0405", cliente_id="c1")
    b = ResultadoProcesso(numero_processo="40001167620268260405", cliente_id="c1")
    c = ResultadoProcesso(numero_processo="4000116-76.2026.8.26.0405", cliente_id="c2")
    assert a.chave == b.chave       # formatação não importa
    assert a.chave != c.chave       # cliente diferente, alerta diferente
