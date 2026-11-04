"""Privacidade (pseudonimização, pacote ao Claude), armazenamento do caso, CLI e ausência de rede."""

import json
import os
import re
import stat
from pathlib import Path

import pytest

from cm_calc import cli
from cm_calc.casos import Caso
from cm_calc.privacidade.pacote import Autorizacao, candidatos, gravar_pacote, montar_pacote
from cm_calc.privacidade.pseudonimizacao import Pseudonimizador, residuos
from tests.fixtures import documentos_ficticios as F

DADOS_PESSOAIS = ["JOANA EXEMPLO DA SILVA", "123.456.789-09", "ABC1D23", "9BWZZZ377VT004251", "12345678901",
                  "joana.exemplo@exemplo.com", "91234-5678", "01000-000", "Rua das Flores", "0001234-56.2023.8.26.0000"]


def test_pseudonimizacao_remove_dados_e_preserva_valores():
    ps = Pseudonimizador()
    t = ps.aplicar(F.CONTRATO + F.SENTENCA)
    for dado in DADOS_PESSOAIS:
        assert dado.lower() not in t.lower(), dado
    for parte in ("JOANA", "EXEMPLO", "SILVA"):          # nenhuma parte do nome pode sobrar isolada
        assert not re.search(rf"\b{parte}\b", t, re.I), parte
    for mantido in ("R$ 40.000,00", "2,20% a.m.", "05/01/2023", "BANCO FICTÍCIO S.A.", "INPC"):
        assert mantido in t, mantido
    assert "[CPF_1]" in t and "[NOME_1]" in t
    assert residuos(t, list(ps.mapa)) == []


def test_marcador_estavel_entre_trechos():
    ps = Pseudonimizador()
    a = ps.aplicar("Autor: JOANA EXEMPLO DA SILVA, CPF 123.456.789-09")
    b = ps.aplicar("A autora JOANA EXEMPLO DA SILVA pagou.")
    assert re.search(r"\[NOME_1\]", a) and re.search(r"\[NOME_1\]", b)


def test_residuo_detectado():
    assert residuos("CPF 123.456.789-09")
    assert residuos("texto com Fulano", ["Fulano"])


def test_pacote_exige_autorizacao(quadro):
    with pytest.raises(PermissionError, match="autorização"):
        montar_pacote(quadro, None)
    with pytest.raises(PermissionError, match="incompleta"):
        montar_pacote(quadro, Autorizacao(responsavel="", finalidade="x", escopo=["titulo.juros_remuneratorios"]))
    with pytest.raises(ValueError, match="fora dos candidatos"):
        montar_pacote(quadro, Autorizacao(responsavel="Adv", finalidade="x", escopo=["contrato.valor_financiado"]))


def test_pacote_so_com_trechos_pseudonimizados(quadro, tmp_path):
    assert "titulo.juros_remuneratorios" in candidatos(quadro)
    aut = Autorizacao(responsavel="Advogada (teste)", finalidade="interpretar critério da taxa revisada",
                      escopo=["titulo.juros_remuneratorios", "pag-contradicao-2"])
    pacote, ps = montar_pacote(quadro, aut, nomes_conhecidos=["JOANA EXEMPLO DA SILVA"])
    corpo = pacote.model_dump_json()
    for dado in DADOS_PESSOAIS:
        assert dado.lower() not in corpo.lower(), dado
    assert len(pacote.trechos) == 2 and all(len(t.trecho) <= 1500 for t in pacote.trechos)
    assert "mapa" not in corpo and "JOANA" not in corpo
    arq = gravar_pacote(pacote, tmp_path / "caso")
    assert arq.exists()
    reg = (tmp_path / "caso" / "claude" / "registro-envios.jsonl").read_text().strip().splitlines()
    assert json.loads(reg[0])["responsavel"] == "Advogada (teste)"


def test_pacote_recusado_se_sobrar_dado_pessoal(quadro):
    p = quadro.parametros["titulo.juros_remuneratorios"]
    p.fontes[0].trecho += " Contato: RG 12.345.678-9 e placa XYZ-9A87 e CPF 98765432100"
    pacote, _ = montar_pacote(quadro, Autorizacao(responsavel="A", finalidade="f", escopo=[p.id]))
    assert "XYZ-9A87" not in pacote.model_dump_json()   # removidos pela pseudonimização (sem sobra)


def test_nenhum_modulo_faz_chamada_de_rede():
    raiz = Path(__file__).resolve().parents[2] / "src" / "cm_calc"
    proibidos = r"^\s*(import|from)\s+(requests|httpx|urllib|socket|http\.client|anthropic|aiohttp)\b"
    for arq in raiz.rglob("*.py"):
        assert not re.search(proibidos, arq.read_text(encoding="utf-8"), re.M), arq


# --- Caso e CLI ---------------------------------------------------------------------------

@pytest.mark.parametrize("ruim", ["joana", "12345678901", "CASO-123.456.789", "A"])
def test_identificador_de_caso_invalido(ruim):
    with pytest.raises(ValueError):
        Caso(ruim)


def test_importacao_somente_leitura_e_integridade(arquivos):
    c = Caso("FICT-002")
    assert "importado" in c.importar(arquivos["contrato"])
    assert "já importado" in c.importar(arquivos["contrato"])
    arq = next(c.docs.iterdir())
    assert stat.S_IMODE(arq.stat().st_mode) == 0o400
    assert stat.S_IMODE(c.pasta.stat().st_mode) == 0o700
    assert str(c.pasta).startswith(os.environ["CM_CALC_DADOS"])     # nunca na pasta real
    assert c.verificar_integridade() == []
    os.chmod(arq, 0o600)
    arq.write_bytes(b"adulterado")
    assert "alterado" in c.verificar_integridade()[0]


def test_cli_ponta_a_ponta(arquivos, capsys):
    assert cli.main(["importar", "FICT-003", *map(str, arquivos.values())]) == 0
    assert cli.main(["extrair", "FICT-003"]) == 0
    assert cli.main(["status", "FICT-003"]) == 1                          # bloqueado
    assert cli.main(["confirmar", "FICT-003", "calculo.convencao_tempo", "--por", "Adv", "--valor", "meses_civis"]) == 0
    assert cli.main(["confirmar", "FICT-003", "titulo.juros_remuneratorios", "--por", "Adv", "--detalhe", "taxa_mensal=1,6"]) == 0
    assert cli.main(["ciencia", "FICT-003", "pag-contradicao-2", "--por", "Adv"]) == 0
    assert cli.main(["quadro", "FICT-003"]) == 0
    out = capsys.readouterr().out
    assert "Quadro de parâmetros" in out and "taxa_mensal: 1,6" in out
    assert cli.main(["pacote", "FICT-003", "--por", "Adv", "--finalidade", "teste", "--itens", "pag-contradicao-2"]) == 0
