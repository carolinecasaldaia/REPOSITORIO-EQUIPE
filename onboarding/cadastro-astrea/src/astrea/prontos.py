#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quem já está pronto para receber a marca "01 - OK -" na pasta.

O prefixo é a marcação dela: quer dizer "pasta em ordem e enviada ao jurídico".
A automação **não renomeia** — decisão dela em 21/08/2026: prefere ser avisada
e marcar à mão. Aqui só se confere o que é objetivo:

    pasta com as 5 subpastas  +  contrato assinado arquivado
    +  onboarding gerado  +  contato no Astrea  +  caso aberto

Faltando qualquer um, o cliente não entra na lista — e o que falta aparece,
para ela saber o que resolver.
"""

import json
import re

SUBPASTAS = ("CONTRATO HO", "DOC CLIENTE", "DOC ESCRITÓRIO", "ONBOARDING", "PETIÇÕES")
JA_MARCADA = re.compile(r"\bOK\b\s*[-–]")


def _tem_subpastas(pasta) -> bool:
    nomes = {p.name.upper().replace("Ó", "O").replace("Õ", "O").replace("Ç", "C")
             for p in pasta.iterdir() if p.is_dir()}
    esperadas = {s.upper().replace("Ó", "O").replace("Õ", "O").replace("Ç", "C") for s in SUBPASTAS}
    return len(esperadas - nomes) == 0


def _tem_arquivo(pasta, subpasta, comeco="") -> bool:
    alvo = pasta / subpasta
    if not alvo.is_dir():
        return False
    return any(a.suffix.lower() == ".pdf" and a.name.lower().startswith(comeco.lower())
               for a in alvo.iterdir() if a.is_file())


def avaliar(pasta, registro=None, tem_caso=None) -> dict:
    """
    Diz o que falta para a pasta poder ser marcada.

    `registro` é a linha do banco de controle (contato no Astrea); `tem_caso`
    vem de fora, porque descobrir isso exige consultar o Astrea.
    """
    faltas = []
    if not _tem_subpastas(pasta):
        faltas.append("subpastas")
    if not _tem_arquivo(pasta, "CONTRATO HO", "contrato"):
        faltas.append("contrato assinado")
    if not _tem_arquivo(pasta, "ONBOARDING", "onboarding"):
        faltas.append("onboarding")
    if not (registro and registro.get("astrea_contato_id")):
        faltas.append("contato no Astrea")
    if tem_caso is False:
        faltas.append("caso no Astrea")
    return {"pasta": pasta, "faltas": faltas, "pronto": not faltas}


def ja_marcada(nome_pasta: str) -> bool:
    return bool(JA_MARCADA.search((nome_pasta or "").upper()))


def registros_por_pasta(banco) -> dict:
    """Mapa caminho -> dados do banco de controle (usa a API do Controle)."""
    mapa = {}
    for linha in banco.listar(limite=2000):
        mapa[linha["caminho"]] = {
            "nome": linha["nome_cliente"],
            "astrea_contato_id": linha["astrea_contato_id"],
            "dados": json.loads(linha["dados_json"] or "{}"),
        }
    return mapa
