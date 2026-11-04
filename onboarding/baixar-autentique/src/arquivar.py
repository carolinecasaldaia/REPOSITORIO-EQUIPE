#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Guarda o PDF assinado na pasta do cliente e separa os documentos do envelope.

A separação NÃO é reescrita aqui: este módulo carrega o
`SEPARADOR AUTENTIQUE/separar_autentique.py` que já roda no escritório e usa as
funções dele (`analisar`, `gravar`, `resolver_subpasta`). Assim, quando o
modelo do contrato mudar, existe um lugar só para ajustar os títulos.

Resultado de cada envelope:
    CONTRATO HO/     <nome do envelope> [assinado].pdf   (envelope inteiro)
    CONTRATO HO/     Contrato HO Assinado.pdf
    DOC ESCRITÓRIO/  Procuracao Assinada.pdf
    DOC ESCRITÓRIO/  Declaracao de Hipo Assinada.pdf
    DOC ESCRITÓRIO/  Declaracao de Residencia Assinada.pdf   (quando houver)
"""

import hashlib
import importlib.util
import re
import sys
from pathlib import Path

_separador = None

# A pasta do cliente tem SEMPRE estas cinco subpastas — padrão do escritório.
SUBPASTAS_PADRAO = ("CONTRATO HO", "DOC CLIENTE", "DOC ESCRITÓRIO",
                    "ONBOARDING", "PETIÇÕES")


class ErroArquivamento(Exception):
    """Não deu para guardar o documento na pasta do cliente."""


# ---------------------------------------------------------------------------
# Separador
# ---------------------------------------------------------------------------

def carregar_separador(caminho):
    """Importa o separador existente uma única vez."""
    global _separador
    if _separador is not None:
        return _separador
    caminho = Path(caminho)
    if not caminho.exists():
        raise ErroArquivamento("Separador não encontrado em %s" % caminho)
    spec = importlib.util.spec_from_file_location("separar_autentique", str(caminho))
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["separar_autentique"] = modulo
    spec.loader.exec_module(modulo)
    _separador = modulo
    return modulo


def analisar_envelope(pdf, separador_py):
    """
    Lê o PDF e devolve (reader, secoes, relatorio, tipos).

    `tipos` é o conjunto de documentos reconhecidos: {'contrato', 'procuracao',
    'hipossuficiencia', 'residencia'}.
    """
    separador = carregar_separador(separador_py)
    try:
        reader = separador.PdfReader(str(pdf))
        secoes, relatorio, _validacao = separador.analisar(reader)
    except Exception as erro:                     # PDF corrompido, protegido...
        raise ErroArquivamento("Não consegui ler o PDF assinado: %s" % erro)
    tipos = {s["tipo"]["chave"] for s in secoes if not s.get("presumido")}
    return reader, secoes, relatorio, tipos


def eh_envelope_de_onboarding(tipos) -> bool:
    """
    Só entra na pasta do cliente o envelope que É do onboarding.

    Critério: reconhecer pelo título ao menos o contrato de prestação de
    serviços, a procuração ou a declaração de hipossuficiência. Petição,
    acordo e qualquer outro documento assinado no Autentique ficam de fora —
    é o que impede a automação de espalhar arquivo em pasta de cliente.
    """
    return bool(tipos & {"contrato", "procuracao", "hipossuficiencia"})


# ---------------------------------------------------------------------------
# Arquivos
# ---------------------------------------------------------------------------

def garantir_subpastas(pasta_cliente, separador) -> None:
    """
    Cria as cinco subpastas do padrão, respeitando grafias antigas.

    Existe por um defeito real: pastas do formato antigo (arquivos soltos, sem
    subpasta) faziam o separador gravar contrato, procuração e hipossuficiência
    **soltos na raiz** — porque ele só usa subpasta quando ela já existe. O
    resultado era pasta de cliente com só ONBOARDING dentro, que é a única que
    o gerador cria por conta própria. Encontrado em 18/08/2026 em 7 clientes.
    """
    pasta_cliente = Path(pasta_cliente)
    pasta_cliente.mkdir(parents=True, exist_ok=True)
    existentes = {separador.normalizar(p.name): p
                  for p in pasta_cliente.iterdir() if p.is_dir()}
    # Grafias já usadas em pastas antigas. Atenção: NÃO dá para reaproveitar
    # `separador.PASTA_ESCRITORIO`, porque lá "DOC CLIENTE" entra como variante
    # de "DOC ESCRITÓRIO" (é uma lista de "onde pode estar", não de sinônimos) —
    # usá-la aqui faria a automação deixar de criar uma das duas.
    variantes = {
        "CONTRATO HO": ("CONTRATO HO", "CONTRATO DE HONORÁRIOS",
                        "CONTRATO HONORÁRIOS", "CONTRATO"),
        "DOC ESCRITÓRIO": ("DOC ESCRITÓRIO", "DOCS ESCRITÓRIO", "DOC ESCRITORIO"),
        "DOC CLIENTE": ("DOC CLIENTE", "DOCS CLIENTE"),
        "PETIÇÕES": ("PETIÇÕES", "PETICOES", "PETIÇÃO"),
    }
    for nome in SUBPASTAS_PADRAO:
        aceitos = variantes.get(nome, [nome])
        if any(separador.normalizar(v) in existentes for v in aceitos):
            continue                       # já existe, com esta ou outra grafia
        (pasta_cliente / nome).mkdir(exist_ok=True)


def impressao_digital(caminho) -> str:
    digest = hashlib.sha256()
    with open(str(caminho), "rb") as arquivo:
        for pedaco in iter(lambda: arquivo.read(1024 * 256), b""):
            digest.update(pedaco)
    return digest.hexdigest()


def nome_de_arquivo(nome_documento: str) -> str:
    """'CONTRATO - PROCURAÇÃO - FULANO' -> 'CONTRATO - PROCURAÇÃO - FULANO [assinado].pdf'."""
    nome = re.sub(r"[/\\:\x00-\x1f]+", " ", (nome_documento or "documento").strip())
    nome = re.sub(r"\s+", " ", nome).strip()
    nome = re.sub(r"(?i)\s*\[assinado\]\s*$", "", nome)
    nome = re.sub(r"(?i)\.pdf$", "", nome).strip() or "documento"
    return "%s [assinado].pdf" % nome[:120].strip()


def ja_arquivado(pasta_cliente, digital: str):
    """Devolve o PDF já existente com o mesmo conteúdo, se houver."""
    pasta_cliente = Path(pasta_cliente)
    if not pasta_cliente.is_dir():
        return None
    for caminho in pasta_cliente.rglob("*.pdf"):
        try:
            if caminho.is_file() and impressao_digital(caminho) == digital:
                return caminho
        except OSError:
            continue
    return None


def arquivar(pdf, pasta_cliente, nome_documento, separador_py,
             separar: bool = True, reader=None, secoes=None, relatorio=None) -> dict:
    """
    Grava o envelope e (opcionalmente) os documentos separados.

    Devolve {'envelope': Path, 'documentos': [(rótulo, Path)], 'ja_existia': bool}.
    Arquivo com o mesmo nome não é sobrescrito — sai como "... (2).pdf",
    mesma regra do separador manual.
    """
    separador = carregar_separador(separador_py)
    pasta_cliente = Path(pasta_cliente)
    pasta_cliente.mkdir(parents=True, exist_ok=True)

    if reader is None or secoes is None or relatorio is None:
        reader, secoes, relatorio, _tipos = analisar_envelope(pdf, separador_py)

    digital = impressao_digital(pdf)
    existente = ja_arquivado(pasta_cliente, digital)
    if existente is not None:
        return {"envelope": existente, "documentos": [], "ja_existia": True}

    # As subpastas são criadas ANTES de gravar: sem isso, pasta no formato
    # antigo recebia tudo solto na raiz.
    garantir_subpastas(pasta_cliente, separador)
    usar_subpastas = True

    # 1) O envelope inteiro, do jeito que veio do Autentique.
    destino_envelope = (separador.resolver_subpasta(pasta_cliente, separador.PASTA_CONTRATO)
                        if usar_subpastas else pasta_cliente)
    destino_envelope.mkdir(parents=True, exist_ok=True)
    caminho_envelope = separador.nome_unico(destino_envelope / nome_de_arquivo(nome_documento))
    caminho_envelope.write_bytes(Path(pdf).read_bytes())

    # 2) Os documentos separados, cada um com o relatório de assinaturas ao final.
    documentos = []
    if separar and secoes:
        for secao in secoes:
            paginas = list(secao["paginas"]) + (relatorio or [])
            tipo = secao["tipo"]
            pasta = (separador.resolver_subpasta(pasta_cliente, tipo["subpasta"])
                     if usar_subpastas else pasta_cliente)
            gravado = separador.gravar(reader, paginas, pasta / tipo["arquivo"], False)
            documentos.append((tipo["rotulo"], gravado))

    return {"envelope": caminho_envelope, "documentos": documentos, "ja_existia": False}


def guardar_na_quarentena(pdf, pasta_quarentena, nome_documento) -> Path:
    """
    Documento que não entrou na pasta de nenhum cliente fica guardado aqui.

    Nada é apagado sem a Caroline ver: a quarentena é o que permite conferir e
    arquivar à mão depois, sem precisar baixar de novo do Autentique.
    """
    pasta_quarentena = Path(pasta_quarentena)
    pasta_quarentena.mkdir(parents=True, exist_ok=True)
    destino = pasta_quarentena / nome_de_arquivo(nome_documento)
    n = 2
    while destino.exists():
        destino = pasta_quarentena / ("%s (%d).pdf" % (nome_de_arquivo(nome_documento)[:-4], n))
        n += 1
    destino.write_bytes(Path(pdf).read_bytes())
    return destino
