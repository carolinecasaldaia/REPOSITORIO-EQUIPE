#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fluxo inteiro, do documento assinado até o arquivo na pasta do cliente.

O Autentique é substituído por um dublê que devolve documentos prontos e
"baixa" um PDF de mentira com a mesma estrutura do envelope real. O separador
usado é o de verdade, o mesmo que roda no escritório.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import arquivar, servico                    # noqa: E402
from src.config import get_config                    # noqa: E402
from src.estado import Estado                        # noqa: E402
from src.log import Log                              # noqa: E402
from tests.test_autentique import assinatura, documento   # noqa: E402
from tests.util_pdf import documento_qualquer, envelope_de_onboarding  # noqa: E402


class AutentiqueFalso(object):
    """
    Dublê do Autentique.

    Por padrão o PDF gerado traz, na qualificação, o nome do primeiro
    signatário que não é do escritório — que é como o contrato de verdade vem.
    `contratante` permite separar os dois (contrato com corresponsável, nome
    abreviado no cadastro do Autentique).
    """

    def __init__(self, documentos, gerar_pdf=None, contratante=None, responsavel=""):
        self.documentos = documentos
        self.gerar_pdf = gerar_pdf
        self.contratante = contratante
        self.responsavel = responsavel
        self.baixados = []

    def prontos(self, **_kwargs):
        return list(self.documentos)

    def baixar_pdf(self, url, destino):
        self.baixados.append(url)
        if self.gerar_pdf is not None:
            self.gerar_pdf(destino)
        else:
            envelope_de_onboarding(destino, contratante=self.contratante or self._nome_padrao(),
                                   responsavel=self.responsavel)
        return Path(destino).stat().st_size

    def _nome_padrao(self):
        for documento in self.documentos:
            for assinante in documento["signatures"]:
                if not (assinante.get("email") or "").endswith("@carolinemacedoadv.com"):
                    return (assinante.get("name") or "").upper()
        return "FULANO DE TAL SOUZA"


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    """Config apontando para pastas temporárias, sem tocar no Drive real."""
    clientes = tmp_path / "PREPARAÇÃO PARA INGRESSO"
    clientes.mkdir()
    monkeypatch.setenv("PASTA_CLIENTES", str(clientes))
    monkeypatch.setenv("PASTA_DADOS", str(tmp_path / "dados"))
    monkeypatch.setenv("PASTA_RELATORIOS", str(tmp_path / "relatorios"))
    monkeypatch.setenv("AUTENTIQUE_TOKEN", "chave-de-teste")
    gerador = tmp_path / "gerador_falso.py"
    gerador.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "destino = Path(sys.argv[1]) / 'ONBOARDING'\n"
        "destino.mkdir(parents=True, exist_ok=True)\n"
        "(destino / 'onboarding_teste.pdf').write_bytes(b'%PDF-1.4 onboarding')\n",
        encoding="utf-8")
    monkeypatch.setenv("GERADOR_ONBOARDING", str(gerador))
    monkeypatch.setenv("PYTHON_ONBOARDING", sys.executable)
    config = get_config(recarregar=True)
    config.preparar_pastas()
    log = Log(config.pasta_logs, mostrar_na_tela=False)
    estado = Estado.carregar(config.arquivo_estado)
    return config, estado, log, clientes


def envelope(nome_cliente, email, id_doc="doc1", quando="2026-08-15T10:00:00.000000Z"):
    return documento(
        [assinatura(nome_cliente, email, quando),
         assinatura("Caroline Macedo", "contato@carolinemacedoadv.com", quando)],
        id=id_doc, name="CONTRATO - PROCURACAO - DECLARACAO - %s" % nome_cliente.split()[0])


def pasta_de_cliente(raiz, mes, nome):
    destino = Path(raiz) / mes / nome
    for subpasta in ("CONTRATO HO", "DOC CLIENTE", "DOC ESCRITÓRIO", "ONBOARDING", "PETIÇÕES"):
        (destino / subpasta).mkdir(parents=True, exist_ok=True)
    return destino


# --- primeira rodada -------------------------------------------------------

def test_primeira_rodada_marca_historico_e_nao_baixa_nada(ambiente):
    config, estado, log, raiz = ambiente
    pasta_de_cliente(raiz, "AGOSTO 2026", "01 - OK - ANDESON LOPES DA SILVA")
    api = AutentiqueFalso([envelope("Anderson Lopes da Silva", "anderson@gmail.com")])

    resumo = servico.rodar(config, estado, log, api)

    assert resumo["primeira_vez"] is True
    assert resumo["baixados"] == 0
    assert api.baixados == []
    assert estado.situacao("doc1") == "historico"


