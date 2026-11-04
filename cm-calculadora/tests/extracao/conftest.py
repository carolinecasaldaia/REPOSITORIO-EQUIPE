"""Fixtures da Fase 3. Tudo gerado em pastas temporárias, com dados FICTÍCIOS."""

import pytest

from cm_calc.documentos.leitura import ler_arquivo
from cm_calc.extracao.quadro import montar_quadro
from tests.fixtures.documentos_ficticios import gerar_caso_completo


@pytest.fixture
def arquivos(tmp_path):
    return gerar_caso_completo(tmp_path / "docs")


def ler(arqs):
    docs, avisos = [], []
    for a in arqs:
        r = ler_arquivo(a)
        docs += r.documentos
        avisos += r.avisos
    return docs, avisos


@pytest.fixture
def documentos(arquivos):
    return ler(arquivos.values())


@pytest.fixture
def quadro(documentos):
    docs, avisos = documentos
    return montar_quadro("FICT-001", docs, avisos)


@pytest.fixture(autouse=True)
def pasta_dados_temporaria(tmp_path, monkeypatch):
    """Garante que nenhum teste escreva em ~/CM-Calculos-Dados."""
    monkeypatch.setenv("CM_CALC_DADOS", str(tmp_path / "dados"))
