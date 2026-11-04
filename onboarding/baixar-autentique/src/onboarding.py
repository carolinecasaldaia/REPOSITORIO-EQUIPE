#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Último passo da rodada: gerar o PDF de onboarding do cliente.

Como no separador, o programa NÃO é reescrito aqui — quem gera é o
`GERADOR ONBOARDING/gerar_onboarding.py` que já roda no escritório, chamado no
modo linha de comando com a pasta do cliente. Ele lê o contrato recém-arquivado
em `CONTRATO HO`, preenche o `gerador_pdf.html` num Chrome invisível e grava
`onboarding_<nome>.pdf` na subpasta `ONBOARDING`.

Duas situações que NÃO são erro e viram recado no relatório:

- **Busca e apreensão**: o banco adverso não consta nesses contratos, e é campo
  obrigatório do onboarding. O gerador recusa e diz o que falta; o contrato
  continua arquivado, e você termina pelo atalho *Gerar Onboarding do Cliente*.
- **Onboarding já existe** na pasta: não gera de novo (o gerador criaria um
  `(2)`), só avisa.
"""

import re
import subprocess
from pathlib import Path

from . import banco as banco_adverso

PASTA_ONBOARDING = ("ONBOARDING", "ON BOARDING")
_FALTANDO = re.compile(r"Falta preencher:\s*(.+)", re.I)


def _subpasta(pasta_cliente: Path):
    existentes = {p.name.strip().upper(): p for p in pasta_cliente.iterdir() if p.is_dir()}
    for nome in PASTA_ONBOARDING:
        if nome in existentes:
            return existentes[nome]
    return None


def ja_tem_onboarding(pasta_cliente) -> Path:
    """Devolve o onboarding que já existe na pasta do cliente, se houver."""
    pasta_cliente = Path(pasta_cliente)
    if not pasta_cliente.is_dir():
        return None
    alvo = _subpasta(pasta_cliente) or pasta_cliente
    for arquivo in sorted(alvo.glob("*.pdf")):
        if arquivo.name.lower().startswith("onboarding"):
            return arquivo
    return None


def _novo_arquivo(pasta_cliente, antes):
    depois = set()
    alvo = _subpasta(Path(pasta_cliente)) or Path(pasta_cliente)
    depois.update(alvo.glob("*.pdf"))
    novos = [a for a in depois if a not in antes]
    return sorted(novos, key=lambda p: p.stat().st_mtime)[-1] if novos else None


def gerar(pasta_cliente, config, timeout: int = 300) -> dict:
    """
    Gera o onboarding do cliente. Nunca levanta exceção: devolve o que houve.

    {'situacao': gerado | ja_existia | pendente | erro, 'arquivo': Path|None,
     'motivo': str}
    """
    pasta_cliente = Path(pasta_cliente)
    gerador = Path(config.gerador_onboarding)
    python = Path(config.python_onboarding)

    existente = ja_tem_onboarding(pasta_cliente)
    if existente is not None:
        return {"situacao": "ja_existia", "arquivo": existente,
                "motivo": "O onboarding já estava na pasta (%s)." % existente.name}

    if not gerador.exists():
        return {"situacao": "erro", "arquivo": None,
                "motivo": "Gerador de onboarding não encontrado em %s." % gerador}
    if not python.exists():
        return {"situacao": "erro", "arquivo": None,
                "motivo": ("O ambiente do gerador de onboarding ainda não foi preparado. "
                           "Abra uma vez o atalho 'Gerar Onboarding do Cliente'.")}

    alvo = _subpasta(pasta_cliente) or pasta_cliente
    antes = set(alvo.glob("*.pdf"))

    try:
        resultado = subprocess.run(
            [str(python), str(gerador), str(pasta_cliente)],
            cwd=str(gerador.parent), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"situacao": "erro", "arquivo": None,
                "motivo": "O gerador de onboarding demorou demais (mais de %d s)." % timeout}
    except OSError as erro:
        return {"situacao": "erro", "arquivo": None,
                "motivo": "Não consegui chamar o gerador de onboarding: %s" % erro}

    saida = "%s\n%s" % (resultado.stdout or "", resultado.stderr or "")

    # Busca e apreensão não nomeia o banco no contrato de honorários. Antes de
    # desistir, procura no contrato de financiamento que o cliente mandou.
    if resultado.returncode != 0 and "Banco adverso" in saida:
        nome, arquivo = banco_adverso.procurar_no_cliente(pasta_cliente)
        if nome:
            try:
                resultado = subprocess.run(
                    [str(python), str(gerador), str(pasta_cliente), "--banco", nome],
                    cwd=str(gerador.parent), capture_output=True, text=True, timeout=timeout)
                saida = "%s\n%s" % (resultado.stdout or "", resultado.stderr or "")
            except (subprocess.TimeoutExpired, OSError):
                pass
            if resultado.returncode == 0:
                novo = _novo_arquivo(pasta_cliente, antes)
                return {"situacao": "gerado", "arquivo": novo,
                        "motivo": ("Onboarding gerado%s. Banco adverso (%s) lido de %s — "
                                   "confira, veio do contrato de financiamento do cliente."
                                   % ((": " + novo.name) if novo else "", nome,
                                      Path(arquivo).name if arquivo else "documento do cliente"))}

    if resultado.returncode != 0:
        faltando = _FALTANDO.search(saida)
        if faltando:
            return {"situacao": "pendente", "arquivo": None,
                    "motivo": ("Onboarding não gerado — falta %s. É o caso das buscas e "
                               "apreensões, em que o banco não consta no contrato: "
                               "termine pelo atalho 'Gerar Onboarding do Cliente'."
                               % faltando.group(1).strip().rstrip("."))}
        ultima = [l for l in saida.splitlines() if l.strip()]
        return {"situacao": "erro", "arquivo": None,
                "motivo": "O gerador de onboarding falhou: %s" % (ultima[-1][:200] if ultima else "sem detalhe")}

    novo = _novo_arquivo(pasta_cliente, antes)
    return {"situacao": "gerado", "arquivo": novo,
            "motivo": "Onboarding gerado%s." % ((": " + novo.name) if novo else "")}