def test_conferir_antes_de_ligar_nao_ativa_a_automacao(ambiente):
    """Conferir é só olhar: não pode marcar o histórico e ligar sem querer."""
    config, estado, log, raiz = ambiente
    api = AutentiqueFalso([envelope("Anderson Lopes da Silva", "anderson@gmail.com")])

    resumo = servico.rodar(config, estado, log, api, somente_conferir=True)

    assert resumo["primeira_vez"] is True
    assert estado.vazio()
    assert not Path(config.arquivo_estado).exists()


# --- caso feliz ------------------------------------------------------------

def test_contrato_assinado_cai_na_pasta_do_cliente_ja_separado(ambiente):
    config, estado, log, raiz = ambiente
    destino = pasta_de_cliente(raiz, "AGOSTO 2026", "01 - OK - ANDESON LOPES DA SILVA")
    estado.anotar("antigo", situacao="historico")     # já ligada: não é primeira rodada
    api = AutentiqueFalso([envelope("Anderson Lopes da Silva", "anderson@gmail.com")])

    resumo = servico.rodar(config, estado, log, api)

    assert resumo["baixados"] == 1
    assert estado.situacao("doc1") == "baixado"
    assert (destino / "CONTRATO HO" / "Contrato HO Assinado.pdf").exists()
    assert (destino / "DOC ESCRITÓRIO" / "Procuracao Assinada.pdf").exists()
    assert (destino / "DOC ESCRITÓRIO" / "Declaracao de Hipo Assinada.pdf").exists()
    envelopes = list((destino / "CONTRATO HO").glob("*[assinado]*.pdf"))
    assert envelopes, "o envelope inteiro também é guardado"


def test_o_onboarding_do_cliente_sai_na_mesma_rodada(ambiente):
    config, estado, log, raiz = ambiente
    destino = pasta_de_cliente(raiz, "AGOSTO 2026", "01 - OK - ANDESON LOPES DA SILVA")
    estado.anotar("antigo", situacao="historico")
    api = AutentiqueFalso([envelope("Anderson Lopes da Silva", "anderson@gmail.com")])

    servico.rodar(config, estado, log, api)

    assert (destino / "ONBOARDING" / "onboarding_teste.pdf").exists()
    assert estado.documentos["doc1"]["onboarding"] == "gerado"


def test_onboarding_desligado_nao_gera_nada(ambiente):
    config, estado, log, raiz = ambiente
    destino = pasta_de_cliente(raiz, "AGOSTO 2026", "01 - OK - ANDESON LOPES DA SILVA")
    config.gerar_onboarding = False
    estado.anotar("antigo", situacao="historico")
    api = AutentiqueFalso([envelope("Anderson Lopes da Silva", "anderson@gmail.com")])

    servico.rodar(config, estado, log, api)

    assert not list((destino / "ONBOARDING").glob("*.pdf"))
    assert (destino / "CONTRATO HO" / "Contrato HO Assinado.pdf").exists()


def test_documento_ja_baixado_nao_e_baixado_de_novo(ambiente):
    config, estado, log, raiz = ambiente
    pasta_de_cliente(raiz, "AGOSTO 2026", "01 - OK - ANDESON LOPES DA SILVA")
    estado.anotar("antigo", situacao="historico")
    api = AutentiqueFalso([envelope("Anderson Lopes da Silva", "anderson@gmail.com")])

    servico.rodar(config, estado, log, api)
    resumo = servico.rodar(config, estado, log, api)

    assert resumo["novos"] == 0
    assert len(api.baixados) == 1


# --- cliente novo ----------------------------------------------------------

def test_cliente_sem_pasta_ganha_pasta_nova_no_mes(ambiente):
    config, estado, log, raiz = ambiente
    estado.anotar("antigo", situacao="historico")
    api = AutentiqueFalso([envelope("Josefa Maria dos Santos", "josefa@gmail.com")])

    resumo = servico.rodar(config, estado, log, api)

    assert resumo["baixados"] == 1
    nova = raiz / "AGOSTO 2026" / "JOSEFA MARIA DOS SANTOS"
    assert (nova / "CONTRATO HO" / "Contrato HO Assinado.pdf").exists()
    assert (nova / "PETIÇÕES").is_dir()


