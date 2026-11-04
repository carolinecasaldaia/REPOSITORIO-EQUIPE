"""Conferência e aprovação do quadro pela advogada responsável.

Regras:
- Confirmar exige o nome da responsável; fica registrado com data e hora.
- Parâmetro conflitante ou ausente só é confirmado com o valor escolhido.
- Parâmetro com lacunas só é confirmado com os detalhes que as suprem.
- Ocorrência bloqueante exige registro de ciência.
- ``bloqueios`` lista tudo o que impede o cálculo definitivo.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .modelos import QuadroParametros, StatusParametro as S


class AprovacaoInvalida(ValueError):
    pass


def _agora() -> datetime:
    return datetime.now().replace(microsecond=0)


def _resp(responsavel: str) -> str:
    if not responsavel or not responsavel.strip():
        raise AprovacaoInvalida("informe a responsável pela conferência")
    return responsavel.strip()


def confirmar(q: QuadroParametros, pid: str, responsavel: str, valor: str | None = None,
              detalhes: dict[str, str] | None = None, observacao: str | None = None) -> None:
    p = q.parametros.get(pid)
    if p is None:
        raise AprovacaoInvalida(f"parâmetro inexistente: {pid}")
    if p.status in (S.CONFLITANTE, S.AUSENTE) and valor is None:
        raise AprovacaoInvalida(f"{pid}: {p.status.value} — informe o valor a adotar")
    if p.status is S.INSUFICIENTE and valor is None and detalhes is None:
        raise AprovacaoInvalida(f"{pid}: complete as lacunas ({'; '.join(p.observacoes)}) antes de confirmar")
    p.valor_confirmado = valor if valor is not None else p.valor
    if detalhes is not None:
        p.detalhes_confirmados = {**p.detalhes, **detalhes}
    p.status = S.CONFIRMADO
    p.confirmado_por = _resp(responsavel)
    p.confirmado_em = _agora()
    if observacao:
        p.observacoes.append(f"[{p.confirmado_por}] {observacao}")


def rejeitar(q: QuadroParametros, pid: str, responsavel: str, motivo: str) -> None:
    p = q.parametros.get(pid)
    if p is None:
        raise AprovacaoInvalida(f"parâmetro inexistente: {pid}")
    if not motivo.strip():
        raise AprovacaoInvalida("informe o motivo da rejeição")
    p.status = S.REJEITADO
    p.confirmado_por = _resp(responsavel)
    p.confirmado_em = _agora()
    p.observacoes.append(f"[{p.confirmado_por}] rejeitado: {motivo}")


def confirmar_pagamentos(q: QuadroParametros, responsavel: str) -> None:
    if not q.pagamentos:
        raise AprovacaoInvalida("não há pagamentos extraídos para confirmar")
    q.pagamentos_status = S.CONFIRMADO
    q.pagamentos_confirmados_por = _resp(responsavel)
    q.pagamentos_confirmados_em = _agora()


def dar_ciencia(q: QuadroParametros, ocorrencia_id: str, responsavel: str) -> None:
    for o in q.ocorrencias:
        if o.id == ocorrencia_id:
            o.ciencia_por = _resp(responsavel)
            o.ciencia_em = _agora()
            return
    raise AprovacaoInvalida(f"ocorrência inexistente: {ocorrencia_id}")


def bloqueios(q: QuadroParametros) -> list[str]:
    out = []
    for p in q.parametros.values():
        if p.status is S.CONFIRMADO:
            continue
        if p.status is S.REJEITADO and not p.obrigatorio:
            continue
        if p.obrigatorio or p.status in (S.CONFLITANTE, S.INSUFICIENTE):
            out.append(f"parâmetro {p.id} ({p.descricao}): {p.status.value}")
    if q.pagamentos_status is not S.CONFIRMADO:
        out.append(f"pagamentos: {q.pagamentos_status.value}")
    for o in q.ocorrencias:
        if o.bloqueia and not o.ciencia_por:
            out.append(f"ocorrência {o.id} ({o.tipo.value}) sem ciência registrada")
    return out


def salvar(q: QuadroParametros, caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(q.model_dump_json(indent=2), encoding="utf-8")


def carregar(caminho: Path) -> QuadroParametros:
    return QuadroParametros.model_validate_json(caminho.read_text(encoding="utf-8"))
