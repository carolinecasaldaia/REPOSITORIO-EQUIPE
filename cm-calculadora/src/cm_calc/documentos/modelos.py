"""Estruturas de documentos, páginas e achados com referência de origem."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class TipoDocumento(str, Enum):
    CONTRATO = "contrato"
    SENTENCA = "sentença"
    ACORDAO = "acórdão"
    EMBARGOS_DECISAO = "decisão de embargos de declaração"
    DECISAO = "decisão interlocutória/monocrática"
    PETICAO_INICIAL = "petição inicial"
    CONTESTACAO = "contestação"
    RECURSO = "razões de recurso"
    COMPROVANTE = "comprovante de pagamento"
    PLANILHA = "planilha financeira"
    LAUDO = "laudo/parecer"
    CERTIDAO = "certidão"
    DESCONHECIDO = "não classificado"


DECISORIOS = {TipoDocumento.SENTENCA, TipoDocumento.ACORDAO, TipoDocumento.EMBARGOS_DECISAO, TipoDocumento.DECISAO}
ALEGACOES = {TipoDocumento.PETICAO_INICIAL, TipoDocumento.CONTESTACAO, TipoDocumento.RECURSO}


class Pagina(BaseModel):
    numero: int
    """Página no arquivo de origem (1 = primeira)."""
    texto: str
    referencia_pje: str | None = None
    """Ex.: 'Num. 12345678 - Pág. 3', quando impresso no rodapé."""

    @property
    def tem_texto(self) -> bool:
        return len(self.texto.strip()) >= 20


class Documento(BaseModel):
    id: str
    arquivo: str
    sha256: str
    tipo: TipoDocumento
    paginas: list[Pagina]
    confianca: float = Field(ge=0, le=1)
    indicios: list[str] = Field(default_factory=list)
    data: date | None = None
    instancia_superior: bool = False
    """Para embargos: True quando opostos contra acórdão."""
    tabela: list[dict[str, str]] | None = None
    """Linhas de planilha (cabeçalho normalizado -> valor em texto)."""

    @property
    def texto(self) -> str:
        return "\n".join(p.texto for p in self.paginas)

    def pagina_do_trecho(self, inicio: int) -> Pagina:
        """Página que contém a posição ``inicio`` de ``self.texto``."""
        pos = 0
        for p in self.paginas:
            fim = pos + len(p.texto) + 1
            if inicio < fim:
                return p
            pos = fim
        return self.paginas[-1]


class Fonte(BaseModel):
    documento_id: str
    arquivo: str
    tipo_documento: TipoDocumento
    pagina: int
    referencia_pje: str | None = None
    trecho: str

    def referencia(self) -> str:
        ref = f"{self.arquivo}, p. {self.pagina}"
        if self.referencia_pje:
            ref += f" ({self.referencia_pje})"
        return ref


class Natureza(str, Enum):
    CONTRATUAL = "contratual"
    RECONHECIDO = "reconhecido em decisão"
    FUNDAMENTACAO = "fundamentação de decisão"
    ALEGADO = "alegação de parte"
    COMPROVADO = "comprovante/planilha"


def fonte_de(doc: Documento, inicio: int, fim: int, margem: int = 60) -> Fonte:
    texto = doc.texto
    a, b = max(0, inicio - margem), min(len(texto), fim + margem)
    pag = doc.pagina_do_trecho(inicio)
    return Fonte(documento_id=doc.id, arquivo=doc.arquivo, tipo_documento=doc.tipo, pagina=pag.numero,
                 referencia_pje=pag.referencia_pje, trecho=" ".join(texto[a:b].split()))
