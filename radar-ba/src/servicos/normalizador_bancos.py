"""Identificação e normalização da instituição financeira do polo ativo.

O mesmo banco aparece no processo com dezenas de grafias:
    "BANCO VOTORANTIM S.A." / "BANCO BV S/A" / "BV FINANCEIRA S.A. CFI"
Todas devem virar   BANCO BV.

A ordem das regras importa: padrões mais específicos são testados primeiro,
para que "BRADESCO FINANCIAMENTOS" não seja capturado por "BRADESCO".
"""
import re
import unicodedata

# (nome canônico, [padrões]) — avaliados em ordem; o primeiro que casar vence.
_REGRAS = [
    ("BANCO BV",            [r"\bBV\s+FINANCEIRA\b", r"\bBANCO\s+BV\b", r"\bVOTORANTIM\b", r"\bBV\s+S[/.]?A\b"]),
    ("BANCO ITAUCARD",      [r"\bITAUCARD\b", r"\bITAU\s*CARD\b"]),
    ("BANCO ITAÚ",          [r"\bITAU\s*UNIBANCO\b", r"\bBANCO\s+ITAU\b", r"\bITAU\b", r"\bUNIBANCO\b"]),
    ("BRADESCO FINANCIAMENTOS", [r"BRADESCO\s+FINANCIAMENTOS", r"\bBANCO\s+FINASA\b", r"\bFINASA\b"]),
    ("BANCO BRADESCO",      [r"\bBRADESCO\b"]),
    ("AYMORÉ",              [r"\bAYMOR[EÉ]\b", r"AYMORE\s+CR[EÉ]DITO"]),
    ("BANCO SANTANDER",     [r"\bSANTANDER\b"]),
    ("BANCO PAN",           [r"\bBANCO\s+PAN\b", r"\bPANAMERICANO\b", r"\bPAN\s+S[/.]?A\b"]),
    ("BANCO VOLKSWAGEN",    [r"\bVOLKSWAGEN\b", r"\bVOLKS\b", r"\bVW\b"]),
    ("BANCO TOYOTA",        [r"\bTOYOTA\b"]),
    ("BANCO HONDA",         [r"\bHONDA\b"]),
    ("BANCO GM",            [r"\bBANCO\s+GM\b", r"\bGENERAL\s+MOTORS\b", r"\bCHEVROLET\s+SERVI"]),
    ("BANCO SAFRA",         [r"\bSAFRA\b"]),
    ("BANCO DAYCOVAL",      [r"\bDAYCOVAL\b"]),
    ("OMNI",                [r"\bOMNI\b"]),
    ("C6 BANK",             [r"\bC6\s*BANK\b", r"\bBANCO\s+C6\b", r"\bC6\s+CONSIGNADO\b"]),
    ("BANCO DIGIMAIS",      [r"\bDIGIMAIS\b", r"\bBANCO\s+RENDIMENTO\b"]),
    ("PORTOSEG",            [r"\bPORTOSEG\b", r"\bPORTO\s+SEGURO\b"]),
    ("BANCO MERCEDES-BENZ", [r"\bMERCEDES\b"]),
    ("BANCO FORD",          [r"\bBANCO\s+FORD\b", r"\bFORD\s+MOTOR\s+CREDIT\b"]),
    ("BANCO RCI / RENAULT", [r"\bRCI\b", r"\bRENAULT\b"]),
    ("BANCO HYUNDAI",       [r"\bHYUNDAI\b"]),
    ("BANCO FIAT / STELLANTIS", [r"\bSTELLANTIS\b", r"\bBANCO\s+FIAT\b", r"\bFIDIS\b"]),
    ("BANCO DO BRASIL",     [r"\bBANCO\s+DO\s+BRASIL\b", r"\bBB\s+FINANCEIRA\b"]),
    ("CAIXA ECONÔMICA FEDERAL", [r"\bCAIXA\s+ECONOMICA\b", r"\bCEF\b"]),
    ("BANCO SICREDI",       [r"\bSICREDI\b"]),
    ("BANCO SICOOB",        [r"\bSICOOB\b"]),
    ("BANCO INTER",         [r"\bBANCO\s+INTER\b"]),
    ("BANCO ORIGINAL",      [r"\bBANCO\s+ORIGINAL\b"]),
    ("BANCO SEMEAR",        [r"\bSEMEAR\b"]),
    ("CREFISA",             [r"\bCREFISA\b"]),
    ("BANCO MERCANTIL",     [r"\bMERCANTIL\s+DO\s+BRASIL\b"]),
]

_COMPILADAS = [(nome, [re.compile(p) for p in padroes]) for nome, padroes in _REGRAS]

# Fundos e securitizadoras: não são "o banco", mas indicam crédito cedido.
_FUNDO = re.compile(
    r"(FUNDO\s+DE\s+INVESTIMENTO|\bFIDC\b|SECURITIZADORA|\bCREDITOS?\s+FINANCEIROS?\b)")

# Sufixos societários que não ajudam a identificar.
_RUIDO = re.compile(
    r"\b(S[/.]?A|SA|LTDA|EPP|ME|CFI|CREDITO,?\s+FINANCIAMENTO\s+E\s+INVESTIMENTO|"
    r"ARRENDAMENTO\s+MERCANTIL|BANCO\s+MULTIPLO|COMPANHIA|CIA)\b\.?")


def _limpar(texto):
    t = unicodedata.normalize("NFKD", str(texto or "").upper())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9\s/.-]", " ", t)).strip()


def normalizar_banco(nome_parte):
    """Devolve o nome canônico do banco, ou "" se não for instituição conhecida."""
    limpo = _limpar(nome_parte)
    if not limpo:
        return ""
    for canonico, padroes in _COMPILADAS:
        for p in padroes:
            if p.search(limpo):
                return canonico
    return ""


def eh_instituicao_financeira(nome_parte):
    """Heurística mais larga: reconhece banco não catalogado, fundo, financeira."""
    if normalizar_banco(nome_parte):
        return True
    limpo = _limpar(nome_parte)
    if _FUNDO.search(limpo):
        return True
    return bool(re.search(r"\b(BANCO|FINANCEIRA|CREDITO|LEASING|CONSORCIO|"
                          r"ADMINISTRADORA\s+DE\s+CONSORCIO|COOPERATIVA\s+DE\s+CREDITO)\b", limpo))


def descrever(nome_parte):
    """Rótulo para o alerta: nome canônico, ou o nome limpo se for desconhecido."""
    canonico = normalizar_banco(nome_parte)
    if canonico:
        return canonico
    limpo = _limpar(nome_parte)
    if _FUNDO.search(limpo):
        return re.sub(_RUIDO, "", limpo).strip(" .-") + " (fundo/securitizadora)"
    if eh_instituicao_financeira(nome_parte):
        return re.sub(_RUIDO, "", limpo).strip(" .-")
    return ""
