"""Leitura do número único CNJ.

    NNNNNNN-DD.AAAA.J.TR.OOOO
    │       │  │    │ │  └── unidade de origem
    │       │  │    │ └───── tribunal
    │       │  │    └─────── segmento (8 = Justiça Estadual, 4 = Federal)
    │       │  └──────────── ANO DE AJUIZAMENTO
    │       └─────────────── dígito verificador
    └─────────────────────── número sequencial

O ano e o tribunal vêm de graça no próprio número. Usá-los evita dois erros
caros medidos na carga real de 18/08/2026:

  · um processo de 1984 foi classificado como CRÍTICO, porque a régua olhava a
    data de publicação no diário e não a de ajuizamento;
  · 75% dos processos encontrados estavam em estado diferente do do cliente —
    sinal forte de homônimo.
"""
import datetime

TR_PARA_SIGLA = {
    "01": "TJAC", "02": "TJAL", "03": "TJAP", "04": "TJAM", "05": "TJBA",
    "06": "TJCE", "07": "TJDFT", "08": "TJES", "09": "TJGO", "10": "TJMA",
    "11": "TJMT", "12": "TJMS", "13": "TJMG", "14": "TJPA", "15": "TJPB",
    "16": "TJPR", "17": "TJPE", "18": "TJPI", "19": "TJRJ", "20": "TJRN",
    "21": "TJRS", "22": "TJRO", "23": "TJRR", "24": "TJSC", "25": "TJSE",
    "26": "TJSP", "27": "TJTO",
}
SIGLA_PARA_UF = {
    "TJAC": "AC", "TJAL": "AL", "TJAP": "AP", "TJAM": "AM", "TJBA": "BA",
    "TJCE": "CE", "TJDFT": "DF", "TJES": "ES", "TJGO": "GO", "TJMA": "MA",
    "TJMT": "MT", "TJMS": "MS", "TJMG": "MG", "TJPA": "PA", "TJPB": "PB",
    "TJPR": "PR", "TJPE": "PE", "TJPI": "PI", "TJRJ": "RJ", "TJRN": "RN",
    "TJRS": "RS", "TJRO": "RO", "TJRR": "RR", "TJSC": "SC", "TJSP": "SP",
    "TJSE": "SE", "TJTO": "TO",
}
ESTADUAL = "8"


def digitos(numero):
    return "".join(c for c in str(numero or "") if c.isdigit())


def ano(numero):
    """Ano de ajuizamento, ou None se o número não for um CNJ válido."""
    d = digitos(numero)
    if len(d) != 20:
        return None
    valor = int(d[9:13])
    if 1900 <= valor <= datetime.date.today().year + 1:
        return valor
    return None


def segmento(numero):
    d = digitos(numero)
    return d[13] if len(d) == 20 else ""


def sigla(numero):
    """Sigla do tribunal estadual, ou '' fora da Justiça Estadual."""
    d = digitos(numero)
    if len(d) != 20 or d[13] != ESTADUAL:
        return ""
    return TR_PARA_SIGLA.get(d[14:16], "")


def uf(numero):
    return SIGLA_PARA_UF.get(sigla(numero), "")


def eh_estadual(numero):
    return segmento(numero) == ESTADUAL