def test_criacao_desligada_deixa_o_documento_pendente(ambiente, monkeypatch):
    config, estado, log, raiz = ambiente
    config.criar_pasta = False
    estado.anotar("antigo", situacao="historico")
    api = AutentiqueFalso([envelope("Josefa Maria dos Santos", "josefa@gmail.com")])

    resumo = servico.rodar(config, estado, log, api)

    assert resumo["pendentes"] == 1
    assert list(Path(config.pasta_quarentena).glob("*.pdf")), "o PDF fica na quarentena"
    assert not (raiz / "AGOSTO 2026").exists()


def test_o_dono_da_pasta_e_o_contratante_do_contrato_nao_quem_assinou_primeiro(ambiente):
    """
    Medido em 17/08/2026: em contrato com corresponsável, o primeiro signatário
    pode ser ele. A pasta tem que sair no nome do Cliente Contratante.
    """
    config, estado, log, raiz = ambiente
    estado.anotar("antigo", situacao="historico")
    doc = documento(
        [assinatura("Evandro de Paulo Santos", "evandro@gmail.com", "2026-08-15T10:00:00.000000Z"),
         assinatura("Cristiane Flauzino Rocha de Souza", "cris@gmail.com", "2026-08-15T10:30:00.000000Z"),
         assinatura("Caroline Macedo", "caroline@carolinemacedoadv.com", "2026-08-15T11:00:00.000000Z")],
        id="doc1", name="CONTRATO - PROCURACAO - DECLARACAO")
    api = AutentiqueFalso([doc], contratante="CRISTIANE FLAUZINO ROCHA DE SOUZA",
                          responsavel="EVANDRO DE PAULO SANTOS")

    servico.rodar(config, estado, log, api)

    assert (raiz / "AGOSTO 2026" / "CRISTIANE FLAUZINO ROCHA DE SOUZA").is_dir()
    assert not (raiz / "AGOSTO 2026" / "EVANDRO DE PAULO SANTOS").exists()
    registro = estado.documentos["doc1"]
    assert registro["cliente"] == "CRISTIANE FLAUZINO ROCHA DE SOUZA"
    assert registro["corresponsavel"] == "EVANDRO DE PAULO SANTOS"


def test_nome_abreviado_no_autentique_nao_impede_de_achar_a_pasta(ambiente):
    """No Autentique: "Felipe De Assis F De Souza"; na pasta e no contrato: o nome inteiro."""
    config, estado, log, raiz = ambiente
    destino = pasta_de_cliente(raiz, "AGOSTO 2026", "FELIPE DE ASSIS FERREIRA DE SOUSA")
    estado.anotar("antigo", situacao="historico")
    api = AutentiqueFalso([envelope("Felipe De Assis F De Souza", "felipe@gmail.com")],
                          contratante="FELIPE DE ASSIS FERREIRA DE SOUSA")

    servico.rodar(config, estado, log, api)

    assert (destino / "CONTRATO HO" / "Contrato HO Assinado.pdf").exists()


# --- documento que não é do onboarding -------------------------------------

def test_documento_que_nao_e_onboarding_nao_entra_em_pasta_de_cliente(ambiente):
    config, estado, log, raiz = ambiente
    pasta_de_cliente(raiz, "AGOSTO 2026", "01 - OK - ANDESON LOPES DA SILVA")
    estado.anotar("antigo", situacao="historico")
    api = AutentiqueFalso([envelope("Anderson Lopes da Silva", "anderson@gmail.com")],
                          gerar_pdf=documento_qualquer)

    resumo = servico.rodar(config, estado, log, api)

    assert resumo["ignorados"] == 1
    assert estado.situacao("doc1") == "ignorado"
    assert not list((raiz / "AGOSTO 2026").rglob("*.pdf"))
    assert list(Path(config.pasta_quarentena).glob("*.pdf"))


# --- conferência e repetição -----------------------------------------------

def test_modo_conferir_nao_grava_nada(ambiente):
    config, estado, log, raiz = ambiente
    pasta_de_cliente(raiz, "AGOSTO 2026", "01 - OK - ANDESON LOPES DA SILVA")
    estado.anotar("antigo", situacao="historico")
    api = AutentiqueFalso([envelope("Anderson Lopes da Silva", "anderson@gmail.com")])

    servico.rodar(config, estado, log, api, somente_conferir=True)

    assert not list((raiz / "AGOSTO 2026").rglob("*.pdf"))
    assert estado.situacao("doc1") == ""


