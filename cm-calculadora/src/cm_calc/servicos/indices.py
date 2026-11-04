"""Séries de índices informadas manualmente (CSV), com fonte obrigatória.

Não há download automático (dependeria de serviço externo, ainda não
autorizado). Formato do CSV: duas colunas — competência (AAAA-MM ou MM/AAAA)
e variação mensal em PERCENTUAL (ex.: 0,42 para 0,42%).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ..casos import raiz_dados
from ..documentos.texto import valor_br
from ..motor.atualizacao import SerieMensal

RE_NOME = re.compile(r"^[A-Z0-9][A-Z0-9_\-]{1,30}$")


def pasta_indices(raiz: Path | None = None) -> Path:
    p = (raiz or raiz_dados()) / "indices"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _competencia(s: str) -> str:
    s = s.strip()
    if m := re.fullmatch(r"(\d{4})-(\d{1,2})", s):
        a, mes = int(m.group(1)), int(m.group(2))
    elif m := re.fullmatch(r"(\d{1,2})/(\d{4})", s):
        a, mes = int(m.group(2)), int(m.group(1))
    else:
        raise ValueError(f"competência inválida: {s!r} (use AAAA-MM ou MM/AAAA)")
    if not 1 <= mes <= 12:
        raise ValueError(f"mês inválido: {s!r}")
    return f"{a:04d}-{mes:02d}"


def serie_de_csv(nome: str, conteudo: bytes, fonte: str, embute_correcao: bool = False) -> SerieMensal:
    if not RE_NOME.match(nome):
        raise ValueError("nome da série: MAIÚSCULAS, dígitos, '_' ou '-' (ex.: INPC, IPCA_E)")
    if not fonte.strip():
        raise ValueError("informe a fonte da série (ex.: 'IBGE — tabela 1736, consultada em 21/10/2026')")
    texto = conteudo.decode("utf-8-sig")
    # ';' é o separador padrão (vírgula decimal); ',' só se não houver ';' (então decimal com ponto)
    delim = ";" if ";" in texto else ","
    valores: dict[str, Decimal] = {}
    for i, linha in enumerate(csv.reader(io.StringIO(texto), delimiter=delim), start=1):
        if not linha or not "".join(linha).strip():
            continue
        if i == 1 and not re.search(r"\d", linha[0]):
            continue   # cabeçalho
        if len(linha) < 2:
            raise ValueError(f"linha {i}: esperadas duas colunas")
        comp = _competencia(linha[0])
        bruto = linha[1].strip().replace("%", "")
        try:
            pct = valor_br(bruto) if "," in bruto else Decimal(bruto)
        except (InvalidOperation, ValueError) as e:
            raise ValueError(f"linha {i}: variação inválida {linha[1]!r}") from e
        if comp in valores:
            raise ValueError(f"linha {i}: competência {comp} repetida")
        valores[comp] = pct / Decimal(100)
    if not valores:
        raise ValueError("série vazia")
    h = hashlib.sha256(conteudo).hexdigest()[:12]
    return SerieMensal(nome=nome, valores=valores, fonte=f"{fonte.strip()} [sha256 {h}]", embute_correcao=embute_correcao)


def salvar_serie(s: SerieMensal, raiz: Path | None = None) -> Path:
    arq = pasta_indices(raiz) / f"{s.nome}.json"
    arq.write_text(s.model_dump_json(indent=1), encoding="utf-8")
    return arq


def carregar_series(raiz: Path | None = None) -> dict[str, SerieMensal]:
    out = {}
    for arq in sorted(pasta_indices(raiz).glob("*.json")):
        s = SerieMensal.model_validate(json.loads(arq.read_text(encoding="utf-8")))
        out[s.nome] = s
    return out


def lacunas(s: SerieMensal, inicio: tuple[int, int], fim: tuple[int, int]) -> list[str]:
    from ..motor.datas import competencias_entre
    return [f"{a:04d}-{m:02d}" for a, m in competencias_entre(inicio, fim) if f"{a:04d}-{m:02d}" not in s.valores]
