"""Ícones de dois cliques (ferramentas/*.command) executados sem diálogos, com material FICTÍCIO."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pymupdf
import pytest

from tests.validacao.test_anonimizacao import PII, parecer_sujo

FERR = Path(__file__).resolve().parents[2] / "ferramentas"
ID = "TESTE-ICONES"


def rodar(script, tmp_path, **env):
    e = {**os.environ, "CM_CALC_DADOS": str(tmp_path / "dados"), "CM_VALIDACAO_ID": ID, "CM_SEM_DIALOGOS": "1", **env}
    return subprocess.run(["/bin/zsh", str(FERR / script)], capture_output=True, text=True, env=e, timeout=300)


@pytest.fixture
def original(tmp_path):
    pasta = tmp_path / "Downloads"
    pasta.mkdir()
    return parecer_sujo(pasta / "Parecer Joana Exemplo da Silva.pdf")    # nome do arquivo com dado pessoal


def test_anonimizar_sem_liberar(tmp_path, original):
    h = hashlib.sha256(original.read_bytes()).hexdigest()
    r = rodar("Anonimizar parecer.command", tmp_path, CM_TESTE_ARQUIVO=str(original),
              CM_TESTE_TERMOS="PROPOSTA-ABC-77;Fulana Perita Teste")
    assert r.returncode == 0, r.stdout + r.stderr
    saida = (r.stdout + r.stderr).lower()
    assert "aprovada" in saida
    for dado in PII + ["Joana Exemplo da Silva"]:
        assert dado.lower() not in saida, dado                  # nem o nome do arquivo aparece
    assert hashlib.sha256(original.read_bytes()).hexdigest() == h          # original intacto
    base = tmp_path / "dados" / "validacao" / ID
    assert [p.name for p in (base / "anonimizados").iterdir()] == ["documento-01-anonimizado.pdf"]
    assert [p.name for p in (base / "original").iterdir()] == ["documento-01.pdf"]
    assert not list((base / "parecer").iterdir())                          # NÃO liberado automaticamente
    verif = (base / "anonimizacao" / "verificacao.md").read_text().lower()
    assert "joana" not in verif and "aprovada" in verif
    assert "Parecer Joana" in (base / "anonimizacao" / "originais.jsonl").read_text()   # só no registro confidencial


SIMULADOR = r'''#!/bin/zsh
# Simula as janelas do Mac (osascript) como a usuária responderia. Registra cada chamada.
print -r -- "$*" >> "$SIM_LOG"
n=$(( $(cat "$SIM_CONT" 2>/dev/null || echo 0) + 1 )); echo $n > "$SIM_CONT"
case "$*" in
  *"choose from list"*)
    [ "$SIM_CANCELAR_EM" = "lista" ] && { echo false; exit 0; }
    echo "$SIM_ESCOLHA";;
  *"Seu nome"*)
    [ "$SIM_CANCELAR_EM" = "nome" ] && exit 1
    i=$(( $(cat "$SIM_NOMES_I" 2>/dev/null || echo 0) + 1 )); echo $i > "$SIM_NOMES_I"
    nomes=("${(@s:|:)SIM_NOMES}"); echo "${nomes[$i]}";;
  *"digite AUTORIZO"*)
    [ "$SIM_CANCELAR_EM" = "confirmacao" ] && exit 1     # Enter/Esc/Cancelar = botão de cancelamento
    echo "$SIM_CONFIRMA";;
  *) echo "button returned:OK";;
esac
'''


@pytest.fixture
def simulador(tmp_path):
    b = tmp_path / "bin"
    b.mkdir()
    (b / "osascript").write_text(SIMULADOR)
    (b / "osascript").chmod(0o755)
    return {"PATH": f"{b}:{os.environ['PATH']}", "SIM_LOG": str(tmp_path / "sim.log"),
            "SIM_CONT": str(tmp_path / "sim.cont"), "SIM_NOMES_I": str(tmp_path / "sim.nomes")}


def liberar(tmp_path, simulador, **resp):
    env = {**simulador, "SIM_ESCOLHA": "documento-01-anonimizado.pdf", "SIM_NOMES": "Advogada (teste)",
           "SIM_CONFIRMA": "AUTORIZO", "SIM_CANCELAR_EM": "", **resp}
    for k in ("SIM_CONT", "SIM_NOMES_I"):
        Path(simulador[k]).unlink(missing_ok=True)
    e = {**os.environ, "CM_CALC_DADOS": str(tmp_path / "dados"), "CM_VALIDACAO_ID": ID, "HOME": str(tmp_path / "home"),
         **env}
    (tmp_path / "home").mkdir(exist_ok=True)
    os.symlink(Path.home() / "cm-calculadora", tmp_path / "home" / "cm-calculadora") \
        if not (tmp_path / "home" / "cm-calculadora").exists() else None
    return subprocess.run(["/bin/zsh", str(FERR / "Liberar parecer anonimizado.command")], capture_output=True,
                          text=True, env=e, timeout=300)


def liberados(tmp_path):
    return [p.name for p in (tmp_path / "dados" / "validacao" / ID / "parecer").iterdir()]


@pytest.fixture
def aprovado(tmp_path, original):
    r = rodar("Anonimizar parecer.command", tmp_path, CM_TESTE_ARQUIVO=str(original), CM_TESTE_TERMOS="PROPOSTA-ABC-77")
    assert r.returncode == 0, r.stdout


def test_liberacao_interativa_completa(tmp_path, aprovado, simulador):
    r = liberar(tmp_path, simulador)
    assert r.returncode == 0, r.stdout + r.stderr
    assert liberados(tmp_path) == ["documento-01-anonimizado.pdf"]
    reg = json.loads((tmp_path / "dados/validacao" / ID / "anonimizacao/liberacoes.jsonl").read_text().splitlines()[-1])
    assert reg["responsavel"] == "Advogada (teste)" and reg["arquivo"] == "documento-01-anonimizado.pdf" and reg["sha256"]
    janelas = Path(simulador["SIM_LOG"]).read_text()
    assert "choose from list" in janelas and "Seu nome" in janelas and "digite AUTORIZO" in janelas
    assert janelas.count("activate") >= 3                                   # janelas trazidas para a frente
    diario = (tmp_path / "home/Library/Logs/CM-Calculadora/liberacao.log").read_text()
    assert "LIBERADO: documento-01-anonimizado.pdf" in diario
    assert "uso:" not in r.stdout + r.stderr


@pytest.mark.parametrize("resp,motivo", [
    ({"SIM_CANCELAR_EM": "lista"}, "nenhuma cópia escolhida"),
    ({"SIM_CANCELAR_EM": "nome"}, "cancelado na janela do nome"),
    ({"SIM_CANCELAR_EM": "confirmacao"}, "cancelado na confirmação"),            # Enter/Esc/Cancelar
    ({"SIM_CONFIRMA": "sim"}, "confirmação não digitada"),
    ({"SIM_CONFIRMA": ""}, "confirmação não digitada"),
    ({"SIM_NOMES": " |  | "}, "nome não informado"),                        # três vezes em branco
    ({"SIM_ESCOLHA": "outro-arquivo.pdf"}, "não está entre as aprovadas"),
])
def test_nada_e_liberado_sem_confirmacao_expressa(tmp_path, aprovado, simulador, resp, motivo):
    r = liberar(tmp_path, simulador, **resp)
    assert motivo in r.stdout, r.stdout + r.stderr
    assert liberados(tmp_path) == []
    assert "uso:" not in r.stdout + r.stderr


def test_nome_em_branco_e_perguntado_de_novo(tmp_path, aprovado, simulador):
    r = liberar(tmp_path, simulador, SIM_NOMES=" |Advogada (teste)")
    assert r.returncode == 0 and liberados(tmp_path) == ["documento-01-anonimizado.pdf"]


def test_reprovada_nao_aparece_para_liberacao(tmp_path, simulador):
    pdf = pymupdf.open()
    pg = pdf.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 600, 840), False)
    pix.set_rect(pix.irect, (250, 250, 250))
    pg.insert_image(pg.rect, pixmap=pix)
    arq = tmp_path / "escaneado.pdf"
    pdf.save(arq)
    rodar("Anonimizar parecer.command", tmp_path, CM_TESTE_ARQUIVO=str(arq), CM_TESTE_TERMOS="")
    r = liberar(tmp_path, simulador)
    assert r.returncode != 0 and "nenhuma cópia aprovada" in r.stdout and liberados(tmp_path) == []


def test_pagina_digitalizada_interrompe(tmp_path):
    pdf = pymupdf.open()
    pg = pdf.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 600, 840), False)
    pix.set_rect(pix.irect, (250, 250, 250))
    pg.insert_image(pg.rect, pixmap=pix)                                    # página escaneada
    pg.insert_text((40, 60), "texto de OCR invisivel CPF 123.456.789-09", render_mode=3)
    arq = tmp_path / "escaneado.pdf"
    pdf.save(arq)
    r = rodar("Anonimizar parecer.command", tmp_path, CM_TESTE_ARQUIVO=str(arq), CM_TESTE_TERMOS="")
    assert r.returncode == 3
    assert "PROCEDIMENTO INTERROMPIDO" in r.stdout and "digitalizada" in r.stdout


def test_formato_nao_suportado(tmp_path):
    doc = tmp_path / "parecer.docx"
    doc.write_bytes(b"x")
    r = rodar("Anonimizar parecer.command", tmp_path, CM_TESTE_ARQUIVO=str(doc), CM_TESTE_TERMOS="")
    assert r.returncode != 0 and "não suportado" in (r.stdout + r.stderr)


def test_icones_nao_mencionam_pasta_de_dados():
    """Os ícones só chamam o sistema: nenhum caminho de dados no texto (a proteção continua valendo)."""
    for script in FERR.glob("*.command"):
        assert "CM-Calculos-Dados" not in script.read_text()
