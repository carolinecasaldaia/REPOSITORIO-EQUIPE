"""Contrato comum a todos os provedores de fonte judicial.

Equivale à interface JudicialProvider da especificação. Em Python usamos uma
classe base abstrata — o contrato é o mesmo:

    buscar_por_cpf(cpf)        -> List[ResultadoProcesso]
    buscar_por_nome(nome)      -> List[ResultadoProcesso]
    detalhar(numero_processo)  -> Optional[DetalheProcesso]
    verificar_saude()          -> bool

Provedor que não puder consultar por CPF de forma automatizada e lícita
devolve ResultadoProcesso com status MANUAL_REVIEW_REQUIRED. Nunca contorna
a limitação.
"""
import abc
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# --- status de casamento (item 21 da especificação) ---------------------
CONFIRMADO = "CONFIRMED_MATCH"            # identidade confirmada por CPF
POSSIVEL = "POSSIBLE_MATCH"               # bate por nome; pode ser homônimo
REVISAO_MANUAL = "MANUAL_REVIEW_REQUIRED"  # fonte não permite conferência automática


@dataclass
class ResultadoProcesso:
    numero_processo: str = ""
    tribunal: str = ""
    grau: str = ""
    classe_codigo: Optional[int] = None
    classe_nome: str = ""
    assunto: str = ""
    orgao_julgador: str = ""
    comarca: str = ""
    uf: str = ""
    autor: str = ""                 # polo ativo (o banco, em busca e apreensão)
    reu: str = ""                   # polo passivo (o cliente)
    banco_normalizado: str = ""
    data_distribuicao: Optional[str] = None    # ISO aaaa-mm-dd
    ano_ajuizamento: Optional[int] = None      # vem do próprio número CNJ
    data_publicacao: Optional[str] = None      # data no DJEN
    ultima_movimentacao: str = ""
    fonte: str = ""
    status_casamento: str = POSSIVEL
    confianca: float = 0.0
    motivo: str = ""
    cliente_id: Optional[str] = None
    bruto: Dict = field(default_factory=dict, repr=False)

    @property
    def chave(self):
        """Chave de deduplicação: numeroCNJ + cliente (item 11)."""
        return "%s|%s" % (so_digitos(self.numero_processo), self.cliente_id or "")


@dataclass
class DetalheProcesso:
    numero_processo: str = ""
    tribunal: str = ""
    classe_codigo: Optional[int] = None
    classe_nome: str = ""
    assuntos: List[str] = field(default_factory=list)
    orgao_julgador: str = ""
    data_distribuicao: Optional[str] = None
    movimentos: List[Dict] = field(default_factory=list)
    sistema: str = ""
    fonte: str = ""


def so_digitos(texto):
    return "".join(c for c in str(texto or "") if c.isdigit())


class ProvedorJudicial(abc.ABC):
    """Base de todo provedor. `nome` e `cobertura` servem ao painel e ao log."""

    nome = "base"
    cobertura = []          # siglas de tribunais atendidos; [] = nacional
    permite_cpf = False     # consulta automatizada por CPF é lícita e possível?

    @abc.abstractmethod
    def verificar_saude(self):
        """True se a fonte respondeu. Não lança exceção."""

    def buscar_por_cpf(self, cpf, **kw):
        """Padrão seguro: quem não implementa devolve revisão manual."""
        return [ResultadoProcesso(
            fonte=self.nome,
            status_casamento=REVISAO_MANUAL,
            motivo="%s não permite consulta automatizada por CPF" % self.nome,
        )]

    def buscar_por_nome(self, nome, **kw):
        return []

    def detalhar(self, numero_processo, tribunal=None):
        return None
