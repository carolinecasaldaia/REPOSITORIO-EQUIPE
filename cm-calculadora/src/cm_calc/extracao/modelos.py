"""Achados, comandos, parâmetros, ocorrências e o quadro de parâmetros."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field

from ..documentos.modelos import Fonte, Natureza, TipoDocumento


class Achado(BaseModel):
    """Um dado localizado num documento (valor normalizado + origem)."""

    campo: str
    valor: str
    """Forma canônica: decimais com ponto ('0.0199'), datas ISO, textos livres."""
    exibicao: str
    natureza: Natureza
    fonte: Fonte
    detalhes: dict[str, str] = Field(default_factory=dict)


class Tema(str, Enum):
    RESULTADO = "resultado"
    JUROS_REMUNERATORIOS = "juros remuneratórios"
    CAPITALIZACAO = "capitalização"
    EXCLUSAO = "exclusão de cobrança"
    MORA = "mora"
    REPETICAO = "repetição do indébito"
    COMPENSACAO = "compensação"
    CORRECAO = "correção monetária"
    JUROS_MORA = "juros de mora"
    HONORARIOS = "honorários"
    MULTA_DL911 = "multa art. 3º §6º DL 911/1969"
    PERDAS_DANOS = "perdas e danos"
    RESTITUICAO_VEICULO = "restituição do veículo"


class Comando(BaseModel):
    tema: Tema
    chave: str
    """Tema + item (ex.: 'exclusao:tarifa de cadastro') — unidade de substituição entre decisões."""
    efeito: str
    detalhes: dict[str, str] = Field(default_factory=dict)
    natureza: Natureza
    fonte: Fonte
    documento_tipo: TipoDocumento
    documento_data: date | None = None
    lacunas: list[str] = Field(default_factory=list)
    """O que o comando não especifica e precisa ser definido (ex.: índice de correção)."""


class Modificacao(BaseModel):
    chave: str
    anterior: Comando | None
    posterior: Comando
    descricao: str


class StatusParametro(str, Enum):
    EXTRAIDO = "extraído — aguardando conferência"
    CONFLITANTE = "valores conflitantes"
    INSUFICIENTE = "informação insuficiente"
    AUSENTE = "ausente"
    CONFIRMADO = "confirmado pela advogada"
    REJEITADO = "rejeitado pela advogada"
    INFORMATIVO = "informativo"


class Alternativa(BaseModel):
    valor: str
    exibicao: str
    natureza: Natureza
    fonte: Fonte


class Parametro(BaseModel):
    id: str
    grupo: str
    descricao: str
    obrigatorio: bool
    status: StatusParametro
    valor: str | None = None
    exibicao: str | None = None
    detalhes: dict[str, str] = Field(default_factory=dict)
    fontes: list[Fonte] = Field(default_factory=list)
    alternativas: list[Alternativa] = Field(default_factory=list)
    observacoes: list[str] = Field(default_factory=list)
    confirmado_por: str | None = None
    confirmado_em: datetime | None = None
    valor_confirmado: str | None = None
    detalhes_confirmados: dict[str, str] | None = None

    def valor_vigente(self) -> str | None:
        return self.valor_confirmado if self.valor_confirmado is not None else self.valor

    def detalhes_vigentes(self) -> dict[str, str]:
        return self.detalhes_confirmados if self.detalhes_confirmados is not None else self.detalhes


class TipoOcorrencia(str, Enum):
    DOCUMENTO_AUSENTE = "documento ausente"
    CONTRADICAO = "valores contraditórios"
    INSUFICIENTE = "informação insuficiente"
    DIVERGENCIA = "divergência de cálculo"
    OCR = "página sem texto (OCR)"
    CLASSIFICACAO = "classificação incerta"
    ALEGACAO_NAO_RECONHECIDA = "alegação não reconhecida no título"
    FUNDAMENTACAO_SEM_DISPOSITIVO = "tema só na fundamentação"
    MODIFICACAO = "modificação por decisão posterior"
    INFORMACAO = "informação"


class Ocorrencia(BaseModel):
    id: str
    tipo: TipoOcorrencia
    texto: str
    bloqueia: bool
    fontes: list[Fonte] = Field(default_factory=list)
    ciencia_por: str | None = None
    ciencia_em: datetime | None = None


class PagamentoExtraido(BaseModel):
    parcela: int | None
    vencimento: date | None
    data_pagamento: date | None
    valor: str | None
    encargos: str | None = None
    fonte: Fonte
    lacunas: list[str] = Field(default_factory=list)


class ResumoDocumento(BaseModel):
    id: str
    arquivo: str
    tipo: TipoDocumento
    paginas: str
    data: date | None
    confianca: float
    sha256: str


class QuadroParametros(BaseModel):
    caso_id: str
    gerado_em: datetime
    versao_extrator: str
    documentos: list[ResumoDocumento]
    parametros: dict[str, Parametro]
    pagamentos: list[PagamentoExtraido]
    pagamentos_status: StatusParametro
    pagamentos_confirmados_por: str | None = None
    pagamentos_confirmados_em: datetime | None = None
    comandos_vigentes: list[Comando]
    modificacoes: list[Modificacao]
    alegacoes: list[Comando]
    ocorrencias: list[Ocorrencia]
    avisos_leitura: list[str]
