"""Pacote de trechos para interpretação pelo Claude (modelo híbrido).

Regras:
1. Nunca documentos inteiros: só trechos selecionados (até 1.500 caracteres
   cada, no máximo 20 por pacote), ligados a um parâmetro ou ocorrência.
2. Sempre pseudonimizados localmente; a tabela de correspondência não sai.
3. Verificação residual: sobrando padrão de dado pessoal, o pacote é recusado.
4. Exige ``Autorizacao`` (responsável, finalidade, escopo). Sem ela,
   ``PermissionError``. O registro da autorização fica no próprio pacote.
5. O pacote é apenas GRAVADO em disco, na pasta do caso. Este módulo não faz
   chamadas de rede: a leitura pelo Claude Code é um ato posterior e manual.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from ..extracao.modelos import QuadroParametros, StatusParametro as S
from .pseudonimizacao import Pseudonimizador, residuos

MAX_TRECHO = 1500
MAX_TRECHOS = 20


class Autorizacao(BaseModel):
    responsavel: str
    finalidade: str
    escopo: list[str]
    """IDs de parâmetros/ocorrências cujos trechos podem ser enviados."""


class TrechoPacote(BaseModel):
    referencia: str
    pergunta: str
    trecho: str


class Pacote(BaseModel):
    caso_id: str
    criado_em: datetime
    autorizacao: Autorizacao
    trechos: list[TrechoPacote]
    aviso: str = ("Trechos pseudonimizados. Não tentar reidentificar pessoas. Responder apenas sobre a "
                  "interpretação jurídica/numérica do trecho, indicando incertezas.")


def candidatos(q: QuadroParametros) -> dict[str, tuple[str, str]]:
    """Itens que podem precisar de interpretação: id -> (pergunta, trecho original)."""
    out = {}
    for p in q.parametros.values():
        if p.status in (S.INSUFICIENTE, S.CONFLITANTE) and p.fontes:
            pergunta = f"{p.descricao}: {'; '.join(p.observacoes)}"
            out[p.id] = (pergunta, "\n---\n".join(f.trecho for f in p.fontes[:3]))
    for o in q.ocorrencias:
        if o.fontes and o.tipo.value in ("informação insuficiente", "valores contraditórios", "tema só na fundamentação"):
            out[o.id] = (o.texto, "\n---\n".join(f.trecho for f in o.fontes[:3]))
    return out


def montar_pacote(q: QuadroParametros, autorizacao: Autorizacao | None, nomes_conhecidos: list[str] | None = None) -> tuple[Pacote, Pseudonimizador]:
    if autorizacao is None:
        raise PermissionError("envio ao Claude exige autorização específica da advogada responsável")
    if not autorizacao.responsavel.strip() or not autorizacao.finalidade.strip() or not autorizacao.escopo:
        raise PermissionError("autorização incompleta: responsável, finalidade e escopo são obrigatórios")
    cands = candidatos(q)
    fora = [i for i in autorizacao.escopo if i not in cands]
    if fora:
        raise ValueError(f"itens fora dos candidatos a interpretação: {fora}")
    if len(autorizacao.escopo) > MAX_TRECHOS:
        raise ValueError(f"no máximo {MAX_TRECHOS} trechos por pacote")

    ps = Pseudonimizador()
    for n in nomes_conhecidos or []:
        ps._marcador("NOME", n)
    trechos = []
    for i in autorizacao.escopo:
        pergunta, trecho = cands[i]
        t = ps.aplicar(trecho[:MAX_TRECHO])
        perg = ps.aplicar(pergunta)
        # todo valor original já mapeado (de qualquer trecho) não pode sobrar em nenhum trecho
        sobra = residuos(t + "\n" + perg, list(ps.mapa))
        if sobra:
            raise PermissionError(f"pacote recusado: dado pessoal remanescente em '{i}' ({', '.join(sobra)})")
        trechos.append(TrechoPacote(referencia=i, pergunta=perg, trecho=t))
    return Pacote(caso_id=q.caso_id, criado_em=datetime.now().replace(microsecond=0), autorizacao=autorizacao,
                  trechos=trechos), ps


def gravar_pacote(pacote: Pacote, pasta_caso: Path) -> Path:
    destino = pasta_caso / "claude" / "pacotes"
    destino.mkdir(parents=True, exist_ok=True)
    corpo = pacote.model_dump_json(indent=2)
    h = hashlib.sha256(corpo.encode()).hexdigest()[:12]
    arq = destino / f"pacote-{pacote.criado_em:%Y%m%d-%H%M%S}-{h}.json"
    arq.write_text(corpo, encoding="utf-8")
    registro = pasta_caso / "claude" / "registro-envios.jsonl"
    with registro.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"arquivo": arq.name, "sha256_12": h, "responsavel": pacote.autorizacao.responsavel,
                            "finalidade": pacote.autorizacao.finalidade, "itens": pacote.autorizacao.escopo,
                            "criado_em": pacote.criado_em.isoformat()}, ensure_ascii=False) + "\n")
    return arq
