"""Base numérica do motor: Decimal, precisão e política de arredondamento.

Regras
------
1. Todo valor monetário ou taxa é ``decimal.Decimal``. ``float`` é recusado
   (``D(0.1)`` levanta ``TypeError``), porque 0.1 em ponto flutuante não é 0.1.
2. Cálculos intermediários usam 34 dígitos significativos (IEEE 754 decimal128)
   e NÃO são arredondados, salvo quando a política declarada mandar.
3. O arredondamento é sempre explícito, feito por ``arredondar`` com uma
   ``PoliticaArredondamento`` que vai impressa no relatório.
"""

from __future__ import annotations

import decimal
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

PRECISAO_INTERNA = 34

CONTEXTO = decimal.Context(
    prec=PRECISAO_INTERNA,
    rounding=decimal.ROUND_HALF_EVEN,
    Emin=-999999,
    Emax=999999,
    traps=[decimal.InvalidOperation, decimal.DivisionByZero, decimal.Overflow],
)
decimal.setcontext(CONTEXTO)
decimal.DefaultContext.prec = PRECISAO_INTERNA
decimal.DefaultContext.traps[decimal.InvalidOperation] = True
decimal.DefaultContext.traps[decimal.DivisionByZero] = True

ZERO = Decimal(0)
UM = Decimal(1)
CEM = Decimal(100)
CENTAVO = Decimal("0.01")


def D(valor: Decimal | int | str) -> Decimal:
    """Converte para Decimal recusando float."""
    if isinstance(valor, bool):
        raise TypeError("bool não é valor numérico")
    if isinstance(valor, float):
        raise TypeError(
            f"float recusado ({valor!r}): informe o valor como texto, ex. D('{valor}')"
        )
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, (int, str)):
        return Decimal(str(valor).strip().replace(" ", ""))
    raise TypeError(f"tipo não suportado: {type(valor).__name__}")


def pct(valor: Decimal | int | str) -> Decimal:
    """Percentual para fração: pct('1,99') -> 0.0199. Aceita vírgula decimal."""
    if isinstance(valor, str):
        valor = valor.replace(".", "").replace(",", ".") if "," in valor else valor
    return D(valor) / CEM


class ModoArredondamento(str, Enum):
    MEIO_PARA_CIMA = "HALF_UP"        # 0,005 -> 0,01 (usual em sistemas bancários)
    MEIO_PARA_PAR = "HALF_EVEN"       # "do banqueiro"
    TRUNCAR = "DOWN"                  # despreza a fração
    PARA_CIMA = "UP"

    @property
    def constante(self) -> str:
        return {
            "HALF_UP": decimal.ROUND_HALF_UP,
            "HALF_EVEN": decimal.ROUND_HALF_EVEN,
            "DOWN": decimal.ROUND_DOWN,
            "UP": decimal.ROUND_UP,
        }[self.value]


class PoliticaArredondamento(BaseModel):
    """Como e quando arredondar. Não há padrão implícito: o caso declara."""

    model_config = ConfigDict(frozen=True)

    casas: int = Field(default=2, ge=0, le=20)
    """Limite de 20 casas para caber na precisão interna de 34 dígitos."""
    modo: ModoArredondamento
    arredondar_cada_parcela: bool
    """True: juros/amortização de cada parcela são arredondados ao centavo
    (como fazem os sistemas bancários). False: só o total final."""
    arredondar_prestacao: bool = True
    """True (padrão): a prestação calculada é arredondada às ``casas`` (valor cobrável).
    False: precisão integral — a prestação segue com todos os dígitos (comparação técnica)."""

    @classmethod
    def integral(cls, casas: int = 2, modo: "ModoArredondamento" = None) -> "PoliticaArredondamento":
        """Precisão integral: nada é arredondado antes do resultado final."""
        return cls(casas=casas, modo=modo or ModoArredondamento.MEIO_PARA_CIMA, arredondar_cada_parcela=False,
                   arredondar_prestacao=False)

    @classmethod
    def de_texto(cls, texto: str) -> "PoliticaArredondamento":
        """'casas;modo;quando' — quando: por_parcela | final | integral (ex.: '2;HALF_UP;integral')."""
        try:
            casas, modo, quando = [p.strip() for p in texto.split(";")]
        except ValueError as e:
            raise ValueError(f"política de arredondamento inválida: {texto!r} (use casas;modo;quando)") from e
        if quando not in ("por_parcela", "final", "integral"):
            raise ValueError(f"'quando' deve ser por_parcela, final ou integral: {quando!r}")
        return cls(casas=int(casas), modo=ModoArredondamento(modo), arredondar_cada_parcela=quando == "por_parcela",
                   arredondar_prestacao=quando != "integral")

    def descricao(self) -> str:
        if not self.arredondar_cada_parcela and not self.arredondar_prestacao:
            quando = "precisão integral (prestação, juros e saldos sem arredondamento; só o resultado final)"
        else:
            quando = "a cada parcela/evento" if self.arredondar_cada_parcela else "apenas no resultado final"
            if not self.arredondar_prestacao:
                quando += "; prestação sem arredondamento"
        return f"{self.casas} casas, modo {self.modo.value}, {quando}; intermediários com {PRECISAO_INTERNA} dígitos"


def arredondar(valor: Decimal, politica: PoliticaArredondamento) -> Decimal:
    quantum = Decimal(1).scaleb(-politica.casas)
    return valor.quantize(quantum, rounding=politica.modo.constante)


def arredondar_prestacao(valor: Decimal, politica: PoliticaArredondamento) -> Decimal:
    return arredondar(valor, politica) if politica.arredondar_prestacao else valor


def arredondar_se_parcela(valor: Decimal, politica: PoliticaArredondamento) -> Decimal:
    return arredondar(valor, politica) if politica.arredondar_cada_parcela else valor


def potencia(base: Decimal, expoente: Decimal | int) -> Decimal:
    """base ** expoente com expoente fracionário (ex.: dias/30) em Decimal."""
    if base <= 0:
        raise ValueError("base de potência deve ser positiva")
    return base ** D(expoente)


def brl(valor: Decimal) -> str:
    """Formata em padrão brasileiro, sem arredondar além de 2 casas (só exibição)."""
    q = valor.quantize(CENTAVO, rounding=decimal.ROUND_HALF_UP)
    s = f"{q:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")