def test_mesmo_pdf_baixado_de_novo_nao_duplica_arquivo(ambiente, tmp_path):
    config, estado, log, raiz = ambiente
    destino = pasta_de_cliente(raiz, "AGOSTO 2026", "01 - OK - ANDESON LOPES DA SILVA")
    pdf = envelope_de_onboarding(tmp_path / "envelope.pdf")

    primeiro = arquivar.arquivar(pdf, destino, "CONTRATO - ANDERSON", config.separador)
    segundo = arquivar.arquivar(pdf, destino, "CONTRATO - ANDERSON", config.separador)

    assert primeiro["ja_existia"] is False
    assert segundo["ja_existia"] is True
    assert len(list((destino / "CONTRATO HO").glob("*.pdf"))) == 2  # envelope + contrato


# --- erro no meio do caminho ------------------------------------------------

def test_falha_ao_baixar_vira_erro_e_a_proxima_rodada_tenta_de_novo(ambiente):
    config, estado, log, raiz = ambiente
    pasta_de_cliente(raiz, "AGOSTO 2026", "01 - OK - ANDESON LOPES DA SILVA")
    estado.anotar("antigo", situacao="historico")

    class ApiQueFalha(AutentiqueFalso):
        def baixar_pdf(self, url, destino):
            from src.autentique import ErroAutentique
            raise ErroAutentique("link expirado")

    api = ApiQueFalha([envelope("Anderson Lopes da Silva", "anderson@gmail.com")])
    resumo = servico.rodar(config, estado, log, api)

    assert resumo["erros"] == 1
    assert estado.situacao("doc1") == "erro"
    assert not estado.conhecido("doc1"), "erro não é situação final: retenta na próxima"


# --- pasta antiga, sem subpastas -------------------------------------------

def test_pasta_no_formato_antigo_ganha_as_cinco_subpastas(ambiente):
    """
    Defeito real de 18/08/2026: em pasta antiga (arquivos soltos), o separador
    gravava contrato e procuração SOLTOS na raiz, e só o ONBOARDING aparecia
    como subpasta. Aconteceu com 7 clientes de agosto.
    """
    config, estado, log, raiz = ambiente
    antiga = Path(raiz) / "AGOSTO 2026" / "01 - OK - ANDESON LOPES DA SILVA"
    antiga.mkdir(parents=True)
    (antiga / "CNH.pdf").write_bytes(b"%PDF-1.4 documento do cliente")
    estado.anotar("antigo", situacao="historico")
    api = AutentiqueFalso([envelope("Anderson Lopes da Silva", "anderson@gmail.com")])

    servico.rodar(config, estado, log, api)

    for subpasta in ("CONTRATO HO", "DOC CLIENTE", "DOC ESCRITÓRIO", "ONBOARDING", "PETIÇÕES"):
        assert (antiga / subpasta).is_dir(), "faltou criar %s" % subpasta
    assert (antiga / "CONTRATO HO" / "Contrato HO Assinado.pdf").exists()
    assert (antiga / "DOC ESCRITÓRIO" / "Procuracao Assinada.pdf").exists()
    assert not (antiga / "Contrato HO Assinado.pdf").exists(), "não pode ficar solto na raiz"
    # Desde 18/08/2026 o documento do cliente que estava solto vai para DOC CLIENTE.
    assert (antiga / "DOC CLIENTE" / "CNH.pdf").exists()
    assert not (antiga / "CNH.pdf").exists()


def test_grafia_antiga_de_subpasta_e_respeitada(ambiente):
    """Pasta com DOC ESCRITORIO (sem acento) não ganha uma segunda com acento."""
    config, estado, log, raiz = ambiente
    pasta = Path(raiz) / "AGOSTO 2026" / "01 - OK - ANDESON LOPES DA SILVA"
    (pasta / "DOC ESCRITORIO").mkdir(parents=True)
    (pasta / "CONTRATO HO").mkdir()
    estado.anotar("antigo", situacao="historico")
    api = AutentiqueFalso([envelope("Anderson Lopes da Silva", "anderson@gmail.com")])

    servico.rodar(config, estado, log, api)

    assert (pasta / "DOC ESCRITORIO" / "Procuracao Assinada.pdf").exists()
    assert not (pasta / "DOC ESCRITÓRIO").exists(), "não pode duplicar a subpasta"
